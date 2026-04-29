"""Receiver main window – assembles all panels."""

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

from common.utils import compute_packet_bit_length, flatten_fields_in_layout_order
from receiver.receiver_config import ReceiverConfig
from receiver.receiver_service import ReceiverService
from receiver.receiver_worker import ReceiverWorker
from receiver.widgets.metrics_panel import MetricsPanel
from receiver.widgets.network_panel import NetworkPanel
from receiver.widgets.output_panel import OutputPanel
from receiver.widgets.packets_table_panel import PacketsTablePanel
from receiver.widgets.schema_panel import SchemaPanel
from receiver.widgets.session_panel import SessionPanel


class ReceiverWindow(QWidget):
    """Top-level receiver GUI."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Traffic Generator – Receiver")
        self.resize(1000, 750)

        self._service = ReceiverService()
        self._thread: QThread | None = None
        self._worker: ReceiverWorker | None = None

        self._build_ui()
        self._connect_signals()

    # -- UI ----------------------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout()

        # Top configuration area
        top = QVBoxLayout()
        self.schema_panel = SchemaPanel()
        top.addWidget(self.schema_panel)

        config_row = QHBoxLayout()
        self.network_panel = NetworkPanel()
        config_row.addWidget(self.network_panel)
        self.output_panel = OutputPanel()
        config_row.addWidget(self.output_panel)
        top.addLayout(config_row)

        top_widget = QWidget()
        top_widget.setLayout(top)

        # Middle: metrics + packets table
        mid = QHBoxLayout()
        self.metrics_panel = MetricsPanel()
        self.metrics_panel.setMaximumWidth(280)
        mid.addWidget(self.metrics_panel)
        self.packets_panel = PacketsTablePanel()
        mid.addWidget(self.packets_panel, 1)
        mid_widget = QWidget()
        mid_widget.setLayout(mid)

        # Bottom: session
        self.session_panel = SessionPanel()

        splitter = QSplitter()
        splitter.setOrientation(Qt.Orientation.Vertical)
        splitter.addWidget(top_widget)
        splitter.addWidget(mid_widget)
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
            schema = self._service.load_schema(path)
        except Exception as exc:
            QMessageBox.critical(self, "Schema Error", str(exc))
            return

        summary = self._service.schema_summary()
        self.schema_panel.set_info(
            f"Loaded: {summary.get('name')}  |  "
            f"{summary.get('field_count')} fields  |  "
            f"{summary.get('payload_bytes')} bytes"
        )
        warnings = self._service.validate_schema_for_receive()
        self.schema_panel.set_warnings(warnings)
        self.session_panel.log(f"Schema loaded: {path}")

    # -- Start / Stop ------------------------------------------------------

    def _on_start(self) -> None:
        if self._service.schema is None:
            QMessageBox.warning(self, "No Schema", "Load a schema first.")
            return

        warnings = self._service.validate_schema_for_receive()
        if warnings:
            QMessageBox.warning(
                self, "Schema Warnings",
                "Cannot start – schema has semantic errors:\n" +
                "\n".join(warnings),
            )
            return

        try:
            config = ReceiverConfig(
                interface_name=self.network_panel.interface_name(),
                ethertype=self.network_panel.ethertype(),
                schema_path=self.schema_panel.current_path(),
                export_format=self.output_panel.export_format(),
                pcap_output_path=self.output_panel.pcap_path(),
                json_output_path=self.output_panel.json_path(),
                duration_sec=self.output_panel.duration_sec(),
                packet_limit=self.output_panel.packet_limit(),
                promiscuous=self.network_panel.promiscuous(),
            )
            errors = config.validate()
            if errors:
                QMessageBox.warning(self, "Config Errors", "\n".join(errors))
                return
        except Exception as exc:
            QMessageBox.critical(self, "Config Error", str(exc))
            return

        self.metrics_panel.reset()
        self.packets_panel.clear()
        self.session_panel.set_running(True)
        self.session_panel.log("Capture started …")

        self._thread = QThread()
        self._worker = ReceiverWorker(self._service, config)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.packet.connect(self._on_packet)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.finished.connect(self._thread.quit)

        self._thread.start()

    def _on_stop(self) -> None:
        self._service.stop()
        self.session_panel.log("Stop requested …")

    def _on_progress(self, snap: dict[str, object]) -> None:
        self.metrics_panel.update_metrics(snap)

    def _on_packet(self, record: dict[str, object]) -> None:
        self.packets_panel.add_packet(record)

    def _on_finished(self) -> None:
        self.session_panel.set_running(False)
        self.session_panel.log("Capture finished.")

    def _on_error(self, msg: str) -> None:
        self.session_panel.set_running(False)
        self.session_panel.log(f"ERROR: {msg}")
        QMessageBox.critical(self, "Receiver Error", msg)

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self._service.stop()
        if self._thread and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(3000)
        super().closeEvent(event)


def run_receiver_gui() -> None:
    """Entry point: launch the Receiver GUI application."""
    app = QApplication.instance() or QApplication(sys.argv)
    window = ReceiverWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run_receiver_gui()
