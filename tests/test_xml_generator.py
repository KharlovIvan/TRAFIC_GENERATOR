"""Tests for builder.xml_generator."""

import pytest

from common.enums import FieldType
from common.schema_models import FieldSchema, HeaderSchema, PacketSchema
from common.schema_parser import load_schema_from_string
from builder.xml_generator import save_schema_to_file, schema_to_xml_string


def _sample_schema() -> PacketSchema:
    return PacketSchema(
        name="TestPkt",
        declared_total_bit_length=128,
        headers=[
            HeaderSchema(
                name="H1",
                fields=[
                    FieldSchema(name="A", type=FieldType.INTEGER, bit_length=32),
                    FieldSchema(name="B", type=FieldType.STRING, bit_length=64),
                ],
            ),
            HeaderSchema(
                name="H2",
                fields=[
                    FieldSchema(name="C", type=FieldType.BOOLEAN, bit_length=8),
                    FieldSchema(name="D", type=FieldType.RAW_BYTES, bit_length=24),
                ],
            ),
        ],
    )


def _nested_schema() -> PacketSchema:
    inner = HeaderSchema(
        name="Inner",
        fields=[FieldSchema(name="Y", type=FieldType.INTEGER, bit_length=16)],
    )
    outer = HeaderSchema(
        name="Outer",
        fields=[FieldSchema(name="X", type=FieldType.INTEGER, bit_length=16)],
        subheaders=[inner],
    )
    return PacketSchema(name="Nested", declared_total_bit_length=32, headers=[outer])


class TestSchemaToXmlString:
    def test_contains_packet_attrs(self) -> None:
        xml = schema_to_xml_string(_sample_schema())
        assert 'name="TestPkt"' in xml
        assert 'totalBitLength="128"' in xml

    def test_contains_field_attrs(self) -> None:
        xml = schema_to_xml_string(_sample_schema())
        assert 'name="A"' in xml
        assert 'type="INTEGER"' in xml
        assert 'bitLength="32"' in xml
        assert 'type="STRING"' in xml
        assert 'type="BOOLEAN"' in xml
        assert 'type="RAW_BYTES"' in xml

    def test_no_forbidden_attrs(self) -> None:
        xml = schema_to_xml_string(_sample_schema())
        assert "startByte" not in xml
        assert "bytePosition" not in xml
        assert "totalSize" not in xml

    def test_nested_headers_preserved(self) -> None:
        xml = schema_to_xml_string(_nested_schema())
        assert 'name="Outer"' in xml
        assert 'name="Inner"' in xml
        assert 'name="X"' in xml
        assert 'name="Y"' in xml

    def test_xml_declaration(self) -> None:
        xml = schema_to_xml_string(_sample_schema())
        assert xml.startswith('<?xml version="1.0" encoding="UTF-8"?>')

    def test_deterministic(self) -> None:
        a = schema_to_xml_string(_sample_schema())
        b = schema_to_xml_string(_sample_schema())
        assert a == b

    def test_ordering_preserved(self) -> None:
        xml = schema_to_xml_string(_sample_schema())
        assert xml.index('name="A"') < xml.index('name="B"')
        assert xml.index('name="H1"') < xml.index('name="H2"')

    def test_round_trip(self) -> None:
        original = _sample_schema()
        xml = schema_to_xml_string(original)
        parsed = load_schema_from_string(xml)
        assert parsed.name == original.name
        assert parsed.declared_total_bit_length == original.declared_total_bit_length
        assert len(parsed.headers) == len(original.headers)
        for orig_h, parsed_h in zip(original.headers, parsed.headers):
            assert orig_h.name == parsed_h.name
            assert len(orig_h.fields) == len(parsed_h.fields)
            for orig_f, parsed_f in zip(orig_h.fields, parsed_h.fields):
                assert orig_f.name == parsed_f.name
                assert orig_f.type == parsed_f.type
                assert orig_f.bit_length == parsed_f.bit_length

    def test_round_trip_nested(self) -> None:
        original = _nested_schema()
        xml = schema_to_xml_string(original)
        parsed = load_schema_from_string(xml)
        outer = parsed.headers[0]
        assert outer.name == "Outer"
        assert outer.fields[0].name == "X"
        assert len(outer.subheaders) == 1
        assert outer.subheaders[0].fields[0].name == "Y"

    def test_round_trip_ordering(self) -> None:
        """Ordering must survive a generate->parse round-trip."""
        original = _sample_schema()
        xml = schema_to_xml_string(original)
        parsed = load_schema_from_string(xml)
        orig_names = [f.name for h in original.headers for f in h.fields]
        parsed_names = [f.name for h in parsed.headers for f in h.fields]
        assert orig_names == parsed_names


class TestSaveSchemaToFile:
    def test_save_and_read_back(self, tmp_path) -> None:
        path = str(tmp_path / "output.xml")
        save_schema_to_file(_sample_schema(), path)
        with open(path, encoding="utf-8") as f:
            content = f.read()
        assert 'name="TestPkt"' in content
        assert 'totalBitLength="128"' in content

    def test_creates_parent_dirs(self, tmp_path) -> None:
        path = str(tmp_path / "sub" / "dir" / "out.xml")
        save_schema_to_file(_sample_schema(), path)
        parsed = load_schema_from_string(open(path, encoding="utf-8").read())
        assert parsed.name == "TestPkt"
