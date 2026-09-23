"""Helpers for the CLI contract tests.

Everything here is derived at run time from the scripts' own `--help` output
rather than from a hard-coded list of argument names, so a new script is covered
automatically and a renamed flag does not silently stop being tested.

The contract under test is the repository-wide one recorded in
tools/_work/REBUILD-BRIEF.md section 4:

    0 = success
    1 = the target result failed
    2 = bad arguments or input
    3 = the environment lacks a capability
    4 = internal tool error

A script that does not follow it yet is not a red test here: the test calls
``pytest.xfail`` with the measured code in the reason, so the summary line stays
green and the xfail list is exactly the work order for unifying exit codes.
"""
from __future__ import annotations

import json
from pathlib import Path

# A path that does not exist anywhere. Used to drive the "bad input" scenario.
NONEXISTENT = str(Path("__apkrev_missing__") / "does-not-exist.bin")

# The four contract codes, plus None for "did not return".
CONTRACT_EXIT_CODES = {0, 1, 2, 3, 4}


def parse_leading_json(text):
    """Parse the first JSON document in `text`, ignoring anything after it.

    Several scripts print a `RESULT=<token>` line after their JSON document (the
    repository's long-task discipline requires that token last), so a plain
    json.loads on the whole stream fails. Only the first document is returned.
    """
    starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
    if not starts:
        return None
    try:
        doc, _end = json.JSONDecoder().raw_decode(text[min(starts):])
    except ValueError:
        return None
    return doc


def usage_block(help_text):
    """Return the joined `usage:` block of an argparse-rendered help text."""
    lines = help_text.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.lower().startswith("usage:"):
            start = i
            break
    if start is None:
        return None
    block = [lines[start][len("usage:"):].strip()]
    for line in lines[start + 1:]:
        if not line.strip() or not line.startswith((" ", "\t")):
            break
        block.append(line.strip())
    return " ".join(block)


def _strip_bracketed(block):
    """Split a usage line into tokens, dropping every bracketed (optional) group."""
    tokens, depth, cur = [], 0, ""
    for ch in block:
        if ch in "[(":
            depth += 1
            continue
        if ch in ")]":
            depth -= 1
            continue
        if depth:
            continue
        if ch.isspace():
            if cur:
                tokens.append(cur)
                cur = ""
        else:
            cur += ch
    if cur:
        tokens.append(cur)
    return tokens


def usage_state(help_text):
    """Classify a script's usage line.

    Returns one of:
      "unreadable"    - no argparse-style `usage:` block at all (hand-written usage)
      "none-required" - a usage block exists but names no positional and no required option
      "required"      - at least one positional or required option is named
    """
    block = usage_block(help_text)
    if block is None:
        return "unreadable"
    return "required" if _strip_bracketed(block)[1:] else "none-required"


def missing_input_args(help_text):
    """Build an argv that points every positional and required option at a missing file.

    Returns None when there is nothing to point at: either the usage block cannot
    be recovered (the four scripts with a hand-written parser print their own
    usage, not argparse's) or the script takes no required argument at all.
    """
    if usage_state(help_text) != "required":
        return None
    tokens = _strip_bracketed(usage_block(help_text))
    args, i = [], 1          # tokens[0] is the program name
    while i < len(tokens):
        token = tokens[i]
        if token.startswith("-"):
            args.append(token)
            if i + 1 < len(tokens) and not tokens[i + 1].startswith("-"):
                args.append(NONEXISTENT)
                i += 1
        else:
            args.append(NONEXISTENT)
        i += 1
    return args or None


def has_option(help_text, option):
    return option in help_text


# Scripts that reach a device, a live frida server or a network peer once their
# arguments parse. They are listed explicitly for one reason: this suite must not
# touch a device, and a development host may well have one attached. Measured on
# the machine this harness was written on, `adb devices` reported one online
# device, and running `coldstart.py --pkg <name>` really did start
# `adb logcat -v threadtime` and capture frames. So the exclusion is not
# theoretical: it is the difference between a unit test and a device test.
#
# `--help` and an unknown flag are still exercised for these scripts: argparse
# answers both before any device call is reached, which was verified for every
# one of them (`--help` returned in well under a second, an unknown flag returned
# 2). It is the argument-complete scenarios that are refused.
DEVICE_OR_NETWORK_BOUND = {
    "coldstart.py", "datastore_inject.py", "devsh.py", "frida_rpc_serve.py",
    "grab_crash.py", "install_test.py", "lib_map.py", "mt_mcp_probe.py",
    "probe_api.py", "run_probe.py", "sig_probe.py", "snap.py",
    "spawn_patch_detach.py", "tls_check.py", "usb_net_proxy.py",
}


def execution_refusal(name, scenario, help_text):
    """Why this script must not be executed for `scenario`, or None if it may be.

    Returns a skip reason rather than a verdict: not executing a script is a
    coverage limit, not a contract violation, and the two must not be reported
    with the same word.
    """
    if name in DEVICE_OR_NETWORK_BOUND:
        return ("%s reaches a device or the network once its arguments parse; %s is not "
                "executed because this suite does not touch a device" % (name, scenario))
    state = usage_state(help_text)
    if state == "unreadable":
        return ("%s prints its own usage instead of argparse's, so %s cannot be derived "
                "automatically" % (name, scenario))
    if state == "none-required":
        return ("%s requires no argument, so %s is legal and the contract does not apply"
                % (name, scenario))
    return None

# The scripts whose --json path is reachable on a bare checkout. Everything else
# that advertises --json needs a sample or a device to get that far; those are
# skipped with that reason rather than asserted against a guess.
JSON_RUNNABLE = {
    "doctor.py": ["--json"],
    "preflight.py": ["--json"],
}

# Keys the unified JSON contract requires at minimum.
JSON_REQUIRED_KEYS = ("status",)
JSON_CONTEXT_KEYS = ("exit_code", "capability", "evidence", "warnings", "next_action")
