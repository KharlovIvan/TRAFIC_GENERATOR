"""QThread wrapper for receiver engine."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal

from common.metrics import ReceiverMetrics
from receiver.receiver_config import ReceiverConfig
from receiver.receiver_service import ReceiverService


class ReceiverWorker(QObject):
    """Runs :meth:`ReceiverService.start` in a background thread."""

    progress = Signal(object)   # ReceiverMetrics snapshot dict
    packet = Signal(object)     # parsed packet record dict
    finished = Signal()
    error = Signal(str)

    def __init__(self, service: ReceiverService, config: ReceiverConfig) -> None:
        super().__init__()
        self._service = service
        self._config = config

    def run(self) -> None:
        try:
            self._service.start(
                config=self._config,
                on_progress=self._on_progress,
                on_packet=self._on_packet,
            )
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.finished.emit()

    def _on_progress(self, metrics: ReceiverMetrics) -> None:
        self.progress.emit(metrics.snapshot())

    def _on_packet(self, record: dict) -> None:
        self.packet.emit(record)
