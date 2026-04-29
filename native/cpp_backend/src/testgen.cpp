#include "testgen.h"
#include <chrono>
#include <cstring>

namespace trafic {

static constexpr uint16_t TESTGEN_MAGIC = 0x5447;
static constexpr uint8_t TESTGEN_VERSION = 1;
static constexpr uint8_t TESTGEN_HEADER_SIZE = 28;

static void write_be16(uint8_t* dst, uint16_t v) {
    dst[0] = static_cast<uint8_t>(v >> 8);
    dst[1] = static_cast<uint8_t>(v);
}

static void write_be32(uint8_t* dst, uint32_t v) {
    dst[0] = static_cast<uint8_t>(v >> 24);
    dst[1] = static_cast<uint8_t>(v >> 16);
    dst[2] = static_cast<uint8_t>(v >> 8);
    dst[3] = static_cast<uint8_t>(v);
}

static void write_be64(uint8_t* dst, uint64_t v) {
    for (int i = 7; i >= 0; --i) {
        dst[7 - i] = static_cast<uint8_t>(v >> (i * 8));
    }
}

uint64_t current_timestamp_ns() {
    auto now = std::chrono::system_clock::now();
    auto ns = std::chrono::duration_cast<std::chrono::nanoseconds>(
                  now.time_since_epoch())
                  .count();
    return static_cast<uint64_t>(ns);
}

std::vector<uint8_t> build_testgen_header(uint32_t seq, uint16_t payload_length) {
    std::vector<uint8_t> buf(TESTGEN_HEADER_SIZE, 0);
    uint8_t* p = buf.data();

    write_be16(p + 0, TESTGEN_MAGIC);        // magic
    p[2] = TESTGEN_VERSION;                   // version
    p[3] = 0;                                 // flags
    write_be32(p + 4, seq);                   // sequence
    write_be64(p + 8, current_timestamp_ns()); // timestamp_ns
    write_be16(p + 16, payload_length);       // payload_length
    // bytes 18..27 reserved (zeroed)

    return buf;
}

} // namespace trafic
