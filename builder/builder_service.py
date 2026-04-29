"""BuilderService – bridge between the GUI and the core schema logic.

Holds the current ``PacketSchema`` and exposes high-level operations that
the GUI calls.  All mutations go through ``model_editor``, parsing through
``schema_parser``, validation through ``schema_validator``, and XML
generation through ``xml_generator``.
"""

from __future__ import annotations

from typing import Union

from common.enums import FieldType
from common.exceptions import (
    BuilderOperationError,
    SchemaValidationError,
)
from common.schema_models import FieldSchema, HeaderSchema, PacketSchema
from common.schema_validator import validate_schema
from builder import model_editor
from builder.xml_generator import save_schema_to_file, schema_to_xml_string
from builder.xml_loader import load_and_validate_schema, load_schema_tolerant


HeaderParent = Union[PacketSchema, HeaderSchema]


class BuilderService:
    """Facade used by the GUI to manipulate and persist packet schemas."""

    def __init__(self) -> None:
        self._schema: PacketSchema | None = None
        self._file_path: str | None = None
        self._semantic_warnings: list[str] = []

    # -- properties --------------------------------------------------------

    @property
    def schema(self) -> PacketSchema | None:
        return self._schema

    @property
    def file_path(self) -> str | None:
        return self._file_path

    @property
    def has_schema(self) -> bool:
        return self._schema is not None

    @property
    def semantic_warnings(self) -> list[str]:
        return list(self._semantic_warnings)

    # -- lifecycle ---------------------------------------------------------

    def new_schema(self, name: str, total_bit_length: int = 0) -> PacketSchema:
        self._schema = model_editor.create_empty_packet(name, total_bit_length)
        self._file_path = None
        self._semantic_warnings = []
        return self._schema

    def load_schema(self, path: str) -> PacketSchema:
        """Load strictly (structural + semantic errors raise)."""
        self._schema = load_and_validate_schema(path)
        self._file_path = path
        self._semantic_warnings = []
        return self._schema

    def load_schema_tolerant(self, path: str) -> tuple[PacketSchema, list[str]]:
        """Load tolerantly: structural errors raise, semantic issues
        are returned as warnings."""
        schema, warnings = load_schema_tolerant(path)
        self._schema = schema
        self._file_path = path
        self._semantic_warnings = warnings
        return schema, warnings

    def save_schema(self, path: str | None = None) -> None:
        self._require_schema()
        target = path or self._file_path
        if target is None:
            raise BuilderOperationError("No file path specified for save.")
        save_schema_to_file(self._schema, target)  # type: ignore[arg-type]
        self._file_path = target

    # -- validation --------------------------------------------------------

    def validate_current_schema(self) -> list[str]:
        self._require_schema()
        return validate_schema(self._schema)  # type: ignore[arg-type]

    # -- preview -----------------------------------------------------------

    def get_xml_preview(self) -> str:
        self._require_schema()
        return schema_to_xml_string(self._schema)  # type: ignore[arg-type]

    # -- header operations -------------------------------------------------

    def add_header(self, parent: HeaderParent, name: str) -> HeaderSchema:
        self._require_schema()
        return model_editor.add_header(parent, name)

    def add_subheader(self, parent_header: HeaderSchema, name: str) -> HeaderSchema:
        self._require_schema()
        return model_editor.add_header(parent_header, name)

    def remove_header(self, parent: HeaderParent, header_name: str) -> None:
        self._require_schema()
        model_editor.remove_header(parent, header_name)

    def update_header(
        self, parent: HeaderParent, header: HeaderSchema, *, name: str | None = None
    ) -> None:
        self._require_schema()
        model_editor.update_header(parent, header, name=name)

    def move_header_up(self, parent: HeaderParent, header_name: str) -> None:
        self._require_schema()
        model_editor.move_header_up(parent, header_name)

    def move_header_down(self, parent: HeaderParent, header_name: str) -> None:
        self._require_schema()
        model_editor.move_header_down(parent, header_name)

    # -- field operations --------------------------------------------------

    def add_field(
        self,
        header: HeaderSchema,
        name: str,
        field_type: FieldType,
        bit_length: int,
        default_value: str | None = None,
    ) -> FieldSchema:
        self._require_schema()
        return model_editor.add_field(
            header, name, field_type, bit_length, default_value
        )

    def remove_field(self, header: HeaderSchema, field_name: str) -> None:
        self._require_schema()
        model_editor.remove_field(header, field_name)

    def update_field(
        self,
        header: HeaderSchema,
        field: FieldSchema,
        *,
        name: str | None = None,
        field_type: FieldType | None = None,
        bit_length: int | None = None,
        default_value: str | None = ...,  # type: ignore[assignment]
    ) -> None:
        self._require_schema()
        model_editor.update_field(
            header, field,
            name=name,
            field_type=field_type,
            bit_length=bit_length,
            default_value=default_value,
        )

    def move_field_up(self, header: HeaderSchema, field_name: str) -> None:
        self._require_schema()
        model_editor.move_field_up(header, field_name)

    def move_field_down(self, header: HeaderSchema, field_name: str) -> None:
        self._require_schema()
        model_editor.move_field_down(header, field_name)

    def swap_fields(self, header: HeaderSchema, first_name: str, second_name: str) -> None:
        self._require_schema()
        model_editor.swap_fields(header, first_name, second_name)

    def move_field_to_end(self, header: HeaderSchema, field_name: str) -> None:
        self._require_schema()
        model_editor.move_field_to_end(header, field_name)

    # -- packet-level updates ---------------------------------------------

    def update_packet(
        self,
        *,
        name: str | None = None,
    ) -> None:
        self._require_schema()
        model_editor.update_packet(
            self._schema, name=name  # type: ignore[arg-type]
        )

    # -- query helpers -----------------------------------------------------

    def get_all_fields(self) -> list[FieldSchema]:
        self._require_schema()
        return model_editor.get_all_fields(self._schema)  # type: ignore[arg-type]

    def get_all_headers(self) -> list[HeaderSchema]:
        self._require_schema()
        return model_editor.get_all_headers(self._schema)  # type: ignore[arg-type]

    # -- internal ----------------------------------------------------------

    def _require_schema(self) -> None:
        if self._schema is None:
            raise BuilderOperationError("No schema loaded. Create or open one first.")
