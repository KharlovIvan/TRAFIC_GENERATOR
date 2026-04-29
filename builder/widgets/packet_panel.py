"""Packet-level property panel (name + read-only computed totalBitLength)."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)


class PacketPanel(QGroupBox):
    """Editable panel for packet-level attributes.

    The total bit length is displayed as a read-only label because it is
    auto-computed from the sum of all fields.
    """

    packet_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Packet Properties", parent)
        self._build_ui()
        self._connect_signals()

    # -- UI setup ----------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QFormLayout()

        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Packet name")
        layout.addRow("Name:", self.name_edit)

        self.total_bits_label = QLabel("0 bits")
        layout.addRow("Total Bit Length:", self.total_bits_label)

        self.setLayout(layout)

    def _connect_signals(self) -> None:
        self.name_edit.editingFinished.connect(self.packet_changed.emit)

    # -- Public API --------------------------------------------------------

    def get_name(self) -> str:
        return self.name_edit.text().strip()

    def get_total_bit_length(self) -> int:
        """Return the displayed total (for informational use only)."""
        text = self.total_bits_label.text().replace(" bits", "").strip()
        try:
            return int(text)
        except ValueError:
            return 0

    def set_values(self, name: str, total_bit_length: int) -> None:
        self.name_edit.blockSignals(True)
        self.name_edit.setText(name)
        self.total_bits_label.setText(f"{total_bit_length} bits")
        self.name_edit.blockSignals(False)

    def update_total(self, total_bit_length: int) -> None:
        """Update only the computed total display."""
        self.total_bits_label.setText(f"{total_bit_length} bits")
