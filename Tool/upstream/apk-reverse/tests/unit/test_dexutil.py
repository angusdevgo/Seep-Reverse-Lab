"""Unit tests for skills/apk-reverse/scripts/dexutil.py.

The dex format table is the one place where a wrong entry silently shifts every
offset after it, so widths are asserted opcode by opcode against the cases the
script's own docstring calls out. No device and no sample file are needed for
the table itself; the sample-backed assertions skip when the git-ignored bench
tree is absent.
"""
from __future__ import annotations

import hashlib
import zlib

import pytest

from conftest import load_script, require_path

dexutil = load_script("dexutil.py")

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------- #
# little-endian scalar readers
# --------------------------------------------------------------------------- #
class TestScalarReaders:
    def test_u16_and_u32_are_little_endian(self):
        assert dexutil.u16(b"\x01\x02", 0) == 0x0201
        assert dexutil.u32(b"\x01\x02\x03\x04", 0) == 0x04030201

    def test_u16_and_u32_read_from_an_offset(self):
        buf = b"\xff\xff\x34\x12\x78\x56\x34\x12"
        assert dexutil.u16(buf, 2) == 0x1234
        assert dexutil.u32(buf, 4) == 0x12345678

    @pytest.mark.parametrize("value,expected", [
        (0x0000, 0),
        (0x7FFF, 0x7FFF),
        (0x8000, -0x8000),
        (0xFFFF, -1),
    ])
    def test_s16_boundaries(self, value, expected):
        assert dexutil.s16(value) == expected

    def test_read_uleb_single_byte(self):
        assert dexutil.read_uleb(b"\x7f", 0) == (0x7F, 1)

    def test_read_uleb_two_bytes_and_offset(self):
        value, off = dexutil.read_uleb(b"\x00\x80\x01", 1)
        assert value == 128
        assert off == 3

    def test_read_uleb_multi_byte(self):
        # 0xE5 0x8E 0x26 -> 624485, the example from the format specification
        value, off = dexutil.read_uleb(b"\xe5\x8e\x26", 0)
        assert value == 624485
        assert off == 3


# --------------------------------------------------------------------------- #
# instruction width table
# --------------------------------------------------------------------------- #
# Each case is a trap the module docstring names explicitly.
WIDTH_CASES = [
    (0x00, 1, "plain nop is one unit"),
    (0x02, 2, "move/from16"),
    (0x03, 3, "move/16"),
    (0x13, 2, "const/16"),
    (0x14, 3, "const"),
    (0x16, 2, "const-wide/16"),
    (0x17, 3, "const-wide/32"),
    (0x18, 5, "const-wide"),
    (0x1A, 2, "const-string (21c) carries a 16-bit index"),
    (0x1B, 3, "const-string/jumbo (31c) carries a 32-bit index"),
    (0x1C, 2, "const-class"),
    (0x1E, 1, "monitor-exit breaks the same-family reading"),
    (0x20, 2, "instance-of"),
    (0x21, 1, "array-length breaks the same-family reading"),
    (0x27, 1, "throw"),
    (0x28, 1, "goto (10t) is one unit"),
    (0x29, 2, "goto/16 (20t)"),
    (0x2A, 3, "goto/32 (30t)"),
    (0x32, 2, "if-test (22t) is two units, not one"),
    (0x37, 2, "last if-test"),
    (0x38, 2, "if-testz (21t) is two units, not one"),
    (0x3D, 2, "last if-testz"),
    (0x6E, 3, "invoke-kind (35c)"),
    (0x74, 3, "invoke-kind/range (3rc)"),
    (0x7B, 1, "neg-int"),
    (0x90, 2, "add-int (23x)"),
    (0xD0, 2, "add-int/lit16 (22s)"),
    (0xFA, 4, "invoke-polymorphic (45cc)"),
    (0xFC, 3, "invoke-custom (35c)"),
]


class TestInstructionWidths:
    @pytest.mark.parametrize("op,units,why", WIDTH_CASES,
                             ids=["%02x" % c[0] for c in WIDTH_CASES])
    def test_width(self, op, units, why):
        assert dexutil.insn_units(op, b"\x00" * 32, 0, 32) == units, why

    def test_table_and_accessor_agree_for_every_listed_opcode(self):
        """insn_units must not diverge from OP_UNITS for any allocated opcode."""
        buf = b"\x00" * 32
        drifted = []
        for op, units in sorted(dexutil.OP_UNITS.items()):
            got = dexutil.insn_units(op, buf, 0, len(buf))
            if got != units:
                drifted.append((hex(op), units, got))
        assert drifted == []

    @pytest.mark.parametrize("op", [0x3E, 0x43, 0x73, 0x79, 0x7A, 0xE3, 0xF9])
    def test_unallocated_opcodes_still_terminate(self, op):
        """An unlisted opcode must advance by one unit, not run off the end."""
        assert dexutil.insn_units(op, b"\x00" * 8, 0, 8) == 1

    def test_packed_switch_payload_width(self):
        # 00 01 | size=3 -> 4 + 3*2 = 10 units
        buf = bytes([0x00, 0x01]) + (3).to_bytes(2, "little") + b"\x00" * 12
        assert dexutil.insn_units(0x00, buf, 0, len(buf)) == 10

    def test_sparse_switch_payload_width(self):
        # 00 02 | size=3 -> 2 + 3*4 = 14 units
        buf = bytes([0x00, 0x02]) + (3).to_bytes(2, "little") + b"\x00" * 24
        assert dexutil.insn_units(0x00, buf, 0, len(buf)) == 14

    def test_fill_array_data_payload_width(self):
        # 00 03 | element_width=4 | size=30 -> 4 + ceil(30*4/2) = 64 units.
        # The measured case named in the docstring: counting this as 5 units is
        # what desynchronises the rest of the walk.
        buf = bytes([0x00, 0x03]) + (4).to_bytes(2, "little") + (30).to_bytes(4, "little")
        assert dexutil.insn_units(0x00, buf, 0, len(buf)) == 64

    def test_fill_array_data_payload_pads_to_an_even_byte_count(self):
        # element_width=1, size=3 -> 3 bytes pads to 4 -> 4 + 2 = 6 units
        buf = bytes([0x00, 0x03]) + (1).to_bytes(2, "little") + (3).to_bytes(4, "little")
        assert dexutil.insn_units(0x00, buf, 0, len(buf)) == 6

    def test_plain_nop_is_not_treated_as_a_payload(self):
        assert dexutil.insn_units(0x00, b"\x00\x00\x00\x00", 0, 4) == 1


# --------------------------------------------------------------------------- #
# header parsing and the structural check
# --------------------------------------------------------------------------- #
# Verified dex header offsets, as declared by dexutil.OFFSETS. Asserted rather
# than assumed: these are the values a hand-written reader most often gets wrong.
HEADER_OFFSETS = {
    "file_size": 0x20, "header_size": 0x24, "endian_tag": 0x28,
    "map_off": 0x34, "string_ids_off": 0x3C, "type_ids_off": 0x44,
    "proto_ids_off": 0x4C, "field_ids_off": 0x54, "method_ids_off": 0x5C,
    "class_defs_off": 0x64,
}

# The six table pointers dex.check() requires to be inside the file.
TABLE_POINTERS = ("string_ids_off", "type_ids_off", "proto_ids_off",
                  "field_ids_off", "method_ids_off", "class_defs_off")


def synthetic_dex(size=512):
    """A dex-shaped buffer whose header is internally consistent.

    Enough for the structural reader: magic, a matching file_size, and the six
    table pointers inside the file. It is deliberately not a runnable dex, so
    nothing here claims parse-level validity of a real image.
    """
    buf = bytearray(size)

    def put(offset, value, width=4):
        buf[offset:offset + width] = value.to_bytes(width, "little")

    buf[0:8] = b"dex\n035\x00"
    put(HEADER_OFFSETS["file_size"], size)
    put(HEADER_OFFSETS["header_size"], 0x70)
    put(HEADER_OFFSETS["endian_tag"], 0x12345678)
    put(HEADER_OFFSETS["map_off"], 0x70)
    for key in TABLE_POINTERS:
        # size 0, pointer 0x70: every pointer lands inside the file.
        put(HEADER_OFFSETS[key] - 4, 0)
        put(HEADER_OFFSETS[key], 0x70)
    return buf


class TestHeaderParsing:
    def test_the_offset_table_matches_the_format_specification(self):
        for key, expected in HEADER_OFFSETS.items():
            assert dexutil.OFFSETS[key] == expected, key

    def test_header_fields_are_parsed_out_of_the_buffer(self):
        dex = dexutil.Dex(bytes(synthetic_dex(512)))
        assert dex.header["file_size"] == 512
        assert dex.header["header_size"] == 0x70
        assert dex.header["string_ids_off"] == 0x70

    def test_magic_is_parsed(self):
        dex = dexutil.Dex(bytes(synthetic_dex(256)))
        assert dex.d[:4] == b"dex\n"

    def test_consistent_header_reports_no_problems(self):
        dex = dexutil.Dex(bytes(synthetic_dex(512)))
        assert dex.check() == []

    def test_bad_magic_is_reported(self):
        buf = synthetic_dex(512)
        buf[0:4] = b"zip\n"
        assert any("not a dex" in p for p in dexutil.Dex(bytes(buf)).check())

    def test_file_size_mismatch_is_reported(self):
        buf = synthetic_dex(512)
        buf[HEADER_OFFSETS["file_size"]:HEADER_OFFSETS["file_size"] + 4] = \
            (999).to_bytes(4, "little")
        assert any("file_size" in p for p in dexutil.Dex(bytes(buf)).check())

    def test_out_of_range_table_pointer_is_reported(self):
        buf = synthetic_dex(512)
        at = HEADER_OFFSETS["string_ids_off"]
        buf[at:at + 4] = (0).to_bytes(4, "little")
        assert any("string_ids_off" in p for p in dexutil.Dex(bytes(buf)).check())

    def test_string_safe_never_raises_on_a_junk_index(self):
        """A desynced decode passes junk indices; the reader must not throw."""
        dex = dexutil.Dex(bytes(synthetic_dex(512)))
        assert dex.string_safe(10**6).startswith("<string_idx")


# --------------------------------------------------------------------------- #
# branch targets
# --------------------------------------------------------------------------- #
def fake_dex(buf):
    """A Dex instance over raw bytes, without header parsing.

    branch_target needs only self.d plus the instruction dict, so this keeps the
    displacement arithmetic testable without a whole valid dex image.
    """
    dex = dexutil.Dex.__new__(dexutil.Dex)
    dex.d = bytes(buf)
    dex.name = "<synthetic>"
    return dex


def insn_at_zero(buf, op, raw_len):
    return {"off": 0, "op": op, "raw": bytes(buf[:raw_len]),
            "units": raw_len // 2, "name": "synthetic"}


class TestBranchTargets:
    def test_if_testz_negative_displacement(self):
        buf = bytes([0x38, 0x00]) + (-1).to_bytes(2, "little", signed=True)
        assert fake_dex(buf).branch_target(insn_at_zero(buf, 0x38, 4)) == -2

    def test_if_testz_positive_displacement(self):
        buf = bytes([0x3D, 0x01]) + (2).to_bytes(2, "little", signed=True)
        assert fake_dex(buf).branch_target(insn_at_zero(buf, 0x3D, 4)) == 4

    def test_if_test_two_registers(self):
        buf = bytes([0x32, 0x10]) + (-4).to_bytes(2, "little", signed=True)
        assert fake_dex(buf).branch_target(insn_at_zero(buf, 0x32, 4)) == -8

    def test_goto_signed_byte(self):
        # 10t: op, int8. 0xFE -> -2 units -> -4 bytes from the instruction.
        buf = bytes([0x28, 0xFE])
        assert fake_dex(buf).branch_target(insn_at_zero(buf, 0x28, 2)) == -4

    def test_goto16(self):
        buf = bytes([0x29, 0x00]) + (3).to_bytes(2, "little", signed=True)
        assert fake_dex(buf).branch_target(insn_at_zero(buf, 0x29, 4)) == 6

    def test_goto32_negative(self):
        buf = bytes([0x2A, 0x00]) + (-1).to_bytes(4, "little", signed=True)
        assert fake_dex(buf).branch_target(insn_at_zero(buf, 0x2A, 6)) == -2

    def test_non_branch_returns_none(self):
        buf = bytes([0x0E, 0x00])
        assert fake_dex(buf).branch_target(insn_at_zero(buf, 0x0E, 2)) is None

    def test_branch_regs_if_testz_reads_one_register(self):
        buf = bytes([0x38, 0x07]) + (-1).to_bytes(2, "little", signed=True)
        regs, kind = fake_dex(buf).branch_regs(insn_at_zero(buf, 0x38, 4))
        assert regs == [7]
        assert kind == "if-testz"

    def test_branch_regs_if_test_reads_two_registers(self):
        buf = bytes([0x32, 0x21]) + (-1).to_bytes(2, "little", signed=True)
        regs, kind = fake_dex(buf).branch_regs(insn_at_zero(buf, 0x32, 4))
        assert regs == [2, 1]
        assert kind == "if-test"

    def test_branch_regs_is_empty_for_a_non_branch(self):
        buf = bytes([0x0E, 0x00])
        assert fake_dex(buf).branch_regs(insn_at_zero(buf, 0x0E, 2)) == ([], None)


# --------------------------------------------------------------------------- #
# header integrity: signature before checksum
# --------------------------------------------------------------------------- #
class TestHeaderIntegrity:
    def test_fix_then_verify_round_trips(self):
        data = bytearray(synthetic_dex(512))
        dexutil.fix_dex_header(data)
        assert dexutil.verify_dex_header(data) == (True, True)

    def test_signature_covers_the_bytes_after_the_signature_field(self):
        data = bytearray(synthetic_dex(512))
        dexutil.fix_dex_header(data)
        assert bytes(data[12:32]) == hashlib.sha1(bytes(data[32:])).digest()

    def test_checksum_covers_the_signature_field(self):
        """The order requirement: adler32 over d[12:] includes the written signature."""
        data = bytearray(synthetic_dex(512))
        dexutil.fix_dex_header(data)
        stored = int.from_bytes(data[8:12], "little")
        assert stored == zlib.adler32(bytes(data[12:])) & 0xFFFFFFFF

    def test_checksum_taken_over_a_zeroed_signature_does_not_verify(self):
        """The failure mode the module docstring names: the header never verifies."""
        data = bytearray(synthetic_dex(512))
        data[12:32] = b"\x00" * 20
        data[8:12] = (zlib.adler32(bytes(data[12:])) & 0xFFFFFFFF).to_bytes(4, "little")
        data[12:32] = hashlib.sha1(bytes(data[32:])).digest()
        checksum_ok, _signature_ok = dexutil.verify_dex_header(data)
        assert checksum_ok is False

    def test_a_tampered_body_fails_verification(self):
        data = bytearray(synthetic_dex(512))
        dexutil.fix_dex_header(data)
        data[-1] ^= 0xFF
        assert dexutil.verify_dex_header(data) == (False, False)

    def test_fix_reports_before_and_after_values(self):
        data = bytearray(synthetic_dex(512))
        report = dexutil.fix_dex_header(data)
        assert set(report) == {"before_checksum", "after_checksum",
                               "before_signature", "after_signature"}
        assert report["before_checksum"] != report["after_checksum"]


# --------------------------------------------------------------------------- #
# sample-backed assertions (skip when the git-ignored bench tree is absent)
# --------------------------------------------------------------------------- #
SAMPLE_CLASS = "Lsg/vantagepoint/uncrackable1/MainActivity;"
SAMPLE_METHOD = ("onCreate", "(Landroid/os/Bundle;)V")
SAMPLE_SITE = 0x9D0
SAMPLE_SITE_BYTES = "39000e00"


class TestAgainstTheRecordedSample:
    """The l1l3 fixture is git-ignored, so these skip in CI by design."""

    @pytest.fixture(autouse=True)
    def _need_sample(self, bench_l1l3):
        self.dex_path = require_path(
            bench_l1l3 / "dex" / "classes.dex",
            "the l1l3 sample is a download into the git-ignored bench tree")

    def _method(self):
        dex, _entry = dexutil.load_dex(str(self.dex_path))
        found = dex.find_method(SAMPLE_CLASS, *SAMPLE_METHOD)
        assert found, "the recorded fixture must still contain MainActivity.onCreate"
        _section, _idx, code_off = found
        return dex, code_off

    def test_sample_dex_parses_cleanly(self):
        dex, _entry = dexutil.load_dex(str(self.dex_path))
        assert dex.check() == []

    def test_decode_walks_exactly_insns_size_units(self):
        dex, code_off = self._method()
        insns, clean, expected = dex.decode_all(code_off)
        assert clean, "decode did not land on 0x%x" % expected
        assert insns

    def test_the_recorded_root_check_branch_is_at_0x9d0(self):
        dex, code_off = self._method()
        target = dex.insn_at(code_off, SAMPLE_SITE)
        assert target is not None, "instruction boundary at 0x%x disappeared" % SAMPLE_SITE
        assert target["raw"].hex() == SAMPLE_SITE_BYTES
        assert target["op"] in dexutil.IF_TESTZ

    def test_branch_target_resolves_to_an_instruction_boundary(self):
        dex, code_off = self._method()
        target = dex.insn_at(code_off, SAMPLE_SITE)
        dest = dex.branch_target(target)
        assert dest is not None
        assert dex.insn_at(code_off, dest) is not None, (
            "branch target 0x%x is not an instruction boundary" % dest)

    def test_every_branch_target_is_an_instruction_boundary(self):
        """A decode desync shows up here first: a branch into the middle of an insn."""
        dex, code_off = self._method()
        boundaries = {i["off"] for i in dex.decode(code_off)}
        stray = sorted(t for t in dex.all_targets(code_off) if t not in boundaries)
        assert stray == [], "branch targets outside the instruction stream: %r" % stray
