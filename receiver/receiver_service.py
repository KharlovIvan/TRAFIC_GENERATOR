"""Bridge between GUI/CLI and receiver engine."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from common.exceptions import ReceiverConfigError, ReceiverOperationError
from common.metrics import ReceiverMetrics
from common.schema_models import PacketSchema
from common.schema_parser import load_schema_from_file
from common.schema_validator import (
    validate_schema_semantics,
    validate_schema_structure,
    validate_unique_field_names_global,
)
from common.utils import compute_packet_bit_length, flatten_fields_in_layout_order
from receiver.receiver_config import ReceiverConfig
from receiver.receiver_engine import ReceiverEngine


class ReceiverService:
    """High-level receiver operations for the GUI/CLI layer."""

    def __init__(self) -> None:
        self._schema: PacketSchema | None = None
        self._semantic_warnings: list[str] = []
        self._semantic_errors: list[str] = []
        self._engine: ReceiverEngine | None = None

    @property
    def schema(self) -> PacketSchema | None:
        return self._schema

    def load_schema(self, path: str | Path) -> PacketSchema:
        """Load and structurally validate a schema file.

        Returns the loaded schema.  Call :meth:`validate_schema_for_receive`
        to check semantic errors before starting capture.

        Raises:
            ReceiverOperationError: If the schema has structural errors.
        """
        schema = load_schema_from_file(str(path))
        struct_errors = validate_schema_structure(schema)
        if struct_errors:
            raise ReceiverOperationError(
                "Schema structural errors:\n"
                + "\n".join(f"  - {e}" for e in struct_errors)
            )
        duplicate_name_errors = validate_unique_field_names_global(schema)
        if duplicate_name_errors:
            raise ReceiverOperationError(
                "Schema uses duplicate field names across headers, which is "
                "unsupported while values are keyed by field name:\n"
                + "\n".join(f"  - {e}" for e in duplicate_name_errors)
            )
        self._schema = schema
        self._semantic_warnings = validate_schema_semantics(schema)
        return schema

    def validate_schema_for_receive(self) -> list[str]:
        """Return semantic validation warnings.

        An empty list means the schema is fully valid for capture.
        """
        if self._schema is None:
            return ["No schema loaded."]
        return list(self._semantic_warnings)

    def schema_summary(self) -> dict[str, object]:
        """Return a UI-friendly schema summary dict."""
        if self._schema is None:
            return {}
        fields = flatten_fields_in_layout_order(self._schema)
        total_bits = compute_packet_bit_length(self._schema)
        return {
            "name": self._schema.name,
            "field_count": len(fields),
            "payload_bits": total_bits,
            "payload_bytes": total_bits // 8,
            "declared_total_bit_length": self._schema.declared_total_bit_length,
        }

    def start(
        self,
        config: ReceiverConfig,
        on_progress: Callable[[ReceiverMetrics], None] | None = None,
        on_packet: Callable[[dict[str, object]], None] | None = None,
    ) -> ReceiverMetrics:
        """Start the capture.  Blocks until stop or limit reached."""
        if self._schema is None:
            raise ReceiverOperationError("No schema loaded.")
        duplicate_name_errors = validate_unique_field_names_global(self._schema)
        if duplicate_name_errors:
            raise ReceiverOperationError(
                "Schema uses duplicate field names across headers, which is "
                "unsupported while values are keyed by field name:\n"
                + "\n".join(f"  - {e}" for e in duplicate_name_errors)
            )
        warnings = self.validate_schema_for_receive()
        if warnings:
            raise ReceiverOperationError(
                "Schema semantic errors block capture:\n"
                + "\n".join(f"  - {w}" for w in warnings)
            )
        errors = config.validate()
        if errors:
            raise ReceiverConfigError("\n".join(errors))

        self._engine = ReceiverEngine()
        return self._engine.run(
            config=config,
            schema=self._schema,
            on_progress=on_progress,
            on_packet=on_packet,
        )

    def stop(self) -> None:
        if self._engine:
            self._engine.stop()

    @property
    def is_running(self) -> bool:
        return self._engine is not None and not self._engine.is_stopped
