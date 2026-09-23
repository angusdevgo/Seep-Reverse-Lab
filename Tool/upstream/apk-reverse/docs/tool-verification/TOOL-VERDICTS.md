# Tool verdicts — measured on a real target

One verdict per script, drawn from the closed set:

| Verdict | Means |
|---|---|
| **verified on real target** | Ran here, and its output was confirmed by an independent method that does not share code with it |
| **broken — fixed** | Was wrong; the defect is localized and a corrected copy was run and re-verified |
| **broken — cause identified, not fixed** | Was wrong; root cause established, no fix attempted |
| **unusable here because …** | Correct diagnosis, but this environment/target cannot exercise it |
| **not applicable to this sample** | The target lacks the feature the tool addresses |

The distinction that governs the whole table: **a script that runs without error is not a script
that is right.** Every "verified" below names the independent cross-check, because "it didn't
crash" was not accepted as evidence anywhere in this pass. Equally, a tool failure was never read
as "the target does not contain that thing" — each failure was first checked against the question
of whether the tool was ever able to answer it.

---

## Summary

| Script | Verdict |
|---|---|
| `elf_plt.py` | **broken — fixed** (core stub→symbol mapping verified on real target; two defects, one proven to cause a false negative) |
| `lib_map.py` | **verified on real target** |
| `so_constpatch.py` | **verified on real target** for equal-length rewriting; **broken — cause identified, not fixed** for one sealed serious defect (zip alignment) |
| `dex_strings.py` | **verified on real target** (multi-dex traversal confirmed) |
| `dexutil.py` | **verified on real target** (used as the primary workhorse for the ad-chain analysis) |
| `find_refs.py` | **broken — fixed and re-verified**; reads a `.dex` directly now |
| `dart_pool_strings.py` | **verified on real target** |
| `dart_pprefs.py` | **broken — fixed** (defect proven; corrected copy agrees with capstone to zero) |
| `dart_disasm.py` | **verified on real target** |
| `coldstart.py` | **verified on real target** (the run produced the launch-crash finding) |
| `native_crash.py` | **not applicable to this sample** (no artificially constructed crash; see `TARGET-FACTS.md`) |
| `so_constpatch.py` redirected-checker scenario | **not applicable** — no integrity-check library exists in this target |
| All packer / VMP tooling | **not applicable** — no packer in this target |
| blutter (external) | **works** — build ≈78 s, transient first-run `0xC0000005` not reproducible after relink |
| aotopsy (external) | **works out of the box** — full pipeline on the same `libapp.so`

Two of these verdicts matter more than the rest: `elf_plt.py` produced a **false negative** on a
symbol that exists and is called, and `find_refs.py` returns a clean "no references" answer for
input it cannot read at all. Both are the failure mode that looks like a finding.

---

## `elf_plt.py` — broken — fixed

**Claim under test:** walks `PT_LOAD`/`PT_DYNAMIC` directly, without depending on the section
table, maps PLT stubs to imported symbols, and diffs two `.so` files byte-wise.

**Sample:** `lib/arm64-v8a/libloader.so` (6,221,896 B, largest `.dynsym` in the APK).

**Run:**

```
python scripts/elf_plt.py work/native/samples/arm64-v8a_libloader.so
  exit 0   790 ms   3440 lines
  arch=aarch64  exec seg: vaddr=0x0 file=0x0 size=0x587070
  imported relocations=36974   stubs resolved=3437
```

**Independent cross-check — four paths, none sharing code with the script:**

1. **Relocation total.** `readelf -d` (pyelftools) reads `RELASZ=804864`, `PLTRELSZ=82512`,
   `RELAENT=24`. `804864/24 = 33536` (`.rela.dyn`) + `82512/24 = 3438` (`.rela.plt`) `= 36974`.
   Matches the script's `imported relocations=36974`.
2. **Symbol names, item by item.** pyelftools parses `.rela.plt` + `.dynsym` independently
   (3,438 entries, all `R_AARCH64_JUMP_SLOT=1026`). Against the script's 3,437 output lines:
   `name mismatches: 0`. The script's GOT set is a subset of the `.rela.plt` GOT set, with an
   intersection of **0** against `.rela.dyn` — i.e. it does not mistake local relocations for
   imports. Zero `?` names.
3. **lief 1.0.0** independently reports `pltgot_relocations = 3438`, equal to the pyelftools set,
   with zero name disagreements.
4. **capstone 5.0.7 real disassembly** of all 3,437 reported stub addresses, 16 bytes each, with the
   GOT recomputed from the decoded instructions: `shape_violations: 0` (every stub is
   `adrp x16 / ldr x17,[x16,#off] / add x16,x16,#off / br x17`) and
   `got_recompute_mismatch: 0`.

Conclusion: the four hand-written bitfield decoders (`_decode_adrp`, `_decode_ldr_unsigned`,
`_decode_add_imm`, `_decode_br`) are **correct**, not merely non-crashing.

### Defect 1 — loop bound, proven to cause a false negative

`.rela.plt` has **3,438** entries; the script reports **3,437**. The arithmetic:

- first `.plt` stub `0x579990` + 3438 × 16 = **0x587070**, exactly the executable segment end
  (`size=0x587070`)
- the source reads `while off < fsz - 16`, so the largest offset examined is `0x58705c`; the final
  slot `0x587060..0x58706f` is never checked. `fsz-16` would need to be `fsz-15`; the correct form
  is `off + 16 <= fsz`.

The skipped slot is a legitimate stub, proven by independent disassembly:

```
0x587060  adrp  x16, #0x5c8000
0x587064  ldr   x17, [x16, #0x108]
0x587068  add   x16, x16, #0x108
0x58706c  br    x17
recomputed GOT = 0x5c8108   -> .rela.plt entry for that GOT: dl_iterate_phdr
BL/B callers of the skipped stub: 1  ['0x576a2c']
```

And the script therefore answers wrongly, with a confident negative:

```
$ elf_plt.py libloader.so --query 0x587060
0x587060 -> not a resolved stub          <-- FALSE NEGATIVE
```

This is the most important single result of the native pass. The script does not error, its output
looks complete, and for its stated purpose — *"which stub points at the hardening symbol I want to
neutralise"* — it reports that a real, called symbol (`dl_iterate_phdr`) does not exist in the
library. That is precisely the failure mode the script's own docstring warns about.

**Fix**, applied to a copy and re-verified — three isomorphic bounds:

```
_stubs_x86:            while i < fsz - 6    ->  while i + 6  <= fsz
_stubs_arm64:          while off < fsz - 16 ->  while off + 16 <= fsz
find_branch_callers:   while off < fsz - 4  ->  while off + 4  <= fsz
```

After the fix: `stubs resolved=3438`, equal to the `.rela.plt` entry count. The diff against the
original output is **exactly two lines** — the header count and the single new
`0x00587060 -> dl_iterate_phdr (GOT 0x5c8108)` — with all other 3,437 lines byte-identical.
`--query 0x587060` now resolves correctly.

### Defect 2 — `--diff --name-regions` compares a file offset against a virtual address

`cmd_diff`'s `describe(off)` receives a **file offset** and compares it against stub **vaddrs**
(`va <= off < va + size`). Those coincide only when `p_vaddr == p_offset`. Two of the 36 libraries
in this target violate that:

```
lib/arm64-v8a/libflutter.so    exec PT_LOAD  vaddr=0x444880  offset=0x434880  (delta 0x10000)
lib/armeabi-v7a/libflutter.so  exec PT_LOAD  vaddr=0x277500  offset=0x267500  (delta 0x10000)
```

Demonstrated by mutating a byte inside the `abort` stub (stub vaddr `0x9f6050`, file offset
`0x9e6050`) and diffing:

```
$ elf_plt.py libflutter.so --diff flutter.mutated.so --name-regions
  differing bytes=1 in 1 run(s)
  off=0x9e6053 len=1   A: b0
                       B: b1
                       <-- the "<- PLT stub for abort" annotation is missing
```

Plain `--diff` and `--diff --name-regions` produce **identical** output, i.e. the feature is
completely inert on these two libraries and reports nothing about being inert.

**Fix:** map the file offset back through `PT_LOAD` before comparing.

**Also:** `size = 16 if elf_a.machine == EM_AARCH64 else 16` — both branches identical; dead code.

**Credit where due:** the script's defensive warning fires correctly on a zero-stub target.
`libapp.so` (Dart AOT, 144-byte `.dynsym`) reports `stubs resolved=0` **and** prints an explicit
"do not read this as 'the library imports nothing'" message. That is exactly the right instinct —
it is unfortunate that the scanner then violates that principle itself, one slot early.

---

## `lib_map.py` — verified on real target

**Claim under test:** reads a live process's mapping table and reports which libraries are actually
loaded, at what base, with what real architecture.

**Run:** `--pkg <PKG> --serial <DEVICE>`, exit 0, 635 ms, pid 27064.
Reported three actually-loaded app libraries — `libloader.so` (3 segments),
`libsentry-android.so` (2), `libsentry.so` (3).

**Independent cross-check:**

- `su -c cat /proc/27064/maps` parsed with an independent parser: path set, segment counts and
  permission strings agree with **zero** differences.
- `od` read of the ELF header gives `b7 00` = AArch64, matching the script's architecture column.
- Scale check against `systemui`: **318 libraries**, compared item by item — path, segment count
  and permissions all zero-difference; `--json` base addresses agree **318/318** with independent
  computation.
- Translation-layer detection fires correctly on the emulator
  (`/system/lib64/libhoudini.so` → `translation suspected: YES`).

**Improvement, not a defect:** `?` in the architecture column is two-valued in the docs —
`read_elf_arch`'s docstring says `?` = read failed; the CLI's trailing note says `?` = not probed.
All 8 libraries printed as `?` were independently read and are AArch64, i.e. they exist and simply
were not probed. A genuine read failure is indistinguishable from "not probed".

**Anomaly resolved as not-a-bug:** one crosscheck showed `libsentry.so 3 vs 4` segments. Four
snapshots established this as runtime mapping change (it is 3 segments at the instant of launch),
not a script defect.

**The real constraint on this tool here:** the target lives ~1.1 s, so `lib_map.py` must run inside
that window. That is also why the app's own libraries are limited to three — `libapp.so` and
`libflutter.so` had not been loaded yet.

---

## `so_constpatch.py` — verified (core) with one sealed serious defect

**Claim under test:** equal-length rewriting of string constants inside a `.so`.

**Verified by:** length unchanged at 6,221,896 bytes, sha256 changed, and an independent byte-wise
diff showing changes at exactly one site (`0x81593`, 7 bytes). `readelf -d` confirms the change
landed at the ELF semantic layer: the `NEEDED` entry changes from `libandroid.so` to
`libfoo0000.so`. Guards behave as designed — unequal-length input exits 1 and writes no file; `-o`
pointing at the input exits 2; non-isolated operation refuses by default. On a real APK copy: 3.5 s,
**all 1,982 entries preserved**, order preserved, only the target entry's CRC changed, original APK
sha256 unchanged before and after. All patching was done on copies; no sample was mutated.

### Defect — zip alignment destroyed on rebuild (sealed, not fixed)

The rebuild discards the local header `extra` field, which breaks 4 KB alignment. Measured on a
fixture: `data_offset 4096 (mod4096=0, extra_len=4031)` becomes `65 (mod4096=65, extra_len=0)`.

**Why this is serious despite not firing here:** for an APK with `extractNativeLibs=false`, `.so`
entries must be `STORED` and 4 KB-aligned or the library will not load. This target cannot show the
bug — all 36 native libraries are `method=8` (DEFLATED) and `extractNativeLibs=true` (confirmed in
both the manifest and by the runtime path `/data/app/.../lib/arm64/` that `lib_map.py` observed).
So the defect is **masked by this sample and proven by a fixture**. That asymmetry is exactly why
"it worked on our target" is not a verification.

**Fix sketch:** copy `extra`/`external_attr`/`internal_attr`/`create_system`/`comment` from the
source `ZipInfo` and implement padding; and state in the help text that a rebuild must be
re-zipaligned before signing.

### Defect — entry metadata reset

`external_attr` is rewritten on **1982/1982** entries (e.g. `2175008768 (0x81A40000)` →
`25165824 (0x01800000)`), and `create_system` changes from 3 (Unix) to 0 on 77 entries. Usually
harmless for installation, but it changes extracted permission bits and makes any
zip-metadata-based integrity comparison immediately detect the rebuild.

### Defect — the change count is misleading

`do_replace` prints `'%d byte(s) changed' % (len(applied) * len(old))`, which is the **overwrite
window length**, not the number of bytes that actually changed. Two measured examples:
`libandroid.so → libfoo0000.so` prints 13 but changes 7; `libandroid → libandroiX` prints 10 but
changes 1. For an attribution/audit tool this invites overstatement.

### Minor

Rebuilding changes the APK's own bytes (+2.2 MB on the sample, different deflate level). Worth a
note in the output that output size may differ from input.

---

## `dex_strings.py` — verified on real target

**The multi-dex question the handover flagged is answered: yes, directory mode walks all four dex
files.** `iter_dex()` globs `*.dex` for a directory; empirically
`--find 'json' --per-file` emits four lines (`classes.dex`, `2`, `3`, `4`), while single-file mode
emits one.

Two traps worth knowing:

- `--per-file` prints **only files that had a hit**. An output containing just `classes3.dex` does
  not mean only `classes3.dex` was scanned. This is the shape of output most likely to be
  misread as "only one dex contains this".
- `--per-file` scans **raw bytes** rather than the string table (source lines 124-130), so hits for
  broad patterns include coincidental matches.

Fast: 0.27 s over the full 27.6 MB.

## `dexutil.py` — verified on real target

The workhorse of the ad-chain analysis: symbol resolution, branch-target back-annotation, and a
`ended cleanly` verdict per method. Coverage: 175,829 method bodies with code, 213,180 `method_id`s.
It is the tool whose output the zero-reference conclusion rests on.

Three defects, all found by working at this scale:

- `decode()` does not resolve operands — string and method indices must be decoded by the caller.
- **Switch payloads were decoded as instructions**, contradicting the docstring's claim that
  `ident 1..3` are recognized. This was one root cause of `saveToLocal` being reported as
  "desync likely".
- **The opcode table was shifted from 0x16 to 0x2C, and nine widths were wrong with it** — fixed.
  `0x1C` carried the name `monitor-enter` and one unit; the format specification has `const-class`
  there, at two units. `0x17` was `const-wide/16`/2 where the spec has `const-wide/32`/3; `0x18` was
  3 where the spec has `const-wide`/5; `goto` was read one slot early, so `throw` was treated as a
  branch. The plausible "same family, same width" reading of that run is wrong at nine opcodes, and
  each wrong entry shifts every instruction after it inside that method.

  Proven by measurement rather than by re-reading the table: on a real 8.9 MB dex, **65 method
  bodies did not decode to their declared boundary and 32 carried an operand index outside its
  table**; after the fix, **50,791 of 50,791 land exactly on `insns_off + insns_size*2` with 0
  illegal indices**. Independently cross-checked against androguard's decoder, which shares no code
  with this project: same method count (50,791), and **0 differing width sequences** across all of
  them.

  Names and widths now come from the format specification's table, and widths are a lookup
  (`OP_UNITS`) rather than a chain of range tests. The `goto` family in `branch_target()` and in
  `dex_find_insn.py`'s kind map moved with it.

## `find_refs.py` — broken — fixed and re-verified

The docstring said it accepts "a smali tree or a directory of dex files". It did not:
`iter_files()` yielded only files ending in `.smali`. A direct `.dex` was yielded, then read as UTF-8
text and regex-matched against smali syntax, which cannot match; a directory holding only dexes
yielded nothing at all. Both printed `[total refs] 0` and a note blaming the needle, so a real dex, a
dex directory and a typo'd path were **indistinguishable in the output**.

This is the worst shape a defect can take in this particular tool, because `find_refs.py` is the
script recommended for judging blast radius *before* patching. Its silent zero is exactly the
input to a confident wrong conclusion — "nothing references this, safe to patch". Because no
baksmali/jadx is installed on this machine, it was **completely unusable** for this target, and the
analysis had to be built on `dexutil.py` instead.

Two corrections to the record above, both from re-measuring rather than re-reading:

- The exit code was **1**, not 0 — the `total == 0` path has always returned 1, so a caller checking
  status could already catch it. What misled was the *text*: the note diagnosed the needle and never
  named the input form.
- The dex-as-text path also read the whole file into memory to regex-scan binary for nothing, then
  dropped it.

Fixed in three ways at once, because all three were the same omission — the tool did not tell the
difference between "found nothing" and "read nothing":

- A `.dex` is decoded through `dexutil` (no baksmali needed), a directory is walked for `.smali` and
  `.dex` alike, and an archive is opened for its `classes*.dex`.
- Unsupported or unreadable input is **refused with exit 2** and a reason, instead of being reported
  as zero references.
- Every run prints `[scanned] N file(s)` first, so the two cases can never print identically again.

Re-verified twice, in both directions:

- Against a fixture whose call graph is known **by construction** (`make_fixture_dex.py` writes two
  classes with 3, 2 and 2 references): the `.dex` and the equivalent smali tree return the same
  counts, and they match what was written — 3 / 2 / 2.
- Against the real 8.9 MB target: `Ljava/lang/String;->length` → **356 references in 2.3 s**; a
  five-dex directory → 9,472 across 2 files; a typo'd path → `[error] no such file or directory`,
  exit 2.

**Correction to a related assumption in this environment:** `readelf` on `PATH` resolves to
pyelftools' `readelf.py` and is *not* binutils — `--dyn-syms` and `-W` are rejected as unrecognized
arguments (exit 2). Likewise MinGW `objdump`/`nm` (binutils 2.28) reject every aarch64 ELF with
`File format not recognized`. Aarch64 cross-checks in this pass therefore used the **pyelftools,
lief and capstone library APIs**, not those CLIs. There is no `xxd`; hex work was done in Python.

---

## Dart / Flutter scripts

Verified facts, each independently cross-checked rather than accepted on exit code:

**`dart_pool_strings.py` — verified on real target.** 18,363 rows recovered. Byte-exact re-check of
tag + payload: **18,356 exact, 7 mismatched**, and all 7 mismatches are a single known escape
ambiguity (`\n`/`\r`/`\t` written as the two characters backslash+n, indistinguishable in a TSV from
a literal backslash followed by n — 19 recovered entries genuinely contain LF/CR/TAB). 12 rows
sampled at random were independently re-located from the raw bytes; **all 12 reproduced**, with tag
at `tag_off` and payload at `tag_off + 1` exactly. Chain violations among run≥2 rows: **0**.

**`dart_pprefs.py` — broken — fixed.** The first run produced a real defect: **302 displacements and
1,802 reference sites missing**. Correcting the mask makes it agree with capstone exactly:

```
                repo (before)         repo (fixed)        capstone
displacements        31,843               32,145             32,145
reference sites      97,571               99,373             99,373
only-in-capstone        302                    0                  —
only-in-repo              0                    0                  —
```

**Root cause — corrected after deeper analysis, and worth recording because the first hypothesis
was wrong.** The obvious guess was an `x27` addressing mask. That is not it: `LDUR` with `Rn=x27`
occurs **zero** times in this snapshot. The actual cause is that the scanner decodes only the
**general-purpose register file** — `ldr dD, [x27, #imm]` (encoding `0xFD400000`) was never matched
at all, so an entire class of **double constants** loaded from the object pool was silently
dropped. Measured recall 98.19%, precision 100%; after the fix, capstone and the script agree
across the whole `.text` with 0/0.

Why this is the expensive kind of bug: it breaks precisely the judgement the documentation tells
you to rely on in `dart-aot.md` §9/§10 — *count the references to decide whether a pool entry
matters*. At one measured site the count goes from `[0 refs]` to `[79 refs]`. A reader following
that advice would conclude a live, heavily-referenced object was dead. It affects all Dart 3.x
arm64 snapshots, and the failure is one-sided and silent.

**`dart_disasm.py` — verified on real target.** Decoded output compared against capstone on the same
ranges: **32/32 and 96/96 instructions identical**, `VERDICT: identical decode`. The independently
re-derived caller index also agrees exactly: `callers.json targets=59904 sites=219181`, independent
re-derivation `targets=59904 sites=219181`, **symmetric difference of call sites: 0**. All B/BL
words in range confirmed by capstone: 27,615/27,615.

**`dart_disasm.py` — verified on real target.** Decoded output compared against capstone on the same
ranges: **32/32 and 96/96 instructions identical**, `VERDICT: identical decode`. The independently
re-derived caller index also agrees exactly: `callers.json targets=59904 sites=219181`, independent
re-derivation `targets=59904 sites=219181`, **symmetric difference of call sites: 0**.

**`dart_pool_strings.py` two-byte mode — unusable here because detection is unreliable.** With
`--two-byte`: 936,136 candidates, 57,049 kept (34,216 UTF-16LE). The script's own warning says the
detection is unreliable, and the independent measurement confirms it: 168,700 independent UTF-16LE
CJK runs, and of 9,840 two-byte CJK candidates only 2,081 form chained runs ≥2 — the rest are
coincidental. Sample output is noise (`誋讋讋讋讋`). The one-byte default is the right default.

---

## `coldstart.py` — verified on real target

Used exactly as documented — `--serial`, `--pkg`, `--activity`, `--duration`, `--interval`,
`--expect-activity`. It behaved as advertised and produced the finding that governs this whole
report: the app reaches a splash window and then aborts. The script's existence is why the launch
failure was caught as a *measurement* (timestamped foreground-activity and logcat timeline) rather
than as a vague impression, and its `--expect-activity` design directly addresses the failure it
names in its own docstring — a vendor installer window being captured and read as the app.

---

## External toolchains

Both Dart AOT analyzers were tested, and they behave differently enough that the difference is
itself a finding.

### blutter — **works; the first-run crash is not reproducible**

`blutter` compiles and embeds a matching Dart VM, so it needs one build per Dart version. Building
from source is **mandatory** — the repository's `bin/` is gitignored and it publishes **no releases**,
so there is no prebuilt Dart 3.6.0 executable to fetch. (Naming, for anyone searching:
`bin/blutter_dartvm3.6.0_android_arm64.exe`, not `_windows_x64`.)

Measured cost, which corrects the documentation:

| Step | Time |
|---|---|
| `git clone --depth 1 worawit/blutter` (HEAD `4a60ac6`) | seconds |
| `python scripts\init_env_win.py` (ICU 73.2 + capstone 4.0.2) | **7,049 ms** |
| sparse clone `dart-lang/sdk` tag `3.6.0` | seconds |
| cmake + ninja, 22 targets (unity build via `dartvm_create_srclist.py`) | — |
| link + install `bin/blutter_dartvm3.6.0_android_arm64.exe` | — |
| **whole pipeline, wall clock** | **≈ 78 s** |

`dart-aot.md` §2 budgets "**tens of minutes** for the first build". Reality here is **≈78 s**,
roughly **30× pessimistic**. The toolchain requirement is also overstated: the README asks for a
very recent C++ compiler with C++20 `<format>` and the doc repeats "VS 2022 required", but
**MSVC 19.34 (VS 17.4.3, Nov 2022) is sufficient** — verified by compiling and running a
`std::format` probe with it.

**The crash, and a correction to the first reading.** Run 1 (`blutter.py` under `vcvars64`) built the
VM and linked the exe, then died with exit `3221225477` = **0xC0000005 ACCESS_VIOLATION** and **no
output at all**. Runs 2-4 (invoking the installed exe directly, on `libapp.so`, `libflutter.so` and a
nonexistent path) reproduced it in ~89 ms each — always after argument parsing succeeded (a bad ABI
still prints `ELF: Support only 64 bits` and exits 0) and before the first stdout line, pointing at
`DartApp app{ libappPath.c_str() }` (`blutter/src/main.cpp:29`).

Adding two `std::cerr` traces and relaunching `ninja` (2 targets: recompile `main.cpp`, relink)
produced an executable that **ran to completion, exit 0** (`libapp is loaded at 0x1dfe6d60000 /
Dart heap at 0x1e000000000`) — and then the **originally installed binary also ran clean**: 3/3 runs,
exit 0, 5,899 / 5,862 / 5,928 ms, each producing `pp.txt` (2,639,894 B), `objs.txt` (648,382 B),
`asm/`, and `blutter_frida.js`.

So the verdict is **not** "unusable here". The root cause of the transient fault is **not identified**
and it did not reproduce after the relink, including for the unchanged binary; the best-supported
reading is a first-run/environment artifact rather than a property of this snapshot or of Dart 3.6.0.
Cleared suspects: `std::format` works on MSVC 19.34; capstone 4.0.2 and ICU 73.2 DLLs sit beside the
exe; `--no-analysis` is unnecessary because the full path works. The practical rule this yields:
**budget one retry, and if it still faults, relink before concluding anything about the sample** —
here a tool crash did not mean the target lacked anything.

### aotopsy — **works out of the box**

`aotopsy_v1.6.0_windows_amd64.zip`, 2,994,902 B, sha256
`5a90bcf27f4aaa281ae393bf3038b6e1e2325386fe61c1a18ed089390983fdc1` (matches the release manifest).
Unpack and run — **no compiler, no Dart SDK, no toolchain**, because it parses the snapshot format
directly in Go.

| | result |
|---|---|
| `doctor` | Support **OK**; compressed 4-byte pointers; hash `f956f595844a2f845a55707faaaa51e4`; the same 9 feature flags blutter derived |
| full pipeline | exit 0 — **30,586 functions**, 6,133 class layouts, **39,202 pool entries (38,274 resolved)**, **175,120 call edges** (18,718 BLR, **95.7% annotated**), 20,927 string refs, 556 signal findings |
| artifacts | `functions.jsonl`, `classes.jsonl`, `call_edges.jsonl`, `string_refs.jsonl`, `dispatch_table.jsonl`, `evidence.jsonl`, `asm/` (16,046 files), a `--decompile` pseudocode mode, `_debug strings --xref` |

**The Dart version discrepancy, resolved.** aotopsy `doctor` says **3.6.2**; blutter derives **3.6.0**
from the engine banner; the banner reads `3.6.0 (stable) (Thu Dec 5 07:46:24 2024 -0800)`; and there
is **no `3.6.2` byte sequence anywhere in `libflutter.so` or `libapp.so`**.

Judgement: **3.6.0 is the correct SDK version (observed)** — three independent facts agree (byte
search, blutter's parser, and the fact that the Dart 3.6.0 runtime blutter built accepts the snapshot
hash). aotopsy's `3.6.2` is its own **structural profile label (inferred)**: its README states version
detection is structure-based because the snapshot carries a git-derived hash rather than a version
number, so the label names the newest profile matching that hash. Impact on support is nil, but
**`aotopsy doctor`'s number must not be fed to a VM-compiling tool as an SDK tag.** The banner route
taught in `dart-aot.md` §1 is correct and is the best-validated instruction in that document.

---

## End-to-end: can the kit locate one specific piece of business logic?

**Yes — with an external snapshot dumper in front of it.** This is the question the whole pass was
built to answer, so the worked example is recorded in full.

| # | Tool | Result |
|---|---|---|
| 1 | blutter `pp.txt` | `[pp+0x23548] String: "showRewardAdProvider"` |
| 2 | `dart_pprefs.py --lookup pp_refs_fixed.json 0x23548` | **1 ref site: `0x7a9464`** |
| 3 | `dart_disasm.py libapp.so --pp bout5/pp.txt --refs pp_refs_fixed.json 0x7a9464` | annotated window (below) |
| 4 | `dart_disasm.py --index callers.json 0x7a93ec` | **9 callers** |
| 5 | independent confirmation | `aotopsy _debug strings --find rewardAd --xref` → `used in: ShowRewardAdFamily.call_2f28ac @ 0x7a93ec (pool load @ 0x7a9464, pool[18087])` |

Step 3 resolves the site completely, including the enclosing Dart closure and its source file:

```
7a943c: add  x1, x27, #0x23, lsl #12
7a9440: ldr  x1, [x1, #0x540]   ; pp+0x23540 AnonymousClosure: (0x7a9508),
                                ;   of [package:<app>/pages/video/video_page.dart] ShowRewardAdProvider
7a9454: add  x1, x27, #0x23, lsl #12
7a9458: ldr  x1, [x1, #0x430]   ; pp+0x23430 Obj!ShowRewardAdFamily@b487a1 : {  [8 refs]
```

Two analyzers built by unrelated projects agree on the function name, the address and the pool index
— which is what makes this a verification rather than a coincidence.

**But the kit cannot take step 1 by itself.** Reaching a pool offset from a string requires resolving
the snapshot's internal container, and the kit has no such resolver: 4,241 strings share a name across
4,237 distinct deltas with no constant bridge between the string table and the object pool. blutter
(or aotopsy) supplies that front end. Everything downstream of it — the cross-reference count, the
disassembly window, the caller index — the kit does do, and correctly.

### Documentation defect that matters more than the crash

`dart-aot.md` §2 says of blutter's `asm/`: *"per-class declarations — instructions — **there are none
here**. Do not plan around it."* That is **wrong** for this blutter HEAD on Dart 3.6.0.
`bout5/asm/<plugin>/src/ads/reward/` is 1,327 lines / 71,099 B and contains class
layouts, function signatures **and a full instruction listing with pool annotations and resolved call
targets**:

```
// 0x923b3c: r0 = LinkedHashMap.from()
//     0x923b3c: bl  #0x60165c  ; [dart:collection] LinkedHashMap::LinkedHashMap.from
```

`asm/` is the single richest artifact in the chain, and the document tells the reader to ignore it.
(Secondary nit: `asm/` is one file per **library URI**, mirroring the package path, not per class.)

## Not applicable to this sample — stated, not stretched

- **`native_crash.py`'s "artificially constructed crash" verdict.** The tool exists to decide
  whether a crash was *manufactured* as an anti-tamper response. This target's crash is a genuine
  internal mutex-lifecycle fault that occurs on the unmodified APK, before any modification, on two
  devices. There is no decoy to detect and no tamper event to attribute, so the judgement the tool
  makes was never exercised. **Not applicable — no artificial crash exists here.**
- **`so_constpatch.py`'s "redirect the checker library" use case.** Requires an integrity-check
  library to subvert. This target has **none** — no packer, no integrity checker, no `.so` that
  validates the APK. The redirection capability is real (see the verified `NEEDED` rewrite) but its
  purpose-built scenario does not exist here.
- **`packers.md` / `code-virtualization-and-custom-linkers.md` in full.** No packer: zero hits for
  every known hardening-library name, and the parsed manifest shows an ordinary application class
  rather than a shell stub. **Unverified in this pass** — nothing here should be read as evidence
  either way about how those documents perform.
- **`native-tamper-and-suicide.md`'s judgement chain.** It reads *native anomalies observed from the
  APK side* (immediate SIGSEGV after a repack, the Java layer saying the check passed while the
  process dies). This pass never produced a repack to observe, because **the unmodified app does not
  start**, so there is no working baseline to regress from. The document's scenarios remain
  unexercised.
