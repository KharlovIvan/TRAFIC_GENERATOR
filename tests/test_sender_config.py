"""Tests for sender.sender_config."""

from __future__ import annotations

import pytest

from common.enums import GenerationMode
from sender.sender_config import SenderConfig, DEFAULT_ETHERTYPE


class TestSenderConfigValidation:
    def test_valid_defaults_except_interface(self):
        cfg = SenderConfig(interface="eth0")
        assert cfg.validate() == []

    def test_missing_interface(self):
        cfg = SenderConfig()
        errors = cfg.validate()
        assert any("interface" in e.lower() for e in errors)

    def test_invalid_dst_mac(self):
        cfg = SenderConfig(interface="eth0", dst_mac="not-a-mac")
        errors = cfg.validate()
        assert any("destination MAC" in e for e in errors)

    def test_invalid_src_mac(self):
        cfg = SenderConfig(interface="eth0", src_mac="ZZ:ZZ:ZZ:ZZ:ZZ:ZZ")
        errors = cfg.validate()
        assert any("source MAC" in e for e in errors)

    def test_valid_mac_with_dashes(self):
        cfg = SenderConfig(interface="eth0", dst_mac="AA-BB-CC-DD-EE-FF")
        errors = cfg.validate()
        assert not any("MAC" in e for e in errors)

    def test_negative_pps(self):
        cfg = SenderConfig(interface="eth0", packets_per_second=0)
        errors = cfg.validate()
        assert any("per second" in e.lower() for e in errors)

    def test_negative_count(self):
        cfg = SenderConfig(interface="eth0", packet_count=-1)
        errors = cfg.validate()
        assert any("count" in e.lower() for e in errors)

    def test_negative_duration(self):
        cfg = SenderConfig(interface="eth0", duration_seconds=-1.0)
        errors = cfg.validate()
        assert any("duration" in e.lower() for e in errors)

    def test_stream_id_too_large(self):
        cfg = SenderConfig(interface="eth0", stream_id=2**33)
        errors = cfg.validate()
        assert any("stream" in e.lower() for e in errors)


class TestNormalizeMac:
    def test_lowercase(self):
        assert SenderConfig.normalize_mac("AA:BB:CC:DD:EE:FF") == "aa:bb:cc:dd:ee:ff"

    def test_dashes_to_colons(self):
        assert SenderConfig.normalize_mac("AA-BB-CC-DD-EE-FF") == "aa:bb:cc:dd:ee:ff"


class TestSenderConfigDefaults:
    def test_ethertype_default(self):
        cfg = SenderConfig()
        assert cfg.ethertype == DEFAULT_ETHERTYPE

    def test_mode_default(self):
        cfg = SenderConfig()
        assert cfg.generation_mode is GenerationMode.FIXED
