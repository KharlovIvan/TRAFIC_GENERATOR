"""Tests for receiver.receiver_engine – exercises packet handling logic.

Since *actually* sniffing the network requires admin/root and a real NIC,
we test the engine's packet-processing logic by:
  1. Building realistic Scapy Ether frames.
  2. Mocking AsyncSniffer so its start()/stop() are no-ops.
  3. Directly invoking the prn callback registered by the engine.
"""

from __future__ import annotations

import struct
import tempfile
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from common.enums import ExportFormat, FieldType
from common.exceptions import PacketParseError
from common.metrics import ReceiverMetrics
from common.schema_models import FieldSchema, HeaderSchema, PacketSchema
from common.testgen_header import (
    TESTGEN_HEADER_FORMAT,
    TESTGEN_HEADER_SIZE,
    TESTGEN_MAGIC,
    TESTGEN_VERSION,
    build_testgen_header,
)
from receiver.receiver_config import ReceiverConfig
from receiver.receiver_engine import ReceiverEngine


# ----- helpers -----

def _simple_schema(bit_length: int = 16) -> PacketSchema:
    """A one-field INTEGER schema."""
    return PacketSchema(
        name="Test",
        declared_total_bit_length=bit_length,
        headers=[
            HeaderSchema(name="H1", fields=[
                FieldSchema(name="val", type=FieldType.INTEGER, bit_length=bit_length),
            ]),
        ],
    )


def _build_ethernet_frame(
    dst: str = "ff:ff:ff:ff:ff:ff",
    src: str = "00:11:22:33:44:55",
    ethertype: int = 0x88B5,
    payload: bytes = b"",
) -> bytes:
    """Minimally build a 14-byte Ethernet header + payload."""
    dst_b = bytes.fromhex(dst.replace(":", ""))
    src_b = bytes.fromhex(src.replace(":", ""))
    return dst_b + src_b + ethertype.to_bytes(2, "big") + payload


def _build_valid_frame(
    val: int = 42,
    stream_id: int = 1,
    sequence: int = 0,
) -> bytes:
    """Build a complete valid frame with TestGenHeader + 2-byte INTEGER payload."""
    user_payload = val.to_bytes(2, "big")
    tg_hdr = build_testgen_header(
        stream_id=stream_id,
        sequence=sequence,
        tx_timestamp_ns=time.time_ns(),
        payload_len=len(user_payload),
    )
    return _build_ethernet_frame(payload=tg_hdr + user_payload)


class _FakePayload:
    """Mimics Scapy's Raw payload layer with proper __bytes__ support."""

    def __init__(self, data: bytes) -> None:
        self._data = data

    def __bytes__(self) -> bytes:
        return self._data


class FakePacket:
    """Mimics a Scapy Ether packet just enough for the engine callback."""

    def __init__(self, frame_bytes: bytes) -> None:
        self._raw = frame_bytes
        self.dst = ":".join(f"{b:02x}" for b in frame_bytes[0:6])
        self.src = ":".join(f"{b:02x}" for b in frame_bytes[6:12])
        self.type = int.from_bytes(frame_bytes[12:14], "big")
        self.payload = _FakePayload(frame_bytes[14:])

    def __bytes__(self) -> bytes:
        return self._raw

    def __len__(self) -> int:
        return len(self._raw)


def _make_config(
    tmp_path: Path,
    fmt: ExportFormat = ExportFormat.JSON,
    packet_limit: int | None = None,
    duration_sec: float | None = None,
) -> ReceiverConfig:
    return ReceiverConfig(
        interface_name="lo",
        schema_path="schema.xml",
        export_format=fmt,
        pcap_output_path=str(tmp_path / "out.pcap"),
        json_output_path=str(tmp_path / "out.jsonl"),
        packet_limit=packet_limit,
        duration_sec=duration_sec,
    )


class _CapturedSniffer:
    """Captures the prn callback so tests can deliver fake packets."""

    def __init__(self):
        self.prn = None
        self.lfilter = None
        self.started = False

    def __call__(self, **kw: Any) -> "_CapturedSniffer":
        self.prn = kw.get("prn")
        self.lfilter = kw.get("lfilter")
        return self

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        pass


# ---- tests ----

class TestReceiverEnginePacketParsing:
    """Uses mocked AsyncSniffer to feed packets to the engine callback."""

    def _run_with_packets(
        self,
        packets: list[FakePacket],
        schema: PacketSchema | None = None,
        fmt: ExportFormat = ExportFormat.JSON,
        packet_limit: int | None = None,
    ) -> tuple[ReceiverMetrics, list[dict]]:
        """Helper: feed packets through the engine and return metrics + records."""
        schema = schema or _simple_schema()
        tmp = Path(tempfile.mkdtemp())
        engine = ReceiverEngine()
        records: list[dict] = []

        captured_sniffer = _CapturedSniffer()

        def _fake_sniffer_class(**kw: Any):
            captured_sniffer.prn = kw.get("prn")
            captured_sniffer.lfilter = kw.get("lfilter")
            return captured_sniffer

        def _start_and_deliver():
            captured_sniffer.started = True
            for pkt in packets:
                if engine.is_stopped:
                    break
                if captured_sniffer.lfilter and not captured_sniffer.lfilter(pkt):
                    continue
                captured_sniffer.prn(pkt)

        captured_sniffer.start = _start_and_deliver

        config = ReceiverConfig(
            interface_name="lo",
            schema_path="schema.xml",
            export_format=fmt,
            pcap_output_path=str(tmp / "out.pcap"),
            json_output_path=str(tmp / "out.jsonl"),
            packet_limit=packet_limit or len(packets),
        )

        def _on_packet(record: dict) -> None:
            records.append(record)

        with patch("scapy.all.AsyncSniffer", side_effect=_fake_sniffer_class):
            metrics = engine.run(
                config=config,
                schema=schema,
                on_packet=_on_packet,
            )

        return metrics, records

    def test_valid_packet_parsed(self):
        frame = _build_valid_frame(val=100, stream_id=7, sequence=0)
        pkt = FakePacket(frame)
        metrics, records = self._run_with_packets([pkt])

        assert metrics.packets_received == 1
        assert metrics.packets_parsed_ok == 1
        assert metrics.packets_invalid == 0
        assert len(records) == 1
        assert records[0]["valid"] is True
        assert records[0]["testgen_header"]["stream_id"] == 7
        assert records[0]["payload"]["val"] == 100

    def test_invalid_magic_counted(self):
        """Bad magic → packet counted as invalid, raw PCAP still ok."""
        bad_tg = struct.pack(TESTGEN_HEADER_FORMAT, 0xBEEF, TESTGEN_VERSION, 0, 1, 0, 0, 2)
        payload = b"\x00\x01"
        frame = _build_ethernet_frame(payload=bad_tg + payload)
        pkt = FakePacket(frame)
        metrics, records = self._run_with_packets([pkt])

        assert metrics.packets_received == 1
        assert metrics.packets_invalid == 1
        assert records[0]["valid"] is False
        assert "magic" in records[0]["error"].lower()

    def test_invalid_version_counted(self):
        bad_tg = struct.pack(TESTGEN_HEADER_FORMAT, TESTGEN_MAGIC, 99, 0, 1, 0, 0, 2)
        payload = b"\x00\x01"
        frame = _build_ethernet_frame(payload=bad_tg + payload)
        pkt = FakePacket(frame)
        metrics, records = self._run_with_packets([pkt])

        assert metrics.packets_received == 1
        assert metrics.packets_invalid == 1
        assert "version" in records[0]["error"].lower()

    def test_truncated_frame_is_invalid(self):
        """A frame with fewer than 28 bytes after Ether header."""
        frame = _build_ethernet_frame(payload=b"\x00" * 10)
        pkt = FakePacket(frame)
        metrics, records = self._run_with_packets([pkt])

        assert metrics.packets_invalid == 1
        assert records[0]["valid"] is False

    def test_multiple_packets_metrics(self):
        pkts = [
            FakePacket(_build_valid_frame(val=i, stream_id=1, sequence=i))
            for i in range(5)
        ]
        metrics, records = self._run_with_packets(pkts, packet_limit=5)

        assert metrics.packets_received == 5
        assert metrics.packets_parsed_ok == 5
        assert all(r["valid"] for r in records)

    def test_stream_tracking(self):
        pkts = [
            FakePacket(_build_valid_frame(val=1, stream_id=10, sequence=0)),
            FakePacket(_build_valid_frame(val=2, stream_id=20, sequence=0)),
            FakePacket(_build_valid_frame(val=3, stream_id=10, sequence=1)),
        ]
        metrics, _ = self._run_with_packets(pkts, packet_limit=3)

        assert metrics.stream_ids_seen == {10, 20}
        assert metrics.last_sequence_per_stream[10] == 1
        assert metrics.last_sequence_per_stream[20] == 0

    def test_ethertype_filter(self):
        """lfilter should reject frames with wrong EtherType."""
        wrong_type_frame = _build_ethernet_frame(ethertype=0x0800, payload=b"\x00" * 40)
        wrong_pkt = FakePacket(wrong_type_frame)

        good_frame = _build_valid_frame(val=1)
        good_pkt = FakePacket(good_frame)

        # Only the good packet should be processed
        metrics, records = self._run_with_packets(
            [wrong_pkt, good_pkt], packet_limit=1
        )
        assert metrics.packets_received == 1
        assert records[0]["valid"] is True

    def test_json_export_file_written(self):
        """When JSON export is enabled, the output file should exist with content."""
        tmp = Path(tempfile.mkdtemp())
        frame = _build_valid_frame(val=1)
        pkt = FakePacket(frame)
        schema = _simple_schema()

        config = ReceiverConfig(
            interface_name="lo",
            schema_path="schema.xml",
            export_format=ExportFormat.JSON,
            json_output_path=str(tmp / "out.jsonl"),
            packet_limit=1,
        )

        captured_sniffer = _CapturedSniffer()

        def _fake_sniffer(**kw: Any):
            captured_sniffer.prn = kw.get("prn")
            captured_sniffer.lfilter = kw.get("lfilter")
            return captured_sniffer

        def _start_and_deliver():
            captured_sniffer.started = True
            captured_sniffer.prn(pkt)

        captured_sniffer.start = _start_and_deliver

        engine = ReceiverEngine()
        with patch("scapy.all.AsyncSniffer", side_effect=_fake_sniffer):
            engine.run(config=config, schema=schema)

        jsonl = (tmp / "out.jsonl")
        assert jsonl.exists()
        content = jsonl.read_text()
        assert '"valid": true' in content or '"valid":true' in content
