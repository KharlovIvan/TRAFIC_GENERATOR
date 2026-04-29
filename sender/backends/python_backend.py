"""Python/Scapy sender backend – wraps the existing engine."""

from __future__ import annotations

import logging
from typing import Any, Callable

from common.metrics import SenderMetrics
from common.schema_models import PacketSchema
from sender.backends.base import SenderBackend
from sender.sender_config import SenderConfig
from sender.sender_engine import SenderEngine
from sender.transports.base import SenderTransport
from sender.transports.scapy_transport import ScapySenderTransport

log = logging.getLogger(__name__)


class PythonSenderBackend(SenderBackend):
    """Sender backend using the existing Python/Scapy infrastructure.

    Internally delegates to :class:`SenderEngine` with a
    :class:`SenderTransport` (defaults to Scapy).
    """

    def __init__(self, transport: SenderTransport | None = None) -> None:
        self._transport = transport
        self._engine: SenderEngine | None = None
        self._config: SenderConfig | None = None
        self._schema: PacketSchema | None = None
        self._fixed_values: dict[str, Any] | None = None

    def initialize(
        self,
        config: SenderConfig,
        schema: PacketSchema,
        fixed_values: dict[str, Any] | None = None,
    ) -> None:
        self._config = config
        self._schema = schema
        self._fixed_values = fixed_values
        transport = self._transport or ScapySenderTransport()
        self._engine = SenderEngine(transport=transport)
        log.info("Python (Scapy) sender initialized: interface=%s", config.interface)

    def start(
        self,
        on_progress: Callable[[SenderMetrics], None] | None = None,
        progress_interval: float = 0.25,
    ) -> SenderMetrics:
        if self._engine is None or self._config is None or self._schema is None:
            raise RuntimeError("Backend not initialized. Call initialize() first.")
        log.info("Python sender started.")
        metrics = self._engine.run(
            config=self._config,
            schema=self._schema,
            fixed_values=self._fixed_values,
            on_progress=on_progress,
            progress_interval=progress_interval,
        )
        log.info(
            "Python sender finished: attempted=%d, sent=%d, failed=%d, bytes=%d",
            metrics.packets_attempted,
            metrics.packets_sent,
            metrics.packets_failed,
            metrics.bytes_sent,
        )
        return metrics

    def stop(self) -> None:
        if self._engine is not None:
            self._engine.stop()

    def is_running(self) -> bool:
        return self._engine is not None and not self._engine.is_stopped

    def get_metrics(self) -> SenderMetrics:
        if self._engine is not None:
            return self._engine.metrics
        return SenderMetrics()

    @classmethod
    def validate_environment(cls) -> list[str]:
        errors: list[str] = []
        try:
            import scapy.all  # noqa: F401  # type: ignore[import-untyped]
        except ImportError:
            errors.append("Scapy is not installed (pip install scapy).")
        return errors

    @classmethod
    def get_backend_name(cls) -> str:
        return "Python (Scapy)"
