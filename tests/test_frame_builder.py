"""Tests for sender.frame_builder."""

from __future__ import annotations

import struct

from common.enums import FieldType, GenerationMode
from common.schema_models import FieldSchema, HeaderSchema, PacketSchema
from common.testgen_header import TESTGEN_HEADER_SIZE, parse_testgen_header
from sender.frame_builder import (
    ETHERNET_HEADER_SIZE,
    build_ethernet_header,
    build_fixed_payload,
    build_frame_bytes,
    build_frame_template,
    build_random_payload,
    stamp_frame,
)


def _simple_schema() -> PacketSchema:
    f = FieldSchema(name="val", type=FieldType.INTEGER, bit_length=16)
    h = HeaderSchema(name="H", fields=[f])
    return PacketSchema(name="P", declared_total_bit_length=16, headers=[h])


class TestBuildEthernetHeader:
    def test_length(self):
        hdr = build_ethernet_header("ff:ff:ff:ff:ff:ff", "00:00:00:00:00:00", 0x88B5)
        assert len(hdr) == ETHERNET_HEADER_SIZE

    def test_dst_src_ethertype(self):
        hdr = build_ethernet_header("aa:bb:cc:dd:ee:ff", "11:22:33:44:55:66", 0x0800)
        assert hdr[:6] == bytes.fromhex("aabbccddeeff")
        assert hdr[6:12] == bytes.fromhex("112233445566")
        assert struct.unpack(">H", hdr[12:14])[0] == 0x0800


class TestFrameTemplate:
    def test_template_length(self):
        schema = _simple_schema()
        payload = build_fixed_payload(schema, {"val": 42})
        tmpl = build_frame_template(
            "ff:ff:ff:ff:ff:ff", "00:00:00:00:00:00", 0x88B5, 1, payload,
        )
        expected = ETHERNET_HEADER_SIZE + TESTGEN_HEADER_SIZE + len(payload)
        assert tmpl.frame_length == expected

    def test_stamp_updates_sequence(self):
        schema = _simple_schema()
        payload = build_fixed_payload(schema, {"val": 99})
        tmpl = build_frame_template(
            "ff:ff:ff:ff:ff:ff", "00:00:00:00:00:00", 0x88B5, 1, payload,
        )
        frame = stamp_frame(tmpl, sequence=7, tx_timestamp_ns=123456)
        # Parse testgen header from frame
        tg_data = frame[ETHERNET_HEADER_SIZE: ETHERNET_HEADER_SIZE + TESTGEN_HEADER_SIZE]
        tg = parse_testgen_header(tg_data)
        assert tg.sequence == 7
        assert tg.tx_timestamp_ns == 123456

    def test_stamp_preserves_payload(self):
        schema = _simple_schema()
        payload = build_fixed_payload(schema, {"val": 0xABCD})
        tmpl = build_frame_template(
            "ff:ff:ff:ff:ff:ff", "00:00:00:00:00:00", 0x88B5, 1, payload,
        )
        frame = stamp_frame(tmpl, sequence=0, tx_timestamp_ns=0)
        payload_in_frame = frame[ETHERNET_HEADER_SIZE + TESTGEN_HEADER_SIZE:]
        assert payload_in_frame == payload

    def test_stamp_length_matches_template(self):
        schema = _simple_schema()
        payload = build_fixed_payload(schema, {"val": 0})
        tmpl = build_frame_template(
            "ff:ff:ff:ff:ff:ff", "00:00:00:00:00:00", 0x88B5, 1, payload,
        )
        frame = stamp_frame(tmpl, sequence=100, tx_timestamp_ns=999)
        assert len(frame) == tmpl.frame_length


class TestBuildFrameBytes:
    def test_length(self):
        eth = build_ethernet_header("ff:ff:ff:ff:ff:ff", "00:00:00:00:00:00", 0x88B5)
        payload = b"\x00\x2A"
        frame = build_frame_bytes(eth, stream_id=1, sequence=0, tx_timestamp_ns=0, user_payload=payload)
        assert len(frame) == ETHERNET_HEADER_SIZE + TESTGEN_HEADER_SIZE + len(payload)


class TestFixedPayloadPrebuilt:
    def test_payload_built_once_and_reusable(self):
        schema = _simple_schema()
        payload = build_fixed_payload(schema, {"val": 42})
        assert isinstance(payload, bytes)
        assert len(payload) == 2  # 16 bits = 2 bytes
        # Build again – should be identical
        payload2 = build_fixed_payload(schema, {"val": 42})
        assert payload == payload2

    def test_random_payload_varies(self):
        schema = _simple_schema()
        payloads = {build_random_payload(schema) for _ in range(20)}
        # With a 16-bit random field, very unlikely all 20 are the same
        assert len(payloads) > 1


class TestFrameSizeConsistency:
    def test_fixed_and_manual_same_size(self):
        schema = _simple_schema()
        payload = build_fixed_payload(schema, {"val": 0})
        eth = build_ethernet_header("ff:ff:ff:ff:ff:ff", "00:00:00:00:00:00", 0x88B5)
        tmpl = build_frame_template(
            "ff:ff:ff:ff:ff:ff", "00:00:00:00:00:00", 0x88B5, 1, payload,
        )
        stamped = stamp_frame(tmpl, sequence=0, tx_timestamp_ns=0)
        manual = build_frame_bytes(eth, 1, 0, 0, payload)
        assert len(stamped) == len(manual)
