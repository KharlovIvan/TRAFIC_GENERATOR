"""Integration test – build payload then verify via header + parsing."""

from __future__ import annotations

from common.enums import FieldType, GenerationMode
from common.schema_models import FieldSchema, HeaderSchema, PacketSchema
from common.serializer import build_user_payload, generate_packet_values
from common.testgen_header import (
    TESTGEN_HEADER_SIZE,
    build_testgen_header,
    current_timestamp_ns,
    parse_testgen_header,
)


def _make_schema() -> PacketSchema:
    fields = [
        FieldSchema(name="seq_no", type=FieldType.INTEGER, bit_length=32),
        FieldSchema(name="flag", type=FieldType.BOOLEAN, bit_length=8),
        FieldSchema(name="tag", type=FieldType.STRING, bit_length=32),
        FieldSchema(name="raw", type=FieldType.RAW_BYTES, bit_length=16),
    ]
    hdr = HeaderSchema(name="Main", fields=fields)
    total = sum(f.bit_length for f in fields)
    return PacketSchema(name="RoundTrip", declared_total_bit_length=total, headers=[hdr])


class TestPayloadRoundTrip:
    def test_fixed_payload_matches_expected(self):
        schema = _make_schema()
        values = {
            "seq_no": 1,
            "flag": True,
            "tag": "AB",
            "raw": b"\xfe\xed",
        }
        payload = build_user_payload(schema, values)
        # 4 + 1 + 4 + 2 = 11 bytes
        assert len(payload) == 11
        # Verify each field
        assert int.from_bytes(payload[0:4], "big") == 1
        assert payload[4:5] == b"\x01"
        assert payload[5:9] == b"AB\x00\x00"
        assert payload[9:11] == b"\xfe\xed"

    def test_header_plus_payload_round_trip(self):
        schema = _make_schema()
        values = generate_packet_values(
            schema, GenerationMode.FIXED,
            {"seq_no": 42, "flag": False, "tag": "XY", "raw": b"\x00\x01"},
        )
        payload = build_user_payload(schema, values)
        ts = current_timestamp_ns()
        hdr_bytes = build_testgen_header(
            stream_id=7, sequence=100, tx_timestamp_ns=ts, payload_len=len(payload)
        )
        frame_data = hdr_bytes + payload

        # Parse header back
        parsed = parse_testgen_header(frame_data)
        assert parsed.stream_id == 7
        assert parsed.sequence == 100
        assert parsed.tx_timestamp_ns == ts
        assert parsed.payload_len == len(payload)

        # Extract payload from frame
        extracted = frame_data[TESTGEN_HEADER_SIZE:]
        assert extracted == payload

    def test_random_mode_produces_valid_payload(self):
        schema = _make_schema()
        values = generate_packet_values(schema, GenerationMode.RANDOM)
        payload = build_user_payload(schema, values)
        assert len(payload) == 11  # 4+1+4+2
