"""Schema panel – file picker, load, validation status, payload info."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class SchemaPanel(QGroupBox):
    """Lets the user pick an XML schema and shows load/validation status."""

    schema_loaded = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Schema", parent)
        self._build_ui()
        self._connect_signals()

    def _build_ui(self) -> None:
        layout = QVBoxLayout()

        row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Path to schema XML …")
        self.path_edit.setReadOnly(True)
        row.addWidget(self.path_edit)

        self.btn_browse = QPushButton("Browse…")
        row.addWidget(self.btn_browse)

        self.btn_load = QPushButton("Load")
        self.btn_load.setEnabled(False)
        row.addWidget(self.btn_load)
        layout.addLayout(row)

        self.lbl_info = QLabel("No schema loaded.")
        layout.addWidget(self.lbl_info)

        self.txt_warnings = QTextEdit()
        self.txt_warnings.setReadOnly(True)
        self.txt_warnings.setMaximumHeight(60)
        self.txt_warnings.setVisible(False)
        layout.addWidget(self.txt_warnings)

        self.setLayout(layout)

    def _connect_signals(self) -> None:
        self.btn_browse.clicked.connect(self._on_browse)

    def _on_browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Schema XML", "", "XML Files (*.xml);;All Files (*)"
        )
        if path:
            self.path_edit.setText(path)
            self.btn_load.setEnabled(True)

    def set_info(self, text: str) -> None:
        self.lbl_info.setText(text)

    def set_warnings(self, warnings: list[str]) -> None:
        if warnings:
            self.txt_warnings.setPlainText("\n".join(warnings))
            self.txt_warnings.setVisible(True)
        else:
            self.txt_warnings.clear()
            self.txt_warnings.setVisible(False)

    def current_path(self) -> str:
        return self.path_edit.text().strip()
