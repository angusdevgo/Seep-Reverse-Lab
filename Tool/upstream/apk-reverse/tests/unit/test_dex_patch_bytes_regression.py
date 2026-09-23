"""The established regression for scripts/dex_patch_bytes.py.

This is the repository's pre-existing red line, not a test invented here: the
l1l3 benchmark row recorded that patching the first root check in
`MainActivity.onCreate` produces a specific file, and any refactor of the dex
reader, the spec matcher, the header fixer or the writer must reproduce it
byte for byte.

`tools/_work/bench/**` is git-ignored, so these tests skip with a printed reason
on a fresh checkout. That is deliberate: a regression marker that turns red
because a sample is absent is a marker people learn to ignore.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from conftest import L1L3_PATCHED_SHA256, load_script, require_path, run_script

dexutil = load_script("dexutil.py")

pytestmark = pytest.mark.unit

SPEC_NAME = "l1_root.spec.json"
SITE_OFF = 0x9D0
OLD_BYTES = "39000e00"
NEW_BYTES = "00000000"


@pytest.fixture
def sample(bench_l1l3):
    """Paths to the recorded input, spec and expected output."""
    dex = require_path(bench_l1l3 / "dex" / "classes.dex",
                       "git-ignored bench tree")
    spec = require_path(bench_l1l3 / SPEC_NAME, "git-ignored bench tree")
    expected = require_path(bench_l1l3 / "dex" / "classes.patched.dex",
                            "git-ignored bench tree")
    return {"dex": dex, "spec": spec, "expected": expected}


def patch(sample, tmp_path, extra=()):
    out = tmp_path / "out.patched.dex"
    report = tmp_path / "report.json"
    result = run_script("dex_patch_bytes.py",
                        [str(sample["dex"]), "--spec", str(sample["spec"]),
                         "-o", str(out), "--report", str(report)] + list(extra))
    return result, out, report


# --------------------------------------------------------------------------- #
# the hash marker
# --------------------------------------------------------------------------- #
class TestRecordedRegression:
    def test_the_patch_runs_and_exits_zero(self, sample, tmp_path):
        result, _out, _report = patch(sample, tmp_path)
        assert not result.timed_out, repr(result)
        assert not result.has_traceback, result.output
        assert result.returncode == 0, result.output

    def test_output_matches_the_recorded_sha256(self, sample, tmp_path):
        _result, out, _report = patch(sample, tmp_path)
        digest = hashlib.sha256(out.read_bytes()).hexdigest()
        assert digest.startswith(L1L3_PATCHED_SHA256), (
            "the recorded marker moved: got %s, expected prefix %s"
            % (digest, L1L3_PATCHED_SHA256))

    def test_output_is_byte_identical_to_the_stored_expectation(self, sample, tmp_path):
        _result, out, _report = patch(sample, tmp_path)
        assert out.read_bytes() == sample["expected"].read_bytes()

    def test_only_the_four_patch_bytes_and_the_header_change(self, sample, tmp_path):
        """Pin *where* the difference is, so a stray write cannot pass as a hash match.

        The allowed window is bytes 8..32 (checksum + signature, recomputed) plus
        the four bytes of the patched instruction. Two of those four keep their
        original value (`0e00` -> `0000` clears one byte and leaves the zero
        byte), and a recomputed checksum may keep a byte by coincidence, so the
        assertion is containment plus the changes that must occur.
        """
        _result, out, _report = patch(sample, tmp_path)
        before = sample["dex"].read_bytes()
        after = out.read_bytes()
        assert len(before) == len(after), "an equal-length patch must not resize the file"

        diffs = {i for i, (a, b) in enumerate(zip(before, after)) if a != b}
        window = set(range(8, 32)) | {SITE_OFF, SITE_OFF + 1, SITE_OFF + 2, SITE_OFF + 3}

        assert diffs <= window, "bytes changed outside the owned window: %r" % sorted(
            diffs - window)
        # The two bytes that differ between 39000e00 and 00000000 must have moved.
        assert {SITE_OFF, SITE_OFF + 2} <= diffs
        # Both header fields are recomputed; each must have changed somewhere.
        assert diffs & set(range(8, 12)), "no checksum byte changed"
        assert diffs & set(range(12, 32)), "no signature byte changed"

    def test_the_written_dex_self_verifies(self, sample, tmp_path):
        _result, out, _report = patch(sample, tmp_path)
        data = bytearray(out.read_bytes())
        assert dexutil.verify_dex_header(data) == (True, True)

    def test_the_result_still_parses_and_decodes_cleanly(self, sample, tmp_path):
        _result, out, _report = patch(sample, tmp_path)
        dex, _entry = dexutil.load_dex(str(out))
        assert dex.check() == []
        found = dex.find_method("Lsg/vantagepoint/uncrackable1/MainActivity;",
                                "onCreate", "(Landroid/os/Bundle;)V")
        assert found
        _section, _idx, code_off = found
        _insns, clean, expected = dex.decode_all(code_off)
        assert clean, "the patched method must still decode to exactly insns_size units"


# --------------------------------------------------------------------------- #
# the report the tool writes
# --------------------------------------------------------------------------- #
class TestPatchReport:
    def test_report_records_the_site_and_the_polarity_check(self, sample, tmp_path):
        _result, _out, report = patch(sample, tmp_path)
        reports = json.loads(report.read_text(encoding="utf-8"))
        assert len(reports) == 1
        entry = reports[0]
        assert entry["ok"] is True
        assert entry["site_off"] == SITE_OFF
        assert entry["old_bytes"] == OLD_BYTES
        assert entry["new_bytes"] == NEW_BYTES
        assert entry["expect_next_ok"] is True
        assert entry["size_delta"] == 0

    def test_report_confirms_the_post_edit_instruction_boundary(self, sample, tmp_path):
        _result, _out, report = patch(sample, tmp_path)
        entry = json.loads(report.read_text(encoding="utf-8"))[0]
        assert entry["post_decode_clean"] is True
        assert entry["verifier_edges"] == 0

    def test_stdout_states_the_polarity_check_passed(self, sample, tmp_path):
        result, _out, _report = patch(sample, tmp_path)
        assert "polarity: expect_next satisfied" in result.stdout

    def test_dry_run_reports_without_writing(self, sample, tmp_path):
        out = tmp_path / "should-not-exist.dex"
        result = run_script("dex_patch_bytes.py",
                            [str(sample["dex"]), "--spec", str(sample["spec"]),
                             "-o", str(out), "--dry-run"])
        assert result.returncode == 0, result.output
        assert "dry run: nothing written" in result.stdout
        assert not out.exists()

    def test_default_output_name_is_derived_from_the_input(self, sample, tmp_path):
        """Run on a copy: the bench tree is evidence and is never written by this suite."""
        local = tmp_path / "classes.dex"
        local.write_bytes(sample["dex"].read_bytes())
        result = run_script("dex_patch_bytes.py",
                            [str(local), "--spec", str(sample["spec"])])
        assert result.returncode == 0, result.output
        derived = tmp_path / "classes.patched.dex"
        assert derived.exists(), result.output
        assert hashlib.sha256(derived.read_bytes()).hexdigest() == \
            hashlib.sha256(sample["expected"].read_bytes()).hexdigest()


# --------------------------------------------------------------------------- #
# refusal paths: a wrong spec must fail loudly, not write a plausible file
# --------------------------------------------------------------------------- #
class TestRefusals:
    def test_a_dry_run_against_a_missing_match_fails(self, sample, tmp_path):
        spec = tmp_path / "bad.spec.json"
        spec.write_text(json.dumps([{
            "name": "no such site",
            "class": "Lsg/vantagepoint/uncrackable1/MainActivity;",
            "method": "onCreate",
            "desc": "(Landroid/os/Bundle;)V",
            "match": {"kind": "if-testz", "bytes": "deadbeef"},
            "replace": {"kind": "nops"},
        }]), encoding="utf-8")
        result = run_script("dex_patch_bytes.py",
                            [str(sample["dex"]), "--spec", str(spec), "--dry-run"])
        assert result.returncode == 1, result.output
        assert "no instruction matched" in result.output

    def test_a_wrong_polarity_pin_is_refused(self, sample, tmp_path):
        """expect_next exists to make the wrong side of a branch impossible to patch."""
        spec = tmp_path / "bad-polarity.spec.json"
        spec.write_text(json.dumps([{
            "name": "wrong expected neighbour",
            "class": "Lsg/vantagepoint/uncrackable1/MainActivity;",
            "method": "onCreate",
            "desc": "(Landroid/os/Bundle;)V",
            "match": {"kind": "if-testz", "bytes": OLD_BYTES},
            "expect_next": {"kind": "return"},
            "replace": {"kind": "nops"},
        }]), encoding="utf-8")
        result = run_script("dex_patch_bytes.py",
                            [str(sample["dex"]), "--spec", str(spec), "--dry-run"])
        assert result.returncode == 1, result.output
        assert "expect_next not satisfied" in result.output

    def test_a_missing_dex_is_a_usage_error(self, tmp_path, sample):
        result = run_script("dex_patch_bytes.py",
                            [str(tmp_path / "nope.dex"), "--spec", str(sample["spec"])])
        assert result.returncode == 2, result.output
        assert "no such file" in result.output

    def test_a_missing_spec_argument_is_a_usage_error(self, sample):
        result = run_script("dex_patch_bytes.py", [str(sample["dex"])])
        assert result.returncode == 2, result.output

    def test_a_non_dex_input_is_refused_with_code_1(self, tmp_path, sample):
        """Structurally invalid input is a target-side failure (1), not a usage error (2)."""
        bogus = tmp_path / "bogus.dex"
        bogus.write_bytes(b"not a dex at all" * 8)
        result = run_script("dex_patch_bytes.py",
                            [str(bogus), "--spec", str(sample["spec"]), "--dry-run"])
        assert result.returncode == 1, result.output
        assert "not a dex" in result.output
