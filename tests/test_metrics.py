"""Tests for common.metrics."""

from __future__ import annotations

import time

from common.metrics import SenderMetrics


class TestSenderMetrics:
    def test_initial_state(self):
        m = SenderMetrics()
        assert m.packets_sent == 0
        assert m.bytes_sent == 0
        assert m.elapsed_seconds == 0.0

    def test_reset(self):
        m = SenderMetrics(packets_sent=10, bytes_sent=500)
        m.reset()
        assert m.packets_sent == 0
        assert m.bytes_sent == 0
        assert m.start_time > 0

    def test_record_packet(self):
        m = SenderMetrics()
        m.reset()
        m.record_packet(100)
        assert m.packets_sent == 1
        assert m.bytes_sent == 100

    def test_record_multiple(self):
        m = SenderMetrics()
        m.reset()
        m.record_packet(50)
        m.record_packet(60)
        assert m.packets_sent == 2
        assert m.bytes_sent == 110

    def test_elapsed_after_reset(self):
        m = SenderMetrics()
        m.reset()
        time.sleep(0.05)
        assert m.elapsed_seconds >= 0.04

    def test_pps_zero_when_no_time(self):
        m = SenderMetrics()
        assert m.packets_per_second == 0.0

    def test_bps_zero_when_no_time(self):
        m = SenderMetrics()
        assert m.bits_per_second == 0.0

    def test_snapshot_keys(self):
        m = SenderMetrics()
        m.reset()
        m.record_packet(64)
        snap = m.snapshot()
        assert "packets_sent" in snap
        assert "bytes_sent" in snap
        assert "elapsed_seconds" in snap
        assert "pps" in snap
        assert "bps" in snap

    def test_snapshot_values(self):
        m = SenderMetrics()
        m.reset()
        m.record_packet(100)
        snap = m.snapshot()
        assert snap["packets_sent"] == 1
        assert snap["bytes_sent"] == 100
