"""Dataclass models for the packet schema."""

from __future__ import annotations

from dataclasses import dataclass, field

from common.enums import FieldType


@dataclass
class FieldSchema:
    """Describes a single field within a header.

    Attributes:
        name: Unique name inside the parent header.
        type: One of the supported FieldType values.
        bit_length: Size in bits (must be > 0 and divisible by 8).
        default_value: Optional default value as a string.
    """

    name: str
    type: FieldType
    bit_length: int
    default_value: str | None = None


@dataclass
class HeaderSchema:
    """Describes a header (logical container) in the packet.

    A header contains an ordered list of fields and optionally an ordered
    list of nested sub-headers. Size is inferred from children.

    Attributes:
        name: Unique name inside the parent container.
        fields: Ordered list of fields within this header.
        subheaders: Ordered list of nested headers.
    """

    name: str
    fields: list[FieldSchema] = field(default_factory=list)
    subheaders: list[HeaderSchema] = field(default_factory=list)


@dataclass
class PacketSchema:
    """Top-level packet schema definition.

    Attributes:
        name: Human-readable packet name.
        declared_total_bit_length: The totalBitLength value as declared in XML
            (or set at creation time).  May differ from the actual computed sum.
        headers: Ordered list of top-level headers.
    """

    name: str
    declared_total_bit_length: int
    headers: list[HeaderSchema] = field(default_factory=list)
