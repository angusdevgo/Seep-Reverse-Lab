# tests/ - the executable half of this repository's evidence

`tests/benchmark.md` is a **record**: what happened when a route was run once, by hand,
against a real sample and a real device. This directory is the other half: checks that run
on every commit with nothing but the standard library and pytest.

The two are not substitutes. A benchmark row can establish that a route works on a hardened
target; it cannot tell you that yesterday's refactor broke the dex width table. A test in
here can tell you that every time, and it can never tell you whether the route achieves the
goal on a real app.

```
python -m pytest -q                    # whole suite
python tests/run_tests.py              # same thing, with a clear message if pytest is missing
python -m pytest -q -m unit            # one marker
python -m pytest -q -m cli             # exit codes, flags, --json
python -m pytest -q -m integration     # no-device flows
python -m pytest -q -ra                # list every skip and xfail reason
```

## What the markers mean

- `unit` - pure functions and parsers of real shipped scripts: the dex width table and branch
  arithmetic, the scheme-less protobuf decoder, the blob rotation search, the leak rules, and
  the established `dex_patch_bytes` regression hash.
- `cli` - one subprocess run per script per invocation shape: `--help`, an unknown flag, no
  arguments, and every input pointed at a file that does not exist.
- `integration` - flows that were made of several parts: adb argv construction under a fake
  runner, logcat signal counting, tombstone parsing, the two-sample launch-health verdict.

## Nothing here needs a device

No test in this suite opens a frida session or touches the network. The device-dependent
behaviour is tested by intercepting the command that *would* have been run and asserting on the
argv list.

The exception is deliberate and enforced: `contract.DEVICE_OR_NETWORK_BOUND` names the 15
scripts that reach a device once their arguments parse, and those are **never executed** with
complete arguments — only `--help` and an unknown flag, which argparse answers before any
device call. That blocklist exists because a development host may well have a phone attached
(the machine this harness was written on did), and an earlier version of the CLI contract test
drove it for real. General safety net: every child runs in a private temporary working
directory, so a script that defaults an output path relative to cwd cannot write into the
shipped tree.

Anything that genuinely cannot be reached this way is not faked into a pass — it is listed as a
coverage gap in `docs/tool-verification/EXTENSION-test-harness.md`.

## Skipped is not passed

Two kinds of non-passing outcome are kept separate on purpose:

- **`skip`** - the check does not apply here. `tools/_work/bench/**` is git-ignored, so the
  `dex_patch_bytes` regression hash self-skips on a fresh checkout and in CI, printing the
  reason. A --json script that needs a sample to reach its JSON path skips too.
- **`xfail`** - the script is present and does **not** meet the repository contract. The
  reason carries the measured value, for example
  `contract says exit 2, measured 1`. These are work items, not flaky tests.

`pytest -q -ra` prints both lists. The xfail list for the CLI layer is the exit-code
unification work order; it is reproduced in `EXTENSION-test-harness.md` with owners.

## Ground rules

- **This suite never edits anything under `skills/`.** A defect found here is registered in
  the harness report. Fixing a script's exit code or quoting strategy is its owner's change,
  and doing it from a test would hide the drift the test exists to expose.
- **The bench tree is evidence and is read-only here.** The regression test copies its input
  into `tmp_path` before patching, so `tools/_work/bench/l1l3/dex/classes.patched.dex` cannot
  be overwritten by a test run.
- **No real target identity is committed.** The leak-scanner decoys are synthesised in
  `tmp_path` at run time, and token-shaped decoys are assembled from fragments so that this
  directory cannot itself become a finding.
- Fixtures in `tests/fixtures/` are small, synthetic sample files. `tests/fixtures/apk/**` is
  owned by a different work item and is not touched from here.
