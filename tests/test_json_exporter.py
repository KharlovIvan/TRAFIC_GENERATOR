"""Tests for receiver.json_exporter."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from receiver.json_exporter import JsonExporter
from common.exceptions import ExportError


class TestJsonExporter:
    def test_start_creates_file(self, tmp_path: Path):
        out = tmp_path / "out.jsonl"
        exporter = JsonExporter()
        exporter.start(str(out))
        exporter.stop()
        assert out.exists()

    def test_write_valid_jsonl(self, tmp_path: Path):
        out = tmp_path / "out.jsonl"
        exporter = JsonExporter()
        exporter.start(str(out))
        exporter.write({"a": 1, "b": "hello"})
        exporter.write({"a": 2, "b": "world"})
        exporter.stop()

        lines = out.read_text().strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0]) == {"a": 1, "b": "hello"}
        assert json.loads(lines[1]) == {"a": 2, "b": "world"}

    def test_write_before_start_raises(self):
        exporter = JsonExporter()
        with pytest.raises(ExportError, match="not started"):
            exporter.write({"x": 1})

    def test_incremental_write_flushes(self, tmp_path: Path):
        out = tmp_path / "out.jsonl"
        exporter = JsonExporter()
        exporter.start(str(out))
        exporter.write({"seq": 1})
        # File should already contain data before stop
        content = out.read_text()
        assert "seq" in content
        exporter.stop()

    def test_invalid_packet_record_serializes(self, tmp_path: Path):
        out = tmp_path / "out.jsonl"
        exporter = JsonExporter()
        exporter.start(str(out))
        record = {
            "rx_timestamp_ns": 123456789,
            "valid": False,
            "error": "Invalid magic: 0x0000",
            "payload": None,
        }
        exporter.write(record)
        exporter.stop()

        parsed = json.loads(out.read_text().strip())
        assert parsed["valid"] is False
        assert "Invalid magic" in parsed["error"]

    def test_creates_parent_dirs(self, tmp_path: Path):
        out = tmp_path / "sub" / "dir" / "out.jsonl"
        exporter = JsonExporter()
        exporter.start(str(out))
        exporter.write({"test": True})
        exporter.stop()
        assert out.exists()

    def test_stop_is_idempotent(self, tmp_path: Path):
        out = tmp_path / "out.jsonl"
        exporter = JsonExporter()
        exporter.start(str(out))
        exporter.stop()
        exporter.stop()  # should not raise
