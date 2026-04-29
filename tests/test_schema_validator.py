"""Tests for common.schema_validator."""

import pytest

from common.enums import FieldType
from common.exceptions import SchemaValidationError
from common.schema_models import FieldSchema, HeaderSchema, PacketSchema
from common.schema_validator import (
    compute_header_bit_length,
    compute_packet_bit_length,
    flatten_fields_in_layout_order,
    validate_schema,
    validate_schema_or_raise,
    validate_schema_semantics,
    validate_schema_structure,
)


def _make_field(name: str = "F", bit_length: int = 8, ft: FieldType = FieldType.INTEGER) -> FieldSchema:
    return FieldSchema(name=name, type=ft, bit_length=bit_length)


def _valid_schema() -> PacketSchema:
    """A minimal valid schema: 1 header, 1 field, 64 bits."""
    return PacketSchema(
        name="Valid",
        declared_total_bit_length=64,
        headers=[
            HeaderSchema(name="H1", fields=[_make_field("A", 64)]),
        ],
    )


# ------------------------------------------------------------------ structural

class TestValidateSchemaStructure:
    def test_valid(self) -> None:
        assert validate_schema_structure(_valid_schema()) == []

    def test_empty_packet_name(self) -> None:
        schema = _valid_schema()
        schema.name = ""
        errors = validate_schema_structure(schema)
        assert any("Packet name" in e for e in errors)

    def test_zero_total(self) -> None:
        schema = _valid_schema()
        schema.declared_total_bit_length = 0
        errors = validate_schema_structure(schema)
        assert any("greater than 0" in e for e in errors)

    def test_not_aligned(self) -> None:
        schema = _valid_schema()
        schema.declared_total_bit_length = 65
        errors = validate_schema_structure(schema)
        assert any("divisible by 8" in e for e in errors)

    def test_field_zero_length(self) -> None:
        schema = PacketSchema(
            name="P",
            declared_total_bit_length=8,
            headers=[HeaderSchema(name="H", fields=[_make_field("F", 0)])],
        )
        errors = validate_schema_structure(schema)
        assert any("greater than 0" in e for e in errors)

    def test_field_not_aligned(self) -> None:
        schema = PacketSchema(
            name="P",
            declared_total_bit_length=8,
            headers=[HeaderSchema(name="H", fields=[_make_field("F", 7)])],
        )
        errors = validate_schema_structure(schema)
        assert any("divisible by 8" in e for e in errors)

    def test_empty_header_name(self) -> None:
        schema = _valid_schema()
        schema.headers[0].name = ""
        errors = validate_schema_structure(schema)
        assert any("Header name" in e for e in errors)

    def test_empty_field_name(self) -> None:
        schema = _valid_schema()
        schema.headers[0].fields[0].name = ""
        errors = validate_schema_structure(schema)
        assert any("Field name" in e for e in errors)


# ------------------------------------------------------------------ semantic

class TestValidateSchemaSemantics:
    def test_valid(self) -> None:
        assert validate_schema_semantics(_valid_schema()) == []

    def test_total_mismatch(self) -> None:
        schema = PacketSchema(
            name="P",
            declared_total_bit_length=128,
            headers=[HeaderSchema(name="H", fields=[_make_field("F", 64)])],
        )
        warnings = validate_schema_semantics(schema)
        assert any("does not match" in w for w in warnings)

    def test_duplicate_field_names(self) -> None:
        schema = PacketSchema(
            name="P",
            declared_total_bit_length=16,
            headers=[
                HeaderSchema(name="H", fields=[_make_field("Dup", 8), _make_field("Dup", 8)]),
            ],
        )
        warnings = validate_schema_semantics(schema)
        assert any("Duplicate field name" in w for w in warnings)

    def test_duplicate_header_names(self) -> None:
        schema = PacketSchema(
            name="P",
            declared_total_bit_length=16,
            headers=[
                HeaderSchema(name="H", fields=[_make_field("A", 8)]),
                HeaderSchema(name="H", fields=[_make_field("B", 8)]),
            ],
        )
        warnings = validate_schema_semantics(schema)
        assert any("Duplicate header name" in w for w in warnings)

    def test_duplicate_subheader_names(self) -> None:
        outer = HeaderSchema(
            name="Outer",
            subheaders=[
                HeaderSchema(name="Sub", fields=[_make_field("A", 8)]),
                HeaderSchema(name="Sub", fields=[_make_field("B", 8)]),
            ],
        )
        schema = PacketSchema(name="P", declared_total_bit_length=16, headers=[outer])
        warnings = validate_schema_semantics(schema)
        assert any("Duplicate header name" in w for w in warnings)

    def test_boolean_must_be_8_bits(self) -> None:
        schema = PacketSchema(
            name="P",
            declared_total_bit_length=16,
            headers=[
                HeaderSchema(name="H", fields=[
                    _make_field("B", 16, FieldType.BOOLEAN),
                ]),
            ],
        )
        warnings = validate_schema_semantics(schema)
        assert any("BOOLEAN" in w and "8" in w for w in warnings)

    def test_boolean_8_bits_ok(self) -> None:
        schema = PacketSchema(
            name="P",
            declared_total_bit_length=8,
            headers=[
                HeaderSchema(name="H", fields=[
                    _make_field("B", 8, FieldType.BOOLEAN),
                ]),
            ],
        )
        assert validate_schema_semantics(schema) == []


# ------------------------------------------------------------------ combined

class TestValidateSchemaValid:
    def test_minimal_valid(self) -> None:
        errors = validate_schema(_valid_schema())
        assert errors == []

    def test_multiple_headers(self) -> None:
        schema = PacketSchema(
            name="Multi",
            declared_total_bit_length=128,
            headers=[
                HeaderSchema(name="H1", fields=[_make_field("A", 64)]),
                HeaderSchema(name="H2", fields=[_make_field("B", 64)]),
            ],
        )
        assert validate_schema(schema) == []

    def test_nested_headers(self) -> None:
        inner = HeaderSchema(name="Inner", fields=[_make_field("Y", 16)])
        outer = HeaderSchema(
            name="Outer",
            fields=[_make_field("X", 16)],
            subheaders=[inner],
        )
        schema = PacketSchema(name="N", declared_total_bit_length=32, headers=[outer])
        assert validate_schema(schema) == []

    def test_all_field_types(self) -> None:
        fields = [
            _make_field("A", 8, FieldType.INTEGER),
            _make_field("B", 8, FieldType.STRING),
            _make_field("C", 8, FieldType.BOOLEAN),
            _make_field("D", 8, FieldType.RAW_BYTES),
        ]
        schema = PacketSchema(
            name="Types",
            declared_total_bit_length=32,
            headers=[HeaderSchema(name="H", fields=fields)],
        )
        assert validate_schema(schema) == []


class TestValidateSchemaInvalid:
    def test_empty_packet_name(self) -> None:
        schema = _valid_schema()
        schema.name = ""
        errors = validate_schema(schema)
        assert any("Packet name" in e for e in errors)

    def test_zero_total_bit_length(self) -> None:
        schema = _valid_schema()
        schema.declared_total_bit_length = 0
        errors = validate_schema(schema)
        assert any("greater than 0" in e for e in errors)

    def test_total_bit_length_not_aligned(self) -> None:
        schema = _valid_schema()
        schema.declared_total_bit_length = 65
        errors = validate_schema(schema)
        assert any("divisible by 8" in e for e in errors)

    def test_empty_header_name(self) -> None:
        schema = _valid_schema()
        schema.headers[0].name = ""
        errors = validate_schema(schema)
        assert any("Header name" in e for e in errors)

    def test_empty_field_name(self) -> None:
        schema = _valid_schema()
        schema.headers[0].fields[0].name = ""
        errors = validate_schema(schema)
        assert any("Field name" in e for e in errors)

    def test_field_bit_length_zero(self) -> None:
        schema = PacketSchema(
            name="P",
            declared_total_bit_length=8,
            headers=[HeaderSchema(name="H", fields=[_make_field("F", 0)])],
        )
        errors = validate_schema(schema)
        assert any("greater than 0" in e for e in errors)

    def test_field_bit_length_not_aligned(self) -> None:
        schema = PacketSchema(
            name="P",
            declared_total_bit_length=8,
            headers=[HeaderSchema(name="H", fields=[_make_field("F", 7)])],
        )
        errors = validate_schema(schema)
        assert any("divisible by 8" in e for e in errors)

    def test_total_mismatch(self) -> None:
        schema = PacketSchema(
            name="P",
            declared_total_bit_length=128,
            headers=[HeaderSchema(name="H", fields=[_make_field("F", 64)])],
        )
        errors = validate_schema(schema)
        assert any("does not match" in e for e in errors)

    def test_duplicate_field_names(self) -> None:
        schema = PacketSchema(
            name="P",
            declared_total_bit_length=16,
            headers=[
                HeaderSchema(name="H", fields=[_make_field("Dup", 8), _make_field("Dup", 8)]),
            ],
        )
        errors = validate_schema(schema)
        assert any("Duplicate field name" in e for e in errors)

    def test_duplicate_header_names(self) -> None:
        schema = PacketSchema(
            name="P",
            declared_total_bit_length=16,
            headers=[
                HeaderSchema(name="H", fields=[_make_field("A", 8)]),
                HeaderSchema(name="H", fields=[_make_field("B", 8)]),
            ],
        )
        errors = validate_schema(schema)
        assert any("Duplicate header name" in e for e in errors)

    def test_duplicate_subheader_names(self) -> None:
        outer = HeaderSchema(
            name="Outer",
            subheaders=[
                HeaderSchema(name="Sub", fields=[_make_field("A", 8)]),
                HeaderSchema(name="Sub", fields=[_make_field("B", 8)]),
            ],
        )
        schema = PacketSchema(name="P", declared_total_bit_length=16, headers=[outer])
        errors = validate_schema(schema)
        assert any("Duplicate header name" in e for e in errors)

    def test_nested_validation(self) -> None:
        inner = HeaderSchema(name="", fields=[_make_field("Y", 8)])
        outer = HeaderSchema(name="Outer", fields=[], subheaders=[inner])
        schema = PacketSchema(name="P", declared_total_bit_length=8, headers=[outer])
        errors = validate_schema(schema)
        assert any("Header name" in e for e in errors)


class TestValidateSchemaOrRaise:
    def test_valid_does_not_raise(self) -> None:
        validate_schema_or_raise(_valid_schema())

    def test_invalid_raises(self) -> None:
        schema = _valid_schema()
        schema.name = ""
        with pytest.raises(SchemaValidationError) as exc_info:
            validate_schema_or_raise(schema)
        assert len(exc_info.value.errors) >= 1


class TestHelpers:
    def test_compute_header_bit_length(self) -> None:
        inner = HeaderSchema(name="I", fields=[_make_field("Y", 16)])
        outer = HeaderSchema(name="O", fields=[_make_field("X", 32)], subheaders=[inner])
        assert compute_header_bit_length(outer) == 48

    def test_compute_packet_bit_length(self) -> None:
        schema = PacketSchema(
            name="P",
            declared_total_bit_length=64,
            headers=[
                HeaderSchema(name="H1", fields=[_make_field("A", 32)]),
                HeaderSchema(name="H2", fields=[_make_field("B", 32)]),
            ],
        )
        assert compute_packet_bit_length(schema) == 64

    def test_flatten_fields_in_layout_order(self) -> None:
        inner = HeaderSchema(name="I", fields=[_make_field("Y", 16)])
        outer = HeaderSchema(
            name="O",
            fields=[_make_field("X", 16)],
            subheaders=[inner],
        )
        schema = PacketSchema(name="P", declared_total_bit_length=32, headers=[outer])
        flat = flatten_fields_in_layout_order(schema)
        assert [f.name for f in flat] == ["X", "Y"]
