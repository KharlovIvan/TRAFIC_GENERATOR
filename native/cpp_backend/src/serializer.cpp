#include "serializer.h"
#include <algorithm>
#include <cstring>

namespace trafic {

std::vector<uint8_t> serialize_integer(const FieldDescriptor& desc, uint64_t value) {
    size_t byte_len = desc.bit_length / 8;
    std::vector<uint8_t> buf(byte_len, 0);
    for (size_t i = 0; i < byte_len && i < 8; ++i) {
        buf[byte_len - 1 - i] = static_cast<uint8_t>(value >> (i * 8));
    }
    return buf;
}

std::vector<uint8_t> serialize_string(const FieldDescriptor& desc, const std::string& value) {
    size_t byte_len = desc.bit_length / 8;
    std::vector<uint8_t> buf(byte_len, 0);
    size_t copy_len = std::min(value.size(), byte_len);
    std::memcpy(buf.data(), value.data(), copy_len);
    return buf;
}

std::vector<uint8_t> serialize_boolean(bool value) {
    return {static_cast<uint8_t>(value ? 1 : 0)};
}

std::vector<uint8_t> serialize_raw_bytes(const FieldDescriptor& desc,
                                         const std::vector<uint8_t>& value) {
    size_t byte_len = desc.bit_length / 8;
    if (value.size() != byte_len) {
        throw NativeError(NativeError::Kind::Serialization,
                          "RAW_BYTES length mismatch for field '" + desc.name + "'");
    }
    return value;
}

} // namespace trafic
