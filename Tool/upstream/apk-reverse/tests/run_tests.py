#!/usr/bin/env python3
"""Single entry point for the regression suite.

Why this file exists in addition to ``pytest.ini``: a fresh checkout without
pytest should say so in one line, with the install command, instead of dying on
an import error. It exits 3 (environment capability insufficient) per the
repository's exit-code policy, so a wrapper script can tell "no pytest here"
apart from "tests failed" (1).

Usage:
    python tests/run_tests.py                 # whole suite, quiet summary
    python tests/run_tests.py -m unit         # one marker
    python tests/run_tests.py -k dexutil -vv  # anything pytest accepts
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def main(argv):
    try:
        import pytest
    except ImportError:
        sys.stderr.write(
            "pytest is not installed; this suite cannot run.\n"
            "  install: python -m pip install pytest\n"
            "  the suite is stdlib-only otherwise (no device, no network, no adb)\n")
        return 3

    # pytest.ini lives at the repository root and is found from there.
    os.chdir(REPO_ROOT)
    args = list(argv[1:]) or ["-q"]
    return int(pytest.main(args))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
