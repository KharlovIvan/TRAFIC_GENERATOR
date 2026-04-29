# Final MVP Sender Summary

## Objective

Transform the sender from a loopback benchmark into a **real end-to-end MVP**
that transmits L2 Ethernet frames through a real NIC and computes metrics only
from frames that were truly accepted for transmission.

---

## Architecture Overview

```
┌────────────────────┐     ┌──────────────────────────────┐
│  GUI (PySide6)     │     │  SenderService               │
│  sender_gui.py     │────▶│  sender_service.py           │
│  sender_worker.py  │     │                              │
└────────────────────┘     │  create_backend(mode)        │
                           │    ├─ PythonSenderBackend     │
                           │    │   └─ SenderEngine        │
                           │    │       └─ SenderTransport │
                           │    │           ├─ Scapy L2    │
                           │    │           └─ (test fakes)│
                           │    └─ NativeSenderBackend     │
                           │        └─ trafic_native (Rust)│
                           │            ├─ NpcapTransport  │
                           │            └─ LoopbackTransport│
                           └──────────────────────────────┘
```

### Two Backends — One Interface

| Backend | Transport | Use Case |
|---------|-----------|----------|
| **Python** (`PythonSenderBackend`) | `ScapySenderTransport` (Scapy L2 socket) or test fakes | Default for development; full Python control |
| **Native** (`NativeSenderBackend`) | `NpcapTransport` (real NIC via Npcap/libpcap) or `LoopbackTransport` (testing only) | High-performance production path |

Both backends expose the exact same `SenderMetrics` shape, making the
`SenderService` and GUI fully backend-agnostic.

---

## Key Design Decisions

### 1. Npcap Dynamic Loading (No SDK Required)

The Rust `NpcapTransport` loads `wpcap.dll` (Windows) or `libpcap.so` (Linux)
**at runtime** via the `libloading` crate. This avoids any compile-time
dependency on the Npcap SDK. Required symbols:

- `pcap_open_live` — open a live capture/send handle
- `pcap_sendpacket` — send a raw L2 frame
- `pcap_close` — release the handle
- `pcap_geterr` — get the last error string
- `pcap_findalldevs` / `pcap_freealldevs` — enumerate interfaces

### 2. Interface Name Resolution

Windows pcap uses `\Device\NPF_{GUID}` names. The transport resolves
user-friendly names via a 4-step strategy:

1. Exact match on pcap device name
2. Device name ends with user string
3. Description contains user string (case-insensitive)
4. Use as-is (pcap_open_live will fail if invalid)

### 3. Transport Contract: `send() → int`

`SenderTransport.send(frame_bytes) -> int` returns bytes accepted on success
and raises on failure. This enables the metrics model to distinguish
successful and failed transmissions.

### 4. Metrics Semantics

| Counter | Meaning |
|---------|---------|
| `packets_attempted` | Every frame submitted to the transport |
| `packets_sent` | Frames successfully accepted by the NIC |
| `packets_failed` | Frames whose send call raised/returned error |
| `bytes_sent` | Total bytes of successfully sent frames |

**Speed metrics** (PPS, bps, Gbps) are derived from `packets_sent` /
`bytes_sent` **only**, never from attempted counts.

### 5. Consecutive Failure Limit

Both Python and Rust engines stop after **50 consecutive** send failures
to prevent infinite loops on a dead interface.

---

## Files Changed

### Common
| File | Change |
|------|--------|
| `common/metrics.py` | Added `packets_attempted`, `packets_failed`, `record_send_attempt()`, `record_send_failure()`, `gbps` property; updated `snapshot()` and `reset()` |

### Sender — Transports & Engine
| File | Change |
|------|--------|
| `sender/transports/base.py` | `send()` returns `int` (bytes accepted) |
| `sender/transports/scapy_transport.py` | `send()` returns `len(frame_bytes)` |
| `sender/sender_engine.py` | Tracks attempted/success/fail; 50 consecutive failure limit |

### Sender — Backends
| File | Change |
|------|--------|
| `sender/backends/native_backend.py` | Transport validation, `is_native_transport_available()`, `list_native_interfaces()`, new metrics mapping, interface check on init |
| `sender/backends/python_backend.py` | Added logging |

### Sender — GUI / Worker
| File | Change |
|------|--------|
| `sender/sender_service.py` | Added logging |
| `sender/sender_worker.py` | Renamed `log` → `log_msg` signal; detailed summary logging |
| `sender/sender_gui.py` | Updated to `log_msg` signal |
| `sender/widgets/session_panel.py` | Two-row counters: Attempted/Sent/Failed/Bytes + PPS/Throughput/Elapsed |
| `sender/widgets/backend_panel.py` | Checks `is_native_transport_available()`; shows Npcap status |

### Native — Rust Backend
| File | Change |
|------|--------|
| `native/rust_backend/Cargo.toml` | Added `libloading = "0.8"` |
| `native/rust_backend/src/transport.rs` | **NEW** — `FrameTransport` trait, `LoopbackTransport`, `NpcapTransport` with dynamic pcap loading |
| `native/rust_backend/src/sender.rs` | Uses `transport` module; `SharedMetrics` with `packets_attempted`/`packets_failed`; error tracking in `run()` |
| `native/rust_backend/src/lib.rs` | `create_sender(config, use_loopback=False)`; `is_transport_available()`; `list_interfaces()` FFI |

### Tests
| File | Change |
|------|--------|
| `tests/test_mvp_transport_metrics.py` | **NEW** — 28 tests covering metrics correctness, engine failure semantics, backend parity, service integration, transport validation, native metrics conversion |
| `tests/test_sender_native_backend.py` | Updated all mock modules for new API surface |
| 7 other test files | Updated `send() → int` signature in test transports |

---

## Test Results

### Rust (`cargo test`)
```
test result: ok. 33 passed; 0 failed; 0 ignored
```

Key Rust tests:
- `test_loopback_transport_run` — 5 frames via loopback, metrics correct
- `test_failing_transport_counts_failures` — 100 attempts through always-failing transport, stops at 50 consecutive failures
- `test_intermittent_failures_counted` — 9 attempts with every 3rd failing, verifies 6 sent / 3 failed
- `test_npcap_availability_check` — verifies the pcap check doesn't panic
- `test_npcap_list_interfaces_if_available` — enumerates real interfaces if Npcap installed

### Python (`pytest`)
```
450 passed, 4 skipped, 0 failed
```

Skipped tests are native-import-failure tests (correctly skipped because the
native extension is installed).

---

## How It Works End-to-End

1. **Schema load**: User loads an XML packet schema via the GUI
2. **Config**: User configures interface, MAC addresses, rate, packet count
3. **Backend selection**: GUI checks `is_native_transport_available()` and shows NIC status
4. **Start**: `SenderService.start_sending()` creates the selected backend
5. **Native path**: `NativeSenderBackend.initialize()` validates transport + interface, creates Rust sender with `NpcapTransport`
6. **Send loop**: Rust `NativeSender::run()` builds Eth+TestGen+Payload frames, sends via `pcap_sendpacket`, tracks metrics atomically
7. **Live polling**: Python thread polls `SharedMetrics` via `get_sender_metrics()` (lock-free atomic reads, GIL released)
8. **GUI update**: Session panel shows Attempted/Sent/Failed/Bytes + PPS/Throughput/Elapsed in real time
9. **Stop**: User clicks Stop → `stop_sender()` sets atomic flag → loop exits → final metrics displayed

---

## Prerequisites

- **Npcap** (Windows) or **libpcap** (Linux) installed at runtime
  - Download: https://npcap.com
  - Check at install: "Install Npcap in WinPcap API-compatible Mode"
- **Rust toolchain** + **maturin** for building the native module
- **Scapy** for the Python backend (fallback)

Build: `cd native/rust_backend && maturin develop --release`
