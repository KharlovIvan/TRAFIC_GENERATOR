"""Property panel – context-sensitive detail editor for selected item."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QLabel,
    QWidget,
)

from common.schema_models import FieldSchema, HeaderSchema, PacketSchema
from common.utils import compute_header_bit_length, compute_packet_bit_length


class PropertyPanel(QGroupBox):
    """Shows read-only summary of the selected item (packet/header/field)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Properties", parent)
        self._build_ui()

    def _build_ui(self) -> None:
        self._layout = QFormLayout()
        self._info_label = QLabel("Select an item to view properties.")
        self._layout.addRow(self._info_label)
        self.setLayout(self._layout)

    def show_packet(self, packet: PacketSchema) -> None:
        self._clear()
        self._add("Type:", "Packet")
        self._add("Name:", packet.name)
        self._add("Declared Bits:", str(packet.declared_total_bit_length))
        actual = compute_packet_bit_length(packet)
        self._add("Computed Bits:", str(actual))
        diff = packet.declared_total_bit_length - actual
        if diff != 0:
            self._add("Mismatch:", f"{diff:+d} bits")

    def show_header(self, header: HeaderSchema) -> None:
        self._clear()
        self._add("Type:", "Header")
        self._add("Name:", header.name)
        bits = compute_header_bit_length(header)
        self._add("Computed Bits:", str(bits))
        self._add("Fields:", str(len(header.fields)))
        self._add("Sub-headers:", str(len(header.subheaders)))

    def show_field(self, field: FieldSchema) -> None:
        self._clear()
        self._add("Type:", "Field")
        self._add("Name:", field.name)
        self._add("Field Type:", field.type.value)
        self._add("Bit Length:", str(field.bit_length))
        if field.default_value:
            self._add("Default:", field.default_value)

    def clear(self) -> None:
        self._clear()

    def _clear(self) -> None:
        while self._layout.rowCount():
            self._layout.removeRow(0)

    def _add(self, label: str, value: str) -> None:
        self._layout.addRow(label, QLabel(value))
