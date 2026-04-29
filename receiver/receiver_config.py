"""Receiver configuration dataclass with validation."""

from __future__ import annotations

from dataclasses import dataclass

from common.enums import CaptureMode, ExportFormat
from common.exceptions import ReceiverConfigError


@dataclass
class ReceiverConfig:
    """All parameters needed to drive a receiving session."""

    interface_name: str = ""
    ethertype: int = 0x88B5
    schema_path: str = ""
    export_format: ExportFormat = ExportFormat.PCAP_AND_JSON
    pcap_output_path: str | None = None
    json_output_path: str | None = None
    duration_sec: float | None = None
    packet_limit: int | None = None
    promiscuous: bool = True
    capture_mode: CaptureMode = CaptureMode.DEBUG

    def validate(self) -> list[str]:
        """Return list of validation errors (empty = valid)."""
        errors: list[str] = []
        if not self.interface_name:
            errors.append("Network interface is required.")
        if not (0 <= self.ethertype <= 0xFFFF):
            errors.append(
                f"EtherType must be 0x0000–0xFFFF, got 0x{self.ethertype:04X}"
            )
        if not self.schema_path:
            errors.append("Schema path is required.")
        if self.export_format in (ExportFormat.PCAP, ExportFormat.PCAP_AND_JSON):
            if not self.pcap_output_path:
                errors.append("PCAP output path is required for selected format.")
        if self.export_format in (ExportFormat.JSON, ExportFormat.PCAP_AND_JSON):
            if not self.json_output_path:
                errors.append("JSON output path is required for selected format.")
        if self.duration_sec is not None and self.duration_sec <= 0:
            errors.append("Duration must be > 0 if specified.")
        if self.packet_limit is not None and self.packet_limit <= 0:
            errors.append("Packet limit must be > 0 if specified.")
        return errors
