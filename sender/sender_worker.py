"""QThread wrapper for sender engine with throttled GUI updates."""

from __future__ import annotations

import logging

from PySide6.QtCore import QObject, QThread, Signal

from common.metrics import SenderMetrics
from sender.sender_config import SenderConfig
from sender.sender_service import SenderService

log = logging.getLogger(__name__)

# How often (seconds) the worker emits a progress signal to the GUI.
_GUI_PROGRESS_INTERVAL: float = 0.20


class SenderWorker(QObject):
    """Runs :meth:`SenderService.start_sending` in a background thread.

    Progress signals are throttled to *_GUI_PROGRESS_INTERVAL* so the GUI
    is never updated per-packet.
    """

    progress = Signal(object)  # SenderMetrics snapshot dict
    started = Signal()
    finished = Signal()
    error = Signal(str)
    log_msg = Signal(str)

    def __init__(self, service: SenderService, config: SenderConfig) -> None:
        super().__init__()
        self._service = service
        self._config = config

    def run(self) -> None:
        """Entry point – called from the worker thread."""
        try:
            self.started.emit()
            self.log_msg.emit(
                f"Sending started — backend={self._config.backend_mode.value}, "
                f"interface={self._config.interface}"
            )
            metrics = self._service.start_sending(
                config=self._config,
                on_progress=self._on_progress,
                progress_interval=_GUI_PROGRESS_INTERVAL,
            )
            summary = (
                f"Sending finished — "
                f"attempted={metrics.packets_attempted}, "
                f"sent={metrics.packets_sent}, "
                f"failed={metrics.packets_failed}, "
                f"bytes={metrics.bytes_sent}"
            )
            self.log_msg.emit(summary)
            log.info(summary)
        except Exception as exc:
            msg = str(exc)
            self.log_msg.emit(f"ERROR: {msg}")
            self.error.emit(msg)
            log.error("Sender error: %s", msg)
        finally:
            self.finished.emit()

    def _on_progress(self, metrics: SenderMetrics) -> None:
        self.progress.emit(metrics.snapshot())
