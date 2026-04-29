"""Tests for builder.builder_service."""

import pytest

from common.enums import FieldType
from common.exceptions import BuilderOperationError, SchemaParseError, SchemaValidationError
from builder.builder_service import BuilderService
from builder.xml_generator import schema_to_xml_string


VALID_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<packet name="Svc" totalBitLength="64">
    <header name="H1">
        <field name="A" type="INTEGER" bitLength="32"/>
        <field name="B" type="STRING" bitLength="32"/>
    </header>
</packet>
"""


MISMATCH_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<packet name="Mismatch" totalBitLength="128">
    <header name="H1">
        <field name="A" type="INTEGER" bitLength="32"/>
    </header>
</packet>
"""


class TestNewSchema:
    def test_create(self) -> None:
        svc = BuilderService()
        schema = svc.new_schema("Pkt", 64)
        assert schema.name == "Pkt"
        assert svc.has_schema
        assert svc.file_path is None

    def test_create_default_total(self) -> None:
        svc = BuilderService()
        schema = svc.new_schema("Pkt")
        assert schema.declared_total_bit_length == 0

    def test_empty_name(self) -> None:
        svc = BuilderService()
        with pytest.raises(BuilderOperationError):
            svc.new_schema("", 64)


class TestLoadSchema:
    def test_load(self, tmp_path) -> None:
        path = tmp_path / "test.xml"
        path.write_text(VALID_XML, encoding="utf-8")
        svc = BuilderService()
        schema = svc.load_schema(str(path))
        assert schema.name == "Svc"
        assert svc.file_path == str(path)

    def test_load_nonexistent(self) -> None:
        svc = BuilderService()
        with pytest.raises(SchemaParseError):
            svc.load_schema("/no/such/file.xml")


class TestLoadSchemaTolerant:
    def test_tolerant_valid(self, tmp_path) -> None:
        path = tmp_path / "valid.xml"
        path.write_text(VALID_XML, encoding="utf-8")
        svc = BuilderService()
        schema, warnings = svc.load_schema_tolerant(str(path))
        assert schema.name == "Svc"
        assert warnings == []
        assert svc.semantic_warnings == []

    def test_tolerant_mismatch(self, tmp_path) -> None:
        path = tmp_path / "mismatch.xml"
        path.write_text(MISMATCH_XML, encoding="utf-8")
        svc = BuilderService()
        schema, warnings = svc.load_schema_tolerant(str(path))
        assert schema.name == "Mismatch"
        assert any("does not match" in w for w in warnings)
        assert svc.semantic_warnings == warnings


class TestSaveSchema:
    def test_save(self, tmp_path) -> None:
        svc = BuilderService()
        svc.new_schema("P", 64)
        path = str(tmp_path / "out.xml")
        svc.save_schema(path)
        assert svc.file_path == path

    def test_save_without_path(self) -> None:
        svc = BuilderService()
        svc.new_schema("P", 64)
        with pytest.raises(BuilderOperationError, match="No file path"):
            svc.save_schema()

    def test_save_no_schema(self) -> None:
        svc = BuilderService()
        with pytest.raises(BuilderOperationError, match="No schema loaded"):
            svc.save_schema("/tmp/x.xml")


class TestValidation:
    def test_valid(self) -> None:
        svc = BuilderService()
        svc.new_schema("P", 64)
        svc.add_header(svc.schema, "H")
        svc.add_field(svc.schema.headers[0], "F", FieldType.INTEGER, 64)
        errors = svc.validate_current_schema()
        assert errors == []

    def test_mismatch(self) -> None:
        svc = BuilderService()
        svc.new_schema("P", 128)
        svc.add_header(svc.schema, "H")
        svc.add_field(svc.schema.headers[0], "F", FieldType.INTEGER, 64)
        errors = svc.validate_current_schema()
        assert any("does not match" in e for e in errors)


class TestXmlPreview:
    def test_preview(self) -> None:
        svc = BuilderService()
        svc.new_schema("P", 64)
        svc.add_header(svc.schema, "H")
        svc.add_field(svc.schema.headers[0], "F", FieldType.INTEGER, 64)
        xml = svc.get_xml_preview()
        assert 'name="P"' in xml
        assert 'name="H"' in xml

    def test_preview_no_schema(self) -> None:
        svc = BuilderService()
        with pytest.raises(BuilderOperationError, match="No schema loaded"):
            svc.get_xml_preview()


class TestHeaderOperations:
    def test_add_and_remove(self) -> None:
        svc = BuilderService()
        svc.new_schema("P", 64)
        svc.add_header(svc.schema, "H1")
        svc.add_header(svc.schema, "H2")
        assert len(svc.schema.headers) == 2
        svc.remove_header(svc.schema, "H1")
        assert len(svc.schema.headers) == 1

    def test_add_subheader(self) -> None:
        svc = BuilderService()
        svc.new_schema("P", 64)
        svc.add_header(svc.schema, "Outer")
        svc.add_subheader(svc.schema.headers[0], "Inner")
        assert len(svc.schema.headers[0].subheaders) == 1

    def test_move_header(self) -> None:
        svc = BuilderService()
        svc.new_schema("P", 64)
        svc.add_header(svc.schema, "A")
        svc.add_header(svc.schema, "B")
        svc.move_header_down(svc.schema, "A")
        assert [h.name for h in svc.schema.headers] == ["B", "A"]
        svc.move_header_up(svc.schema, "A")
        assert [h.name for h in svc.schema.headers] == ["A", "B"]

    def test_update_header(self) -> None:
        svc = BuilderService()
        svc.new_schema("P", 64)
        svc.add_header(svc.schema, "Old")
        hdr = svc.schema.headers[0]
        svc.update_header(svc.schema, hdr, name="New")
        assert hdr.name == "New"


class TestFieldOperations:
    def test_add_and_remove(self) -> None:
        svc = BuilderService()
        svc.new_schema("P", 64)
        svc.add_header(svc.schema, "H")
        h = svc.schema.headers[0]
        svc.add_field(h, "F1", FieldType.INTEGER, 32)
        svc.add_field(h, "F2", FieldType.STRING, 32)
        assert len(h.fields) == 2
        svc.remove_field(h, "F1")
        assert len(h.fields) == 1

    def test_move_field(self) -> None:
        svc = BuilderService()
        svc.new_schema("P", 16)
        svc.add_header(svc.schema, "H")
        h = svc.schema.headers[0]
        svc.add_field(h, "A", FieldType.INTEGER, 8)
        svc.add_field(h, "B", FieldType.INTEGER, 8)
        svc.move_field_down(h, "A")
        assert [f.name for f in h.fields] == ["B", "A"]

    def test_update_field(self) -> None:
        svc = BuilderService()
        svc.new_schema("P", 64)
        svc.add_header(svc.schema, "H")
        h = svc.schema.headers[0]
        svc.add_field(h, "F", FieldType.INTEGER, 64)
        f = h.fields[0]
        svc.update_field(h, f, name="X", field_type=FieldType.BOOLEAN, bit_length=8)
        assert f.name == "X"
        assert f.type is FieldType.BOOLEAN


class TestReorderPropagation:
    def test_reorder_changes_xml(self) -> None:
        svc = BuilderService()
        svc.new_schema("P", 16)
        svc.add_header(svc.schema, "H")
        h = svc.schema.headers[0]
        svc.add_field(h, "A", FieldType.INTEGER, 8)
        svc.add_field(h, "B", FieldType.STRING, 8)
        xml_before = svc.get_xml_preview()
        svc.move_field_down(h, "A")
        xml_after = svc.get_xml_preview()
        assert xml_before != xml_after
        assert xml_after.index('name="B"') < xml_after.index('name="A"')
