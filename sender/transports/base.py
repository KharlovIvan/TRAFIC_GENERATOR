"""Abstract base class for sender transport backends."""

from __future__ import annotations

from abc import ABC, abstractmethod


class SenderTransport(ABC):
    """Interface for sending raw Ethernet frames.

    Concrete implementations wrap a specific transport mechanism
    (Scapy L2 socket, raw socket, DPDK, etc.).
    """

    @abstractmethod
    def open(self, interface: str) -> None:
        """Open the transport on the given network interface."""

    @abstractmethod
    def send(self, frame_bytes: bytes) -> int:
        """Send a single raw Ethernet frame.

        Returns the number of bytes accepted for transmission by the
        OS / NIC send path.  Raises on unrecoverable transport errors.
        """

    @abstractmethod
    def close(self) -> None:
        """Release all resources held by this transport."""

    def __enter__(self) -> SenderTransport:
        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self.close()
