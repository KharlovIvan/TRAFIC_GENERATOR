"""Tests for common.serializer."""

from __future__ import annotations

import pytest

from common.enums import FieldType, GenerationMode
from common.exceptions import SerializationError
from common.schema_models import FieldSchema, HeaderSchema, PacketSchema
from common.serializer import (
    build_default_values_map,
    build_user_payload,
    generate_field_value,
    generate_packet_values,
    parse_default_value,
    serialize_field,
)


# ── helpers ──────────────────────────────────────────────────────────────

def _field(name: str, ftype: FieldType, bits: int, default: str | None = None) -> FieldSchema:
    return FieldSchema(name=name, type=ftype, bit_length=bits, default_value=default)


def _simple_schema(*fields: FieldSchema) -> PacketSchema:
    hdr = HeaderSchema(name="H1", fields=list(fields))
    total = sum(f.bit_length for f in fields)
    return PacketSchema(name="TestPkt", declared_total_bit_length=total, headers=[hdr])


# ── serialize_field ──────────────────────────────────────────────────────

class TestSerializeFieldInteger:
    def test_basic_8bit(self):
        f = _field("x", FieldType.INTEGER, 8)
        assert serialize_field(f, 42) == b"\x2a"

    def test_16bit(self):
        f = _field("x", FieldType.INTEGER, 16)
        assert serialize_field(f, 0x1234) == b"\x12\x34"

    def test_32bit_zero(self):
        f = _field("x", FieldType.INTEGER, 32)
        assert serialize_field(f, 0) == b"\x00\x00\x00\x00"

    def test_overflow_raises(self):
        f = _field("x", FieldType.INTEGER, 8)
        with pytest.raises(SerializationError, match="does not fit"):
            serialize_field(f, 256)

    def test_wrong_type_raises(self):
        f = _field("x", FieldType.INTEGER, 8)
        with pytest.raises(SerializationError, match="expected int"):
            serialize_field(f, "not an int")


class TestSerializeFieldString:
    def test_exact_length(self):
        f = _field("s", FieldType.STRING, 24)  # 3 bytes
        assert serialize_field(f, "abc") == b"abc"

    def test_short_padded(self):
        f = _field("s", FieldType.STRING, 32)  # 4 bytes
        assert serialize_field(f, "ab") == b"ab\x00\x00"

    def test_truncated(self):
        f = _field("s", FieldType.STRING, 16)  # 2 bytes
        assert serialize_field(f, "abcdef") == b"ab"

    def test_wrong_type_raises(self):
        f = _field("s", FieldType.STRING, 8)
        with pytest.raises(SerializationError, match="expected str"):
            serialize_field(f, 123)


class TestSerializeFieldBoolean:
    def test_true(self):
        f = _field("b", FieldType.BOOLEAN, 8)
        assert serialize_field(f, True) == b"\x01"

    def test_false(self):
        f = _field("b", FieldType.BOOLEAN, 8)
        assert serialize_field(f, False) == b"\x00"

    def test_truthy(self):
        f = _field("b", FieldType.BOOLEAN, 8)
        assert serialize_field(f, 1) == b"\x01"


class TestSerializeFieldRawBytes:
    def test_bytes_value(self):
        f = _field("r", FieldType.RAW_BYTES, 16)
        assert serialize_field(f, b"\xab\xcd") == b"\xab\xcd"

    def test_hex_string(self):
        f = _field("r", FieldType.RAW_BYTES, 16)
        assert serialize_field(f, "abcd") == b"\xab\xcd"

    def test_wrong_length_raises(self):
        f = _field("r", FieldType.RAW_BYTES, 16)
        with pytest.raises(SerializationError, match="expected 2 bytes"):
            serialize_field(f, b"\xab")


# ── build_user_payload ───────────────────────────────────────────────────

class TestBuildUserPayload:
    def test_multi_field(self):
        schema = _simple_schema(
            _field("a", FieldType.INTEGER, 16),
            _field("b", FieldType.BOOLEAN, 8),
            _field("c", FieldType.STRING, 24),
        )
        payload = build_user_payload(
            schema, {"a": 0x0102, "b": True, "c": "xy"}
        )
        assert payload == b"\x01\x02" + b"\x01" + b"xy\x00"

    def test_missing_field_raises(self):
        schema = _simple_schema(_field("a", FieldType.INTEGER, 8))
        with pytest.raises(SerializationError, match="Missing value"):
            build_user_payload(schema, {})


# ── parse_default_value ──────────────────────────────────────────────────

class TestParseDefaultValue:
    def test_integer_decimal(self):
        assert parse_default_value(_field("x", FieldType.INTEGER, 8, "42")) == 42

    def test_integer_hex(self):
        assert parse_default_value(_field("x", FieldType.INTEGER, 8, "0xFF")) == 255

    def test_integer_none(self):
        assert parse_default_value(_field("x", FieldType.INTEGER, 8, None)) == 0

    def test_string(self):
        assert parse_default_value(_field("x", FieldType.STRING, 24, "abc")) == "abc"

    def test_string_none(self):
        assert parse_default_value(_field("x", FieldType.STRING, 24, None)) == ""

    def test_boolean_true(self):
        assert parse_default_value(_field("x", FieldType.BOOLEAN, 8, "true")) is True

    def test_boolean_false(self):
        assert parse_default_value(_field("x", FieldType.BOOLEAN, 8, "false")) is False

    def test_boolean_none(self):
        assert parse_default_value(_field("x", FieldType.BOOLEAN, 8, None)) is False

    def test_raw_bytes_hex(self):
        assert parse_default_value(_field("x", FieldType.RAW_BYTES, 16, "AABB")) == b"\xaa\xbb"

    def test_raw_bytes_none(self):
        assert parse_default_value(_field("x", FieldType.RAW_BYTES, 16, None)) == b"\x00\x00"


# ── build_default_values_map ─────────────────────────────────────────────

class TestBuildDefaultValuesMap:
    def test_populated(self):
        schema = _simple_schema(
            _field("a", FieldType.INTEGER, 8, "10"),
            _field("b", FieldType.BOOLEAN, 8, "true"),
        )
        vals = build_default_values_map(schema)
        assert vals == {"a": 10, "b": True}


# ── generate_field_value ─────────────────────────────────────────────────

class TestGenerateFieldValue:
    def test_integer_range(self):
        f = _field("x", FieldType.INTEGER, 8)
        val = generate_field_value(f)
        assert 0 <= val <= 255

    def test_string_length(self):
        f = _field("x", FieldType.STRING, 24)
        val = generate_field_value(f)
        assert len(val) == 3

    def test_boolean_type(self):
        f = _field("x", FieldType.BOOLEAN, 8)
        val = generate_field_value(f)
        assert isinstance(val, bool)

    def test_raw_bytes_length(self):
        f = _field("x", FieldType.RAW_BYTES, 32)
        val = generate_field_value(f)
        assert isinstance(val, bytes) and len(val) == 4


# ── generate_packet_values ───────────────────────────────────────────────

class TestGeneratePacketValues:
    def test_fixed_uses_given_values(self):
        schema = _simple_schema(_field("a", FieldType.INTEGER, 8))
        vals = generate_packet_values(
            schema, GenerationMode.FIXED, {"a": 99}
        )
        assert vals["a"] == 99

    def test_fixed_defaults_when_none(self):
        schema = _simple_schema(_field("a", FieldType.INTEGER, 8, "5"))
        vals = generate_packet_values(schema, GenerationMode.FIXED)
        assert vals["a"] == 5

    def test_random_returns_all_fields(self):
        schema = _simple_schema(
            _field("a", FieldType.INTEGER, 16),
            _field("b", FieldType.BOOLEAN, 8),
        )
        vals = generate_packet_values(schema, GenerationMode.RANDOM)
        assert "a" in vals and "b" in vals
