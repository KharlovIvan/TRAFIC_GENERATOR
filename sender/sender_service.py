"""Bridge between GUI and sender backends."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from common.enums import BackendMode
from common.exceptions import SenderConfigError, SenderOperationError
from common.metrics import SenderMetrics
from common.schema_models import PacketSchema
from common.schema_parser import load_schema_from_file
from common.schema_validator import validate_schema_semantics, validate_schema_structure
from common.serializer import build_default_values_map
from sender.backends.base import SenderBackend
from sender.backends.native_backend import NativeSenderBackend
from sender.backends.python_backend import PythonSenderBackend
from sender.sender_config import SenderConfig
from sender.transports.base import SenderTransport

log = logging.getLogger(__name__)


def create_backend(
    mode: BackendMode,
    transport: SenderTransport | None = None,
) -> SenderBackend:
    """Instantiate the correct backend for the given *mode*."""
    if mode is BackendMode.NATIVE:
        return NativeSenderBackend()
    return PythonSenderBackend(transport=transport)


class SenderService:
    """High-level sender operations for the GUI layer.

    Backend selection is driven by :attr:`SenderConfig.backend_mode`.
    The service creates the appropriate :class:`SenderBackend` at
    :meth:`start_sending` time.
    """

    def __init__(self, transport: SenderTransport | None = None) -> None:
        self._schema: PacketSchema | None = None
        self._fixed_values: dict[str, Any] | None = None
        self._backend: SenderBackend | None = None
        self._transport = transport

    @property
    def schema(self) -> PacketSchema | None:
        return self._schema

    @property
    def fixed_values(self) -> dict[str, Any] | None:
        return self._fixed_values

    def load_schema(self, path: str | Path) -> tuple[PacketSchema, list[str]]:
        """Load and validate a schema file.

        Returns:
            (schema, warnings) where *warnings* are non-fatal semantic issues.

        Raises:
            SenderOperationError: If the schema has structural errors.
        """
        schema = load_schema_from_file(str(path))
        struct_errors = validate_schema_structure(schema)
        if struct_errors:
            raise SenderOperationError(
                "Schema structural errors:\n"
                + "\n".join(f"  - {e}" for e in struct_errors)
            )
        warnings = validate_schema_semantics(schema)
        self._schema = schema
        self._fixed_values = build_default_values_map(schema)
        return schema, warnings

    def update_fixed_value(self, field_name: str, value: Any) -> None:
        """Update a single fixed-mode field value."""
        if self._fixed_values is None:
            raise SenderOperationError("No schema loaded.")
        self._fixed_values[field_name] = value

    def start_sending(
        self,
        config: SenderConfig,
        on_progress: Callable[[SenderMetrics], None] | None = None,
        progress_interval: float = 0.25,
    ) -> SenderMetrics:
        """Start the sending loop.  Blocks until complete or stopped."""
        if self._schema is None:
            raise SenderOperationError("No schema loaded.")
        errors = config.validate()
        if errors:
            raise SenderConfigError("\n".join(errors))

        log.info(
            "Starting send: backend=%s, interface=%s",
            config.backend_mode.value,
            config.interface,
        )

        backend = create_backend(config.backend_mode, transport=self._transport)
        backend.initialize(config, self._schema, self._fixed_values)
        self._backend = backend
        return backend.start(
            on_progress=on_progress,
            progress_interval=progress_interval,
        )

    def stop_sending(self) -> None:
        """Request the active backend to stop."""
        if self._backend is not None:
            self._backend.stop()

    @property
    def is_running(self) -> bool:
        return self._backend is not None and self._backend.is_running()

    @property
    def latest_metrics(self) -> SenderMetrics | None:
        """Return the current backend metrics, or *None* if not running."""
        if self._backend is not None:
            return self._backend.get_metrics()
        return None
