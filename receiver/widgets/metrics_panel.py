"""Metrics panel – live receiver counters."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QLabel,
    QWidget,
)


class MetricsPanel(QGroupBox):
    """Displays live receiver metrics."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Metrics", parent)
        self._build_ui()

    def _build_ui(self) -> None:
        form = QFormLayout()
        self.lbl_received = QLabel("0")
        self.lbl_ok = QLabel("0")
        self.lbl_invalid = QLabel("0")
        self.lbl_bytes = QLabel("0")
        self.lbl_elapsed = QLabel("0.0")
        self.lbl_pps = QLabel("0")
        self.lbl_gbps = QLabel("0.000000")
        self.lbl_streams = QLabel("0")

        form.addRow("Packets received:", self.lbl_received)
        form.addRow("Parsed OK:", self.lbl_ok)
        form.addRow("Invalid:", self.lbl_invalid)
        form.addRow("Bytes received:", self.lbl_bytes)
        form.addRow("Elapsed (s):", self.lbl_elapsed)
        form.addRow("PPS:", self.lbl_pps)
        form.addRow("Avg Gbps:", self.lbl_gbps)
        form.addRow("Unique streams:", self.lbl_streams)

        self.setLayout(form)

    def update_metrics(self, snap: dict[str, object]) -> None:
        self.lbl_received.setText(str(snap.get("packets_received", 0)))
        self.lbl_ok.setText(str(snap.get("packets_parsed_ok", 0)))
        self.lbl_invalid.setText(str(snap.get("packets_invalid", 0)))
        self.lbl_bytes.setText(str(snap.get("bytes_received", 0)))
        self.lbl_elapsed.setText(str(snap.get("elapsed_seconds", 0)))
        self.lbl_pps.setText(str(snap.get("pps", 0)))
        self.lbl_gbps.setText(str(snap.get("average_gbps", 0)))
        self.lbl_streams.setText(str(snap.get("unique_streams", 0)))

    def reset(self) -> None:
        for lbl in (self.lbl_received, self.lbl_ok, self.lbl_invalid,
                     self.lbl_bytes, self.lbl_streams):
            lbl.setText("0")
        self.lbl_elapsed.setText("0.0")
        self.lbl_pps.setText("0")
        self.lbl_gbps.setText("0.000000")
