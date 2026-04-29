"""Tests for receiver.receiver_service."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from common.enums import ExportFormat
from common.exceptions import ReceiverConfigError, ReceiverOperationError
from receiver.receiver_config import ReceiverConfig
from receiver.receiver_service import ReceiverService

_VALID_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<packet name="Test" totalBitLength="16">
  <header name="H1">
    <field name="val" type="INTEGER" bitLength="16" />
  </header>
</packet>
"""

_SEMANTIC_BAD_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<packet name="Test" totalBitLength="32">
  <header name="H1">
    <field name="val" type="INTEGER" bitLength="16" />
  </header>
</packet>
"""

_DUP_GLOBAL_FIELD_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<packet name="Test" totalBitLength="16">
    <header name="H1">
        <field name="dup" type="INTEGER" bitLength="8" />
    </header>
    <header name="H2">
        <field name="dup" type="INTEGER" bitLength="8" />
    </header>
</packet>
"""


def _write_temp_xml(content: str) -> Path:
    f = tempfile.NamedTemporaryFile(suffix=".xml", delete=False, mode="w", encoding="utf-8")
    f.write(content)
    f.close()
    return Path(f.name)


class TestReceiverServiceLoad:
    def test_load_valid_schema(self):
        path = _write_temp_xml(_VALID_XML)
        svc = ReceiverService()
        schema = svc.load_schema(path)
        assert schema.name == "Test"
        assert svc.schema is not None

    def test_schema_summary(self):
        path = _write_temp_xml(_VALID_XML)
        svc = ReceiverService()
        svc.load_schema(path)
        summary = svc.schema_summary()
        assert summary["name"] == "Test"
        assert summary["field_count"] == 1
        assert summary["payload_bits"] == 16
        assert summary["payload_bytes"] == 2

    def test_validate_clean_schema(self):
        path = _write_temp_xml(_VALID_XML)
        svc = ReceiverService()
        svc.load_schema(path)
        warnings = svc.validate_schema_for_receive()
        assert warnings == []

    def test_validate_semantic_issues(self):
        path = _write_temp_xml(_SEMANTIC_BAD_XML)
        svc = ReceiverService()
        svc.load_schema(path)
        warnings = svc.validate_schema_for_receive()
        assert len(warnings) > 0

    def test_load_rejects_duplicate_global_field_names(self):
        path = _write_temp_xml(_DUP_GLOBAL_FIELD_XML)
        svc = ReceiverService()
        with pytest.raises(ReceiverOperationError, match="duplicate field names"):
            svc.load_schema(path)


class TestReceiverServiceStart:
    def test_start_without_schema_raises(self):
        svc = ReceiverService()
        cfg = ReceiverConfig(
            interface_name="eth0", schema_path="s.xml",
            pcap_output_path="o.pcap", json_output_path="o.jsonl",
        )
        with pytest.raises(ReceiverOperationError, match="No schema"):
            svc.start(cfg)

    def test_start_with_semantic_errors_raises(self):
        path = _write_temp_xml(_SEMANTIC_BAD_XML)
        svc = ReceiverService()
        svc.load_schema(path)
        cfg = ReceiverConfig(
            interface_name="eth0", schema_path=str(path),
            pcap_output_path="o.pcap", json_output_path="o.jsonl",
        )
        with pytest.raises(ReceiverOperationError, match="semantic"):
            svc.start(cfg)

    def test_start_with_bad_config_raises(self):
        path = _write_temp_xml(_VALID_XML)
        svc = ReceiverService()
        svc.load_schema(path)
        cfg = ReceiverConfig(schema_path=str(path))  # missing interface
        with pytest.raises(ReceiverConfigError):
            svc.start(cfg)

    def test_not_running_initially(self):
        svc = ReceiverService()
        assert not svc.is_running

    def test_validate_without_load(self):
        svc = ReceiverService()
        warnings = svc.validate_schema_for_receive()
        assert any("no schema" in w.lower() for w in warnings)
