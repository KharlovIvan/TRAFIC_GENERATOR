//! TestGen header builder — mirrors the Python `common.testgen_header` module.
//!
//! Format (28 bytes, big-endian):
//!   magic:          u16   (0x5447 = "TG")
//!   version:        u8    (1)
//!   flags:          u8    (0)
//!   stream_id:      u32
//!   sequence:       u64
//!   tx_timestamp_ns: u64
//!   payload_len:    u32

pub const TESTGEN_MAGIC: u16 = 0x5447;
pub const TESTGEN_VERSION: u8 = 1;
pub const TESTGEN_HEADER_SIZE: usize = 28;

/// Build a 28-byte TestGen header.
pub fn build_testgen_header(
    stream_id: u32,
    sequence: u64,
    tx_timestamp_ns: u64,
    payload_len: u32,
    flags: u8,
) -> [u8; TESTGEN_HEADER_SIZE] {
    let mut buf = [0u8; TESTGEN_HEADER_SIZE];
    buf[0..2].copy_from_slice(&TESTGEN_MAGIC.to_be_bytes());
    buf[2] = TESTGEN_VERSION;
    buf[3] = flags;
    buf[4..8].copy_from_slice(&stream_id.to_be_bytes());
    buf[8..16].copy_from_slice(&sequence.to_be_bytes());
    buf[16..24].copy_from_slice(&tx_timestamp_ns.to_be_bytes());
    buf[24..28].copy_from_slice(&payload_len.to_be_bytes());
    buf
}

/// Return current time as nanoseconds since Unix epoch.
pub fn current_timestamp_ns() -> u64 {
    use std::time::{SystemTime, UNIX_EPOCH};
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_nanos() as u64
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_header_size() {
        let hdr = build_testgen_header(1, 0, 0, 10, 0);
        assert_eq!(hdr.len(), TESTGEN_HEADER_SIZE);
    }

    #[test]
    fn test_header_magic() {
        let hdr = build_testgen_header(1, 0, 0, 10, 0);
        assert_eq!(u16::from_be_bytes([hdr[0], hdr[1]]), TESTGEN_MAGIC);
    }

    #[test]
    fn test_header_fields() {
        let hdr = build_testgen_header(42, 7, 12345, 100, 0);
        assert_eq!(u32::from_be_bytes(hdr[4..8].try_into().unwrap()), 42);
        assert_eq!(u64::from_be_bytes(hdr[8..16].try_into().unwrap()), 7);
        assert_eq!(u64::from_be_bytes(hdr[16..24].try_into().unwrap()), 12345);
        assert_eq!(u32::from_be_bytes(hdr[24..28].try_into().unwrap()), 100);
    }
}
