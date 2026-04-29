"""Network configuration panel – interface, MACs, EtherType."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from sender.sender_config import DEFAULT_ETHERTYPE


def _get_interfaces() -> list[str]:
    """Return available network interface names via Scapy."""
    try:
        from scapy.all import conf  # type: ignore[import-untyped]

        ifaces: list[str] = []
        if hasattr(conf, "ifaces"):
            for iface in conf.ifaces.values():
                name = getattr(iface, "name", None) or str(iface)
                desc = getattr(iface, "description", "")
                label = f"{name}" if not desc else f"{name} ({desc})"
                ifaces.append(label)
        if not ifaces:
            ifaces = list(conf.route.routes)  # fallback
        return sorted(ifaces)
    except Exception:
        return []


class NetworkPanel(QGroupBox):
    """Interface selector, MAC inputs, EtherType."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Network", parent)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout()

        # Interface
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

        # MACs
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Dst MAC:"))
        self.edit_dst_mac = QLineEdit("ff:ff:ff:ff:ff:ff")
        self.edit_dst_mac.setMaximumWidth(180)
        row2.addWidget(self.edit_dst_mac)
        row2.addWidget(QLabel("Src MAC:"))
        self.edit_src_mac = QLineEdit("00:00:00:00:00:00")
        self.edit_src_mac.setMaximumWidth(180)
        row2.addWidget(self.edit_src_mac)
        layout.addLayout(row2)

        # EtherType
        row3 = QHBoxLayout()
        row3.addWidget(QLabel("EtherType:"))
        self.edit_ethertype = QLineEdit(f"0x{DEFAULT_ETHERTYPE:04X}")
        self.edit_ethertype.setMaximumWidth(100)
        row3.addWidget(self.edit_ethertype)
        row3.addStretch()
        layout.addLayout(row3)

        self.setLayout(layout)

    def refresh_interfaces(self) -> None:
        current = self.combo_iface.currentText()
        self.combo_iface.clear()
        ifaces = _get_interfaces()
        self.combo_iface.addItems(ifaces)
        if current and current in ifaces:
            self.combo_iface.setCurrentText(current)

    def interface_name(self) -> str:
        """Return the raw interface name (before any description in parens)."""
        text = self.combo_iface.currentText().strip()
        if " (" in text:
            text = text.split(" (")[0]
        return text

    def dst_mac(self) -> str:
        return self.edit_dst_mac.text().strip()

    def src_mac(self) -> str:
        return self.edit_src_mac.text().strip()

    def ethertype(self) -> int:
        text = self.edit_ethertype.text().strip()
        if text.startswith(("0x", "0X")):
            return int(text, 16)
        return int(text)
