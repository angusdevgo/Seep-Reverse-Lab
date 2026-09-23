# Extension verification — truthful environment gates, documented-command validation, and APK rebuild safety

Covers the P0 pass that replaced the optimistic half of `skills/apk-reverse/scripts/doctor.py`
with a probed capability registry, added `check_commands.py` at the repository root, and — in the
same round, by teammate `zip-safety` — replaced the APK-rebuild writer inside
`skills/apk-reverse/scripts/so_constpatch.py`. Strength labels are the ones this directory's
README defines: **observed** (reproduced here, exact command and output recorded), **inferred**
(follows from observed facts, the step itself was not executed), **unverified** (assumed or
reported elsewhere, not independently reproduced).

Two gates depend on the material below, which is why the report was allowed to become worse
looking: G2 (environment gating) reads the capability verdicts, and the documented-command check
is what keeps a reader from following a page instead of the tool. "Documented command" below means
a script invocation written in a code block or inline backtick in a markdown file — the shape
`check_commands.py` extracts and validates.

Reference environment for this pass: Windows 11 / AMD64, Python **3.14.0**, JDK **17.0.4.1**
(`java`/`javac` only, on the Oracle launcher shim path), `adb` 1.0.41 with one attached
`arm64-v8a` device at API 30, Frida **16.7.19** host package, capstone present, Android
build-tools unpacked at a local directory but **not** on `PATH`. Workbench artifacts live in
`tools/_work/truth-gates/` and `tools/_work/zip-safety-out/` (not part of the skill; `tools/` is
gitignored, so those paths are an operation record rather than something a reader can open).

---

## 0. Summary of what this pass established

| Claim | Label |
|---|---|
| The committed `doctor.py` registered **28** scripts against **51** files actually in `scripts/` (46 `.py` + 5 `.js`) | observed |
| Its capability table derived `repack + sign` and `smali round-trip` from `java` alone; on a JDK-only `PATH` it reported **both as OK** while `keytool`, `jarsigner`, `zipalign`, `apksigner` and all eight smali jars were absent | observed |
| The rebuilt `doctor.py` scans the directory, so `registered/checked = N / N` equals the file count; on this host `52 / 52` (47 `.py` + 5 `.js`, the new `capabilities.py` included) | observed |
| Capability verdicts now come from a real `requires` closure with an executable next action and a cost estimate; 16 capabilities are resolved, and the same JDK-only host reports `repack_signed` and `smali_roundtrip` **BLOCKED** | observed |
| `check_commands.py` reads each script's `argparse` interface with `ast` (no script executed to learn its interface) and validates **139** documented commands across 76 markdown files against 39 interfaces, with 0 drift after the one known drift was fixed | observed |
| The drift the checker was written for — `sig_probe.py --live --pkg <pkg>` — is reproduced **from `git show HEAD:`** of the pre-fix page and is reported at the right line | observed |
| The pre-existing `so_constpatch.py` APK writer dropped per-entry zip metadata and lost `resources.arsc` alignment; the replacement keeps metadata byte-for-byte and the alignment gate passes | observed |
| `zipalign -c -v 4` from the Android build-tools agrees with that verdict independently (old writer `rc=1 FAILED`, new writer `rc=0`), re-checked in this pass on artifacts produced by the other teammate | observed |
| `repack.py:_needs_alignment` uses `^lib/[^/]+\.so$`, which never matches the real `lib/<abi>/x.so` layout, so its alignment filler is dead code on real APKs | observed (reported, **not** fixed — outside every current write scope) |
| A real `pm install` of any rebuilt artifact | not done — no install was attempted in this pass |

---

## 1. The doctor was optimistic, and a gate trusted it

### 1.1 A hand-written inventory that could only go stale

The committed version carried `script_dependencies()` returning a literal dict of 28 entries. The
directory held 51 files. The 23 absent from the table were not peripheral: they included
`dex_patch_bytes.py`, `dex_find_insn.py`, `dex_dump_validate.py`, `dex_mem_scan.py`, `dexutil.py`,
`protobuf_decode_raw.py`, `java2c_probe.py`, `vmp_diff_harness.py` and `scan_leaks.py` — nine of the
scripts this skill exists for. The summary line read `scripts runnable here: 28 / 28`, so the report
looked like complete coverage of a set that was less than half the set.

The replacement cannot drift in that direction, because the list *is* the directory:

```
$ python skills/apk-reverse/scripts/doctor.py --scripts
--- scripts ---
  directory: E:\apk-reverse\skills\apk-reverse\scripts
  registered/checked = 52 / 52   (.py=47, .js=5)
  ok=33  partial=13  blocked=6  unknown=0
```

A file whose dependency set cannot be decided is printed as `UNKNOWN` and still counted in the
denominator; `unknown=0` here is a measurement, not an assumption. Dependencies come from an `ast`
pass over imports checked against `sys.stdlib_module_names`, plus a narrow scan for host tools
(`resolve_tool('java')`, the program of a `subprocess` list) against a known-tool set. Modules are
never imported to probe them, because importing the probe target is itself a side effect — `frida`
starts threads and enumerates devices at import time.

### 1.2 The formula that ignored the toolchain — decisive reproduction

`doctor.py:319-320` (committed):

```python
caps['repack + sign']    = bool(tools['java']['path']) and py['ok']
caps['smali round-trip'] = bool(tools['java']['path']) and py['ok']
```

Neither ability follows from `java`. To show that the mechanism was wrong rather than merely lucky,
the committed script was extracted from git and run with a `PATH` holding a JDK and nothing else:

```
$ git show HEAD:skills/apk-reverse/scripts/doctor.py > tools/_work/truth-gates/doctor-HEAD.py
$ set PATH=C:\Program Files\Common Files\Oracle\Java\javapath;C:\Windows\System32;C:\Windows;C:\Python314
$ python tools/_work/truth-gates/doctor-HEAD.py

--- capabilities ---
  [OK ] static (dex/zip/strings)
  [OK ] repack + sign          <-- no keytool, no zipalign, no signer on this PATH
  [OK ] smali round-trip       <-- none of the eight jars exist on this host
  [OK ] native ELF patching
  [-- ] jadx decompile
  ...
```

The rebuilt script, on the **same** restricted `PATH`:

```
  [BLOCKED] repack_signed     Repack, align and sign an APK
            missing : tool:keytool -- not on PATH or APKREV_TOOLS
                      next: the directory on PATH (C:\Program Files\Common Files\Oracle\Java\javapath)
                            is a launcher shim, not a full JDK bin/: put %JAVA_HOME%\bin first, or
                            install a JDK - a JRE ships no keytool   [~2 min, unverified]
            missing : tool:zipalign -- not on PATH or APKREV_TOOLS
                      next: build-tools are already unpacked here but are not on the search path:
                            set APKREV_TOOLS=E:\tools\android-14;E:\tools\bin (found: ...)   [~0 min, observed]
            missing : artifact:signer -- tool:apksigner (not on PATH or APKREV_TOOLS);
                            jar:uber-apk-signer (uber-apk-signer.jar not found)
            reduced : tool:jarsigner -- not on PATH or APKREV_TOOLS
  [BLOCKED] smali_roundtrip   Smali disassemble / assemble round-trip
  [OK     ] repack_unsigned   Repack an APK without signing (--no-sign path)

  ok=5  partial=1  blocked=10  (of 16 capabilities)
```

`repack_unsigned` staying OK is deliberate and true: `repack.py --no-sign` is `zipfile` plus the
STORED-entry rules and needs no Java tooling at all. A gate that reported the whole file unusable
would have been a pessimism of its own.

### 1.3 The closure is the point, not the atom list

`capabilities.py` is the single registry: 16 capabilities, each a `name`, a `note`, the scripts it
serves, `required` atoms, `optional` atoms, and `depends_on` capabilities that are expanded
recursively. `repack_signed` depends on `repack_unsigned`, so it cannot be OK while the repacking it
is built on is not. Atoms cover the four kinds that actually decide something here: an importable
module, a tool resolvable on `PATH` or `APKREV_TOOLS`, a jar set, a device property (present,
rooted, frida-server running), a repository file, and one **input artifact** that no host can
install — the Dart AOT snapshot dump, which is why `dart_aot_full` reports BLOCKED with
`build blutter … or run the pinned aotopsy front end` rather than a download link.

`status ∈ ok | partial | blocked`. A missing *required* atom blocks. A missing *optional* atom
degrades: `static_native` stays usable without `capstone` and names the part that is not
(`svc_scan.py` refuses to run without it; the caller index in `dart_disasm.py` works).

Two probes were worth getting right rather than guessing:

- A JDK whose launcher shim is on `PATH` (`...\Oracle\Java\javapath`) exposes `java` and `javac`
  but not `keytool` or `jarsigner`. The registry probes those separately and, on failure, says the
  shim directory is a shim instead of reporting a missing JDK.
- Build-tools present but unexposed are found by searching the usual SDK locations plus a
  conventional `tools/` directory, and the next action becomes the exact assignment
  (`set APKREV_TOOLS=E:\tools\android-14;E:\tools\bin`) with a measured cost of `~0 min`, rather
  than "install build-tools".

That last hint was verified end to end: with `APKREV_TOOLS` set, `repack_signed` loses the
`zipalign` and `signer` blockers and keeps only `keytool` — which is the honest residual on this
host, because the JDK really is a shim install.

### 1.4 Cost estimates carry their own strength

Every install hint carries `est_minutes` with a `basis`. `observed` means measured in this
repository: the `--unsafe-rebuild`-independent blutter build is **≈78 s** end to end
(`TOOL-VERDICTS.md`), and exposing an already-unpacked build-tools directory is 0 minutes because
the search found it. Everything else is labelled `unverified` and is a planning aid only: a guessed
ten minutes printed as a measurement is the same class of error as a capability verdict derived
from the wrong tool.

Per-capability `est_basis` is `mixed` when the missing atoms disagree, which is what makes
`repack_signed` read `~12 min, mixed` rather than an authoritative-looking single number.

### 1.5 Exit codes and the token

`doctor.py` and `capabilities.py` both follow this round's convention: `0` = nothing blocked
(`partial` does not fail a gate, and the counts are printed so it cannot hide), `3` = at least one
capability blocked, `2` = usage, `4` = internal. The last line is `RESULT=env_ok` /
`env_partial` / `env_blocked` / `usage_error` / `internal_error`, and the usage-error path keeps the
token too — `argparse` would otherwise exit 2 with nothing a caller can branch on.

`--json` carries `{status, exit_code, capability?, evidence[], warnings[], next_action?}` plus, for
compatibility, the keys the old report used (`python`, `tools`, `jars`, `device`, `capabilities`,
`scripts`). `capabilities` changed shape on purpose — the old flat `{name: bool}` map *was* the
optimism — and a `capabilities_legacy` map gives the same information as `{id: "ok"|"partial"|"blocked"}`
for any consumer that only wants the verdict.

---

## 2. `check_commands.py` — the commands a reader is told to run

### 2.1 What it reads, and from where

`check_repo.py` proves that a referenced path resolves and every script answers `--help`. Neither
can see a documented command whose flags no longer exist, and the repository shipped exactly one for
a long time. `check_commands.py` closes that gap by reading each script's real interface with `ast`:

- `ArgumentParser()` / `add_argument()` calls are parsed statically, so **no script is executed to
  learn its interface**;
- `add_subparsers()` / `add_parser('name')` are followed, and a sub-parser's flags are attributed
  to that sub-command rather than merged into the parent (one variable reused across several
  sub-parsers is handled, and the parameters are then attributed to the group as a whole);
- `action=store_true|store_false|count|help|version` and `nargs=0` mean the flag consumes no value;
- a script with no `argparse` at all (a hand-rolled `sys.argv` parser: `smtool.py`,
  `dex_strpatch.py`) falls back to parsing its own `--help` output, and `smtool.py`'s `--cp` is
  recovered that way. The probe runs in a **throwaway directory**, because a probe must not leave
  anything behind — a script that reads its first argument as an output directory would otherwise
  create one named after the flag.

Documented commands are extracted from fenced code blocks and inline backticks in `README.md`,
`skills/**/*.md` and `docs/**/*.md`. A documented line is split on `&&`, `||`, `;` and `|`, and a
redirection truncates the segment: `python check_repo.py && python check_refs.py` is two commands,
not one with two extra positionals. `<PKG>`-style placeholders are kept as single tokens, because
reading `<pkg>` as a shell input redirect truncates the command at `--pkg` — and a truncated
command checks clean, which is how the checker would have missed the one drift it was built for.

### 2.2 Allowance rules that keep it honest rather than noisy

- argparse accepts a **unique prefix** of a long option, so `--max` passes for `--max-depth`; an
  *ambiguous* prefix is reported.
- `-h` / `--help` are always accepted.
- A flag that needs a value does **not** consume an option-looking token; argparse reports
  "expected one argument" instead. This is the rule that makes `--live --pkg <pkg>` report `--pkg`
  rather than swallow it as the value of `--live`.
- Positional counts are computed from the declared positionals (with `nargs=None|int|'?'|'*'|'+'`)
  and are reported as **warnings**, never as drift: a static count can be thrown off by a
  placeholder or an elision, so it does not get to fail a gate. It is skipped entirely when any
  option has a variable `nargs` or the interface came from `--help`.

### 2.3 The drift it exists for, reproduced from git

The page was already fixed by the time this checker ran, so the pre-fix revision is taken from git
and checked as a file:

```
$ git show HEAD:skills/apk-reverse/references/signature-derived-keys.md > tools/_work/truth-gates/sig-derived-HEAD.md
$ python check_commands.py --fix-report --path tools/_work/truth-gates/sig-derived-HEAD.md
tools\_work\truth-gates\sig-derived-HEAD.md:61	sig_probe.py	unknown flag --pkg	closest known: --apk	cmd: python scripts/sig_probe.py --live --pkg <pkg>
RESULT=commands_drift
```

Line 61, the right script, and the correct suggestion (`sig_probe.py` takes `--live PKG` and has
never had `--pkg`). A second, synthetic fixture proves the check is not a single-rule special case:

```
$ python check_commands.py --fix-report --path tools\_work\truth-gates\NEGATIVE-unknown-flag.md
...:4	sig_probe.py	unknown flag --pkg	closest known: --apk	cmd: python skills/apk-reverse/scripts/sig_probe.py --live --pkg <pkg>
...:5	dex_classdiff.py	unknown flag --original	closest known: --max-list	cmd: ... --original a.dex --patched b.dex
...:5	dex_classdiff.py	unknown flag --patched	closest known: --max-list	cmd: ... --original a.dex --patched b.dex
...:7	skills/apk-reverse/scripts/does_not_exist.py	unknown flag missing-script	closest known: -	cmd: python .../does_not_exist.py --x 1
RESULT=commands_drift
```

Exit code 1, one machine-readable line per finding, with the document line, the command, the
unknown flag and the closest known flags — which is what `--fix-report` is for.

### 2.4 Coverage on the real repository

```
$ python check_commands.py
docs        : 76 markdown file(s)
scripts     : 39 argument table(s) read, 2 without a readable table
commands    : 139 checked (139 clean, 0 drift, 0 warning)
skipped     : 24 workbench, 1 external, 1 quoted, 0 unverifiable, 30 not a script invocation
RESULT=commands_ok
```

`139 checked` counts every invocation resolved to a readable interface, not merely the ones with
findings; a pass that reports only its findings cannot tell "clean" from "nothing looked at".
Everything skipped is printed with its reason, and the reasons are of four kinds:

- **workbench** (24): the script lives under `tools/`, which `.gitignore` excludes, so a reader
  cannot open it and a missing file there is not drift. A bare filename that only exists under
  `tools/` is caught too, because those evidence records refer to workbench scripts by name.
- **not a script invocation** (30): `python -m …`, `python -c "…"`, an elided `python ... --flag`,
  or an output line that merely starts with `python`.
- **external** (1): `python scripts\init_env_win.py` in the blutter build record is a path inside
  *another* repository's checkout — the record's preceding line is `git clone --depth 1
  worawit/blutter`. Each such entry carries its reason in an auditable table that the report
  prints, because a silent allow-list is indistinguishable from a missed drift.
- **quoted** (1): `FINDINGS.md` quotes `python scripts/sig_probe.py --live --pkg <pkg>` *as the
  defect it records*. It is evidence, not an instruction; the page's own sentence says the script
  has no `--pkg`. Same auditable-table treatment.

The two scripts with no readable table are listed by name. A script with no flags has nothing that
can drift, so its invocations pass without being checkable — stated so the edge of the check is
visible instead of implied.

### 2.5 Defects the negative tests found in the checker itself

Each of these produced a *false clean* on the pre-fix page, and each was found by testing the
checker against a known-bad document rather than by reading its code.

| # | Defect | How it surfaced | Fix |
|---|---|---|---|
| 1 | `<pkg>` was read as a shell input redirection, truncating the command at `--pkg`; the truncated command then checked clean | the git-HEAD reproduction reported no drift at all | `<...>` with no interior space is treated as a placeholder token; `>`/`>>` still truncate |
| 2 | A flag that takes a value consumed the *next* token unconditionally, so `--live --pkg` made `--pkg` the value of `--live` | the same reproduction, after fix 1 | an option-looking next token is not consumed, matching argparse's "expected one argument" |
| 3 | The whole documented line was read as one argv, so `&&`, the second `python`, and a redirect target entered the positional count | 3 warnings about `check_repo.py && python check_refs.py` and `… --json > out.json` | lines are split on `&&`/`\|\|`/`;`/`\|` and truncated at a redirection |
| 4 | `docs/**` records reach workbench scripts as `../../tools/_work/…`, which resolves to a real file, so they were reported as unverifiable repository scripts | 17 spurious entries | a resolved path under `tools/` is classified workbench, and paths are `realpath`-normalised so `dexpatch/../smtool.py` is one entry, not two |
| 5 | `commands_checked` counted only commands *with findings*, so a clean run reported `3 checked` instead of 139 | comparing the summary against the extraction dump | every resolved invocation is emitted as a `clean` record and counted |
| 6 | `--help` fallback probes ran with `cwd` at the repository root | reasoning about probe side effects, then confirmed | the probe runs in a temporary directory |

Defect 1 is the instructive one: a checker whose parser silently shortens a command reports success
for exactly the inputs it was written to reject, and nothing in its own output looks wrong. The
defence is not more careful reading, it is a fixture that is known to be bad.

### 2.6 A second blind spot, found by a reviewer reading this gate's output

A reviewer reported seven "drifting" commands. Reproducing them split the report three ways, and the
middle category is the one worth reading.

**Not reproducible.** `python tests/run_tests.py -q` runs: `run_tests.py` forwards what it is given
to pytest (`args = list(argv[1:]) or ["-q"]`), and its usage block documents exactly that. `dcc.py`
is an external checkout, not a script this repository ships — the form the record uses is:

```
$ cd tools/_work/bench/repos/dcc
$ python ./dcc.py <SAMPLE_DIR>/baseline.apk --no-build --dynamic-register
```

**Real, and fixed.** Seven commands in two evidence records named a **workbench** script with no path
at all (`$ python analyze_pair.py`, `b2_measure.py`, `ttd_attach.py`, `make_skeleton.py`). Those files
exist under `tools/`, which `.gitignore` excludes, so a reader copying the command from the
repository root gets `No such file`. Two of those documents wrote the correct path elsewhere, so they
disagreed with themselves.

**The part that matters: this gate had been scoring those `ok`.** `resolve_script()` tried the
*document's own directory* first, so a bare `analyze_pair.py` inside `docs/tool-verification/`
resolved to `tools/_work/bench/unpack/b3/analyze_pair.py` — a real file — and passed. The fix is not
a stricter regex but a corrected resolution order plus a corrected classification:

1. Resolution now follows the order a **reader** would try: repository root, then the skill's script
   directory, then the document's own directory (which is what `../x.py` in a nested README means).
2. A bare name that only resolves under `tools/` is `unqualified-workbench`, and it counts as
   **drift, not a skip** — a one-token fix that a reader cannot run. A first attempt classified it as
   a low-confidence warning, which would have left all seven in place.
3. The one honest exception is pinned too: a block that opens with `cd tools/_work/bench/repos/dcc`
   tells the reader where to stand, so a bare `python dcc.py` after it is correct. That is skipped as
   `workbench-after-cd`.

### 2.6a The same gate failed on CI and passed locally, and the reason is worth keeping

The first version of the fix above shipped and CI went red on `check_commands.py` — in both the 3.11
and 3.13 jobs — while the identical command passed on the machine that wrote it. The difference is
`tools/`: it is gitignored, so a clean checkout does not have it, and **recognition of a workbench
artifact by filename required the tree to exist**. On the developer's box `dcc.py` matched a name
under `tools/` and was skipped as `workbench-after-cd`; on CI nothing matched, it fell through to
`missing-script`, and the gate reported drift for three quoted lines in this very file.

Two lessons, both now enforced rather than remembered:

- **A check whose verdict depends on a gitignored directory is not a check.** The classification is
  now computed from the **document** as well: `qualified_basenames()` collects every `.py` the text
  itself writes *with* a path, and a bare name that appears in that set is a shorthand the document
  already explains — so it skips identically on a clean checkout and on a populated one.
- **A gate that cannot be run in the same shape as CI will disagree with CI.** Reproduce the CI
  condition locally before believing a green run: `mv tools /tmp/hidden && python check_commands.py`
  is the whole experiment, and it takes seconds. That is what found this, after the fix had already
  been pushed.


**Two defects of this pass's own, found while fixing it.** A `--json` run printed the `RESULT=` token
*after* the JSON document, so `--json | jq` failed with `Extra data`; the token is gone from that path
and the status is a field in the document instead. And the fix's own substitution left four literal
backslashes before `$` in the two files — a reader would have copied them.

`tests/integration/test_check_commands_gate.py` pins the resolution order, the drift classification,
the `cd` exception, and a clean pass over the committed tree, so this blind spot cannot return
silently.

### 2.7 What this check does not cover

- It validates **flags and (weakly) positional counts**, not semantics. A command with correct flags
  and a wrong path still passes; so does a documented `--duration 14` where the useful value is
  different.
- A script whose interface is neither declarative nor printable is outside the check; the two
  current cases are listed by name rather than folded into the pass count.
- It does not verify that a command *works* — only that the script would not reject it as unknown
  arguments. Running the 139 commands remains a benchmark-pass activity.

---

## 3. APK rebuild safety in `so_constpatch.py` (teammate `zip-safety`; re-checked here)

### 3.1 What the committed writer did

```python
# so_constpatch.py:204-218, before this round
with zipfile.ZipFile(out_path, 'w', zipfile.ZIP_DEFLATED) as dst:
    for item in src.infolist():
        blob = new_data if item.filename == entry else src.read(item.filename)
        dst.writestr(zipfile.ZipInfo(item.filename, date_time=item.date_time),
                     blob, item.compress_type)
```

A new `ZipInfo` built from a filename and a timestamp carries nothing else, so `extra` and
`external_attr` are lost; `create_system`, `internal_attr` and the version fields are reset; and
every entry is re-compressed as DEFLATED, so a STORED `resources.arsc` may stop being STORED and
lose its 4-byte data alignment. There was no `extractNativeLibs` check, no alignment check, and no
pointer at `scripts/repack.py`.

### 3.2 What replaced it

The writer now emits the local headers and the central directory itself, because alignment is a
property of the local header length that `zipfile` cannot express. Per entry it reproduces the raw
local name bytes, both `extra` fields, `external_attr`, `internal_attr`, `create_system`,
`create_version`, `extract_version`, the comment, the DOS time/date words and the general-purpose
flags (the data-descriptor bit is cleared, since the size is known up front). An untouched STORED
entry's compressed stream is copied verbatim in 1 MiB chunks, so its CRC and `compress_size` are
identical by construction rather than by luck. Only the named entry is ever re-compressed, and only
if it was DEFLATED. Alignment padding goes into a private local extra record (`0xCA`) so the
original extra field stays a byte-for-byte prefix.

### 3.3 The offset that matters — a correction to state plainly

The alignment contract is the **data offset** of the entry, not its local-header offset. This
matters because the two differ by the header length plus the name, and real archives routinely have
an unaligned header offset:

```
r2pay (input, 435 entries):  resources.arsc  STORED  data offset 0x3cec08  header_offset 0x3cebce
                             data offset % 4 == 0  OK      header_offset % 4 == 2
```

`zipalign`, `apksigner` and `repack.py`'s own `check_alignment` all test the data offset. So the
rule this tool enforces is: `resources.arsc` must be STORED and its **data offset must be a
multiple of 4**; any other STORED entry that arrived aligned must still be aligned after the
rebuild. The alignment predicate differs from `repack.py`'s in one substantive way —

```
always   : resources.arsc                        (Android R+ install gate)
always   : STORED lib/**/*.so                    (extractNativeLibs=false maps them in place)
preserved: any other STORED entry already at a 4-byte data offset
never    : DEFLATED entries, and STORED entries that arrived unaligned
```

— and it uses `^lib/.+\.so$` where `repack.py` uses `^lib/[^/]+\.so$`. The latter matches
`lib/x86/libfoo.so` but **not** `lib/arm64-v8a/libfoo.so`, because the ABI directory is a second
path segment: on a real APK that pattern matches nothing, so the alignment filler it guards would
never fire. That is a live defect in `repack.py` (`_needs_alignment`, and the
`check_alignment`/`zip_report` paths that inherit the predicate), reported rather than fixed
because `repack.py` is in no one's write scope this round. It is worth fixing before the refusal
message tells users to switch to that tool.

### 3.4 Evidence, fixture level

```
arsc_aligned.apk (7 entries)
OLD writer vs INPUT                              NEW writer vs INPUT
  extra      differ 7/7                            (nothing but offset)
  eattr      differ 7/7
  csys       differ 7/7
  ver_made   differ 7/7
  untouched entries with changed CRC/size : 2      untouched entries with changed CRC/size : 0
  resources.arsc: STORED @0x3a3 UNALIGNED          resources.arsc: STORED @0x3e4 ALIGNED
  zipalign -c -v 4 -> rc=1                         zipalign -c -v 4 -> rc=0
```

### 3.5 Evidence, a real 435-entry package, and an independent re-check

Same sample, same patch, old writer versus new writer versus the input:

```
  extra      differ 205/435                        (nothing but offset)
  eattr      differ 435/435
  iattr, csys, ver_made differ 272/435
  flags      differ 164/435
  untouched entries with changed CRC/size : 132    untouched entries with changed CRC/size : 0
  file size  4,293,620 -> 3,897,949                file size 4,293,620 -> 4,289,340
  resources.arsc: @0x36f931 UNALIGNED              resources.arsc: @0x3cec08 ALIGNED
```

The old writer also *shrinks* the archive by ~396 KB: re-compressing entries that were already
compressed changes the container, not the payload.

This pass re-checked the decisive claim with the Android build-tools' own verifier — a tool in
neither teammate's write scope — on the artifacts the other teammate produced:

```
$ E:\tools\android-14\zipalign.exe -c -v 4 <file>
plain.old.apk       rc=1  Verification FAILED        plain.new.apk       rc=0  Verification succesful
arsc.old.apk        rc=1  Verification FAILED        arsc.new.apk        rc=0  Verification succesful
r2pay.old.apk       rc=1                             r2pay.new.apk       rc=0
```

`zipalign -c 4` checks every uncompressed entry, which is stricter than Android's install gate. The
bare-`.so` path (no container) was re-hashed as well and shows the intended zero regression:

```
0790faeaec0ed4ea8bd3e859db23840dd9d1c2635330b48c4d2e3a3f68fdd371  bare.old.so
0790faeaec0ed4ea8bd3e859db23840dd9d1c2635330b48c4d2e3a3f68fdd371  bare.new.so
```

### 3.6 The refusal gate

Rebuilding is declined by default when the package cannot be rebuilt safely, with the measurement
and a pointer at the tool that owns a full resource-safe repack:

```
$ python skills/apk-reverse/scripts/so_constpatch.py tests/fixtures/apk/noextract.apk \
      --entry lib/arm64-v8a/libfoo.so --replace apkhuan=android -o out.apk
   extractNativeLibs=false
   UNSAFE: AndroidManifest.xml declares android:extractNativeLibs="false": ...
REFUSED: this package cannot be rebuilt safely by this tool (see the UNSAFE line(s) above).
  * If you want a resource-safe repack, use scripts/repack.py: ...
  * ... re-run with --unsafe-rebuild to proceed anyway.
RESULT=refused_unsafe_rebuild        exit=1        output written: no
```

Refusal is exit `1`, not `3`: `3` means the tool lacks the capability, whereas here the tool is
capable and the *package* is the reason nothing was written, so it is a negative finding about the
target. `--unsafe-rebuild` proceeds and still re-measures the STORED/alignment gate on its own
output. Exit codes follow the round's set — `0` success, `1` negative finding, `2` usage (including
an equal-length violation), `3` unsupported container (zip64, a non-deflate target, not a zip),
`4` internal error with the output deleted — and `--json` carries
`{status, exit_code, capability, evidence[], warnings[], next_action?}` plus `result`, `audit`,
`verify` and `patch`, with the final line `RESULT=<token>`.

### 3.7 What section 3 does not establish

- **No device, no install.** No `adb` install or cold start was run. The `[-124]` install failure is
  argued from the bytes and from `zipalign`, not observed on a device. `inferred`.
- **No signing run.** The rebuild output is unsigned by design; `repack.py` owns signing, so no
  `apksigner verify` result exists. `unverified`.
- **No genuine zip64 sample.** zip64 is refused (`exit 3`); the refusal path was exercised with a
  hand-built non-zip file, not with a >4 GiB archive.
- **Page alignment (4 KB/16 KB) is out of scope.** This work guarantees 4-byte alignment, the
  install gate. 4 KB/16 KB alignment for `extractNativeLibs=false` builds is `zipalign -p`'s job and
  stays with `repack.py`.
- `--unsafe-rebuild` cannot repair an already-compressed `resources.arsc`: the method is preserved,
  the self-check reports it as a warning, and the output stays non-compliant.

---

## 4. What this pass did not do

- **No `pm install` of any artifact**, and therefore no cold-start or behavioural verification of a
  rebuilt or re-signed APK. Everything in §3 is container-level plus an external alignment verifier.
- **No signing.** On this host `repack_signed` is genuinely blocked (a JDK launcher shim, no
  build-tools on `PATH`, no signer jar), so the signed-repack path was **not** executed; the
  capability verdict is a probe result, not an observation of a failed run.
- **No smali round-trip**, for the same reason: the eight jars are absent. `smali_roundtrip` is
  reported BLOCKED and was not exercised.
- **`dart_aot_full` was not exercised**: no snapshot dump exists in this session, and that
  capability reports an artifact the host cannot install rather than a missing package.
- **`check_commands.py` was not run against a benchmark target**, only against this repository. Its
  false-clean rate on a foreign documentation set is unknown.
- **The 30 skipped invocations were not individually confirmed** to be non-scripts; they are
  classified by the reason printed for each (`-m`, `-c`, an elision, or a prose line beginning with
  `python`), and a misclassification there would be a missed check rather than a false finding.
- **One workbench nuisance observed and not cleaned up** (not in any write scope): the tree carries
  an untracked `--help/` directory containing `exempt/benign.txt` and `planted/{appkey,device,
  endpoint,package,path}.txt`, i.e. the planted leak-fixture layout. It is not produced by
  `scan_leaks.py --help` (reproduced in a scratch directory: usage only, nothing written) and not
  by this pass's tools, which now probe in a temporary directory. The generator is
  `tools/_work/leak-precedent/gen_fixtures.py`, whose output directory is taken from an argument, so
  a probe that passed `--help` as that argument would create exactly this. It is worth removing by
  whoever runs the final commit, because the directory holds deliberately leak-shaped files.

## 5. Files changed by this pass

New: `skills/apk-reverse/scripts/capabilities.py`, `check_commands.py`.
Rewritten: `skills/apk-reverse/scripts/doctor.py` (its documented CLI is unchanged; `--scripts` and
`--json` still work, and the JSON keeps its old keys).
Merged here from teammate `zip-safety`'s work (their write scope, not this one):
`skills/apk-reverse/scripts/so_constpatch.py`, `tests/test_so_constpatch.py`,
`tests/fixtures/make_fixture_apk.py`, `tests/fixtures/apk/{plain,arsc_aligned,noextract,services}.apk`
and `tests/fixtures/apk/.gitignore` (the repo-wide `*.apk` ignore rule needs a `!*.apk` reverse rule
for fixtures to be stageable; `git check-ignore -v` confirms it).

Neither teammate committed or pushed. Nothing in §1 or §2 was measured on a device; §3's device
work did not happen either.

## 6. Index lines handed to the Lead

- `skills/apk-reverse/SKILL.md` (and `README.md` where the tool table lists scripts):
  **`scripts/capabilities.py`** — new. "Capability registry: the single source of truth for what
  this host can actually do. Resolves a capability's real `requires` closure (tools, modules, jar
  sets, device properties, input artifacts) into `ok | partial | blocked`, with an executable next
  step and a cost estimate that names its own strength. `--list`, `--json`; used by `doctor.py`."
- **`check_commands.py`** (repository root, sibling of `check_repo.py` / `check_refs.py`) — new.
  "Validates every documented script invocation (`python …`) against the script's own `argparse`
  table, read with `ast` so no script is executed to learn its interface. `--fix-report` prints
  `doc:line`, the command, the unknown flag and the closest known flags. Exit 0 clean / 1 drift /
  2 usage." It is a natural fourth entry in the publish-gate list wherever those are described.
- **`skills/apk-reverse/scripts/doctor.py`** — the existing row's wording can gain: "the script
  inventory is scanned from the directory (`registered/checked = N / N`, undecidable entries counted
  as `unknown`), and capabilities are probed rather than inferred from `java`".
- **`skills/apk-reverse/scripts/so_constpatch.py`** — the existing row can gain the clause from
  `zip-safety`'s §7: an APK rebuild preserves each entry's zip metadata (STORED stays STORED,
  `extra`/`external_attr`/`create_system` intact, `resources.arsc` kept STORED and 4-byte aligned)
  and is **refused by default** when `extractNativeLibs="false"` or `resources.arsc` is not
  STORED + aligned — `scripts/repack.py` is the route for that package, or `--unsafe-rebuild` to
  override deliberately.
- **`repack.py:_needs_alignment` is a live defect** (`^lib/[^/]+\.so$` cannot match
  `lib/<abi>/x.so`), reported by `zip-safety` and confirmed here by reading the predicate. Someone
  needs a write scope for `repack.py`, or it should be recorded as a known gap.
