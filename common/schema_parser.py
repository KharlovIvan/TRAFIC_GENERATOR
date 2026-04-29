"""Parse XML into PacketSchema models.

Provides functions to load a schema from an XML file or an XML string,
producing a fully populated ``PacketSchema`` object.  The parser enforces
**structural** validity (well-formed XML, required tags/attributes, allowed
attribute sets, no deprecated attributes) but does **not** reject files with
semantic issues (e.g. totalBitLength mismatch, BOOLEAN size, duplicates).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from common.constants import (
    ALLOWED_FIELD_ATTRS,
    ALLOWED_HEADER_ATTRS,
    ALLOWED_HEADER_CHILDREN,
    ALLOWED_PACKET_ATTRS,
    ALLOWED_PACKET_CHILDREN,
    FORBIDDEN_ATTRS,
    XML_ATTR_BIT_LENGTH,
    XML_ATTR_DEFAULT_VALUE,
    XML_ATTR_NAME,
    XML_ATTR_TOTAL_BIT_LENGTH,
    XML_ATTR_TYPE,
    XML_TAG_FIELD,
    XML_TAG_HEADER,
    XML_TAG_PACKET,
)
from common.enums import FieldType
from common.exceptions import SchemaParseError
from common.schema_models import FieldSchema, HeaderSchema, PacketSchema


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _require_attr(element: ET.Element, attr: str) -> str:
    """Return the attribute value or raise ``SchemaParseError``."""
    value = element.get(attr)
    if value is None or value.strip() == "":
        tag = element.tag
        raise SchemaParseError(
            f"<{tag}> element is missing required attribute '{attr}'"
        )
    return value.strip()


def _parse_int_attr(element: ET.Element, attr: str) -> int:
    raw = _require_attr(element, attr)
    try:
        return int(raw)
    except ValueError:
        raise SchemaParseError(
            f"Attribute '{attr}' on <{element.tag}> must be an integer, got '{raw}'"
        ) from None


def _check_forbidden_attrs(element: ET.Element) -> None:
    """Raise if element has any deprecated / forbidden attributes."""
    for attr in element.attrib:
        if attr in FORBIDDEN_ATTRS:
            raise SchemaParseError(
                f"<{element.tag}> contains forbidden attribute '{attr}'"
            )


def _check_unknown_attrs(element: ET.Element, allowed: set[str]) -> None:
    """Raise if element has attributes not in the allowed set."""
    for attr in element.attrib:
        if attr not in allowed:
            raise SchemaParseError(
                f"<{element.tag}> contains unknown attribute '{attr}'"
            )


def _parse_field(element: ET.Element) -> FieldSchema:
    _check_forbidden_attrs(element)
    _check_unknown_attrs(element, ALLOWED_FIELD_ATTRS)

    name = _require_attr(element, XML_ATTR_NAME)
    type_str = _require_attr(element, XML_ATTR_TYPE)
    bit_length = _parse_int_attr(element, XML_ATTR_BIT_LENGTH)

    try:
        field_type = FieldType.from_string(type_str)
    except ValueError as exc:
        raise SchemaParseError(str(exc)) from None

    default_value = element.get(XML_ATTR_DEFAULT_VALUE)
    if default_value is not None:
        default_value = default_value.strip() or None

    return FieldSchema(
        name=name,
        type=field_type,
        bit_length=bit_length,
        default_value=default_value,
    )


def _parse_header(element: ET.Element) -> HeaderSchema:
    _check_forbidden_attrs(element)
    _check_unknown_attrs(element, ALLOWED_HEADER_ATTRS)

    name = _require_attr(element, XML_ATTR_NAME)
    children: list = []

    # Preserve XML order by processing children sequentially
    for child in element:
        if child.tag not in ALLOWED_HEADER_CHILDREN:
            raise SchemaParseError(
                f"Unexpected element <{child.tag}> inside <header name='{name}'>"
            )
        if child.tag == XML_TAG_FIELD:
            children.append(_parse_field(child))
        elif child.tag == XML_TAG_HEADER:
            children.append(_parse_header(child))

    return HeaderSchema(name=name, children=children)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_schema_from_string(xml_text: str) -> PacketSchema:
    """Parse an XML string and return a ``PacketSchema``.

    Only **structural** violations cause a ``SchemaParseError``.  Semantic
    issues (size mismatch, BOOLEAN bitLength, duplicates) are left for the
    validator layer.
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise SchemaParseError(f"Malformed XML: {exc}") from exc

    if root.tag != XML_TAG_PACKET:
        raise SchemaParseError(
            f"Root element must be <{XML_TAG_PACKET}>, got <{root.tag}>"
        )

    _check_forbidden_attrs(root)
    _check_unknown_attrs(root, ALLOWED_PACKET_ATTRS)

    packet_name = _require_attr(root, XML_ATTR_NAME)
    declared_total = _parse_int_attr(root, XML_ATTR_TOTAL_BIT_LENGTH)

    headers: list[HeaderSchema] = []
    for child in root:
        if child.tag not in ALLOWED_PACKET_CHILDREN:
            raise SchemaParseError(
                f"Unexpected element <{child.tag}> inside <packet>"
            )
        headers.append(_parse_header(child))

    return PacketSchema(
        name=packet_name,
        declared_total_bit_length=declared_total,
        headers=headers,
    )


def load_schema_from_file(path: str) -> PacketSchema:
    """Load an XML file and return a ``PacketSchema``.

    Raises:
        SchemaParseError: On I/O errors, malformed XML, or missing attributes.
    """
    file_path = Path(path)
    if not file_path.is_file():
        raise SchemaParseError(f"File not found: {path}")
    try:
        xml_text = file_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise SchemaParseError(f"Cannot read file '{path}': {exc}") from exc

    return load_schema_from_string(xml_text)
