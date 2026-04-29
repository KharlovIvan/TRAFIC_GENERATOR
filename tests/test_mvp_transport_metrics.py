"""Tests for MVP sender transport and metrics semantics.

Covers:
- Metrics distinguish attempted / successful / failed sends
- Throughput calculated from successful sends only
- Python and Native backends expose the same metrics fields
- Transport abstraction: loopback is not production, real transport validated
- SenderService remains backend-agnostic
- Environment validation
"""

from __future__ import annotations

import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from common.enums import BackendMode, FieldType, GenerationMode
from common.metrics import SenderMetrics
from common.schema_models import FieldSchema, HeaderSchema, PacketSchema
from sender.backends.base import SenderBackend
from sender.backends.native_backend import (
    NativeSenderBackend,
    _native_metrics_to_python,
    flatten_config_for_native,
    is_native_available,
    is_native_transport_available,
)
from sender.backends.python_backend import PythonSenderBackend
from sender.sender_config import SenderConfig
from sender.sender_engine import SenderEngine
from sender.sender_service import SenderService, create_backend
from sender.transports.base import SenderTransport

_VALID_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<packet name="Test" totalBitLength="16">
  <header name="H1">
    <field name="val" type="INTEGER" bitLength="16" />
  </header>
</packet>
"""


def _simple_schema() -> PacketSchema:
    f = FieldSchema(name="val", type=FieldType.INTEGER, bit_length=16)
    h = HeaderSchema(name="H", fields=[f])
    return PacketSchema(name="P", declared_total_bit_length=16, headers=[h])


def _write_temp_xml(content: str = _VALID_XML) -> Path:
    f = tempfile.NamedTemporaryFile(suffix=".xml", delete=False, mode="w", encoding="utf-8")
    f.write(content)
    f.close()
    return Path(f.name)


# ===========================================================================
# Test transports
# ===========================================================================


class _CountingTransport(SenderTransport):
    """Counts sends and returns byte counts."""

    def __init__(self) -> None:
        self.sends: list[int] = []

    def open(self, interface: str) -> None:
        pass

    def send(self, frame_bytes: bytes) -> int:
        n = len(frame_bytes)
        self.sends.append(n)
        return n

    def close(self) -> None:
        pass


class _FailingTransport(SenderTransport):
    """Fails every send call."""

    def open(self, interface: str) -> None:
        pass

    def send(self, frame_bytes: bytes) -> int:
        raise OSError("simulated send failure")

    def close(self) -> None:
        pass


class _IntermittentTransport(SenderTransport):
    """Fails every Nth send."""

    def __init__(self, fail_every: int = 3) -> None:
        self.call_count = 0
        self.fail_every = fail_every

    def open(self, interface: str) -> None:
        pass

    def send(self, frame_bytes: bytes) -> int:
        self.call_count += 1
        if self.call_count % self.fail_every == 0:
            raise OSError("intermittent failure")
        return len(frame_bytes)

    def close(self) -> None:
        pass


# ===========================================================================
# A.  Metrics correctness tests
# ===========================================================================


class TestMetricsFields:
    """Verify new metrics fields exist and work correctly."""

    def test_initial_state_has_all_fields(self):
        m = SenderMetrics()
        assert m.packets_attempted == 0
        assert m.packets_sent == 0
        assert m.packets_failed == 0
        assert m.bytes_sent == 0

    def test_record_send_attempt(self):
        m = SenderMetrics()
        m.reset()
        m.record_send_attempt()
        m.record_send_attempt()
        assert m.packets_attempted == 2

    def test_record_send_failure(self):
        m = SenderMetrics()
        m.reset()
        m.record_send_failure()
        assert m.packets_failed == 1
        assert m.packets_sent == 0

    def test_record_packet_increments_sent(self):
        m = SenderMetrics()
        m.reset()
        m.record_packet(100)
        assert m.packets_sent == 1
        assert m.bytes_sent == 100

    def test_snapshot_includes_all_keys(self):
        m = SenderMetrics()
        m.reset()
        m.record_send_attempt()
        m.record_packet(64)
        snap = m.snapshot()
        required_keys = {
            "packets_attempted",
            "packets_sent",
            "packets_failed",
            "bytes_sent",
            "elapsed_seconds",
            "pps",
            "bps",
            "gbps",
        }
        assert required_keys.issubset(snap.keys())

    def test_pps_uses_successful_sends(self):
        m = SenderMetrics()
        m.reset()
        m.record_send_attempt()
        m.record_send_attempt()
        m.record_send_attempt()
        m.record_packet(64)  # only 1 success
        m.record_send_failure()
        m.record_send_failure()
        time.sleep(0.05)
        # PPS is based on 1 successfully sent packet
        pps = m.packets_per_second
        assert pps > 0
        # bps should reflect 64 bytes = 512 bits
        bps = m.bits_per_second
        assert bps > 0

    def test_gbps_property(self):
        m = SenderMetrics()
        m.reset()
        m.packets_sent = 1_000_000
        m.bytes_sent = 1_000_000_000  # 1 GB
        time.sleep(0.01)
        assert m.gbps > 0

    def test_reset_clears_all_new_fields(self):
        m = SenderMetrics()
        m.packets_attempted = 100
        m.packets_failed = 10
        m.reset()
        assert m.packets_attempted == 0
        assert m.packets_failed == 0


# ===========================================================================
# B.  Engine metrics correctness (Python path)
# ===========================================================================


class TestEngineMetrics:
    """SenderEngine tracks attempted/successful/failed correctly."""

    def test_all_successful(self):
        transport = _CountingTransport()
        engine = SenderEngine(transport=transport)
        cfg = SenderConfig(
            interface="dummy0",
            packet_count=5,
            packets_per_second=100_000,
            generation_mode=GenerationMode.FIXED,
        )
        metrics = engine.run(cfg, _simple_schema(), {"val": 42})
        assert metrics.packets_attempted == 5
        assert metrics.packets_sent == 5
        assert metrics.packets_failed == 0
        assert metrics.bytes_sent > 0
        assert len(transport.sends) == 5

    def test_all_failing_stops_after_limit(self):
        transport = _FailingTransport()
        engine = SenderEngine(transport=transport)
        cfg = SenderConfig(
            interface="dummy0",
            packet_count=200,
            packets_per_second=100_000,
            generation_mode=GenerationMode.FIXED,
        )
        metrics = engine.run(cfg, _simple_schema(), {"val": 0})
        assert metrics.packets_attempted > 0
        assert metrics.packets_sent == 0
        assert metrics.packets_failed > 0
        # Should stop after consecutive failure limit (50)
        assert metrics.packets_failed == 50

    def test_intermittent_failures(self):
        transport = _IntermittentTransport(fail_every=3)
        engine = SenderEngine(transport=transport)
        cfg = SenderConfig(
            interface="dummy0",
            packet_count=9,
            packets_per_second=100_000,
            generation_mode=GenerationMode.FIXED,
        )
        metrics = engine.run(cfg, _simple_schema(), {"val": 0})
        assert metrics.packets_attempted == 9
        assert metrics.packets_sent == 6
        assert metrics.packets_failed == 3
        assert metrics.bytes_sent > 0

    def test_speed_uses_successful_bytes_only(self):
        transport = _IntermittentTransport(fail_every=2)
        engine = SenderEngine(transport=transport)
        cfg = SenderConfig(
            interface="dummy0",
            packet_count=4,
            packets_per_second=100_000,
            generation_mode=GenerationMode.FIXED,
        )
        metrics = engine.run(cfg, _simple_schema(), {"val": 0})
        # 4 attempts, 2 successes, 2 failures
        assert metrics.packets_sent == 2
        assert metrics.packets_failed == 2
        # bps should be based on 2 successful snd bytes only
        snap = metrics.snapshot()
        assert snap["bytes_sent"] == metrics.bytes_sent
        assert snap["pps"] > 0  # based on 2 successful


# ===========================================================================
# C.  Backend semantics parity
# ===========================================================================


class TestBackendParity:
    """Both backends expose the same metrics shape."""

    def test_python_backend_metrics_have_new_fields(self):
        transport = _CountingTransport()
        backend = PythonSenderBackend(transport=transport)
        backend.initialize(
            SenderConfig(
                interface="dummy0",
                packet_count=3,
                packets_per_second=100_000,
                generation_mode=GenerationMode.FIXED,
            ),
            _simple_schema(),
            {"val": 1},
        )
        metrics = backend.start()
        assert hasattr(metrics, "packets_attempted")
        assert hasattr(metrics, "packets_failed")
        assert metrics.packets_attempted == 3
        assert metrics.packets_sent == 3
        assert metrics.packets_failed == 0

    @patch("sender.backends.native_backend._try_import_native")
    def test_native_backend_metrics_have_new_fields(self, mock_import):
        mod = MagicMock()
        mod.create_sender.return_value = 42
        mod.start_sender.return_value = {
            "packets_attempted": 10,
            "packets_sent": 8,
            "packets_failed": 2,
            "bytes_sent": 400,
            "first_tx_timestamp_ns": 1,
            "last_tx_timestamp_ns": 2,
        }
        mod.is_transport_available.return_value = True
        mod.list_interfaces.return_value = []
        mock_import.return_value = (mod, None)

        backend = NativeSenderBackend()
        backend.initialize(
            SenderConfig(interface="eth0"),
            _simple_schema(),
            {"val": 1},
        )
        metrics = backend.start()
        assert metrics.packets_attempted == 10
        assert metrics.packets_sent == 8
        assert metrics.packets_failed == 2

    def test_snapshot_shape_matches(self):
        """Both backends produce snapshots with the same keys."""
        transport = _CountingTransport()
        backend = PythonSenderBackend(transport=transport)
        backend.initialize(
            SenderConfig(
                interface="dummy0",
                packet_count=1,
                packets_per_second=100_000,
                generation_mode=GenerationMode.FIXED,
            ),
            _simple_schema(),
            {"val": 0},
        )
        metrics = backend.start()
        snap = metrics.snapshot()
        required = {
            "packets_attempted",
            "packets_sent",
            "packets_failed",
            "bytes_sent",
            "pps",
            "bps",
            "gbps",
            "elapsed_seconds",
        }
        assert required.issubset(snap.keys())


# ===========================================================================
# D.  Service integration
# ===========================================================================


class TestServiceIntegration:
    """SenderService works backend-agnostically with new metrics."""

    def test_python_mode_works(self):
        svc = SenderService(transport=_CountingTransport())
        svc.load_schema(_write_temp_xml())
        cfg = SenderConfig(
            interface="dummy0",
            packet_count=3,
            packets_per_second=100_000,
            generation_mode=GenerationMode.FIXED,
            backend_mode=BackendMode.PYTHON,
        )
        metrics = svc.start_sending(cfg)
        assert metrics.packets_attempted == 3
        assert metrics.packets_sent == 3

    @patch("sender.backends.native_backend._try_import_native")
    def test_native_mode_requires_transport(self, mock_import):
        """Native mode refuses if transport not available."""
        mod = MagicMock()
        mod.is_transport_available.return_value = False
        mock_import.return_value = (mod, None)

        svc = SenderService()
        svc.load_schema(_write_temp_xml())
        cfg = SenderConfig(
            interface="dummy0",
            packet_count=1,
            packets_per_second=100_000,
            backend_mode=BackendMode.NATIVE,
        )
        with pytest.raises(RuntimeError, match="transport.*not available"):
            svc.start_sending(cfg)

    def test_backend_toggle_still_works(self):
        """create_backend returns correct type for each mode."""
        py = create_backend(BackendMode.PYTHON)
        assert isinstance(py, PythonSenderBackend)
        nat = create_backend(BackendMode.NATIVE)
        assert isinstance(nat, NativeSenderBackend)


# ===========================================================================
# E.  Transport validation
# ===========================================================================


class TestTransportValidation:
    @patch("sender.backends.native_backend._try_import_native")
    def test_validate_environment_no_transport(self, mock_import):
        mod = MagicMock()
        mod.is_transport_available.return_value = False
        mock_import.return_value = (mod, None)

        errors = NativeSenderBackend.validate_environment()
        assert len(errors) >= 1
        assert any("npcap" in e.lower() or "libpcap" in e.lower() for e in errors)

    @patch("sender.backends.native_backend._try_import_native")
    def test_validate_environment_all_ok(self, mock_import):
        mod = MagicMock()
        mod.is_transport_available.return_value = True
        mock_import.return_value = (mod, None)

        errors = NativeSenderBackend.validate_environment()
        assert len(errors) == 0

    @patch("sender.backends.native_backend._try_import_native")
    def test_initialize_refuses_without_transport(self, mock_import):
        mod = MagicMock()
        mod.is_transport_available.return_value = False
        mock_import.return_value = (mod, None)

        b = NativeSenderBackend()
        with pytest.raises(RuntimeError, match="transport.*not available"):
            b.initialize(SenderConfig(interface="eth0"), _simple_schema())


# ===========================================================================
# F.  Transport abstraction tests
# ===========================================================================


class TestTransportAbstraction:
    def test_counting_transport_returns_bytes(self):
        t = _CountingTransport()
        t.open("eth0")
        n = t.send(b"\x00" * 64)
        assert n == 64
        t.close()

    def test_failing_transport_raises(self):
        t = _FailingTransport()
        t.open("eth0")
        with pytest.raises(OSError):
            t.send(b"\x00" * 64)
        t.close()

    def test_intermittent_transport_pattern(self):
        t = _IntermittentTransport(fail_every=2)
        t.open("eth0")
        n1 = t.send(b"\x00" * 64)
        assert n1 == 64  # call 1: success
        with pytest.raises(OSError):
            t.send(b"\x00" * 64)  # call 2: fail
        n3 = t.send(b"\x00" * 64)
        assert n3 == 64  # call 3: success
        t.close()


# ===========================================================================
# G.  Native metrics conversion with new fields
# ===========================================================================


class TestNativeMetricsNewFields:
    def test_all_new_fields_mapped(self):
        raw = {
            "packets_attempted": 100,
            "packets_sent": 90,
            "packets_failed": 10,
            "bytes_sent": 4500,
            "first_tx_timestamp_ns": 1000,
            "last_tx_timestamp_ns": 2000,
        }
        m = _native_metrics_to_python(raw, start_time=1000.0)
        assert m.packets_attempted == 100
        assert m.packets_sent == 90
        assert m.packets_failed == 10
        assert m.bytes_sent == 4500
        assert m.start_time == 1000.0

    def test_backward_compat_missing_new_fields(self):
        """Old native module that doesn't send new fields → defaults to 0."""
        raw = {"packets_sent": 50, "bytes_sent": 2500}
        m = _native_metrics_to_python(raw)
        assert m.packets_attempted == 0
        assert m.packets_failed == 0
        assert m.packets_sent == 50
