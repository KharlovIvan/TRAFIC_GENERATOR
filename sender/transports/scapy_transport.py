"""Scapy-based sender transport backend."""

from __future__ import annotations

from scapy.all import conf  # type: ignore[import-untyped]

from sender.transports.base import SenderTransport


class ScapySenderTransport(SenderTransport):
    """Sends raw Ethernet frames via Scapy's L2 socket.

    Keeps a single persistent socket open for the lifetime of the
    transport, avoiding the per-packet overhead of ``sendp()``.
    """

    def __init__(self) -> None:
        self._socket: object | None = None

    def open(self, interface: str) -> None:
        """Open an L2 socket on *interface*."""
        if self._socket is not None:
            self.close()
        self._socket = conf.L2socket(iface=interface)

    def send(self, frame_bytes: bytes) -> int:
        """Send raw *frame_bytes* through the open L2 socket."""
        if self._socket is None:
            raise RuntimeError("Transport is not open.")
        self._socket.send(frame_bytes)
        return len(frame_bytes)

    def close(self) -> None:
        """Close the L2 socket."""
        if self._socket is not None:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None
