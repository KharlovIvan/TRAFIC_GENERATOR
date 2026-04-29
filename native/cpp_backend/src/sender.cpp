#include "sender.h"
#include "testgen.h"

#ifdef _WIN32
#include <winsock2.h>
#include <ws2tcpip.h>
#pragma comment(lib, "ws2_32.lib")
#else
#include <arpa/inet.h>
#include <sys/socket.h>
#include <unistd.h>
#endif

#include <chrono>
#include <cstring>
#include <thread>

namespace trafic {

NativeSender::NativeSender(SenderConfig config) : config_(std::move(config)) {
    if (config_.dest_ip.empty()) {
        throw NativeError(NativeError::Kind::Config, "dest_ip is empty");
    }
}

void NativeSender::request_stop() {
    stop_flag_.store(true, std::memory_order_relaxed);
}

std::unordered_map<std::string, uint64_t> NativeSender::run() {
    // Stub — real socket implementation follows the Rust version's pattern.
    // Returns zero metrics for the skeleton build.
    std::unordered_map<std::string, uint64_t> metrics;
    metrics["packets_sent"] = 0;
    metrics["bytes_sent"] = 0;
    metrics["elapsed_ms"] = 0;
    metrics["errors"] = 0;
    return metrics;
}

} // namespace trafic
