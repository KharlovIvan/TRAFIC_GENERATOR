"""Non-GUI editing API for PacketSchema manipulation.

Every mutating operation validates the result before committing.  If
validation fails the original state is preserved and
``BuilderOperationError`` is raised.
"""

from __future__ import annotations

import copy
from typing import Union

from common.constants import BOOLEAN_BIT_LENGTH
from common.enums import FieldType
from common.exceptions import BuilderOperationError
from common.schema_models import FieldSchema, HeaderSchema, PacketSchema
from common.utils import iter_all_fields, iter_all_headers


# Type alias for a container that holds headers (packet or header)
HeaderParent = Union[PacketSchema, HeaderSchema]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _headers_list(parent: HeaderParent) -> list[HeaderSchema]:
    if isinstance(parent, PacketSchema):
        return parent.headers
    return parent.subheaders


def _find_header(parent: HeaderParent, name: str) -> HeaderSchema | None:
    for h in _headers_list(parent):
        if h.name == name:
            return h
    return None


def _find_field(header: HeaderSchema, name: str) -> FieldSchema | None:
    for f in header.fields:
        if f.name == name:
            return f
    return None


def _swap(lst: list, i: int, j: int) -> None:
    lst[i], lst[j] = lst[j], lst[i]


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_empty_packet(name: str, total_bit_length: int = 0) -> PacketSchema:
    """Create a new empty ``PacketSchema``.

    *total_bit_length* sets the declared value.  Pass 0 (default) to let
    the system compute it automatically from fields.
    """
    if not name or not name.strip():
        raise BuilderOperationError("Packet name must not be empty.")
    if total_bit_length < 0:
        raise BuilderOperationError("Packet totalBitLength must be >= 0.")
    return PacketSchema(name=name.strip(), declared_total_bit_length=total_bit_length, headers=[])


# ---------------------------------------------------------------------------
# Add operations
# ---------------------------------------------------------------------------

def add_header(parent: HeaderParent, name: str) -> HeaderSchema:
    """Add a new header to *parent* and return it.

    Raises ``BuilderOperationError`` on duplicate name or empty name.
    """
    if not name or not name.strip():
        raise BuilderOperationError("Header name must not be empty.")
    name = name.strip()
    existing = _headers_list(parent)
    if any(h.name == name for h in existing):
        raise BuilderOperationError(f"Duplicate header name '{name}'.")
    header = HeaderSchema(name=name)
    existing.append(header)
    return header


def add_field(
    header: HeaderSchema,
    name: str,
    field_type: FieldType,
    bit_length: int,
    default_value: str | None = None,
) -> FieldSchema:
    """Add a new field to *header* and return it.

    Raises ``BuilderOperationError`` on duplicate name, invalid bit_length, etc.
    """
    if not name or not name.strip():
        raise BuilderOperationError("Field name must not be empty.")
    name = name.strip()
    if any(f.name == name for f in header.fields):
        raise BuilderOperationError(
            f"Duplicate field name '{name}' in header '{header.name}'."
        )
    if bit_length <= 0:
        raise BuilderOperationError("Field bitLength must be > 0.")
    if bit_length % 8 != 0:
        raise BuilderOperationError(
            f"Field bitLength ({bit_length}) must be divisible by 8."
        )
    if not isinstance(field_type, FieldType):
        raise BuilderOperationError(f"Invalid field type: {field_type}")
    if field_type is FieldType.BOOLEAN and bit_length != BOOLEAN_BIT_LENGTH:
        raise BuilderOperationError(
            f"BOOLEAN field must have bitLength={BOOLEAN_BIT_LENGTH}."
        )

    field = FieldSchema(
        name=name, type=field_type, bit_length=bit_length, default_value=default_value
    )
    header.fields.append(field)
    return field


# ---------------------------------------------------------------------------
# Remove operations
# ---------------------------------------------------------------------------

def remove_header(parent: HeaderParent, header_name: str) -> None:
    """Remove a header by name from *parent*.

    Raises ``BuilderOperationError`` if not found.
    """
    headers = _headers_list(parent)
    for i, h in enumerate(headers):
        if h.name == header_name:
            headers.pop(i)
            return
    raise BuilderOperationError(f"Header '{header_name}' not found.")


def remove_field(header: HeaderSchema, field_name: str) -> None:
    """Remove a field by name from *header*.

    Raises ``BuilderOperationError`` if not found.
    """
    for i, f in enumerate(header.fields):
        if f.name == field_name:
            header.fields.pop(i)
            return
    raise BuilderOperationError(
        f"Field '{field_name}' not found in header '{header.name}'."
    )


# ---------------------------------------------------------------------------
# Update operations
# ---------------------------------------------------------------------------

def update_packet(
    packet: PacketSchema,
    *,
    name: str | None = None,
) -> None:
    """Update packet-level properties in place.

    ``declared_total_bit_length`` is auto-computed and cannot be set
    manually.
    """
    if name is not None:
        if not name.strip():
            raise BuilderOperationError("Packet name must not be empty.")
        packet.name = name.strip()


def update_header(
    parent: HeaderParent,
    header: HeaderSchema,
    *,
    name: str | None = None,
) -> None:
    """Update header properties in place.

    Checks for duplicate names among siblings.
    """
    if name is not None:
        if not name.strip():
            raise BuilderOperationError("Header name must not be empty.")
        new_name = name.strip()
        siblings = _headers_list(parent)
        for h in siblings:
            if h is not header and h.name == new_name:
                raise BuilderOperationError(f"Duplicate header name '{new_name}'.")
        header.name = new_name


def update_field(
    header: HeaderSchema,
    field: FieldSchema,
    *,
    name: str | None = None,
    field_type: FieldType | None = None,
    bit_length: int | None = None,
    default_value: str | None = ...,  # type: ignore[assignment]
) -> None:
    """Update field properties in place.

    Pass ``default_value=None`` to clear the default; omit it to leave unchanged.
    """
    if name is not None:
        if not name.strip():
            raise BuilderOperationError("Field name must not be empty.")
        new_name = name.strip()
        for f in header.fields:
            if f is not field and f.name == new_name:
                raise BuilderOperationError(
                    f"Duplicate field name '{new_name}' in header '{header.name}'."
                )
        field.name = new_name

    if field_type is not None:
        if not isinstance(field_type, FieldType):
            raise BuilderOperationError(f"Invalid field type: {field_type}")
        field.type = field_type

    if bit_length is not None:
        if bit_length <= 0:
            raise BuilderOperationError("Field bitLength must be > 0.")
        if bit_length % 8 != 0:
            raise BuilderOperationError(
                f"Field bitLength ({bit_length}) must be divisible by 8."
            )
        field.bit_length = bit_length

    # Enforce BOOLEAN constraint after both type and length may have changed
    effective_type = field_type if field_type is not None else field.type
    effective_length = bit_length if bit_length is not None else field.bit_length
    if effective_type is FieldType.BOOLEAN and effective_length != BOOLEAN_BIT_LENGTH:
        # Auto-correct the bit length
        field.bit_length = BOOLEAN_BIT_LENGTH

    if default_value is not ...:
        field.default_value = default_value


# ---------------------------------------------------------------------------
# Query operations
# ---------------------------------------------------------------------------

def get_all_fields(packet: PacketSchema) -> list[FieldSchema]:
    """Return a flat list of every field in layout order."""
    return list(iter_all_fields(packet))


def get_all_headers(packet: PacketSchema) -> list[HeaderSchema]:
    """Return a flat list of every header (including nested) depth-first."""
    return list(iter_all_headers(packet))


# ---------------------------------------------------------------------------
# Move operations (headers)
# ---------------------------------------------------------------------------

def move_header_up(parent: HeaderParent, header_name: str) -> None:
    """Move a top-level or sibling header one position earlier."""
    headers = _headers_list(parent)
    idx = _index_of_header(headers, header_name)
    if idx == 0:
        raise BuilderOperationError(f"Header '{header_name}' is already first.")
    _swap(headers, idx, idx - 1)


def move_header_down(parent: HeaderParent, header_name: str) -> None:
    """Move a top-level or sibling header one position later."""
    headers = _headers_list(parent)
    idx = _index_of_header(headers, header_name)
    if idx == len(headers) - 1:
        raise BuilderOperationError(f"Header '{header_name}' is already last.")
    _swap(headers, idx, idx + 1)


def move_subheader_up(parent_header: HeaderSchema, header_name: str) -> None:
    """Move a sub-header one position earlier inside its parent header."""
    move_header_up(parent_header, header_name)


def move_subheader_down(parent_header: HeaderSchema, header_name: str) -> None:
    """Move a sub-header one position later inside its parent header."""
    move_header_down(parent_header, header_name)


# ---------------------------------------------------------------------------
# Move operations (fields)
# ---------------------------------------------------------------------------

def move_field_up(header: HeaderSchema, field_name: str) -> None:
    """Move a field one position earlier within its header."""
    idx = _index_of_field(header, field_name)
    if idx == 0:
        raise BuilderOperationError(f"Field '{field_name}' is already first.")
    _swap(header.fields, idx, idx - 1)


def move_field_down(header: HeaderSchema, field_name: str) -> None:
    """Move a field one position later within its header."""
    idx = _index_of_field(header, field_name)
    if idx == len(header.fields) - 1:
        raise BuilderOperationError(f"Field '{field_name}' is already last.")
    _swap(header.fields, idx, idx + 1)


# ---------------------------------------------------------------------------
# Internal index helpers
# ---------------------------------------------------------------------------

def _index_of_header(headers: list[HeaderSchema], name: str) -> int:
    for i, h in enumerate(headers):
        if h.name == name:
            return i
    raise BuilderOperationError(f"Header '{name}' not found.")


def _index_of_field(header: HeaderSchema, name: str) -> int:
    for i, f in enumerate(header.fields):
        if f.name == name:
            return i
    raise BuilderOperationError(
        f"Field '{name}' not found in header '{header.name}'."
    )
