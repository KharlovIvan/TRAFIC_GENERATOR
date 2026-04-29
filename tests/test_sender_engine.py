"""Tests for sender.sender_engine (mocked transport)."""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock, call

import pytest

from common.enums import FieldType, GenerationMode
from common.schema_models import FieldSchema, HeaderSchema, PacketSchema
from sender.sender_config import SenderConfig
from sender.sender_engine import SenderEngine
from sender.transports.base import SenderTransport


def _simple_schema() -> PacketSchema:
    f = FieldSchema(name="val", type=FieldType.INTEGER, bit_length=16)
    h = HeaderSchema(name="H", fields=[f])
    return PacketSchema(name="P", declared_total_bit_length=16, headers=[h])


class _MockTransport(SenderTransport):
    """In-memory transport for testing."""

    def __init__(self) -> None:
        self.opened_interface: str | None = None
        self.sent_frames: list[bytes] = []
        self.closed = False

    def open(self, interface: str) -> None:
        self.opened_interface = interface

    def send(self, frame_bytes: bytes) -> int:
        self.sent_frames.append(frame_bytes)
        return len(frame_bytes)

    def close(self) -> None:
        self.closed = True


class TestSenderEngine:
    def test_sends_packets(self):
        transport = _MockTransport()
        engine = SenderEngine(transport=transport)
        schema = _simple_schema()
        config = SenderConfig(
            interface="dummy0",
            packet_count=3,
            packets_per_second=100_000,
            generation_mode=GenerationMode.FIXED,
        )
        metrics = engine.run(config, schema, fixed_values={"val": 42})
        assert metrics.packets_sent == 3
        assert len(transport.sent_frames) == 3

    def test_stop_flag(self):
        transport = _MockTransport()
        engine = SenderEngine(transport=transport)
        schema = _simple_schema()
        config = SenderConfig(
            interface="dummy0",
            packets_per_second=100_000,
            generation_mode=GenerationMode.FIXED,
        )

        def stop_after_delay():
            time.sleep(0.15)
            engine.stop()

        t = threading.Thread(target=stop_after_delay)
        t.start()
        metrics = engine.run(config, schema, fixed_values={"val": 0})
        t.join()
        assert metrics.packets_sent > 0

    def test_progress_callback(self):
        transport = _MockTransport()
        engine = SenderEngine(transport=transport)
        schema = _simple_schema()
        config = SenderConfig(
            interface="dummy0",
            packet_count=5,
            packets_per_second=100_000,
            generation_mode=GenerationMode.FIXED,
        )
        calls: list[dict] = []
        metrics = engine.run(
            config, schema, fixed_values={"val": 1},
            on_progress=lambda m: calls.append(m.snapshot()),
            progress_interval=0.0,
        )
        # At least the final progress callback
        assert len(calls) >= 1
        assert calls[-1]["packets_sent"] == 5

    def test_duration_limit(self):
        transport = _MockTransport()
        engine = SenderEngine(transport=transport)
        schema = _simple_schema()
        config = SenderConfig(
            interface="dummy0",
            packets_per_second=100_000,
            duration_seconds=0.1,
            generation_mode=GenerationMode.FIXED,
        )
        metrics = engine.run(config, schema, fixed_values={"val": 0})
        assert metrics.packets_sent > 0
        assert metrics.elapsed_seconds < 1.0

    def test_uses_transport_abstraction(self):
        transport = _MockTransport()
        engine = SenderEngine(transport=transport)
        schema = _simple_schema()
        config = SenderConfig(
            interface="test_iface",
            packet_count=1,
            packets_per_second=100_000,
            generation_mode=GenerationMode.FIXED,
        )
        engine.run(config, schema, fixed_values={"val": 0})
        assert transport.opened_interface == "test_iface"
        assert transport.closed is True
        assert len(transport.sent_frames) == 1

    def test_transport_can_be_mocked_cleanly(self):
        mock = MagicMock(spec=SenderTransport)
        engine = SenderEngine(transport=mock)
        schema = _simple_schema()
        config = SenderConfig(
            interface="eth0",
            packet_count=2,
            packets_per_second=100_000,
            generation_mode=GenerationMode.FIXED,
        )
        engine.run(config, schema, fixed_values={"val": 7})
        mock.open.assert_called_once_with("eth0")
        assert mock.send.call_count == 2
        mock.close.assert_called_once()

    def test_bytes_sent_increments(self):
        transport = _MockTransport()
        engine = SenderEngine(transport=transport)
        schema = _simple_schema()
        config = SenderConfig(
            interface="dummy0",
            packet_count=3,
            packets_per_second=100_000,
            generation_mode=GenerationMode.FIXED,
        )
        metrics = engine.run(config, schema, fixed_values={"val": 0})
        assert metrics.bytes_sent > 0
        # All frames should be same size in FIXED mode
        frame_len = len(transport.sent_frames[0])
        assert metrics.bytes_sent == 3 * frame_len

    def test_random_mode(self):
        transport = _MockTransport()
        engine = SenderEngine(transport=transport)
        schema = _simple_schema()
        config = SenderConfig(
            interface="dummy0",
            packet_count=5,
            packets_per_second=100_000,
            generation_mode=GenerationMode.RANDOM,
        )
        metrics = engine.run(config, schema)
        assert metrics.packets_sent == 5
        assert len(transport.sent_frames) == 5
