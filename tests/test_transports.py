"""Tests for sender.transports (transport abstraction layer)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from sender.transports.base import SenderTransport
from sender.transports.scapy_transport import ScapySenderTransport


class _InMemoryTransport(SenderTransport):
    """Concrete transport for testing the ABC contract."""

    def __init__(self) -> None:
        self.interface: str | None = None
        self.frames: list[bytes] = []
        self.is_closed = False

    def open(self, interface: str) -> None:
        self.interface = interface

    def send(self, frame_bytes: bytes) -> int:
        self.frames.append(frame_bytes)
        return len(frame_bytes)

    def close(self) -> None:
        self.is_closed = True


class TestSenderTransportABC:
    def test_concrete_implements_interface(self):
        t = _InMemoryTransport()
        t.open("eth0")
        t.send(b"\x00" * 14)
        t.close()
        assert t.interface == "eth0"
        assert len(t.frames) == 1
        assert t.is_closed

    def test_context_manager(self):
        t = _InMemoryTransport()
        with t:
            t.open("lo")
            t.send(b"\xff" * 20)
        assert t.is_closed

    def test_cannot_instantiate_abc(self):
        with pytest.raises(TypeError):
            SenderTransport()  # type: ignore[abstract]


class TestScapySenderTransport:
    def test_send_without_open_raises(self):
        t = ScapySenderTransport()
        with pytest.raises(RuntimeError, match="not open"):
            t.send(b"\x00")

    def test_close_without_open_is_safe(self):
        t = ScapySenderTransport()
        t.close()  # Should not raise


class TestTransportSubstitution:
    """Verify that the engine can swap transports without code changes."""

    def test_mock_transport_accepted_by_engine(self):
        from common.enums import FieldType, GenerationMode
        from common.schema_models import FieldSchema, HeaderSchema, PacketSchema
        from sender.sender_config import SenderConfig
        from sender.sender_engine import SenderEngine

        mock = MagicMock(spec=SenderTransport)
        engine = SenderEngine(transport=mock)
        f = FieldSchema(name="x", type=FieldType.INTEGER, bit_length=8)
        h = HeaderSchema(name="H", fields=[f])
        schema = PacketSchema(name="P", declared_total_bit_length=8, headers=[h])
        cfg = SenderConfig(
            interface="mock0",
            packet_count=1,
            packets_per_second=100_000,
            generation_mode=GenerationMode.FIXED,
        )
        engine.run(cfg, schema, fixed_values={"x": 0})
        mock.open.assert_called_once_with("mock0")
        mock.send.assert_called_once()
        mock.close.assert_called_once()
