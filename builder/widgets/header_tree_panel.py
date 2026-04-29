"""Header tree panel – tree view of headers and nested sub-headers."""

from __future__ import annotations

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from common.schema_models import HeaderSchema, PacketSchema


_HEADER_ROLE = Qt.ItemDataRole.UserRole


class HeaderTreePanel(QGroupBox):
    """Displays the header hierarchy and allows add/remove/reorder."""

    header_selected = Signal(object)  # emits HeaderSchema or None
    # Emits (parent, header_name, action) where action is one of the strings
    # "add", "add_sub", "remove", "up", "down".
    header_action = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Headers", parent)
        self._schema: PacketSchema | None = None
        self._build_ui()
        self._connect_signals()

    # -- UI ----------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout()

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Header Name"])
        self.tree.setColumnCount(1)
        self.tree.setDragDropMode(QTreeWidget.DragDropMode.InternalMove)
        self.tree.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.tree.setDragEnabled(True)
        self.tree.setAcceptDrops(True)
        layout.addWidget(self.tree)

        btn_layout = QHBoxLayout()
        self.btn_add = QPushButton("Add Header")
        self.btn_add_sub = QPushButton("Add Sub-header")
        self.btn_remove = QPushButton("Remove")
        self.btn_up = QPushButton("▲ Up")
        self.btn_down = QPushButton("▼ Down")
        for btn in (self.btn_add, self.btn_add_sub, self.btn_remove, self.btn_up, self.btn_down):
            btn_layout.addWidget(btn)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

    def _connect_signals(self) -> None:
        self.tree.currentItemChanged.connect(self._on_selection_changed)
        self.btn_add.clicked.connect(lambda: self.header_action.emit("add"))
        self.btn_add_sub.clicked.connect(lambda: self.header_action.emit("add_sub"))
        self.btn_remove.clicked.connect(lambda: self.header_action.emit("remove"))
        self.btn_up.clicked.connect(lambda: self.header_action.emit("up"))
        self.btn_down.clicked.connect(lambda: self.header_action.emit("down"))

    # -- Public API --------------------------------------------------------

    def set_schema(self, schema: PacketSchema | None) -> None:
        self._schema = schema
        self.refresh()

    def refresh(self) -> None:
        self.tree.blockSignals(True)
        self.tree.clear()
        if self._schema:
            for hdr in self._schema.headers:
                self._add_header_item(None, hdr)
        self.tree.expandAll()
        self.tree.blockSignals(False)
        self._on_selection_changed()

    def selected_header(self) -> HeaderSchema | None:
        item = self.tree.currentItem()
        if item is None:
            return None
        return item.data(0, _HEADER_ROLE)

    def selected_parent(self) -> PacketSchema | HeaderSchema | None:
        """Return the parent container of the selected header."""
        item = self.tree.currentItem()
        if item is None:
            return self._schema
        parent_item = item.parent()
        if parent_item is None:
            return self._schema
        return parent_item.data(0, _HEADER_ROLE)

    # -- Internal ----------------------------------------------------------

    def _add_header_item(
        self, parent_item: QTreeWidgetItem | None, header: HeaderSchema
    ) -> QTreeWidgetItem:
        if parent_item is None:
            item = QTreeWidgetItem(self.tree, [header.name])
        else:
            item = QTreeWidgetItem(parent_item, [header.name])
        item.setData(0, _HEADER_ROLE, header)
        for sub in header.subheaders:
            self._add_header_item(item, sub)
        return item

    def _on_selection_changed(self) -> None:
        hdr = self.selected_header()
        self.header_selected.emit(hdr)
        has_sel = hdr is not None
        self.btn_add_sub.setEnabled(has_sel)
        self.btn_remove.setEnabled(has_sel)
        self.btn_up.setEnabled(has_sel)
        self.btn_down.setEnabled(has_sel)
