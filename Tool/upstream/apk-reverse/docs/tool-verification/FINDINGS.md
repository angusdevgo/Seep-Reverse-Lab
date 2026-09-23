# Findings about the skill, from measuring it

Everything here is a result about **the skill**, not about the target. Each item names the evidence
that produced it and its strength.

---

## F1 — The Coverage claim was partly aspirational, and the pass identified exactly which part

`SKILL.md`'s Coverage section lists as *covered by verified mechanisms*:

> Flutter / Dart AOT: pinning the engine version, decoding the object pool, locating and patching
> business logic inside `libapp.so` (`dart-aot.md`).

Measured against a real Dart 3.6.0 `libapp.so`, that sentence splits into three claims of very
different standing:

| Sub-claim | Standing after this pass |
|---|---|
| pinning the engine version | **verified** — the banner route (§1) is correct and 3.6.0 is confirmed three ways |
| decoding the object pool | **false as written** — the kit cannot do it; there is no resolver |
| locating business logic inside `libapp.so` | **true, but conditional** — it works, on top of an external snapshot dumper that the skill neither ships nor installs |

The worked example in `TOOL-VERDICTS.md` shows both halves at once: the chain
`"showRewardAdProvider"` → `pp+0x23548` → ref site `0x7a9464` → `ShowRewardAdFamily.call_2f28ac
@ 0x7a93ec` succeeded, and step 1 was performed by blutter, not by the skill.

The reason is structural, not a shortage of effort: `dart_pool_strings.py` reports **file offsets**
while `pp.txt` and `dart_pprefs.py` work in **pool offsets**. Over the 4,241 strings present in both
spaces there are **4,237 distinct deltas** (min −1,361,429, max +277,654). The mapping is a property
of the reconstructed pool and is not a constant, so no amount of care inside the script recovers it.

Capabilities the kit does not have, stated plainly: snapshot/object-pool deserialisation; symbol and
name recovery; a real call graph (the `--build-index` index holds raw `B`/`BL` targets only); a
decompiler; a function boundary/size table.

---

## F2 — Two scripts fail in the way that reads as a target finding (the P26 class)

The handover singled out `pitfalls.md` P26: *"a self-built analysis script fails in a way that reads
as a target finding."* This pass produced two live instances of exactly that, which is why the P26
warning earns its place.

**`elf_plt.py` returned a confident false negative.** It reports 3,437 stubs where `.rela.plt` holds
3,438, and answers `0x587060 -> not a resolved stub` for an entry that is a legitimate stub for
`dl_iterate_phdr`, with a real caller at `0x576a2c`. Nothing in the output indicates a problem. For
the script's stated purpose — deciding whether a hardening symbol exists in a library — the wrong
answer is indistinguishable from the right one.

**`find_refs.py` returned a clean empty result for input it could not read.** Its docstring advertised
"a smali tree or a directory of dex files"; `iter_files()` accepted only `.smali`. Given the dex
directory it printed `[total refs] 0`, exited **1**, and emitted no warning. This is worse than a
crash: it is the exact input to "nothing references this, safe to patch", produced by the very tool
recommended for judging blast radius before patching.

Re-measured later: the exit code recorded in this section was **0** and it is **1** — the `total == 0`
path has always returned 1. The correction matters because it moves the defect from "no signal at
all" to "the signal was there and the text contradicted it": the note diagnosed the *needle* and never
named the *input form*, so a caller reading the message was still sent the wrong way. Fixed and
re-verified; see F9 for what measuring it turned up underneath.

Both, plus `dart_pprefs.py`'s silently dropped double constants, share one property: **the failure is
one-sided and quiet.** None of the three reports reduced confidence in its own output.

---

## F3 — Defects found, ranked by consequence

| # | Script | Defect | Consequence | Status |
|---|---|---|---|---|
| 1 | `find_refs.py` | `iter_files()` matched only `.smali`; a dex dir yielded 0 results and a direct dex was regex-scanned as text | silent false "no references" on the tool whose job is blast-radius | **fixed, re-verified against a fixture and the real target** |
| 2 | `elf_plt.py` | loop bound `off < fsz - 16` misses the final stub slot | false negative for one real symbol per library, conditionally | **fixed on a copy, re-verified** |
| 3 | `dart_pprefs.py` | only the GP register file is decoded; `ldr dD,[x27,#imm]` (`0xFD400000`) and all double constants lost | under-reports pool references (302 displacements / 1,802 sites here), which breaks the "count refs to judge importance" advice in `dart-aot.md` §9/§10 — one site went `[0 refs]` → `[79 refs]` | **fixed on a copy; agrees with capstone 0/0** |
| 4 | `so_constpatch.py` | rebuild drops the zip `extra` field, destroying 4 KB alignment | for `extractNativeLibs=false` APKs the output will not load; masked here because this target is DEFLATED + `extractNativeLibs=true` | **cause identified, proven by fixture; not fixed** |
| 5 | `so_constpatch.py` | `--diff --name-regions` compares file offset with vaddr | feature completely inert on libraries where `p_vaddr != p_offset` (2 of 36 here), with no warning | cause identified |
| 6 | `so_constpatch.py` | `external_attr` rewritten on 1982/1982 entries | metadata-based integrity comparison detects the rebuild | cause identified |
| 7 | `dexutil.py` | switch payloads decoded as instructions; `decode()` does not resolve operands | caused a spurious "desync likely" verdict on `saveToLocal` | cause identified |
| 8 | `so_constpatch.py` | "N byte(s) changed" is the overwrite window, not bytes changed | overstates change count (13 reported vs 7 actual) | cause identified |
| 9 | `lib_map.py` | `?` means both "read failed" and "not probed" | a real read failure is invisible | cause identified |
| 10 | `dart_pool_strings.py` | TSV escaping is lossy for LF/CR/TAB | 7 of 18,363 rows ambiguous; 19 entries genuinely contain those bytes | cause identified |
| 11 | `elf_plt.py` | `size = 16 if ... else 16` | dead code | cause identified |
| 12 | `dex_strings.py` | `--per-file` prints only files with hits | can be misread as "only this dex was scanned" | cause identified |

Items 1-3 are the ones that changed a conclusion during this pass rather than merely being noticed.

---

## F4 — Documentation contradictions

Independently found while mapping the skill and while using it. The executable cross-reference
checkers (`check_refs.py`, `check_repo.py`) pass, so these are invisible to the repo's own gates.

| # | Location | Problem |
|---|---|---|
| 1 | `dart-aot.md` §2 | Claims blutter's `asm/` has *no instructions* — "Do not plan around it." **Wrong.** One plugin file under `asm/<plugin>/src/ads/reward/` is 1,327 lines carrying class layouts, signatures, a full instruction listing, pool annotations and resolved call targets. It is the richest artifact in the chain and the doc says to ignore it. |
| 2 | `dart-aot.md` §2 | Budgets "tens of minutes" for the first blutter build; measured **≈78 s** (~30× pessimistic). Also demands a very recent C++ compiler; **MSVC 19.34 (Nov 2022) suffices**. |
| 3 | `dart-aot.md` §7 | Presents two-byte hit chaining as an acceptance test. On this sample, 9,840 two-byte CJK candidates yield 2,081 chained runs, all garbage. |
| 4 | `signature-derived-keys.md:61` | Documents `python scripts/sig_probe.py --live --pkg <pkg>` — the script has no `--pkg`; it takes `--live PKG`. Line 54 and `pitfalls.md` P27 give the correct form. |
| 5 | `dart-aot.md:204` | `dart_disasm.py ... --index callers.json --build-index` omits the required argument value; argparse errors out. |
| 6 | `byte-level-patching.md:186` | Says different-length strings "need `dex_strpatch`-class tooling", while `dex_strpatch.py` requires `len(new) == len(old)` — it is precisely the tool that cannot do this. Contradicts `dex-patching.md:123`. |
| 7 | Coverage vs `toolchain.md` | Coverage lists Unity/IL2CPP logic recovery as **not covered**, but `toolchain.md` Tier 4 names concrete tooling without pointing back at that disclaimer, so a reader of `toolchain.md` alone would take IL2CPP for a supported route. |
| 8 | Script count | `SKILL.md`/`README.md` index 35 rows, which is 34 scripts plus the `scripts/dexpatch/` directory row. |
| 9 | `dart_pool_strings.py` docstring | Says two-byte auto-detection is unreliable (confirmed here); `dart-aot.md` §7 treats UTF-16LE hits as a reliable rule. |
| 10 | `verification.md` rung 7 | Re-downloading a distributed file to compare hashes has no landing place in `SKILL.md`'s six "done" criteria, so the two sections disagree on strength. |

Item 1 is the most damaging because it steers a reader away from the best available evidence.

---

## F5 — "verified mechanisms" left no reproducible trace in the repo

The Coverage preamble frames its list as *verified mechanisms*, and `references/long-task-discipline.md`
defines **Observed** as *"reproduced it, with the exact command and output"*. The repository contains
no sample, no fixture, no captured log or screenshot, no patch record, no test and no CI, and its
`README.md` states it holds no target-specific data.

So the strongest support the repository itself can exhibit for those claims is *Inferred*. This is
**not** an accusation that the claims are false — several were confirmed here on the first attempt,
and `dart-aot.md` §1 proved exactly right. It is a statement about evidentiary standing: the repo
asks its readers to label their own claims and does not leave itself a way to meet its own bar.

The concrete measurement figures that *are* reproducible are the 14 sample-scoped numbers listed in
the skill map (e.g. dex 4.32 MB → 7.73 MB; `.RSA` 1199 B vs 777 B at runtime; a log tag going `8 → 0`).

---

## F6 — Boundary evidence: where the skill's method held, and where it ran out

This is the observation the pass was built to produce, so it is stated as a sequence rather than a
verdict.

**Held, unchanged:** manifest and packer triage; multi-dex string/class recon at 27.6 MB across four
dex files (`dex_strings.py`, `dexutil.py`); native ELF import mapping at scale (36,974 relocations);
live-process library mapping; equal-length `.so` constant patching; the launch-timeline methodology
(`coldstart.py`); the P26 discipline itself — checking whether a tool was ever able to answer before
reading its silence as a finding, which is what turned the blutter crash from a false "unusable" into
a corrected "works after a relink".

**Ran out:** from the Dart snapshot inward. Everything past `pp.txt` is fine; getting *to* `pp.txt`
from the binary requires a container resolver the kit does not have. That is one dependency, not a
subject area.

**Not exercised at all:** packers, code virtualization, custom linkers, integrity-check redirection,
tamper-triggered suicide. This target has none of those, and the unmodified app's own startup failure
also removes the repack loop those scenarios need.

---

## F7 — A trap in this specific environment that will produce false confirmations

`androguard` 4.x (the version installed here) has **four independent reference-analysis failures on
this sample**: `get_xref_from()` returns 0 for everything, including `AdLoader.loadAd()V` which has
20+ callers by other means; `get_ref()` raises; a full `get_operands()` sweep returns 0 strings.

Anyone who reaches for androguard to double-check a "zero references" conclusion will get **zero, and
therefore agreement**. The zero-reference result in `TARGET-FACTS.md` does not come from androguard;
it comes from `dexutil.py` plus raw-byte re-checks of the bodies that would not decode cleanly. This
is worth a line in the environment documentation because it is a tool that lies in the direction of
the hypothesis being tested.

---

## F8 — Reconciling the two failures: a genuine but unproven loader signal

Recorded as a boundary between what was established and what was guessed, because collapsing them
would be its own error.

The launch does show non-standard startup plumbing (observed):

- `E LoaderLog: 10026 / 101004` on the device, `10020 / 101003` on the emulator — an SDK-side
  loader logging numeric status codes
- `E Instrumentation: Uninitialized ActivityThread, likely app-created Instrumentation, disabling
  AppComponentFactory` — the process is not taking the ordinary `ActivityThread` path
- `E <PKG-truncated>: Unknown bits set in runtime_flags: 0x40000000` (logcat truncates the tag to 23
  characters, so the package name appears clipped in this line)

And yet the dex-side packer verdict is clean: no hardening library in the native set, an ordinary
`application android:name` (the app's own class, not a packer stub), no known packer markers. Those two
observations sit in tension.

**Not resolved.** The `LoaderLog` emitter was not attributed to a specific class — the string exists
in `classes2.dex` and `classes3.dex` but the classes that declare it are third-party, and this pass
did not trace the call chain. Whether this plumbing is a benign logging SDK, part of the Flutter
plugin bootstrap, or a light-weight loader contributing to the abort is **unverified**. Stating it
as established would be exactly the kind of overreach this report is trying to document.

---

## F9 — Fixing F2 exposed a deeper one: the dex opcode table was shifted, and nine widths were wrong

Fixing `find_refs.py`'s dex path means depending on `dexutil.decode()`'s boundaries being right, so
that was measured rather than assumed. It was not right: on a real 8.9 MB dex, **65 of 50,791 method
bodies did not decode to their declared boundary**, and **32 carried an operand index outside the
table it indexes**.

The cause is a run of `OP_NAMES` and `insn_units` shifted by one from `0x16` to `0x2C`:

| opcode | specification says | the repository had | width: spec vs repo |
|---|---|---|---|
| `0x17` | `const-wide/32` (31i) | `const-wide/16` | **3 vs 2** |
| `0x18` | `const-wide` (51l) | `const-wide/32` | **5 vs 3** |
| `0x1B` | `const-string/jumbo` (31c) | `const-class` | **3 vs 2** |
| `0x1C` | `const-class` (21c) | `monitor-enter` | **2 vs 1** |
| `0x1E` | `monitor-exit` (11x) | `check-cast` | **1 vs 2** |
| `0x20` | `instance-of` (22c) | `array-length` | **2 vs 1** |
| `0x21` | `array-length` (12x) | `new-instance` | **1 vs 2** |
| `0x23` | `new-array` (22c) | `filled-new-array` | **2 vs 3** |
| `0x26` | `fill-array-data` (31t) | `throw` | **3 vs 1** |
| `0x2C` | `sparse-switch` (31t) | *(absent)* | **3 vs 2** |

Plus `0xFA`-`0xFF` (`invoke-polymorphic`, `invoke-custom`, `const-method-handle`,
`const-method-type`), absent from the width logic and defaulting to one unit each where the
specification has 4, 4, 3, 3, 2, 2.

The `goto` family went with it: `branch_target()` computed a branch target for `0x27`, which is
`throw`, and read the offset width one opcode early for the rest. `dex_find_insn.py`'s kind map
carried the same shift in its `goto` and `switch` entries, so a semantic search for a branch matched
the wrong instructions.

That this survived an earlier "fix instruction widths" pass is not surprising in hindsight:
`insn_units` ended with `if op == 0x29: # measured: this slot is goto/16 (20t)` — the shape of a
repair made one observation at a time, where the width of `0x29` was corrected without checking the
opcode's *name* against a specification. Name and width were wrong together and consistently, which
is exactly why the decode still looked plausible.

**How it was settled.** Not by reading the table again, but by two measurements that do not depend on
this project's code:

1. **Self-consistency at scale.** A real dex is a stream ART can execute, so a correct decoder must
   land every method body exactly on `insns_off + insns_size*2`. 65 did not. After the fix,
   **50,791 of 50,791 do, with 0 illegal operand indices.**
2. **A second decoder.** `androguard` 4.1.4 decoded the same dex independently. Aligned by method
   order, the per-instruction width sequences are **identical for all 50,791 bodies — 0 differing.**

Names and widths now come from the format specification's table, and width is a lookup (`OP_UNITS`)
rather than a chain of range tests, which is the shape that made this class of error possible.

**Two things this pass did not fix, recorded so they are not mistaken for clean:**

- **`dexutil.string()` decodes MUTF-8 with `errors="replace"`.** Identifiers containing non-BMP
  characters decode to U+FFFD — this sample has them, and one crashed a `print` with a
  `UnicodeEncodeError` on a non-BMP codepoint. A class name read from the dex may therefore not
  compare equal to the same name read from another tool. It does not affect instruction decoding or a
  descriptor-based needle, but it is why the cross-check above had to align by order rather than by
  key.
- `OP_NAMES` had no entry for roughly 150 valid opcodes (`aget`/`aput`, the `cmp` family, the
  `neg`/`not`/conversion unops, the arithmetic and `lit8`/`lit16` families). They decoded correctly by
  fallback but printed as `op_XX`. The regenerated table covers 224 opcodes.
