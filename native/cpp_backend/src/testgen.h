#pragma once
#include <cstdint>
#include <vector>

namespace trafic {

/// Build a 28-byte TestGen header (big-endian) matching the Python format.
std::vector<uint8_t> build_testgen_header(uint32_t seq, uint16_t payload_length);

/// Current UNIX timestamp in nanoseconds.
uint64_t current_timestamp_ns();

} // namespace trafic
