"""Field editor panel – table of fields for the currently selected header."""

from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from common.constants import BOOLEAN_BIT_LENGTH
from common.enums import FieldType
from common.schema_models import FieldSchema, HeaderSchema


class FieldEditorPanel(QGroupBox):
    """Displays and edits the fields of a single header."""

    field_changed = Signal()  # any field was added/removed/edited
    field_selected = Signal(object)  # FieldSchema or None

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Fields", parent)
        self._header: HeaderSchema | None = None
        self._updating = False
        self._build_ui()
        self._connect_signals()

    # -- UI ----------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout()

        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["Name", "Type", "Bit Length"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setDragDropMode(QTableWidget.DragDropMode.InternalMove)
        self.table.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.table.setDragEnabled(True)
        self.table.setAcceptDrops(True)
        layout.addWidget(self.table)

        btn_layout = QHBoxLayout()
        self.btn_add = QPushButton("Add Field")
        self.btn_remove = QPushButton("Remove Field")
        self.btn_up = QPushButton("▲ Up")
        self.btn_down = QPushButton("▼ Down")
        for btn in (self.btn_add, self.btn_remove, self.btn_up, self.btn_down):
            btn_layout.addWidget(btn)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

    def _connect_signals(self) -> None:
        self.table.currentCellChanged.connect(self._on_selection)
        self.table.cellChanged.connect(self._on_cell_changed)

    # -- Public API --------------------------------------------------------

    def set_header(self, header: HeaderSchema | None) -> None:
        self._header = header
        self.refresh()

    def refresh(self) -> None:
        self._updating = True
        self.table.setRowCount(0)
        if self._header:
            for field in self._header.fields:
                self._append_field_row(field)
        self._updating = False
        self._update_buttons()

    def selected_field(self) -> FieldSchema | None:
        row = self.table.currentRow()
        if row < 0 or self._header is None or row >= len(self._header.fields):
            return None
        return self._header.fields[row]

    def selected_row(self) -> int:
        return self.table.currentRow()

    # -- Internal ----------------------------------------------------------

    def _append_field_row(self, field: FieldSchema) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)

        name_item = QTableWidgetItem(field.name)
        self.table.setItem(row, 0, name_item)

        combo = QComboBox()
        for ft in FieldType:
            combo.addItem(ft.value)
        combo.setCurrentText(field.type.value)
        combo.currentTextChanged.connect(lambda _, r=row: self._on_combo_changed_for_row(r))
        self.table.setCellWidget(row, 1, combo)

        spin = QSpinBox()
        spin.setRange(8, 2_147_483_640)
        spin.setSingleStep(8)
        spin.setValue(field.bit_length)
        # Lock bitLength for BOOLEAN fields
        if field.type is FieldType.BOOLEAN:
            spin.setValue(BOOLEAN_BIT_LENGTH)
            spin.setEnabled(False)
        spin.valueChanged.connect(lambda _: self._on_spin_changed())
        self.table.setCellWidget(row, 2, spin)

    def _on_selection(self, row: int, _col: int, _prev_row: int, _prev_col: int) -> None:
        self.field_selected.emit(self.selected_field())
        self._update_buttons()

    def _on_cell_changed(self, row: int, col: int) -> None:
        if self._updating:
            return
        self.field_changed.emit()

    def _on_combo_changed_for_row(self, row: int) -> None:
        """Handle type combo change: lock/unlock spin for BOOLEAN."""
        combo: QComboBox | None = self.table.cellWidget(row, 1)  # type: ignore[assignment]
        spin: QSpinBox | None = self.table.cellWidget(row, 2)  # type: ignore[assignment]
        if combo and spin:
            is_bool = combo.currentText() == FieldType.BOOLEAN.value
            if is_bool:
                spin.setValue(BOOLEAN_BIT_LENGTH)
                spin.setEnabled(False)
            else:
                spin.setEnabled(True)
        if not self._updating:
            self.field_changed.emit()

    def _on_spin_changed(self) -> None:
        if not self._updating:
            self.field_changed.emit()

    def _update_buttons(self) -> None:
        has_sel = self.table.currentRow() >= 0 and self._header is not None
        self.btn_remove.setEnabled(has_sel)
        self.btn_up.setEnabled(has_sel)
        self.btn_down.setEnabled(has_sel)

    def read_row(self, row: int) -> tuple[str, str, int]:
        """Return (name, type_str, bit_length) from the given table row."""
        name_item = self.table.item(row, 0)
        name = name_item.text().strip() if name_item else ""
        combo: QComboBox = self.table.cellWidget(row, 1)  # type: ignore[assignment]
        type_str = combo.currentText() if combo else FieldType.INTEGER.value
        spin: QSpinBox = self.table.cellWidget(row, 2)  # type: ignore[assignment]
        bit_length = spin.value() if spin else 8
        return name, type_str, bit_length
