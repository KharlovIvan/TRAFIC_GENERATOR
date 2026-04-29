#pragma once
#include "errors.h"
#include "serializer.h"
#include <atomic>
#include <cstdint>
#include <string>
#include <unordered_map>
#include <vector>

namespace trafic {

struct SenderConfig {
    std::string dest_ip;
    uint16_t dest_port = 0;
    uint16_t src_port = 0;
    uint64_t packet_count = 0;
    uint64_t send_rate_pps = 0;
    std::vector<FieldDescriptor> fields;
    // For simplicity, all values stored as strings; parsed per field_type.
    std::vector<std::string> raw_values;
};

class NativeSender {
public:
    explicit NativeSender(SenderConfig config);

    /// Execute the send loop, returns metrics map.
    std::unordered_map<std::string, uint64_t> run();

    /// Request early stop from another thread.
    void request_stop();

private:
    SenderConfig config_;
    std::atomic<bool> stop_flag_{false};
};

} // namespace trafic
