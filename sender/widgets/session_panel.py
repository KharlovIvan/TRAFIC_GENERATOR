"""Session control panel – Start/Stop, live counters, status log."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class SessionPanel(QGroupBox):
    """Start/Stop buttons, live counters, and a scrollable status log."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Session", parent)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout()

        # Buttons
        btn_row = QHBoxLayout()
        self.btn_start = QPushButton("Start")
        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setEnabled(False)
        btn_row.addWidget(self.btn_start)
        btn_row.addWidget(self.btn_stop)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # Counters — row 1
        counter_row1 = QHBoxLayout()
        self.lbl_attempted = QLabel("Attempted: 0")
        self.lbl_packets = QLabel("Sent: 0")
        self.lbl_failed = QLabel("Failed: 0")
        self.lbl_bytes = QLabel("Bytes: 0")
        for lbl in (self.lbl_attempted, self.lbl_packets, self.lbl_failed, self.lbl_bytes):
            counter_row1.addWidget(lbl)
        counter_row1.addStretch()
        layout.addLayout(counter_row1)

        # Counters — row 2
        counter_row2 = QHBoxLayout()
        self.lbl_pps = QLabel("PPS: 0")
        self.lbl_throughput = QLabel("Throughput: 0 bps")
        self.lbl_elapsed = QLabel("Elapsed: 0.0 s")
        for lbl in (self.lbl_pps, self.lbl_throughput, self.lbl_elapsed):
            counter_row2.addWidget(lbl)
        counter_row2.addStretch()
        layout.addLayout(counter_row2)

        # Status log
        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        self.txt_log.setMaximumHeight(120)
        layout.addWidget(self.txt_log)

        self.setLayout(layout)

    def set_running(self, running: bool) -> None:
        """Toggle button states."""
        self.btn_start.setEnabled(not running)
        self.btn_stop.setEnabled(running)

    def update_counters(self, snap: dict[str, object]) -> None:
        """Update counter labels from a metrics snapshot dict."""
        self.lbl_attempted.setText(f"Attempted: {snap.get('packets_attempted', 0)}")
        self.lbl_packets.setText(f"Sent: {snap.get('packets_sent', 0)}")
        self.lbl_failed.setText(f"Failed: {snap.get('packets_failed', 0)}")
        self.lbl_bytes.setText(f"Bytes: {snap.get('bytes_sent', 0)}")
        self.lbl_pps.setText(f"PPS: {snap.get('pps', 0)}")
        # Format throughput readably
        bps = float(snap.get("bps", 0) or 0)
        gbps = float(snap.get("gbps", 0) or 0)
        if gbps >= 0.01:
            tp_str = f"{gbps:.3f} Gbps"
        elif bps >= 1_000_000:
            tp_str = f"{bps / 1_000_000:.2f} Mbps"
        elif bps >= 1_000:
            tp_str = f"{bps / 1_000:.1f} kbps"
        else:
            tp_str = f"{bps:.0f} bps"
        self.lbl_throughput.setText(f"Throughput: {tp_str}")
        self.lbl_elapsed.setText(f"Elapsed: {snap.get('elapsed_seconds', 0)} s")

    def reset_counters(self) -> None:
        self.lbl_attempted.setText("Attempted: 0")
        self.lbl_packets.setText("Sent: 0")
        self.lbl_failed.setText("Failed: 0")
        self.lbl_bytes.setText("Bytes: 0")
        self.lbl_pps.setText("PPS: 0")
        self.lbl_throughput.setText("Throughput: 0 bps")
        self.lbl_elapsed.setText("Elapsed: 0.0 s")

    def log(self, message: str) -> None:
        self.txt_log.append(message)
