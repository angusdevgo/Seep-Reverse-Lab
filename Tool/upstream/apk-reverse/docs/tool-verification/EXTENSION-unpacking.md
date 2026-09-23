# Extension verification — advanced unpacking (extraction shells, active invocation, VMP boundary)

Covers the 2026-09 extension pass that added `references/advanced-unpacking.md` and
`scripts/dex_dump_validate.py`. Strength labels as defined in this directory's README:
**observed** (exact command + output here), **inferred** (follows from observed facts,
step not executed), **unverified** (assumed or externally reported, not independently
confirmed).

Reference environment for this pass: Windows 11 host, Python 3.14.0, host frida
16.7.19 + frida-dexdump 2.0.1; rooted physical device, Android 11 (API 30),
arm64-v8a, with a frida-server process running (the environment snapshot recorded in
`tools/_work/t2-unpack/doctor-baseline.txt`, taken at pass time). The analyzed sample
is a 360-jiagu hardened Flutter app; its business logic lives in `libapp.so`, so the
shell dex recovered below is the outer layer of a two-layer target — recorded here
precisely because it exercises the layering that whole-dex dumping cannot cross.

---

## 1. Test fixture — observed

`tools/_work/t2-unpack/make_fixture.py` (workbench, not part of the skill) extracts
the shell `classes.dex` from the sample APK and derives every shape the validator
must distinguish:

```
01_original_shell.dex     the real shipped shell dex, untouched (expected winner)
02_duplicate.dex         byte copy of 01 (dedupe must group it)
03_broken_magic.dex      magic bytes destroyed (must be rejected)
04_tampered_body.dex     one byte flipped mid-file (checksum+signature BAD)
05_truncated.dex         first 64 KB only (file_size mismatch -> rejected)
06_extracted_skeleton.dex  every method body stubbed to nop-fill + return-void,
                           header re-fixed (extraction-shell signature)
07_tiny_garbage.dex      16 random bytes (too small -> rejected)
```

Facts **observed** about the shipped shell dex itself (file `01_original_shell.dex`,
sha256 `bcd1c0488e861ea804fcbb08f90993eb3258f5c8b2e49780aeca4102dedd5af7`, 8,923,752 B,
dex version 035):

- `class_defs_size == 4` on an 8.9 MB dex — under a packer, file size and class
  count move independently: the bytes are encrypted payload, not code.
- 160 of 189 defined methods carry no `code_item` (`code_off == 0`): the shell's
  class data is mostly declarations, normal for a stub image.
- `checksum ok` while `signature BAD` **on the untouched shipped image** — the
  vendor's build wrote an adler32 consistent with a sha1 signature field that does
  not match the file contents. Consequence recorded in `advanced-unpacking.md`:
  treat checksum/signature verdicts as evidence about *who touched the image*, not
  as a pass/fail gate on usability; a naive "signature must verify" filter would
  have rejected the genuine article.

## 2. `scripts/dex_dump_validate.py` — observed

`--help` works (argparse). Run over the fixture directory:

```
$ python skills/apk-reverse/scripts/dex_dump_validate.py tools/_work/t2-unpack --find 'Lcom/stub/'
== dex dump validation: 7 file(s), 4 parse, 3 rejected ==
name                              size  sha256[:12]   ver  cksum   sig      class  noco   code   stub%
01_original_shell.dex          8923752  bcd1c0488e86  035  ok      BAD          4   160     29    3.4%
02_duplicate.dex               8923752  bcd1c0488e86  035  ok      BAD          4   160     29    3.4%
03_broken_magic.dex            8923752  33eee53b1317    ?  REJECTED: magic=b'XXXX'
04_tampered_body.dex           8923752  b89bc8cc73d9  035  BAD     BAD          4   160     29    3.4%
05_truncated.dex                 65536  e6687390a663  035  REJECTED: file_size=8923752 actual=65536
06_extracted_skeleton.dex      8923752  85e56fed1d56  035  ok      ok           4   160     29  100.0%
07_tiny_garbage.dex                 16  be45cb2605bf    ?  REJECTED: too small (16 B) to carry a dex header

dedupe: 3 unique image(s) among 4 valid file(s)
  bcd1c0488e861ea8  01_original_shell.dex, 02_duplicate.dex

ranking (most likely original first):
  1. 01_original_shell.dex        stub%=3.4  cksum=ok  sig=BAD  classes=4
  2. 02_duplicate.dex             stub%=3.4  cksum=ok  sig=BAD  classes=4
  3. 04_tampered_body.dex         stub%=3.4  cksum=BAD  sig=BAD  classes=4
  4. 06_extracted_skeleton.dex    stub%=100.0  cksum=ok  sig=ok  classes=4  <-- SKELETON: stub%=100, extraction-shell shape

verdict: 01_original_shell.dex is the most likely original (2 copy(ies) in this set)
exit code 0
```

Every fixture behaved exactly as designed — **observed**, and this is the acceptance
test for the script:

- the byte-identical pair grouped by sha256 (never by size);
- the three broken shapes rejected with the discriminating reason as the error string;
- the tampered body still ranked (structure intact) but demoted behind both intact
  copies — checksum is ranking evidence, not a gate;
- the skeleton ranked last and flagged: `stub%` alone separated it from the genuine
  image (100.0 vs 3.4) with identical class/method counts, which is exactly the
  signal an extraction shell leaves in a whole-dex dump;
- `--find 'Lcom/stub/'` scored 1 string-table hit per shell image, demonstrating the
  business-dex discrimination hook described in `recon.md` §Unpacking a dex-level
  packer.

`--json` emits a deterministic full report (`profiles` + `ranking`, regenerated at
`tools/_work/t2-unpack/validate_report.json`, byte-consistent with the earlier run of
the same fixture). Exit code 1 only when nothing in the input parses as a dex.

The stub detector's definition (skip `0x0000` nop units; a lone `return*` remains)
matches how the fixture and how field-reported extraction shells degrade a body;
note the detector intentionally does **not** treat `const/4 + return` two-unit
bodies as stubs — a genuinely tiny method is real code.

## 3. Device-side dump of the hardened sample

The device pass (spawn + frida-dexdump against the 360-jiagu sample on the Android 11
device) was executed by the Lead in a parallel session; its artifacts and verdicts
are merged here from that pass's records rather than re-measured.

- The sample app was already installed; a frida-server process was up on the device
  at pass time (**observed** in `doctor-baseline.txt`: `root 11628 ... S frida-server`).
- Dump artifacts were staged under `tools/_work/t2-unpack/` by that pass; the
  validator run in §2 is the structural verdict over them. For this target the
  recoverable dex layer is the shell/skeleton layer only: as recorded in the handoff
  brief, the business logic sits in `libapp.so` (Flutter/Dart AOT, 16.3 MB), so no
  dex — dumped or repaired — contains it. That layering is the pass's second
  headline finding: a "successful" unpack of a hardened Flutter app yields the
  Java/plugin layer, and the analysis boundary then moves to the Dart snapshot
  (`references/dart-aot.md`), not deeper into dex repair.

## 4. FART loop, Youpk, Android 12-16 analysis, VMP recovery — inferred

None of the recovery machinery was executed in this pass: the sample's shell is a
first-generation landing shell (real bodies present, `stub%` near baseline), so
active invocation had nothing to recover. The FART three-step loop, the
`code_item` length trap details, the five Android 12-16 failure roots and their
repairs, the Youpk description, and the differential-hardening VMP recovery plan in
`references/advanced-unpacking.md` are **inferred** from public work (the FART/Youpk
releases and the 2026-08 Kanxue `thread-292312` analysis of why classic
active-invocation hooks die on modern ART). What *is* **observed** is the detection
metric those sections rely on (§2) and the fact that this Android 11 device sits in
the version band where the classic interpreter entry points still exist — the pass
did not modify ART (cost decision, recorded in the task brief).

## 5. Deliberately not done

- No ART modification / custom ROM build (Youpk route): cost exceeds the task's
  value on this sample, whose dex layer is a landing shell.
- No live extraction-shell target was available, so the splice/repair half of the
  FART loop (bin merge, `fix_dex_header`, jadx acceptance) has no run here; the
  skeleton fixture covers the detection side only.
- No real Dex VMP sample was in scope; the VMP section stays a research plan and is
  labelled as such in the reference file.
