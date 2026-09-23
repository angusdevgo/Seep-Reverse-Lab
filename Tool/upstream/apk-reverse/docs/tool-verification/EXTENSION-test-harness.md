# EXTENSION — executable test harness, CI, and the exit-code work order

This file records what the regression harness in `tests/` actually does, what it measured on
this machine, and what it does **not** cover. Strength labels follow the repository rule in
`references/long-task-discipline.md`: `observed` means an exact command and its output are
below, `inferred` means reasoned from a neighbouring measurement, `unverified` means nobody
has put a command behind it here.

The distinction this file exists to keep honest: `tests/benchmark.md` is a **record** of routes
run once by hand against real samples and a real device. `tests/` is a **gate** that runs on
every commit with the standard library and pytest and nothing else. Neither replaces the
other, and a green suite is not evidence that any route works on a hardened target.

---

## 1. How to run it, and what it printed

```
$ python -m pytest -q
596 passed, 153 skipped, 26 xfailed in 49.67s                      observed

$ python -m pytest -q -m unit
163 passed, 612 deselected in 4.50s                                observed

$ python -m pytest -q -m cli
342 passed, 153 skipped, 255 deselected, 25 xfailed in 38.26s      observed

$ python -m pytest -q -m integration
65 passed, 709 deselected, 1 xfailed in 1.33s                      observed

$ python tests/run_tests.py -q -m unit
163 passed, 612 deselected in 5.08s                                observed
```

`tests/run_tests.py` is the one-command entry point. It refuses to fail obscurely when pytest
is absent — measured by putting a `pytest.py` that raises `ImportError` first on
`PYTHONPATH`:

```
$ python tests/run_tests.py
pytest is not installed; this suite cannot run.
  install: python -m pip install pytest
  the suite is stdlib-only otherwise (no device, no network, no adb)
exit=3                                                             observed
```

Exit 3 is the repository's "environment capability insufficient" code, so a wrapper can tell
"no pytest here" apart from "tests failed". The suite is stdlib-only apart from pytest itself.
CI targets Python 3.11 and 3.13; this machine measured on 3.14.0 with pytest 8.4.1.

---

## 2. Coverage

| Area | What runs | Strength |
|---|---|---|
| dex format table | `insn_units` asserted opcode by opcode against 29 named traps (payload widths, `0x32`-`0x3D` being two units, `const-string` vs `/jumbo`, the `goto` family at `0x28`-`0x2A`); `OP_UNITS` and the accessor must agree for every listed opcode; unallocated opcodes still terminate | observed |
| dex header | magic/`file_size`/table-pointer checks against a synthesised consistent header; the verified offset table asserted by value; signature-before-checksum order, including the failure mode where a checksum taken over a zeroed signature never verifies | observed |
| branch arithmetic | `if-test`/`if-testz`/`goto`/`goto16`/`goto32` targets and register extraction, on a synthetic buffer | observed |
| the sample regression | `dex_patch_bytes.py` + `l1_root.spec.json` → sha256 `67ae1e58…` and byte-identical to `classes.patched.dex`; the diff window is pinned (see §6) | observed |
| scheme-less protobuf | built-in fixture set 26/26, per-fixture expectations, decode→re-encode byte-identical for every canonical fixture, the non-canonical fixture required to *report* its mismatch, both wire-format traps | observed |
| blob rotation search | outer encodings round-trip, raw/zlib/gzip identified by name, the rotation and prefix (`skip`) parameters recovered from a payload built with known parameters | observed |
| leak scanner | synthesised decoys in a temporary directory are reported with the right rules and strengths; the exemption list (`com.android.*`, `com.google.*`, `org.example.*`, `<pkg>`, loopback) produces no finding; an RFC 5737 address stays `weak` and keeps the default gate green while `--fail-on any` fails it; JSON report keys and the last-line `RESULT=` token | observed |
| CLI contract | every shipped script, four invocation shapes where they apply: `--help`, unknown flag, no arguments, all inputs pointed at a missing file | observed |
| adb argv construction | `devsh.py`, `coldstart.Device`, `install_test.adb` build an **argv list**; `\|`, `>`, `$()` and quotes survive as literal text inside one argument; serial injection as `-s`; env-var precedence | observed |
| screenshot validation | `coldstart.Device.screencap` judges the bytes on disk: PNG magic accepted, non-PNG rejected, a sub-8-byte body rejected, a timeout reported as a failed capture | observed |
| launch-health verdict | `install_test.main` driven with a scripted `pidof`: stable pid + no fatal signature is the only pass; a changed pid, a dead app, or a stable pid with a `FATAL EXCEPTION` line all fail; two samples are actually taken | observed |
| log/tombstone parsing | `coldstart.signal_counts` over a logcat fixture (9 patterns, exact counts); `native_crash.parse` signal/code/pid/uptime/frames/registers; `is_system_lib` classification; the `verdict_hint` for an arranged fault | observed |

---

## 3. Not covered — the honest gaps

### 3.1 Device work: excluded by design, because hardware is present

This harness must not touch a device, and after one measured incident that is now enforced
rather than assumed. It has to be: `adb devices` on the machine this was written on reports an
online device, so a naive "run every script with its arguments filled in" test drives real
hardware.

```
$ adb devices
<DEVICE>                device                            observed
```

**What happened.** An early version of the CLI contract test executed `coldstart.py` with its
requirements filled in. The script found the single online device, adopted it, started
`adb logcat -v threadtime`, wrote a 927,893-byte `logcat.txt`, captured four frames, and left
**five orphaned `adb logcat` processes** behind when the 12 s timeout killed the parent. The
whole mess landed in `skills/apk-reverse/scripts/`, which is another owner's write scope.

**What was cleaned up.** The five orphaned `adb logcat` processes were terminated, and the
directory the script created (`skills/apk-reverse/scripts/coldstart/`, containing `logcat.txt`
and `shots/f0*.png`) was removed. Verified: `git status` on `skills/apk-reverse/scripts` no
longer lists it.

**What changed in the design.**

- Every child process now runs in a private temporary working directory, so a script that
  defaults an output path relative to cwd cannot write into the shipped tree. This is the
  general fix; the incident was one instance of the class.
- `contract.DEVICE_OR_NETWORK_BOUND` — 15 scripts — is never executed with complete arguments.
  `--help` and an unknown flag are still exercised for all of them, because argparse answers
  both before any device call is reached, and that was verified for every script individually:
  `--help` returned in well under a second and an unknown flag returned 2 for each.

**Residual risk, stated plainly.** This is a blocklist, not a sandbox. A script not on the
list that grows device access would be executed. The list is checked against the tree on every
run (a script that appears without being classified becomes a new pass or a new xfail rather
than a silent gap), but it is maintained by hand.

Fifteen scripts are device- or network-bound and their argument-complete behaviour is
`unverified` here. What that means concretely: this harness cannot tell you that a repack
installs, that an anti-debug patch survives, that a hook fires, or that a tracer reports
blocks. Those live in `tests/benchmark.md`, and the `unverified` marks there are unchanged by
anything in this directory.

### 3.2 CI has never executed: `unverified`

`.github/workflows/ci.yml` exists and is syntactically valid — verified locally:

```
$ python -c "import yaml,io; yaml.safe_load(io.open('.github/workflows/ci.yml',encoding='utf-8'))"
ci.yml: valid YAML                                                observed
```

and every command it runs was executed by hand on this machine:

```
$ python check_refs.py          exit 0                             observed
$ python check_budget.py        exit 0  ("0 failure(s), 0 warning(s), 3 note(s)")   observed
$ python check_repo.py          exit 0  (with PYTHONUTF8=1; see §5.1)               observed
$ python -m pytest -q           exit 0  ("596 passed, 153 skipped, 26 xfailed")     observed
```

It is still `unverified` as a workflow, and the blocker is specific: there is no GitHub Actions
runner reachable from this machine, the workflow has not been pushed (this work item is
forbidden from committing), and no local runner (`act`) is installed. What cannot be claimed
until the first push: that `actions/setup-python` resolves both matrix versions, that the gates
behave identically under a Linux UTF-8 locale, and that the suite's timing stays inside any
runner limit. The last two matter because the gates behave *differently* on this Windows host —
see §5.1 — and because the CLI suite spawns roughly 200 subprocesses.

A remote does exist (`origin` → `github.com/newliver666/apk-reverse`), so the workflow will run
on the first push; nobody has observed it do so.

### 3.3 Agent behaviour: `unverified`, and deliberately out of scope

`skills/apk-reverse/evals/evals.json` is a skeleton: three cases with expected outputs and
grading assertions, and an explicit statement **in the file** that nothing in it has ever been
executed. No with-skill arm and no without-skill arm has been run. Running them means running
the agent twice per case and grading transcripts, which was excluded from this pass by decision
(`REBUILD-BRIEF.md` §2, the do-not-do list). The file carries its own run procedure.

### 3.4 The 153 skips, by category

| Count | Reason | Reading |
|---|---|---|
| 60 | device/network bound, not executed | 15 scripts × 4 scenarios. Deliberate; see §3.1. |
| 40 | requires no argument, so the contract does not apply | 10 scripts × 4 scenarios. Requiring exit 2 from `doctor.py` or `scan_leaks.py` with no arguments would invent a rule the contract does not state. |
| 34 | does not advertise `--json` | the 34 of 46 scripts with no `--json` flag. That is the §1.6 problem, not a harness gap. |
| 11 | `--json` advertised but the path needs a device or a sample | includes `capabilities.py`, added during this pass. The shape is not asserted because the run that would reach it needs a target. |
| 8 | hand-written usage, argv not derivable | `dexutil.py` and `smtool.py`, 4 scenarios each. Their usage line is prose, so the missing-input argv is not machine-derivable. `devsh.py` and `patch_smali.py` share the trait but are already covered by row 1. |

Total 153, which is why the headline is "passed, skipped, xfailed" and not "passed".

---

## 4. The exit-code work order — 26 xfails

These are not flaky tests. Each is a script on the tree that does not meet the repository
contract in `REBUILD-BRIEF.md` §4 (`0` success, `1` target result failed, `2` bad
arguments/input, `3` environment capability missing, `4` internal error). The xfail reason
carries the measured value, so `pytest -q -ra` prints the work order at any time.

**A. `--help` does not exit 0 — 4 scripts.** A hand-written parser rather than argparse, so
`--help` falls through to "unknown argument". None of them prints a traceback, so this is a
contract gap and not a crash.

`devsh.py`, `dexutil.py`, `patch_smali.py`, `smtool.py` — measured `2`, expected `0`.

**B. A missing input file exits 1 instead of 2 — 13 scripts.** The distinction matters to a
calling agent: 1 means "your target failed", 2 means "your invocation was wrong". Reporting a
typo in a path as a target failure sends the next agent to debug the sample.

`apk_diff.py`, `dart_disasm.py`, `dart_pool_strings.py`, `dex_classdiff.py`,
`dex_dump_validate.py`, `dex_find_insn.py`, `dex_mem_scan.py`, `dex_strpatch.py`,
`elf_plt.py`, `native_crash.py`, `patch_smali.py`, `stalker_report.py`, `svc_scan.py` —
measured `1`, expected `2`.

**C. An uncaught exception instead of a clean report — 7 scripts.** The user-visible
difference: a traceback instead of a sentence.

`dart_pool_strings.py`, `dex_classdiff.py`, `dex_find_insn.py`, `dex_mem_scan.py`,
`dex_strpatch.py`, `patch_smali.py`, `stalker_report.py` — all `FileNotFoundError` (on Windows,
`dex_mem_scan.py` reports `WinError 3`).

**D. `--json` without a `status` field — 1 script.**

`preflight.py --json` returns top-level keys `rows` and `worst`, with no `status`. Per §4 the
document must carry `status` (and ideally `exit_code`, `capability`, `evidence`, `warnings`,
`next_action`). For contrast, `doctor.py --json` was measured during this pass and *does* carry
`status`, and now exits 3 rather than 0 when a capability is missing — the unified convention
is arriving script by script.

**E. `su` quoting — 1 item, outside the exit-code list.** `devsh.su` wraps in double quotes and
escapes only `"`, so `;`, `$()`, backticks and `|` from a `--pkg`-style value still reach the
device shell. `coldstart.Device.shell` uses the POSIX single-quote escape and does neutralise
them. Two helpers, two strategies — the `device_shell()` unification item. The contrast is
asserted in `tests/integration/test_adb_command_construction.py::TestDevshSuQuotingGap`.

Nothing in this list was fixed by this work item: every one of those scripts belongs to another
owner, and a test that quietly repaired its subject would stop being a test.

---

## 5. Defects found and registered, not fixed

### 5.1 `check_repo.py` misreports a script as crashing under a non-UTF-8 console (`observed`)

```
$ python check_repo.py
  - E:\apk-reverse\skills\apk-reverse\scripts\dex_strpatch.py --help crashed:
== result: 1 problem(s) ==
exit=1
```

with, above it, `UnicodeDecodeError: 'gbk' codec can't decode byte 0x94 in position 63` raised
inside `subprocess`'s reader thread. The gate spawns each script with `text=True` and no
explicit encoding, so on this host the child's output is decoded with GBK. One script's
`--help` text is not GBK-decodable, and the gate attributes the failure to that script. The
script itself is fine:

```
$ python skills/apk-reverse/scripts/dex_strpatch.py --help ; echo $?
0                                                                 observed
```

Pinning the codec fixes it:

```
$ PYTHONUTF8=1 python check_repo.py
== result: 0 problem(s) ==
exit=0                                                            observed
```

`PYTHONUTF8: "1"` is therefore set in `ci.yml`. Two caveats: CI runs on Linux, where the default
codec is already UTF-8, so this is a portability fix for anyone running the gates on Windows
rather than a fix for the CI run; and `check_repo.py` is in the Lead's write scope, so the
underlying `text=True` call is not changed here.

### 5.2 `native_crash.py` overwrites `regs['pc']` with a backtrace frame (`observed`)

Register extraction scans every line of a crash block with one permissive pattern, so a
`#NN pc <hex>` backtrace line matches too and the last one wins. On the fixture, the register
dump's own `pc 00000000007a111128cc` is not what `regs['pc']` holds; `0x55488` — the last
frame's pc — is. The verdict is unaffected (the arranged-fault hint keys off the fault address
and the registers holding it, and neither is `pc`), but a reader who trusts `regs['pc']` as the
faulting instruction pointer is misled. Pinned in
`tests/integration/test_no_device_flows.py::TestTombstoneParsing`.

### 5.3 `coldstart.installed_facts` `versionCode` swallows the rest of the line (`observed`)

The extraction is `r'\s*(versionCode|...)=(.*)'`, so on a real `dumpsys package` line —
`versionCode=42 minSdk=24 targetSdk=34` — the value is the whole remainder, not `42`. It still
works as the before/after fingerprint the caller uses it for, but the field name overstates
what it holds. Pinned in `tests/integration/test_adb_command_construction.py`.

### 5.4 The leak scanner reports one `ip:port` twice (`observed`)

`192.0.2.10:8080` satisfies both `plain_addr` (`ip:port`) and `plain_addr_ipliteral` (bare
IPv4), because the literal rule's trailing `(?![\w.])` is not violated by a colon. Both hits
are `weak`, so the default gate stays green; the effect is report volume, not a wrong verdict.
Pinned, with the reasoning, in `tests/unit/test_scan_leaks.py`.

### 5.5 `usb_net_proxy.py` does something with no arguments (`observed`)

With no arguments it neither prints usage nor exits: it ran past both a 12 s and a 20 s timeout
during probing. Every other script either requires arguments or prints its own documentation.
Not diagnosed further here — the fix belongs to whoever owns that script. It is classified as
device/network bound, so the suite does not execute it.

### 5.6 Stray artifacts in the tree that this work item did not create (`observed`)

Found while checking its own side effects, left in place because they are not this work item's
to delete and may belong to a concurrent one:

- `--help/` at the repository root, containing `planted/{package,device,appkey,endpoint,path,token}.txt`
  and `exempt/benign.txt`. The names say "leak-scanner decoy set", so some scanner test wrote
  its fixtures into a directory literally named `--help` — most likely an argument-parsing bug
  in that test, not a scan result.
- `skills/apk-reverse/scripts/example.preferences_pb` and `skills/apk-reverse/scripts/snapshots/`
  (containing `snap.png`, 3.97 MB, and `_snap_ui.xml`). Timestamps 01:17 and 01:18, unchanged
  across this work item's later runs, so they are not its output.

---

## 6. The established regression marker

The red line recorded in `REBUILD-BRIEF.md` §2 is reproduced by the suite rather than
re-invented:

```
$ python skills/apk-reverse/scripts/dex_patch_bytes.py \
    tools/_work/bench/l1l3/dex/classes.dex \
    --spec tools/_work/bench/l1l3/l1_root.spec.json \
    -o <tmp>/classes.patched.dex
== header checksum 0x7fb7d9fa -> 0x86e1d928
   signature b7fafe72cb521450 -> eb632328fd1ba03c
   self-verify: checksum_ok=True signature_ok=True
== wrote <tmp>/classes.patched.dex (5528 bytes, delta 0)

$ sha256sum <tmp>/classes.patched.dex
67ae1e58e7a44777e5ac8f9f823ab21e55e56c6122d2d64c3627232d902a2bba        observed
```

Identical to the stored `tools/_work/bench/l1l3/dex/classes.patched.dex`, byte for byte. The
suite asserts the hash **and** where the difference is allowed to be: bytes 8..32 (checksum and
signature, recomputed) plus the four bytes at `0x9d0`. Two of those four keep their original
value — `39000e00` → `00000000` clears two bytes — and a recomputed checksum can keep a byte by
coincidence, so the assertion is containment plus "these must have moved", not equality of the
diff set. That is the honest form: an equality assertion would fail on a correct build.

The test copies the bench input into `tmp_path` before patching, so a test run cannot overwrite
the stored expectation.

`tools/_work/bench/**` is git-ignored, so on a fresh checkout and in CI this test **skips** with
the printed reason instead of turning red. A regression marker that fails because a sample is
absent is a marker people learn to ignore.

---

## 7. Files added by this work item

```
pytest.ini                                            repository root
tests/README.md                                       how to run it, and the ground rules
tests/run_tests.py                                    entry point; exits 3 without pytest
tests/conftest.py                                     fixtures, subprocess runner, isolated cwd
tests/unit/test_dexutil.py
tests/unit/test_protobuf_decode_raw.py
tests/unit/test_blob_decode.py
tests/unit/test_scan_leaks.py
tests/unit/test_dex_patch_bytes_regression.py
tests/cli/contract.py                                 usage parsing and the contract constants
tests/cli/test_cli_contract.py
tests/integration/test_adb_command_construction.py
tests/integration/test_no_device_flows.py
tests/fixtures/tombstone_sample.txt                   synthetic, 1.3 KB
tests/fixtures/logcat_sample.txt                      synthetic, 1.0 KB
.github/workflows/ci.yml
skills/apk-reverse/evals/evals.json                   skeleton, never executed
```

Not touched: `skills/apk-reverse/scripts/**`, `tests/test_so_constpatch.py`,
`tests/fixtures/apk/**`, `SKILL.md`, `README.md`, the root `check_*.py` scripts. No commit, no
push. The only write this work item made inside the shipped tree was its own accident (§3.1),
and it was reverted.

Fixture budget: two text fixtures, 2.3 KB total, well under the 32 KB per-file limit. The leak
decoys are synthesised at run time and are not committed.
