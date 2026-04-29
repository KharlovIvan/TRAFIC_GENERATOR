"""Validate a PacketSchema against the MVP schema rules.

Validation is split into two tiers:

* **Structural** – names present, types valid, bit-lengths positive and
  8-aligned.  Structural errors mean the schema cannot be safely used.
* **Semantic** – declared vs computed totals, BOOLEAN field must be 8 bits,
  duplicate names.  Semantic issues are *warnings*; the schema can still be
  loaded and edited.

The legacy ``validate_schema`` / ``validate_schema_or_raise`` functions
combine both tiers for backward compatibility.
"""

from __future__ import annotations

from common.constants import BIT_ALIGNMENT, BOOLEAN_BIT_LENGTH
from common.enums import FieldType
from common.exceptions import SchemaValidationError
from common.schema_models import FieldSchema, HeaderSchema, PacketSchema
from common.utils import compute_header_bit_length, compute_packet_bit_length, flatten_fields_in_layout_order


# ---------------------------------------------------------------------------
# Public API – two-tier validation
# ---------------------------------------------------------------------------

def validate_schema_structure(schema: PacketSchema) -> list[str]:
    """Return **structural** errors (empty ⇒ structurally sound)."""
    errors: list[str] = []
    _structural_packet(schema, errors)
    return errors


def validate_schema_semantics(schema: PacketSchema) -> list[str]:
    """Return **semantic** warnings (empty ⇒ no warnings)."""
    warnings: list[str] = []
    _semantic_packet(schema, warnings)
    return warnings


def validate_schema(schema: PacketSchema) -> list[str]:
    """Return a combined list of structural errors + semantic warnings."""
    return validate_schema_structure(schema) + validate_schema_semantics(schema)


def validate_schema_or_raise(schema: PacketSchema) -> None:
    """Validate the schema and raise ``SchemaValidationError`` if invalid."""
    errors = validate_schema(schema)
    if errors:
        raise SchemaValidationError(errors)


# ---------------------------------------------------------------------------
# Helper: compute / flatten (re-exported for convenience)
# ---------------------------------------------------------------------------

compute_header_bit_length = compute_header_bit_length
compute_packet_bit_length = compute_packet_bit_length
flatten_fields_in_layout_order = flatten_fields_in_layout_order


# ---------------------------------------------------------------------------
# Structural checks (hard errors)
# ---------------------------------------------------------------------------

def _structural_packet(packet: PacketSchema, errors: list[str]) -> None:
    if not packet.name or not packet.name.strip():
        errors.append("Packet name must not be empty.")

    if packet.declared_total_bit_length <= 0:
        errors.append("Packet totalBitLength must be greater than 0.")
    elif packet.declared_total_bit_length % BIT_ALIGNMENT != 0:
        errors.append(
            f"Packet totalBitLength ({packet.declared_total_bit_length}) "
            f"must be divisible by {BIT_ALIGNMENT}."
        )

    for header in packet.headers:
        _structural_header(header, "packet", errors)


def _structural_header(header: HeaderSchema, parent_path: str, errors: list[str]) -> None:
    path = f"{parent_path} > header '{header.name}'"

    if not header.name or not header.name.strip():
        errors.append(f"Header name must not be empty (inside {parent_path}).")

    # Use children list to preserve XML order (Issue #3)
    for child in header.children:
        if isinstance(child, FieldSchema):
            _structural_field(child, path, errors)
        elif isinstance(child, HeaderSchema):
            _structural_header(child, path, errors)


def _structural_field(field: FieldSchema, parent_path: str, errors: list[str]) -> None:
    path = f"{parent_path} > field '{field.name}'"

    if not field.name or not field.name.strip():
        errors.append(f"Field name must not be empty (inside {parent_path}).")

    if not isinstance(field.type, FieldType):
        errors.append(f"{path}: field type must be a valid FieldType.")

    if field.bit_length <= 0:
        errors.append(f"{path}: bitLength must be greater than 0.")
    elif field.bit_length % BIT_ALIGNMENT != 0:
        errors.append(
            f"{path}: bitLength ({field.bit_length}) must be divisible by {BIT_ALIGNMENT}."
        )


# ---------------------------------------------------------------------------
# Semantic checks (warnings)
# ---------------------------------------------------------------------------

def _semantic_packet(packet: PacketSchema, warnings: list[str]) -> None:
    # Duplicate header names at top level
    _check_unique_header_names(packet.headers, "packet", warnings)

    # Check for duplicate field names globally (Issue #2)
    _check_unique_field_names_global(packet, warnings)

    for header in packet.headers:
        _semantic_header(header, "packet", warnings)

    # Declared vs computed total
    actual_bits = compute_packet_bit_length(packet)
    if packet.declared_total_bit_length > 0 and actual_bits != packet.declared_total_bit_length:
        warnings.append(
            f"Total field bit length ({actual_bits}) does not match "
            f"packet totalBitLength ({packet.declared_total_bit_length})."
        )


def _semantic_header(header: HeaderSchema, parent_path: str, warnings: list[str]) -> None:
    path = f"{parent_path} > header '{header.name}'"

    # Extract fields and subheaders from children
    fields = [c for c in header.children if isinstance(c, FieldSchema)]
    subheaders = [c for c in header.children if isinstance(c, HeaderSchema)]
    
    _check_unique_field_names(fields, path, warnings)
    _check_unique_header_names(subheaders, path, warnings)

    # Iterate through children in order (Issue #3)
    for child in header.children:
        if isinstance(child, FieldSchema):
            _semantic_field(child, path, warnings)
        elif isinstance(child, HeaderSchema):
            _semantic_header(child, path, warnings)


def _semantic_field(field: FieldSchema, parent_path: str, warnings: list[str]) -> None:
    path = f"{parent_path} > field '{field.name}'"

    if field.type is FieldType.BOOLEAN and field.bit_length != BOOLEAN_BIT_LENGTH:
        warnings.append(
            f"{path}: BOOLEAN field must have bitLength={BOOLEAN_BIT_LENGTH}, "
            f"got {field.bit_length}."
        )


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _check_unique_field_names(
    fields: list[FieldSchema], parent_path: str, errors: list[str]
) -> None:
    seen: set[str] = set()
    for f in fields:
        if f.name in seen:
            errors.append(
                f"Duplicate field name '{f.name}' inside {parent_path}."
            )
        seen.add(f.name)


def _check_unique_header_names(
    headers: list[HeaderSchema], parent_path: str, errors: list[str]
) -> None:
    seen: set[str] = set()
    for h in headers:
        if h.name in seen:
            errors.append(
                f"Duplicate header name '{h.name}' inside {parent_path}."
            )
        seen.add(h.name)


def _check_unique_field_names_global(packet: PacketSchema, warnings: list[str]) -> None:
    """Check that all field names are globally unique across the entire packet.
    
    Issue #2: Serialization uses a flat dict[field_name], so duplicate field names
    across different headers will cause values to collide.
    """
    seen: dict[str, str] = {}  # field_name -> path
    
    def _collect_fields(header: HeaderSchema, parent_path: str) -> None:
        path = f"{parent_path} > header '{header.name}'"
        for field in header.fields:
            if field.name in seen:
                warnings.append(
                    f"Field name '{field.name}' is not globally unique. "
                    f"Found at both {seen[field.name]} and {path}. "
                    f"This will cause serialization errors due to dict key collisions."
                )
            else:
                seen[field.name] = path
        for sub in header.subheaders:
            _collect_fields(sub, path)
    
    for header in packet.headers:
        _collect_fields(header, "packet")
