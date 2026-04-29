"""TestGen header: 28-byte binary header for traffic generation frames."""

from __future__ import annotations

import struct
import time
from dataclasses import dataclass

TESTGEN_MAGIC: int = 0x5447  # ASCII "TG"
TESTGEN_VERSION: int = 1
TESTGEN_HEADER_FORMAT: str = ">HBBIQQI"
TESTGEN_HEADER_SIZE: int = struct.calcsize(TESTGEN_HEADER_FORMAT)  # 28


@dataclass(frozen=True)
class TestGenHeader:
    """Parsed representation of the 28-byte TestGen header."""

    magic: int
    version: int
    flags: int
    stream_id: int
    sequence: int
    tx_timestamp_ns: int
    payload_len: int


def build_testgen_header(
    stream_id: int,
    sequence: int,
    tx_timestamp_ns: int,
    payload_len: int,
    flags: int = 0,
) -> bytes:
    """Pack a TestGen header into 28 bytes (big-endian)."""
    return struct.pack(
        TESTGEN_HEADER_FORMAT,
        TESTGEN_MAGIC,
        TESTGEN_VERSION,
        flags,
        stream_id,
        sequence,
        tx_timestamp_ns,
        payload_len,
    )


def parse_testgen_header(data: bytes) -> TestGenHeader:
    """Unpack 28 bytes into a :class:`TestGenHeader`."""
    if len(data) < TESTGEN_HEADER_SIZE:
        raise ValueError(
            f"Expected at least {TESTGEN_HEADER_SIZE} bytes, got {len(data)}"
        )
    magic, version, flags, stream_id, sequence, tx_ts, plen = struct.unpack(
        TESTGEN_HEADER_FORMAT, data[:TESTGEN_HEADER_SIZE]
    )
    return TestGenHeader(
        magic=magic,
        version=version,
        flags=flags,
        stream_id=stream_id,
        sequence=sequence,
        tx_timestamp_ns=tx_ts,
        payload_len=plen,
    )


def current_timestamp_ns() -> int:
    """Return the current time as nanoseconds since epoch."""
    return time.time_ns()
