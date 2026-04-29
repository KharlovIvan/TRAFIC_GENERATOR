"""Network configuration panel – interface, EtherType, promiscuous."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


def _get_interfaces() -> list[str]:
    try:
        from scapy.all import conf  # type: ignore[import-untyped]

        ifaces: list[str] = []
        if hasattr(conf, "ifaces"):
            for iface in conf.ifaces.values():
                name = getattr(iface, "name", None) or str(iface)
                desc = getattr(iface, "description", "")
                label = f"{name}" if not desc else f"{name} ({desc})"
                ifaces.append(label)
        return sorted(ifaces)
    except Exception:
        return []


class NetworkPanel(QGroupBox):
    """Interface selector, EtherType, promiscuous mode."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Network", parent)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout()

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Interface:"))
        self.combo_iface = QComboBox()
        self.combo_iface.setEditable(True)
        self.combo_iface.setMinimumWidth(250)
        row1.addWidget(self.combo_iface, 1)
        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.clicked.connect(self.refresh_interfaces)
        row1.addWidget(self.btn_refresh)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("EtherType:"))
        self.edit_ethertype = QLineEdit("0x88B5")
        self.edit_ethertype.setMaximumWidth(100)
        row2.addWidget(self.edit_ethertype)
        self.chk_promisc = QCheckBox("Promiscuous mode")
        self.chk_promisc.setChecked(True)
        row2.addWidget(self.chk_promisc)
        row2.addStretch()
        layout.addLayout(row2)

        self.setLayout(layout)

    def refresh_interfaces(self) -> None:
        current = self.combo_iface.currentText()
        self.combo_iface.clear()
        ifaces = _get_interfaces()
        self.combo_iface.addItems(ifaces)
        if current and current in ifaces:
            self.combo_iface.setCurrentText(current)

    def interface_name(self) -> str:
        text = self.combo_iface.currentText().strip()
        if " (" in text:
            text = text.split(" (")[0]
        return text

    def ethertype(self) -> int:
        text = self.edit_ethertype.text().strip()
        if text.startswith(("0x", "0X")):
            return int(text, 16)
        return int(text)

    def promiscuous(self) -> bool:
        return self.chk_promisc.isChecked()
