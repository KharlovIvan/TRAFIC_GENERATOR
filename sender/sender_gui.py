"""Sender main window – assembles all panels."""

from __future__ import annotations

import sys

from PySide6.QtCore import QThread, Qt
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QMessageBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from common.enums import BackendMode, GenerationMode
from sender.sender_config import SenderConfig
from sender.sender_service import SenderService
from sender.sender_worker import SenderWorker
from sender.widgets.backend_panel import BackendPanel
from sender.widgets.field_values_panel import FieldValuesPanel
from sender.widgets.generation_panel import GenerationPanel
from sender.widgets.network_panel import NetworkPanel
from sender.widgets.schema_panel import SchemaPanel
from sender.widgets.session_panel import SessionPanel


class SenderWindow(QWidget):
    """Top-level sender GUI."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Traffic Generator – Sender")
        self.resize(900, 700)

        self._service = SenderService()
        self._thread: QThread | None = None
        self._worker: SenderWorker | None = None

        self._build_ui()
        self._connect_signals()

    # -- UI ----------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout()

        # Top area: schema + network + generation + backend
        top = QVBoxLayout()
        self.schema_panel = SchemaPanel()
        top.addWidget(self.schema_panel)

        self.network_panel = NetworkPanel()
        top.addWidget(self.network_panel)

        self.generation_panel = GenerationPanel()
        top.addWidget(self.generation_panel)

        self.backend_panel = BackendPanel()
        top.addWidget(self.backend_panel)

        top_widget = QWidget()
        top_widget.setLayout(top)

        # Middle: field values
        self.field_values_panel = FieldValuesPanel()

        # Bottom: session
        self.session_panel = SessionPanel()

        splitter = QSplitter()
        splitter.setOrientation(Qt.Orientation.Vertical)
        splitter.addWidget(top_widget)
        splitter.addWidget(self.field_values_panel)
        splitter.addWidget(self.session_panel)

        root.addWidget(splitter)
        self.setLayout(root)

    def _connect_signals(self) -> None:
        self.schema_panel.btn_load.clicked.connect(self._on_load_schema)
        self.session_panel.btn_start.clicked.connect(self._on_start)
        self.session_panel.btn_stop.clicked.connect(self._on_stop)

    # -- Schema loading ----------------------------------------------------

    def _on_load_schema(self) -> None:
        path = self.schema_panel.current_path()
        if not path:
            return
        try:
            schema, warnings = self._service.load_schema(path)
        except Exception as exc:
            QMessageBox.critical(self, "Schema Error", str(exc))
            return

        from common.utils import flatten_fields_in_layout_order

        fields = flatten_fields_in_layout_order(schema)
        self.schema_panel.set_info(
            f"Loaded: {schema.name}  |  "
            f"{len(fields)} fields  |  "
            f"{schema.declared_total_bit_length} bits"
        )
        self.schema_panel.set_warnings(warnings)

        # Populate field values panel
        defaults = self._service.fixed_values or {}
        self.field_values_panel.load_schema(schema, defaults)

        self.session_panel.log(f"Schema loaded: {path}")

    # -- Start / Stop ------------------------------------------------------

    def _on_start(self) -> None:
        if self._service.schema is None:
            QMessageBox.warning(self, "No Schema", "Load a schema first.")
            return

        # Collect field values if FIXED mode
        mode = self.generation_panel.generation_mode()
        if mode is GenerationMode.FIXED:
            fv = self.field_values_panel.collect_values()
            for name, val in fv.items():
                self._service.update_fixed_value(name, val)

        try:
            config = SenderConfig(
                interface=self.network_panel.interface_name(),
                dst_mac=self.network_panel.dst_mac(),
                src_mac=self.network_panel.src_mac(),
                ethertype=self.network_panel.ethertype(),
                packets_per_second=self.generation_panel.packets_per_second(),
                packet_count=self.generation_panel.packet_count(),
                duration_seconds=self.generation_panel.duration_seconds(),
                stream_id=self.generation_panel.stream_id(),
                generation_mode=mode,
                backend_mode=self.backend_panel.backend_mode(),
            )
            errors = config.validate()
            if errors:
                QMessageBox.warning(
                    self, "Config Errors", "\n".join(errors)
                )
                return
        except Exception as exc:
            QMessageBox.critical(self, "Config Error", str(exc))
            return

        self.session_panel.reset_counters()
        self.session_panel.set_running(True)

        self._thread = QThread()
        self._worker = SenderWorker(self._service, config)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.started.connect(self._on_started)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.log_msg.connect(self._on_log)
        self._worker.finished.connect(self._thread.quit)

        self._thread.start()

    def _on_stop(self) -> None:
        self._service.stop_sending()
        self.session_panel.log("Stop requested.")

    def _on_started(self) -> None:
        pass

    def _on_progress(self, snap: dict[str, object]) -> None:
        self.session_panel.update_counters(snap)

    def _on_finished(self) -> None:
        self.session_panel.set_running(False)
        # Emit final counters
        metrics = self._service.latest_metrics
        if metrics is not None:
            self.session_panel.update_counters(metrics.snapshot())

    def _on_error(self, msg: str) -> None:
        self.session_panel.set_running(False)
        QMessageBox.critical(self, "Sender Error", msg)

    def _on_log(self, msg: str) -> None:
        self.session_panel.log(msg)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._service.stop_sending()
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(3000)
        super().closeEvent(event)


def run_sender_gui() -> None:
    """Entry point: launch the Sender GUI application."""
    app = QApplication.instance() or QApplication(sys.argv)
    window = SenderWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run_sender_gui()
