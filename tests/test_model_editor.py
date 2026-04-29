"""Tests for builder.model_editor."""

import pytest

from common.enums import FieldType
from common.exceptions import BuilderOperationError
from common.schema_models import FieldSchema, HeaderSchema, PacketSchema
from builder.model_editor import (
    add_field,
    add_header,
    create_empty_packet,
    get_all_fields,
    get_all_headers,
    move_field_down,
    move_field_up,
    move_header_down,
    move_header_up,
    move_subheader_down,
    move_subheader_up,
    remove_field,
    remove_header,
    update_field,
    update_header,
    update_packet,
)


class TestCreateEmptyPacket:
    def test_valid(self) -> None:
        pkt = create_empty_packet("MyPkt", 64)
        assert pkt.name == "MyPkt"
        assert pkt.declared_total_bit_length == 64
        assert pkt.headers == []

    def test_default_zero(self) -> None:
        pkt = create_empty_packet("P")
        assert pkt.declared_total_bit_length == 0

    def test_empty_name(self) -> None:
        with pytest.raises(BuilderOperationError, match="name"):
            create_empty_packet("", 64)

    def test_negative_bits(self) -> None:
        with pytest.raises(BuilderOperationError, match="totalBitLength"):
            create_empty_packet("P", -1)


class TestAddHeader:
    def test_add_to_packet(self) -> None:
        pkt = create_empty_packet("P", 64)
        h = add_header(pkt, "H1")
        assert h.name == "H1"
        assert len(pkt.headers) == 1

    def test_add_nested(self) -> None:
        pkt = create_empty_packet("P", 64)
        h1 = add_header(pkt, "Outer")
        h2 = add_header(h1, "Inner")
        assert len(h1.subheaders) == 1
        assert h2.name == "Inner"

    def test_duplicate_name(self) -> None:
        pkt = create_empty_packet("P", 64)
        add_header(pkt, "H")
        with pytest.raises(BuilderOperationError, match="Duplicate"):
            add_header(pkt, "H")

    def test_empty_name(self) -> None:
        pkt = create_empty_packet("P", 64)
        with pytest.raises(BuilderOperationError, match="name"):
            add_header(pkt, "")


class TestAddField:
    def test_add(self) -> None:
        pkt = create_empty_packet("P", 64)
        h = add_header(pkt, "H")
        f = add_field(h, "F1", FieldType.INTEGER, 32)
        assert f.name == "F1"
        assert len(h.fields) == 1

    def test_duplicate(self) -> None:
        h = HeaderSchema(name="H")
        add_field(h, "F", FieldType.INTEGER, 8)
        with pytest.raises(BuilderOperationError, match="Duplicate"):
            add_field(h, "F", FieldType.STRING, 8)

    def test_non_aligned(self) -> None:
        h = HeaderSchema(name="H")
        with pytest.raises(BuilderOperationError, match="divisible by 8"):
            add_field(h, "F", FieldType.INTEGER, 7)

    def test_zero_length(self) -> None:
        h = HeaderSchema(name="H")
        with pytest.raises(BuilderOperationError, match="> 0"):
            add_field(h, "F", FieldType.INTEGER, 0)

    def test_empty_name(self) -> None:
        h = HeaderSchema(name="H")
        with pytest.raises(BuilderOperationError, match="name"):
            add_field(h, "", FieldType.INTEGER, 8)

    def test_boolean_must_be_8(self) -> None:
        h = HeaderSchema(name="H")
        with pytest.raises(BuilderOperationError, match="BOOLEAN"):
            add_field(h, "F", FieldType.BOOLEAN, 16)

    def test_boolean_8_ok(self) -> None:
        h = HeaderSchema(name="H")
        f = add_field(h, "F", FieldType.BOOLEAN, 8)
        assert f.bit_length == 8


class TestRemoveHeader:
    def test_remove(self) -> None:
        pkt = create_empty_packet("P", 64)
        add_header(pkt, "H1")
        remove_header(pkt, "H1")
        assert len(pkt.headers) == 0

    def test_not_found(self) -> None:
        pkt = create_empty_packet("P", 64)
        with pytest.raises(BuilderOperationError, match="not found"):
            remove_header(pkt, "X")


class TestRemoveField:
    def test_remove(self) -> None:
        h = HeaderSchema(name="H")
        add_field(h, "F", FieldType.INTEGER, 8)
        remove_field(h, "F")
        assert len(h.fields) == 0

    def test_not_found(self) -> None:
        h = HeaderSchema(name="H")
        with pytest.raises(BuilderOperationError, match="not found"):
            remove_field(h, "X")


class TestUpdatePacket:
    def test_update_name(self) -> None:
        pkt = create_empty_packet("Old", 64)
        update_packet(pkt, name="New")
        assert pkt.name == "New"

    def test_empty_name(self) -> None:
        pkt = create_empty_packet("P", 64)
        with pytest.raises(BuilderOperationError):
            update_packet(pkt, name="")


class TestUpdateHeader:
    def test_rename(self) -> None:
        pkt = create_empty_packet("P", 64)
        h = add_header(pkt, "Old")
        update_header(pkt, h, name="New")
        assert h.name == "New"

    def test_rename_duplicate(self) -> None:
        pkt = create_empty_packet("P", 64)
        add_header(pkt, "A")
        hb = add_header(pkt, "B")
        with pytest.raises(BuilderOperationError, match="Duplicate"):
            update_header(pkt, hb, name="A")


class TestUpdateField:
    def test_update_all(self) -> None:
        h = HeaderSchema(name="H")
        f = add_field(h, "F", FieldType.INTEGER, 8)
        update_field(h, f, name="X", field_type=FieldType.STRING, bit_length=16)
        assert f.name == "X"
        assert f.type is FieldType.STRING
        assert f.bit_length == 16

    def test_update_duplicate_name(self) -> None:
        h = HeaderSchema(name="H")
        add_field(h, "A", FieldType.INTEGER, 8)
        fb = add_field(h, "B", FieldType.INTEGER, 8)
        with pytest.raises(BuilderOperationError, match="Duplicate"):
            update_field(h, fb, name="A")

    def test_bad_bit_length(self) -> None:
        h = HeaderSchema(name="H")
        f = add_field(h, "F", FieldType.INTEGER, 8)
        with pytest.raises(BuilderOperationError, match="divisible"):
            update_field(h, f, bit_length=7)

    def test_boolean_autocorrects_bit_length(self) -> None:
        h = HeaderSchema(name="H")
        f = add_field(h, "F", FieldType.INTEGER, 32)
        update_field(h, f, field_type=FieldType.BOOLEAN, bit_length=32)
        assert f.bit_length == 8  # auto-corrected to BOOLEAN_BIT_LENGTH

    def test_change_type_to_boolean_auto_corrects(self) -> None:
        h = HeaderSchema(name="H")
        f = add_field(h, "F", FieldType.INTEGER, 16)
        update_field(h, f, field_type=FieldType.BOOLEAN)
        assert f.bit_length == 8


class TestMoveHeader:
    def test_move_up(self) -> None:
        pkt = create_empty_packet("P", 64)
        add_header(pkt, "A")
        add_header(pkt, "B")
        move_header_up(pkt, "B")
        assert [h.name for h in pkt.headers] == ["B", "A"]

    def test_move_down(self) -> None:
        pkt = create_empty_packet("P", 64)
        add_header(pkt, "A")
        add_header(pkt, "B")
        move_header_down(pkt, "A")
        assert [h.name for h in pkt.headers] == ["B", "A"]

    def test_move_up_already_first(self) -> None:
        pkt = create_empty_packet("P", 64)
        add_header(pkt, "A")
        with pytest.raises(BuilderOperationError, match="already first"):
            move_header_up(pkt, "A")

    def test_move_down_already_last(self) -> None:
        pkt = create_empty_packet("P", 64)
        add_header(pkt, "A")
        with pytest.raises(BuilderOperationError, match="already last"):
            move_header_down(pkt, "A")


class TestMoveSubheader:
    def test_move_subheader_up(self) -> None:
        parent = HeaderSchema(name="P")
        add_header(parent, "S1")
        add_header(parent, "S2")
        move_subheader_up(parent, "S2")
        assert [s.name for s in parent.subheaders] == ["S2", "S1"]

    def test_move_subheader_down(self) -> None:
        parent = HeaderSchema(name="P")
        add_header(parent, "S1")
        add_header(parent, "S2")
        move_subheader_down(parent, "S1")
        assert [s.name for s in parent.subheaders] == ["S2", "S1"]

    def test_move_subheader_up_across_field_in_children_order(self) -> None:
        parent = HeaderSchema(name="P")
        add_header(parent, "S1")
        add_field(parent, "F", FieldType.INTEGER, 8)
        add_header(parent, "S2")

        move_subheader_up(parent, "S2")

        assert [type(c).__name__ for c in parent.children] == ["HeaderSchema", "HeaderSchema", "FieldSchema"]
        assert isinstance(parent.children[0], HeaderSchema) and parent.children[0].name == "S1"
        assert isinstance(parent.children[1], HeaderSchema) and parent.children[1].name == "S2"
        assert isinstance(parent.children[2], FieldSchema) and parent.children[2].name == "F"


class TestMoveField:
    def test_move_up(self) -> None:
        h = HeaderSchema(name="H")
        add_field(h, "A", FieldType.INTEGER, 8)
        add_field(h, "B", FieldType.INTEGER, 8)
        move_field_up(h, "B")
        assert [f.name for f in h.fields] == ["B", "A"]

    def test_move_down(self) -> None:
        h = HeaderSchema(name="H")
        add_field(h, "A", FieldType.INTEGER, 8)
        add_field(h, "B", FieldType.INTEGER, 8)
        move_field_down(h, "A")
        assert [f.name for f in h.fields] == ["B", "A"]

    def test_move_up_first(self) -> None:
        h = HeaderSchema(name="H")
        add_field(h, "A", FieldType.INTEGER, 8)
        with pytest.raises(BuilderOperationError, match="already first"):
            move_field_up(h, "A")

    def test_move_down_last(self) -> None:
        h = HeaderSchema(name="H")
        add_field(h, "A", FieldType.INTEGER, 8)
        with pytest.raises(BuilderOperationError, match="already last"):
            move_field_down(h, "A")

    def test_move_up_across_subheader_one_slot(self) -> None:
        h = HeaderSchema(name="H")
        add_field(h, "A", FieldType.INTEGER, 8)
        add_header(h, "X")
        add_field(h, "B", FieldType.INTEGER, 8)

        move_field_up(h, "B")

        assert [type(c).__name__ for c in h.children] == ["FieldSchema", "FieldSchema", "HeaderSchema"]
        assert isinstance(h.children[0], FieldSchema) and h.children[0].name == "A"
        assert isinstance(h.children[1], FieldSchema) and h.children[1].name == "B"
        assert isinstance(h.children[2], HeaderSchema) and h.children[2].name == "X"


class TestQueryHelpers:
    def test_get_all_fields(self) -> None:
        pkt = create_empty_packet("P", 16)
        h = add_header(pkt, "H")
        add_field(h, "A", FieldType.INTEGER, 8)
        add_field(h, "B", FieldType.INTEGER, 8)
        assert [f.name for f in get_all_fields(pkt)] == ["A", "B"]

    def test_get_all_headers(self) -> None:
        pkt = create_empty_packet("P", 16)
        outer = add_header(pkt, "Outer")
        add_header(outer, "Inner")
        names = [h.name for h in get_all_headers(pkt)]
        assert names == ["Outer", "Inner"]


class TestFailedOperationNoCorruption:
    def test_duplicate_add_does_not_mutate(self) -> None:
        pkt = create_empty_packet("P", 64)
        add_header(pkt, "H")
        with pytest.raises(BuilderOperationError):
            add_header(pkt, "H")
        assert len(pkt.headers) == 1

    def test_failed_field_add_no_mutation(self) -> None:
        h = HeaderSchema(name="H")
        add_field(h, "F", FieldType.INTEGER, 8)
        with pytest.raises(BuilderOperationError):
            add_field(h, "F", FieldType.INTEGER, 16)
        assert len(h.fields) == 1
