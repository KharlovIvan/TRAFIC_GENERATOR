"""Low-level capture engine using Scapy AsyncSniffer."""

from __future__ import annotations

import threading
import time
from typing import Any, Callable

from common.enums import ExportFormat
from common.exceptions import PacketParseError
from common.metrics import ReceiverMetrics
from common.schema_models import PacketSchema
from common.serializer import parse_user_payload
from common.testgen_header import (
    TESTGEN_HEADER_SIZE,
    TESTGEN_MAGIC,
    TESTGEN_VERSION,
    parse_testgen_header,
)
from common.utils import compute_packet_bit_length
from receiver.json_exporter import JsonExporter
from receiver.pcap_recorder import PcapRecorder
from receiver.receiver_config import ReceiverConfig


class ReceiverEngine:
    """Sniffs Ethernet L2 frames, parses them, and exports results."""

    def __init__(self) -> None:
        self._stop_event = threading.Event()
        self.metrics = ReceiverMetrics()
        self._sniffer: Any = None
        self._pcap: PcapRecorder | None = None
        self._json: JsonExporter | None = None

    def stop(self) -> None:
        self._stop_event.set()
        if self._sniffer is not None:
            try:
                self._sniffer.stop()
            except Exception:
                pass

    @property
    def is_stopped(self) -> bool:
        return self._stop_event.is_set()

    def run(
        self,
        config: ReceiverConfig,
        schema: PacketSchema,
        on_progress: Callable[[ReceiverMetrics], None] | None = None,
        on_packet: Callable[[dict[str, object]], None] | None = None,
        progress_interval: float = 0.25,
    ) -> ReceiverMetrics:
        """Run the capture loop.  Blocks until stopped or limit reached."""
        from scapy.all import AsyncSniffer, Ether  # type: ignore[import-untyped]

        self._stop_event.clear()
        self.metrics.reset()

        expected_payload_bytes = compute_packet_bit_length(schema) // 8

        # Open exporters
        if config.export_format in (ExportFormat.PCAP, ExportFormat.PCAP_AND_JSON):
            self._pcap = PcapRecorder()
            self._pcap.start(config.pcap_output_path)  # type: ignore[arg-type]
        if config.export_format in (ExportFormat.JSON, ExportFormat.PCAP_AND_JSON):
            self._json = JsonExporter()
            self._json.start(config.json_output_path)  # type: ignore[arg-type]

        last_progress = time.monotonic()

        def _handle_packet(pkt: Any) -> None:
            nonlocal last_progress

            if self._stop_event.is_set():
                return

            # Check packet limit
            if (
                config.packet_limit is not None
                and self.metrics.packets_received >= config.packet_limit
            ):
                self._stop_event.set()
                return

            rx_ts_ns = time.time_ns()
            frame_bytes = bytes(pkt)
            frame_len = len(frame_bytes)

            # Write raw PCAP regardless of parse outcome
            if self._pcap is not None:
                self._pcap.write(pkt)

            # Parse Ethernet layer
            eth_dst = pkt.dst if hasattr(pkt, "dst") else "?"
            eth_src = pkt.src if hasattr(pkt, "src") else "?"
            eth_type = pkt.type if hasattr(pkt, "type") else 0

            record: dict[str, object] = {
                "rx_timestamp_ns": rx_ts_ns,
                "ethernet": {
                    "dst_mac": eth_dst,
                    "src_mac": eth_src,
                    "ethertype": f"0x{eth_type:04X}",
                    "frame_len_bytes": frame_len,
                },
                "testgen_header": None,
                "payload": None,
                "valid": False,
                "error": None,
            }

            valid = False
            stream_id: int | None = None
            sequence: int | None = None

            try:
                raw_after_eth = bytes(pkt.payload) if hasattr(pkt, "payload") else frame_bytes[14:]
                if len(raw_after_eth) < TESTGEN_HEADER_SIZE:
                    raise PacketParseError(
                        f"Frame too short for TestGenHeader: {len(raw_after_eth)} bytes"
                    )

                tg = parse_testgen_header(raw_after_eth)
                if tg.magic != TESTGEN_MAGIC:
                    raise PacketParseError(
                        f"Invalid magic: 0x{tg.magic:04X} (expected 0x{TESTGEN_MAGIC:04X})"
                    )
                if tg.version != TESTGEN_VERSION:
                    raise PacketParseError(
                        f"Unsupported version: {tg.version} (expected {TESTGEN_VERSION})"
                    )

                record["testgen_header"] = {
                    "magic": tg.magic,
                    "version": tg.version,
                    "flags": tg.flags,
                    "stream_id": tg.stream_id,
                    "sequence": tg.sequence,
                    "tx_timestamp_ns": tg.tx_timestamp_ns,
                    "payload_len": tg.payload_len,
                }
                stream_id = tg.stream_id
                sequence = tg.sequence

                user_payload_raw = raw_after_eth[TESTGEN_HEADER_SIZE:
                                                 TESTGEN_HEADER_SIZE + tg.payload_len]
                if len(user_payload_raw) < expected_payload_bytes:
                    raise PacketParseError(
                        f"Truncated user payload: got {len(user_payload_raw)}, "
                        f"expected {expected_payload_bytes}"
                    )

                parsed = parse_user_payload(schema, user_payload_raw[:expected_payload_bytes])
                record["payload"] = parsed
                record["valid"] = True
                valid = True

            except (PacketParseError, ValueError, Exception) as exc:
                record["error"] = str(exc)

            self.metrics.record_packet(
                frame_len, rx_ts_ns, valid, stream_id, sequence
            )

            if self._json is not None:
                self._json.write(record)

            if on_packet is not None:
                on_packet(record)

            now = time.monotonic()
            if on_progress and (now - last_progress) >= progress_interval:
                on_progress(self.metrics)
                last_progress = now

        ethertype = config.ethertype
        lfilter = lambda pkt: (hasattr(pkt, "type") and pkt.type == ethertype)

        try:
            self._sniffer = AsyncSniffer(
                iface=config.interface_name,
                prn=_handle_packet,
                lfilter=lfilter,
                store=False,
            )
            self._sniffer.start()

            # Block until stop or duration
            while not self._stop_event.is_set():
                if (
                    config.duration_sec is not None
                    and self.metrics.elapsed_seconds >= config.duration_sec
                ):
                    break
                if (
                    config.packet_limit is not None
                    and self.metrics.packets_received >= config.packet_limit
                ):
                    break
                self._stop_event.wait(0.1)

            self._sniffer.stop()
        except Exception:
            if self._sniffer is not None:
                try:
                    self._sniffer.stop()
                except Exception:
                    pass
                raise
        finally:
            if self._pcap is not None:
                self._pcap.stop()
                self._pcap = None
            if self._json is not None:
                self._json.stop()
                self._json = None

        if on_progress:
            on_progress(self.metrics)

        return self.metrics
