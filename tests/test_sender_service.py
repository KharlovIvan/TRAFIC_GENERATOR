"""Tests for sender.sender_service (mocked transport)."""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from common.enums import GenerationMode
from common.exceptions import SenderConfigError, SenderOperationError
from sender.sender_config import SenderConfig
from sender.sender_service import SenderService
from sender.transports.base import SenderTransport

# A minimal valid XML schema for testing
_VALID_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<packet name="Test" totalBitLength="16">
  <header name="H1">
    <field name="val" type="INTEGER" bitLength="16" />
  </header>
</packet>
"""

_DUP_GLOBAL_FIELD_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<packet name="Test" totalBitLength="16">
    <header name="H1">
        <field name="dup" type="INTEGER" bitLength="8" />
    </header>
    <header name="H2">
        <field name="dup" type="INTEGER" bitLength="8" />
    </header>
</packet>
"""


class _NoopTransport(SenderTransport):
    """Transport that does nothing."""

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


class TestSenderServiceLoad:
    def test_load_valid_schema(self):
        path = _write_temp_xml()
        svc = SenderService()
        schema, warnings = svc.load_schema(path)
        assert schema.name == "Test"
        assert svc.schema is not None
        assert svc.fixed_values is not None

    def test_load_populates_defaults(self):
        path = _write_temp_xml()
        svc = SenderService()
        svc.load_schema(path)
        assert "val" in svc.fixed_values  # type: ignore[operator]

    def test_update_fixed_value(self):
        path = _write_temp_xml()
        svc = SenderService()
        svc.load_schema(path)
        svc.update_fixed_value("val", 1234)
        assert svc.fixed_values["val"] == 1234  # type: ignore[index]

    def test_update_before_load_raises(self):
        svc = SenderService()
        with pytest.raises(SenderOperationError):
            svc.update_fixed_value("x", 0)

    def test_load_rejects_duplicate_global_field_names(self):
        path = _write_temp_xml(_DUP_GLOBAL_FIELD_XML)
        svc = SenderService()
        with pytest.raises(SenderOperationError, match="duplicate field names"):
            svc.load_schema(path)


class TestSenderServiceStart:
    def test_start_without_schema_raises(self):
        svc = SenderService(transport=_NoopTransport())
        cfg = SenderConfig(interface="eth0")
        with pytest.raises(SenderOperationError, match="No schema"):
            svc.start_sending(cfg)

    def test_start_with_bad_config_raises(self):
        path = _write_temp_xml()
        svc = SenderService(transport=_NoopTransport())
        svc.load_schema(path)
        cfg = SenderConfig()  # missing interface
        with pytest.raises(SenderConfigError):
            svc.start_sending(cfg)

    def test_start_and_stop(self):
        path = _write_temp_xml()
        svc = SenderService(transport=_NoopTransport())
        svc.load_schema(path)
        cfg = SenderConfig(
            interface="dummy0",
            packet_count=2,
            packets_per_second=100_000,
            generation_mode=GenerationMode.FIXED,
        )
        metrics = svc.start_sending(cfg)
        assert metrics.packets_sent == 2

    def test_periodic_metrics_exposed(self):
        path = _write_temp_xml()
        svc = SenderService(transport=_NoopTransport())
        svc.load_schema(path)
        cfg = SenderConfig(
            interface="dummy0",
            packet_count=5,
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
        assert updates[-1]["packets_sent"] == 5

    def test_latest_metrics_after_send(self):
        path = _write_temp_xml()
        svc = SenderService(transport=_NoopTransport())
        svc.load_schema(path)
        cfg = SenderConfig(
            interface="dummy0",
            packet_count=3,
            packets_per_second=100_000,
            generation_mode=GenerationMode.FIXED,
        )
        svc.start_sending(cfg)
        assert svc.latest_metrics is not None
        assert svc.latest_metrics.packets_sent == 3

    def test_logs_reduced_to_important_events(self):
        """Ensure on_progress is called periodically, not per-packet."""
        path = _write_temp_xml()
        svc = SenderService(transport=_NoopTransport())
        svc.load_schema(path)
        cfg = SenderConfig(
            interface="dummy0",
            packet_count=20,
            packets_per_second=100_000,
            generation_mode=GenerationMode.FIXED,
        )
        updates: list[dict] = []
        svc.start_sending(
            cfg,
            on_progress=lambda m: updates.append(m.snapshot()),
            progress_interval=0.05,
        )
        # With 20 packets at 100k pps, the progress callbacks should be
        # much fewer than 20 (throttled).  The final callback is always
        # emitted by the engine.
        assert len(updates) >= 1
        assert len(updates) < 20
