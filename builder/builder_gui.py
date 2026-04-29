"""Main window for the XML Builder desktop application.

All business logic is delegated to ``BuilderService``.  The window
orchestrates the widget panels and connects GUI events to service calls.
"""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from builder.builder_config import (
    DEFAULT_PACKET_NAME,
    WINDOW_MIN_HEIGHT,
    WINDOW_MIN_WIDTH,
    WINDOW_TITLE,
    XML_FILE_FILTER,
)
from builder.builder_service import BuilderService
from builder.widgets.field_editor_panel import FieldEditorPanel
from builder.widgets.header_tree_panel import HeaderTreePanel
from builder.widgets.packet_panel import PacketPanel
from builder.widgets.property_panel import PropertyPanel
from builder.widgets.xml_preview_panel import XmlPreviewPanel
from common.enums import FieldType
from common.exceptions import BuilderOperationError, SchemaValidationError
from common.schema_models import FieldSchema, HeaderSchema
from common.utils import compute_packet_bit_length


class BuilderWindow(QMainWindow):
    """PySide6 main window for the XML Builder."""

    def __init__(self) -> None:
        super().__init__()
        self.service = BuilderService()
        self.setWindowTitle(WINDOW_TITLE)
        self.setMinimumSize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        self._build_menu()
        self._build_ui()
        self._connect_signals()
        self._sync_ui()

    # ------------------------------------------------------------------ menu

    def _build_menu(self) -> None:
        menu_bar = self.menuBar()

        file_menu = menu_bar.addMenu("&File")
        file_menu.addAction("&New", self._on_new)
        file_menu.addAction("&Open…", self._on_open)
        file_menu.addSeparator()
        file_menu.addAction("&Save", self._on_save)
        file_menu.addAction("Save &As…", self._on_save_as)

        tools_menu = menu_bar.addMenu("&Tools")
        tools_menu.addAction("&Validate", self._on_validate)

    # -------------------------------------------------------------------- UI

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)

        # Top: packet panel
        self.packet_panel = PacketPanel()
        root_layout.addWidget(self.packet_panel)

        # Main splitter: left (tree + fields) | right (properties + preview)
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left column
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.header_tree = HeaderTreePanel()
        left_layout.addWidget(self.header_tree, 2)
        self.field_editor = FieldEditorPanel()
        left_layout.addWidget(self.field_editor, 3)
        splitter.addWidget(left)

        # Right column
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.property_panel = PropertyPanel()
        right_layout.addWidget(self.property_panel, 1)
        self.xml_preview = XmlPreviewPanel()
        right_layout.addWidget(self.xml_preview, 3)
        splitter.addWidget(right)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        root_layout.addWidget(splitter, 1)

        # Bottom: validation area
        self.validation_area = QPlainTextEdit()
        self.validation_area.setReadOnly(True)
        self.validation_area.setMaximumHeight(100)
        self.validation_area.setPlaceholderText("Validation messages appear here.")
        root_layout.addWidget(self.validation_area)

        # Status bar
        self.setStatusBar(QStatusBar())

    # ------------------------------------------------------------- signals

    def _connect_signals(self) -> None:
        self.packet_panel.packet_changed.connect(self._on_packet_changed)
        self.header_tree.header_selected.connect(self._on_header_selected)
        self.header_tree.field_selected.connect(self._on_tree_field_selected)
        self.header_tree.reorder_failed.connect(self._on_tree_reorder_failed)
        self.header_tree.header_action.connect(self._on_header_action)
        self.field_editor.btn_add.clicked.connect(self._on_add_field)
        self.field_editor.btn_remove.clicked.connect(self._on_remove_field)
        self.field_editor.btn_up.clicked.connect(self._on_field_up)
        self.field_editor.btn_down.clicked.connect(self._on_field_down)
        self.field_editor.field_changed.connect(self._on_field_table_changed)
        self.field_editor.field_selected.connect(self._on_field_selected)
        self.field_editor.field_reordered.connect(self._on_field_reordered)
        self.field_editor.field_reordered.connect(self._on_field_reordered)

    # --------------------------------------------------------- file actions

    def _on_new(self) -> None:
        name, ok = QInputDialog.getText(
            self, "New Packet", "Packet name:", text=DEFAULT_PACKET_NAME
        )
        if not ok or not name.strip():
            return
        try:
            self.service.new_schema(name.strip())
        except BuilderOperationError as exc:
            QMessageBox.warning(self, "Error", str(exc))
            return
        self._sync_ui()
        self.statusBar().showMessage("New schema created.", 3000)

    def _on_open(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open Schema", "", XML_FILE_FILTER
        )
        if not path:
            return
        try:
            _schema, warnings = self.service.load_schema_tolerant(path)
        except (SchemaValidationError, Exception) as exc:
            QMessageBox.critical(self, "Open Failed", str(exc))
            return
        self._sync_ui()
        if warnings:
            self.validation_area.setPlainText(
                "Opened with warnings:\n" + "\n".join(warnings)
            )
        self.statusBar().showMessage(f"Opened: {path}", 3000)

    def _on_save(self) -> None:
        if not self.service.has_schema:
            return
        if self.service.file_path:
            self._do_save(self.service.file_path)
        else:
            self._on_save_as()

    def _on_save_as(self) -> None:
        if not self.service.has_schema:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Schema As", "", XML_FILE_FILTER
        )
        if not path:
            return
        self._do_save(path)

    def _do_save(self, path: str) -> None:
        try:
            self.service.save_schema(path)
        except Exception as exc:
            QMessageBox.critical(self, "Save Failed", str(exc))
            return
        self.statusBar().showMessage(f"Saved: {path}", 3000)

    # ------------------------------------------------------- validation

    def _on_validate(self) -> None:
        if not self.service.has_schema:
            self.validation_area.setPlainText("No schema loaded.")
            return
        errors = self.service.validate_current_schema()
        if errors:
            self.validation_area.setPlainText("\n".join(errors))
        else:
            self.validation_area.setPlainText("✓ Schema is valid.")

    # ------------------------------------------------------- packet panel

    def _on_packet_changed(self) -> None:
        if not self.service.has_schema:
            return
        try:
            self.service.update_packet(
                name=self.packet_panel.get_name() or None,
            )
        except BuilderOperationError as exc:
            self.statusBar().showMessage(str(exc), 3000)
            return
        self._refresh_preview()
        self._refresh_validation()
        self._show_packet_properties()

    # ------------------------------------------------------- header actions

    def _on_header_action(self, action: str) -> None:
        if not self.service.has_schema:
            return
        schema = self.service.schema
        assert schema is not None
        new_header: HeaderSchema | None = None
        new_header: HeaderSchema | None = None

        if action == "add":
            name, ok = QInputDialog.getText(self, "Add Header", "Header name:")
            if not ok or not name.strip():
                return
            try:
                selected = self.header_tree.selected_header()
                if selected is None:
                    new_header = self.service.add_header(schema, name.strip())
                else:
                    new_header = self.service.add_subheader(selected, name.strip())
                selected = self.header_tree.selected_header()
                if selected is None:
                    new_header = self.service.add_header(schema, name.strip())
                else:
                    new_header = self.service.add_subheader(selected, name.strip())
            except BuilderOperationError as exc:
                QMessageBox.warning(self, "Error", str(exc))
                return

        elif action == "remove":
            hdr = self.header_tree.selected_header()
            parent = self.header_tree.selected_parent()
            if hdr is None or parent is None:
                return
            reply = QMessageBox.question(
                self,
                "Confirm Remove",
                f"Remove header '{hdr.name}' and all its contents?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
            try:
                self.service.remove_header(parent, hdr.name)
            except BuilderOperationError as exc:
                QMessageBox.warning(self, "Error", str(exc))
                return

        elif action == "up":
            hdr = self.header_tree.selected_header()
            parent = self.header_tree.selected_parent()
            if hdr is None or parent is None:
                return
            try:
                self.service.move_header_up(parent, hdr.name)
            except BuilderOperationError as exc:
                self.statusBar().showMessage(str(exc), 2000)
                return

        elif action == "down":
            hdr = self.header_tree.selected_header()
            parent = self.header_tree.selected_parent()
            if hdr is None or parent is None:
                return
            try:
                self.service.move_header_down(parent, hdr.name)
            except BuilderOperationError as exc:
                self.statusBar().showMessage(str(exc), 2000)
                return

        elif action == "reordered":
            self._refresh_preview()
            self._refresh_validation()
            self._refresh_total()
            return

        elif action == "rename":
            selected_header = self.header_tree.selected_header()
            selected_field = self.header_tree.selected_field()

            if selected_header is not None:
                parent = self.header_tree.selected_parent()
                if parent is None:
                    return
                name, ok = QInputDialog.getText(
                    self, "Rename Header", "Header name:", text=selected_header.name
                )
                if not ok or not name.strip():
                    return
                try:
                    self.service.update_header(parent, selected_header, name=name.strip())
                except BuilderOperationError as exc:
                    QMessageBox.warning(self, "Error", str(exc))
                    return
            elif selected_field is not None:
                parent_header = self.header_tree.selected_field_parent()
                if parent_header is None:
                    return
                name, ok = QInputDialog.getText(
                    self, "Rename Field", "Field name:", text=selected_field.name
                )
                if not ok or not name.strip():
                    return
                try:
                    self.service.update_field(parent_header, selected_field, name=name.strip())
                except BuilderOperationError as exc:
                    QMessageBox.warning(self, "Error", str(exc))
                    return
            else:
                return

        elif action == "reordered":
            self._refresh_preview()
            self._refresh_validation()
            self._refresh_total()
            return

        elif action == "rename":
            selected_header = self.header_tree.selected_header()
            selected_field = self.header_tree.selected_field()

            if selected_header is not None:
                parent = self.header_tree.selected_parent()
                if parent is None:
                    return
                name, ok = QInputDialog.getText(
                    self, "Rename Header", "Header name:", text=selected_header.name
                )
                if not ok or not name.strip():
                    return
                try:
                    self.service.update_header(parent, selected_header, name=name.strip())
                except BuilderOperationError as exc:
                    QMessageBox.warning(self, "Error", str(exc))
                    return
            elif selected_field is not None:
                parent_header = self.header_tree.selected_field_parent()
                if parent_header is None:
                    return
                name, ok = QInputDialog.getText(
                    self, "Rename Field", "Field name:", text=selected_field.name
                )
                if not ok or not name.strip():
                    return
                try:
                    self.service.update_field(parent_header, selected_field, name=name.strip())
                except BuilderOperationError as exc:
                    QMessageBox.warning(self, "Error", str(exc))
                    return
            else:
                return

        self._refresh_tree()
        if new_header is not None:
            self.header_tree.select_header(new_header)
        if new_header is not None:
            self.header_tree.select_header(new_header)
        self._refresh_preview()
        self._refresh_validation()
        self._refresh_total()

    def _on_header_selected(self, header: HeaderSchema | None) -> None:
        self.field_editor.set_header(header)
        if header is not None:
            self.property_panel.show_header(header)
        elif self.service.has_schema:
            self._show_packet_properties()
        else:
            self.property_panel.clear()

    # ------------------------------------------------------- field actions

    def _on_add_field(self) -> None:
        hdr = self._active_header_for_field_editing()
        if hdr is None:
            QMessageBox.information(self, "Info", "Select a header first.")
            return
        name, ok = QInputDialog.getText(self, "Add Field", "Field name:")
        if not ok or not name.strip():
            return
        try:
            new_field = self.service.add_field(hdr, name.strip(), FieldType.INTEGER, 8)
        except BuilderOperationError as exc:
            QMessageBox.warning(self, "Error", str(exc))
            return
        self.header_tree.select_header(hdr)
        self._refresh_tree()
        self.field_editor.set_header(hdr)
        self.field_editor.select_field(new_field)
        self._refresh_preview()
        self._refresh_validation()
        self._refresh_total()

    def _on_remove_field(self) -> None:
        hdr = self._active_header_for_field_editing()
        field = self.field_editor.selected_field()
        if hdr is None or field is None:
            return
        reply = QMessageBox.question(
            self,
            "Confirm Remove",
            f"Remove field '{field.name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            self.service.remove_field(hdr, field.name)
        except BuilderOperationError as exc:
            QMessageBox.warning(self, "Error", str(exc))
            return
        self._refresh_tree()
        self._refresh_tree()
        self.field_editor.refresh()
        self._refresh_preview()
        self._refresh_validation()
        self._refresh_total()

    def _on_field_up(self) -> None:
        hdr = self._active_header_for_field_editing()
        field = self.field_editor.selected_field()
        if hdr is None or field is None:
            return
        try:
            self.service.move_field_up(hdr, field.name)
        except BuilderOperationError as exc:
            self.statusBar().showMessage(str(exc), 2000)
            return
        moved = field
        self.header_tree.select_header(hdr)
        self._refresh_tree()
        self.field_editor.set_header(hdr)
        self.field_editor.select_field(moved)
        self._refresh_preview()
        self._refresh_validation()
        self._refresh_total()

    def _on_field_down(self) -> None:
        hdr = self._active_header_for_field_editing()
        field = self.field_editor.selected_field()
        if hdr is None or field is None:
            return
        try:
            self.service.move_field_down(hdr, field.name)
        except BuilderOperationError as exc:
            self.statusBar().showMessage(str(exc), 2000)
            return
        moved = field
        self.header_tree.select_header(hdr)
        self._refresh_tree()
        self.field_editor.set_header(hdr)
        self.field_editor.select_field(moved)
        self._refresh_preview()
        self._refresh_validation()
        self._refresh_total()

    def _on_field_table_changed(self) -> None:
        """Apply inline edits from the field table back to the model."""
        hdr = self._active_header_for_field_editing()
        if hdr is None:
            return
        for row_idx in range(self.field_editor.table.rowCount()):
            if row_idx >= len(hdr.fields):
                break
            name, type_str, bit_length = self.field_editor.read_row(row_idx)
            field = hdr.fields[row_idx]
            try:
                ft = FieldType.from_string(type_str)
                self.service.update_field(
                    hdr,
                    field,
                    name=name or None,
                    field_type=ft,
                    bit_length=bit_length,
                )
            except (BuilderOperationError, ValueError) as exc:
                self.statusBar().showMessage(str(exc), 3000)
        self._refresh_tree()
        self._refresh_preview()
        self._refresh_validation()
        self._refresh_total()

    def _on_field_reordered(self, source_row: int, target_row: int, to_end: bool) -> None:
        hdr = self._active_header_for_field_editing()
        if hdr is None:
            return

        src_field = self.field_editor.field_at_row(source_row)
        if src_field is None:
            return

        try:
            if to_end:
                self.service.move_field_to_end(hdr, src_field.name)
            else:
                dst_field = self.field_editor.field_at_row(target_row)
                if dst_field is None or dst_field.name == src_field.name:
                    return
                self.service.swap_fields(hdr, src_field.name, dst_field.name)
        except BuilderOperationError as exc:
            self.statusBar().showMessage(str(exc), 3000)
            return

        self.header_tree.select_header(hdr)
        self._refresh_tree()
        self.field_editor.set_header(hdr)
        self.field_editor.select_field(src_field)
        self._refresh_preview()
        self._refresh_validation()
        self._refresh_total()

    def _active_header_for_field_editing(self) -> HeaderSchema | None:
        return self.header_tree.selected_header() or self.header_tree.selected_field_parent()

    def _on_tree_field_selected(self, field: FieldSchema | None) -> None:
        if field is not None:
            self.property_panel.show_field(field)

    def _on_tree_reorder_failed(self, message: str) -> None:
        self.validation_area.setPlainText(message)
        self.statusBar().showMessage("Invalid tree reorder was reverted.", 4000)

    def _on_field_selected(self, field) -> None:
        if field is not None:
            self.property_panel.show_field(field)
            return

        header = self.header_tree.selected_header()
        if header is not None:
            self.property_panel.show_header(header)
        elif self.service.has_schema:
            self._show_packet_properties()
        else:
            self.property_panel.clear()
            return

        header = self.header_tree.selected_header()
        if header is not None:
            self.property_panel.show_header(header)
        elif self.service.has_schema:
            self._show_packet_properties()
        else:
            self.property_panel.clear()

    # ------------------------------------------------------- refresh helpers

    def _sync_ui(self) -> None:
        schema = self.service.schema
        if schema:
            computed = compute_packet_bit_length(schema)
            self.packet_panel.set_values(schema.name, computed)
            self.header_tree.set_schema(schema)
        else:
            self.packet_panel.set_values("", 0)
            self.header_tree.set_schema(None)
        self.field_editor.set_header(None)
        self._refresh_preview()
        self._refresh_validation()
        if schema:
            self._show_packet_properties()
        else:
            self.property_panel.clear()

    def _refresh_tree(self) -> None:
        self.header_tree.refresh()

    def _refresh_total(self) -> None:
        if self.service.has_schema:
            computed = compute_packet_bit_length(self.service.schema)  # type: ignore[arg-type]
            self.service.schema.declared_total_bit_length = computed  # type: ignore[union-attr]
            self.service.schema.declared_total_bit_length = computed  # type: ignore[union-attr]
            self.packet_panel.update_total(computed)

    def _refresh_preview(self) -> None:
        if self.service.has_schema:
            try:
                xml = self.service.get_xml_preview()
                self.xml_preview.set_xml(xml)
            except Exception:
                self.xml_preview.set_xml("(error generating preview)")
        else:
            self.xml_preview.clear()

    def _refresh_validation(self) -> None:
        if not self.service.has_schema:
            self.validation_area.clear()
            return
        errors = self.service.validate_current_schema()
        if errors:
            self.validation_area.setPlainText("\n".join(errors))
        else:
            self.validation_area.setPlainText("✓ Schema is valid.")

    def _show_packet_properties(self) -> None:
        if self.service.schema:
            self.property_panel.show_packet(self.service.schema)


def run_builder_gui() -> None:
    """Entry point: launch the Builder GUI application."""
    app = QApplication.instance() or QApplication(sys.argv)
    window = BuilderWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    run_builder_gui()
