"""Sender and receiver metrics dataclasses and helpers."""

from __future__ import annotations

import time
from dataclasses import dataclass, field as dataclass_field


@dataclass
class SenderMetrics:
    """Tracks sender performance counters.

    ``packets_sent`` and ``bytes_sent`` reflect **successfully** sent data
    only.  ``packets_attempted`` counts every frame submitted to the
    transport, and ``packets_failed`` counts frames whose send call failed.
    Speed metrics (PPS, bps) are derived from successful counters only.
    """

    packets_attempted: int = 0
    packets_sent: int = 0
    packets_failed: int = 0
    bytes_sent: int = 0
    start_time: float = 0.0
    last_update_time: float = 0.0
    first_tx_timestamp_ns: int = 0
    last_tx_timestamp_ns: int = 0

    def reset(self) -> None:
        """Reset all counters and record the start time."""
        self.packets_attempted = 0
        self.packets_sent = 0
        self.packets_failed = 0
        self.bytes_sent = 0
        self.start_time = time.monotonic()
        self.last_update_time = self.start_time
        self.first_tx_timestamp_ns = 0
        self.last_tx_timestamp_ns = 0

    def record_send_attempt(self) -> None:
        """Record that a frame was submitted to the transport."""
        self.packets_attempted += 1

    def record_packet(self, byte_count: int, tx_timestamp_ns: int = 0) -> None:
        """Record a successfully sent packet."""
        self.packets_sent += 1
        self.bytes_sent += byte_count
        self.last_update_time = time.monotonic()
        if tx_timestamp_ns:
            if self.first_tx_timestamp_ns == 0:
                self.first_tx_timestamp_ns = tx_timestamp_ns
            self.last_tx_timestamp_ns = tx_timestamp_ns

    def record_send_failure(self) -> None:
        """Record a failed send attempt."""
        self.packets_failed += 1

    @property
    def elapsed_seconds(self) -> float:
        if self.start_time == 0.0:
            return 0.0
        return time.monotonic() - self.start_time

    @property
    def packets_per_second(self) -> float:
        elapsed = self.elapsed_seconds
        if elapsed <= 0:
            return 0.0
        return self.packets_sent / elapsed

    @property
    def bits_per_second(self) -> float:
        elapsed = self.elapsed_seconds
        if elapsed <= 0:
            return 0.0
        return (self.bytes_sent * 8) / elapsed

    @property
    def gbps(self) -> float:
        return self.bits_per_second / 1_000_000_000

    def snapshot(self) -> dict[str, object]:
        """Return a JSON-friendly snapshot of the current metrics."""
        return {
            "packets_attempted": self.packets_attempted,
            "packets_sent": self.packets_sent,
            "packets_failed": self.packets_failed,
            "bytes_sent": self.bytes_sent,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "pps": round(self.packets_per_second, 1),
            "bps": round(self.bits_per_second, 1),
            "gbps": round(self.gbps, 6),
        }


@dataclass
class ReceiverMetrics:
    """Tracks receiver performance counters."""

    packets_received: int = 0
    packets_parsed_ok: int = 0
    packets_invalid: int = 0
    bytes_received: int = 0
    first_rx_timestamp_ns: int | None = None
    last_rx_timestamp_ns: int | None = None
    stream_ids_seen: set[int] = dataclass_field(default_factory=set)
    last_sequence_per_stream: dict[int, int] = dataclass_field(default_factory=dict)
    start_time: float = 0.0

    def reset(self) -> None:
        self.packets_received = 0
        self.packets_parsed_ok = 0
        self.packets_invalid = 0
        self.bytes_received = 0
        self.first_rx_timestamp_ns = None
        self.last_rx_timestamp_ns = None
        self.stream_ids_seen = set()
        self.last_sequence_per_stream = {}
        self.start_time = time.monotonic()

    def record_packet(self, byte_count: int, rx_timestamp_ns: int,
                      valid: bool, stream_id: int | None = None,
                      sequence: int | None = None) -> None:
        self.packets_received += 1
        self.bytes_received += byte_count
        if self.first_rx_timestamp_ns is None:
            self.first_rx_timestamp_ns = rx_timestamp_ns
        self.last_rx_timestamp_ns = rx_timestamp_ns
        if valid:
            self.packets_parsed_ok += 1
        else:
            self.packets_invalid += 1
        if stream_id is not None:
            self.stream_ids_seen.add(stream_id)
        if stream_id is not None and sequence is not None:
            self.last_sequence_per_stream[stream_id] = sequence

    @property
    def elapsed_seconds(self) -> float:
        if self.start_time == 0.0:
            return 0.0
        return time.monotonic() - self.start_time

    @property
    def packets_per_second(self) -> float:
        elapsed = self.elapsed_seconds
        if elapsed <= 0:
            return 0.0
        return self.packets_received / elapsed

    @property
    def average_gbps(self) -> float:
        elapsed = self.elapsed_seconds
        if elapsed <= 0:
            return 0.0
        return (self.bytes_received * 8) / elapsed / 1_000_000_000

    def snapshot(self) -> dict[str, object]:
        return {
            "packets_received": self.packets_received,
            "packets_parsed_ok": self.packets_parsed_ok,
            "packets_invalid": self.packets_invalid,
            "bytes_received": self.bytes_received,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "pps": round(self.packets_per_second, 1),
            "average_gbps": round(self.average_gbps, 6),
            "unique_streams": len(self.stream_ids_seen),
        }
