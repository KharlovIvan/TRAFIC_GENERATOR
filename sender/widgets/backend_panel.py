"""Backend selector panel – toggle between Python and Native backends."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from common.enums import BackendMode
from sender.backends.native_backend import (
    is_native_available,
    is_native_transport_available,
    reset_native_cache,
)
from sender.backends.python_backend import PythonSenderBackend


class BackendPanel(QGroupBox):
    """Lets the user choose between the Python and Native sender backends."""

    backend_changed = Signal(str)  # emits BackendMode.value

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Backend", parent)
        self._build_ui()
        self._update_status()

    def _build_ui(self) -> None:
        layout = QVBoxLayout()

        row = QHBoxLayout()
        self._btn_group = QButtonGroup(self)

        self.radio_python = QRadioButton("Python")
        self.radio_python.setChecked(True)
        self._btn_group.addButton(self.radio_python)
        row.addWidget(self.radio_python)

        self.radio_native = QRadioButton("Native (Rust/C++)")
        self._btn_group.addButton(self.radio_native)
        row.addWidget(self.radio_native)

        row.addStretch()
        layout.addLayout(row)

        self.lbl_status = QLabel()
        layout.addWidget(self.lbl_status)

        self.setLayout(layout)

        self._btn_group.buttonClicked.connect(self._on_selection_changed)

    def _update_status(self) -> None:
        """Refresh the status label and enable/disable options accordingly."""
        python_errors = PythonSenderBackend.validate_environment()
        native_ok = is_native_available()
        transport_ok = is_native_transport_available()

        parts: list[str] = []

        if python_errors:
            parts.append(f"Python: {', '.join(python_errors)}")
            self.radio_python.setEnabled(False)
        else:
            parts.append("Python backend ready")
            self.radio_python.setEnabled(True)

        if native_ok and transport_ok:
            parts.append("Native backend ready (real NIC)")
            self.radio_native.setEnabled(True)
        elif native_ok:
            parts.append("Native backend: Npcap not found — no NIC access")
            self.radio_native.setEnabled(False)
        else:
            parts.append("Native backend not available")
            self.radio_native.setEnabled(False)

        self.lbl_status.setText("  |  ".join(parts))

    def _on_selection_changed(self) -> None:
        self.backend_changed.emit(self.backend_mode().value)

    def backend_mode(self) -> BackendMode:
        """Return the currently selected backend mode."""
        if self.radio_native.isChecked():
            return BackendMode.NATIVE
        return BackendMode.PYTHON

    def refresh(self) -> None:
        """Re-check backend availability (e.g. after installing native extension)."""
        reset_native_cache()
        self._update_status()
