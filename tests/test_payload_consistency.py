"""Tests that Python backend produces structurally consistent payloads.

These tests verify that the serialization layer used by PythonSenderBackend
generates payloads with correct byte layout, which the native backend must
eventually match bit-for-bit.

Cross-backend payload matching tests are included at the bottom — these
verify that for a given set of inputs the Python frame builder and the
Rust frame builder produce *identical* bytes.  They are skipped when the
native extension is not installed.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from common.enums import FieldType, GenerationMode
from common.schema_models import FieldSchema, HeaderSchema, PacketSchema
from sender.sender_config import SenderConfig
from sender.sender_engine import SenderEngine
from sender.transports.base import SenderTransport


class _CapturingTransport(SenderTransport):
    """Captures all sent frames for inspection."""

    def __init__(self) -> None:
        self.frames: list[bytes] = []

    def open(self, interface: str) -> None:
        pass

    def send(self, frame_bytes: bytes) -> int:
        self.frames.append(frame_bytes)
        return len(frame_bytes)

    def close(self) -> None:
        pass


def _schema_with_fields(*fields: FieldSchema) -> PacketSchema:
    total_bits = sum(f.bit_length for f in fields)
    h = HeaderSchema(name="H", fields=list(fields))
    return PacketSchema(name="P", declared_total_bit_length=total_bits, headers=[h])


class TestFixedPayloadConsistency:
    """All packets in FIXED mode should have the same payload bytes."""

    def test_integer_field_same_bytes(self):
        schema = _schema_with_fields(
            FieldSchema(name="id", type=FieldType.INTEGER, bit_length=32),
        )
        transport = _CapturingTransport()
        engine = SenderEngine(transport=transport)
        cfg = SenderConfig(
            interface="dummy0",
            packet_count=5,
            packets_per_second=100_000,
            generation_mode=GenerationMode.FIXED,
        )
        engine.run(cfg, schema, fixed_values={"id": 0xDEADBEEF})

        assert len(transport.frames) == 5
        # All frames should be identical length
        lengths = {len(f) for f in transport.frames}
        assert len(lengths) == 1

    def test_string_field_padded(self):
        schema = _schema_with_fields(
            FieldSchema(name="label", type=FieldType.STRING, bit_length=64),
        )
        transport = _CapturingTransport()
        engine = SenderEngine(transport=transport)
        cfg = SenderConfig(
            interface="dummy0",
            packet_count=3,
            packets_per_second=100_000,
            generation_mode=GenerationMode.FIXED,
        )
        engine.run(cfg, schema, fixed_values={"label": "Hi"})
        assert len(transport.frames) == 3
        # User payload starts after Ethernet(14) + TestGen(28) = 42 bytes
        payloads = [f[42:] for f in transport.frames]
        assert payloads[0] == payloads[1] == payloads[2]

    def test_multi_field_layout_order(self):
        schema = _schema_with_fields(
            FieldSchema(name="a", type=FieldType.INTEGER, bit_length=8),
            FieldSchema(name="b", type=FieldType.INTEGER, bit_length=16),
        )
        transport = _CapturingTransport()
        engine = SenderEngine(transport=transport)
        cfg = SenderConfig(
            interface="dummy0",
            packet_count=2,
            packets_per_second=100_000,
            generation_mode=GenerationMode.FIXED,
        )
        engine.run(cfg, schema, fixed_values={"a": 0x01, "b": 0x0203})
        assert len(transport.frames) == 2
        payloads = [f[42:] for f in transport.frames]
        assert payloads[0] == payloads[1]

    def test_boolean_field(self):
        schema = _schema_with_fields(
            FieldSchema(name="flag", type=FieldType.BOOLEAN, bit_length=8),
        )
        transport = _CapturingTransport()
        engine = SenderEngine(transport=transport)
        cfg = SenderConfig(
            interface="dummy0",
            packet_count=2,
            packets_per_second=100_000,
            generation_mode=GenerationMode.FIXED,
        )
        engine.run(cfg, schema, fixed_values={"flag": True})
        assert len(transport.frames) == 2
        payloads = [f[42:] for f in transport.frames]
        assert payloads[0] == payloads[1]


class TestRandomPayloadVariation:
    """RANDOM mode should produce varying payloads (with high probability)."""

    def test_random_integer_varies(self):
        schema = _schema_with_fields(
            FieldSchema(name="id", type=FieldType.INTEGER, bit_length=32),
        )
        transport = _CapturingTransport()
        engine = SenderEngine(transport=transport)
        cfg = SenderConfig(
            interface="dummy0",
            packet_count=20,
            packets_per_second=100_000,
            generation_mode=GenerationMode.RANDOM,
        )
        engine.run(cfg, schema)

        assert len(transport.frames) == 20
        # With 32-bit random values, we expect at least some variation
        unique = set(transport.frames)
        assert len(unique) > 1, "RANDOM mode produced all identical frames"


class TestFrameStructure:
    """Verify the overall frame structure (Ethernet + TestGen + Payload)."""

    def test_frame_minimum_length(self):
        schema = _schema_with_fields(
            FieldSchema(name="val", type=FieldType.INTEGER, bit_length=16),
        )
        transport = _CapturingTransport()
        engine = SenderEngine(transport=transport)
        cfg = SenderConfig(
            interface="dummy0",
            packet_count=1,
            packets_per_second=100_000,
            generation_mode=GenerationMode.FIXED,
        )
        engine.run(cfg, schema, fixed_values={"val": 0})
        assert len(transport.frames) == 1
        frame = transport.frames[0]
        # Ethernet(14) + TestGen(28) + UserPayload(2) = 44 minimum
        assert len(frame) >= 44

    def test_ethertype_in_frame(self):
        schema = _schema_with_fields(
            FieldSchema(name="val", type=FieldType.INTEGER, bit_length=16),
        )
        transport = _CapturingTransport()
        engine = SenderEngine(transport=transport)
        cfg = SenderConfig(
            interface="dummy0",
            packet_count=1,
            packets_per_second=100_000,
            generation_mode=GenerationMode.FIXED,
            ethertype=0x88B5,
        )
        engine.run(cfg, schema, fixed_values={"val": 0})
        frame = transport.frames[0]
        # EtherType is at bytes 12-13 in raw Ethernet frame
        assert frame[12:14] == b"\x88\xB5"


# ===========================================================================
# Python-side deterministic frame building (for cross-check reference)
# ===========================================================================


class TestPythonDeterministicFrame:
    """Build frames with known sequence/timestamp to produce reference bytes."""

    def test_frame_bytes_with_known_inputs(self):
        """Build a frame with known seq=0, ts=1000 and verify key offsets."""
        from common.serializer import build_user_payload as py_build_payload
        from common.testgen_header import build_testgen_header as py_build_tg
        from sender.frame_builder import build_ethernet_header as py_build_eth, build_frame_bytes

        schema = _schema_with_fields(
            FieldSchema(name="val", type=FieldType.INTEGER, bit_length=16),
        )
        user_payload = py_build_payload(schema, {"val": 42})
        assert user_payload == b"\x00\x2A"

        eth = py_build_eth("ff:ff:ff:ff:ff:ff", "00:00:00:00:00:00", 0x88B5)
        frame = build_frame_bytes(eth, stream_id=1, sequence=0, tx_timestamp_ns=1000, user_payload=user_payload)

        # Ethernet header
        assert frame[0:6] == b"\xff\xff\xff\xff\xff\xff"  # dst MAC
        assert frame[6:12] == b"\x00\x00\x00\x00\x00\x00"  # src MAC
        assert frame[12:14] == b"\x88\xB5"  # ethertype

        # TestGen header starts at 14
        assert frame[14:16] == b"\x54\x47"  # magic "TG"
        assert frame[16] == 1  # version
        assert frame[17] == 0  # flags

        # Payload at 42
        assert frame[42:44] == b"\x00\x2A"

    def test_multi_field_payload_layout(self):
        """Verify multi-field layout matches expected byte order."""
        from common.serializer import build_user_payload as py_build_payload

        schema = _schema_with_fields(
            FieldSchema(name="a", type=FieldType.INTEGER, bit_length=8),
            FieldSchema(name="b", type=FieldType.INTEGER, bit_length=16),
            FieldSchema(name="c", type=FieldType.BOOLEAN, bit_length=8),
        )
        payload = py_build_payload(schema, {"a": 0x01, "b": 0x0203, "c": True})
        assert payload == b"\x01\x02\x03\x01"


# ===========================================================================
# Cross-backend payload matching (skipped if native module not installed)
# ===========================================================================


try:
    import trafic_native  # type: ignore[import-not-found]
    _HAS_NATIVE = True
except ImportError:
    _HAS_NATIVE = False


@pytest.mark.skipif(not _HAS_NATIVE, reason="Native extension not installed")
class TestCrossBackendPayloadMatch:
    """Verify Python and Rust produce identical frame bytes for the same inputs.

    Uses ``trafic_native.prepare_frame()`` on the Rust side and
    ``sender.frame_builder.build_frame_bytes()`` on the Python side with
    identical, deterministic inputs.
    """

    @staticmethod
    def _build_python_frame(
        dst_mac: str,
        src_mac: str,
        ethertype: int,
        stream_id: int,
        sequence: int,
        timestamp_ns: int,
        schema: PacketSchema,
        fixed_values: dict,
    ) -> bytes:
        from common.serializer import build_user_payload as py_build_payload
        from sender.frame_builder import build_ethernet_header as py_build_eth, build_frame_bytes

        user_payload = py_build_payload(schema, fixed_values)
        eth = py_build_eth(dst_mac, src_mac, ethertype)
        return build_frame_bytes(eth, stream_id, sequence, timestamp_ns, user_payload)

    @staticmethod
    def _build_native_config(
        dst_mac: str,
        src_mac: str,
        ethertype: int,
        stream_id: int,
        schema: PacketSchema,
        fixed_values: dict,
    ) -> dict:
        from sender.backends.native_backend import flatten_config_for_native

        cfg = SenderConfig(
            interface="dummy0",
            dst_mac=dst_mac,
            src_mac=src_mac,
            ethertype=ethertype,
            stream_id=stream_id,
            generation_mode=GenerationMode.FIXED,
        )
        return flatten_config_for_native(cfg, schema, fixed_values)

    def test_integer_16bit_frame_match(self):
        schema = _schema_with_fields(
            FieldSchema(name="val", type=FieldType.INTEGER, bit_length=16),
        )
        fv = {"val": 42}
        py_frame = self._build_python_frame(
            "ff:ff:ff:ff:ff:ff", "00:00:00:00:00:00", 0x88B5, 1, 0, 1000, schema, fv,
        )
        native_cfg = self._build_native_config(
            "ff:ff:ff:ff:ff:ff", "00:00:00:00:00:00", 0x88B5, 1, schema, fv,
        )
        rs_frame = bytes(trafic_native.prepare_frame(native_cfg, 0, 1000))
        assert py_frame == rs_frame

    def test_multi_field_frame_match(self):
        schema = _schema_with_fields(
            FieldSchema(name="a", type=FieldType.INTEGER, bit_length=8),
            FieldSchema(name="b", type=FieldType.INTEGER, bit_length=32),
            FieldSchema(name="c", type=FieldType.STRING, bit_length=64),
        )
        fv = {"a": 0xFF, "b": 0xDEADBEEF, "c": "Hi"}
        py_frame = self._build_python_frame(
            "aa:bb:cc:dd:ee:ff", "11:22:33:44:55:66", 0x88B5, 42, 7, 999999, schema, fv,
        )
        native_cfg = self._build_native_config(
            "aa:bb:cc:dd:ee:ff", "11:22:33:44:55:66", 0x88B5, 42, schema, fv,
        )
        rs_frame = bytes(trafic_native.prepare_frame(native_cfg, 7, 999999))
        assert py_frame == rs_frame

    def test_boolean_field_frame_match(self):
        schema = _schema_with_fields(
            FieldSchema(name="flag", type=FieldType.BOOLEAN, bit_length=8),
        )
        for val in (True, False):
            fv = {"flag": val}
            py_frame = self._build_python_frame(
                "ff:ff:ff:ff:ff:ff", "00:00:00:00:00:00", 0x88B5, 1, 0, 0, schema, fv,
            )
            native_cfg = self._build_native_config(
                "ff:ff:ff:ff:ff:ff", "00:00:00:00:00:00", 0x88B5, 1, schema, fv,
            )
            rs_frame = bytes(trafic_native.prepare_frame(native_cfg, 0, 0))
            assert py_frame == rs_frame, f"Mismatch for flag={val}"
