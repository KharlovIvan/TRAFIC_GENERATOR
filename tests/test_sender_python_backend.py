"""Regression tests for PythonSenderBackend through SenderService."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from common.enums import BackendMode, GenerationMode
from common.metrics import SenderMetrics
from sender.backends.python_backend import PythonSenderBackend
from sender.sender_config import SenderConfig
from sender.sender_service import SenderService
from sender.transports.base import SenderTransport

_VALID_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<packet name="Test" totalBitLength="16">
  <header name="H1">
    <field name="val" type="INTEGER" bitLength="16" />
  </header>
</packet>
"""


class _NoopTransport(SenderTransport):
    def open(self, interface: str) -> None:
        pass

    def send(self, frame_bytes: bytes) -> int:
        return len(frame_bytes)

    def close(self) -> None:
        pass


def _write_temp_xml(content: str = _VALID_XML) -> Path:
    f = tempfile.NamedTemporaryFile(suffix=".xml", delete=False, mode="w", encoding="utf-8")
    f.write(content)
    f.close()
    return Path(f.name)


class TestPythonBackendRegression:
    """Ensure the Python backend still works identically through the service layer."""

    def test_fixed_mode_count(self):
        svc = SenderService(transport=_NoopTransport())
        svc.load_schema(_write_temp_xml())
        cfg = SenderConfig(
            interface="dummy0",
            packet_count=5,
            packets_per_second=100_000,
            generation_mode=GenerationMode.FIXED,
            backend_mode=BackendMode.PYTHON,
        )
        metrics = svc.start_sending(cfg)
        assert metrics.packets_sent == 5

    def test_random_mode_count(self):
        svc = SenderService(transport=_NoopTransport())
        svc.load_schema(_write_temp_xml())
        cfg = SenderConfig(
            interface="dummy0",
            packet_count=5,
            packets_per_second=100_000,
            generation_mode=GenerationMode.RANDOM,
            backend_mode=BackendMode.PYTHON,
        )
        metrics = svc.start_sending(cfg)
        assert metrics.packets_sent == 5

    def test_bytes_sent_positive(self):
        svc = SenderService(transport=_NoopTransport())
        svc.load_schema(_write_temp_xml())
        cfg = SenderConfig(
            interface="dummy0",
            packet_count=3,
            packets_per_second=100_000,
            generation_mode=GenerationMode.FIXED,
        )
        metrics = svc.start_sending(cfg)
        assert metrics.bytes_sent > 0

    def test_progress_callback_via_service(self):
        svc = SenderService(transport=_NoopTransport())
        svc.load_schema(_write_temp_xml())
        cfg = SenderConfig(
            interface="dummy0",
            packet_count=10,
            packets_per_second=100_000,
            generation_mode=GenerationMode.FIXED,
        )
        updates: list[dict] = []
        svc.start_sending(
            cfg,
            on_progress=lambda m: updates.append(m.snapshot()),
            progress_interval=0.0,
        )
        assert len(updates) >= 1
        assert updates[-1]["packets_sent"] == 10

    def test_latest_metrics_after_send(self):
        svc = SenderService(transport=_NoopTransport())
        svc.load_schema(_write_temp_xml())
        cfg = SenderConfig(
            interface="dummy0",
            packet_count=4,
            packets_per_second=100_000,
            generation_mode=GenerationMode.FIXED,
        )
        svc.start_sending(cfg)
        assert svc.latest_metrics is not None
        assert svc.latest_metrics.packets_sent == 4

    def test_fixed_values_update(self):
        svc = SenderService(transport=_NoopTransport())
        svc.load_schema(_write_temp_xml())
        svc.update_fixed_value("val", 0xBEEF)
        cfg = SenderConfig(
            interface="dummy0",
            packet_count=1,
            packets_per_second=100_000,
            generation_mode=GenerationMode.FIXED,
        )
        metrics = svc.start_sending(cfg)
        assert metrics.packets_sent == 1

    def test_validate_environment(self):
        errors = PythonSenderBackend.validate_environment()
        assert isinstance(errors, list)
        # Scapy should be installed in our test environment
