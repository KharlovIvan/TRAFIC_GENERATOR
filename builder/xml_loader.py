"""Load and optionally validate an XML schema file.

Reuses ``common.schema_parser`` for parsing and ``common.schema_validator``
for validation.  Loading is **tolerant**: only structural errors prevent
loading.  Semantic issues are returned as warnings.
"""

from __future__ import annotations

from common.exceptions import SchemaParseError, SchemaValidationError
from common.schema_models import PacketSchema
from common.schema_parser import load_schema_from_file
from common.schema_validator import (
    validate_schema_or_raise,
    validate_schema_semantics,
    validate_schema_structure,
)


def load_and_validate_schema(path: str) -> PacketSchema:
    """Load an XML schema from *path*, validate it, and return the model.

    Raises:
        SchemaParseError: If the file cannot be read or parsed.
        SchemaValidationError: If the parsed schema violates any rule
        (structural **or** semantic – kept for backward compatibility).
    """
    schema = load_schema_from_file(path)
    validate_schema_or_raise(schema)
    return schema


def load_schema_tolerant(path: str) -> tuple[PacketSchema, list[str]]:
    """Load a schema tolerantly.

    Structural errors still raise ``SchemaParseError`` or
    ``SchemaValidationError``.  Semantic issues are returned as a list of
    warning strings (possibly empty).
    """
    schema = load_schema_from_file(path)
    structural = validate_schema_structure(schema)
    if structural:
        raise SchemaValidationError(structural)
    warnings = validate_schema_semantics(schema)
    return schema, warnings
