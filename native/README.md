# Native Backends for Traffic Generator

This directory contains the native (Rust and C++) backend implementations
for the traffic generator.  They are optional — the Python backend works
independently.

## Directory structure

```
native/
  rust_backend/     Rust implementation (preferred)
  cpp_backend/      C++ implementation (alternative)
```

---

## Rust backend

### Prerequisites

| Tool | Minimum version |
|------|----------------|
| Rust (rustc + cargo) | 1.75+ |
| Python | 3.12+ |
| maturin | 1.4+ |

Install maturin:

```bash
pip install maturin
```

### Build & install (development mode)

```bash
cd native/rust_backend
maturin develop --release
```

This compiles the Rust code and installs `trafic_native` as a Python
package into the current environment.

### Build a wheel

```bash
maturin build --release
pip install target/wheels/trafic_native-*.whl
```

### Run Rust tests

```bash
cargo test
```

### Windows notes

- Install Rust via <https://rustup.rs>.
- Ensure the MSVC toolchain is available (Visual Studio Build Tools).
- Npcap or WinPcap may be needed for raw socket sending.

### Linux notes

- `sudo` or `CAP_NET_RAW` may be needed for raw socket sending.
- Install Rust via `rustup`.

---

## C++ backend

### Prerequisites

| Tool | Minimum version |
|------|----------------|
| C++ compiler | C++17 capable |
| CMake | 3.20+ |
| Python | 3.12+ |
| pybind11 | 2.11+ |

### Build & install

```bash
cd native/cpp_backend
pip install .
```

Or use CMake directly:

```bash
mkdir build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
cmake --build . --config Release
```

### Windows notes

- Visual Studio 2022 or Build Tools with C++ workload.
- pybind11 is fetched automatically via CMake FetchContent.

---

## Verifying the native backend is available

From Python:

```python
try:
    import trafic_native
    print("Native backend version:", trafic_native.__version__)
except ImportError:
    print("Native backend not installed")
```

Or launch the Sender GUI — the Backend panel will show the availability
status automatically.

## Switching backend mode in the GUI

1. Open the Sender GUI.
2. In the **Backend** section, select **Python** or **Native (Rust/C++)**.
3. Load a schema and configure your session normally.
4. Click **Start**.

Both backends use the same XML schema and the same GUI controls.
