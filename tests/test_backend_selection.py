"""Tests for sender backend selection, factory, and abstraction layer."""

from __future__ import annotations

import pytest

from common.enums import BackendMode, GenerationMode
from common.metrics import SenderMetrics
from common.schema_models import FieldSchema, HeaderSchema, PacketSchema
from common.enums import FieldType
from sender.backends.base import SenderBackend
from sender.backends.python_backend import PythonSenderBackend
from sender.backends.native_backend import (
    NativeSenderBackend,
    flatten_schema_for_native,
    flatten_config_for_native,
    is_native_available,
)
from sender.sender_config import SenderConfig
from sender.sender_service import SenderService, create_backend
from sender.transports.base import SenderTransport


def _simple_schema() -> PacketSchema:
    f = FieldSchema(name="val", type=FieldType.INTEGER, bit_length=16)
    h = HeaderSchema(name="H", fields=[f])
    return PacketSchema(name="P", declared_total_bit_length=16, headers=[h])


class _NoopTransport(SenderTransport):
    def open(self, interface: str) -> None:
        pass

    def send(self, frame_bytes: bytes) -> int:
        return len(frame_bytes)

    def close(self) -> None:
        pass


# ===========================================================================
# Backend mode enum
# ===========================================================================


class TestBackendMode:
    def test_default_is_python(self):
        cfg = SenderConfig(interface="eth0")
        assert cfg.backend_mode is BackendMode.PYTHON

    def test_set_native(self):
        cfg = SenderConfig(interface="eth0", backend_mode=BackendMode.NATIVE)
        assert cfg.backend_mode is BackendMode.NATIVE

    def test_enum_values(self):
        assert BackendMode.PYTHON.value == "PYTHON"
        assert BackendMode.NATIVE.value == "NATIVE"


# ===========================================================================
# create_backend factory
# ===========================================================================


class TestCreateBackend:
    def test_python_mode_returns_python_backend(self):
        backend = create_backend(BackendMode.PYTHON, transport=_NoopTransport())
        assert isinstance(backend, PythonSenderBackend)

    def test_native_mode_returns_native_backend(self):
        backend = create_backend(BackendMode.NATIVE)
        assert isinstance(backend, NativeSenderBackend)

    def test_all_backends_are_sender_backend(self):
        for mode in BackendMode:
            backend = create_backend(mode, transport=_NoopTransport())
            assert isinstance(backend, SenderBackend)


# ===========================================================================
# SenderBackend ABC contract
# ===========================================================================


class TestBackendContract:
    """Verify that both backends implement the full interface."""

    @pytest.fixture(params=[BackendMode.PYTHON, BackendMode.NATIVE])
    def backend(self, request):
        return create_backend(request.param, transport=_NoopTransport())

    def test_has_initialize(self, backend):
        assert callable(getattr(backend, "initialize"))

    def test_has_start(self, backend):
        assert callable(getattr(backend, "start"))

    def test_has_stop(self, backend):
        assert callable(getattr(backend, "stop"))

    def test_has_is_running(self, backend):
        assert callable(getattr(backend, "is_running"))

    def test_has_get_metrics(self, backend):
        assert callable(getattr(backend, "get_metrics"))

    def test_has_validate_environment(self, backend):
        assert callable(getattr(type(backend), "validate_environment"))

    def test_has_get_backend_name(self, backend):
        name = type(backend).get_backend_name()
        assert isinstance(name, str)
        assert len(name) > 0


# ===========================================================================
# PythonSenderBackend specifics
# ===========================================================================


class TestPythonSenderBackend:
    def test_backend_name(self):
        assert PythonSenderBackend.get_backend_name() == "Python (Scapy)"

    def test_validate_environment_returns_list(self):
        errors = PythonSenderBackend.validate_environment()
        assert isinstance(errors, list)

    def test_initial_state(self):
        b = PythonSenderBackend(transport=_NoopTransport())
        assert not b.is_running()
        m = b.get_metrics()
        assert isinstance(m, SenderMetrics)
        assert m.packets_sent == 0

    def test_start_without_initialize_raises(self):
        b = PythonSenderBackend(transport=_NoopTransport())
        with pytest.raises(RuntimeError, match="not initialized"):
            b.start()

    def test_full_lifecycle(self):
        b = PythonSenderBackend(transport=_NoopTransport())
        schema = _simple_schema()
        cfg = SenderConfig(
            interface="dummy0",
            packet_count=3,
            packets_per_second=100_000,
            generation_mode=GenerationMode.FIXED,
        )
        b.initialize(cfg, schema, {"val": 42})
        metrics = b.start()
        assert metrics.packets_sent == 3
        assert not b.is_running()


# ===========================================================================
# NativeSenderBackend specifics
# ===========================================================================


class TestNativeSenderBackend:
    def test_backend_name(self):
        assert NativeSenderBackend.get_backend_name() == "Native (Rust/C++)"

    def test_native_not_available(self):
        # Unless the native extension is installed, it should gracefully fail
        if not is_native_available():
            errors = NativeSenderBackend.validate_environment()
            assert len(errors) > 0
            assert "not available" in errors[0].lower()

    def test_initialize_without_native_raises(self):
        if is_native_available():
            pytest.skip("Native module is installed")
        b = NativeSenderBackend()
        schema = _simple_schema()
        cfg = SenderConfig(interface="eth0")
        with pytest.raises(RuntimeError, match="not available"):
            b.initialize(cfg, schema)

    def test_start_without_initialize_raises(self):
        b = NativeSenderBackend()
        with pytest.raises(RuntimeError, match="not initialized"):
            b.start()

    def test_initial_metrics_empty(self):
        b = NativeSenderBackend()
        m = b.get_metrics()
        assert m.packets_sent == 0


# ===========================================================================
# Schema/config flattening for native FFI
# ===========================================================================


class TestNativeFlattening:
    def test_flatten_schema_simple(self):
        schema = _simple_schema()
        flat = flatten_schema_for_native(schema)
        assert len(flat) == 1
        assert flat[0]["name"] == "val"
        assert flat[0]["type"] == "INTEGER"
        assert flat[0]["bit_length"] == 16

    def test_flatten_schema_multi_field(self):
        f1 = FieldSchema(name="a", type=FieldType.INTEGER, bit_length=8)
        f2 = FieldSchema(name="b", type=FieldType.STRING, bit_length=32)
        h = HeaderSchema(name="H", fields=[f1, f2])
        schema = PacketSchema(name="X", declared_total_bit_length=40, headers=[h])
        flat = flatten_schema_for_native(schema)
        assert len(flat) == 2
        assert flat[0]["name"] == "a"
        assert flat[1]["type"] == "STRING"
        assert flat[1]["bit_length"] == 32

    def test_flatten_config(self):
        schema = _simple_schema()
        cfg = SenderConfig(
            interface="eth0",
            packets_per_second=1000,
            packet_count=100,
            generation_mode=GenerationMode.FIXED,
        )
        native_cfg = flatten_config_for_native(cfg, schema, {"val": 42})
        assert native_cfg["interface"] == "eth0"
        assert native_cfg["pps"] == 1000
        assert native_cfg["packet_count"] == 100
        assert native_cfg["generation_mode"] == "FIXED"
        assert native_cfg["fixed_values"]["val"] == 42

    def test_flatten_config_bytes_to_hex(self):
        schema = _simple_schema()
        cfg = SenderConfig(interface="eth0")
        native_cfg = flatten_config_for_native(cfg, schema, {"val": b"\xAB\xCD"})
        assert native_cfg["fixed_values"]["val"] == "abcd"


# ===========================================================================
# SenderService backend selection integration
# ===========================================================================


class TestSenderServiceBackendSelection:
    def test_service_uses_python_by_default(self):
        import tempfile
        from pathlib import Path

        xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<packet name="T" totalBitLength="16">
  <header name="H">
    <field name="v" type="INTEGER" bitLength="16" />
  </header>
</packet>
"""
        f = tempfile.NamedTemporaryFile(suffix=".xml", delete=False, mode="w", encoding="utf-8")
        f.write(xml)
        f.close()
        path = Path(f.name)

        svc = SenderService(transport=_NoopTransport())
        svc.load_schema(path)
        cfg = SenderConfig(
            interface="dummy0",
            packet_count=2,
            packets_per_second=100_000,
            generation_mode=GenerationMode.FIXED,
            backend_mode=BackendMode.PYTHON,
        )
        metrics = svc.start_sending(cfg)
        assert metrics.packets_sent == 2

    def test_service_native_without_extension_raises(self):
        if is_native_available():
            pytest.skip("Native module is installed")

        import tempfile
        from pathlib import Path

        xml = """\
<?xml version="1.0" encoding="UTF-8"?>
<packet name="T" totalBitLength="16">
  <header name="H">
    <field name="v" type="INTEGER" bitLength="16" />
  </header>
</packet>
"""
        f = tempfile.NamedTemporaryFile(suffix=".xml", delete=False, mode="w", encoding="utf-8")
        f.write(xml)
        f.close()
        path = Path(f.name)

        svc = SenderService(transport=_NoopTransport())
        svc.load_schema(path)
        cfg = SenderConfig(
            interface="dummy0",
            packet_count=2,
            backend_mode=BackendMode.NATIVE,
        )
        with pytest.raises(RuntimeError, match="not available"):
            svc.start_sending(cfg)
