#pragma once
#include "errors.h"
#include <cstdint>
#include <string>
#include <vector>

namespace trafic {

/// Describes a single schema field.
struct FieldDescriptor {
    std::string name;
    std::string field_type; // "INTEGER", "STRING", "BOOLEAN", "RAW_BYTES"
    size_t bit_length;
};

/// Serialize one field value to bytes (big-endian, matching Python rules).
std::vector<uint8_t> serialize_integer(const FieldDescriptor& desc, uint64_t value);
std::vector<uint8_t> serialize_string(const FieldDescriptor& desc, const std::string& value);
std::vector<uint8_t> serialize_boolean(bool value);
std::vector<uint8_t> serialize_raw_bytes(const FieldDescriptor& desc,
                                         const std::vector<uint8_t>& value);

} // namespace trafic
