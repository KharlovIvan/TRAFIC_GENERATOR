//! Native sender — builds and sends raw Ethernet / TestGen / UserPayload frames.
//!
//! Mirrors the Python `sender.sender_engine` + `sender.frame_builder` modules.
//! The sender constructs complete L2 frames in memory and sends them via a
//! transport abstraction.  On systems with Npcap/libpcap the frames go out at
//! L2 through a real NIC; a loopback transport is available for testing only.

use std::collections::HashMap;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

use crate::errors::NativeError;
use crate::serializer::{build_user_payload, FieldDescriptor, FieldValue};
use crate::testgen::{build_testgen_header, current_timestamp_ns, TESTGEN_HEADER_SIZE, TESTGEN_MAGIC, TESTGEN_VERSION};
use crate::transport::FrameTransport;

/// Spin only for the last 200 µs of a wait — sleep the rest.
const SPIN_THRESHOLD: Duration = Duration::from_micros(200);

/// Number of payloads pre-generated for RANDOM pool mode.
const POOL_SIZE: usize = 256;

// ---- Shared metrics (lock-free) ----------------------------------------

/// Metrics that are updated atomically during the send loop so they can be
/// read from another thread (the Python progress-polling thread) without
/// acquiring the sender mutex.
pub struct SharedMetrics {
    pub packets_attempted: AtomicU64,
    pub packets_sent: AtomicU64,
    pub packets_failed: AtomicU64,
    pub bytes_sent: AtomicU64,
    pub first_tx_timestamp_ns: AtomicU64,
    pub last_tx_timestamp_ns: AtomicU64,
}

impl SharedMetrics {
    pub fn new() -> Self {
        Self {
            packets_attempted: AtomicU64::new(0),
            packets_sent: AtomicU64::new(0),
            packets_failed: AtomicU64::new(0),
            bytes_sent: AtomicU64::new(0),
            first_tx_timestamp_ns: AtomicU64::new(0),
            last_tx_timestamp_ns: AtomicU64::new(0),
        }
    }

    pub fn snapshot(&self) -> HashMap<String, u64> {
        let mut m = HashMap::new();
        m.insert("packets_attempted".into(), self.packets_attempted.load(Ordering::Relaxed));
        m.insert("packets_sent".into(), self.packets_sent.load(Ordering::Relaxed));
        m.insert("packets_failed".into(), self.packets_failed.load(Ordering::Relaxed));
        m.insert("bytes_sent".into(), self.bytes_sent.load(Ordering::Relaxed));
        m.insert("first_tx_timestamp_ns".into(), self.first_tx_timestamp_ns.load(Ordering::Relaxed));
        m.insert("last_tx_timestamp_ns".into(), self.last_tx_timestamp_ns.load(Ordering::Relaxed));
        m
    }
}

// ---- Ethernet helpers --------------------------------------------------

pub const ETHERNET_HEADER_SIZE: usize = 14; // 6 dst + 6 src + 2 ethertype

/// Parse a MAC address string ("aa:bb:cc:dd:ee:ff") into 6 bytes.
pub fn parse_mac(mac: &str) -> Result<[u8; 6], NativeError> {
    let parts: Vec<&str> = mac.split(':').collect();
    if parts.len() != 6 {
        return Err(NativeError::FrameBuild(format!(
            "Invalid MAC '{}': expected 6 colon-separated octets",
            mac
        )));
    }
    let mut bytes = [0u8; 6];
    for (i, part) in parts.iter().enumerate() {
        bytes[i] = u8::from_str_radix(part, 16).map_err(|_| {
            NativeError::FrameBuild(format!("Invalid MAC octet '{part}' in '{mac}'"))
        })?;
    }
    Ok(bytes)
}

/// Build a 14-byte Ethernet header.
pub fn build_ethernet_header(
    dst_mac: &[u8; 6],
    src_mac: &[u8; 6],
    ethertype: u16,
) -> [u8; ETHERNET_HEADER_SIZE] {
    let mut hdr = [0u8; ETHERNET_HEADER_SIZE];
    hdr[0..6].copy_from_slice(dst_mac);
    hdr[6..12].copy_from_slice(src_mac);
    hdr[12..14].copy_from_slice(&ethertype.to_be_bytes());
    hdr
}

// ---- Frame template (pre-allocated, patch-in-place) --------------------

/// A pre-built frame buffer where only sequence and timestamp change per packet.
///
/// The full frame (Ethernet + TestGen + UserPayload) is allocated once.
/// Each call to `stamp` patches the two mutable 8-byte fields in-place —
/// no Vec allocation happens in the hot loop.
pub struct FrameTemplate {
    /// Complete frame bytes: Ethernet(14) + TestGen(28) + UserPayload.
    pub frame: Vec<u8>,
    /// Byte offset of the 8-byte sequence number field.
    pub sequence_offset: usize,
    /// Byte offset of the 8-byte tx_timestamp_ns field.
    pub timestamp_offset: usize,
}

impl FrameTemplate {
    /// Build the template from the immutable configuration parts.
    pub fn new(
        eth_header: &[u8; ETHERNET_HEADER_SIZE],
        stream_id: u32,
        user_payload: &[u8],
    ) -> Self {
        let payload_len = user_payload.len() as u32;
        let total = ETHERNET_HEADER_SIZE + TESTGEN_HEADER_SIZE + user_payload.len();
        let mut frame = Vec::with_capacity(total);

        // Ethernet header
        frame.extend_from_slice(eth_header);

        // TestGen header — static fields first, then placeholder zeros for the
        // two mutable fields (sequence and timestamp).
        let tg_start = frame.len(); // = ETHERNET_HEADER_SIZE
        frame.extend_from_slice(&TESTGEN_MAGIC.to_be_bytes()); // [0..2]
        frame.push(TESTGEN_VERSION);                            // [2]
        frame.push(0u8);                                        // [3] flags
        frame.extend_from_slice(&stream_id.to_be_bytes());      // [4..8]
        let sequence_offset = tg_start + 8;
        frame.extend_from_slice(&0u64.to_be_bytes());           // [8..16]  sequence placeholder
        let timestamp_offset = tg_start + 16;
        frame.extend_from_slice(&0u64.to_be_bytes());           // [16..24] timestamp placeholder
        frame.extend_from_slice(&payload_len.to_be_bytes());    // [24..28]

        // User payload
        frame.extend_from_slice(user_payload);

        Self { frame, sequence_offset, timestamp_offset }
    }

    /// Patch sequence and timestamp in-place.  Zero-allocation hot path.
    #[inline]
    pub fn stamp(&mut self, sequence: u64, timestamp_ns: u64) {
        self.frame[self.sequence_offset..self.sequence_offset + 8]
            .copy_from_slice(&sequence.to_be_bytes());
        self.frame[self.timestamp_offset..self.timestamp_offset + 8]
            .copy_from_slice(&timestamp_ns.to_be_bytes());
    }
}

// ---- Payload pool for RANDOM mode --------------------------------------

/// A pre-generated pool of random payloads rotated through in the send loop.
/// Avoids per-packet RNG calls in the hot path.
struct PayloadPool {
    payloads: Vec<Vec<u8>>,
    index: usize,
}

impl PayloadPool {
    fn build(payload_len: usize, count: usize) -> Self {
        let payloads = (0..count)
            .map(|_| {
                let mut buf = vec![0u8; payload_len];
                for b in buf.iter_mut() {
                    // Simple LCG-quality fill — fast enough for a traffic generator
                    *b = rand_byte();
                }
                buf
            })
            .collect();
        Self { payloads, index: 0 }
    }

    #[inline]
    fn next(&mut self) -> &[u8] {
        let p = &self.payloads[self.index];
        self.index = (self.index + 1) % self.payloads.len();
        p
    }
}

/// Very cheap pseudo-random byte using a thread-local LCG.
fn rand_byte() -> u8 {
    use std::cell::Cell;
    thread_local! {
        static STATE: Cell<u64> = Cell::new(0x853c_49e6_748f_ea9b);
    }
    STATE.with(|s| {
        let mut v = s.get();
        v ^= v << 13;
        v ^= v >> 7;
        v ^= v << 17;
        s.set(v);
        v as u8
    })
}

/// Assemble a complete frame: Ethernet + TestGen + UserPayload.
/// Kept for use by `prepare_frame`; the hot loop uses `FrameTemplate` instead.
pub fn build_frame(
    eth_header: &[u8; ETHERNET_HEADER_SIZE],
    stream_id: u32,
    sequence: u64,
    tx_timestamp_ns: u64,
    user_payload: &[u8],
) -> Vec<u8> {
    let tg = build_testgen_header(
        stream_id,
        sequence,
        tx_timestamp_ns,
        user_payload.len() as u32,
        0,
    );
    let total = ETHERNET_HEADER_SIZE + TESTGEN_HEADER_SIZE + user_payload.len();
    let mut frame = Vec::with_capacity(total);
    frame.extend_from_slice(eth_header);
    frame.extend_from_slice(&tg);
    frame.extend_from_slice(user_payload);
    frame
}

// ---- Sender config -----------------------------------------------------

/// Full sender configuration received from Python.
#[derive(Debug, Clone)]
pub struct SenderConfig {
    pub interface: String,
    pub dst_mac: [u8; 6],
    pub src_mac: [u8; 6],
    pub ethertype: u16,
    pub stream_id: u32,
    pub pps: u64,
    pub packet_count: u64,   // 0 = unlimited
    pub duration_sec: f64,   // 0.0 = unlimited
    pub generation_mode: String,
    pub fields: Vec<FieldDescriptor>,
    pub values: Vec<FieldValue>,
}

impl SenderConfig {
    pub fn validate(&self) -> Result<(), NativeError> {
        if self.interface.is_empty() {
            return Err(NativeError::Config("interface is empty".into()));
        }
        if self.fields.len() != self.values.len() {
            return Err(NativeError::Config(
                "fields / values length mismatch".into(),
            ));
        }
        // "RANDOM" is now supported via pool mode; other modes are still rejected
        if self.generation_mode != "FIXED" && self.generation_mode != "RANDOM" {
            return Err(NativeError::Config(format!(
                "Unsupported generation_mode '{}'. Use FIXED or RANDOM.",
                self.generation_mode
            )));
        }
        Ok(())
    }
}

// ---- NativeSender ------------------------------------------------------

/// The native sender — builds and transmits frames.
pub struct NativeSender {
    config: SenderConfig,
    transport: Box<dyn FrameTransport>,
    stop_flag: Arc<AtomicBool>,
    running: bool,
    metrics: Arc<SharedMetrics>,
}

impl NativeSender {
    pub fn new(config: SenderConfig, transport: Box<dyn FrameTransport>) -> Self {
        Self {
            config,
            transport,
            stop_flag: Arc::new(AtomicBool::new(false)),
            running: false,
            metrics: Arc::new(SharedMetrics::new()),
        }
    }

    /// Request the send loop to stop early.
    pub fn request_stop(&self) {
        self.stop_flag.store(true, Ordering::Relaxed);
    }

    /// Return a clone of the stop flag for external use (e.g. from another thread).
    pub fn stop_flag(&self) -> Arc<AtomicBool> {
        self.stop_flag.clone()
    }

    /// Return a clone of the shared metrics for lock-free reading from another thread.
    pub fn shared_metrics(&self) -> Arc<SharedMetrics> {
        self.metrics.clone()
    }

    pub fn is_running(&self) -> bool {
        self.running
    }

    /// Return collected metrics as a HashMap for easy FFI.
    pub fn get_metrics(&self) -> HashMap<String, u64> {
        self.metrics.snapshot()
    }

    /// Execute the send loop. Returns summary metrics.
    pub fn run(&mut self) -> Result<HashMap<String, u64>, NativeError> {
        self.config.validate()?;

        // Reset metrics
        self.metrics.packets_attempted.store(0, Ordering::Relaxed);
        self.metrics.packets_sent.store(0, Ordering::Relaxed);
        self.metrics.packets_failed.store(0, Ordering::Relaxed);
        self.metrics.bytes_sent.store(0, Ordering::Relaxed);
        self.metrics.first_tx_timestamp_ns.store(0, Ordering::Relaxed);
        self.metrics.last_tx_timestamp_ns.store(0, Ordering::Relaxed);
        self.stop_flag.store(false, Ordering::Relaxed);
        self.running = true;

        // Build Ethernet header once
        let eth_header = build_ethernet_header(
            &self.config.dst_mac,
            &self.config.src_mac,
            self.config.ethertype,
        );

        // Build base user payload (for FIXED mode) or pool (for RANDOM mode)
        let base_payload = build_user_payload(&self.config.fields, &self.config.values)?;
        let payload_len = base_payload.len();

        let is_random = self.config.generation_mode == "RANDOM";
        let mut pool = if is_random {
            Some(PayloadPool::build(payload_len, POOL_SIZE))
        } else {
            None
        };

        // Pre-build frame template (avoids per-packet Vec allocation in fixed mode)
        let mut tmpl = FrameTemplate::new(&eth_header, self.config.stream_id, &base_payload);

        // Open transport (after all allocation so errors are clean)
        let result = (|| -> Result<(), NativeError> {
            self.transport
                .open(&self.config.interface)
                .map_err(|e| NativeError::Transport(format!("open: {e}")))?;

            // pps=0 means unlimited rate (no pacing)
            let interval = if self.config.pps > 0 {
                Duration::from_nanos(1_000_000_000 / self.config.pps)
            } else {
                Duration::ZERO
            };

            let unlimited = self.config.packet_count == 0;
            let has_duration = self.config.duration_sec > 0.0;
            let duration_limit = Duration::from_secs_f64(self.config.duration_sec);

            let mut local_sent: u64 = 0;
            let mut local_failed: u64 = 0;
            let mut consecutive_failures: u64 = 0;
            const MAX_CONSECUTIVE_FAILURES: u64 = 50;

            let mut seq: u64 = 0;
            // next_send tracks the ideal time for the next packet (avoids u32 overflow)
            let mut next_send = Instant::now();
            let start = Instant::now();

            loop {
                if self.stop_flag.load(Ordering::Relaxed) {
                    break;
                }
                if !unlimited && seq >= self.config.packet_count {
                    break;
                }
                if has_duration && start.elapsed() >= duration_limit {
                    break;
                }

                let ts = current_timestamp_ns();

                // Stamp the pre-built template or patch a pool payload
                if let Some(ref mut p) = pool {
                    let payload = p.next();
                    // For RANDOM mode, patch the payload section of the template in-place
                    let payload_start = tmpl.frame.len() - payload_len;
                    tmpl.frame[payload_start..].copy_from_slice(payload);
                }
                tmpl.stamp(seq, ts);

                self.metrics.packets_attempted.fetch_add(1, Ordering::Relaxed);

                match self.transport.send_frame(&tmpl.frame) {
                    Ok(n) => {
                        local_sent += 1;
                        self.metrics.packets_sent.store(local_sent, Ordering::Relaxed);
                        self.metrics.bytes_sent.fetch_add(n as u64, Ordering::Relaxed);
                        if self.metrics.first_tx_timestamp_ns.load(Ordering::Relaxed) == 0 {
                            self.metrics.first_tx_timestamp_ns.store(ts, Ordering::Relaxed);
                        }
                        self.metrics.last_tx_timestamp_ns.store(ts, Ordering::Relaxed);
                        consecutive_failures = 0;
                    }
                    Err(e) => {
                        local_failed += 1;
                        self.metrics.packets_failed.store(local_failed, Ordering::Relaxed);
                        consecutive_failures += 1;
                        if local_failed <= 5 || local_failed % 100 == 0 {
                            eprintln!("send error at seq {seq}: {e}");
                        }
                        if consecutive_failures >= MAX_CONSECUTIVE_FAILURES {
                            return Err(NativeError::Transport(format!(
                                "Too many consecutive send failures ({MAX_CONSECUTIVE_FAILURES}). Last: {e}"
                            )));
                        }
                    }
                }

                seq += 1;

                // Pacing: sleep for most of the wait, spin only for the tail.
                // This keeps CPU usage low at moderate rates while staying
                // accurate at high rates. pps=0 skips pacing entirely.
                if !interval.is_zero() {
                    next_send += interval;
                    let now = Instant::now();
                    if next_send > now {
                        let remaining = next_send - now;
                        if remaining > SPIN_THRESHOLD {
                            std::thread::sleep(remaining - SPIN_THRESHOLD);
                        }
                        while Instant::now() < next_send {
                            if self.stop_flag.load(Ordering::Relaxed) {
                                break;
                            }
                            std::hint::spin_loop();
                        }
                    }
                }
            }
            Ok(())
        })();

        self.transport.close();
        self.running = false;
        result?;
        Ok(self.get_metrics())
    }

    /// Build a single frame without sending — useful for tests.
    pub fn prepare_frame(&self, sequence: u64, timestamp_ns: u64) -> Result<Vec<u8>, NativeError> {
        let user_payload = build_user_payload(&self.config.fields, &self.config.values)?;
        let eth_header = build_ethernet_header(
            &self.config.dst_mac,
            &self.config.src_mac,
            self.config.ethertype,
        );
        Ok(build_frame(
            &eth_header,
            self.config.stream_id,
            sequence,
            timestamp_ns,
            &user_payload,
        ))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::transport::LoopbackTransport;

    fn test_config() -> SenderConfig {
        SenderConfig {
            interface: "dummy0".into(),
            dst_mac: [0xFF; 6],
            src_mac: [0x00; 6],
            ethertype: 0x88B5,
            stream_id: 1,
            pps: 0,
            packet_count: 5,
            duration_sec: 0.0,
            generation_mode: "FIXED".into(),
            fields: vec![FieldDescriptor {
                name: "val".into(),
                field_type: "INTEGER".into(),
                bit_length: 16,
            }],
            values: vec![FieldValue::Integer(42)],
        }
    }

    #[test]
    fn test_parse_mac_valid() {
        let mac = parse_mac("aa:bb:cc:dd:ee:ff").unwrap();
        assert_eq!(mac, [0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF]);
    }

    #[test]
    fn test_parse_mac_invalid() {
        assert!(parse_mac("invalid").is_err());
        assert!(parse_mac("aa:bb:cc:dd:ee").is_err());
        assert!(parse_mac("gg:bb:cc:dd:ee:ff").is_err());
    }

    #[test]
    fn test_build_ethernet_header() {
        let dst = [0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF];
        let src = [0x00, 0x11, 0x22, 0x33, 0x44, 0x55];
        let hdr = build_ethernet_header(&dst, &src, 0x88B5);
        assert_eq!(hdr.len(), 14);
        assert_eq!(&hdr[0..6], &dst);
        assert_eq!(&hdr[6..12], &src);
        assert_eq!(&hdr[12..14], &[0x88, 0xB5]);
    }

    #[test]
    fn test_build_frame_structure() {
        let eth = build_ethernet_header(
            &[0xFF; 6],
            &[0x00; 6],
            0x88B5,
        );
        let payload = vec![0x00, 0x2A]; // 16-bit integer = 42
        let frame = build_frame(&eth, 1, 0, 12345, &payload);
        // Ethernet(14) + TestGen(28) + Payload(2) = 44
        assert_eq!(frame.len(), 44);
        // Check EtherType at offset 12
        assert_eq!(frame[12], 0x88);
        assert_eq!(frame[13], 0xB5);
        // Check TestGen magic at offset 14
        assert_eq!(frame[14], 0x54); // 'T'
        assert_eq!(frame[15], 0x47); // 'G'
        // Check payload at offset 42
        assert_eq!(frame[42], 0x00);
        assert_eq!(frame[43], 0x2A);
    }

    #[test]
    fn test_loopback_transport_run() {
        let config = test_config();
        let transport = LoopbackTransport::new();
        let mut sender = NativeSender::new(config, Box::new(transport));
        let metrics = sender.run().unwrap();
        assert_eq!(metrics["packets_attempted"], 5);
        assert_eq!(metrics["packets_sent"], 5);
        assert_eq!(metrics["packets_failed"], 0);
        assert!(metrics["bytes_sent"] > 0);
        assert!(metrics["first_tx_timestamp_ns"] > 0);
        assert!(metrics["last_tx_timestamp_ns"] >= metrics["first_tx_timestamp_ns"]);
    }

    #[test]
    fn test_prepare_frame_deterministic() {
        let config = test_config();
        let transport = LoopbackTransport::new();
        let sender = NativeSender::new(config, Box::new(transport));
        let f1 = sender.prepare_frame(0, 999).unwrap();
        let f2 = sender.prepare_frame(0, 999).unwrap();
        assert_eq!(f1, f2);
    }

    #[test]
    fn test_request_stop() {
        let config = test_config();
        let transport = LoopbackTransport::new();
        let sender = NativeSender::new(config, Box::new(transport));
        assert!(!sender.stop_flag.load(Ordering::Relaxed));
        sender.request_stop();
        assert!(sender.stop_flag.load(Ordering::Relaxed));
    }

    #[test]
    fn test_random_mode_rejected() {
        let mut config = test_config();
        config.generation_mode = "RANDOM".into();
        let transport = LoopbackTransport::new();
        let mut sender = NativeSender::new(config, Box::new(transport));
        assert!(sender.run().is_err());
    }

    #[test]
    fn test_frame_payload_matches_python_serialization() {
        // Verify that the user payload portion of the frame matches
        // what Python's serialize_field would produce for INTEGER 16-bit = 42.
        let config = test_config();
        let transport = LoopbackTransport::new();
        let sender = NativeSender::new(config, Box::new(transport));
        let frame = sender.prepare_frame(0, 0).unwrap();
        // Payload starts at offset 42 (14 eth + 28 testgen)
        let payload = &frame[42..];
        assert_eq!(payload, &[0x00, 0x2A]); // 42 in big-endian 16-bit
    }

    #[test]
    fn test_config_validation() {
        let mut cfg = test_config();
        cfg.interface = "".into();
        assert!(cfg.validate().is_err());
    }

    /// Transport that fails every send call.
    struct FailingTransport;

    impl FrameTransport for FailingTransport {
        fn open(&mut self, _interface: &str) -> Result<(), NativeError> {
            Ok(())
        }
        fn send_frame(&mut self, _frame: &[u8]) -> Result<usize, NativeError> {
            Err(NativeError::Transport("simulated failure".into()))
        }
        fn close(&mut self) {}
    }

    #[test]
    fn test_failing_transport_counts_failures() {
        let mut config = test_config();
        config.packet_count = 100;
        let mut sender = NativeSender::new(config, Box::new(FailingTransport));
        // Should stop due to consecutive failure limit (50)
        let result = sender.run();
        assert!(result.is_err());
        let metrics = sender.get_metrics();
        assert_eq!(metrics["packets_sent"], 0);
        assert_eq!(metrics["packets_failed"], 50);
        assert_eq!(metrics["packets_attempted"], 50);
        assert_eq!(metrics["bytes_sent"], 0);
    }

    /// Transport that fails intermittently.
    struct IntermittentTransport {
        call_count: usize,
    }

    impl IntermittentTransport {
        fn new() -> Self {
            Self { call_count: 0 }
        }
    }

    impl FrameTransport for IntermittentTransport {
        fn open(&mut self, _interface: &str) -> Result<(), NativeError> {
            Ok(())
        }
        fn send_frame(&mut self, frame: &[u8]) -> Result<usize, NativeError> {
            self.call_count += 1;
            if self.call_count % 3 == 0 {
                Err(NativeError::Transport("intermittent failure".into()))
            } else {
                Ok(frame.len())
            }
        }
        fn close(&mut self) {}
    }

    #[test]
    fn test_intermittent_failures_counted() {
        let mut config = test_config();
        config.packet_count = 9;
        let mut sender = NativeSender::new(config, Box::new(IntermittentTransport::new()));
        let metrics = sender.run().unwrap();
        // 9 attempts, every 3rd fails => 3 failures, 6 successes
        assert_eq!(metrics["packets_attempted"], 9);
        assert_eq!(metrics["packets_sent"], 6);
        assert_eq!(metrics["packets_failed"], 3);
        assert!(metrics["bytes_sent"] > 0);
    }
}
