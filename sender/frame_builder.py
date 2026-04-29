"""Frame builder: constructs raw Ethernet frames from components.

Supports a *template* mode for FIXED generation where the user-payload
bytes are precomputed once and the per-packet mutable fields (sequence,
tx_timestamp) are patched directly into a byte-array template.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Any

from common.enums import GenerationMode
from common.schema_models import PacketSchema
from common.serializer import (
    build_user_payload,
    generate_packet_values,
)
from common.testgen_header import (
    TESTGEN_HEADER_FORMAT,
    TESTGEN_HEADER_SIZE,
    build_testgen_header,
    current_timestamp_ns,
)

ETHERNET_HEADER_SIZE: int = 14  # 6 dst + 6 src + 2 ethertype

# Offsets within the TestGenHeader for mutable fields (big-endian).
# Format: >HBBIQQI  →  magic(2) version(1) flags(1) stream_id(4) sequence(8) tx_ts(8) payload_len(4)
_TG_SEQUENCE_OFFSET: int = 8   # bytes into TG header
_TG_TIMESTAMP_OFFSET: int = 16  # bytes into TG header


def build_ethernet_header(dst_mac: str, src_mac: str, ethertype: int) -> bytes:
    """Build a 14-byte Ethernet header from normalised MAC strings."""
    dst = bytes.fromhex(dst_mac.replace(":", ""))
    src = bytes.fromhex(src_mac.replace(":", ""))
    return dst + src + struct.pack(">H", ethertype)


@dataclass(frozen=True)
class FrameTemplate:
    """Pre-built frame data for FIXED mode.

    *eth_header*   – 14-byte Ethernet header (static).
    *tg_header*    – 28-byte TestGenHeader template with placeholder seq/ts.
    *user_payload* – Serialised user-payload bytes (static in FIXED mode).

    The *sequence_frame_offset* and *timestamp_frame_offset* fields record
    where in the concatenated frame the mutable 8-byte values live so the
    consumer can patch them in-place via :func:`patch_frame_template`.
    """
    eth_header: bytes
    tg_header: bytes
    user_payload: bytes
    sequence_frame_offset: int
    timestamp_frame_offset: int

    @property
    def template_bytes(self) -> bytes:
        """Full frame bytes with placeholder sequence=0 and timestamp=0."""
        return self.eth_header + self.tg_header + self.user_payload

    @property
    def frame_length(self) -> int:
        return len(self.eth_header) + len(self.tg_header) + len(self.user_payload)


def build_frame_template(
    dst_mac: str,
    src_mac: str,
    ethertype: int,
    stream_id: int,
    user_payload: bytes,
) -> FrameTemplate:
    """Create a :class:`FrameTemplate` for FIXED-mode sending."""
    eth = build_ethernet_header(dst_mac, src_mac, ethertype)
    tg = build_testgen_header(
        stream_id=stream_id,
        sequence=0,
        tx_timestamp_ns=0,
        payload_len=len(user_payload),
    )
    return FrameTemplate(
        eth_header=eth,
        tg_header=tg,
        user_payload=user_payload,
        sequence_frame_offset=ETHERNET_HEADER_SIZE + _TG_SEQUENCE_OFFSET,
        timestamp_frame_offset=ETHERNET_HEADER_SIZE + _TG_TIMESTAMP_OFFSET,
    )


def stamp_frame(template: FrameTemplate, sequence: int, tx_timestamp_ns: int) -> bytes:
    """Return a complete frame from *template* with *sequence* and *tx_timestamp_ns* patched in.

    This avoids full payload reserialization in FIXED mode.
    """
    buf = bytearray(template.template_bytes)
    struct.pack_into(">Q", buf, template.sequence_frame_offset, sequence)
    struct.pack_into(">Q", buf, template.timestamp_frame_offset, tx_timestamp_ns)
    return bytes(buf)


def build_frame_bytes(
    eth_header: bytes,
    stream_id: int,
    sequence: int,
    tx_timestamp_ns: int,
    user_payload: bytes,
) -> bytes:
    """Build a complete frame from individual components (used in RANDOM mode)."""
    tg = build_testgen_header(
        stream_id=stream_id,
        sequence=sequence,
        tx_timestamp_ns=tx_timestamp_ns,
        payload_len=len(user_payload),
    )
    return eth_header + tg + user_payload


def build_fixed_payload(
    schema: PacketSchema,
    fixed_values: dict[str, Any],
) -> bytes:
    """Serialize the user payload once for FIXED mode."""
    values = generate_packet_values(schema, GenerationMode.FIXED, fixed_values)
    return build_user_payload(schema, values)


def build_random_payload(schema: PacketSchema) -> bytes:
    """Serialize a freshly randomised user payload for RANDOM mode."""
    values = generate_packet_values(schema, GenerationMode.RANDOM)
    return build_user_payload(schema, values)
