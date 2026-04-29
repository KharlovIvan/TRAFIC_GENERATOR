"""Utility helpers for the traffic generator project."""

from __future__ import annotations

import copy
import xml.dom.minidom as minidom
from typing import Generator

from common.enums import FieldType
from common.schema_models import FieldSchema, HeaderSchema, PacketSchema


# ---------------------------------------------------------------------------
# FieldType helpers
# ---------------------------------------------------------------------------

def field_type_to_string(ft: FieldType) -> str:
    """Convert a FieldType enum to its XML string representation."""
    return ft.value


def field_type_from_string(value: str) -> FieldType:
    """Convert a string to a FieldType enum.

    Raises:
        ValueError: If the string is not a valid field type.
    """
    return FieldType.from_string(value)


# ---------------------------------------------------------------------------
# XML pretty-printing
# ---------------------------------------------------------------------------

def pretty_print_xml(xml_text: str, indent: str = "    ") -> str:
    """Return a pretty-printed version of *xml_text*.

    Uses xml.dom.minidom for reformatting.  Strips the redundant XML
    declaration that minidom adds and then prepends a clean one.
    """
    dom = minidom.parseString(xml_text)
    pretty = dom.toprettyxml(indent=indent, encoding=None)
    # minidom adds its own declaration; replace with a clean one.
    lines = pretty.splitlines()
    if lines and lines[0].startswith("<?xml"):
        lines = lines[1:]
    # Remove blank lines that minidom sometimes inserts
    cleaned = "\n".join(line for line in lines if line.strip())
    return f'<?xml version="1.0" encoding="UTF-8"?>\n{cleaned}\n'


# ---------------------------------------------------------------------------
# Recursive traversal helpers
# ---------------------------------------------------------------------------

def iter_fields_in_order(header: HeaderSchema) -> Generator[FieldSchema, None, None]:
    """Yield every field inside *header* (including nested sub-headers) in
    sequential layout order (depth-first, preserving original XML element order).
    
    Uses the children list to preserve XML order (Issue #3).
    """
    for child in header.children:
        if isinstance(child, FieldSchema):
            yield child
        elif isinstance(child, HeaderSchema):
            yield from iter_fields_in_order(child)


def iter_all_fields(packet: PacketSchema) -> Generator[FieldSchema, None, None]:
    """Yield every field in the packet in layout order."""
    for hdr in packet.headers:
        yield from iter_fields_in_order(hdr)


def iter_headers_recursive(header: HeaderSchema) -> Generator[HeaderSchema, None, None]:
    """Yield *header* itself and then recurse into sub-headers depth-first."""
    yield header
    for child in header.children:
        if isinstance(child, HeaderSchema):
            yield from iter_headers_recursive(child)


def iter_all_headers(packet: PacketSchema) -> Generator[HeaderSchema, None, None]:
    """Yield every header in the packet (including nested) depth-first."""
    for hdr in packet.headers:
        yield from iter_headers_recursive(hdr)


def compute_header_bit_length(header: HeaderSchema) -> int:
    """Return the total bit length of a header (fields + nested sub-headers)."""
    total = 0
    for child in header.children:
        if isinstance(child, FieldSchema):
            total += child.bit_length
        elif isinstance(child, HeaderSchema):
            total += compute_header_bit_length(child)
    return total


def compute_packet_bit_length(packet: PacketSchema) -> int:
    """Return the sum of all field bit lengths across the whole packet."""
    return sum(compute_header_bit_length(h) for h in packet.headers)


def flatten_fields_in_layout_order(packet: PacketSchema) -> list[FieldSchema]:
    """Return a flat list of all fields in the packet in layout order."""
    return list(iter_all_fields(packet))


# ---------------------------------------------------------------------------
# Deep copy helper
# ---------------------------------------------------------------------------

def deep_copy_schema(schema: PacketSchema) -> PacketSchema:
    """Return an independent deep copy of the schema."""
    return copy.deepcopy(schema)
