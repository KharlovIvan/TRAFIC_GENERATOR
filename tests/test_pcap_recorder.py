"""Tests for receiver.pcap_recorder (using Scapy PcapWriter)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from common.exceptions import ExportError
from receiver.pcap_recorder import PcapRecorder


class TestPcapRecorder:
    @patch("receiver.pcap_recorder.PcapRecorder.start")
    def test_write_before_start_raises(self, mock_start: MagicMock):
        recorder = PcapRecorder()
        with pytest.raises(ExportError, match="not started"):
            recorder.write(b"fake")

    def test_start_write_stop(self, tmp_path: Path):
        from scapy.all import Ether, Raw  # type: ignore[import-untyped]

        out = tmp_path / "out.pcap"
        recorder = PcapRecorder()
        recorder.start(str(out))
        pkt = Ether(dst="ff:ff:ff:ff:ff:ff", src="00:00:00:00:00:00") / Raw(b"\x01\x02")
        recorder.write(pkt)
        recorder.stop()
        assert out.exists()
        assert out.stat().st_size > 0

    def test_stop_is_idempotent(self, tmp_path: Path):
        from scapy.all import Ether, Raw  # type: ignore[import-untyped]

        out = tmp_path / "out.pcap"
        recorder = PcapRecorder()
        recorder.start(str(out))
        pkt = Ether(dst="ff:ff:ff:ff:ff:ff") / Raw(b"\x01")
        recorder.write(pkt)
        recorder.stop()
        recorder.stop()  # should not raise
