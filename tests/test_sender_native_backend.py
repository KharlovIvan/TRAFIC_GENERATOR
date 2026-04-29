"""Tests for the NativeSenderBackend adapter (no native module required)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from common.enums import BackendMode, FieldType, GenerationMode
from common.metrics import SenderMetrics
from common.schema_models import FieldSchema, HeaderSchema, PacketSchema
from sender.backends.native_backend import (
    NativeSenderBackend,
    _native_metrics_to_python,
    flatten_config_for_native,
    flatten_schema_for_native,
    is_native_available,
    reset_native_cache,
)
from sender.sender_config import SenderConfig


def _simple_schema() -> PacketSchema:
    f = FieldSchema(name="val", type=FieldType.INTEGER, bit_length=16)
    h = HeaderSchema(name="H", fields=[f])
    return PacketSchema(name="P", declared_total_bit_length=16, headers=[h])


def _multi_field_schema() -> PacketSchema:
    f1 = FieldSchema(name="id", type=FieldType.INTEGER, bit_length=32)
    f2 = FieldSchema(name="label", type=FieldType.STRING, bit_length=64)
    f3 = FieldSchema(name="flag", type=FieldType.BOOLEAN, bit_length=8)
    h = HeaderSchema(name="H", fields=[f1, f2, f3])
    return PacketSchema(name="Multi", declared_total_bit_length=104, headers=[h])


# ===========================================================================
# Schema flattening
# ===========================================================================


class TestFlattenSchema:
    def test_single_field(self):
        flat = flatten_schema_for_native(_simple_schema())
        assert len(flat) == 1
        assert flat[0] == {"name": "val", "type": "INTEGER", "bit_length": 16}

    def test_multi_field_order_preserved(self):
        flat = flatten_schema_for_native(_multi_field_schema())
        names = [f["name"] for f in flat]
        assert names == ["id", "label", "flag"]

    def test_field_types_are_strings(self):
        flat = flatten_schema_for_native(_multi_field_schema())
        for f in flat:
            assert isinstance(f["type"], str)
            assert isinstance(f["bit_length"], int)

    def test_nested_headers(self):
        inner_f = FieldSchema(name="inner_val", type=FieldType.INTEGER, bit_length=8)
        inner_h = HeaderSchema(name="Inner", fields=[inner_f])
        outer_f = FieldSchema(name="outer_val", type=FieldType.INTEGER, bit_length=16)
        outer_h = HeaderSchema(name="Outer", fields=[outer_f], subheaders=[inner_h])
        schema = PacketSchema(name="Nested", declared_total_bit_length=24, headers=[outer_h])
        flat = flatten_schema_for_native(schema)
        names = [f["name"] for f in flat]
        assert "outer_val" in names
        assert "inner_val" in names


# ===========================================================================
# Config flattening
# ===========================================================================


class TestFlattenConfig:
    def test_basic_fields(self):
        cfg = SenderConfig(
            interface="eth0",
            packets_per_second=5000,
            packet_count=100,
        )
        result = flatten_config_for_native(cfg, _simple_schema(), {"val": 42})
        assert result["interface"] == "eth0"
        assert result["pps"] == 5000
        assert result["packet_count"] == 100

    def test_fixed_values_included(self):
        cfg = SenderConfig(interface="eth0")
        result = flatten_config_for_native(cfg, _simple_schema(), {"val": 99})
        assert result["fixed_values"]["val"] == 99

    def test_bytes_converted_to_hex(self):
        cfg = SenderConfig(interface="eth0")
        result = flatten_config_for_native(cfg, _simple_schema(), {"val": b"\xDE\xAD"})
        assert result["fixed_values"]["val"] == "dead"

    def test_none_fixed_values(self):
        cfg = SenderConfig(interface="eth0")
        result = flatten_config_for_native(cfg, _simple_schema(), None)
        assert result["fixed_values"] == {}

    def test_generation_mode_serialized(self):
        cfg = SenderConfig(interface="eth0", generation_mode=GenerationMode.RANDOM)
        result = flatten_config_for_native(cfg, _simple_schema(), {})
        assert result["generation_mode"] == "RANDOM"


# ===========================================================================
# Native metrics conversion
# ===========================================================================


class TestNativeMetricsConversion:
    def test_all_fields(self):
        raw = {
            "packets_attempted": 120,
            "packets_sent": 100,
            "packets_failed": 20,
            "bytes_sent": 5000,
            "first_tx_timestamp_ns": 1000,
            "last_tx_timestamp_ns": 2000,
        }
        m = _native_metrics_to_python(raw)
        assert isinstance(m, SenderMetrics)
        assert m.packets_attempted == 120
        assert m.packets_sent == 100
        assert m.packets_failed == 20
        assert m.bytes_sent == 5000
        assert m.first_tx_timestamp_ns == 1000
        assert m.last_tx_timestamp_ns == 2000

    def test_missing_fields_default_to_zero(self):
        m = _native_metrics_to_python({})
        assert m.packets_attempted == 0
        assert m.packets_sent == 0
        assert m.packets_failed == 0
        assert m.bytes_sent == 0

    def test_partial_fields(self):
        m = _native_metrics_to_python({"packets_sent": 7})
        assert m.packets_sent == 7
        assert m.bytes_sent == 0


# ===========================================================================
# Backend lifecycle (mocked native module)
# ===========================================================================


class TestNativeBackendWithMock:
    """Test NativeSenderBackend using a mocked trafic_native module."""

    def _make_mock_module(self):
        mod = MagicMock()
        mod.create_sender.return_value = 12345  # handle
        mod.start_sender.return_value = {
            "packets_attempted": 10,
            "packets_sent": 10,
            "packets_failed": 0,
            "bytes_sent": 500,
            "first_tx_timestamp_ns": 100,
            "last_tx_timestamp_ns": 200,
        }
        mod.is_transport_available.return_value = True
        mod.list_interfaces.return_value = [("\\Device\\NPF_eth0", "eth0")]
        return mod

    @patch("sender.backends.native_backend._try_import_native")
    def test_initialize_calls_create_sender(self, mock_import):
        mod = self._make_mock_module()
        mock_import.return_value = (mod, None)

        b = NativeSenderBackend()
        cfg = SenderConfig(interface="eth0")
        b.initialize(cfg, _simple_schema(), {"val": 42})

        mod.create_sender.assert_called_once()
        # The interface should be resolved to the pcap device name
        call_args = mod.create_sender.call_args[0][0]
        assert call_args["interface"] == "\\Device\\NPF_eth0"

    @patch("sender.backends.native_backend._try_import_native")
    def test_full_lifecycle(self, mock_import):
        mod = self._make_mock_module()
        mock_import.return_value = (mod, None)

        b = NativeSenderBackend()
        cfg = SenderConfig(interface="eth0")
        b.initialize(cfg, _simple_schema(), {"val": 42})

        metrics = b.start()
        assert metrics.packets_sent == 10
        assert metrics.bytes_sent == 500
        assert not b.is_running()

    @patch("sender.backends.native_backend._try_import_native")
    def test_stop_calls_module(self, mock_import):
        mod = self._make_mock_module()
        mock_import.return_value = (mod, None)

        b = NativeSenderBackend()
        cfg = SenderConfig(interface="eth0")
        b.initialize(cfg, _simple_schema())
        b.stop()
        mod.stop_sender.assert_called_once()

    @patch("sender.backends.native_backend._try_import_native")
    def test_progress_callback_fired(self, mock_import):
        mod = self._make_mock_module()
        mock_import.return_value = (mod, None)

        b = NativeSenderBackend()
        cfg = SenderConfig(interface="eth0")
        b.initialize(cfg, _simple_schema())

        updates = []
        b.start(on_progress=lambda m: updates.append(m))
        assert len(updates) == 1
        assert updates[0].packets_sent == 10


# ===========================================================================
# Import failure handling
# ===========================================================================


class TestNativeImportFailure:
    def test_validate_environment_reports_error(self):
        if is_native_available():
            pytest.skip("Native module is installed")
        errors = NativeSenderBackend.validate_environment()
        assert len(errors) >= 1

    def test_is_native_available_false(self):
        if is_native_available():
            pytest.skip("Native module is installed")
        assert not is_native_available()

    def test_backend_name_always_works(self):
        # Even without native module, the class method should work
        assert NativeSenderBackend.get_backend_name() == "Native (Rust/C++)"


# ===========================================================================
# RANDOM mode is now supported
# ===========================================================================


class TestRandomModeAllowed:
    """Native backend must pass RANDOM mode through to the Rust backend."""

    @patch("sender.backends.native_backend._try_import_native")
    def test_initialize_random_mode_succeeds(self, mock_import):
        mod = MagicMock()
        mod.create_sender.return_value = 12345
        mod.is_transport_available.return_value = True
        mod.list_interfaces.return_value = [("\\Device\\NPF_eth0", "eth0")]
        mock_import.return_value = (mod, None)

        b = NativeSenderBackend()
        cfg = SenderConfig(
            interface="eth0",
            generation_mode=GenerationMode.RANDOM,
        )
        b.initialize(cfg, _simple_schema(), {"val": 42})

        # create_sender SHOULD be called — RANDOM is handled by the Rust PayloadPool
        mod.create_sender.assert_called_once()

    @patch("sender.backends.native_backend._try_import_native")
    def test_fixed_mode_still_works(self, mock_import):
        mod = MagicMock()
        mod.create_sender.return_value = 12345
        mod.is_transport_available.return_value = True
        mod.list_interfaces.return_value = [("\\Device\\NPF_eth0", "eth0")]
        mock_import.return_value = (mod, None)

        b = NativeSenderBackend()
        cfg = SenderConfig(
            interface="eth0",
            generation_mode=GenerationMode.FIXED,
        )
        b.initialize(cfg, _simple_schema(), {"val": 42})
        mod.create_sender.assert_called_once()


# ===========================================================================
# destroy_sender cleanup
# ===========================================================================


class TestDestroyCleanup:
    """Verify that destroy_sender is called when start() finishes."""

    def _make_mock_module(self):
        mod = MagicMock()
        mod.create_sender.return_value = 99999
        mod.start_sender.return_value = {
            "packets_attempted": 5,
            "packets_sent": 5,
            "packets_failed": 0,
            "bytes_sent": 200,
            "first_tx_timestamp_ns": 50,
            "last_tx_timestamp_ns": 100,
        }
        mod.is_transport_available.return_value = True
        mod.list_interfaces.return_value = [("\\Device\\NPF_eth0", "eth0")]
        return mod

    @patch("sender.backends.native_backend._try_import_native")
    def test_destroy_called_after_start(self, mock_import):
        mod = self._make_mock_module()
        mock_import.return_value = (mod, None)

        b = NativeSenderBackend()
        cfg = SenderConfig(interface="eth0")
        b.initialize(cfg, _simple_schema(), {"val": 1})
        b.start()

        mod.destroy_sender.assert_called_once_with(99999)
        # Handle should be cleared
        assert b._handle is None

    @patch("sender.backends.native_backend._try_import_native")
    def test_destroy_called_even_on_start_error(self, mock_import):
        mod = self._make_mock_module()
        mod.start_sender.side_effect = RuntimeError("send failure")
        mock_import.return_value = (mod, None)

        b = NativeSenderBackend()
        cfg = SenderConfig(interface="eth0")
        b.initialize(cfg, _simple_schema(), {"val": 1})

        with pytest.raises(RuntimeError, match="send failure"):
            b.start()

        # destroy should still be called (in finally block)
        mod.destroy_sender.assert_called_once_with(99999)
        assert b._handle is None


# ===========================================================================
# reset_native_cache
# ===========================================================================


class TestResetNativeCache:
    def test_reset_clears_state(self):
        reset_native_cache()
        # After reset, is_native_available should re-attempt import
        # (it won't find the module, but the cache is cleared)
        result = is_native_available()
        assert isinstance(result, bool)


# ===========================================================================
# Config dict completeness
# ===========================================================================


class TestFlattenConfigCompleteness:
    """Ensure flatten_config_for_native produces all keys expected by Rust."""

    EXPECTED_KEYS = {
        "interface",
        "dst_mac",
        "src_mac",
        "ethertype",
        "stream_id",
        "pps",
        "packet_count",
        "duration_sec",
        "generation_mode",
        "fields",
        "fixed_values",
    }

    def test_all_expected_keys_present(self):
        cfg = SenderConfig(interface="eth0")
        result = flatten_config_for_native(cfg, _simple_schema(), {"val": 0})
        assert set(result.keys()) == self.EXPECTED_KEYS

    def test_mac_addresses_normalized(self):
        cfg = SenderConfig(
            interface="eth0",
            dst_mac="AA-BB-CC-DD-EE-FF",
            src_mac="11:22:33:44:55:66",
        )
        result = flatten_config_for_native(cfg, _simple_schema(), {"val": 0})
        assert result["dst_mac"] == "aa:bb:cc:dd:ee:ff"
        assert result["src_mac"] == "11:22:33:44:55:66"

    def test_fields_have_required_keys(self):
        cfg = SenderConfig(interface="eth0")
        result = flatten_config_for_native(cfg, _multi_field_schema(), {
            "id": 1, "label": "test", "flag": True,
        })
        for f in result["fields"]:
            assert set(f.keys()) == {"name", "type", "bit_length"}
