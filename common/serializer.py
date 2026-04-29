"""Serializer: converts schema + field values to binary payload."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from common.constants import BOOLEAN_BIT_LENGTH
from common.enums import FieldType, GenerationMode
from common.exceptions import PacketParseError, SerializationError
from common.schema_models import FieldSchema, HeaderSchema, PacketSchema
from common.utils import (
    compute_packet_bit_length,
    flatten_fields_in_layout_order,
    iter_fields_in_order,
)


# ---------------------------------------------------------------------------
# Compiled schema — precomputed offsets for fast payload parsing
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CompiledField:
    """A field descriptor with its precomputed byte offset inside the payload.

    Build once via ``compile_schema``; reuse for every received packet so that
    parsing avoids repeated schema traversal and dict lookups.
    """

    name: str
    field_type: FieldType
    offset: int   # byte offset from payload start
    size: int     # byte width


def compile_schema(schema: PacketSchema) -> list[CompiledField]:
    """Compile *schema* into a flat list of ``CompiledField`` with byte offsets.

    The resulting list mirrors the layout order produced by
    ``flatten_fields_in_layout_order``.  Call this once per schema load and
    pass the result to ``parse_payload_compiled`` for each received frame.
    """
    result: list[CompiledField] = []
    offset = 0
    for f in flatten_fields_in_layout_order(schema):
        size = f.bit_length // 8
        result.append(CompiledField(name=f.name, field_type=f.type, offset=offset, size=size))
        offset += size
    return result


def _parse_compiled_field(cf: CompiledField, data: bytes) -> Any:
    """Parse a single ``CompiledField`` from *data* using its precomputed offset."""
    chunk = data[cf.offset:cf.offset + cf.size]

    if cf.field_type is FieldType.INTEGER:
        return int.from_bytes(chunk, "big", signed=False)

    if cf.field_type is FieldType.STRING:
        return chunk.decode("utf-8", errors="replace").rstrip("\x00")

    if cf.field_type is FieldType.BOOLEAN:
        if chunk == b"\x00":
            return False
        if chunk == b"\x01":
            return True
        raise PacketParseError(
            f"Field '{cf.name}': invalid BOOLEAN byte 0x{chunk[0]:02X}"
        )

    if cf.field_type is FieldType.RAW_BYTES:
        return chunk.hex().upper()

    raise PacketParseError(f"Unsupported field type: {cf.field_type}")


def parse_payload_compiled(compiled: list[CompiledField], raw: bytes) -> dict[str, Any]:
    """Parse *raw* payload bytes into a flat field-name dict using precomputed offsets.

    This is faster than ``parse_user_payload`` for repeated calls on the same
    schema because:
    * no schema object traversal per call
    * no repeated byte-offset arithmetic
    * no nested dict building (returns a flat map)

    For the receiver hot path prefer this over ``parse_user_payload``.
    """
    expected = compiled[-1].offset + compiled[-1].size if compiled else 0
    if len(raw) < expected:
        raise PacketParseError(
            f"Payload too short: expected {expected} bytes, got {len(raw)}"
        )
    return {cf.name: _parse_compiled_field(cf, raw) for cf in compiled}


# ---------------------------------------------------------------------------
# Single-field serialization
# ---------------------------------------------------------------------------

def serialize_field(field: FieldSchema, value: Any) -> bytes:
    """Serialize a single field value to bytes (big-endian)."""
    byte_len = field.bit_length // 8

    if field.type is FieldType.INTEGER:
        if not isinstance(value, int):
            raise SerializationError(
                f"Field '{field.name}': expected int, got {type(value).__name__}"
            )
        try:
            return value.to_bytes(byte_len, byteorder="big", signed=False)
        except OverflowError:
            raise SerializationError(
                f"Field '{field.name}': value {value} does not fit in {byte_len} bytes"
            ) from None

    if field.type is FieldType.STRING:
        if not isinstance(value, str):
            raise SerializationError(
                f"Field '{field.name}': expected str, got {type(value).__name__}"
            )
        encoded = value.encode("utf-8")
        if len(encoded) > byte_len:
            encoded = encoded[:byte_len]
        return encoded.ljust(byte_len, b"\x00")

    if field.type is FieldType.BOOLEAN:
        return b"\x01" if value else b"\x00"

    if field.type is FieldType.RAW_BYTES:
        if isinstance(value, (bytes, bytearray)):
            raw = bytes(value)
        elif isinstance(value, str):
            raw = bytes.fromhex(value.replace(" ", "").replace("0x", ""))
        else:
            raise SerializationError(
                f"Field '{field.name}': expected bytes or hex str, "
                f"got {type(value).__name__}"
            )
        if len(raw) != byte_len:
            raise SerializationError(
                f"Field '{field.name}': expected {byte_len} bytes, got {len(raw)}"
            )
        return raw

    raise SerializationError(f"Unsupported field type: {field.type}")


# ---------------------------------------------------------------------------
# Full payload assembly
# ---------------------------------------------------------------------------

def build_user_payload(schema: PacketSchema, values: dict[str, Any]) -> bytes:
    """Build the complete user payload from schema and field values."""
    fields = flatten_fields_in_layout_order(schema)
    parts: list[bytes] = []
    for f in fields:
        if f.name not in values:
            raise SerializationError(f"Missing value for field '{f.name}'")
        parts.append(serialize_field(f, values[f.name]))
    return b"".join(parts)


# ---------------------------------------------------------------------------
# Default value map
# ---------------------------------------------------------------------------

def build_default_values_map(schema: PacketSchema) -> dict[str, Any]:
    """Build a map of field names to default values based on schema defaults."""
    fields = flatten_fields_in_layout_order(schema)
    return {f.name: parse_default_value(f) for f in fields}


def parse_default_value(field: FieldSchema) -> Any:
    """Parse the *default_value* string for a field into its Python type."""
    raw = field.default_value
    byte_len = field.bit_length // 8

    if field.type is FieldType.INTEGER:
        if raw is None or raw.strip() == "":
            return 0
        text = raw.strip()
        if text.startswith(("0x", "0X")):
            return int(text, 16)
        return int(text)

    if field.type is FieldType.STRING:
        return raw or ""

    if field.type is FieldType.BOOLEAN:
        if raw is None:
            return False
        return raw.strip().lower() in ("true", "1", "yes")

    if field.type is FieldType.RAW_BYTES:
        if raw is None or raw.strip() == "":
            return b"\x00" * byte_len
        return bytes.fromhex(raw.strip().replace(" ", "").replace("0x", ""))

    return 0


# ---------------------------------------------------------------------------
# Random value generation
# ---------------------------------------------------------------------------

def generate_field_value(field: FieldSchema) -> Any:
    """Generate a random value for *field* based on its type."""
    byte_len = field.bit_length // 8

    if field.type is FieldType.INTEGER:
        return int.from_bytes(os.urandom(byte_len), "big")

    if field.type is FieldType.STRING:
        raw = os.urandom(byte_len)
        return "".join(chr(32 + (b % 95)) for b in raw)

    if field.type is FieldType.BOOLEAN:
        return bool(os.urandom(1)[0] & 1)

    if field.type is FieldType.RAW_BYTES:
        return os.urandom(byte_len)

    raise SerializationError(f"Unsupported field type: {field.type}")


# ---------------------------------------------------------------------------
# Packet-level value generation
# ---------------------------------------------------------------------------

def generate_packet_values(
    schema: PacketSchema,
    mode: GenerationMode,
    fixed_values: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate a complete values dict for all fields in *schema*."""
    fields = flatten_fields_in_layout_order(schema)

    if mode is GenerationMode.FIXED:
        if fixed_values is None:
            fixed_values = build_default_values_map(schema)
        for f in fields:
            if f.name not in fixed_values:
                raise SerializationError(
                    f"Missing fixed value for field '{f.name}'"
                )
        return dict(fixed_values)

    if mode is GenerationMode.RANDOM:
        return {f.name: generate_field_value(f) for f in fields}

    raise SerializationError(f"Unsupported generation mode: {mode}")


# ---------------------------------------------------------------------------
# Single-field parsing (binary -> Python)
# ---------------------------------------------------------------------------

def parse_field(field: FieldSchema, data: bytes) -> Any:
    """Parse a single field from raw bytes."""
    byte_len = field.bit_length // 8
    if len(data) < byte_len:
        raise PacketParseError(
            f"Field '{field.name}': need {byte_len} bytes, got {len(data)}"
        )
    chunk = data[:byte_len]

    if field.type is FieldType.INTEGER:
        return int.from_bytes(chunk, "big", signed=False)

    if field.type is FieldType.STRING:
        return chunk.decode("utf-8", errors="replace").rstrip("\x00")

    if field.type is FieldType.BOOLEAN:
        if chunk == b"\x00":
            return False
        if chunk == b"\x01":
            return True
        raise PacketParseError(
            f"Field '{field.name}': invalid BOOLEAN byte 0x{chunk[0]:02X}"
        )

    if field.type is FieldType.RAW_BYTES:
        return chunk.hex().upper()

    raise PacketParseError(f"Unsupported field type: {field.type}")


# ---------------------------------------------------------------------------
# Payload parsing (with nested header structure)
# ---------------------------------------------------------------------------

def _parse_header(header: HeaderSchema, data: bytes, offset: int) -> tuple[dict[str, object], int]:
    """Parse a single header and its children from *data* starting at *offset*.

    Preserves XML-defined children order (Issue #3).  Returns (parsed_dict, new_offset).
    """
    result: dict[str, object] = {}
    for child in header.children:
        if isinstance(child, FieldSchema):
            byte_len = child.bit_length // 8
            result[child.name] = parse_field(child, data[offset:])
            offset += byte_len
        elif isinstance(child, HeaderSchema):
            sub_dict, offset = _parse_header(child, data, offset)
            result[child.name] = sub_dict
    return result, offset


def parse_user_payload(schema: PacketSchema, raw_payload: bytes) -> dict[str, object]:
    """Parse *raw_payload* according to *schema* preserving header nesting.

    Raises:
        PacketParseError: If the payload length doesn't match or a field is
            invalid.
    """
    expected = compute_packet_bit_length(schema) // 8
    if len(raw_payload) != expected:
        raise PacketParseError(
            f"Payload length mismatch: expected {expected} bytes, got {len(raw_payload)}"
        )

    result: dict[str, object] = {}
    offset = 0
    for hdr in schema.headers:
        hdr_dict, offset = _parse_header(hdr, raw_payload, offset)
        result[hdr.name] = hdr_dict
    return result
