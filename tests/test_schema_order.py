"""Schema child-order consistency tests across parser/generator/serializer."""

from __future__ import annotations

from builder.xml_generator import schema_to_xml_string
from common.enums import FieldType
from common.schema_models import FieldSchema, HeaderSchema, PacketSchema
from common.schema_parser import load_schema_from_string
from common.serializer import build_user_payload, parse_user_payload
from common.utils import flatten_fields_in_layout_order


MIXED_ORDER_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<packet name="P" totalBitLength="24">
  <header name="Outer">
    <field name="A" type="INTEGER" bitLength="8"/>
    <header name="Inner">
      <field name="X" type="INTEGER" bitLength="8"/>
    </header>
    <field name="B" type="INTEGER" bitLength="8"/>
  </header>
</packet>
"""


def test_mixed_order_parser_flatten_generator_serializer_and_deserializer_agree() -> None:
    schema = load_schema_from_string(MIXED_ORDER_XML)

    # XML parser + flatten order
    assert [f.name for f in flatten_fields_in_layout_order(schema)] == ["A", "X", "B"]

    # XML generator should preserve mixed children order
    out_xml = schema_to_xml_string(schema)
    assert out_xml.index('name="A"') < out_xml.index('name="Inner"')
    assert out_xml.index('name="Inner"') < out_xml.index('name="B"')

    # Build payload and parse back with nested output
    payload = build_user_payload(schema, {"A": 1, "X": 2, "B": 3})
    assert payload == bytes.fromhex("01 02 03")

    parsed = parse_user_payload(schema, payload)
    assert parsed == {
        "Outer": {
            "A": 1,
            "Inner": {"X": 2},
            "B": 3,
        }
    }


def test_deeper_nested_mixed_order_roundtrip() -> None:
    schema = PacketSchema(
        name="Deep",
        declared_total_bit_length=32,
        headers=[
            HeaderSchema(
                name="Outer",
                children=[
                    FieldSchema(name="A", type=FieldType.INTEGER, bit_length=8),
                    HeaderSchema(
                        name="Mid",
                        children=[
                            FieldSchema(name="M", type=FieldType.INTEGER, bit_length=8),
                            HeaderSchema(
                                name="Inner",
                                children=[
                                    FieldSchema(name="X", type=FieldType.INTEGER, bit_length=8)
                                ],
                            ),
                        ],
                    ),
                    FieldSchema(name="B", type=FieldType.INTEGER, bit_length=8),
                ],
            )
        ],
    )

    assert [f.name for f in flatten_fields_in_layout_order(schema)] == ["A", "M", "X", "B"]
    payload = build_user_payload(schema, {"A": 1, "M": 2, "X": 3, "B": 4})
    assert payload == bytes.fromhex("01 02 03 04")

    parsed = parse_user_payload(schema, payload)
    assert parsed == {
        "Outer": {
            "A": 1,
            "Mid": {
                "M": 2,
                "Inner": {"X": 3},
            },
            "B": 4,
        }
    }
