"""Generation settings panel – mode, PPS, count, duration, stream ID."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from common.enums import GenerationMode


class GenerationPanel(QGroupBox):
    """Controls for generation mode, pacing, and stop conditions."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Generation", parent)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout()

        # Mode
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Mode:"))
        self.combo_mode = QComboBox()
        for mode in GenerationMode:
            self.combo_mode.addItem(mode.value)
        row1.addWidget(self.combo_mode)
        row1.addStretch()
        layout.addLayout(row1)

        # PPS + Stream ID
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("PPS:"))
        self.spin_pps = QSpinBox()
        self.spin_pps.setRange(1, 1_000_000)
        self.spin_pps.setValue(1)
        row2.addWidget(self.spin_pps)

        row2.addWidget(QLabel("Stream ID:"))
        self.spin_stream_id = QSpinBox()
        self.spin_stream_id.setRange(0, 2_147_483_647)
        self.spin_stream_id.setValue(1)
        row2.addWidget(self.spin_stream_id)
        row2.addStretch()
        layout.addLayout(row2)

        # Packet count + Duration
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Packet Count (0=∞):"))
        self.spin_count = QSpinBox()
        self.spin_count.setRange(0, 2_147_483_647)
        self.spin_count.setValue(0)
        row3.addWidget(self.spin_count)

        row3.addWidget(QLabel("Duration sec (0=∞):"))
        self.spin_duration = QDoubleSpinBox()
        self.spin_duration.setRange(0.0, 86400.0)
        self.spin_duration.setDecimals(1)
        self.spin_duration.setValue(0.0)
        row3.addWidget(self.spin_duration)
        row3.addStretch()
        layout.addLayout(row3)

        self.setLayout(layout)

    def generation_mode(self) -> GenerationMode:
        return GenerationMode(self.combo_mode.currentText())

    def packets_per_second(self) -> int:
        return self.spin_pps.value()

    def packet_count(self) -> int:
        return self.spin_count.value()

    def duration_seconds(self) -> float:
        return self.spin_duration.value()

    def stream_id(self) -> int:
        return self.spin_stream_id.value()
