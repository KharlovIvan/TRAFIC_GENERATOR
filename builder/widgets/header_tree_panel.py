"""Header tree panel – tree view of headers and nested sub-headers."""

from __future__ import annotations

import copy

from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from common.schema_models import FieldSchema, HeaderSchema, PacketSchema
from common.schema_validator import validate_schema_structure


_HEADER_ROLE = Qt.ItemDataRole.UserRole
_FIELD_ROLE = Qt.ItemDataRole.UserRole + 1


class HeaderTreeWidget(QTreeWidget):
    """Tree widget that emits a signal after a successful internal drop."""

    dropped = Signal()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        item = self.itemAt(event.position().toPoint())

        # Right-click deselection feature: clear current selection quickly.
        if event.button() == Qt.MouseButton.RightButton:
            self.clearSelection()
            self.setCurrentItem(None)
            event.accept()
            return

        # Left-click on empty area should deselect active header.
        if event.button() == Qt.MouseButton.LeftButton and item is None:
            self.clearSelection()
            self.setCurrentItem(None)
            event.accept()
            return

        super().mousePressEvent(event)

    def dropEvent(self, event) -> None:  # type: ignore[override]
        super().dropEvent(event)
        self.dropped.emit()
_FIELD_ROLE = Qt.ItemDataRole.UserRole + 1


class HeaderTreeWidget(QTreeWidget):
    """Tree widget that emits a signal after a successful internal drop."""

    dropped = Signal()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # type: ignore[override]
        item = self.itemAt(event.position().toPoint())

        # Right-click deselection feature: clear current selection quickly.
        if event.button() == Qt.MouseButton.RightButton:
            self.clearSelection()
            self.setCurrentItem(None)
            event.accept()
            return

        # Left-click on empty area should deselect active header.
        if event.button() == Qt.MouseButton.LeftButton and item is None:
            self.clearSelection()
            self.setCurrentItem(None)
            event.accept()
            return

        super().mousePressEvent(event)

    def dropEvent(self, event) -> None:  # type: ignore[override]
        super().dropEvent(event)
        self.dropped.emit()


class HeaderTreePanel(QGroupBox):
    """Displays the header/field hierarchy and allows add/remove/reorder."""
    """Displays the header/field hierarchy and allows add/remove/reorder."""

    header_selected = Signal(object)  # emits HeaderSchema or None
    field_selected = Signal(object)  # emits FieldSchema or None
    reorder_failed = Signal(str)
    # action is one of: "add", "remove", "up", "down", "reordered", "rename".
    header_action = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Headers", parent)
        self._schema: PacketSchema | None = None
        self._build_ui()
        self._connect_signals()

    # -- UI ----------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout()

        self.tree = HeaderTreeWidget()
        self.tree = HeaderTreeWidget()
        self.tree.setHeaderLabels(["Header Name"])
        self.tree.setColumnCount(1)
        self.tree.setDragDropMode(QTreeWidget.DragDropMode.InternalMove)
        self.tree.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.tree.setDragEnabled(True)
        self.tree.setAcceptDrops(True)
        layout.addWidget(self.tree)

        btn_layout = QHBoxLayout()
        self.btn_add = QPushButton("Add Header")
        self.btn_remove = QPushButton("Remove")
        self.btn_up = QPushButton("▲ Up")
        self.btn_down = QPushButton("▼ Down")
        for btn in (self.btn_add, self.btn_remove, self.btn_up, self.btn_down):
        for btn in (self.btn_add, self.btn_remove, self.btn_up, self.btn_down):
            btn_layout.addWidget(btn)
        layout.addLayout(btn_layout)

        self.setLayout(layout)

    def _connect_signals(self) -> None:
        self.tree.currentItemChanged.connect(self._on_selection_changed)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.tree.dropped.connect(self._on_tree_dropped)
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        self.tree.dropped.connect(self._on_tree_dropped)
        self.btn_add.clicked.connect(lambda: self.header_action.emit("add"))
        self.btn_remove.clicked.connect(lambda: self.header_action.emit("remove"))
        self.btn_up.clicked.connect(lambda: self.header_action.emit("up"))
        self.btn_down.clicked.connect(lambda: self.header_action.emit("down"))

    # -- Public API --------------------------------------------------------

    def set_schema(self, schema: PacketSchema | None) -> None:
        self._schema = schema
        self.refresh()

    def refresh(self) -> None:
        selected_header = self.selected_header()
        selected_field = self.selected_field()

        selected_header = self.selected_header()
        selected_field = self.selected_field()

        self.tree.blockSignals(True)
        self.tree.clear()
        if self._schema:
            for hdr in self._schema.headers:
                self._add_header_item(None, hdr)
        self.tree.expandAll()

        if selected_field is not None:
            item = self._find_item_for_field(selected_field)
            if item is not None:
                self.tree.setCurrentItem(item)
        elif selected_header is not None:
            item = self._find_item_for_header(selected_header)
            if item is not None:
                self.tree.setCurrentItem(item)


        if selected_field is not None:
            item = self._find_item_for_field(selected_field)
            if item is not None:
                self.tree.setCurrentItem(item)
        elif selected_header is not None:
            item = self._find_item_for_header(selected_header)
            if item is not None:
                self.tree.setCurrentItem(item)

        self.tree.blockSignals(False)
        self._on_selection_changed()

    def select_header(self, header: HeaderSchema | None) -> None:
        if header is None:
            self.tree.clearSelection()
            self.tree.setCurrentItem(None)
            self._on_selection_changed()
            return
        item = self._find_item_for_header(header)
        if item is not None:
            self.tree.setCurrentItem(item)
            self._on_selection_changed()
        self._on_selection_changed()

    def select_header(self, header: HeaderSchema | None) -> None:
        if header is None:
            self.tree.clearSelection()
            self.tree.setCurrentItem(None)
            self._on_selection_changed()
            return
        item = self._find_item_for_header(header)
        if item is not None:
            self.tree.setCurrentItem(item)
            self._on_selection_changed()

    def selected_header(self) -> HeaderSchema | None:
        item = self.tree.currentItem()
        if item is None:
            return None
        header = item.data(0, _HEADER_ROLE)
        return header if isinstance(header, HeaderSchema) else None

    def selected_field(self) -> FieldSchema | None:
        item = self.tree.currentItem()
        if item is None:
            return None
        field = item.data(0, _FIELD_ROLE)
        return field if isinstance(field, FieldSchema) else None
        header = item.data(0, _HEADER_ROLE)
        return header if isinstance(header, HeaderSchema) else None

    def selected_field(self) -> FieldSchema | None:
        item = self.tree.currentItem()
        if item is None:
            return None
        field = item.data(0, _FIELD_ROLE)
        return field if isinstance(field, FieldSchema) else None

    def selected_parent(self) -> PacketSchema | HeaderSchema | None:
        """Return the parent container of the selected header."""
        item = self.tree.currentItem()
        if item is None:
            return self._schema
        if self.selected_header() is None:
            return None
        if self.selected_header() is None:
            return None
        parent_item = item.parent()
        if parent_item is None:
            return self._schema
        return parent_item.data(0, _HEADER_ROLE)

    def selected_field_parent(self) -> HeaderSchema | None:
        item = self.tree.currentItem()
        if item is None:
            return None
        if self.selected_field() is None:
            return None
        parent_item = item.parent()
        if parent_item is None:
            return None
        parent = parent_item.data(0, _HEADER_ROLE)
        return parent if isinstance(parent, HeaderSchema) else None

    def selected_field_parent(self) -> HeaderSchema | None:
        item = self.tree.currentItem()
        if item is None:
            return None
        if self.selected_field() is None:
            return None
        parent_item = item.parent()
        if parent_item is None:
            return None
        parent = parent_item.data(0, _HEADER_ROLE)
        return parent if isinstance(parent, HeaderSchema) else None

    # -- Internal ----------------------------------------------------------

    def _add_header_item(
        self, parent_item: QTreeWidgetItem | None, header: HeaderSchema
    ) -> QTreeWidgetItem:
        if parent_item is None:
            item = QTreeWidgetItem(self.tree, [header.name])
        else:
            item = QTreeWidgetItem(parent_item, [header.name])
        item.setData(0, _HEADER_ROLE, header)
        item.setFlags(
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsDragEnabled
            | Qt.ItemFlag.ItemIsDropEnabled
        )

        for child in header.children:
            if isinstance(child, HeaderSchema):
                self._add_header_item(item, child)
            elif isinstance(child, FieldSchema):
                field_item = QTreeWidgetItem(item, [child.name])
                field_item.setData(0, _FIELD_ROLE, child)
                field_item.setFlags(
                    Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                )
        item.setFlags(
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsDragEnabled
            | Qt.ItemFlag.ItemIsDropEnabled
        )

        for child in header.children:
            if isinstance(child, HeaderSchema):
                self._add_header_item(item, child)
            elif isinstance(child, FieldSchema):
                field_item = QTreeWidgetItem(item, [child.name])
                field_item.setData(0, _FIELD_ROLE, child)
                field_item.setFlags(
                    Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                )
        return item

    def _on_tree_dropped(self) -> None:
        if self._schema is None:
            return

        # Keep a safe copy so invalid drag/drop states can be rolled back.
        backup = copy.deepcopy(self._schema)
        self._sync_schema_from_tree()

        errors = validate_schema_structure(self._schema)
        if errors:
            # Roll back to last valid schema state and restore the tree view.
            self._schema.headers = backup.headers
            self._schema.declared_total_bit_length = backup.declared_total_bit_length
            self._schema.name = backup.name
            self.refresh()
            self.reorder_failed.emit("\n".join(errors))
            return

        self._on_selection_changed()
        self.header_action.emit("reordered")

    def _on_item_double_clicked(self, _item: QTreeWidgetItem, _column: int) -> None:
        self.header_action.emit("rename")

    def _find_item_for_header(self, header: HeaderSchema) -> QTreeWidgetItem | None:
        for i in range(self.tree.topLevelItemCount()):
            found = self._find_item_for_header_recursive(self.tree.topLevelItem(i), header)
            if found is not None:
                return found
        return None

    def _find_item_for_header_recursive(
        self, item: QTreeWidgetItem, header: HeaderSchema
    ) -> QTreeWidgetItem | None:
        candidate = item.data(0, _HEADER_ROLE)
        if candidate is header:
            return item
        for i in range(item.childCount()):
            found = self._find_item_for_header_recursive(item.child(i), header)
            if found is not None:
                return found
        return None

    def _find_item_for_field(self, field: FieldSchema) -> QTreeWidgetItem | None:
        for i in range(self.tree.topLevelItemCount()):
            found = self._find_item_for_field_recursive(self.tree.topLevelItem(i), field)
            if found is not None:
                return found
        return None

    def _find_item_for_field_recursive(
        self, item: QTreeWidgetItem, field: FieldSchema
    ) -> QTreeWidgetItem | None:
        candidate = item.data(0, _FIELD_ROLE)
        if candidate is field:
            return item
        for i in range(item.childCount()):
            found = self._find_item_for_field_recursive(item.child(i), field)
            if found is not None:
                return found
        return None

    def _sync_schema_from_tree(self) -> None:
        assert self._schema is not None

        def sync_header(item: QTreeWidgetItem, header: HeaderSchema) -> None:
            new_children: list[HeaderSchema | FieldSchema] = []
            for i in range(item.childCount()):
                child_item = item.child(i)
                subheader = child_item.data(0, _HEADER_ROLE)
                field = child_item.data(0, _FIELD_ROLE)
                if isinstance(subheader, HeaderSchema):
                    new_children.append(subheader)
                    sync_header(child_item, subheader)
                elif isinstance(field, FieldSchema):
                    new_children.append(field)
            header.children = new_children

        new_top: list[HeaderSchema] = []
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            header = item.data(0, _HEADER_ROLE)
            if isinstance(header, HeaderSchema):
                new_top.append(header)
                sync_header(item, header)
        self._schema.headers = new_top

    def _on_selection_changed(self) -> None:
        selected_header = self.selected_header()
        selected_field = self.selected_field()

        # If a field is selected, keep the parent header active in other panels.
        if selected_header is None and selected_field is not None:
            item = self.tree.currentItem()
            parent_item = item.parent() if item else None
            parent_header = parent_item.data(0, _HEADER_ROLE) if parent_item else None
            active_parent = parent_header if isinstance(parent_header, HeaderSchema) else None
            self.header_selected.emit(active_parent)
            self.field_selected.emit(selected_field)
        else:
            self.header_selected.emit(selected_header)
            self.field_selected.emit(None)

        has_header_selected = selected_header is not None
        self.btn_remove.setEnabled(has_header_selected)
        self.btn_up.setEnabled(has_header_selected)
        self.btn_down.setEnabled(has_header_selected)
