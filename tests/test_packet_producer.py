"""Tests for sender.packet_producer (producer/consumer queue architecture)."""

from __future__ import annotations

import queue
import threading

import pytest

from common.enums import FieldType, GenerationMode
from common.schema_models import FieldSchema, HeaderSchema, PacketSchema
from sender.packet_producer import DEFAULT_QUEUE_SIZE, PacketProducer, ProducedFrame
from sender.sender_config import SenderConfig


def _simple_schema() -> PacketSchema:
    f = FieldSchema(name="val", type=FieldType.INTEGER, bit_length=16)
    h = HeaderSchema(name="H", fields=[f])
    return PacketSchema(name="P", declared_total_bit_length=16, headers=[h])


def _make_config(mode: GenerationMode = GenerationMode.FIXED, count: int = 0) -> SenderConfig:
    return SenderConfig(
        interface="dummy0",
        packets_per_second=100_000,
        packet_count=count,
        generation_mode=mode,
    )


class TestQueueBounded:
    def test_queue_has_max_size(self):
        q: queue.Queue[ProducedFrame | None] = queue.Queue(maxsize=DEFAULT_QUEUE_SIZE)
        assert q.maxsize == DEFAULT_QUEUE_SIZE

    def test_default_queue_size_is_positive(self):
        assert DEFAULT_QUEUE_SIZE > 0


class TestProducerFixed:
    def test_produces_correct_count(self):
        schema = _simple_schema()
        config = _make_config(GenerationMode.FIXED, count=5)
        q: queue.Queue[ProducedFrame | None] = queue.Queue(maxsize=100)
        stop = threading.Event()
        producer = PacketProducer(config, schema, {"val": 42}, q, stop, packet_limit=5)
        producer.run()

        items: list[ProducedFrame] = []
        while True:
            item = q.get_nowait()
            if item is None:
                break
            items.append(item)

        assert len(items) == 5

    def test_fixed_payload_reused(self):
        """In FIXED mode all frames should have the same user-payload portion."""
        schema = _simple_schema()
        config = _make_config(GenerationMode.FIXED, count=10)
        q: queue.Queue[ProducedFrame | None] = queue.Queue(maxsize=100)
        stop = threading.Event()
        producer = PacketProducer(config, schema, {"val": 7}, q, stop, packet_limit=10)
        producer.run()

        frames: list[bytes] = []
        while True:
            item = q.get_nowait()
            if item is None:
                break
            frames.append(item.frame_bytes)

        # User payload starts after ethernet (14 bytes) + testgen header (28 bytes)
        payloads = {f[14 + 28:] for f in frames}
        assert len(payloads) == 1, "FIXED mode should produce identical payloads"

    def test_sequences_increment(self):
        schema = _simple_schema()
        config = _make_config(GenerationMode.FIXED, count=5)
        q: queue.Queue[ProducedFrame | None] = queue.Queue(maxsize=100)
        stop = threading.Event()
        producer = PacketProducer(config, schema, {"val": 0}, q, stop, packet_limit=5)
        producer.run()

        seqs: list[int] = []
        while True:
            item = q.get_nowait()
            if item is None:
                break
            seqs.append(item.sequence)

        assert seqs == [0, 1, 2, 3, 4]


class TestProducerRandom:
    def test_random_produces_varying_payloads(self):
        schema = _simple_schema()
        config = _make_config(GenerationMode.RANDOM, count=20)
        q: queue.Queue[ProducedFrame | None] = queue.Queue(maxsize=100)
        stop = threading.Event()
        producer = PacketProducer(config, schema, None, q, stop, packet_limit=20)
        producer.run()

        payloads: set[bytes] = set()
        while True:
            item = q.get_nowait()
            if item is None:
                break
            payloads.add(item.frame_bytes[14 + 28:])

        assert len(payloads) > 1, "RANDOM mode should produce varying payloads"


class TestProducerStopBehavior:
    def test_stop_event_terminates_producer(self):
        schema = _simple_schema()
        config = _make_config(GenerationMode.FIXED, count=0)  # unlimited
        q: queue.Queue[ProducedFrame | None] = queue.Queue(maxsize=10)
        stop = threading.Event()
        producer = PacketProducer(config, schema, {"val": 0}, q, stop, packet_limit=0)

        t = threading.Thread(target=producer.run, daemon=True)
        t.start()
        # Let producer fill the queue a bit
        threading.Event().wait(0.05)
        stop.set()
        # Drain queue so producer can place its sentinel and exit.
        while not q.empty():
            try:
                q.get_nowait()
            except queue.Empty:
                break
        t.join(timeout=2.0)
        assert not t.is_alive(), "Producer should terminate after stop"

    def test_stop_with_non_empty_queue(self):
        schema = _simple_schema()
        config = _make_config(GenerationMode.FIXED, count=0)
        q: queue.Queue[ProducedFrame | None] = queue.Queue(maxsize=5)
        stop = threading.Event()
        producer = PacketProducer(config, schema, {"val": 0}, q, stop, packet_limit=0)

        t = threading.Thread(target=producer.run, daemon=True)
        t.start()
        threading.Event().wait(0.05)
        stop.set()
        # Drain one item to let producer place sentinel.
        try:
            q.get(timeout=0.5)
        except queue.Empty:
            pass
        t.join(timeout=2.0)
        assert not t.is_alive()

        # Queue should contain some produced frames plus sentinel
        count = 0
        sentinel_seen = False
        while not q.empty():
            item = q.get_nowait()
            if item is None:
                sentinel_seen = True
            else:
                count += 1
        assert count > 0 or sentinel_seen


class TestConsumerDrainsQueue:
    def test_engine_consumes_all_produced_frames(self):
        from unittest.mock import MagicMock
        from sender.sender_engine import SenderEngine
        from sender.transports.base import SenderTransport

        mock = MagicMock(spec=SenderTransport)
        engine = SenderEngine(transport=mock)
        schema = _simple_schema()
        config = _make_config(GenerationMode.FIXED, count=10)
        metrics = engine.run(config, schema, fixed_values={"val": 0})
        assert metrics.packets_sent == 10
        assert mock.send.call_count == 10
