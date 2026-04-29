"""Tests for common.testgen_header."""

from __future__ import annotations

import struct

import pytest

from common.testgen_header import (
    TESTGEN_HEADER_SIZE,
    TESTGEN_MAGIC,
    TESTGEN_VERSION,
    TestGenHeader,
    build_testgen_header,
    current_timestamp_ns,
    parse_testgen_header,
)


class TestBuildTestGenHeader:
    def test_size(self):
        hdr = build_testgen_header(
            stream_id=1, sequence=0, tx_timestamp_ns=0, payload_len=0
        )
        assert len(hdr) == TESTGEN_HEADER_SIZE

    def test_magic_and_version(self):
        hdr = build_testgen_header(
            stream_id=1, sequence=0, tx_timestamp_ns=0, payload_len=0
        )
        magic = int.from_bytes(hdr[0:2], "big")
        version = hdr[2]
        assert magic == TESTGEN_MAGIC
        assert version == TESTGEN_VERSION

    def test_fields_packed(self):
        hdr = build_testgen_header(
            stream_id=42,
            sequence=100,
            tx_timestamp_ns=999_999_999,
            payload_len=64,
            flags=3,
        )
        parsed = parse_testgen_header(hdr)
        assert parsed.stream_id == 42
        assert parsed.sequence == 100
        assert parsed.tx_timestamp_ns == 999_999_999
        assert parsed.payload_len == 64
        assert parsed.flags == 3


class TestParseTestGenHeader:
    def test_round_trip(self):
        raw = build_testgen_header(
            stream_id=7, sequence=12345, tx_timestamp_ns=10**18, payload_len=128
        )
        parsed = parse_testgen_header(raw)
        assert parsed.magic == TESTGEN_MAGIC
        assert parsed.version == TESTGEN_VERSION
        assert parsed.stream_id == 7
        assert parsed.sequence == 12345
        assert parsed.tx_timestamp_ns == 10**18
        assert parsed.payload_len == 128

    def test_too_short_raises(self):
        with pytest.raises(ValueError, match="at least"):
            parse_testgen_header(b"\x00" * 10)

    def test_extra_bytes_ignored(self):
        raw = build_testgen_header(
            stream_id=1, sequence=0, tx_timestamp_ns=0, payload_len=0
        )
        parsed = parse_testgen_header(raw + b"\xff\xff\xff")
        assert parsed.stream_id == 1


class TestCurrentTimestampNs:
    def test_positive(self):
        ts = current_timestamp_ns()
        assert ts > 0

    def test_nanosecond_scale(self):
        ts = current_timestamp_ns()
        # Should be roughly year-2024 epoch nanos (> 1.7e18)
        assert ts > 1_000_000_000_000_000_000


class TestHeaderConstants:
    def test_size_is_28(self):
        assert TESTGEN_HEADER_SIZE == 28

    def test_magic_value(self):
        assert TESTGEN_MAGIC == 0x5447
