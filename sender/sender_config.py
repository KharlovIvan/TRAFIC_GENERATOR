"""Sender configuration dataclass with validation."""

from __future__ import annotations

import re
from dataclasses import dataclass

from common.enums import BackendMode, GenerationMode

MAC_PATTERN = re.compile(r"^([0-9A-Fa-f]{2}[:\-]){5}[0-9A-Fa-f]{2}$")
DEFAULT_ETHERTYPE = 0x88B5


@dataclass
class SenderConfig:
    """All parameters needed to drive a sending session."""

    interface: str = ""
    dst_mac: str = "ff:ff:ff:ff:ff:ff"
    src_mac: str = "00:00:00:00:00:00"
    ethertype: int = DEFAULT_ETHERTYPE
    packets_per_second: int = 1
    packet_count: int = 0  # 0 = unlimited
    duration_seconds: float = 0.0  # 0 = unlimited
    stream_id: int = 1
    generation_mode: GenerationMode = GenerationMode.FIXED
    backend_mode: BackendMode = BackendMode.PYTHON

    def validate(self) -> list[str]:
        """Return list of validation errors (empty = valid)."""
        errors: list[str] = []
        if not self.interface:
            errors.append("Network interface is required.")
        if not MAC_PATTERN.match(self.dst_mac):
            errors.append(f"Invalid destination MAC: {self.dst_mac}")
        if not MAC_PATTERN.match(self.src_mac):
            errors.append(f"Invalid source MAC: {self.src_mac}")
        if not (0 <= self.ethertype <= 0xFFFF):
            errors.append(
                f"EtherType must be 0x0000\u20130xFFFF, got 0x{self.ethertype:04X}"
            )
        if self.packets_per_second < 0:
            errors.append("Packets per second must be >= 0 (0 = unlimited rate).")
        if self.packet_count < 0:
            errors.append("Packet count must be >= 0 (0 = unlimited).")
        if self.duration_seconds < 0:
            errors.append("Duration must be >= 0 (0 = unlimited).")
        if not (0 <= self.stream_id <= 0xFFFFFFFF):
            errors.append("Stream ID must fit in 32 bits.")
        return errors

    @staticmethod
    def normalize_mac(mac: str) -> str:
        """Normalize a MAC to colon-separated lowercase."""
        return mac.replace("-", ":").lower()
