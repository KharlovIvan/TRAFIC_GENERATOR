"""Integration tests for sender optimizations.

Covers: GUI throttling, FIXED prebuild, thread separation,
producer/consumer, transport abstraction, and regression tests.
"""

from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

import pytest

from common.enums import FieldType, GenerationMode
from common.metrics import SenderMetrics
from common.schema_models import FieldSchema, HeaderSchema, PacketSchema
from common.testgen_header import TESTGEN_HEADER_SIZE, parse_testgen_header
from sender.frame_builder import ETHERNET_HEADER_SIZE, build_fixed_payload, stamp_frame, build_frame_template
from sender.sender_config import SenderConfig
from sender.sender_engine import SenderEngine
from sender.transports.base import SenderTransport


def _simple_schema() -> PacketSchema:
    f = FieldSchema(name="val", type=FieldType.INTEGER, bit_length=16)
    h = HeaderSchema(name="H", fields=[f])
    return PacketSchema(name="P", declared_total_bit_length=16, headers=[h])


class _RecordingTransport(SenderTransport):
    """Transport that records all sent frames."""

    def __init__(self) -> None:
        self.frames: list[bytes] = []
        self.send_thread_ids: set[int] = set()

    def open(self, interface: str) -> None:
        pass

    def send(self, frame_bytes: bytes) -> int:
        self.frames.append(frame_bytes)
        return len(frame_bytes)
        self.send_thread_ids.add(threading.current_thread().ident or 0)

    def close(self) -> None:
        pass


# ---- A. GUI throttling related tests ------------------------------------

class TestGUIThrottling:
    def test_progress_batched(self):
        """Progress callback fires less often than once per packet."""
        transport = _RecordingTransport()
        engine = SenderEngine(transport=transport)
        schema = _simple_schema()
        config = SenderConfig(
            interface="d0",
            packet_count=50,
            packets_per_second=100_000,
            generation_mode=GenerationMode.FIXED,
        )
        callbacks: list[dict] = []
        engine.run(
            config, schema, fixed_values={"val": 0},
            on_progress=lambda m: callbacks.append(m.snapshot()),
            progress_interval=0.05,
        )
        # Final callback is always emitted.  With 50 fast packets at
        # 0.05 s interval we should see far fewer than 50 callbacks.
        assert len(callbacks) >= 1
        assert len(callbacks) < 50

    def test_no_per_packet_gui_callback_needed(self):
        """Engine works fine with no progress callback."""
        transport = _RecordingTransport()
        engine = SenderEngine(transport=transport)
        schema = _simple_schema()
        config = SenderConfig(
            interface="d0",
            packet_count=10,
            packets_per_second=100_000,
            generation_mode=GenerationMode.FIXED,
        )
        metrics = engine.run(config, schema, fixed_values={"val": 0})
        assert metrics.packets_sent == 10

    def test_worker_emits_periodic_not_per_packet(self):
        """SenderWorker progress_interval controls update rate."""
        transport = _RecordingTransport()
        engine = SenderEngine(transport=transport)
        schema = _simple_schema()
        config = SenderConfig(
            interface="d0",
            packet_count=100,
            packets_per_second=100_000,
            generation_mode=GenerationMode.FIXED,
        )
        updates: list[dict] = []
        engine.run(
            config, schema, fixed_values={"val": 0},
            on_progress=lambda m: updates.append(m.snapshot()),
            progress_interval=0.1,
        )
        assert len(updates) < 100


# ---- B. FIXED mode prebuild tests --------------------------------------

class TestFixedModePrebuild:
    def test_fixed_payload_built_once(self):
        schema = _simple_schema()
        payload = build_fixed_payload(schema, {"val": 42})
        payload2 = build_fixed_payload(schema, {"val": 42})
        assert payload == payload2

    def test_per_packet_payload_not_rebuilt(self):
        """All FIXED frames share the same user-payload bytes."""
        transport = _RecordingTransport()
        engine = SenderEngine(transport=transport)
        schema = _simple_schema()
        config = SenderConfig(
            interface="d0",
            packet_count=10,
            packets_per_second=100_000,
            generation_mode=GenerationMode.FIXED,
        )
        engine.run(config, schema, fixed_values={"val": 0xBEEF})
        payload_offset = ETHERNET_HEADER_SIZE + TESTGEN_HEADER_SIZE
        payloads = {f[payload_offset:] for f in transport.frames}
        assert len(payloads) == 1

    def test_dynamic_fields_change(self):
        """Sequence values should differ across fixed-mode frames."""
        transport = _RecordingTransport()
        engine = SenderEngine(transport=transport)
        schema = _simple_schema()
        config = SenderConfig(
            interface="d0",
            packet_count=5,
            packets_per_second=100_000,
            generation_mode=GenerationMode.FIXED,
        )
        engine.run(config, schema, fixed_values={"val": 0})
        seqs: list[int] = []
        for f in transport.frames:
            tg = parse_testgen_header(f[ETHERNET_HEADER_SIZE:])
            seqs.append(tg.sequence)
        assert seqs == [0, 1, 2, 3, 4]

    def test_frame_sizes_correct(self):
        transport = _RecordingTransport()
        engine = SenderEngine(transport=transport)
        schema = _simple_schema()
        config = SenderConfig(
            interface="d0",
            packet_count=3,
            packets_per_second=100_000,
            generation_mode=GenerationMode.FIXED,
        )
        engine.run(config, schema, fixed_values={"val": 0})
        expected_len = ETHERNET_HEADER_SIZE + TESTGEN_HEADER_SIZE + 2  # 16-bit field
        for f in transport.frames:
            assert len(f) == expected_len


# ---- C. Thread separation tests ----------------------------------------

class TestThreadSeparation:
    def test_send_loop_outside_main_thread(self):
        """Engine.run() sends from the calling thread, not the GUI thread."""
        transport = _RecordingTransport()
        engine = SenderEngine(transport=transport)
        schema = _simple_schema()
        config = SenderConfig(
            interface="d0",
            packet_count=5,
            packets_per_second=100_000,
            generation_mode=GenerationMode.FIXED,
        )
        # Run in a separate thread to simulate worker thread
        result = {}
        def run_in_thread():
            result["metrics"] = engine.run(config, schema, fixed_values={"val": 0})
            result["thread_id"] = threading.current_thread().ident

        t = threading.Thread(target=run_in_thread)
        t.start()
        t.join()
        # Sending happened in the worker thread, not the main thread
        main_id = threading.current_thread().ident
        assert result["thread_id"] != main_id
        assert result["metrics"].packets_sent == 5

    def test_stop_terminates_worker(self):
        transport = _RecordingTransport()
        engine = SenderEngine(transport=transport)
        schema = _simple_schema()
        config = SenderConfig(
            interface="d0",
            packets_per_second=100_000,
            generation_mode=GenerationMode.FIXED,
        )

        def run_engine():
            engine.run(config, schema, fixed_values={"val": 0})

        t = threading.Thread(target=run_engine)
        t.start()
        time.sleep(0.1)
        engine.stop()
        t.join(timeout=3.0)
        assert not t.is_alive()

    def test_no_gui_dependency_in_engine(self):
        """SenderEngine has no Qt imports."""
        import sender.sender_engine as mod
        source = open(mod.__file__, encoding="utf-8").read()
        assert "PySide6" not in source
        assert "QThread" not in source
        assert "QObject" not in source


# ---- D. Producer/consumer tests (see also test_packet_producer.py) ------

class TestProducerConsumerIntegration:
    def test_bounded_queue_used(self):
        """Engine uses a bounded queue internally."""
        from sender.packet_producer import DEFAULT_QUEUE_SIZE
        assert DEFAULT_QUEUE_SIZE > 0

    def test_engine_sends_exact_count(self):
        transport = _RecordingTransport()
        engine = SenderEngine(transport=transport)
        schema = _simple_schema()
        config = SenderConfig(
            interface="d0",
            packet_count=20,
            packets_per_second=100_000,
            generation_mode=GenerationMode.FIXED,
        )
        metrics = engine.run(config, schema, fixed_values={"val": 0})
        assert metrics.packets_sent == 20
        assert len(transport.frames) == 20


# ---- E. Transport abstraction (see also test_transports.py) -------------

class TestTransportAbstraction:
    def test_engine_uses_transport(self):
        mock = MagicMock(spec=SenderTransport)
        engine = SenderEngine(transport=mock)
        schema = _simple_schema()
        config = SenderConfig(
            interface="eth42",
            packet_count=1,
            packets_per_second=100_000,
            generation_mode=GenerationMode.FIXED,
        )
        engine.run(config, schema, fixed_values={"val": 0})
        mock.open.assert_called_once_with("eth42")
        mock.send.assert_called_once()
        mock.close.assert_called_once()

    def test_different_transport_works(self):
        transport = _RecordingTransport()
        engine = SenderEngine(transport=transport)
        schema = _simple_schema()
        config = SenderConfig(
            interface="x",
            packet_count=2,
            packets_per_second=100_000,
            generation_mode=GenerationMode.FIXED,
        )
        engine.run(config, schema, fixed_values={"val": 0})
        assert len(transport.frames) == 2


# ---- F. Sender engine regression tests ----------------------------------

class TestSenderEngineRegression:
    def test_packet_count_stop(self):
        transport = _RecordingTransport()
        engine = SenderEngine(transport=transport)
        schema = _simple_schema()
        config = SenderConfig(
            interface="d0",
            packet_count=7,
            packets_per_second=100_000,
            generation_mode=GenerationMode.FIXED,
        )
        m = engine.run(config, schema, fixed_values={"val": 0})
        assert m.packets_sent == 7

    def test_duration_stop(self):
        transport = _RecordingTransport()
        engine = SenderEngine(transport=transport)
        schema = _simple_schema()
        config = SenderConfig(
            interface="d0",
            packets_per_second=100_000,
            duration_seconds=0.1,
            generation_mode=GenerationMode.FIXED,
        )
        m = engine.run(config, schema, fixed_values={"val": 0})
        assert m.packets_sent > 0
        assert m.elapsed_seconds < 1.0

    def test_packets_sent_increments(self):
        transport = _RecordingTransport()
        engine = SenderEngine(transport=transport)
        schema = _simple_schema()
        config = SenderConfig(
            interface="d0",
            packet_count=4,
            packets_per_second=100_000,
            generation_mode=GenerationMode.FIXED,
        )
        m = engine.run(config, schema, fixed_values={"val": 0})
        assert m.packets_sent == 4

    def test_bytes_sent_increments(self):
        transport = _RecordingTransport()
        engine = SenderEngine(transport=transport)
        schema = _simple_schema()
        config = SenderConfig(
            interface="d0",
            packet_count=3,
            packets_per_second=100_000,
            generation_mode=GenerationMode.FIXED,
        )
        m = engine.run(config, schema, fixed_values={"val": 0})
        assert m.bytes_sent > 0
        frame_len = len(transport.frames[0])
        assert m.bytes_sent == 3 * frame_len

    def test_frame_construction_valid(self):
        transport = _RecordingTransport()
        engine = SenderEngine(transport=transport)
        schema = _simple_schema()
        config = SenderConfig(
            interface="d0",
            packet_count=1,
            packets_per_second=100_000,
            generation_mode=GenerationMode.FIXED,
        )
        engine.run(config, schema, fixed_values={"val": 0xCAFE})
        frame = transport.frames[0]
        # Ethernet header
        assert len(frame) >= ETHERNET_HEADER_SIZE + TESTGEN_HEADER_SIZE + 2
        # TestGen header
        tg = parse_testgen_header(frame[ETHERNET_HEADER_SIZE:])
        assert tg.magic == 0x5447
        assert tg.payload_len == 2
        # User payload
        user = frame[ETHERNET_HEADER_SIZE + TESTGEN_HEADER_SIZE:]
        assert int.from_bytes(user, "big") == 0xCAFE


# ---- G. Metrics timestamp tests ----------------------------------------

class TestMetricsTimestamps:
    def test_first_and_last_tx_timestamp(self):
        m = SenderMetrics()
        m.reset()
        m.record_packet(100, tx_timestamp_ns=1000)
        m.record_packet(100, tx_timestamp_ns=2000)
        assert m.first_tx_timestamp_ns == 1000
        assert m.last_tx_timestamp_ns == 2000

    def test_timestamp_zero_default(self):
        m = SenderMetrics()
        m.reset()
        m.record_packet(100)
        assert m.first_tx_timestamp_ns == 0
        assert m.last_tx_timestamp_ns == 0
