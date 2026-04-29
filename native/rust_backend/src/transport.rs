//! Transport abstractions for raw frame transmission.
//!
//! Provides a `FrameTransport` trait implemented by:
//! - `LoopbackTransport` – records frames in memory (testing only)
//! - `NpcapTransport` – sends real L2 Ethernet frames via Npcap/libpcap
//!
//! `NpcapTransport` dynamically loads the pcap library at runtime so no
//! SDK or build-time headers are required.  On Windows it loads `wpcap.dll`
//! (installed by Npcap); on Linux it loads `libpcap.so`.

use crate::errors::NativeError;
use std::ffi::{c_char, c_int, c_void, CStr, CString};

// ---- Trait ----------------------------------------------------------------

/// Trait for sending raw Ethernet frames through a transport backend.
pub trait FrameTransport: Send {
    /// Open the transport on the given network interface.
    fn open(&mut self, interface: &str) -> Result<(), NativeError>;

    /// Send a single raw frame.  Returns the number of bytes accepted
    /// for transmission on success.
    fn send_frame(&mut self, frame: &[u8]) -> Result<usize, NativeError>;

    /// Close the transport and release resources.
    fn close(&mut self);
}

// ---- Loopback (testing) ---------------------------------------------------

/// In-memory transport that records frames without sending (testing only).
pub struct LoopbackTransport {
    pub frames: Vec<Vec<u8>>,
}

impl LoopbackTransport {
    pub fn new() -> Self {
        Self { frames: Vec::new() }
    }
}

impl FrameTransport for LoopbackTransport {
    fn open(&mut self, _interface: &str) -> Result<(), NativeError> {
        Ok(())
    }

    fn send_frame(&mut self, frame: &[u8]) -> Result<usize, NativeError> {
        let len = frame.len();
        self.frames.push(frame.to_vec());
        Ok(len)
    }

    fn close(&mut self) {}
}

// ---- Npcap / libpcap dynamic loading --------------------------------------

/// Name of the pcap shared library on the current platform.
#[cfg(target_os = "windows")]
const PCAP_LIB_NAME: &str = "wpcap.dll";

#[cfg(not(target_os = "windows"))]
const PCAP_LIB_NAME: &str = "libpcap.so";

/// Npcap subdirectory on Windows (fallback search path).
#[cfg(target_os = "windows")]
const NPCAP_DIR: &str = r"C:\Windows\System32\Npcap\wpcap.dll";

const PCAP_ERRBUF_SIZE: usize = 256;

// C struct mirroring pcap_if_t for interface enumeration.
#[repr(C)]
struct PcapIf {
    next: *mut PcapIf,
    name: *const c_char,
    description: *const c_char,
    addresses: *mut c_void,
    flags: u32,
}

/// Dynamically loaded pcap function table.
struct PcapFns {
    pcap_open_live: unsafe extern "C" fn(
        *const c_char,
        c_int,
        c_int,
        c_int,
        *mut c_char,
    ) -> *mut c_void,
    pcap_sendpacket: unsafe extern "C" fn(*mut c_void, *const u8, c_int) -> c_int,
    pcap_close: unsafe extern "C" fn(*mut c_void),
    pcap_geterr: unsafe extern "C" fn(*mut c_void) -> *const c_char,
    pcap_findalldevs:
        unsafe extern "C" fn(*mut *mut PcapIf, *mut c_char) -> c_int,
    pcap_freealldevs: unsafe extern "C" fn(*mut PcapIf),
}

/// Try to load the pcap library and resolve all required symbols.
fn load_pcap_fns() -> Result<(libloading::Library, PcapFns), NativeError> {
    // Try primary name, then platform-specific fallback.
    let lib = unsafe { libloading::Library::new(PCAP_LIB_NAME) }
        .or_else(|_| {
            #[cfg(target_os = "windows")]
            {
                unsafe { libloading::Library::new(NPCAP_DIR) }
            }
            #[cfg(not(target_os = "windows"))]
            {
                Err(libloading::Error::DlOpen {
                    desc: "libpcap not found".into(),
                })
            }
        })
        .map_err(|e| {
            NativeError::Transport(format!(
                "Cannot load pcap library ({PCAP_LIB_NAME}): {e}. \
                 Install Npcap from https://npcap.com"
            ))
        })?;

    unsafe {
        let fns = PcapFns {
            pcap_open_live: *lib
                .get::<unsafe extern "C" fn(
                    *const c_char,
                    c_int,
                    c_int,
                    c_int,
                    *mut c_char,
                ) -> *mut c_void>(b"pcap_open_live\0")
                .map_err(|e| {
                    NativeError::Transport(format!("pcap_open_live not found: {e}"))
                })?,
            pcap_sendpacket: *lib
                .get::<unsafe extern "C" fn(*mut c_void, *const u8, c_int) -> c_int>(
                    b"pcap_sendpacket\0",
                )
                .map_err(|e| {
                    NativeError::Transport(format!("pcap_sendpacket not found: {e}"))
                })?,
            pcap_close: *lib
                .get::<unsafe extern "C" fn(*mut c_void)>(b"pcap_close\0")
                .map_err(|e| {
                    NativeError::Transport(format!("pcap_close not found: {e}"))
                })?,
            pcap_geterr: *lib
                .get::<unsafe extern "C" fn(*mut c_void) -> *const c_char>(
                    b"pcap_geterr\0",
                )
                .map_err(|e| {
                    NativeError::Transport(format!("pcap_geterr not found: {e}"))
                })?,
            pcap_findalldevs: *lib
                .get::<unsafe extern "C" fn(*mut *mut PcapIf, *mut c_char) -> c_int>(
                    b"pcap_findalldevs\0",
                )
                .map_err(|e| {
                    NativeError::Transport(format!("pcap_findalldevs not found: {e}"))
                })?,
            pcap_freealldevs: *lib
                .get::<unsafe extern "C" fn(*mut PcapIf)>(b"pcap_freealldevs\0")
                .map_err(|e| {
                    NativeError::Transport(format!("pcap_freealldevs not found: {e}"))
                })?,
        };
        Ok((lib, fns))
    }
}

// ---- NpcapTransport -------------------------------------------------------

/// Real L2 Ethernet transport via Npcap (Windows) or libpcap (Linux).
///
/// The pcap library is loaded *dynamically* at runtime so no SDK headers
/// or link libraries are needed at compile time.  If the library is not
/// installed, `open()` returns a clear error.
pub struct NpcapTransport {
    _lib: Option<libloading::Library>,
    fns: Option<PcapFns>,
    handle: *mut c_void,
}

// SAFETY: The pcap handle is used exclusively from the sender thread.
// It is never shared or sent to another thread while in use.
unsafe impl Send for NpcapTransport {}

impl NpcapTransport {
    pub fn new() -> Self {
        Self {
            _lib: None,
            fns: None,
            handle: std::ptr::null_mut(),
        }
    }

    /// Check whether the pcap library can be loaded on this system.
    pub fn is_available() -> bool {
        load_pcap_fns().is_ok()
    }

    /// List available network interfaces reported by pcap.
    /// Returns Vec of (device_name, description) pairs.
    pub fn list_interfaces() -> Result<Vec<(String, String)>, NativeError> {
        let (_lib, fns) = load_pcap_fns()?;
        let mut errbuf = [0 as c_char; PCAP_ERRBUF_SIZE];
        let mut alldevs: *mut PcapIf = std::ptr::null_mut();

        let rc = unsafe { (fns.pcap_findalldevs)(&mut alldevs, errbuf.as_mut_ptr()) };
        if rc != 0 {
            let msg = unsafe { CStr::from_ptr(errbuf.as_ptr()) }
                .to_string_lossy()
                .to_string();
            return Err(NativeError::Transport(format!(
                "pcap_findalldevs failed: {msg}"
            )));
        }

        let mut interfaces = Vec::new();
        let mut dev = alldevs;
        while !dev.is_null() {
            unsafe {
                let name = if (*dev).name.is_null() {
                    String::new()
                } else {
                    CStr::from_ptr((*dev).name).to_string_lossy().to_string()
                };
                let desc = if (*dev).description.is_null() {
                    String::new()
                } else {
                    CStr::from_ptr((*dev).description)
                        .to_string_lossy()
                        .to_string()
                };
                interfaces.push((name, desc));
                dev = (*dev).next;
            }
        }
        unsafe { (fns.pcap_freealldevs)(alldevs) };
        Ok(interfaces)
    }

    /// Resolve a user-friendly interface name to the pcap device name.
    ///
    /// Matching strategy (first match wins):
    /// 1. Exact match on device name
    /// 2. Device name ends with the given string
    /// 3. Description contains the given string (case-insensitive)
    /// 4. Fall through: use the given name as-is
    fn resolve_device(
        fns: &PcapFns,
        interface: &str,
    ) -> Result<String, NativeError> {
        let mut errbuf = [0 as c_char; PCAP_ERRBUF_SIZE];
        let mut alldevs: *mut PcapIf = std::ptr::null_mut();

        let rc = unsafe { (fns.pcap_findalldevs)(&mut alldevs, errbuf.as_mut_ptr()) };
        if rc != 0 {
            let msg = unsafe { CStr::from_ptr(errbuf.as_ptr()) }
                .to_string_lossy()
                .to_string();
            return Err(NativeError::Transport(format!(
                "pcap_findalldevs failed: {msg}"
            )));
        }

        let iface_lower = interface.to_lowercase();
        let mut result: Option<String> = None;
        let mut dev = alldevs;

        while !dev.is_null() {
            unsafe {
                let name = if (*dev).name.is_null() {
                    String::new()
                } else {
                    CStr::from_ptr((*dev).name).to_string_lossy().to_string()
                };
                let desc = if (*dev).description.is_null() {
                    String::new()
                } else {
                    CStr::from_ptr((*dev).description)
                        .to_string_lossy()
                        .to_string()
                };

                // Strategy 1: exact match on device name
                if name == interface {
                    result = Some(name);
                    break;
                }
                // Strategy 2: device name ends with the given string
                if name.to_lowercase().ends_with(&iface_lower) {
                    result = Some(name);
                    break;
                }
                // Strategy 3: description contains the given string
                if !desc.is_empty() && desc.to_lowercase().contains(&iface_lower) {
                    result = Some(name);
                    break;
                }

                dev = (*dev).next;
            }
        }

        unsafe { (fns.pcap_freealldevs)(alldevs) };

        // Strategy 4: use as-is (pcap_open_live will fail if invalid)
        Ok(result.unwrap_or_else(|| interface.to_string()))
    }
}

impl FrameTransport for NpcapTransport {
    fn open(&mut self, interface: &str) -> Result<(), NativeError> {
        // Close any existing handle first.
        self.close();

        let (lib, fns) = load_pcap_fns()?;

        // Resolve the interface name to a pcap device.
        let device_name = Self::resolve_device(&fns, interface)?;
        let c_device = CString::new(device_name.as_str()).map_err(|_| {
            NativeError::Transport("Interface name contains NUL byte".into())
        })?;

        let mut errbuf = [0 as c_char; PCAP_ERRBUF_SIZE];

        let handle = unsafe {
            (fns.pcap_open_live)(
                c_device.as_ptr(),
                65535, // snaplen
                0,     // promisc off for sending
                1000,  // timeout ms
                errbuf.as_mut_ptr(),
            )
        };

        if handle.is_null() {
            let msg = unsafe { CStr::from_ptr(errbuf.as_ptr()) }
                .to_string_lossy()
                .to_string();
            return Err(NativeError::Transport(format!(
                "pcap_open_live failed for '{}' (resolved to '{}'): {}",
                interface, device_name, msg
            )));
        }

        self._lib = Some(lib);
        self.fns = Some(fns);
        self.handle = handle;
        Ok(())
    }

    fn send_frame(&mut self, frame: &[u8]) -> Result<usize, NativeError> {
        let fns = self
            .fns
            .as_ref()
            .ok_or_else(|| NativeError::Transport("Transport not open".into()))?;

        if self.handle.is_null() {
            return Err(NativeError::Transport("Transport not open".into()));
        }

        let rc = unsafe {
            (fns.pcap_sendpacket)(self.handle, frame.as_ptr(), frame.len() as c_int)
        };

        if rc == 0 {
            Ok(frame.len())
        } else {
            let err_ptr = unsafe { (fns.pcap_geterr)(self.handle) };
            let msg = if err_ptr.is_null() {
                "unknown pcap error".to_string()
            } else {
                unsafe { CStr::from_ptr(err_ptr) }
                    .to_string_lossy()
                    .to_string()
            };
            Err(NativeError::Transport(format!(
                "pcap_sendpacket failed: {msg}"
            )))
        }
    }

    fn close(&mut self) {
        if !self.handle.is_null() {
            if let Some(ref fns) = self.fns {
                unsafe { (fns.pcap_close)(self.handle) };
            }
            self.handle = std::ptr::null_mut();
        }
        self.fns = None;
        self._lib = None;
    }
}

impl Drop for NpcapTransport {
    fn drop(&mut self) {
        self.close();
    }
}

// ---- Tests ----------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_loopback_open_close() {
        let mut t = LoopbackTransport::new();
        assert!(t.open("dummy0").is_ok());
        t.close();
    }

    #[test]
    fn test_loopback_send_returns_len() {
        let mut t = LoopbackTransport::new();
        t.open("lo").unwrap();
        let frame = vec![0u8; 64];
        let sent = t.send_frame(&frame).unwrap();
        assert_eq!(sent, 64);
        assert_eq!(t.frames.len(), 1);
        assert_eq!(t.frames[0].len(), 64);
    }

    #[test]
    fn test_loopback_send_multiple() {
        let mut t = LoopbackTransport::new();
        t.open("lo").unwrap();
        for i in 0..5 {
            let frame = vec![i as u8; 32];
            assert_eq!(t.send_frame(&frame).unwrap(), 32);
        }
        assert_eq!(t.frames.len(), 5);
    }

    #[test]
    fn test_npcap_availability_check() {
        // This test just verifies the check doesn't panic.
        // Result depends on whether Npcap is installed.
        let _available = NpcapTransport::is_available();
    }

    #[test]
    fn test_npcap_list_interfaces_if_available() {
        if !NpcapTransport::is_available() {
            return; // skip on CI without Npcap
        }
        let interfaces = NpcapTransport::list_interfaces().unwrap();
        assert!(!interfaces.is_empty());
        for (name, _desc) in &interfaces {
            assert!(!name.is_empty());
        }
    }
}
