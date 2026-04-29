"""Dataclass models for the packet schema."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Union

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

    A header contains an ordered list of fields and optionally nested
    sub-headers, all stored in ``children`` to preserve original XML order.
    For backward compatibility, ``fields`` and ``subheaders`` provide
    read-only filtered views of ``children``.

    Attributes:
        name: Unique name inside the parent container.
        children: Ordered list of fields and sub-headers in XML order.
        fields: Read-only compatibility view. Mutating the returned list does
            not update ``children``.
        subheaders: Read-only compatibility view. Mutating the returned list
            does not update ``children``.
    """

    name: str
    children: list[Union[FieldSchema, HeaderSchema]] = field(default_factory=list)

    def __init__(
        self,
        name: str,
        children: list[Union[FieldSchema, HeaderSchema]] | None = None,
        fields: list[FieldSchema] | None = None,
        subheaders: list[HeaderSchema] | None = None,
    ):
        """Initialize HeaderSchema with support for both old and new APIs.
        
        The children parameter takes precedence. If fields/subheaders are provided
        without children, they are merged into children (fields first, then subheaders)
        to maintain backward compatibility with existing code.
        
        Args:
            name: Header name
            children: Ordered list of fields and headers (new API)
            fields: List of fields (old API, deprecated)
            subheaders: List of sub-headers (old API, deprecated)
        """
        self.name = name
        
        if children is not None:
            # New API: use children directly
            self.children = children
        elif fields is not None or subheaders is not None:
            # Old API: merge fields and subheaders into children for backward compat
            merged = []
            if fields:
                merged.extend(fields)
            if subheaders:
                merged.extend(subheaders)
            self.children = merged
        else:
            # No children, fields, or subheaders specified
            self.children = []

    @property
    def fields(self) -> list[FieldSchema]:
        """Return a read-only compatibility view of fields in ``children``.

        The returned list is a filtered copy. Mutating it does not change the
        schema. Use ``children`` (or builder model-editor helpers) for
        structural edits.
        """
        return [c for c in self.children if isinstance(c, FieldSchema)]

    @property
    def subheaders(self) -> list[HeaderSchema]:
        """Return a read-only compatibility view of subheaders in ``children``.

        The returned list is a filtered copy. Mutating it does not change the
        schema. Use ``children`` (or builder model-editor helpers) for
        structural edits.
        """
        return [c for c in self.children if isinstance(c, HeaderSchema)]


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
