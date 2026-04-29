"""Tests for payload parsing (parse_user_payload) and round-trip."""

from __future__ import annotations

import pytest

from common.enums import FieldType
from common.exceptions import PacketParseError
from common.schema_models import FieldSchema, HeaderSchema, PacketSchema
from common.serializer import (
    build_user_payload,
    parse_field,
    parse_user_payload,
)


# ── helpers ──────────────────────────────────────────────────────────────

def _field(name: str, ftype: FieldType, bits: int) -> FieldSchema:
    return FieldSchema(name=name, type=ftype, bit_length=bits)


def _simple_schema(*fields: FieldSchema) -> PacketSchema:
    hdr = HeaderSchema(name="H1", fields=list(fields))
    total = sum(f.bit_length for f in fields)
    return PacketSchema(name="TestPkt", declared_total_bit_length=total, headers=[hdr])


# ── parse_field ──────────────────────────────────────────────────────────

class TestParseFieldInteger:
    def test_8bit(self):
        f = _field("x", FieldType.INTEGER, 8)
        assert parse_field(f, b"\x2a") == 42

    def test_16bit(self):
        f = _field("x", FieldType.INTEGER, 16)
        assert parse_field(f, b"\x12\x34") == 0x1234

    def test_32bit_zero(self):
        f = _field("x", FieldType.INTEGER, 32)
        assert parse_field(f, b"\x00\x00\x00\x00") == 0


class TestParseFieldString:
    def test_strips_trailing_zeros(self):
        f = _field("s", FieldType.STRING, 32)
        assert parse_field(f, b"ab\x00\x00") == "ab"

    def test_exact_length(self):
        f = _field("s", FieldType.STRING, 24)
        assert parse_field(f, b"abc") == "abc"

    def test_invalid_utf8_replaced(self):
        f = _field("s", FieldType.STRING, 8)
        result = parse_field(f, b"\xff")
        assert isinstance(result, str)


class TestParseFieldBoolean:
    def test_false(self):
        f = _field("b", FieldType.BOOLEAN, 8)
        assert parse_field(f, b"\x00") is False

    def test_true(self):
        f = _field("b", FieldType.BOOLEAN, 8)
        assert parse_field(f, b"\x01") is True

    def test_invalid_byte_raises(self):
        f = _field("b", FieldType.BOOLEAN, 8)
        with pytest.raises(PacketParseError, match="invalid BOOLEAN"):
            parse_field(f, b"\x02")


class TestParseFieldRawBytes:
    def test_hex_uppercase(self):
        f = _field("r", FieldType.RAW_BYTES, 16)
        result = parse_field(f, b"\xab\xcd")
        assert result == "ABCD"


class TestParseFieldErrors:
    def test_short_data_raises(self):
        f = _field("x", FieldType.INTEGER, 16)
        with pytest.raises(PacketParseError, match="need 2 bytes"):
            parse_field(f, b"\x01")


# ── parse_user_payload ───────────────────────────────────────────────────

class TestParseUserPayload:
    def test_simple_schema(self):
        schema = _simple_schema(
            _field("a", FieldType.INTEGER, 16),
            _field("b", FieldType.BOOLEAN, 8),
        )
        result = parse_user_payload(schema, b"\x00\x2a\x01")
        assert result == {"H1": {"a": 42, "b": True}}

    def test_length_mismatch_raises(self):
        schema = _simple_schema(_field("a", FieldType.INTEGER, 8))
        with pytest.raises(PacketParseError, match="length mismatch"):
            parse_user_payload(schema, b"\x01\x02")


class TestParseNestedHeaders:
    def test_nested_structure_preserved(self):
        inner = HeaderSchema(
            name="Inner",
            fields=[_field("x", FieldType.INTEGER, 8)],
        )
        outer = HeaderSchema(
            name="Outer",
            fields=[_field("y", FieldType.INTEGER, 8)],
            subheaders=[inner],
        )
        schema = PacketSchema(name="P", declared_total_bit_length=16, headers=[outer])
        result = parse_user_payload(schema, b"\x0a\x0b")
        assert result == {"Outer": {"y": 10, "Inner": {"x": 11}}}


# ── round-trip tests ─────────────────────────────────────────────────────

class TestRoundTrip:
    def test_integer_round_trip(self):
        schema = _simple_schema(_field("a", FieldType.INTEGER, 32))
        payload = build_user_payload(schema, {"a": 12345})
        parsed = parse_user_payload(schema, payload)
        assert parsed["H1"]["a"] == 12345  # type: ignore[index]

    def test_boolean_round_trip(self):
        schema = _simple_schema(_field("b", FieldType.BOOLEAN, 8))
        for val in (True, False):
            payload = build_user_payload(schema, {"b": val})
            parsed = parse_user_payload(schema, payload)
            assert parsed["H1"]["b"] is val  # type: ignore[index]

    def test_string_round_trip(self):
        schema = _simple_schema(_field("s", FieldType.STRING, 32))
        payload = build_user_payload(schema, {"s": "hi"})
        parsed = parse_user_payload(schema, payload)
        assert parsed["H1"]["s"] == "hi"  # type: ignore[index]

    def test_raw_bytes_round_trip(self):
        schema = _simple_schema(_field("r", FieldType.RAW_BYTES, 16))
        payload = build_user_payload(schema, {"r": b"\xab\xcd"})
        parsed = parse_user_payload(schema, payload)
        assert parsed["H1"]["r"] == "ABCD"  # type: ignore[index]

    def test_nested_round_trip(self):
        inner = HeaderSchema(
            name="Inner",
            fields=[_field("x", FieldType.INTEGER, 16)],
        )
        outer = HeaderSchema(
            name="Outer",
            fields=[_field("y", FieldType.STRING, 24)],
            subheaders=[inner],
        )
        schema = PacketSchema(name="P", declared_total_bit_length=40, headers=[outer])
        values = {"y": "AB", "x": 999}
        payload = build_user_payload(schema, values)
        parsed = parse_user_payload(schema, payload)
        assert parsed["Outer"]["y"] == "AB"  # type: ignore[index]
        assert parsed["Outer"]["Inner"]["x"] == 999  # type: ignore[index]

    def test_multi_field_round_trip(self):
        schema = _simple_schema(
            _field("a", FieldType.INTEGER, 16),
            _field("b", FieldType.BOOLEAN, 8),
            _field("c", FieldType.STRING, 24),
            _field("d", FieldType.RAW_BYTES, 16),
        )
        values = {"a": 0x0102, "b": True, "c": "xy", "d": b"\xfe\xed"}
        payload = build_user_payload(schema, values)
        parsed = parse_user_payload(schema, payload)
        h = parsed["H1"]
        assert h["a"] == 0x0102  # type: ignore[index]
        assert h["b"] is True  # type: ignore[index]
        assert h["c"] == "xy"  # type: ignore[index]
        assert h["d"] == "FEED"  # type: ignore[index]
