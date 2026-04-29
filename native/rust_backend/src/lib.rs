//! Python extension module entry point.
//!
//! Exposes `create_sender`, `start_sender`, `stop_sender`, and
//! `prepare_frame` to Python via PyO3.
//!
//! The config dict received from Python matches the output of
//! ``sender.backends.native_backend.flatten_config_for_native``.

mod errors;
mod sender;
mod serializer;
mod testgen;
mod transport;

use pyo3::prelude::*;
use pyo3::types::{PyBool, PyDict, PyFloat, PyInt, PyList, PyString};
use std::collections::HashMap;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};

use sender::{NativeSender, SenderConfig, SharedMetrics};
use serializer::{FieldDescriptor, FieldValue};
use transport::{LoopbackTransport, NpcapTransport};

/// Opaque handle stored behind a raw pointer.
/// Keeps the stop flag and metrics accessible without locking the sender mutex.
struct SenderHandle {
    sender: Arc<Mutex<NativeSender>>,
    stop_flag: Arc<AtomicBool>,
    metrics: Arc<SharedMetrics>,
}

// ---- Helper: extract typed values from PyDict --------------------------

fn extract_string(dict: &Bound<'_, PyDict>, key: &str) -> PyResult<String> {
    dict.get_item(key)?
        .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err(key.to_string()))?
        .extract::<String>()
}

fn extract_u16(dict: &Bound<'_, PyDict>, key: &str) -> PyResult<u16> {
    dict.get_item(key)?
        .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err(key.to_string()))?
        .extract::<u16>()
}

fn extract_u32(dict: &Bound<'_, PyDict>, key: &str) -> PyResult<u32> {
    dict.get_item(key)?
        .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err(key.to_string()))?
        .extract::<u32>()
}

fn extract_u64(dict: &Bound<'_, PyDict>, key: &str) -> PyResult<u64> {
    dict.get_item(key)?
        .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err(key.to_string()))?
        .extract::<u64>()
}

fn extract_f64(dict: &Bound<'_, PyDict>, key: &str) -> PyResult<f64> {
    let item = dict
        .get_item(key)?
        .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err(key.to_string()))?;
    // Accept both int and float from Python
    if let Ok(v) = item.extract::<f64>() {
        return Ok(v);
    }
    if let Ok(v) = item.extract::<i64>() {
        return Ok(v as f64);
    }
    Err(pyo3::exceptions::PyTypeError::new_err(format!(
        "Expected float for '{key}'"
    )))
}

/// Convert a Python field value (from fixed_values dict) into a Rust FieldValue,
/// guided by the field type string.
fn py_value_to_field_value(
    py: Python<'_>,
    obj: &Bound<'_, PyAny>,
    field_type: &str,
) -> PyResult<FieldValue> {
    match field_type {
        "INTEGER" => {
            let v = obj.extract::<u64>()?;
            Ok(FieldValue::Integer(v))
        }
        "STRING" => {
            let v = obj.extract::<String>()?;
            Ok(FieldValue::Str(v))
        }
        "BOOLEAN" => {
            let v = obj.is_truthy()?;
            Ok(FieldValue::Bool(v))
        }
        "RAW_BYTES" => {
            // Python adapter sends hex string for bytes values
            if let Ok(s) = obj.extract::<String>() {
                Ok(FieldValue::Str(s)) // serializer handles hex-string RAW_BYTES
            } else if let Ok(b) = obj.extract::<Vec<u8>>() {
                Ok(FieldValue::RawBytes(b))
            } else {
                Err(pyo3::exceptions::PyTypeError::new_err(
                    "RAW_BYTES: expected str or bytes",
                ))
            }
        }
        _ => Err(pyo3::exceptions::PyValueError::new_err(format!(
            "Unknown field type '{field_type}'"
        ))),
    }
}

/// Parse the config dict into a SenderConfig + transport.
fn parse_config(py: Python<'_>, config: &Bound<'_, PyDict>) -> PyResult<SenderConfig> {
    let interface = extract_string(config, "interface")?;
    let dst_mac_str = extract_string(config, "dst_mac")?;
    let src_mac_str = extract_string(config, "src_mac")?;
    let ethertype = extract_u16(config, "ethertype")
        .or_else(|_| config.get_item("ethertype")?.unwrap().extract::<u32>().map(|v| v as u16))?;
    let stream_id = extract_u32(config, "stream_id")?;
    let pps = extract_u64(config, "pps")?;
    let packet_count = extract_u64(config, "packet_count")?;
    let duration_sec = extract_f64(config, "duration_sec").unwrap_or(0.0);
    let generation_mode = extract_string(config, "generation_mode")?;

    let dst_mac = sender::parse_mac(&dst_mac_str)
        .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))?;
    let src_mac = sender::parse_mac(&src_mac_str)
        .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))?;

    // Parse fields list
    let fields_list = config
        .get_item("fields")?
        .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err("fields"))?;
    let fields_list = fields_list.downcast::<PyList>()?;

    let mut fields = Vec::with_capacity(fields_list.len());
    let mut field_types: Vec<String> = Vec::with_capacity(fields_list.len());
    for item in fields_list.iter() {
        let fdict = item.downcast::<PyDict>()?;
        let name = extract_string(fdict, "name")?;
        let ftype = extract_string(fdict, "type")?;
        let bit_length = fdict
            .get_item("bit_length")?
            .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err("bit_length"))?
            .extract::<usize>()?;
        field_types.push(ftype.clone());
        fields.push(FieldDescriptor {
            name,
            field_type: ftype,
            bit_length,
        });
    }

    // Parse fixed_values dict
    let fixed_values_obj = config
        .get_item("fixed_values")?
        .ok_or_else(|| pyo3::exceptions::PyKeyError::new_err("fixed_values"))?;
    let fixed_values_dict = fixed_values_obj.downcast::<PyDict>()?;

    let mut values = Vec::with_capacity(fields.len());
    for (i, fd) in fields.iter().enumerate() {
        let val_obj = fixed_values_dict
            .get_item(&fd.name)?
            .ok_or_else(|| {
                pyo3::exceptions::PyKeyError::new_err(format!(
                    "Missing fixed value for field '{}'",
                    fd.name
                ))
            })?;
        values.push(py_value_to_field_value(py, &val_obj, &field_types[i])?);
    }

    Ok(SenderConfig {
        interface,
        dst_mac,
        src_mac,
        ethertype,
        stream_id,
        pps,
        packet_count,
        duration_sec,
        generation_mode,
        fields,
        values,
    })
}

// ---- Exported Python functions -----------------------------------------

/// Create a new sender handle from a Python config dict.
///
/// The config dict must contain all keys produced by
/// ``flatten_config_for_native()`` on the Python side.
///
/// If ``use_loopback`` is true, frame transmission uses an in-memory
/// loopback transport (testing only).  Otherwise the real Npcap/libpcap
/// transport is used.
#[pyfunction]
#[pyo3(signature = (config, use_loopback = false))]
fn create_sender(py: Python<'_>, config: &Bound<'_, PyDict>, use_loopback: bool) -> PyResult<u64> {
    let cfg = parse_config(py, config)?;
    let transport: Box<dyn transport::FrameTransport> = if use_loopback {
        Box::new(LoopbackTransport::new())
    } else {
        Box::new(NpcapTransport::new())
    };
    let native_sender = NativeSender::new(cfg, transport);
    let stop_flag = native_sender.stop_flag();
    let metrics = native_sender.shared_metrics();
    let handle = SenderHandle {
        sender: Arc::new(Mutex::new(native_sender)),
        stop_flag,
        metrics,
    };
    let boxed = Box::new(handle);
    let ptr = Box::into_raw(boxed) as u64;
    Ok(ptr)
}

/// Start the sender.  Blocks until finished or stopped.
/// Releases the GIL so the GUI thread stays responsive and
/// `stop_sender` can be called from another Python thread.
#[pyfunction]
fn start_sender(
    py: Python<'_>,
    handle: u64,
    _progress_interval: f64,
) -> PyResult<HashMap<String, u64>> {
    let sender_handle = unsafe { &*(handle as *const SenderHandle) };
    let sender_arc = sender_handle.sender.clone();

    // Release the GIL for the entire send loop so the GUI stays
    // responsive and stop_sender can be called from another thread.
    let result = py.allow_threads(move || {
        let mut sender = sender_arc
            .lock()
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;
        sender
            .run()
            .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))
    })?;
    Ok(result)
}

/// Request a running sender to stop.
/// Does NOT acquire the sender mutex — uses the atomic stop flag directly,
/// so it can be called safely while `start_sender` is running.
#[pyfunction]
fn stop_sender(_py: Python<'_>, handle: u64) -> PyResult<()> {
    let sender_handle = unsafe { &*(handle as *const SenderHandle) };
    sender_handle.stop_flag.store(true, Ordering::Relaxed);
    Ok(())
}

/// Destroy a sender handle and free memory.
#[pyfunction]
fn destroy_sender(_py: Python<'_>, handle: u64) -> PyResult<()> {
    if handle == 0 {
        return Ok(());
    }
    unsafe {
        let _ = Box::from_raw(handle as *mut SenderHandle);
    }
    Ok(())
}

/// Read the current metrics from an active sender without blocking the send loop.
/// Safe to call while `start_sender` is running from another thread.
#[pyfunction]
fn get_sender_metrics(_py: Python<'_>, handle: u64) -> PyResult<HashMap<String, u64>> {
    let sender_handle = unsafe { &*(handle as *const SenderHandle) };
    Ok(sender_handle.metrics.snapshot())
}

/// Build a single frame deterministically (for cross-checking with Python).
///
/// Returns frame bytes.
#[pyfunction]
fn prepare_frame(
    py: Python<'_>,
    config: &Bound<'_, PyDict>,
    sequence: u64,
    timestamp_ns: u64,
) -> PyResult<Vec<u8>> {
    let cfg = parse_config(py, config)?;
    let transport = Box::new(LoopbackTransport::new());
    let sender = NativeSender::new(cfg, transport);
    let frame = sender
        .prepare_frame(sequence, timestamp_ns)
        .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))?;
    Ok(frame)
}

/// Check whether real NIC transport (Npcap/libpcap) is available.
#[pyfunction]
fn is_transport_available() -> bool {
    NpcapTransport::is_available()
}

/// List network interfaces visible to the pcap library.
///
/// Returns a list of ``(device_name, description)`` tuples.
#[pyfunction]
fn list_interfaces() -> PyResult<Vec<(String, String)>> {
    NpcapTransport::list_interfaces()
        .map_err(|e| pyo3::exceptions::PyRuntimeError::new_err(e.to_string()))
}

/// The Python module definition.
#[pymodule]
fn trafic_native(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("__version__", "0.1.0")?;
    m.add_function(wrap_pyfunction!(create_sender, m)?)?;
    m.add_function(wrap_pyfunction!(start_sender, m)?)?;
    m.add_function(wrap_pyfunction!(stop_sender, m)?)?;
    m.add_function(wrap_pyfunction!(destroy_sender, m)?)?;
    m.add_function(wrap_pyfunction!(get_sender_metrics, m)?)?;
    m.add_function(wrap_pyfunction!(prepare_frame, m)?)?;
    m.add_function(wrap_pyfunction!(is_transport_available, m)?)?;
    m.add_function(wrap_pyfunction!(list_interfaces, m)?)?;
    Ok(())
}
