"""Device-side command construction, exercised without a device.

The behaviour under test is the one the repository's own documentation says is
the reason these helpers exist: a device command is built as an **argv list** and
handed to `subprocess` directly, so the host shell never expands `$`, `|`, `>`,
`;` or quotes before adb sees them. Every assertion here inspects the argv list
that would have been executed; none of them launches adb.
"""
from __future__ import annotations

import re
import subprocess
import sys

import pytest

from conftest import load_script

devsh = load_script("devsh.py")
coldstart = load_script("coldstart.py")
install_test = load_script("install_test.py")

pytestmark = pytest.mark.integration


class Recorder:
    """Captures the argv lists handed to a patched subprocess runner."""

    def __init__(self, stdout="", stderr="", returncode=0):
        self.calls = []
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode

    def __call__(self, cmd, *args, **kwargs):
        self.calls.append((list(cmd), kwargs))
        return subprocess.CompletedProcess(cmd, self.returncode, self.stdout, self.stderr)

    @property
    def last(self):
        return self.calls[-1][0]


# --------------------------------------------------------------------------- #
# devsh.py
# --------------------------------------------------------------------------- #
@pytest.fixture
def devsh_recorder(monkeypatch):
    rec = Recorder(stdout="ok\n")
    monkeypatch.setattr(devsh.subprocess, "run", rec)
    monkeypatch.delenv("ADB_PATH", raising=False)
    monkeypatch.delenv("ADB_SERIAL", raising=False)
    return rec


def run_devsh(monkeypatch, rec, argv):
    monkeypatch.setattr(sys, "argv", ["devsh.py"] + argv)
    return devsh.main()


class TestDevshCommandConstruction:
    def test_shell_command_is_one_argv_element_not_a_shell_string(self, monkeypatch, devsh_recorder):
        """`|` and `grep` must survive as literal text inside a single argument."""
        assert run_devsh(monkeypatch, devsh_recorder, ["sh", "pm list packages | grep myapp"]) == 0
        assert devsh_recorder.last == ["adb", "shell", "pm list packages | grep myapp"]

    def test_serial_is_injected_as_dash_s(self, monkeypatch, devsh_recorder):
        run_devsh(monkeypatch, devsh_recorder, ["--serial", "SERIAL123", "sh", "id"])
        assert devsh_recorder.last == ["adb", "-s", "SERIAL123", "shell", "id"]

    def test_serial_equals_form_is_accepted(self, monkeypatch, devsh_recorder):
        run_devsh(monkeypatch, devsh_recorder, ["--adb=x", "--serial=SERIAL123", "sh", "id"])
        assert devsh_recorder.last == ["x", "-s", "SERIAL123", "shell", "id"]

    def test_adb_path_comes_from_the_environment_when_not_given(self, monkeypatch, devsh_recorder):
        monkeypatch.setenv("ADB_PATH", "/opt/platform-tools/adb")
        monkeypatch.setenv("ADB_SERIAL", "ENVSERIAL")
        run_devsh(monkeypatch, devsh_recorder, ["sh", "id"])
        assert devsh_recorder.last == ["/opt/platform-tools/adb", "-s", "ENVSERIAL", "shell", "id"]

    def test_device_listing_explicitly_ignores_the_serial(self, monkeypatch, devsh_recorder):
        run_devsh(monkeypatch, devsh_recorder, ["dev"])
        assert devsh_recorder.last == ["adb", "devices", "-l"]

    def test_pull_and_push_keep_their_arguments_positional(self, monkeypatch, devsh_recorder):
        run_devsh(monkeypatch, devsh_recorder, ["pull", "/data/local/tmp/x.apk", "./x.apk"])
        assert devsh_recorder.last == ["adb", "pull", "/data/local/tmp/x.apk", "./x.apk"]
        run_devsh(monkeypatch, devsh_recorder, ["push", "./x.apk", "/data/local/tmp/x.apk"])
        assert devsh_recorder.last == ["adb", "push", "./x.apk", "/data/local/tmp/x.apk"]

    def test_a_nonzero_device_status_is_reported_as_one(self, monkeypatch, devsh_recorder):
        devsh_recorder.returncode = 1
        assert run_devsh(monkeypatch, devsh_recorder, ["sh", "false"]) == 1

    def test_the_su_wrapper_is_posix_single_quoted(self, monkeypatch, devsh_recorder):
        # Assert the *property*, not the representation. The previous version of this test pinned
        # `su -c "..."` with `\"` escapes, which is exactly the form that let `;`, `$( )` and
        # backticks through to the device shell -- the test was guarding the defect.
        run_devsh(monkeypatch, devsh_recorder, ["su", 'pm grant com.example.app "android.permission.X"'])
        payload = devsh_recorder.last[-1]
        assert payload.startswith("su -c '") and payload.endswith("'")
        inner = payload[len("su -c '"):-1]
        # A POSIX single-quoted string: no bare quote may appear except as the '\'' escape.
        assert re.fullmatch(r"[^']*('\\''[^']*)*", inner), payload
        assert '"' in inner            # the caller's double quotes survive as literal characters

    def test_an_unknown_mode_prints_usage_and_exits_two(self, monkeypatch, devsh_recorder):
        assert run_devsh(monkeypatch, devsh_recorder, ["frobnicate", "x"]) == 2

    def test_no_arguments_prints_usage_and_exits_two(self, monkeypatch, devsh_recorder):
        assert run_devsh(monkeypatch, devsh_recorder, []) == 2


class TestDevshSuQuotingGap:
    """The quoting contract, now unified through `scripts/device_shell.py`.

    This class used to record a *gap*: `devsh.su` wrapped the command in double quotes and escaped
    only `"`, so `$`, backticks, `;` and `|` from a caller-supplied value still reached the device
    shell, while `coldstart.Device.shell` used the POSIX single-quote escape and did neutralise them.
    Both now go through the shared module; the tests below pin the property from both sides, so a
    future edit that reintroduces double-quote escaping fails here instead of on a device.
    """

    @pytest.mark.parametrize("payload", [
        "id; rm -rf /sdcard/x",
        "id$(touch /data/local/tmp/pwned)",
        "id`touch /data/local/tmp/pwned`",
        "id | tee /data/local/tmp/pwned",
        "id 'quoted'",
    ])
    def test_su_wrapper_neutralises_shell_metacharacters(self, monkeypatch, devsh_recorder, payload):
        run_devsh(monkeypatch, devsh_recorder, ["su", payload])
        wrapped = devsh_recorder.last[-1]
        assert wrapped.startswith("su -c '"), wrapped
        inner = wrapped[len("su -c '"):-1]
        # The payload must be present verbatim, with only the '\'' sequence able to break out --
        # i.e. the whole payload is one argument to sh, not syntax.
        assert re.fullmatch(r"[^']*('\\''[^']*)*", inner), wrapped
        assert payload.replace("'", "'\\''") == inner

    def test_a_malformed_path_is_refused_before_the_device_shell(self, monkeypatch, devsh_recorder):
        """`suf` interpolates a path, so it validates rather than quotes-and-hopes."""
        rc = run_devsh(monkeypatch, devsh_recorder, ["suf", "/data/local/tmp/x;id", "200"])
        assert rc == 2
        assert not devsh_recorder.calls, "the refused command must never reach adb"

    def test_coldstart_uses_the_posix_single_quote_escape(self, monkeypatch):
        """The contrasting implementation: this one does neutralise metacharacters."""
        rec = Recorder()
        monkeypatch.setattr(coldstart, "run", rec)
        dev = coldstart.Device(None, use_su=False)
        dev.su = True
        dev.shell("echo 'hi'; rm -rf /sdcard/x")

        payload = rec.last[-1]
        assert payload.startswith("su -c '")
        assert payload.endswith("'")
        assert "'\\''" in payload, "the POSIX single-quote escape is missing"


# --------------------------------------------------------------------------- #
# coldstart.Device: command shape and screenshot handling
# --------------------------------------------------------------------------- #
class TestDeviceHelperCommands:
    def make_device(self, monkeypatch, serial=None):
        rec = Recorder()
        monkeypatch.setattr(coldstart, "run", rec)
        dev = coldstart.Device(serial, use_su=False)
        return dev, rec

    def test_shell_without_root_passes_the_command_as_one_argument(self, monkeypatch):
        dev, rec = self.make_device(monkeypatch, serial="SERIAL123")
        dev.shell("dumpsys window | grep mCurrentFocus")
        assert rec.last == ["adb", "-s", "SERIAL123", "shell", "dumpsys window | grep mCurrentFocus"]

    def test_shell_without_a_serial_omits_dash_s(self, monkeypatch):
        dev, rec = self.make_device(monkeypatch)
        dev.shell("id")
        assert rec.last == ["adb", "shell", "id"]

    def test_foreground_activity_parses_the_resumed_component(self, monkeypatch):
        dev, rec = self.make_device(monkeypatch, serial="S")
        rec.stdout = ("mResumedActivity: ActivityRecord{9f2c1 u0 "
                      "com.example.app/.MainActivity t42}\n")
        assert coldstart.foreground_activity(dev) == "com.example.app/.MainActivity"

    def test_foreground_activity_returns_none_when_absent(self, monkeypatch):
        dev, rec = self.make_device(monkeypatch, serial="S")
        rec.stdout = "no matches\n"
        assert coldstart.foreground_activity(dev) is None

    def test_installed_facts_extracts_version_and_uid(self, monkeypatch):
        dev, rec = self.make_device(monkeypatch, serial="S")

        def respond(cmd, *args, **kwargs):
            rec.calls.append((list(cmd), kwargs))
            if "versionCode" in cmd[-1]:
                out = "    versionCode=42 minSdk=24 targetSdk=34\n    versionName=1.2.3\n"
            elif "sha256sum" in cmd[-1]:
                out = "a" * 64 + "  /data/app/base.apk\n"
            elif "base.apk" in cmd[-1]:
                out = "/data/app/~~x==/com.example.app-1/base.apk\n"
            elif "userId=" in cmd[-1]:
                out = "    userId=10123\n"
            else:
                out = ""
            return subprocess.CompletedProcess(cmd, 0, out, "")

        monkeypatch.setattr(coldstart, "run", respond)
        facts = coldstart.installed_facts(dev, "com.example.app")
        assert facts["versionName"] == "1.2.3"
        assert facts["uid"] == "10123"
        assert facts["apk_sha256"] == "a" * 64

    def test_version_code_swallows_the_rest_of_the_line(self, monkeypatch):
        """Measured sub-string behaviour of `installed_facts`, recorded as a work item.

        The extraction is `r'\\s*(versionCode|...)=(.*)'`, so on a real
        `dumpsys package` line -- `versionCode=42 minSdk=24 targetSdk=34` --
        `facts['versionCode']` is the whole remainder, not `42`. It is still a
        usable before/after fingerprint, which is how the caller uses it, but the
        field name overstates what it holds.
        """
        dev = coldstart.Device(None, use_su=False)

        def respond(cmd, *args, **kwargs):
            if "versionCode" in cmd[-1]:
                out = "    versionCode=42 minSdk=24 targetSdk=34\n"
            else:
                out = ""
            return subprocess.CompletedProcess(cmd, 0, out, "")

        monkeypatch.setattr(coldstart, "run", respond)
        facts = coldstart.installed_facts(dev, "com.example.app")
        assert facts["versionCode"] == "42 minSdk=24 targetSdk=34"


class TestScreenshotValidation:
    """`screencap` is judged by the bytes on disk, not by the command's exit status."""

    PNG_MAGIC = b"\x89PNG\r\n\x1a\n"

    def make_device(self, monkeypatch):
        dev = coldstart.Device(None, use_su=False)
        return dev

    def test_a_png_header_is_accepted_and_the_size_returned(self, monkeypatch, tmp_path):
        dev = self.make_device(monkeypatch)
        payload = self.PNG_MAGIC + b"\x00" * 100

        def fake_run(cmd, *args, **kwargs):
            kwargs["stdout"].write(payload)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr(coldstart.subprocess, "run", fake_run)
        out = tmp_path / "shot.png"
        assert dev.screencap(str(out)) == len(payload)
        assert out.read_bytes() == payload

    def test_the_capture_uses_exec_out_not_shell_redirect(self, monkeypatch, tmp_path):
        dev = self.make_device(monkeypatch)
        seen = []

        def fake_run(cmd, *args, **kwargs):
            seen.append(list(cmd))
            kwargs["stdout"].write(self.PNG_MAGIC + b"\x00" * 100)
            return subprocess.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr(coldstart.subprocess, "run", fake_run)
        dev.screencap(str(tmp_path / "shot.png"))
        assert seen[0] == ["adb", "exec-out", "screencap", "-p"]

    def test_a_non_png_body_is_rejected(self, monkeypatch, tmp_path):
        """A device that printed an error into the stream must not be read as a frame."""
        dev = self.make_device(monkeypatch)

        def fake_run(cmd, *args, **kwargs):
            kwargs["stdout"].write(b"error: device offline\n")
            return subprocess.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr(coldstart.subprocess, "run", fake_run)
        assert dev.screencap(str(tmp_path / "shot.png")) == -1

    def test_a_truncated_body_is_rejected(self, monkeypatch, tmp_path):
        dev = self.make_device(monkeypatch)

        def fake_run(cmd, *args, **kwargs):
            kwargs["stdout"].write(b"\x89PNG")
            return subprocess.CompletedProcess(cmd, 0, "", "")

        monkeypatch.setattr(coldstart.subprocess, "run", fake_run)
        assert dev.screencap(str(tmp_path / "shot.png")) == -1

    def test_a_timeout_is_reported_as_a_failed_capture(self, monkeypatch, tmp_path):
        dev = self.make_device(monkeypatch)

        def fake_run(cmd, *args, **kwargs):
            raise subprocess.TimeoutExpired(cmd, 30)

        monkeypatch.setattr(coldstart.subprocess, "run", fake_run)
        assert dev.screencap(str(tmp_path / "shot.png")) == -1


# --------------------------------------------------------------------------- #
# install_test.py: argument plumbing
# --------------------------------------------------------------------------- #
class TestInstallTestAdbWrappers:
    def test_serial_is_injected_as_dash_s(self, monkeypatch):
        rec = Recorder()
        monkeypatch.setattr(install_test.subprocess, "run", rec)
        install_test.adb(["shell", "id"], "SERIAL")
        assert rec.last == ["adb", "-s", "SERIAL", "shell", "id"]

    def test_without_a_serial_no_dash_s_is_added(self, monkeypatch):
        rec = Recorder()
        monkeypatch.setattr(install_test.subprocess, "run", rec)
        install_test.adb(["devices", "-l"])
        assert rec.last == ["adb", "devices", "-l"]

    def test_stderr_is_appended_so_device_errors_are_not_silently_dropped(self, monkeypatch):
        rec = Recorder(stdout="out", stderr="error: device offline")
        monkeypatch.setattr(install_test.subprocess, "run", rec)
        combined = install_test.adb(["devices"])
        assert "out" in combined
        assert "device offline" in combined

    def test_su_wrapper_keeps_the_command_as_one_argument(self, monkeypatch):
        rec = Recorder()
        monkeypatch.setattr(install_test.subprocess, "run", rec)
        install_test.su('pm grant com.example.app "android.permission.X"', "S")
        assert rec.last == [
            "adb", "-s", "S", "shell",
            'su -c "pm grant com.example.app \\"android.permission.X\\""',
        ]
