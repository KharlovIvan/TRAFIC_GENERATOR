"""XML preview panel – read-only display of current generated XML."""

from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QGroupBox,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)


class XmlPreviewPanel(QGroupBox):
    """Read-only text area showing the XML representation of the schema."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("XML Preview", parent)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout()
        self.text_edit = QPlainTextEdit()
        self.text_edit.setReadOnly(True)
        font = QFont("Consolas", 10)
        font.setStyleHint(QFont.StyleHint.Monospace)
        self.text_edit.setFont(font)
        layout.addWidget(self.text_edit)
        self.setLayout(layout)

    def set_xml(self, xml_text: str) -> None:
        self.text_edit.setPlainText(xml_text)

    def clear(self) -> None:
        self.text_edit.clear()
