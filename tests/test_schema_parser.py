"""Tests for common.schema_parser."""

import pytest

from common.enums import FieldType
from common.exceptions import SchemaParseError
from common.schema_parser import load_schema_from_file, load_schema_from_string


VALID_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<packet name="TestPacket" totalBitLength="128">
    <header name="H1">
        <field name="A" type="INTEGER" bitLength="32"/>
        <field name="B" type="STRING" bitLength="64"/>
    </header>
    <header name="H2">
        <field name="C" type="BOOLEAN" bitLength="8"/>
        <field name="D" type="RAW_BYTES" bitLength="24"/>
    </header>
</packet>
"""

NESTED_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<packet name="Nested" totalBitLength="64">
    <header name="Outer">
        <field name="X" type="INTEGER" bitLength="16"/>
        <header name="Inner">
            <field name="Y" type="INTEGER" bitLength="16"/>
        </header>
        <field name="Z" type="INTEGER" bitLength="32"/>
    </header>
</packet>
"""


class TestLoadSchemaFromString:
    def test_valid_simple(self) -> None:
        schema = load_schema_from_string(VALID_XML)
        assert schema.name == "TestPacket"
        assert schema.declared_total_bit_length == 128
        assert len(schema.headers) == 2
        assert schema.headers[0].name == "H1"
        assert len(schema.headers[0].fields) == 2
        assert schema.headers[0].fields[0].name == "A"
        assert schema.headers[0].fields[0].type is FieldType.INTEGER

    def test_nested_headers(self) -> None:
        schema = load_schema_from_string(NESTED_XML)
        outer = schema.headers[0]
        assert outer.name == "Outer"
        assert len(outer.fields) == 2  # X and Z (fields directly in Outer)
        assert len(outer.subheaders) == 1
        inner = outer.subheaders[0]
        assert inner.name == "Inner"
        assert inner.fields[0].name == "Y"

    def test_ordering_preserved(self) -> None:
        schema = load_schema_from_string(VALID_XML)
        field_names = [f.name for f in schema.headers[0].fields]
        assert field_names == ["A", "B"]
        header_names = [h.name for h in schema.headers]
        assert header_names == ["H1", "H2"]

    def test_malformed_xml(self) -> None:
        with pytest.raises(SchemaParseError, match="Malformed XML"):
            load_schema_from_string("<packet broken")

    def test_missing_packet_name(self) -> None:
        xml = '<packet totalBitLength="64"><header name="H"><field name="F" type="INTEGER" bitLength="64"/></header></packet>'
        with pytest.raises(SchemaParseError, match="missing required attribute 'name'"):
            load_schema_from_string(xml)

    def test_missing_total_bit_length(self) -> None:
        xml = '<packet name="P"><header name="H"><field name="F" type="INTEGER" bitLength="64"/></header></packet>'
        with pytest.raises(SchemaParseError, match="totalBitLength"):
            load_schema_from_string(xml)

    def test_missing_field_type(self) -> None:
        xml = '<packet name="P" totalBitLength="8"><header name="H"><field name="F" bitLength="8"/></header></packet>'
        with pytest.raises(SchemaParseError, match="missing required attribute 'type'"):
            load_schema_from_string(xml)

    def test_unsupported_field_type(self) -> None:
        xml = '<packet name="P" totalBitLength="8"><header name="H"><field name="F" type="FLOAT" bitLength="8"/></header></packet>'
        with pytest.raises(SchemaParseError, match="Unsupported field type"):
            load_schema_from_string(xml)

    def test_missing_field_bit_length(self) -> None:
        xml = '<packet name="P" totalBitLength="8"><header name="H"><field name="F" type="INTEGER"/></header></packet>'
        with pytest.raises(SchemaParseError, match="bitLength"):
            load_schema_from_string(xml)

    def test_non_integer_bit_length(self) -> None:
        xml = '<packet name="P" totalBitLength="abc"><header name="H"><field name="F" type="INTEGER" bitLength="8"/></header></packet>'
        with pytest.raises(SchemaParseError, match="must be an integer"):
            load_schema_from_string(xml)

    def test_wrong_root_tag(self) -> None:
        xml = '<config name="X" totalBitLength="8"/>'
        with pytest.raises(SchemaParseError, match="Root element must be <packet>"):
            load_schema_from_string(xml)

    def test_unexpected_child_in_packet(self) -> None:
        xml = '<packet name="P" totalBitLength="8"><unknown/></packet>'
        with pytest.raises(SchemaParseError, match="Unexpected element"):
            load_schema_from_string(xml)

    def test_unexpected_child_in_header(self) -> None:
        xml = '<packet name="P" totalBitLength="8"><header name="H"><data/></header></packet>'
        with pytest.raises(SchemaParseError, match="Unexpected element"):
            load_schema_from_string(xml)

    def test_default_value_preserved(self) -> None:
        xml = '<packet name="P" totalBitLength="8"><header name="H"><field name="F" type="INTEGER" bitLength="8" defaultValue="42"/></header></packet>'
        schema = load_schema_from_string(xml)
        assert schema.headers[0].fields[0].default_value == "42"

    def test_forbidden_attr_on_packet(self) -> None:
        xml = '<packet name="P" totalBitLength="8" startByte="0"><header name="H"><field name="F" type="INTEGER" bitLength="8"/></header></packet>'
        with pytest.raises(SchemaParseError, match="forbidden attribute"):
            load_schema_from_string(xml)

    def test_forbidden_attr_on_field(self) -> None:
        xml = '<packet name="P" totalBitLength="8"><header name="H"><field name="F" type="INTEGER" bitLength="8" offset="0"/></header></packet>'
        with pytest.raises(SchemaParseError, match="forbidden attribute"):
            load_schema_from_string(xml)

    def test_unknown_attr_on_packet(self) -> None:
        xml = '<packet name="P" totalBitLength="8" color="red"><header name="H"><field name="F" type="INTEGER" bitLength="8"/></header></packet>'
        with pytest.raises(SchemaParseError, match="unknown attribute"):
            load_schema_from_string(xml)

    def test_unknown_attr_on_header(self) -> None:
        xml = '<packet name="P" totalBitLength="8"><header name="H" color="red"><field name="F" type="INTEGER" bitLength="8"/></header></packet>'
        with pytest.raises(SchemaParseError, match="unknown attribute"):
            load_schema_from_string(xml)

    def test_unknown_attr_on_field(self) -> None:
        xml = '<packet name="P" totalBitLength="8"><header name="H"><field name="F" type="INTEGER" bitLength="8" extra="x"/></header></packet>'
        with pytest.raises(SchemaParseError, match="unknown attribute"):
            load_schema_from_string(xml)


class TestLoadSchemaFromFile:
    def test_file_not_found(self) -> None:
        with pytest.raises(SchemaParseError, match="File not found"):
            load_schema_from_file("/nonexistent/path.xml")

    def test_load_valid_file(self, tmp_path) -> None:
        xml_file = tmp_path / "test.xml"
        xml_file.write_text(VALID_XML, encoding="utf-8")
        schema = load_schema_from_file(str(xml_file))
        assert schema.name == "TestPacket"
        assert len(schema.headers) == 2
