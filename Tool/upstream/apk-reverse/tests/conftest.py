"""Shared fixtures for the apk-reverse regression suite.

The rules this directory follows (they are the point of the directory, not a
style preference):

  * Nothing here may need a device, adb, frida, or the network. Routes that do
    are recorded as experiments in ``tests/benchmark.md``; their coverage gap is
    stated in ``docs/tool-verification/EXTENSION-test-harness.md`` rather than
    simulated into a green tick.
  * A missing fixture is ``pytest.skip`` with the reason on stdout, never a red
    test. ``tools/_work/bench/**`` is git-ignored, so CI legitimately does not
    have it and the regression hash test must degrade to a skip there.
  * This suite observes behaviour. It never edits anything under
    ``skills/apk-reverse/scripts/`` -- a defect found here is written into the
    report as a work item, not patched in place.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "skills" / "apk-reverse" / "scripts"
FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
BENCH_L1L3 = REPO_ROOT / "tools" / "_work" / "bench" / "l1l3"

# Some scripts import their siblings by bare name (`from dexutil import ...`);
# loading them as modules requires that directory on sys.path. The suite's own
# directory is added too, so `from conftest import load_script` works regardless
# of how pytest resolves the rootdir.
for _p in (SCRIPTS_DIR, Path(__file__).resolve().parent):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

PYTHON = sys.executable

# Children run with this as their working directory, never the scripts directory.
# Measured reason: `coldstart.py` writes its capture under `--out` (default
# `coldstart/`), so a contract test that ran it with the scripts directory as cwd
# left a `skills/apk-reverse/scripts/coldstart/logcat.txt` behind. This suite must
# not write anywhere near the shipped tree, and a script that defaults an output
# path relative to cwd is exactly the case that catches a harness out.
ISOLATED_CWD = tempfile.mkdtemp(prefix="apkrev-suite-cwd-")

# The regression marker established before this harness existed. It is a hash,
# not a golden-file rewrite: scripts/dex_patch_bytes.py applied to the
# l1l3 fixture must still reproduce the file that the recorded benchmark row
# produced.
L1L3_PATCHED_SHA256 = "67ae1e58e7a44777e5ac8f9f823ab21e"

_loaded: dict[str, object] = {}


class ScriptResult:
    """Result of running one script as a subprocess."""

    def __init__(self, argv, returncode, stdout, stderr, timed_out=False):
        self.argv = argv
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr
        self.timed_out = timed_out

    @property
    def output(self) -> str:
        return self.stdout + self.stderr

    @property
    def has_traceback(self) -> bool:
        return "Traceback (most recent call last)" in self.output

    def __repr__(self) -> str:  # keeps assertion failures readable
        return "ScriptResult(argv=%r, rc=%r, timed_out=%r)" % (
            self.argv, self.returncode, self.timed_out)


def script_path(name: str) -> Path:
    return SCRIPTS_DIR / name


def all_scripts() -> list[str]:
    """Every shipped script, sorted. Used to parameterise the CLI contract tests."""
    return sorted(p.name for p in SCRIPTS_DIR.glob("*.py"))


def run_script(name, args=(), timeout=60, cwd=None, stdin=None, env=None):
    """Run one shipped script in a subprocess and capture everything.

    The child runs with ``PYTHONIOENCODING=utf-8`` so that a non-UTF-8 console
    (a Windows CP936 shell, a CI runner with C locale) does not turn a UTF-8
    print into a UnicodeEncodeError and change the exit code under test, and with
    an isolated working directory so that a script defaulting an output path
    relative to cwd cannot write into the shipped tree.
    """
    argv = [PYTHON, str(script_path(name))] + [str(a) for a in args]
    child_env = dict(os.environ)
    child_env["PYTHONIOENCODING"] = "utf-8"
    child_env["PYTHONDONTWRITEBYTECODE"] = "1"
    if env:
        child_env.update(env)
    try:
        proc = subprocess.run(
            argv, capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, cwd=str(cwd or ISOLATED_CWD), input=stdin, env=child_env,
        )
    except subprocess.TimeoutExpired as exc:
        return ScriptResult(argv, None, _text(exc.stdout), _text(exc.stderr),
                            timed_out=True)
    return ScriptResult(argv, proc.returncode, proc.stdout or "", proc.stderr or "")


def _text(blob):
    if blob is None:
        return ""
    if isinstance(blob, bytes):
        return blob.decode("utf-8", "replace")
    return blob


def load_script(name):
    """Import a shipped script as a module, so pure functions can be unit-tested.

    The module is registered under a namespaced name (``apkrev_<stem>``) because
    several scripts have siblings with the same basename in other trees.
    """
    if name in _loaded:
        return _loaded[name]
    path = script_path(name)
    mod_name = "apkrev_" + path.stem
    spec = importlib.util.spec_from_file_location(mod_name, str(path))
    if spec is None or spec.loader is None:
        raise ImportError("cannot load %s" % path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    spec.loader.exec_module(module)
    _loaded[name] = module
    return module


def require_path(path: Path, why: str):
    """Skip with a printed reason when a git-ignored fixture is absent."""
    if not Path(path).exists():
        pytest.skip("fixture absent: %s (%s)" % (path, why))
    return Path(path)


@pytest.fixture(scope="session")
def repo_root():
    return REPO_ROOT


@pytest.fixture(scope="session")
def scripts_dir():
    return SCRIPTS_DIR


@pytest.fixture(scope="session")
def fixtures_dir():
    return FIXTURES_DIR


@pytest.fixture(scope="session")
def bench_l1l3():
    return require_path(
        BENCH_L1L3,
        "tools/_work/bench is git-ignored; re-download the l1l3 sample to run the "
        "dex_patch_bytes regression hash test",
    )
