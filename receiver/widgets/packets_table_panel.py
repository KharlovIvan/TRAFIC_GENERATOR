"""Packets table panel – bounded preview of recently parsed packets."""

from __future__ import annotations

from collections import deque

from PySide6.QtWidgets import (
    QGroupBox,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

_MAX_ROWS = 200


class PacketsTablePanel(QGroupBox):
    """Shows a bounded table of recently received packets."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Recent Packets", parent)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout()
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([
            "Timestamp", "Stream ID", "Sequence", "Valid", "Error",
        ])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents
        )
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.table)
        self.setLayout(layout)

    def add_packet(self, record: dict[str, object]) -> None:
        """Append a parsed packet record to the table (bounded)."""
        if self.table.rowCount() >= _MAX_ROWS:
            self.table.removeRow(0)

        row = self.table.rowCount()
        self.table.insertRow(row)

        rx_ts = str(record.get("rx_timestamp_ns", ""))
        tg = record.get("testgen_header")
        stream_id = ""
        sequence = ""
        if isinstance(tg, dict):
            stream_id = str(tg.get("stream_id", ""))
            sequence = str(tg.get("sequence", ""))

        valid = "OK" if record.get("valid") else "FAIL"
        error = str(record.get("error") or "")

        self.table.setItem(row, 0, QTableWidgetItem(rx_ts))
        self.table.setItem(row, 1, QTableWidgetItem(stream_id))
        self.table.setItem(row, 2, QTableWidgetItem(sequence))
        self.table.setItem(row, 3, QTableWidgetItem(valid))
        self.table.setItem(row, 4, QTableWidgetItem(error))

        self.table.scrollToBottom()

    def clear(self) -> None:
        self.table.setRowCount(0)
