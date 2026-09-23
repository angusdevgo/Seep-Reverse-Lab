"""No-device flows: launch-health verdicts, log parsing, tombstone parsing.

Everything here runs on a bare checkout. The device commands are intercepted, so
what is being tested is the *decision logic* -- which is exactly the part that a
device test would otherwise hide behind "it looked fine on screen".
"""
from __future__ import annotations

import sys

import pytest

from conftest import load_script, run_script

install_test = load_script("install_test.py")
coldstart = load_script("coldstart.py")
native_crash = load_script("native_crash.py")

pytestmark = pytest.mark.integration

TOMBSTONE = "tombstone_sample.txt"
LOGCAT = "logcat_sample.txt"


# --------------------------------------------------------------------------- #
# install_test.py: the two-sample pid verdict
# --------------------------------------------------------------------------- #
def drive(monkeypatch, pids, log="", capsys=None):
    """Run install_test.main() with the device replaced by a scripted responder.

    `pids` is consumed in order by successive `pidof` calls, which is the whole
    point of the check: one sample cannot tell a running app from a crash loop.
    """
    pids = list(pids)
    calls = []

    def fake_adb(args, serial=None, timeout=600):
        calls.append(list(args))
        if list(args)[:1] == ["logcat"] and "-d" in args:
            return log
        return ""

    def fake_sh(cmd, serial=None):
        calls.append(cmd)
        if cmd.startswith("pidof"):
            return pids.pop(0) if pids else ""
        if "mCurrentFocus" in cmd:
            return "mCurrentFocus=Window{a1b2 u0 com.example.app/.MainActivity}"
        return ""

    monkeypatch.setattr(install_test, "adb", fake_adb)
    monkeypatch.setattr(install_test, "sh", fake_sh)
    monkeypatch.setattr(install_test.time, "sleep", lambda _s: None)
    monkeypatch.setattr(sys, "argv", [
        "install_test.py", "--apk", "out/app.apk", "--pkg", "com.example.app",
        "--activity", ".MainActivity",
    ])
    return install_test.main(), calls


class TestLaunchHealthVerdict:
    def test_a_stable_pid_with_no_fatal_signature_is_ok(self, monkeypatch, capsys):
        code, calls = drive(monkeypatch, ["1234", "1234"])
        assert code == 0, capsys.readouterr().out

    def test_a_changed_pid_is_a_failure_even_though_the_app_is_running(self, monkeypatch, capsys):
        """The measured shape of a crash loop: alive at the first sample, restarted by the second."""
        code, _calls = drive(monkeypatch, ["1234", "5678"])
        out = capsys.readouterr().out
        assert code == 1
        assert "pid @+6s : 1234" in out
        assert "5678" in out

    def test_a_dead_app_is_a_failure(self, monkeypatch, capsys):
        code, _calls = drive(monkeypatch, ["", ""])
        assert code == 1
        assert "(dead)" in capsys.readouterr().out

    def test_a_fatal_signature_fails_even_with_a_stable_pid(self, monkeypatch, capsys):
        """Stability is not health: a caught-but-fatal error still fails the check."""
        code, _calls = drive(monkeypatch, ["1234", "1234"],
                             log="01-01 10:00:01 E AndroidRuntime: FATAL EXCEPTION: main\n")
        assert code == 1
        assert "FATAL EXCEPTION" in capsys.readouterr().out

    def test_both_pid_samples_are_actually_taken(self, monkeypatch, capsys):
        _code, calls = drive(monkeypatch, ["1234", "1234"])
        capsys.readouterr()
        pidof_calls = [c for c in calls if isinstance(c, str) and c.startswith("pidof")]
        assert len(pidof_calls) == 2, "the second sample is what catches a crash loop"

    def test_the_launch_uses_the_package_slash_activity_component(self, monkeypatch, capsys):
        _code, calls = drive(monkeypatch, ["1234", "1234"])
        capsys.readouterr()
        assert any("am start -n com.example.app/.MainActivity" == c for c in calls
                   if isinstance(c, str))


# --------------------------------------------------------------------------- #
# coldstart.py: logcat signal counting
# --------------------------------------------------------------------------- #
class TestLogcatSignalCounting:
    @pytest.fixture
    def counts(self, fixtures_dir):
        path = fixtures_dir / LOGCAT
        assert path.exists(), "the logcat fixture is missing from tests/fixtures"
        return coldstart.signal_counts(str(path), coldstart.SIGNAL_PATTERNS)

    @pytest.mark.parametrize("name,expected", [
        ("FATAL EXCEPTION", 1),
        ("VerifyError", 1),
        ("Bad checksum", 1),
        ("ANR", 1),
        ("Displayed", 1),
        ("IncompatibleClassChangeError", 0),
        ("ClassNotFoundException", 0),
        ("uncaughtException", 0),
        ("am_crash", 0),
    ])
    def test_counts(self, counts, name, expected):
        assert counts[name] == expected

    def test_every_pattern_in_the_table_is_reported(self, counts):
        assert set(counts) == set(coldstart.SIGNAL_PATTERNS)

    def test_a_missing_log_yields_no_counts_rather_than_raising(self, tmp_path):
        assert coldstart.signal_counts(str(tmp_path / "nope.txt"),
                                       coldstart.SIGNAL_PATTERNS) == {}

    def test_the_displayed_pattern_captures_the_milliseconds(self):
        import re
        match = re.search(coldstart.SIGNAL_PATTERNS["Displayed"],
                          "I ActivityManager: Displayed com.example.app/.MainActivity: +842ms")
        assert match is not None
        assert match.group(1) == "842"


# --------------------------------------------------------------------------- #
# native_crash.py: tombstone parsing
# --------------------------------------------------------------------------- #
@pytest.fixture
def crash(fixtures_dir):
    text = (fixtures_dir / TOMBSTONE).read_text(encoding="utf-8")
    crashes = native_crash.parse(text)
    assert len(crashes) == 1, "the fixture holds exactly one crash block"
    return crashes[0]


class TestTombstoneParsing:
    def test_signal_and_code(self, crash):
        assert crash["signal"] == 11
        assert crash["signame"] == "SIGSEGV"
        assert crash["si_code"] == "SEGV_MAPERR"
        assert crash["fault"] == "0x0000000000000010"

    def test_process_identity_is_picked_up(self, crash):
        assert crash["pid"] == "12345"
        assert crash["tid"] == "12345"
        assert crash["proc"] == "com.example.app"

    def test_uptime_and_cause(self, crash):
        assert crash["uptime"] == "5"
        assert "null pointer" in crash["cause"]

    def test_backtrace_frames_are_complete(self, crash):
        assert len(crash["frames"]) == 4
        assert crash["frames"][0]["path"].endswith("libfoo.so")
        assert crash["frames"][0]["symbol"] == ""
        assert crash["frames"][1]["symbol"] == "Java_com_example_app_Native_check+120"
        assert crash["frames"][2]["path"].startswith("/apex/")
        assert crash["frames"][2]["symbol"] == "__pthread_start+256"

    def test_registers_are_collected_from_the_dump_line(self, crash):
        assert crash["regs"]["x0"] == 0x10
        assert crash["regs"]["x1"] == 0x7A12345678
        assert crash["regs"]["sp"] == 0x7FFABC1110
        assert crash["regs"]["lr"] == 0x7A11112222

    def test_the_pc_key_is_overwritten_by_the_last_backtrace_frame(self, crash):
        """Measured behaviour, recorded rather than smoothed over.

        Register extraction scans every line of the block with one permissive
        pattern, so a `#NN pc <hex>` backtrace line also matches and the last one
        wins. The register dump's own `pc 0000007a111128cc` is therefore not what
        `regs['pc']` holds. It is a reporting wart, not a wrong verdict -- but it
        is a wart, so it is pinned here and listed in the harness report.
        """
        assert crash["regs"]["pc"] == 0x55488, "the last frame's pc"
        assert crash["regs"]["pc"] != 0x7A111128CC, "the register dump's pc"

    def test_empty_input_produces_no_crashes(self):
        assert native_crash.parse("") == []

    def test_a_log_without_a_signal_line_produces_no_crashes(self):
        assert native_crash.parse("I/whatever: nothing to see\n") == []


class TestLibraryClassification:
    @pytest.mark.parametrize("path,expected", [
        ("/apex/com.android.runtime/lib64/bionic/libc.so", True),
        ("/system/lib64/libart.so", True),
        ("/vendor/lib64/libqcom.so", True),
        ("/data/dalvik-cache/arm64/system@framework@boot.oat", True),
        ("/data/app/~~AbCdEf==/com.example.app-1/lib/arm64/libfoo.so", False),
        ("/data/local/tmp/libpayload.so", False),
    ])
    def test_classification(self, path, expected):
        assert native_crash.is_system_lib(path) is expected

    def test_a_bare_name_is_treated_as_system(self):
        """Measured behaviour: a path that is not absolute cannot be attributed to the app."""
        assert native_crash.is_system_lib("libfoo.so") is True


class TestVerdictHint:
    def test_a_small_fault_address_held_in_a_register_is_flagged_as_arranged(self, crash):
        hints = " ".join(native_crash.verdict_hint(crash))
        assert "small integer" in hints
        assert "ARRANGED" in hints
        assert "x0" in hints

    def test_an_ordinary_null_dereference_gets_no_arranged_hint(self):
        ordinary = {"fault": "0x0", "regs": {"x1": 0x7A111128CC}, "signame": "SIGSEGV"}
        hints = native_crash.verdict_hint(ordinary)
        assert any("small integer" in h for h in hints)
        assert not any("ARRANGED" in h for h in hints)

    def test_sigkill_is_called_out_as_a_deliberate_termination(self):
        hints = native_crash.verdict_hint({"fault": "0x0", "regs": {}, "signame": "SIGKILL"})
        assert any("deliberate termination" in h for h in hints)


class TestNativeCrashCli:
    def test_the_fixture_tombstone_is_parsed_by_the_cli(self, fixtures_dir):
        result = run_script("native_crash.py", [str(fixtures_dir / TOMBSTONE)], timeout=120)
        assert not result.timed_out
        assert not result.has_traceback, result.output
        assert result.returncode == 0, result.output
        assert "libfoo.so" in result.stdout
        assert "SIGSEGV" in result.stdout

    def test_a_missing_log_is_reported_without_a_traceback(self, tmp_path):
        result = run_script("native_crash.py", [str(tmp_path / "absent.txt")])
        assert not result.has_traceback, result.output
        assert result.returncode != 0
        assert "no such file" in result.output

    def test_a_malformed_lib_spec_is_refused(self, fixtures_dir):
        result = run_script("native_crash.py",
                            [str(fixtures_dir / TOMBSTONE), "--lib", "notapair"])
        assert result.returncode != 0
        assert "NAME=PATH" in result.output
