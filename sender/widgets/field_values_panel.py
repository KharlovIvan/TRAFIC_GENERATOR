"""Field values panel – shows flattened fields with input widgets."""

from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import (
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from common.enums import FieldType
from common.schema_models import FieldSchema, PacketSchema
from common.utils import flatten_fields_in_layout_order


class FieldValuesPanel(QGroupBox):
    """Displays flattened fields and lets the user set fixed values."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Field Values (FIXED mode)", parent)
        self._fields: list[FieldSchema] = []
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout()
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Field", "Type", "Bits", "Value"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table)
        self.setLayout(layout)

    def load_schema(self, schema: PacketSchema, defaults: dict[str, Any]) -> None:
        """Populate the table from a loaded schema and its default values."""
        self._fields = flatten_fields_in_layout_order(schema)
        self.table.setRowCount(0)
        for field in self._fields:
            self._add_field_row(field, defaults.get(field.name))

    def _add_field_row(self, field: FieldSchema, default: Any) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)

        # Name
        self.table.setItem(row, 0, QTableWidgetItem(field.name))

        # Type
        self.table.setItem(row, 1, QTableWidgetItem(field.type.value))

        # Bit length
        self.table.setItem(row, 2, QTableWidgetItem(str(field.bit_length)))

        # Value widget
        widget = self._make_value_widget(field, default)
        self.table.setCellWidget(row, 3, widget)

    def _make_value_widget(self, field: FieldSchema, default: Any) -> QWidget:
        """Create the appropriate input widget for the field type."""
        if field.type is FieldType.INTEGER:
            spin = QSpinBox()
            spin.setRange(0, 2_147_483_647)
            spin.setValue(int(default) if default is not None else 0)
            return spin

        if field.type is FieldType.BOOLEAN:
            cb = QCheckBox()
            cb.setChecked(bool(default))
            return cb

        if field.type is FieldType.STRING:
            edit = QLineEdit()
            edit.setText(str(default) if default is not None else "")
            return edit

        # RAW_BYTES
        edit = QLineEdit()
        if isinstance(default, (bytes, bytearray)):
            edit.setText(default.hex())
        elif isinstance(default, str):
            edit.setText(default)
        else:
            edit.setText("00" * (field.bit_length // 8))
        edit.setPlaceholderText("hex bytes, e.g. AABB01")
        return edit

    def collect_values(self) -> dict[str, Any]:
        """Read current widget values and return a field-name → value map."""
        values: dict[str, Any] = {}
        for i, field in enumerate(self._fields):
            widget = self.table.cellWidget(i, 3)
            values[field.name] = self._read_widget(field, widget)
        return values

    def _read_widget(self, field: FieldSchema, widget: QWidget | None) -> Any:
        if widget is None:
            return 0

        if field.type is FieldType.INTEGER:
            return widget.value()  # type: ignore[union-attr]

        if field.type is FieldType.BOOLEAN:
            return widget.isChecked()  # type: ignore[union-attr]

        if field.type is FieldType.STRING:
            return widget.text()  # type: ignore[union-attr]

        # RAW_BYTES
        hex_str: str = widget.text().strip()  # type: ignore[union-attr]
        try:
            return bytes.fromhex(hex_str.replace(" ", "").replace("0x", ""))
        except ValueError:
            return b"\x00" * (field.bit_length // 8)
