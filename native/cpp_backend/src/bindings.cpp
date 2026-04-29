#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include "sender.h"

namespace py = pybind11;

static trafic::NativeSender* g_sender = nullptr;

static uintptr_t create_sender(py::dict config_dict) {
    trafic::SenderConfig cfg;
    cfg.dest_ip = config_dict["dest_ip"].cast<std::string>();
    cfg.dest_port = config_dict["dest_port"].cast<uint16_t>();
    cfg.src_port = config_dict.contains("src_port") ? config_dict["src_port"].cast<uint16_t>() : 0;
    cfg.packet_count = config_dict["packet_count"].cast<uint64_t>();
    cfg.send_rate_pps = config_dict.contains("send_rate_pps") ? config_dict["send_rate_pps"].cast<uint64_t>() : 0;

    auto* sender = new trafic::NativeSender(std::move(cfg));
    return reinterpret_cast<uintptr_t>(sender);
}

static py::dict start_sender(uintptr_t handle, double /*progress_interval*/) {
    auto* sender = reinterpret_cast<trafic::NativeSender*>(handle);
    auto metrics = sender->run();
    py::dict result;
    for (auto& [k, v] : metrics) {
        result[py::str(k)] = v;
    }
    return result;
}

static void stop_sender(uintptr_t handle) {
    auto* sender = reinterpret_cast<trafic::NativeSender*>(handle);
    sender->request_stop();
    delete sender;
}

PYBIND11_MODULE(trafic_native, m) {
    m.doc() = "C++ native sender backend for TRAFIC_GENERATOR";
    m.def("create_sender", &create_sender, "Create a sender from config dict");
    m.def("start_sender", &start_sender, "Run the sender, return metrics dict");
    m.def("stop_sender", &stop_sender, "Stop and destroy a sender");
}
