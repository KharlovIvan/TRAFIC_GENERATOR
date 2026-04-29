"""Session panel – Start/Stop buttons and status log."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class SessionPanel(QGroupBox):
    """Start/Stop buttons and a scrollable status log."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Session", parent)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout()

        btn_row = QHBoxLayout()
        self.btn_start = QPushButton("Start")
        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setEnabled(False)
        btn_row.addWidget(self.btn_start)
        btn_row.addWidget(self.btn_stop)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setMaximumHeight(120)
        layout.addWidget(self.txt_log)

        self.setLayout(layout)

    def set_running(self, running: bool) -> None:
        self.btn_start.setEnabled(not running)
        self.btn_stop.setEnabled(running)

    def log(self, message: str) -> None:
        self.txt_log.append(message)
