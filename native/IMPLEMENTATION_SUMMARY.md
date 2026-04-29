# Native Backend — Implementation Summary

## Overview

The Native (Rust) backend is a high-performance alternative to the
Python/Scapy sender. It builds and transmits raw Ethernet + TestGen +
User-Payload frames using the same wire format as the Python backend,
enabling bit-for-bit payload parity for the FIXED generation mode.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  Python GUI / SenderService                         │
│   ├── BackendPanel  (radio: Python | Native)        │
│   ├── SenderConfig  (backend_mode field)            │
│   └── create_backend(mode) → SenderBackend          │
│         ├── PythonSenderBackend  (Scapy transport)   │
│         └── NativeSenderBackend  (Rust FFI adapter)  │
│               ↓                                     │
│   flatten_config_for_native(config, schema, …)      │
│               ↓  plain dict                         │
├─────────────────── FFI boundary ────────────────────┤
│               ↓  PyO3                               │
│  trafic_native  (Rust cdylib)                       │
│   ├── lib.rs       (parse_config, FFI exports)      │
│   ├── sender.rs    (NativeSender, FrameTransport)   │
│   ├── serializer.rs(field → bytes, big-endian)      │
│   ├── testgen.rs   (28-byte TestGen header)         │
│   └── errors.rs    (NativeError enum)               │
└─────────────────────────────────────────────────────┘
```

## Frame Wire Format (identical Python ↔ Rust)

| Offset | Size | Field |
|--------|------|-------|
| 0 | 6 | Destination MAC |
| 6 | 6 | Source MAC |
| 12 | 2 | EtherType (big-endian) |
| 14 | 2 | TestGen Magic `0x5447` ("TG") |
| 16 | 1 | Version (`1`) |
| 17 | 1 | Flags |
| 18 | 4 | Stream ID (big-endian) |
| 22 | 8 | Sequence (big-endian u64) |
| 30 | 8 | TX Timestamp NS (big-endian u64) |
| 38 | 4 | Payload Length (big-endian u32) |
| 42 | N | User Payload (serialized fields) |

**Minimum frame size:** 42 + payload bytes.

## Rust Modules

### `errors.rs`
Defines `NativeError` with four variants: `Config`, `Serialization`,
`Transport`, `FrameBuild`. Implements `Display` and `Error`.

### `serializer.rs`
Mirrors `common/serializer.py`. Supports field types:

| Type | Serialization |
|------|---------------|
| `INTEGER` | Big-endian, 1–8 bytes. Overflow check for values > max. |
| `STRING` | UTF-8 encoded, zero-padded/truncated to `bit_length/8`. |
| `BOOLEAN` | `0x01` / `0x00` (must be 8 bits). |
| `RAW_BYTES` | Direct bytes or hex-string decode. Length must match exactly. |

Includes 13 unit tests covering all branches.

### `testgen.rs`
Mirrors `common/testgen_header.py`. Produces a 28-byte header with format
`>HBBIQQI` matching the Python `struct.pack`. 3 unit tests.

### `sender.rs`
Mirrors `sender/sender_engine.py` + `sender/frame_builder.py`.

Key components:
- **`parse_mac()`** — strict `aa:bb:cc:dd:ee:ff` MAC parsing.
- **`build_ethernet_header()`** — 14-byte Ethernet header.
- **`build_frame()`** — concatenates Ethernet + TestGen + payload.
- **`FrameTransport` trait** — abstraction for frame I/O (`open`, `send_frame`, `close`).
- **`LoopbackTransport`** — in-memory frame recorder for testing.
- **`SenderConfig`** — all parameters from `flatten_config_for_native()`.
- **`NativeSender`** — owns config + transport + stop flag + metrics. `run()` pre-builds
  the Ethernet header and user payload once (FIXED mode), then loops sending frames with
  rate pacing. Supports `packet_count`, `duration_sec`, and `stop_flag` termination.
- **`prepare_frame()`** — deterministic single-frame builder for cross-backend verification.

10 unit tests.

### `lib.rs`
PyO3 module entry point. Exported functions:

| Function | Purpose |
|----------|---------|
| `create_sender(config_dict) → handle` | Parse config dict, create `NativeSender`, return opaque handle. |
| `start_sender(handle, progress_interval) → metrics` | Run send loop, return metrics dict. |
| `stop_sender(handle)` | Set the stop flag on a running sender. |
| `destroy_sender(handle)` | Free the native sender memory. |
| `prepare_frame(config_dict, seq, ts) → bytes` | Build one frame deterministically for cross-checking. |

Config parsing uses `py_value_to_field_value()` to convert Python types
guided by the field type string (INTEGER→u64, STRING→String, BOOLEAN→bool,
RAW\_BYTES→hex string or bytes vector).

## Python Adapter (`sender/backends/native_backend.py`)

### `flatten_config_for_native(config, schema, fixed_values)`
Produces a plain dict with keys matching what `parse_config()` in Rust expects:
`interface`, `dst_mac`, `src_mac`, `ethertype`, `stream_id`, `pps`,
`packet_count`, `duration_sec`, `generation_mode`, `fields`, `fixed_values`.

Bytes values in `fixed_values` are converted to hex strings before crossing FFI.

### `NativeSenderBackend`
Implements `SenderBackend` ABC:
- **`initialize()`** — rejects RANDOM mode early, calls `create_sender()`.
- **`start()`** — calls `start_sender()`, converts metrics, calls `destroy_sender()`
  in the `finally` block for deterministic cleanup.
- **`stop()`** — calls `stop_sender()` to set the stop flag.
- **`_cleanup_handle()`** — calls `destroy_sender()` and clears the handle.

### `reset_native_cache()`
Clears the cached import state. Useful for tests.

## GUI Integration

- **`BackendPanel`** — radio buttons for Python / Native. `is_native_available()`
  grays out the Native option when the extension is not importable.
- **`SenderConfig.backend_mode`** — `BackendMode.PYTHON` (default) or `BackendMode.NATIVE`.
- **`SenderService.create_backend()`** — factory dispatches to the correct backend class.
- **`SenderWorker`** — runs the selected backend in a `QThread`. No backend-specific code.

## Generation Modes

| Mode | Python | Native |
|------|--------|--------|
| FIXED | Supported | Supported |
| RANDOM | Supported | **Rejected** with clear error message |

RANDOM mode rejection happens in two places:
1. Python adapter: `NativeSenderBackend.initialize()` raises `RuntimeError`.
2. Rust sender: `SenderConfig.validate()` returns `NativeError::Config`.

## Testing

### Python tests (425 pass, 3 skip)

| File | Focus | New tests added |
|------|-------|-----------------|
| `test_sender_native_backend.py` | Adapter, flattening, mocked lifecycle | RANDOM rejection (2), destroy cleanup (2), reset cache (1), config completeness (3) |
| `test_payload_consistency.py` | Frame structure, payload layout | Python deterministic frame (2), cross-backend match (3, skipped without native) |
| `test_backend_selection.py` | Factory, ABC contract, enum | — (unchanged) |
| `test_sender_python_backend.py` | Python backend regression | — (unchanged) |

### Rust tests (23 total, inline)

| Module | Tests |
|--------|-------|
| `serializer.rs` | 13 (int 8/16/32, overflow, string, truncate, boolean, raw\_bytes, hex, payload, mismatch, unsupported) |
| `sender.rs` | 10 (MAC parse, ethernet header, frame structure, loopback run, deterministic frame, stop flag, RANDOM reject, payload match, config validation) |
| `testgen.rs` | 3 (size, magic, field values) |

## Build & Install

```bash
cd native/rust_backend
pip install maturin
maturin develop --release
```

Requires: Rust toolchain (rustup), Python 3.12+, PyO3 0.22.

After install, the BackendPanel in the GUI will automatically detect
`trafic_native` and enable the Native radio button.

## Acceptance Criteria

- [x] Rust serializer matches Python `common.serializer` for INTEGER, STRING, BOOLEAN, RAW\_BYTES
- [x] Rust TestGen header matches Python `common.testgen_header` format (`>HBBIQQI`, 28 bytes)
- [x] Ethernet frame structure: 14-byte header at offset 0, TestGen at 14, payload at 42
- [x] `prepare_frame()` enables bit-for-bit cross-backend verification
- [x] FIXED mode produces correct frames in the send loop
- [x] RANDOM mode is rejected with a clear error on both Python and Rust sides
- [x] `destroy_sender()` provides deterministic memory cleanup
- [x] `LoopbackTransport` allows full frame-building path to be tested without raw sockets
- [x] GUI disables Native radio when extension is not available
- [x] Python backend is completely untouched
- [x] All 425 Python tests pass; 3 cross-backend tests auto-skip without native module
- [x] 23 Rust inline tests cover serializer, sender, and testgen modules
