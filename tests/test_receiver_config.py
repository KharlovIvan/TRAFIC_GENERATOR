"""Tests for receiver.receiver_config."""

from __future__ import annotations

import pytest

from common.enums import ExportFormat
from receiver.receiver_config import ReceiverConfig


class TestReceiverConfigValidation:
    def test_valid_full_config(self):
        cfg = ReceiverConfig(
            interface_name="eth0",
            schema_path="schema.xml",
            export_format=ExportFormat.PCAP_AND_JSON,
            pcap_output_path="out.pcap",
            json_output_path="out.jsonl",
        )
        assert cfg.validate() == []

    def test_missing_interface(self):
        cfg = ReceiverConfig(schema_path="s.xml", pcap_output_path="o.pcap",
                             json_output_path="o.jsonl")
        errors = cfg.validate()
        assert any("interface" in e.lower() for e in errors)

    def test_missing_schema(self):
        cfg = ReceiverConfig(interface_name="eth0", pcap_output_path="o.pcap",
                             json_output_path="o.jsonl")
        errors = cfg.validate()
        assert any("schema" in e.lower() for e in errors)

    def test_invalid_ethertype(self):
        cfg = ReceiverConfig(interface_name="eth0", schema_path="s.xml",
                             ethertype=0x1FFFF,
                             pcap_output_path="o.pcap",
                             json_output_path="o.jsonl")
        errors = cfg.validate()
        assert any("ethertype" in e.lower() for e in errors)

    def test_pcap_format_requires_pcap_path(self):
        cfg = ReceiverConfig(
            interface_name="eth0", schema_path="s.xml",
            export_format=ExportFormat.PCAP,
            pcap_output_path=None,
        )
        errors = cfg.validate()
        assert any("pcap" in e.lower() for e in errors)

    def test_json_format_requires_json_path(self):
        cfg = ReceiverConfig(
            interface_name="eth0", schema_path="s.xml",
            export_format=ExportFormat.JSON,
            json_output_path=None,
        )
        errors = cfg.validate()
        assert any("json" in e.lower() for e in errors)

    def test_pcap_json_requires_both(self):
        cfg = ReceiverConfig(
            interface_name="eth0", schema_path="s.xml",
            export_format=ExportFormat.PCAP_AND_JSON,
            pcap_output_path=None, json_output_path=None,
        )
        errors = cfg.validate()
        assert len(errors) >= 2

    def test_pcap_only_no_json_path_needed(self):
        cfg = ReceiverConfig(
            interface_name="eth0", schema_path="s.xml",
            export_format=ExportFormat.PCAP,
            pcap_output_path="out.pcap",
            json_output_path=None,
        )
        assert cfg.validate() == []

    def test_json_only_no_pcap_path_needed(self):
        cfg = ReceiverConfig(
            interface_name="eth0", schema_path="s.xml",
            export_format=ExportFormat.JSON,
            json_output_path="out.jsonl",
            pcap_output_path=None,
        )
        assert cfg.validate() == []

    def test_invalid_duration(self):
        cfg = ReceiverConfig(
            interface_name="eth0", schema_path="s.xml",
            pcap_output_path="o.pcap", json_output_path="o.jsonl",
            duration_sec=-1.0,
        )
        errors = cfg.validate()
        assert any("duration" in e.lower() for e in errors)

    def test_zero_duration_invalid(self):
        cfg = ReceiverConfig(
            interface_name="eth0", schema_path="s.xml",
            pcap_output_path="o.pcap", json_output_path="o.jsonl",
            duration_sec=0.0,
        )
        errors = cfg.validate()
        assert any("duration" in e.lower() for e in errors)

    def test_invalid_packet_limit(self):
        cfg = ReceiverConfig(
            interface_name="eth0", schema_path="s.xml",
            pcap_output_path="o.pcap", json_output_path="o.jsonl",
            packet_limit=-5,
        )
        errors = cfg.validate()
        assert any("packet limit" in e.lower() for e in errors)

    def test_none_duration_is_ok(self):
        cfg = ReceiverConfig(
            interface_name="eth0", schema_path="s.xml",
            pcap_output_path="o.pcap", json_output_path="o.jsonl",
            duration_sec=None,
        )
        assert cfg.validate() == []
