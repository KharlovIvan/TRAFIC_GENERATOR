"""Tests for builder.xml_loader."""

import pytest

from common.exceptions import SchemaParseError, SchemaValidationError
from builder.xml_loader import load_and_validate_schema, load_schema_tolerant


VALID_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<packet name="Test" totalBitLength="64">
    <header name="H1">
        <field name="A" type="INTEGER" bitLength="32"/>
        <field name="B" type="STRING" bitLength="32"/>
    </header>
</packet>
"""

INVALID_MISMATCH_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<packet name="Bad" totalBitLength="128">
    <header name="H1">
        <field name="A" type="INTEGER" bitLength="32"/>
    </header>
</packet>
"""


class TestLoadAndValidateSchema:
    def test_valid_file(self, tmp_path) -> None:
        path = tmp_path / "valid.xml"
        path.write_text(VALID_XML, encoding="utf-8")
        schema = load_and_validate_schema(str(path))
        assert schema.name == "Test"
        assert schema.declared_total_bit_length == 64

    def test_file_not_found(self) -> None:
        with pytest.raises(SchemaParseError, match="File not found"):
            load_and_validate_schema("/does/not/exist.xml")

    def test_validation_fails(self, tmp_path) -> None:
        path = tmp_path / "bad.xml"
        path.write_text(INVALID_MISMATCH_XML, encoding="utf-8")
        with pytest.raises(SchemaValidationError, match="does not match"):
            load_and_validate_schema(str(path))

    def test_malformed_xml(self, tmp_path) -> None:
        path = tmp_path / "broken.xml"
        path.write_text("<packet broken", encoding="utf-8")
        with pytest.raises(SchemaParseError):
            load_and_validate_schema(str(path))


class TestLoadSchemaTolerant:
    def test_valid_no_warnings(self, tmp_path) -> None:
        path = tmp_path / "valid.xml"
        path.write_text(VALID_XML, encoding="utf-8")
        schema, warnings = load_schema_tolerant(str(path))
        assert schema.name == "Test"
        assert warnings == []

    def test_semantic_mismatch_returns_warnings(self, tmp_path) -> None:
        path = tmp_path / "mismatch.xml"
        path.write_text(INVALID_MISMATCH_XML, encoding="utf-8")
        schema, warnings = load_schema_tolerant(str(path))
        assert schema.name == "Bad"
        assert any("does not match" in w for w in warnings)

    def test_structural_error_raises(self, tmp_path) -> None:
        # Empty packet name triggers a SchemaParseError at parse time
        xml = '<packet name="" totalBitLength="8"><header name="H"><field name="F" type="INTEGER" bitLength="8"/></header></packet>'
        path = tmp_path / "bad_struct.xml"
        path.write_text(xml, encoding="utf-8")
        with pytest.raises((SchemaValidationError, SchemaParseError)):
            load_schema_tolerant(str(path))

    def test_malformed_raises(self, tmp_path) -> None:
        path = tmp_path / "broken.xml"
        path.write_text("<packet broken", encoding="utf-8")
        with pytest.raises(SchemaParseError):
            load_schema_tolerant(str(path))
