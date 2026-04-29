"""PCAP recorder – thin wrapper around Scapy PcapWriter."""

from __future__ import annotations

from common.exceptions import ExportError


class PcapRecorder:
    """Write raw packets to a PCAP file incrementally."""

    def __init__(self) -> None:
        self._writer = None  # type: ignore[assignment]
        self._path: str | None = None

    def start(self, path: str) -> None:
        from scapy.utils import PcapWriter  # type: ignore[import-untyped]

        self._path = path
        try:
            self._writer = PcapWriter(path, append=False, sync=True)
        except Exception as exc:
            raise ExportError(f"Cannot open PCAP file: {exc}") from exc

    def write(self, packet: object) -> None:
        if self._writer is None:
            raise ExportError("PcapRecorder not started.")
        self._writer.write(packet)  # type: ignore[arg-type]

    def stop(self) -> None:
        if self._writer is not None:
            self._writer.close()
            self._writer = None
