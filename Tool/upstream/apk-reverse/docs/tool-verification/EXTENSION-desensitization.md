# Extension verification — desensitization and leak scans

Covers the pass that added `skills/apk-reverse/scripts/scan_leaks.py` and
`skills/apk-reverse/references/desensitization-and-leak-scans.md`, plus the precedent library
under `skills/apk-reverse/references/precedents/`.

Strength labels follow `docs/tool-verification/README.md`: **observed** (the exact command and
its output are reproduced here), **inferred** (follows from observed facts; the step itself was
not executed), **unverified** (assumed or reported elsewhere and not independently confirmed).

Reference environment: Windows 11 host, Python 3.14.0, repository root on branch
`main`. **No device, no network and no target sample were involved** — this pass is entirely
machine-local, because the thing worth measuring is what a scanner reports against a tree whose
contents are already known. Every identifier in the fixture and in every transcript below is
synthetic; the repository's convention of `<PKG>` / `<DEVICE>` / `<serial>` is used wherever a
real one would have appeared.

Date of the recorded runs: 2026-09-21. The numbers in §3b and §4a were measured on that date, on
the tree this pass leaves behind; those two sections' transcripts are the ones this pass produced.

**Headline: the planted-leak corpus is reported in full (30 findings, 10 further shapes admitted
through the exemption path), and the repository scan converges to zero strong/certain findings —
the residue is four `endpoint/weak` hits, all four an RFC 5737 documentation address, which is a
class this scanner reports on purpose. The first version of this file was itself the
counter-example to its own subject: it quoted the planted values to prove the rules fire, and the
scanner found that as a leak (§3b). The corpus keeps its values, because a corpus that cannot be
found proves nothing; the published document keeps none. The gate is not wired into anything yet;
that is the largest gap, and it is a Lead-side action.**

---

## 1. What was built, and what it was measured against

| Artifact | Role | Measured? |
|---|---|---|
| `skills/apk-reverse/scripts/scan_leaks.py` | the scanner: 17 rules in 6 categories, exemption table, four `RESULT=` tokens, `--fail-on strong\|any` | **observed** — every run below |
| `tools/_work/leak-precedent/gen_fixtures.py` | generates the planted corpus and the exemption corpus | **observed** — 7 files, re-runnable |
| `tools/_work/leak-precedent/fixture/` | the corpus itself (git-ignored work area) | **observed** |
| `skills/apk-reverse/references/desensitization-and-leak-scans.md` | the reasoning, the do-not-anonymize table, the failure modes | not executable |
| `skills/apk-reverse/references/precedents/**` | the case library, distilled from this repository's existing evidence | see the per-case strength tables |

The fixture exists so the claim "the scanner reports planted leaks" is reproducible rather than
a transcript pasted once:

```
$ python tools/_work/leak-precedent/gen_fixtures.py
wrote tools/_work/leak-precedent\fixture\planted\package.txt (411 bytes)
wrote tools/_work/leak-precedent\fixture\planted\device.txt (218 bytes)
wrote tools/_work/leak-precedent\fixture\planted\token.txt (261 bytes)
wrote tools/_work/leak-precedent\fixture\planted\appkey.txt (212 bytes)
wrote tools/_work/leak-precedent\fixture\planted\endpoint.txt (146 bytes)
wrote tools/_work/leak-precedent\fixture\planted\path.txt (175 bytes)
wrote tools/_work/leak-precedent\fixture\exempt\benign.txt (1396 bytes)
== 7 fixture file(s) ==
```

## 2. `--help`, and the rule table — observed

```
$ python skills/apk-reverse/scripts/scan_leaks.py --help
usage: scan_leaks.py [-h] [--root ROOT] [--only ONLY] [--exclude EXCLUDE]
                     [--format {text,json}] [--show-exempt] [--list-rules]
                     [--max MAX] [--quiet] [--fail-on {strong,any}]
                     [--no-color]

Scan a skills repository for target identity that should not be published (bundle ids, device serials, tokens, SDK keys, literal endpoints, user paths). Exit 0 clean / 1 leaks_found / 2 error; prints RESULT=<token> last. `--fail-on strong` (default) keeps the gate green when the only hits are documentation-range addresses.

options:
  -h, --help            show this help message and exit
  --root ROOT           repository root to scan (default: the repo this script
                        lives in)
  --only ONLY           comma-separated categories to restrict to, e.g.
                        pat,appkey
  --exclude EXCLUDE     extra directory name to skip (repeatable)
  --format {text,json}
  --show-exempt         also print findings that were suppressed by an
                        exemption
  --list-rules          print the rule table and exit
  --max MAX             stop after N findings (0 = no limit)
  --quiet               print only the RESULT token
  --fail-on {strong,any}
                        which findings make the exit code non-zero: `strong`
                        (default) fails only on strong/certain findings, `any`
                        also fails on `weak` ones such as an address from the
                        RFC 5737 documentation range
  --no-color            accepted for compatibility

Categories: package, device, token, appkey, endpoint, path
Exemptions (tool names, library names, CVE ids, hardening products, public
crackme names, <PKG>-style placeholders, loopback/emulator addresses) are built
in and audited with --show-exempt.
```

`--list-rules` prints the table the exemption functions are attached to, which is what makes the
scanner arguable rather than opaque. It exits 0 and prints `RESULT=clean` (no files were read),
and the top of its output is:

```
$ python skills/apk-reverse/scripts/scan_leaks.py --list-rules
== rules ==
  bundle_pkg_attr            package   strong   a `package=` bundle id in a manifest or transcript
  bundle_pkg_decl            package   strong   a bundle id in a `<manifest>` line
  bundle_pm_path             package   strong   a bundle id in a `pm`/`am`/`monkey` invocation
  bundle_process_line        package   strong   a bundle id in a `ps`/`pidof`/`top` capture
  bundle_component           package   strong   a bundle id in a `component=`/`-n` activity reference
  device_serial              device    strong   an `adb devices`-shaped device serial
  device_serial_context      device    strong   a serial next to a device/install/`su` context word
  device_serial_tabular      device    strong   a bare 16-char token in a device-listing table
  token_github_pat           token     certain  a GitHub fine-grained personal access token
  token_github_classic       token     certain  a GitHub classic token
  token_env_assignment       token     strong   an inline API-key/token/secret assignment
  token_authorization_header token     strong   a literal Authorization header value
  appkey_assignment          appkey    strong   an SDK appkey/appsecret assignment with a literal value
  plain_addr                 endpoint  weak     a non-loopback literal IP:port
  plain_addr_ipliteral       endpoint  weak     a non-loopback bare IPv4 literal
  user_path_posix            path      strong   an absolute POSIX user-home path
  user_path_windows          path      strong   an absolute Windows user-profile path
RESULT=clean        (exit 0)
```

## 3. The planted corpus — observed, every rule fires

```
$ python skills/apk-reverse/scripts/scan_leaks.py --root tools/_work/leak-precedent/fixture --format json
{ "root": "...\\tools\\_work\\leak-precedent\\fixture", "files_scanned": 7,
  "findings": [ ... 30 ... ], "exempted": [], "errors": [], "result": "leaks_found" }
RESULT=leaks_found        (exit 1)
```

aggregated (the `findings` array of the same JSON run, grouped by category):

```
files 7
findings 30  {'appkey': 4, 'token': 5, 'device': 8, 'endpoint': 5, 'package': 5, 'path': 3}
```

and the 30 hits by position, rule and value **shape** — every field of the report except the
literal itself. Rule name, category, strength, position and count are the evidence; the quoted
value is a copy of the leak, and copying it into a published document re-creates what the scan
exists to prevent (§3b is where that rule was paid for):

```
planted/package.txt:2:16   bundle_pkg_decl       4-segment all-lowercase reverse domain
planted/package.txt:2:26   bundle_pkg_attr       the same value, second rule on the same line
planted/package.txt:3:1    bundle_pm_path        3-segment all-lowercase reverse domain, after `pm path`
planted/package.txt:5:1    bundle_process_line   4-segment all-lowercase reverse domain, after `pidof`
planted/package.txt:6:15   bundle_component      4-segment all-lowercase reverse domain, after `component=`

planted/device.txt:4:1     device_serial          16×[A-Z0-9], tab-separated from the word `device`
planted/device.txt:4:1     device_serial_tabular  the same value, second rule on the same line
planted/device.txt:5:3     device_serial_context  16×[A-Z0-9], after `$ adb -s `
planted/device.txt:5:10    device_serial          the same value, second rule on the same line
planted/device.txt:6:2     device_serial_context  16×[A-Z0-9], after `[serial `
planted/device.txt:6:9     device_serial          the same value, second rule on the same line
planted/device.txt:7:1     device_serial_context  16×[A-Z0-9], after `device serial: ` (a second value)
planted/device.txt:7:16    device_serial          the same value, second rule on the same line

planted/token.txt:2:14     token_github_pat             fixed provider prefix + 62×[A-Za-z0-9_]
planted/token.txt:3:15     token_github_classic         fixed 4-char provider prefix + 36×[A-Za-z0-9]
planted/token.txt:4:1      token_env_assignment         20-char `AKIA`-prefixed key id after a key assignment
planted/token.txt:5:9      token_authorization_header   32×[A-Za-z0-9] after an `Authorization:` keyword
planted/appkey.txt:5:1     token_env_assignment         the same 40-char secret, second rule on the same line

planted/appkey.txt:2:1     appkey_assignment  24×[0-9a-f] after an appkey assignment
planted/appkey.txt:3:1     appkey_assignment  24×[0-9a-f], quoted, after a camelCase app-secret assignment
planted/appkey.txt:4:1     appkey_assignment  7 dash-separated 4-character uppercase groups
planted/appkey.txt:5:1     appkey_assignment  40-char mixed-case secret after a `SECRET_KEY` assignment

planted/endpoint.txt:2:7   plain_addr            an RFC 5737 documentation address, with `:port`
planted/endpoint.txt:2:7   plain_addr_ipliteral  the bare form of the same address
planted/endpoint.txt:3:16  plain_addr            an RFC 1918 private-range address, with `:port`
planted/endpoint.txt:3:16  plain_addr_ipliteral  the bare form of the same address
planted/endpoint.txt:4:12  plain_addr_ipliteral  an RFC 5737 documentation address, bare

planted/path.txt:2:10      user_path_posix    two-segment personal name after `/home/`
planted/path.txt:3:6       user_path_posix    one-word personal name after `/Users/`
planted/path.txt:4:6       user_path_windows  capitalized personal name after `C:\Users\`
```

Two rules firing on one line (`SECRET_KEY=` matches both an appkey and a token pattern) is kept
deliberately and is visible in the count; identical duplicates (same rule, same value, same
line) are collapsed. Eight of the 30 findings share their line with a second rule — one package
line, all four serial lines, the `SECRET_KEY` line and the two endpoint lines — which is why 30
findings cover 22 distinct values (counted from the `findings` array of the JSON run above, not
by hand).

### 3a. The exemption corpus — observed, and it is the half that is easy to get wrong

The same run with `--show-exempt` shows what was *not* reported from
`fixture/exempt/benign.txt`, and the reason:

```
$ python skills/apk-reverse/scripts/scan_leaks.py --root tools/_work/leak-precedent/fixture --show-exempt
== suppressed by exemption: 10 ==
  exempt/benign.txt:13  [user_path_windows] <user> -> placeholder user
  exempt/benign.txt:17  [plain_addr] 127.0.0.1:27042 -> loopback/unspecified/emulator address
  exempt/benign.txt:17  [plain_addr_ipliteral] 127.0.0.1 -> loopback/unspecified/emulator address
  exempt/benign.txt:17  [plain_addr] 0.0.0.0:8080 -> loopback/unspecified/emulator address
  exempt/benign.txt:17  [plain_addr_ipliteral] 0.0.0.0 -> loopback/unspecified/emulator address
  exempt/benign.txt:17  [plain_addr] 10.0.2.2:8080 -> loopback/unspecified/emulator address
  exempt/benign.txt:17  [plain_addr_ipliteral] 10.0.2.2 -> loopback/unspecified/emulator address
  exempt/benign.txt:18  [plain_addr] 127.0.0.1:8787 -> loopback/unspecified/emulator address
  exempt/benign.txt:18  [plain_addr_ipliteral] 127.0.0.1 -> loopback/unspecified/emulator address
  exempt/benign.txt:18  [plain_addr_ipliteral] 169.254.169.254 -> loopback/unspecified/emulator address
```

The earlier pass recorded 6 suppressed hits, all `plain_addr`; the current run reports the paired
`plain_addr_ipliteral` for each exempt address as well, which is what the two same-line rules
look like when nothing is being collapsed. The count moved from 6 to 10 for that reason and not
because the exemption table changed — nothing in it was touched by this pass.

Everything else on that file — tool names, library names, function names, dex/ELF constant
identifiers, protocol field names, CVE ids, hardening product names, the public crackme and its
URL, platform and SDK packages, `com.example.*` / `probe.synthetic.*` and the `<PKG>`/`<DEVICE>`/
`<hash>` placeholders — produced **no finding at all**, which is the intended outcome for the
do-not-anonymize list and is also the check that the two synthetic fixture prefixes named in
`references/desensitization-and-leak-scans.md` really are exempt: `com.example.app` sits on line
83 of that file and is absent from both the findings and the suppressed list, because
`BENIGN_PACKAGE_PREFIXES` contains `com.example`, `org.example`, `net.example`, `io.example` and
`probe.synthetic`. The file was written to hold every category of that list, one line each, so a
regression there shows up as a new finding rather than as a silent behavioural drift.

`169.254.169.254` (the cloud metadata endpoint) is exempted **only** in this documented-endpoint
form. It is a real address that matters in a different context; the exemption is a judgement
recorded in `BENIGN_IP_PREFIXES`, not a pattern match, and it is the entry most worth
re-examining if this list is ever copied to another repository.

### 3b. The leak this file carried — found by the scanner it documents

The first version of this section listed all 30 hits **with their values**, quoted out of the
JSON, because a report with the value in it is the concrete kind. The Lead then ran the tool
against the repository and got `RESULT=leaks_found`, exit 1, with **26 strong/certain findings
and 14 weak ones — all 26 strong ones inside this file**, at lines 113–146 of the version that
existed then: the 5 bundle-id hits, 2 distinct device serials (12 hits), 2 provider-format tokens,
2 inline assignment values, 2 SDK appkeys and 3 host user names it had just finished quoting.
Nothing else in the tracked surface produced a strong hit.

That is the failure mode this whole pass exists to prevent, committed by the pass itself, and it
states the boundary in one line: **the corpus is where identity is allowed; the published surface
is not.** `tools/_work/leak-precedent/` is git-ignored and excluded from the default scan root so
that it *can* hold the values — a corpus that does not contain them cannot demonstrate the rules
firing. This file is not in that category: it is tracked, it is read, and every string in it is
published.

The correction, applied in this pass:

1. The hit list in §3 now carries rule, category, strength, position, count and a **structural
   description** of each value, in the repository's own placeholder notation. No evidence was
   dropped: all 30 positions, all 17 rule ids, both strength labels and the per-category counts
   are still here, and the corpus still produces all 30 when it is scanned directly (§3).
2. The two version-shaped literals in §4's false-positive table are now written in
   `<N>.<N>.<N>.<N>` form. They are legitimate values, but leaving them would put two *different*
   classes in the weak residue instead of one, and an unexplained second class is how a weak hit
   starts getting ignored.
3. `references/desensitization-and-leak-scans.md` records the rule this produced — a report is a
   copy of what it found, so the report is scanned like any other published surface — and its
   exit table now carries the `leaks_found_strong_only` state.

The scanner's own verdict on the corrected tree is in §4a. The lesson is the one the reference
file already made about entry points, applied to an evidence file: **run the scan on the file you
are about to publish, not on the file you started from** — and then do not paste the thing it
found back into that file.

## 4. The repository scan — observed, and the false positives that produced it

The first run against the real tree reported **28 findings**, of which 27 were wrong. The
sequence is recorded in full because the corrections are the useful part: every one of them was
found by running the scanner, not by reasoning about it.

```
$ python skills/apk-reverse/scripts/scan_leaks.py                # first run
== leak scan: 118 file(s) scanned under the repository root ==
   findings by category: device=4, endpoint=20, package=4
== result: 28 finding(s) ==            RESULT=leaks_found   (exit 1)
```

| # | Reported | Why it was wrong | Fix |
|---|---|---|---|
| 1 | a `jdk`-version-shaped run (`…\jdk-<N>.<N>.<N>.<N>`) ×19, across eight files in `docs/tool-verification/` | it is the JDK version in the toolchain's own path; the token `jdk` sits immediately before the match | a 30-character context window before the literal must not end in a version word (`jdk\|java\|python\|frida\|…`) |
| 2 | `0000000040001000`, `0000000000714240` | tombstone register/`pc` values — 16 hex digits, all digits | an all-digit 16-character token is suppressed; a real platform serial carries at least one letter |
| 3 | `0807060504030201` ×3 | a protobuf `fixed64` fixture in `EXTENSION-protobuf-raw.md` and in `scripts/protobuf_decode_raw.py` | same rule as #2 |
| 4 | `sg.vantagepoint.uncrackable3` | the published package name of an OWASP MASTG crackme | `PUBLIC_TARGET_PREFIXES` (public crackme/benchmark families are reuse, not identity) |
| 5 | `probe.synthetic.vmpdiff` | the synthetic manifest inside `vmp_diff_harness.py` | added `probe.synthetic` to the fixture prefixes |
| 6 | `args.package.spli` (twice truncated to `spli`) | a property lookup in `scripts/spawn_patch_detach.py`; the exemption window was measured from the *match* start, which an unbounded `[^\n]*?` prefix pushes past the `args.` | the window starts at the **capture group** (`m.start(group)`), and the exemption reason is printed so the path can be audited |
| 7 | `<N>.<N>.<N>.<N>` | an SDK version *directory* (`…/com.kwad.components.tachikoma/<N>.<N>.<N>.<N>/base-1_apk`) inside a private-storage path | a version-directory rule: a `.`-separated digit run enclosed in path separators is not an address |

Two rows in that table are quoted in placeholder form rather than as the literal the first run
printed — row 1's four-part JDK version run and row 7's four-part SDK version run. Neither names
anybody: both are version numbers, and both were rewritten in this pass for the reason given in
§3b, because leaving them would put a second class (version runs, not addresses) into the weak
residue, where an unexplained class is the first thing a reader learns to skip. The shape is what
each row is about, and it survives the rewrite intact.

### 4a. What this pass inherited, and what it leaves — observed

Inherited state, reproduced at the start of this pass (same tree, before the §3b correction):

```
$ python skills/apk-reverse/scripts/scan_leaks.py
== leak scan: 128 file(s) scanned under the repository root ==
   findings by category: appkey=2, device=12, endpoint=14, package=5, path=3, token=4
== result: 40 finding(s) -- each one is a line to look at, not a verdict ==
RESULT=leaks_found        (exit 1)
```

26 of the 40 are strong/certain (`package` 5, `device` 12, `token` 4, `appkey` 2, `path` 3) and
every one of those 26 is a line of this file's former §3 hit list, at lines 113–146. The other 14
are weak: 5 more lines of that same block (its endpoint rows), 2 version strings in §4's own
table, 3 RFC 5737 range literals in
`skills/apk-reverse/references/desensitization-and-leak-scans.md`, and `scripts/tls_check.py`'s
usage example.

Post-correction, on the tree this pass leaves behind:

```
$ python skills/apk-reverse/scripts/scan_leaks.py --quiet
RESULT=leaks_found_strong_only        (exit 0)

$ python skills/apk-reverse/scripts/scan_leaks.py
== leak scan: 129 file(s) scanned under the repository root ==
   findings by category: endpoint=4

  skills/apk-reverse/references/desensitization-and-leak-scans.md:81:10  [endpoint/weak]  plain_addr_ipliteral
    match:   <RFC 5737 literal>
  skills/apk-reverse/references/desensitization-and-leak-scans.md:81:26  [endpoint/weak]  plain_addr_ipliteral
    match:   <RFC 5737 literal>
  skills/apk-reverse/references/desensitization-and-leak-scans.md:81:45  [endpoint/weak]  plain_addr_ipliteral
    match:   <RFC 5737 literal>
  skills/apk-reverse/scripts/tls_check.py:44:23  [endpoint/weak]  plain_addr_ipliteral
    match:   <RFC 5737 literal>

== result: 4 finding(s) -- each one is a line to look at, not a verdict ==
   all are `weak` (the documented address ranges); the gate is green under the default --fail-on strong, and `--fail-on any` is the strict pass
RESULT=leaks_found_strong_only

$ python skills/apk-reverse/scripts/scan_leaks.py --quiet --fail-on any
RESULT=leaks_found                    (exit 1)
```

The four residual hits, by position, rule and class. Their individual values are deliberately not
reprinted here — that is §3b's correction, and re-printing them is how this file leaked the first
time. All four are the same class:

| position | rule / strength | class |
|---|---|---|
| `skills/apk-reverse/references/desensitization-and-leak-scans.md:81` ×3 | `plain_addr_ipliteral` / weak | the three RFC 5737 documentation blocks, named inside that file's own statement that they are *not* exempt |
| `skills/apk-reverse/scripts/tls_check.py:44` | `plain_addr_ipliteral` / weak | the script's usage example, an RFC 5737 address |

Reading: **zero strong/certain findings and zero unexplained hits on the tracked surface; four
weak ones, one class, both sources named.** The residue is the price of the design decision
recorded in §"Deliberately *not* exempt" of the reference file: the documentation that states the
decision has to name the ranges, and the ranges are exactly what the rule reports. That is why
the gate's pass condition lives in `--fail-on` and not in the exemption table, and why
`--fail-on any` stays red on this repository on purpose.

The file count is 129 here, 128 in the inherited run above and 119 in the first pass: the tracked
surface grows while several writers work on it, and this pass added no file to the scanned
surface, so the count is a property of the run rather than of the leak. The number that is
comparable across the runs is the strong/certain one: **26 inherited, 0 now**. The inherited
figure also reproduces the Lead's own catch (§3b) exactly, which is the point of quoting the
transcript rather than the conclusion.

Two work artifacts of this pass live beside the corpus in the same git-ignored directory, and
neither is part of the scanned surface: `EXTENSION-desensitization.before.md` (the pre-correction
snapshot of this file, kept so that the correction is auditable in both directions) and
`fixture-scan-before.txt` (a captured run of the fixture scan). Both contain the planted values
by construction, exactly like the corpus, and both are excluded from every default run — the work
area is where identity is allowed to exist; that is the whole of §3b's boundary.

## 5. The exit-code contract — observed, all four states

```
$ python skills/apk-reverse/scripts/scan_leaks.py --root LICENSE --quiet
RESULT=clean        (exit 0)

$ python skills/apk-reverse/scripts/scan_leaks.py --quiet
RESULT=leaks_found_strong_only        (exit 0)      # the repository tree, weak hits only

$ python skills/apk-reverse/scripts/scan_leaks.py --quiet --fail-on any
RESULT=leaks_found                    (exit 1)      # the same tree, strict pass

$ python skills/apk-reverse/scripts/scan_leaks.py --root tools/_work/leak-precedent/fixture --quiet
RESULT=leaks_found  (exit 1)

$ python skills/apk-reverse/scripts/scan_leaks.py --root tools/_work/nope-not-here
error: root does not exist: tools/_work/nope-not-here     [stderr]
RESULT=error        (exit 2)

$ python skills/apk-reverse/scripts/scan_leaks.py --only nope
error: unknown category (or categories): nope                            [stderr]
RESULT=error        (exit 2)
```

The token and the exit code are deliberately separate channels: a wrapper that only greps
stdout cannot tell "clean" from "the scanner never ran", and one that only reads `$?` cannot
explain itself in a log.

`--fail-on` is what keeps those two channels from contradicting each other on a tree that is
documentation-shaped. Under the default (`strong`) a tree whose only findings are `weak` reports
`leaks_found_strong_only` and exits 0: the findings are still printed in full, they simply do not
fail the gate. Under `--fail-on any` the same tree reports `leaks_found` and exits 1, which is the
right verdict at publish time and the wrong one for a habit that runs on every change — a gate
that is red on its own design documentation is a gate people disable.

## 6. What was not done

- **The `RESULT=` token convention was undocumented when this pass started, and it is documented
  now.** The Lead added `references/long-task-discipline.md` §Every script answers with a token,
  not with prose during this pass, so the scanner is no longer the convention's only user. That
  section's vocabulary is generic (`clean`, `patched`, `success`, `crash`, `timeout`,
  `unavailable`, …) and does not spell out `leaks_found` / `leaks_found_strong_only`; whether
  they belong in the enumeration is a Lead call. Verified with
  `grep -n "RESULT=" skills/apk-reverse/references/long-task-discipline.md` → one match, line 70.
- **Nothing is wired into a gate.** No pre-commit hook, no CI job, no line in the maintenance
  three-command habit. The scanner has never run automatically; every result above is a manual
  invocation. Recorded as `unverified` in the sense that matters: whether it *would* be run is
  untested.
- **No scan of the git-tracked list specifically.** The scan walks a filesystem root, so its
  coverage is "the default surface under this root", not "the files that exist in HEAD". A file
  that is present locally but ignored, or tracked but absent, is not distinguished.
- **No check of binary or archive content.** `*.apk`, `*.png`, `*.pcap` and `*.zip` are not
  opened. Identity inside a screenshot or a capture file is real and this pass does not address
  it.
- **No git-history scan.** A string deleted from the working tree remains in the history; nothing
  here inspects commits. This pass did check the one case it created: `git status --short` shows
  `docs/tool-verification/EXTENSION-desensitization.md` as `??` (untracked), so the values §3b
  removed were never committed and nothing was written into history. That is a check of this
  file, not a history scan.
- **No second-language rule set.** Identifiers that are not reverse-domain shaped (a nickname, a
  local-part email, a CJK app name) are not covered. The rules are shape-based by construction.
- **No cross-repository validation of the exemption list.** The benign prefixes were derived from
  this tree's own contents (a grep over its Markdown for reverse-domain tokens). Whether the same
  list is right for another repository is `unverified`, and the reference file says so.
- **The `--max` / `--only` / `--exclude` paths were exercised only in the forms shown above.**
  `--max` was not driven at all.

## 7. One-line deliverable statement, and the open items

**Deliverable (verified):** `python skills/apk-reverse/scripts/scan_leaks.py` scans a repository
root for six categories of target identity, reports each hit with a limited context window and a
strength label, exits 0/1/2 with a matching `RESULT=` token, reports all 30 planted leaks in the
reproducible corpus at `tools/_work/leak-precedent/fixture` (7 files, 10 further shapes admitted
through the exemption path), and against this repository's 129-file tracked surface returns zero
strong/certain findings — the residue is four `endpoint/weak` hits, all RFC 5737, both sources
named in §4a — so the default gate is green (`RESULT=leaks_found_strong_only`, exit 0) while
`--fail-on any` stays available as the strict pass (`RESULT=leaks_found`, exit 1).

**Open items for the Lead:**

1. Wire the scan into the maintenance gate (`check_repo.py`, `check_refs.py`, `scan_leaks.py`)
   and record in `README.md` that the third one's exit 1 is a *content* finding, not a
   mechanical failure like the other two.
2. Decide on a history scan. Nothing in this pass looked at commits, and a leak removed from the
   tree is still in them.
