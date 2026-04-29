"""Output configuration panel – export format, file paths, limits."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from common.enums import ExportFormat


class OutputPanel(QGroupBox):
    """Export format, output paths, duration, packet limit."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Output", parent)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout()

        # Format
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Format:"))
        self.combo_format = QComboBox()
        for fmt in ExportFormat:
            self.combo_format.addItem(fmt.value)
        self.combo_format.setCurrentText(ExportFormat.PCAP_AND_JSON.value)
        row1.addWidget(self.combo_format)
        row1.addStretch()
        layout.addLayout(row1)

        # PCAP path
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("PCAP path:"))
        self.edit_pcap = QLineEdit()
        self.edit_pcap.setPlaceholderText("captures/session.pcap")
        row2.addWidget(self.edit_pcap, 1)
        self.btn_pcap_browse = QPushButton("…")
        self.btn_pcap_browse.setMaximumWidth(30)
        self.btn_pcap_browse.clicked.connect(self._browse_pcap)
        row2.addWidget(self.btn_pcap_browse)
        layout.addLayout(row2)

        # JSON path
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("JSON path:"))
        self.edit_json = QLineEdit()
        self.edit_json.setPlaceholderText("captures/session.jsonl")
        row3.addWidget(self.edit_json, 1)
        self.btn_json_browse = QPushButton("…")
        self.btn_json_browse.setMaximumWidth(30)
        self.btn_json_browse.clicked.connect(self._browse_json)
        row3.addWidget(self.btn_json_browse)
        layout.addLayout(row3)

        # Duration + Packet limit
        row4 = QHBoxLayout()
        row4.addWidget(QLabel("Duration sec (0=∞):"))
        self.spin_duration = QDoubleSpinBox()
        self.spin_duration.setRange(0.0, 86400.0)
        self.spin_duration.setDecimals(1)
        self.spin_duration.setValue(0.0)
        row4.addWidget(self.spin_duration)
        row4.addWidget(QLabel("Pkt limit (0=∞):"))
        self.spin_limit = QSpinBox()
        self.spin_limit.setRange(0, 2_147_483_647)
        self.spin_limit.setValue(0)
        row4.addWidget(self.spin_limit)
        row4.addStretch()
        layout.addLayout(row4)

        self.setLayout(layout)

    def _browse_pcap(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "PCAP Output", "", "PCAP Files (*.pcap);;All Files (*)"
        )
        if path:
            self.edit_pcap.setText(path)

    def _browse_json(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "JSONL Output", "", "JSONL Files (*.jsonl);;All Files (*)"
        )
        if path:
            self.edit_json.setText(path)

    def export_format(self) -> ExportFormat:
        return ExportFormat(self.combo_format.currentText())

    def pcap_path(self) -> str | None:
        t = self.edit_pcap.text().strip()
        return t if t else None

    def json_path(self) -> str | None:
        t = self.edit_json.text().strip()
        return t if t else None

    def duration_sec(self) -> float | None:
        v = self.spin_duration.value()
        return v if v > 0 else None

    def packet_limit(self) -> int | None:
        v = self.spin_limit.value()
        return v if v > 0 else None
