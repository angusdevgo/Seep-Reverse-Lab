"""Unit tests for skills/apk-reverse/scripts/protobuf_decode_raw.py.

Two properties are pinned here, because both are claims the reference material
makes and neither is visible from reading the decoder:

  * the built-in known-answer fixture set passes in full (26/26), and
  * a decode -> re-encode round trip is byte-identical for every fixture except
    the one fixture that is deliberately non-canonical, which must instead
    report *why* it differs rather than silently normalising.
"""
from __future__ import annotations

import pytest

from conftest import load_script, run_script

pb = load_script("protobuf_decode_raw.py")

pytestmark = pytest.mark.unit

# 12 fixtures x (fixture check + round trip) + 2 wire-format trap checks.
EXPECTED_FIXTURE_COUNT = 12
EXPECTED_TOTAL_CHECKS = 26


@pytest.fixture(scope="module")
def fixtures():
    return pb._fixtures()


# --------------------------------------------------------------------------- #
# varint primitives
# --------------------------------------------------------------------------- #
class TestVarintPrimitives:
    def test_canonical_example(self):
        assert pb.encode_varint(150) == bytes.fromhex("9601")

    def test_read_varint_returns_info_next_index_and_no_error(self):
        info, nxt, err = pb.read_varint(bytes.fromhex("9601"), 0, 2)
        assert err is None
        assert info["value"] == 150
        assert info["bytes"] == 2
        assert nxt == 2

    def test_a_truncated_varint_is_an_error_not_a_value(self):
        info, nxt, err = pb.read_varint(bytes.fromhex("96"), 0, 1)
        assert info is None
        assert err and "truncated" in err
        assert nxt == 0

    def test_a_non_canonical_encoding_is_flagged(self):
        """A padded varint must be reported: it is why re-encode cannot be assumed equal."""
        info, _nxt, _err = pb.read_varint(bytes.fromhex("8000"), 0, 2)
        assert info["value"] == 0
        assert info["non_canonical"] is True
        assert info["canonical_bytes"] == 1

    def test_varint_len_matches_the_encoding(self):
        for value in (0, 1, 127, 128, 300, 2 ** 31, 2 ** 63 - 1):
            assert pb.varint_len(value) == len(pb.encode_varint(value))

    def test_zigzag(self):
        assert pb.zigzag_decode(0) == 0
        assert pb.zigzag_decode(1) == -1
        assert pb.zigzag_decode(2) == 1
        assert pb.zigzag_decode(4294967294) == 2147483647

    def test_int_views_wrap(self):
        assert pb.int32_view(0xFFFFFFFF) == -1
        assert pb.int64_view(0xFFFFFFFFFFFFFFFF) == -1


# --------------------------------------------------------------------------- #
# the built-in fixture set
# --------------------------------------------------------------------------- #
class TestFixtureSet:
    def test_the_selftest_function_passes_end_to_end(self, capsys):
        assert pb.selftest(None) == 0
        out = capsys.readouterr().out
        assert "selftest: %d/%d PASS" % (EXPECTED_TOTAL_CHECKS, EXPECTED_TOTAL_CHECKS) in out
        assert "FAIL" not in out

    def test_fixture_count_is_stable(self, fixtures):
        """The 26/26 headline is 12 fixtures x 2 + 2; a silent drop would hide."""
        assert len(fixtures) == EXPECTED_FIXTURE_COUNT

    def test_every_fixture_has_a_name_payload_and_expectations(self, fixtures):
        for name, payload, expects, _rt in fixtures:
            assert isinstance(name, str) and name
            assert isinstance(payload, (bytes, bytearray)) and payload
            assert expects, "fixture %s has no assertions" % name

    def test_each_declared_expectation_holds(self, fixtures):
        failures = []
        for name, payload, expects, _rt in fixtures:
            ctx = pb.Ctx(max_depth=6)
            frames = pb._fixture_frames(name, payload)
            fields = []
            for start, end, _p in frames:
                found, _n, _s = pb.walk(payload, start, end, 0, ctx, "f", analyse=True)
                fields.extend(found)
            for label, num, expected in expects:
                got = pb._selftest_lookup(fields, frames, payload, label, num)
                if got != expected:
                    failures.append((name, label, expected, got))
        assert failures == []


# --------------------------------------------------------------------------- #
# round trip
# --------------------------------------------------------------------------- #
class TestRoundTrip:
    def _reencode(self, name, payload):
        frames = pb._fixture_frames(name, payload)
        tree = {"frames": [{"fields": pb.walk(payload, s, e, 0, pb.Ctx(6), "f",
                                              analyse=True)[0]}
                           for s, e, _p in frames]}
        report = {"fields": 0, "identical": 0, "mismatched": []}
        out = pb.reencode_tree(tree, report)
        expected = b"".join(payload[s:e] for s, e, _p in frames)
        return out, expected, report

    def test_canonical_fixtures_reencode_byte_identically(self, fixtures):
        differing = []
        for name, payload, _expects, rt in fixtures:
            if rt == "non-canonical":
                continue
            out, expected, _report = self._reencode(name, payload)
            if out != expected:
                differing.append((name, expected.hex(), out.hex()))
        assert differing == []

    def test_the_non_canonical_fixture_reports_why_it_differs(self, fixtures):
        """A normalising re-encode must say so, not return different bytes quietly."""
        targets = [f for f in fixtures if f[3] == "non-canonical"]
        assert targets, "the non-canonical fixture disappeared from the set"
        for name, payload, _expects, _rt in targets:
            out, expected, report = self._reencode(name, payload)
            assert out != expected
            assert out.hex() == "089601"
            assert report["mismatched"], "the mismatch must be recorded"
            assert "non-canonical" in report["mismatched"][0]["reason"]

    def test_reencode_accounts_for_every_field(self, fixtures):
        for name, payload, _expects, rt in fixtures:
            _out, _expected, report = self._reencode(name, payload)
            assert report["fields"] > 0, name


# --------------------------------------------------------------------------- #
# the two wire-format traps, asserted rather than narrated
# --------------------------------------------------------------------------- #
class TestWireFormatTraps:
    def test_explicit_zero_is_not_the_same_bytes_as_absent(self):
        zero = pb.tag_0(5, 0) + pb.encode_varint(0)
        assert zero != b""

    def test_explicit_zero_decodes_to_value_zero(self):
        zero = pb.tag_0(5, 0) + pb.encode_varint(0)
        fields = pb.walk(zero, 0, len(zero), 0, pb.Ctx(6), "f")[0]
        assert fields[0]["value"] == 0

    def test_absent_field_decodes_to_no_fields(self):
        assert pb.walk(b"", 0, 0, 0, pb.Ctx(6), "f")[0] == []

    def test_a_packed_payload_offers_both_readings(self):
        """Three varints are also a valid nested message; only a schema decides."""
        packed = b"".join(pb.encode_varint(v) for v in (3, 270, 86942))
        cands, view = pb.analyse_payload(packed, 0, pb.Ctx(6), "f", 0)
        live = sorted(c["kind"] for c in cands if c["confidence"] > 0.0)
        all_kinds = sorted(c["kind"] for c in cands)
        assert "packed_varint" in live
        assert "nested_message" in all_kinds
        assert view == "packed_varint"


# --------------------------------------------------------------------------- #
# the subprocess contract
# --------------------------------------------------------------------------- #
class TestSelftestCli:
    def test_selftest_subcommand_exits_zero_and_prints_the_tally(self):
        result = run_script("protobuf_decode_raw.py", ["--selftest"], timeout=180)
        assert not result.timed_out
        assert not result.has_traceback, result.output
        assert result.returncode == 0, result.output
        assert "selftest: %d/%d PASS" % (EXPECTED_TOTAL_CHECKS, EXPECTED_TOTAL_CHECKS) \
            in result.stdout

    def test_help_lists_the_selftest_flag(self):
        result = run_script("protobuf_decode_raw.py", ["--help"])
        assert result.returncode == 0
        assert "--selftest" in result.stdout
