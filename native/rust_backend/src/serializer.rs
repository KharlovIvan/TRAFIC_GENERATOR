//! Field serializer — mirrors the Python `common.serializer` module.
//!
//! Converts field descriptors + values into binary payload bytes
//! using the same rules as the Python implementation.

use crate::errors::NativeError;

/// Describes a single field in layout order.
#[derive(Debug, Clone)]
pub struct FieldDescriptor {
    pub name: String,
    pub field_type: String, // "INTEGER", "STRING", "BOOLEAN", "RAW_BYTES"
    pub bit_length: usize,
}

/// A field value received from Python.
#[derive(Debug, Clone)]
pub enum FieldValue {
    Integer(u64),
    Str(String),
    Bool(bool),
    RawBytes(Vec<u8>),
}

/// Serialize a single field value to bytes (big-endian, matching Python).
pub fn serialize_field(
    desc: &FieldDescriptor,
    value: &FieldValue,
) -> Result<Vec<u8>, NativeError> {
    let byte_len = desc.bit_length / 8;

    match (&*desc.field_type, value) {
        ("INTEGER", FieldValue::Integer(v)) => {
            if byte_len > 8 {
                return Err(NativeError::Serialization(format!(
                    "Field '{}': INTEGER byte_len {} exceeds 8",
                    desc.name, byte_len
                )));
            }
            // Check value fits in byte_len bytes
            if byte_len < 8 {
                let max_val = (1u64 << (byte_len * 8)) - 1;
                if *v > max_val {
                    return Err(NativeError::Serialization(format!(
                        "Field '{}': value {} does not fit in {} bytes",
                        desc.name, v, byte_len
                    )));
                }
            }
            let bytes = v.to_be_bytes();
            Ok(bytes[8 - byte_len..].to_vec())
        }
        ("STRING", FieldValue::Str(s)) => {
            let encoded = s.as_bytes();
            let mut buf = vec![0u8; byte_len];
            let copy_len = encoded.len().min(byte_len);
            buf[..copy_len].copy_from_slice(&encoded[..copy_len]);
            Ok(buf)
        }
        ("BOOLEAN", FieldValue::Bool(b)) => {
            if byte_len != 1 {
                return Err(NativeError::Serialization(format!(
                    "Field '{}': BOOLEAN must be 8 bits, got {}",
                    desc.name, desc.bit_length
                )));
            }
            Ok(vec![if *b { 1 } else { 0 }])
        }
        ("RAW_BYTES", FieldValue::RawBytes(raw)) => {
            if raw.len() != byte_len {
                return Err(NativeError::Serialization(format!(
                    "Field '{}': expected {} bytes, got {}",
                    desc.name, byte_len, raw.len()
                )));
            }
            Ok(raw.clone())
        }
        // RAW_BYTES can also arrive as hex string from Python side
        ("RAW_BYTES", FieldValue::Str(hex_str)) => {
            let cleaned: String = hex_str
                .replace(' ', "")
                .replace("0x", "")
                .replace("0X", "");
            let raw = hex_decode(&cleaned).map_err(|e| {
                NativeError::Serialization(format!(
                    "Field '{}': invalid hex string '{}': {}",
                    desc.name, hex_str, e
                ))
            })?;
            if raw.len() != byte_len {
                return Err(NativeError::Serialization(format!(
                    "Field '{}': expected {} bytes from hex, got {}",
                    desc.name, byte_len, raw.len()
                )));
            }
            Ok(raw)
        }
        _ => Err(NativeError::Serialization(format!(
            "Unsupported type '{}' / value combo for field '{}'",
            desc.field_type, desc.name
        ))),
    }
}

/// Build the full user payload from field descriptors and values in layout order.
pub fn build_user_payload(
    fields: &[FieldDescriptor],
    values: &[FieldValue],
) -> Result<Vec<u8>, NativeError> {
    if fields.len() != values.len() {
        return Err(NativeError::Serialization(format!(
            "Field count mismatch: {} descriptors, {} values",
            fields.len(),
            values.len()
        )));
    }
    let mut payload = Vec::new();
    for (desc, val) in fields.iter().zip(values.iter()) {
        payload.extend(serialize_field(desc, val)?);
    }
    Ok(payload)
}

/// Simple hex string decoder (no prefix).
fn hex_decode(s: &str) -> Result<Vec<u8>, String> {
    if s.len() % 2 != 0 {
        return Err("odd-length hex string".into());
    }
    let mut bytes = Vec::with_capacity(s.len() / 2);
    for i in (0..s.len()).step_by(2) {
        let byte_str = &s[i..i + 2];
        let b = u8::from_str_radix(byte_str, 16)
            .map_err(|_| format!("invalid hex byte '{byte_str}'"))?;
        bytes.push(b);
    }
    Ok(bytes)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn int_field(name: &str, bits: usize) -> FieldDescriptor {
        FieldDescriptor {
            name: name.to_string(),
            field_type: "INTEGER".to_string(),
            bit_length: bits,
        }
    }

    #[test]
    fn test_serialize_integer_8bit() {
        let desc = int_field("val", 8);
        let val = FieldValue::Integer(0x2A);
        let bytes = serialize_field(&desc, &val).unwrap();
        assert_eq!(bytes, vec![0x2A]);
    }

    #[test]
    fn test_serialize_integer_16bit() {
        let desc = int_field("val", 16);
        let val = FieldValue::Integer(0x1234);
        let bytes = serialize_field(&desc, &val).unwrap();
        assert_eq!(bytes, vec![0x12, 0x34]);
    }

    #[test]
    fn test_serialize_integer_32bit_zero() {
        let desc = int_field("val", 32);
        let val = FieldValue::Integer(0);
        let bytes = serialize_field(&desc, &val).unwrap();
        assert_eq!(bytes, vec![0, 0, 0, 0]);
    }

    #[test]
    fn test_serialize_integer_overflow() {
        let desc = int_field("val", 8);
        let val = FieldValue::Integer(256);
        assert!(serialize_field(&desc, &val).is_err());
    }

    #[test]
    fn test_serialize_string() {
        let desc = FieldDescriptor {
            name: "s".to_string(),
            field_type: "STRING".to_string(),
            bit_length: 32,
        };
        let val = FieldValue::Str("Hi".to_string());
        let bytes = serialize_field(&desc, &val).unwrap();
        assert_eq!(bytes, vec![b'H', b'i', 0, 0]);
    }

    #[test]
    fn test_serialize_string_truncate() {
        let desc = FieldDescriptor {
            name: "s".to_string(),
            field_type: "STRING".to_string(),
            bit_length: 16, // 2 bytes
        };
        let val = FieldValue::Str("Hello".to_string());
        let bytes = serialize_field(&desc, &val).unwrap();
        assert_eq!(bytes, vec![b'H', b'e']);
    }

    #[test]
    fn test_serialize_boolean() {
        let desc = FieldDescriptor {
            name: "b".to_string(),
            field_type: "BOOLEAN".to_string(),
            bit_length: 8,
        };
        assert_eq!(
            serialize_field(&desc, &FieldValue::Bool(true)).unwrap(),
            vec![1]
        );
        assert_eq!(
            serialize_field(&desc, &FieldValue::Bool(false)).unwrap(),
            vec![0]
        );
    }

    #[test]
    fn test_serialize_raw_bytes() {
        let desc = FieldDescriptor {
            name: "r".to_string(),
            field_type: "RAW_BYTES".to_string(),
            bit_length: 24,
        };
        let val = FieldValue::RawBytes(vec![0xAA, 0xBB, 0xCC]);
        let bytes = serialize_field(&desc, &val).unwrap();
        assert_eq!(bytes, vec![0xAA, 0xBB, 0xCC]);
    }

    #[test]
    fn test_serialize_raw_bytes_length_mismatch() {
        let desc = FieldDescriptor {
            name: "r".to_string(),
            field_type: "RAW_BYTES".to_string(),
            bit_length: 24,
        };
        let val = FieldValue::RawBytes(vec![0xAA]);
        assert!(serialize_field(&desc, &val).is_err());
    }

    #[test]
    fn test_serialize_raw_bytes_from_hex_string() {
        let desc = FieldDescriptor {
            name: "r".to_string(),
            field_type: "RAW_BYTES".to_string(),
            bit_length: 16,
        };
        let val = FieldValue::Str("aabb".to_string());
        let bytes = serialize_field(&desc, &val).unwrap();
        assert_eq!(bytes, vec![0xAA, 0xBB]);
    }

    #[test]
    fn test_build_user_payload() {
        let fields = vec![int_field("a", 16), int_field("b", 16)];
        let values = vec![FieldValue::Integer(1), FieldValue::Integer(2)];
        let payload = build_user_payload(&fields, &values).unwrap();
        assert_eq!(payload, vec![0, 1, 0, 2]);
    }

    #[test]
    fn test_build_user_payload_count_mismatch() {
        let fields = vec![int_field("a", 16)];
        let values = vec![FieldValue::Integer(1), FieldValue::Integer(2)];
        assert!(build_user_payload(&fields, &values).is_err());
    }

    #[test]
    fn test_unsupported_type() {
        let desc = FieldDescriptor {
            name: "x".to_string(),
            field_type: "UNKNOWN".to_string(),
            bit_length: 8,
        };
        assert!(serialize_field(&desc, &FieldValue::Integer(0)).is_err());
    }
}
