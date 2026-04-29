"""Sender engine: producer/consumer architecture with transport abstraction."""

from __future__ import annotations

import queue
import threading
import time
from typing import Any, Callable

from common.enums import GenerationMode
from common.metrics import SenderMetrics
from common.schema_models import PacketSchema
from common.testgen_header import current_timestamp_ns
from sender.frame_builder import (
    build_ethernet_header,
    build_fixed_payload,
    build_frame_template,
    stamp_frame,
    build_frame_bytes,
    build_random_payload,
)
from sender.packet_producer import (
    DEFAULT_QUEUE_SIZE,
    PacketProducer,
    ProducedFrame,
)
from sender.sender_config import SenderConfig
from sender.transports.base import SenderTransport
from sender.transports.scapy_transport import ScapySenderTransport


class SenderEngine:
    """Builds and sends Ether / TestGenHeader / UserPayload frames.

    Uses a producer thread to prepare frames into a bounded queue and a
    consumer loop (running in the caller's thread) that sends them via a
    :class:`SenderTransport`.
    """

    def __init__(self, transport: SenderTransport | None = None) -> None:
        self._stop_event = threading.Event()
        self.metrics = SenderMetrics()
        self._transport = transport or ScapySenderTransport()
        self._producer_thread: threading.Thread | None = None

    @property
    def transport(self) -> SenderTransport:
        return self._transport

    def stop(self) -> None:
        """Request the send loop to stop."""
        self._stop_event.set()

    @property
    def is_stopped(self) -> bool:
        return self._stop_event.is_set()

    def run(
        self,
        config: SenderConfig,
        schema: PacketSchema,
        fixed_values: dict[str, Any] | None = None,
        on_progress: Callable[[SenderMetrics], None] | None = None,
        progress_interval: float = 0.25,
    ) -> SenderMetrics:
        """Run the send loop.  Blocks until stop or limit reached."""
        self._stop_event.clear()
        self.metrics.reset()

        frame_queue: queue.Queue[ProducedFrame | None] = queue.Queue(
            maxsize=DEFAULT_QUEUE_SIZE,
        )

        producer = PacketProducer(
            config=config,
            schema=schema,
            fixed_values=fixed_values,
            out_queue=frame_queue,
            stop_event=self._stop_event,
            packet_limit=config.packet_count,
        )

        self._producer_thread = threading.Thread(
            target=producer.run, name="packet-producer", daemon=True,
        )
        self._producer_thread.start()

        try:
            self._transport.open(config.interface)
            self._consume_loop(config, frame_queue, on_progress, progress_interval)
        finally:
            self._stop_event.set()
            # Drain residual items so the producer can place its sentinel
            # and exit without blocking on a full queue.
            while not frame_queue.empty():
                try:
                    frame_queue.get_nowait()
                except queue.Empty:
                    break
            if self._producer_thread is not None:
                self._producer_thread.join(timeout=2.0)
            self._transport.close()

        # Final progress
        if on_progress:
            on_progress(self.metrics)

        return self.metrics

    def _consume_loop(
        self,
        config: SenderConfig,
        frame_queue: queue.Queue[ProducedFrame | None],
        on_progress: Callable[[SenderMetrics], None] | None,
        progress_interval: float,
    ) -> None:
        """Drain the queue, send each frame, and handle pacing."""
        interval = 1.0 / config.packets_per_second
        last_progress = time.monotonic()
        packets_consumed = 0
        _consecutive_failures = 0
        _MAX_CONSECUTIVE_FAILURES = 50

        while not self._stop_event.is_set():
            # Duration stop condition
            if (
                config.duration_seconds > 0
                and self.metrics.elapsed_seconds >= config.duration_seconds
            ):
                break

            try:
                item = frame_queue.get(timeout=0.05)
            except queue.Empty:
                continue

            if item is None:
                # Producer finished.
                break

            self.metrics.record_send_attempt()
            try:
                bytes_sent = self._transport.send(item.frame_bytes)
                self.metrics.record_packet(bytes_sent, tx_timestamp_ns=current_timestamp_ns())
                _consecutive_failures = 0
            except Exception:
                self.metrics.record_send_failure()
                _consecutive_failures += 1
                if _consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
                    break

            packets_consumed += 1

            # Periodic progress
            now = time.monotonic()
            if on_progress and (now - last_progress) >= progress_interval:
                on_progress(self.metrics)
                last_progress = now

            # Pacing
            expected = self.metrics.start_time + packets_consumed * interval
            sleep_time = expected - time.monotonic()
            if sleep_time > 0:
                self._stop_event.wait(sleep_time)
