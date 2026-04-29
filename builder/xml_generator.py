"""Generate XML text from a PacketSchema model.

The output preserves header nesting and element order exactly.  No explicit
offset attributes (startByte, bytePosition, etc.) are written.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from common.constants import (
    XML_ATTR_BIT_LENGTH,
    XML_ATTR_DEFAULT_VALUE,
    XML_ATTR_NAME,
    XML_ATTR_TOTAL_BIT_LENGTH,
    XML_ATTR_TYPE,
    XML_ENCODING,
    XML_TAG_FIELD,
    XML_TAG_HEADER,
    XML_TAG_PACKET,
)
from common.schema_models import FieldSchema, HeaderSchema, PacketSchema
from common.utils import compute_packet_bit_length, pretty_print_xml


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_field_element(field: FieldSchema) -> ET.Element:
    attribs: dict[str, str] = {
        XML_ATTR_NAME: field.name,
        XML_ATTR_TYPE: field.type.value,
        XML_ATTR_BIT_LENGTH: str(field.bit_length),
    }
    if field.default_value is not None:
        attribs[XML_ATTR_DEFAULT_VALUE] = field.default_value
    return ET.Element(XML_TAG_FIELD, attribs)


def _build_header_element(header: HeaderSchema) -> ET.Element:
    elem = ET.Element(XML_TAG_HEADER, {XML_ATTR_NAME: header.name})
    for field in header.fields:
        elem.append(_build_field_element(field))
    for sub in header.subheaders:
        elem.append(_build_header_element(sub))
    return elem


def _build_packet_element(schema: PacketSchema) -> ET.Element:
    computed_total = compute_packet_bit_length(schema)
    root = ET.Element(XML_TAG_PACKET, {
        XML_ATTR_NAME: schema.name,
        XML_ATTR_TOTAL_BIT_LENGTH: str(computed_total),
    })
    for header in schema.headers:
        root.append(_build_header_element(header))
    return root


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def schema_to_xml_string(schema: PacketSchema) -> str:
    """Convert a ``PacketSchema`` to a pretty-printed XML string.

    The output includes an XML declaration and uses 4-space indentation.
    """
    root = _build_packet_element(schema)
    raw_xml = ET.tostring(root, encoding="unicode")
    return pretty_print_xml(raw_xml)


def save_schema_to_file(schema: PacketSchema, path: str) -> None:
    """Write the schema as XML to *path*.

    Parent directories are created automatically.
    """
    xml_text = schema_to_xml_string(schema)
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(xml_text, encoding=XML_ENCODING.lower())
