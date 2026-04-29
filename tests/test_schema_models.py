"""Tests for common.schema_models and common.enums."""

import pytest

from common.enums import FieldType
from common.schema_models import FieldSchema, HeaderSchema, PacketSchema


# ------------------------------------------------------------------ FieldType

class TestFieldType:
    def test_all_values(self) -> None:
        assert set(ft.value for ft in FieldType) == {
            "INTEGER", "STRING", "BOOLEAN", "RAW_BYTES",
        }

    def test_from_string_valid(self) -> None:
        assert FieldType.from_string("INTEGER") is FieldType.INTEGER
        assert FieldType.from_string("string") is FieldType.STRING
        assert FieldType.from_string("  BOOLEAN ") is FieldType.BOOLEAN
        assert FieldType.from_string("RAW_BYTES") is FieldType.RAW_BYTES

    def test_from_string_invalid(self) -> None:
        with pytest.raises(ValueError, match="Unsupported field type"):
            FieldType.from_string("FLOAT")

    def test_to_string(self) -> None:
        assert FieldType.INTEGER.to_string() == "INTEGER"
        assert FieldType.RAW_BYTES.to_string() == "RAW_BYTES"


# ------------------------------------------------------------------ FieldSchema

class TestFieldSchema:
    def test_basic_creation(self) -> None:
        f = FieldSchema(name="Counter", type=FieldType.INTEGER, bit_length=32)
        assert f.name == "Counter"
        assert f.type is FieldType.INTEGER
        assert f.bit_length == 32
        assert f.default_value is None

    def test_with_default_value(self) -> None:
        f = FieldSchema(
            name="Text", type=FieldType.STRING, bit_length=64, default_value="hello"
        )
        assert f.default_value == "hello"


# ------------------------------------------------------------------ HeaderSchema

class TestHeaderSchema:
    def test_empty_header(self) -> None:
        h = HeaderSchema(name="EmptyHeader")
        assert h.name == "EmptyHeader"
        assert h.fields == []
        assert h.subheaders == []

    def test_header_with_fields(self) -> None:
        f1 = FieldSchema(name="A", type=FieldType.INTEGER, bit_length=8)
        f2 = FieldSchema(name="B", type=FieldType.BOOLEAN, bit_length=8)
        h = HeaderSchema(name="H", fields=[f1, f2])
        assert len(h.fields) == 2
        assert h.fields[0].name == "A"

    def test_header_with_subheaders(self) -> None:
        child = HeaderSchema(name="Child")
        parent = HeaderSchema(name="Parent", subheaders=[child])
        assert len(parent.subheaders) == 1
        assert parent.subheaders[0].name == "Child"


# ------------------------------------------------------------------ PacketSchema

class TestPacketSchema:
    def test_empty_packet(self) -> None:
        p = PacketSchema(name="Pkt", declared_total_bit_length=64)
        assert p.name == "Pkt"
        assert p.declared_total_bit_length == 64
        assert p.headers == []

    def test_packet_with_headers(self) -> None:
        h = HeaderSchema(
            name="H1",
            fields=[FieldSchema(name="F", type=FieldType.INTEGER, bit_length=64)],
        )
        p = PacketSchema(name="Pkt", declared_total_bit_length=64, headers=[h])
        assert len(p.headers) == 1
        assert p.headers[0].fields[0].bit_length == 64
