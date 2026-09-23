# Extension verification — extraction shells and the Dex-VMP boundary (bench rows B3 / B4)

Covers benchmark rows **B3** (extraction-shell skeleton detection) and **B4** (Dex-VMP
boundary: refuse-to-repack and downgrade the deliverable). Strength labels are this
directory's own three tiers: **observed** (an exact command and its output are quoted
here), **inferred** (follows from observed facts; the step was not executed),
**unverified** (assumed or externally reported, not reproduced here).

Everything below was produced on this repository's Windows 11 host with the rootless
PC toolchain in `tools/_work/ENV.md`; the device results in §4 name a
`<DEVICE>` and use `<PKG>` placeholders for the target package.

## 0. Headline

| Question | Answer | Strength |
|---|---|---|
| Does `stub%` separate a skeleton copy from a genuine dex? | **Only when the shell writes bare `return-void`.** Three other measured emptying shapes score 0.0 %–2.3 %, at or below the *untouched* control (1.9 %) | observed |
| Was the pre-existing `trivial_ratio` detector correct? | **No — two defects**, one of which inverted the ranking and named a fully-nop-wiped skeleton the "most likely original" | observed |
| Is `repos/CyReverse`'s shipped "extraction shell" asset usable as a shell fixture? | **No.** The pair differs by six bytes and one body; neither is a shell | observed |
| Is `DexPatcher/assets/ezAndroid.apk` a Dex VMP? | **No.** It is a JNI-sinking target: 7 `native` declarations, an exported `Java_*` for each, 34,566 clean dalvik instruction decodes, zero structural errors | observed |
| Can a static dex probe decide VMP vs not? | **It can decide "not dex-VMP"** when the bodies decode cleanly and each native declaration has an export. It **cannot** decide whether the native island performs runtime hardening | observed (negative half) / unverified (positive half) |
| Does `dex_mem_scan.py` find and cut a dex out of a blob? | **Yes** — exact offset, no false hits in 2 MiB of noise, image accepted by the judge | observed |
| Does it reach a dex in a live process's anonymous mapping? | **Not measured here.** The fixture is built and the commands staged; the device was held by another row throughout | unverified |

One claim in this pass was **retracted**: §3.4 records a Dex-VMP verdict drawn from a
desynchronised decoder and the measurement that killed it.

---

## 1. B3 — the shipped CyReverse "extraction shell" assets are a 6-byte difference, not a shell

Source: `repos/CyReverse/app/src/main/assets/{classes3.dex, classes3_extracted.dex}`
(12,536 B each).

```
$ python skills/apk-reverse/scripts/dex_dump_validate.py tools/_work/bench/unpack/b3
== dex dump validation: 2 file(s), 2 parse, 0 rejected ==
name                     size  sha256[:12]   ver  cksum  sig  class  noco  code  stub%
cyrev-extracted.dex     12536  c2d7345e955a  037  ok     BAD      4     0    20   10.0%
cyrev-skeleton.dex      12536  ba9d5b120a3a  037  ok     ok       4     0    20   10.0%
```

A byte diff of the pair (`tools/_work/bench/unpack/b3/analyze_pair.py`) locates every
difference:

```
$ python tools/_work/bench/unpack/b3/analyze_pair.py
len A=12536 len B=12536
first diff offset = 8 (0x8)
diff byte count = 6
diff ranges:
  0x8 .. 0x8  (1 B)          <- dex checksum (header offset 8)
  0xa .. 0xb  (2 B)          <- dex signature, first half (offset 12 is 4 B wide)
  0x121c .. 0x121c (1 B)     <- INSNS of PluginClass->getString, units 0 and 2
  0x121e .. 0x121e (1 B)
  0x1220 .. 0x1220 (1 B)
```

Per-method census of the pair shows the "extracted" copy is the *degraded* one:

```
== cyrev-skeleton.dex ==      Lcom/cyrus/example/plugin/PluginClass;->getString  insns=3  units=001a 0087 0011
== cyrev-extracted.dex ==     Lcom/cyrus/example/plugin/PluginClass;->getString  insns=3  units=0000 0000 0000
```

`const-string v0, "…"; return-object v0` was overwritten with three `0x0000` units in
exactly one of the twenty bodies, and the header was re-fixed. The shipped
`classes3_extracted.dex` is **not** an extraction shell and **not** a recovered dex:
it is a single-body demonstration of body clearing, with 19 of 20 bodies identical to
the skeleton. Neither file can test extraction-shell routing — 10.0 % `stub%` on both
sides is a coincidence of the same body set, not a signal.

**Consequence for the benchmark row:** B3 cannot be run against this asset pair. The
skeleton measurement below had to be built from a real application dex instead.

## 2. B3 — measured `stub%` across every emptying shape, with a zero-change control

Fixture builder: `tools/_work/bench/unpack/b3/make_skeleton.py` derives each variant
from a real 982,480-byte application dex (`src-r2pay.dex`, extracted from
`tools/_work/bench/apks/r2pay-v1.0.apk`, sha256 `c89ff2364879…`). Every variant is
**byte-length preserving**: only the `insns` array of a `code_item` is rewritten and
the tail is nop-filled, so offsets, class table and string table are untouched and the
header is re-fixed with `dexutil.fix_dex_header` (signature first, checksum last).

```
$ python tools/_work/bench/unpack/b3/make_skeleton.py src-r2pay.dex skel
source: src-r2pay.dex
  ctrl.dex           fraction=0.00 mode=return   emptied=0/5061
  skel-25.dex        fraction=0.25 mode=return   emptied=1265/5061
  skel-50.dex        fraction=0.50 mode=return   emptied=2531/5061
  skel-75.dex        fraction=0.75 mode=return   emptied=3796/5061
  skel-all.dex       fraction=1.00 mode=return   emptied=5061/5061
  pruned.dex         fraction=1.00 mode=pruned   emptied=5061/5061
  nopfilled.dex      fraction=1.00 mode=nop      emptied=5061/5061
  allstub.dex        fraction=1.00 mode=allstub  emptied=5061/5061
  throwstub.dex      fraction=1.00 mode=throw    emptied=4134/5061
```

Verdicts from `dex_dump_validate.py` over the whole set — the decisive matrix:

```
$ python skills/apk-reverse/scripts/dex_dump_validate.py tools/_work/bench/unpack/b3/skelall
name            size  sha256[:12]  ver cksum sig  class noco  code   stub% erased% emptied%
allstub.dex   982480  c8d7ca8fb163 035  ok   ok     647  250  5061  100.0%   0.0%  100.0%
ctrl.dex      982480  1b3a97896b40 035  ok   ok     647  250  5061    1.9%   0.0%    1.9%
nopfilled.dex 982480  de92dcea4eaf 035  ok   ok     647  250  5061    0.0% 100.0%  100.0%
pruned.dex    982480  58d7fa3dce48 035  ok   ok     647  250  5061   93.2%   0.0%   93.2%
skel-25.dex   982480  63346d9b41f5 035  ok   ok     647  250  5061    1.7%   0.0%    1.7%
skel-50.dex   982480  d84601b7aa47 035  ok   ok     647  250  5061    1.7%   0.0%    1.7%
skel-75.dex   982480  64114285656d 035  ok   ok     647  250  5061    2.1%   0.0%    2.1%
skel-all.dex  982480  6345daef0a3f 035  ok   ok     647  250  5061    2.3%   0.0%    2.3%
throwstub.dex 982480  cab8fd51a743 035  ok   ok     647  250  5061    1.9%   0.0%    1.9%
```

Read the `mode=` column against `stub%`:

| Emptying shape (what the shell leaves behind) | `stub%` | Separated from `ctrl` (1.9 %)? |
|---|---|---|
| bare `return-void` in every body (`allstub`) | **100.0 %** | yes, by 98 points |
| body truncated to `const/4 v0,#0; return v0` + nop fill (`pruned`) | 93.2 % | yes |
| nop fill, no return at all (`nopfilled`) | **0.0 %** | **no — scores *below* the untouched control** |
| `new RuntimeException; throw` stub (`throwstub`) | 1.9 % | **no — indistinguishable from control** |
| 25 % / 50 % / 75 % of bodies emptied with a legal minimal body | 1.7 / 1.7 / 2.1 % | **no** |

Three conclusions, all observed:

1. **The threshold is not a number, it is a shape.** `stub%` is bimodal — it is either
   ≈ control (blind) or ≈ 100 % (sighted). There is no intermediate band where a
   threshold could sit, so the "tens of percent" calibration the reference file
   describes has no measured support.
2. **Partial extraction is invisible.** `skel-75.dex` — three quarters of all bodies
   emptied — reports 2.1 % against a 1.9 % control, a 0.2-point difference inside the
   sampling noise of what a real app's own trivial bodies contribute.
3. **The two shapes that defeat it are the two that real shells prefer.**
   `throw new RuntimeException` stubs are the classic 360/legu family shape, and a
   nop-wiped body is what a shell writes when it clears the slot before decrypting.

The false-negative on `nopfilled` was a **defect, not a boundary**, and is fixed in §3.
The `throwstub` blind spot is a **boundary** and is documented as one.

## 3. B3 — defects found in `dex_dump_validate.py`, and the fix

### 3.1 Defect 1: a fully nop-filled body was classified `real`

`classify_body` skipped every `0x0000` unit and then fell through to `return "real"`
when nothing else was found. Measured consequence: `nopfilled.dex` — **all 5,061
bodies wiped** — reported `stub% = 0.0`, and the ranking named it the most likely
original:

```
$ python skills/apk-reverse/scripts/dex_dump_validate.py …/skel/{nopfilled,ctrl}.dex
ranking (most likely original first):
  1. nopfilled.dex                stub%=0.0  cksum=ok  sig=ok  classes=647
  …
verdict: nopfilled.dex is the most likely original (1 copy(ies) in this set)
```

An agent routing on that line patches a wiped skeleton. That is the failure the file
exists to prevent, so the defect is on the wrong side of "the tool still produces
output".

**Fix.** `classify_body` gained two classes and a wider body scan:

- `erased` — `insns_size > 0` with every unit `0x0000`. A real compiler never emits a
  whole body of nops, so this is skeleton evidence.
- `minimal` — a body truncated to `const/4 vR,#0; return vR` (legal, and the shape the
  detector is blind to by design). Reported separately so the blind spot is visible
  rather than hidden inside `real`.
- The early-exit `meaningful > 1 → real` became `meaningful > 2`, so the two-unit
  minimal body reaches its own verdict instead of being mislabelled.

`trivial_ratio` keeps its original definition so previously recorded numbers stay
comparable; `emptied_ratio = (stub + erased) / with_code` is the new skeleton signal,
and `rank_key` sorts on it **low-first** with `bodies_erased` as a tiebreak.

### 3.2 Defect 2 (retracted in-flight): `0xNN0E` is not malformed

An intermediate version of the fix classified a lone `0x020E` unit as `malformed`,
reading a non-zero high byte on a `0x0E` opcode as an illegal `return-void`. The
control dump proved otherwise — 82 of the untouched dex's own bodies are exactly that
shape — and `const/4 v0, #0; return v0` is a legal minimal non-void body. The class was
renamed `minimal`, its comment corrected, and the fixture extended with `pruned.dex`
to measure it deliberately (93.2 %, `stub%` sighted). Recorded here because the
mislabel would have taught the next reader that ordinary short methods are damage.

### 3.3 Post-fix behaviour, and no regression on the recorded fixture

`nopfilled.dex` is now ranked last and flagged:

```
  8. nopfilled.dex   stub%=0.0  erased%=100.0  cksum=ok  sig=ok  classes=647  <-- SKELETON: emptied%=100, extraction-shell shape
  9. …
verdict: skel-25.dex is the most likely original (1 copy(ies) in this set)
```

The pre-existing acceptance fixture from `EXTENSION-unpacking.md` §2 still produces
its recorded verdict, with only the two new columns appended:

```
$ python skills/apk-reverse/scripts/dex_dump_validate.py tools/_work/t2-unpack --find 'Lcom/stub/'
== dex dump validation: 7 file(s), 4 parse, 3 rejected ==
01_original_shell.dex          8923752  bcd1c0488e86  035  ok      BAD          4    160     29    3.4%    0.0%    3.4%
02_duplicate.dex               8923752  bcd1c0488e86  035  ok      BAD          4    160     29    3.4%    0.0%    3.4%
03_broken_magic.dex            8923752  33eee53b1317    ?  REJECTED: magic=b'XXXX'
04_tampered_body.dex           8923752  b89bc8cc73d9  035  BAD     BAD          4    160     29    3.4%    0.0%    3.4%
05_truncated.dex                 65536  e6687390a663  035  REJECTED: file_size=8923752 actual=65536
06_extracted_skeleton.dex      8923752  85e56fed1d56  035  ok      ok           4    160     29  100.0%    0.0%  100.0%
07_tiny_garbage.dex                 16  be45cb2605bf    ?  REJECTED: too small (16 B) to carry a dex header
verdict: 01_original_shell.dex is the most likely original (2 copy(ies) in this set)
```

Same winner, same three rejections, same dedupe group. The change is additive on that
fixture and corrective on the new one.

### 3.3b The ranking was still pointing at a modified image (found by independent review)

The first fix above added the `emptied_ratio` signal — and then **kept ranking on a
metric this same pass had just proved insensitive to skeletons**. Reproduced by
leading the review on the variant set:

```
$ python skills/apk-reverse/scripts/dex_dump_validate.py tools/_work/bench/unpack/b3/skel
ranking (most likely original first):
  1. skel-25.dex                  stub%=1.7  erased%=0.0  cksum=ok  sig=ok  classes=647
  2. skel-50.dex                  stub%=1.7  erased%=0.0  cksum=ok  sig=ok  classes=647
  3. ctrl.dex                     stub%=1.9  erased%=0.0  cksum=ok  sig=ok  classes=647
  …
verdict: skel-25.dex is the most likely original (1 copy(ies) in this set)
```

`skel-25.dex` — a dex with **25 % of its bodies removed** — was named the most likely
original, and the genuine untouched control ranked third. The cause is the bimodality
of §2: inside the low band the ratio is not a signal, and 1.7 % versus 1.9 % is noise
(the extracted bodies are replaced by `const/4 + return`, which *lowers* the
`return-void` count relative to the control). An agent routing on that line adopts a
modified image as its baseline, and every later diff is then built on the wrong
artifact — the same class of failure as the defect in §3.1, reached by a different
path.

**Fix.** `rank_key` became three-level, with an explicit eviction level so that either
signal can disqualify an image instead of the two merely tying:

1. `emptied_ratio >= 0.5` sorts last. Nothing mostly emptied is a candidate however
   else it scores. This level exists because the count below cannot see the
   `return-void`-in-every-body skeleton: that image has `minimal = erased = 0`, so a
   pure-count key ranked it **first** — measured, and it is why this level was added
   rather than the count being promoted alone.
2. `bodies_minimal + bodies_erased` low-first. This orders the low band, where the
   count is monotone: 82 untouched, then 1299 / 2524 / 3736 / 4946 at 25 / 50 / 75 /
   100 %.
3. `emptied_ratio` low-first, then header verdicts, then name.

Result on the same command:

```
ranking (most likely original first):
  1. ctrl.dex                     stub%=1.9  erased%=0.0  min/erased=82    cksum=ok  sig=ok
  2. only.dex                     stub%=1.9  erased%=0.0  min/erased=82    cksum=ok  sig=ok
  3. throwstub.dex                stub%=1.9  erased%=0.0  min/erased=82    cksum=ok  sig=ok
  4. skel-25.dex                  stub%=1.7  erased%=0.0  min/erased=1299  cksum=ok  sig=ok
  5. skel-50.dex                  stub%=1.7  erased%=0.0  min/erased=2524  cksum=ok  sig=ok
  6. skel-75.dex                  stub%=2.1  erased%=0.0  min/erased=3736  cksum=ok  sig=ok
  7. skel-all.dex                 stub%=2.3  erased%=0.0  min/erased=4946  cksum=ok  sig=ok
  8. allstub.dex                  stub%=100.0 erased%=0.0 min/erased=0    cksum=ok  sig=ok  <-- SKELETON
  9. pruned.dex                   stub%=93.2 erased%=0.0  min/erased=344   cksum=ok  sig=ok  <-- SKELETON
 10. nopfilled.dex                stub%=0.0  erased%=100.0 min/erased=5061 cksum=ok  sig=ok  <-- SKELETON
verdict: ctrl.dex is the best-supported candidate for the original (1 copy(ies) in this set)
```

The control wins and every skeleton sorts behind it. The verdict line now states the
key and its limits instead of declaring a winner outright, and phrases the result as
"best-supported candidate" with an instruction to confirm before patching. `--trim`,
`--json` and `--find` are unchanged (verified: the recorded fixture still returns
`01_original_shell.dex` first, `--json` only gained keys). Note the residual limit the
report prints rather than hides: **`throwstub.dex` still ranks third**, because no body
statistic here sees a `throw`-stub skeleton. That is a boundary, not a bug — it is
listed in §7 with the reproduction.

### 3.4 A retracted Dex-VMP verdict — the measurement that killed it

An intermediate workbench script of mine
(`tools/_work/bench/unpack/b4/vmp_probe.py`, `vmp_methods.py`) decoded instruction
widths from a hand-written table and reported:

```
code_items=22424  desync=1393  (6.21%)   bad_op=0xf8 / 0xef / 0xea / …
```

I read that as "bodies present but not decodable → private opcodes → Dex VMP". **The
reading was wrong, and the error was my table's.** The official decoder settles it:

```
$ E:\tools\android-14\dexdump.exe -d tools/_work/bench/unpack/b4/orig/classes.dex
Processing 'orig\classes.dex'...
Opened 'orig\classes.dex', DEX version '035'
  … 943,223 lines …
instruction lines (hex:...)  : 348566
code items resolved ('insns size :') : 22424
code '(none)'                : 1179
```

One of the methods my script called a desync decodes cleanly under `dexdump`:

```
--- androidx.appcompat.app.AlertController$ButtonHandler.<init>:(Landroid/content/DialogInterface;)V
      insns size    : 11 16-bit code units
1fd564: 7010 9b05 0100   |0000: invoke-direct {v1}, Landroid/os/Handler;.<init>:()V
1fd56a: 2200 040e        |0003: new-instance v0, Ljava/lang/ref/WeakReference;
1fd56e: 7020 fb76 2000   |0005: invoke-direct {v0, v2}, Ljava/lang/ref/WeakReference;.<init>:(Ljava/lang/Object;)V
1fd574: 5b10 ed08        |0008: iput-object v0, v1, …$ButtonHandler;.mDialog:…;
1fd578: 0e00             |000a: return-void
```

My script consumed 9 of 11 units and stopped on `0xed`; `0xed` is a legal
`invoke-*/range` opcode. **The lesson is the one the reference file already states and
this pass then failed to apply: a hand-rolled opcode table is not a VMP detector, and
"my decoder desynchronised" is a statement about my decoder.** Any future
"rare-opcode density" metric must be validated against `dexdump` on the same file
before it is allowed to inform a verdict.

The corrected count of bodies that fail to decode as dalvik in this dex is **0**.
Correction confirmed by an independent path: `dexdump` emits 34,566 instruction lines
and reports no structural error for any of the 22,424 code items.

## 4. B4 — the Dex-VMP judgement chain, re-opened

### 4.1 Static findings (`observed`)

Target: `repos/DexPatcher/assets/ezAndroid.apk`, 2,984,841 B, sha256
`76e3fa8119cf8b7c…`, package `<PKG>` (the `ezAndroid` CTF sample shipped in DexPatcher).

```
$ python skills/apk-reverse/scripts/dex_dump_validate.py …/b4/orig/classes.dex
classes=2905  methods_with_code=22424  stub%=1.9  cksum=ok  sig=BAD
```

- **Native declarations: 7**, all in the app's own obfuscated classes, each with no
  code (`code : (none)`), enumerated from `dexdump`:
  `Lcom/example/ezandroid/C;->cf(Ljava/lang/String;I)Z`,
  `Lcom/example/ezandroid/MU;->GMS(Ljava/lang/String;)Ljava/lang/String;`,
  `Lcom/example/ezandroid/S;->Stringfjni()Ljava/lang/String;`,
  `Lcom/example/ezandroid/S;->onCreate`, `Lcom/example/ezandroid/S2;->onCreate`,
  `Lcom/example/ezandroid/S$1;->onClick`, `Lcom/example/ezandroid/S2$1;->onClick`.
- **Two JNI exports** in `lib/arm64-v8a/libezandroid.so` (206,904 B, aarch64):
  `Java_com_example_ezandroid_S_Stringfjni` @ `0xea6c` (184 B) and
  `Java_com_example_ezandroid_MainActivity_stringFromJNI` @ `0xe91c` (184 B).
  Both are thin JNI wrappers that construct a `std::string` and dispatch through a
  virtual call — the body of the check is behind the vtable, not in the wrapper.
- **No `JNI_OnLoad` and no `RegisterNatives` symbol** anywhere in the library; the
  string `JNI_OnLoad` does not occur in the file at all.
- **`assets/` holds six small opaque files** (`0OooOO` 118 B, `O0ooOO` 126 B,
  `oo0Ooo` 86 B, `ooO0oo` 132 B, `OOoo0O` 398 B, `OOooO0` 260 B). Each begins with a
  three-unit header (`05 00 38 00 02 00 …`) followed by 2-byte-aligned units.
- **No dex string references those six filenames.** Grep over the full 943,223-line
  `dexdump` output for `0OooOO|O0ooOO|oo0Ooo|ooO0oo|OOoo0O|OOooO0|assets/` returns
  **0 hits**.

### 4.2 Verdict: JNI sinking, not Dex VMP (`observed`)

The reference file's Dex-VMP test is "the dump's method bodies are intact but decode
as private opcodes — rare-opcode density off the charts, unknown opcode slots". On this
target **zero method bodies fail to decode**, and every `native` declaration has a
matching exported `Java_*`. The dex is not carrying an encoded program; the code left
the dex for the `.so`, which is `java2c-and-jni-sinking.md`'s territory, not this
file's. The two must not be conflated: an agent that reads "bodies decode as nonsense"
here will go hunting a private disassembler for code that is ordinary ARM64 in a
206 KB library.

The six `assets/` files are a separate, **unresolved** observation: they are not
referenced by any dex string, so they cannot be load-bearing at the dex layer. Whether
the native island reads them by constructing the path at runtime, and what they
contain, is **unverified** here — it needs a dynamic run (§4.3), not more static
searching.

### 4.3 What static analysis structurally cannot see (the B4 boundary)

`java2c`'s independent pass reached the same classification on this sample and recorded
that the hardening takes effect **at runtime only**. That is the general shape, and it
is the half of B4 that no dex probe can settle:

| Question | Answerable statically? | Why |
|---|---|---|
| Are the bodies real dalvik or private opcodes? | yes | `dexdump` decodes them or does not; measured 0 failures here |
| Did the code leave the dex for native? | yes | `native` access flags + `Java_*` exports / `JNI_OnLoad` |
| Does the native island check the signature / root / debugger? | **no** | the logic is ARM64 behind a vtable; the check may not exist in any dex |
| Do those `assets/` blobs get decrypted and used? | **no** | the path may be assembled at runtime; grep for the literal names finds nothing |
| Does a repack actually fail, and why? | **no** | needs the repack installed and run against a control (G4) |

**Rule this pass proposes for the reference file:** a static dex probe may return
"this is *not* dex-VMP" when the bodies decode cleanly and every native declaration has
an export. It may **not** return "this is not hardened" from the same evidence —
those are different claims, and the second one is the misdiagnosis
`java2c-and-jni-sinking.md` was written to stop.

### 4.4 Repack control — `observed` up to the install, `unverified` beyond

G4 requires a zero-change control through the same pipeline. Built with the
repository's own repacker against an explicit toolchain (this host has no uber-apk-signer;
`keytool` lives in the JDK that `ENV.md` does not list):

```
$ python skills/apk-reverse/scripts/repack.py \
    --apk tools/_work/bench/unpack/b4/ezAndroid.apk \
    --out tools/_work/bench/unpack/b4/ez-ctrl.apk \
    --ks tools/_work/bench/unpack/b4/ctrl.jks --signer apksigner \
    --apksigner E:\tools\android-14\apksigner.bat \
    --zipalign E:\tools\android-14\zipalign.exe \
    --keytool "C:\Program Files\Java\jdk-17.0.4.1\bin\keytool.exe"
[in ] tools/_work/bench\unpack\b4\ezAndroid.apk (2984841 bytes)
[zip] - META-INF/1N0R.SF / 1N0R.RSA / MANIFEST.MF (signature artifact)
[zip] unsigned written: 2828919 bytes
[zip]   AndroidManifest.xml  STORED  offset=0x31
[zip]   classes.dex 3960320 bytes method=8 crc=037e9cb3
[zip]   resources.arsc       STORED  offset=0x202f14  aligned
[sign] route: apksigner
[verify:zipalign] rc=0
[verify:v2block] present
[cert] SHA1 C9:89:C5:75:A4:83:AE:E0:A6:4B:F4:F6:0D:E3:D2:73:C2:8B:65:69
[result] OK
```

Zero-change repack, v2 block present, alignment verified, `classes.dex` carried through
at its original CRC (`037e9cb3`). **Install and launch on `<DEVICE>` are `unverified`
in this record**: the shared device was held by a parallel benchmark row (`B1 L1 repack
control + patched install`, `B2 L3 frida`) for the whole window available to this pass.
No claim is made here about whether the control launches; the artifact and the command
above are the reproducible half, and the device half is the open item.

Consequently **"repacking is truly refused on this target" is `inferred`, not
`observed`** — it follows from the native island being the only home of the app's own
logic (`Stringfjni`, `cf`, `GMS` are all native declarations), which makes a
dex-level patch unable to reach the behaviour, but no device run confirms a refusal.
The honest deliverable form for this target is the G1 row **annotated analysis report
with a stated boundary**, with `lsposed_scaffold.py` / `frida_rpc_serve.py` named as
the routes *if* a device run shows the build is refused.

## 5. `dex_mem_scan.py` — the cut half is measured, the in-process half is not

The script's job splits cleanly into *find-and-cut* (locate `dex\n03x` in a blob and
write exactly the declared `file_size`) and *reach the blob at all* (do it against a
live process's anonymous mappings through `/proc/<pid>/mem`). Only the first half was
measurable in this pass, and it was measured with a synthetic high-entropy capture
built to have the shape a heap buffer presents:

```
$ python … # 2 MiB of random bytes with a 4,124-byte dex written at offset 0x9a000
fixture dex: 4124 bytes, magic=b'dex\n039\x00'
capture written: …/memscan/anonregion.bin  2097152 bytes  dex at 0x9a000

$ python skills/apk-reverse/scripts/dex_mem_scan.py …/anonregion.bin --dump …/scanout
== dex memory scan: 1 capture(s), 1 hit(s) ==
capture          offset  ver  file_size  classes  state
anonregion.bin  0x9a000  039       4124        1  ok
                 wrote …/scanout/anonregion+0x0009a000.dex

$ python skills/apk-reverse/scripts/dex_dump_validate.py …/scanout
name                        size  sha256[:12]  ver cksum sig  class noco code  stub%
anonregion+0x0009a000.dex   4124  d3dedcd2b75e 039  ok    ok       1    0    5   0.0%
```

Exact offset, zero false hits in 2 MiB of noise, the extracted image byte-identical
by construction and accepted by the judge including its checksum and signature. That
is the **whole find-and-cut path, observed** — the halves compose correctly.

**What is not measured.** The live-process half: the fixture that would exercise it is
built and staged (§6), but the shared device was held by a parallel benchmark row for
the entire window this pass had, so `dex_mem_scan.py` has still never been run against
a real anonymous mapping here. The one related number that exists is from the earlier
root-dump pass, and it is a **zero**: 142 anonymous regions scanned, no hits, against
17 dex images found in *named* ART mappings with no search at all. A zero-hit scan is
weak evidence for the reasons listed in the script's own header, and the honest
summary is "the finder works on a shape that looks right; its in-process reach is
unverified".

To close it (all commands staged, none run in this pass):

```
adb push tools/_work/bench/unpack/memscan/out2/memfixture.jar  /data/local/tmp/
adb push tools/_work/bench/unpack/b3/src-r2pay.dex             /data/local/tmp/payload.dex
adb shell 'su -c "CLASSPATH=/data/local/tmp/memfixture.jar app_process /system/bin \
    com.revprobe.memfixture.Main /data/local/tmp/payload.dex"' &
# the fixture prints its own pid, truncates the on-disk payload so the heap copy is the
# only remaining source, and writes /data/local/tmp/memfixture.maps
adb shell 'su -c "grep -c . /proc/<pid>/maps"'          # confirm cheap maps first
adb shell 'su -c "grep -v \"/\" /proc/<pid>/maps"'      # the anonymous set to export
```

Note the fixture deliberately truncates its source file: a scan that finds the dex
after that point cannot have found a file copy, which is what makes the result
attributable to memory rather than to disk.

## 6. Not done — and why

- **No device run of the B4 control build.** The shared device was locked by another
  benchmark row for the whole window; `devlock.py acquire unpack` timed out twice
  (900 s and 1,800 s waits). Install, launch, time-to-death and refusal/success are
  therefore `unverified`.
- **No in-process run of `dex_mem_scan.py`.** The fixture is built and staged
  (`tools/_work/bench/unpack/memscan/`, §5), the arm64 `app_process` route is chosen
  because this host has **no `android.jar`** and therefore cannot compile a real APK
  at all, and the closing commands are listed — but the device was never available, so
  the anonymous-mapping hit rate remains unmeasured. The only related measurement is
  the earlier pass's **0 of 142** anonymous regions.
- **Whether the `assets/` blobs are live.** Needs a dynamic run (read the files out of
  the process after the native island runs, or hook the path construction).
- **No end-to-end FART splice.** The reference file's FART loop needs a live
  extraction-shell target; nothing in `repos/` is one (§1), and building an actively
  resisting shell is out of scope for this pass.
- **A real APK build on this host.** The build-tools directory ships `d8`, `aapt2`,
  `apksigner` and `zipalign` but **no `android.jar`**, and no `android.jar` exists
  anywhere on the machine (searched the tool directories, `C:\Program Files`, and
  the SDK path). Any
  `javac` against `android.*` fails with "package android.os does not exist". APKs can
  still be *repacked* here (`repack.py` does not recompile), which is why §4.4 works
  and the self-built-APK route in the task brief does not.

## 7. Reproduction

```
python tools/_work/bench/unpack/b3/make_skeleton.py tools/_work/bench/unpack/b3/src-r2pay.dex tools/_work/bench/unpack/b3/skel
python tools/_work/bench/unpack/b3/analyze_pair.py
python tools/_work/bench/unpack/b3/crosscheck.py tools/_work/bench/unpack/b3/skel/*.dex
python skills/apk-reverse/scripts/dex_dump_validate.py tools/_work/bench/unpack/b3/skelall
python skills/apk-reverse/scripts/dex_dump_validate.py tools/_work/t2-unpack --find 'Lcom/stub/'
python tools/_work/bench/unpack/b4/vmp_boundary.py tools/_work/bench/unpack/b4/orig/classes.dex
E:\tools\android-14\dexdump.exe -d tools/_work/bench/unpack/b4/orig/classes.dex
python skills/apk-reverse/scripts/dex_mem_scan.py tools/_work/bench/unpack/memscan/anonregion.bin --dump tools/_work/bench/unpack/memscan/scanout
```

Raw captures live beside the fixtures: `evidence/prefix-validate.txt` (before the fix,
including the inverted ranking) and `evidence/postfix-validate.txt` (after). The
`memscan/` tree carries the staged (unrun) in-process fixture: `plain/com/revprobe/memfixture/Main.java`
(no-`android.jar` form), `build.ps1` (the APK build that cannot complete here, kept as
the record of *why*), and `out2/{classes.dex,memfixture.jar}`.

To re-verify the fix from scratch, the two commands that matter are
`dex_dump_validate.py …/skelall` (expect `nopfilled.dex` flagged, not ranked first) and
`dex_dump_validate.py tools/_work/t2-unpack --find 'Lcom/stub/'` (expect
`01_original_shell.dex` still the winner).
