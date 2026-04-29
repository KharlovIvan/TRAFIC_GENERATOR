"""Packet producer: fills a bounded queue with ready-to-send frames.

The producer runs in its own thread and prepares frames ahead of the
consumer (send loop), decoupling payload generation from transmission.
"""

from __future__ import annotations

import queue
import threading
from dataclasses import dataclass
from typing import Any

from common.enums import GenerationMode
from common.schema_models import PacketSchema
from common.testgen_header import current_timestamp_ns
from sender.frame_builder import (
    FrameTemplate,
    build_ethernet_header,
    build_fixed_payload,
    build_frame_bytes,
    build_frame_template,
    build_random_payload,
    stamp_frame,
)
from sender.sender_config import SenderConfig

# Sentinel placed into the queue to signal the consumer that no more
# items will be produced.
_SENTINEL: None = None

# Default bounded-queue capacity.
DEFAULT_QUEUE_SIZE: int = 512


@dataclass(frozen=True)
class ProducedFrame:
    """A frame ready for the consumer to send."""
    sequence: int
    frame_bytes: bytes
    frame_length: int


class PacketProducer:
    """Produces :class:`ProducedFrame` items into a bounded queue.

    In **FIXED** mode the user payload and Ethernet header are computed
    once; each produced item only patches sequence and tx_timestamp into
    the prebuilt template.

    In **RANDOM** mode a fresh payload is generated for every frame.
    """

    def __init__(
        self,
        config: SenderConfig,
        schema: PacketSchema,
        fixed_values: dict[str, Any] | None,
        out_queue: queue.Queue[ProducedFrame | None],
        stop_event: threading.Event,
        *,
        packet_limit: int = 0,
    ) -> None:
        self._config = config
        self._schema = schema
        self._fixed_values = fixed_values
        self._queue = out_queue
        self._stop = stop_event
        self._packet_limit = packet_limit

        dst_mac = SenderConfig.normalize_mac(config.dst_mac)
        src_mac = SenderConfig.normalize_mac(config.src_mac)

        self._eth_header = build_ethernet_header(dst_mac, src_mac, config.ethertype)
        self._template: FrameTemplate | None = None

        if config.generation_mode is GenerationMode.FIXED:
            payload = build_fixed_payload(schema, fixed_values or {})
            self._template = build_frame_template(
                dst_mac, src_mac, config.ethertype, config.stream_id, payload,
            )

    def run(self) -> None:
        """Produce frames until stopped or packet limit reached.

        Blocks on ``queue.put()`` when the queue is full, providing
        natural back-pressure.  Places a sentinel ``None`` when done.
        """
        try:
            self._produce_loop()
        finally:
            # Signal consumer that production is over.
            try:
                self._queue.put(_SENTINEL, timeout=0.2)
            except queue.Full:
                pass

    def _produce_loop(self) -> None:
        seq = 0
        is_fixed = self._config.generation_mode is GenerationMode.FIXED

        while not self._stop.is_set():
            if self._packet_limit > 0 and seq >= self._packet_limit:
                break

            ts = current_timestamp_ns()

            if is_fixed and self._template is not None:
                frame = stamp_frame(self._template, seq, ts)
                length = self._template.frame_length
            else:
                payload = build_random_payload(self._schema)
                frame = build_frame_bytes(
                    self._eth_header,
                    self._config.stream_id,
                    seq,
                    ts,
                    payload,
                )
                length = len(frame)

            item = ProducedFrame(sequence=seq, frame_bytes=frame, frame_length=length)
            try:
                self._queue.put(item, timeout=0.1)
            except queue.Full:
                if self._stop.is_set():
                    break
                continue

            seq += 1
