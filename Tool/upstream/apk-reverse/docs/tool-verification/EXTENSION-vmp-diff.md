# Extension verification — differential hardening for Dex-VMP

Covers the extension pass that added `references/vmp-differential-analysis.md` and
`scripts/vmp_diff_harness.py`. Strength labels as defined in this directory's README:
**observed** (exact command + output here), **inferred** (follows from observed facts,
step not executed), **unverified** (assumed or externally reported, not independently
confirmed).

Reference environment: Windows 11 host, Python 3.14.0, JDK 17.0.4.1
(`C:\Program Files\Java\jdk-17.0.4.1\bin\javac.exe`), Android build-tools 2.19 / D8
8.2.2-dev off-PATH. **No device and no network were involved in this pass** — unlike the
unpacking and rootdump passes, this one is deliberately machine-local, because the thing
worth measuring here is the comparison logic, not the platform.

**Headline: the local half of the route is measured and closes exactly; the
platform half was not exercised at all, and the cost table says why it cannot be.**

---

## 1. Environment discovery — observed, and one correction to `tools/_work/ENV.md`

`ENV.md` records `E:\tools\android-14\` as a complete build-tools directory. At pass time
it held **three** entries:

```
$ Get-ChildItem 'E:\tools\android-14\' -Name
apksigner.bat
lib
zipalign.exe
```

`aapt2.exe`, `d8.bat` and `dexdump.exe` were absent, so the `build` subcommand had no
toolchain. The complete build-tools tree was sitting unextracted in `E:\tools\bt.zip`:

```
$ (bt.zip entries) | Where-Object { $_.Name -match '^(aapt2|d8|dexdump|split-select)' }
android-14/aapt2.exe         4566296
android-14/d8.bat               3156
android-14/dexdump.exe        986392
android-14/split-select.exe  1589016
android-14/lib/d8.jar       14929869
```

After `Expand-Archive -Path 'E:\tools\bt.zip' -DestinationPath 'E:\tools\' -Force`:

```
$ E:\tools\android-14\aapt2.exe version
Android Asset Packaging Tool (aapt) 2.19-10229193

$ E:\tools\android-14\d8.bat --version
D8 8.2.2-dev (build facedf41bbd28b563d1e9e09c5f72d7c5ca598d8 from go/r8bot (luci-r8-custom-ci-focal-14-zjz7))
```

Two further tool facts worth recording, both **observed**:

- **The apktool jar the wrapper points at does not exist**, so `<tools>\bin\apktool.bat` (which is
  `java -jar "<tools>\agb_apktool.jar" %*`) resolves to nothing. apktool is unavailable on this
  machine, and a bare `apktool d` fails with a jar-not-found error rather than a
  recognisable "tool missing" message.
- `javac` is on PATH only through the Oracle `javapath` forwarder; the real JDK is at
  `C:\Program Files\Java\jdk-17.0.4.1`. The harness takes `--javac` explicitly for this
  reason.

## 2. `build` — observed

```
$ python skills/apk-reverse/scripts/vmp_diff_harness.py build \
    --build-tools E:\tools\android-14 --out tools/_work/t5-vmp/fixture \
    --javac "C:\Program Files\Java\jdk-17.0.4.1\bin\javac.exe" --apk
javac:      C:\Program Files\Java\jdk-17.0.4.1\bin\javac.exe
d8:         E:\tools\android-14\d8.bat
aapt2:      E:\tools\android-14\aapt2.exe
generated:  ...\src\OpCoverBig.java (37196 B)

$ ... javac -g --release 11 -d ...\classes ...\OpCoverProbe.java ...\OpCoverBig.java
javac ok:   9 class files

$ E:\tools\android-14\d8.bat --min-api 26 --no-desugaring --output ...\dex <9 .class paths>
d8 ok:      ...\dex\classes.dex (35028 B)
== ...\classes.dex (35028 bytes) ==
  classes=9 methods_with_code=75 instructions=3065 desynced=0
  opcode coverage: 218/224 (97.3%)
  not emitted by this fixture (6):
    0x09 move-object/16      move-object/16 (32x) needs both registers >= 256; the object
                             frame reaches 256 on the source side only, which d8 encodes as 0x08
    0x1b const-string/jumbo  needs a string_ids index > 65535, i.e. a fixture carrying
                             65536+ string constants
    0x2a goto/32             needs a >32767-code-unit backward jump; javac refuses the method
                             first with 'code too large' (its own 64 KB per-method bytecode cap)
    0xfd invoke-custom/range  d8 emitted the 35c form for every lambda shape tried, including
                             a six-parameter one
    0xfe const-method-handle no Java-language literal; reachable only by hand-written smali
                             or direct dex construction
    0xff const-method-type   same as 0xFE

$ E:\tools\android-14\aapt2.exe link --manifest ...\apk\AndroidManifest.xml -o ...\apk\base.apk
aapt2 ok:   ...\probe.apk (20482 B, unsigned)
build rc=0
```

Structural facts behind those numbers: **0 desynced methods** (every `decode_all` walk
ended exactly on `insns_off + insns_size*2`, i.e. the format table and the emitted stream
agree), 3,065 instructions across 75 method bodies, 9 classes.

### 2a. The two toolchain traps this measured — observed

Both are encoded in the script so they are not re-derived:

- **`d8` refuses a non-existent `--output` directory.** First run:
  `Error: Invalid output: ...\dex / Output must be a .zip or .jar archive or an existing
  directory / Compilation failed` and rc=1. Same class of trap as `frida-dexdump -o`.
  `build` creates the directory first.
- **`aapt2 link` needs `android.jar` for every `android:` attribute.** A manifest carrying
  `android:versionCode` / `android:versionName` / `android:minSdkVersion` produced five
  `error: attribute android:... not found` lines and rc=1. A manifest using only the
  un-namespaced `package` attribute links cleanly with no `-I` flag at all — which is what
  the harness ships, at the cost of an APK with no version attributes. That is acceptable
  for a dex carrier and is stated in the output.

### 2b. `goto/32` is unreachable from Java — observed

Driving the generator to 33,000 loop-body statements to push the backward jump past the
20t range:

```
$ python tools/_work/t5-vmp/gen_big_probe.py 33000
generated ...\OpCoverBig.java: 34442 lines, 766468 bytes
javac rc=1
OpCoverBig.java:1427: error: code too large
    public static int gotoFar(int x) {
1 error
```

The JVM's own 64 KB per-method bytecode limit fires before the dex branch-distance
threshold can be crossed. `goto/32` therefore cannot be covered by any javac-built
fixture, at any generator size — this is a structural ceiling, not a tuning problem.

## 3. Closed loop — observed, and this is the load-bearing result

`simulate` relabels every opcode through a bijection whose ground truth it writes to disk.
`compare` is then given only the two dex files and must re-derive that table.

```
$ python .../vmp_diff_harness.py simulate .../fixture/dex/classes.dex \
      --out tools/_work/t5-vmp/sim.dex --seed 7 --table tools/_work/t5-vmp/truth.json
simulated:   ...classes.dex -> ...sim.dex
             mode=relabel, 3065 method body(ies)/instruction(s) touched (seed 7)
             header recomputed: checksum_ok=True signature_ok=True
             ground-truth table written to ...truth.json (compare must re-derive it)

$ python .../vmp_diff_harness.py compare .../fixture/dex/classes.dex tools/_work/t5-vmp/sim.dex
   aligned=75 resized=0 stripped=0 missing=0 added=0
   aligned slots compared: 3065
   verdict: USABLE
   (map: 218 rows, every one verdict=high)
compare rc=0
```

Scoring the derivation against the ground truth:

```
ground-truth bijection size     : 256
opcodes the fixture emits       : 218
compare rows                    : 218
compare high-confidence rows    : 218
compare undetermined            : 6
compare non-injective           : 0
compare run verdict             : usable

derived entries that are WRONG  : 0 (none)
derived entries with no truth   : 0 []
emitted opcodes NOT derived     : 0 []

EXACT RECOVERY: 218/218 emitted opcodes (100.0%)
CLOSED-LOOP VERDICT: IDENTICAL
```

Why the denominator is 218 and not 256: the ground-truth bijection covers all 256 byte
values, but 32 of those are unallocated dex slots and 6 are opcodes this fixture never
emits — and an opcode that never appears leaves no known plaintext. The six are reported
as `undetermined` with their reasons, never guessed. **Every entry the run did produce was
correct, and every opcode that could be read was read.**

## 4. Negative shapes — observed

The decision table's failure branches were driven on purpose, because a detector that has
never been seen to fire is not a detector.

**Stub shape** (`--mode stub`: every body replaced by an equal-length `return-void` fill —
the extraction shape):

```
$ python .../vmp_diff_harness.py compare .../classes.dex tools/_work/t5-vmp/stub.dex --quiet
   aligned=75 resized=0 stripped=0 missing=0 added=0
   aligned slots compared: 3065
   verdict: NOT-USABLE
     ! 1 private byte(s) are claimed by up to 218 original opcodes each. No injective
       relabelling can do that: it is the signature of method bodies replaced by one
       common stub, and any substitution read off such a pair describes the stub, not a
       private opcode space.
rc=1
```

This is the failure mode worth reading twice. In the per-opcode direction the reading is
**perfect** — 218 rows, all `high`, zero conflicts — because every original opcode maps to
the same private byte. Only the reverse (`private byte → set of originals`) check exposes
it. An implementation without that check would have returned a confident, wholly
meaningless table, and the first version of this one did exactly that: measured before the
fix, the same input returned `verdict: PARTIALLY-USABLE` alongside a note reading
"0 of 218 opcodes saw more than one candidate byte" — a warning that contradicted itself.

**Length-changing shape** (`--mode shrink`: `insns_size` rewritten without moving bytes, a
deliberately inconsistent image that exists only to drive the detector):

```
$ python .../vmp_diff_harness.py compare .../classes.dex tools/_work/t5-vmp/shrink.dex --quiet
   aligned=0 resized=75 stripped=0 missing=0 added=0
   aligned slots compared: 0
   verdict: NOT-APPLICABLE
     ! 75 method(s) kept a body but changed its length. Boundaries cannot be projected
       across a length change; a private opcode stream with its own length table is not
       reachable this way.
rc=1
```

Regression after both fixes: the relabel loop still reports `USABLE` and the closed-loop
check still reports `IDENTICAL` — recorded above, re-run after the verdict-logic change.

**Not driven:** the `stripped` shape (`code_off == 0`) needs a class-data rewrite rather
than a byte edit, so its detector path is **inferred** from the shape counters, not
observed firing. The counters themselves (`stripped=0` in every run above) are observed.

## 5. `emit-smali` — observed

```
$ python .../vmp_diff_harness.py emit-smali tools/_work/t5-vmp/sim.dex \
      --table tools/_work/t5-vmp/cmp.json --class LOpCoverProbe --method arithInt
; instructions restored: 3065 ; unmapped-opcode stops: 0
; THIS IS A READING SKELETON, NOT ASSEMBLABLE SMALI.
...
.class public LOpCoverProbe;
.super Ljava/lang/Object;
.source "OpCoverProbe.java"

# ---- arithInt(II)I  registers=4 insns_size=29
.method public static arithInt(II)I
    .registers 4
    # 0x0000  90000203       add-int
    # 0x0004  d000e803       add-int/lit16
    # 0x0008  d8000007       add-int/lit8
    # 0x000c  b130           sub-int/2addr
    ...
    # 0x0038  0f00           return
.end method
```

Two checks that the restore is real rather than plausible: the stream decodes to the
**original fixture's** `arithInt` body (compare it against `OpCoverProbe.java`'s 17
operations), and the payload-bearing `switchPacked` method also restores cleanly —
`packed-switch` followed by its payload block, stepped over by its own layout rather than
mistaken for opcodes. `unmapped-opcode stops: 0` is the honest coverage measure, and it is
zero only because the table is complete for this fixture.

Three defects were found and fixed by this run, each one a silent-wrong-answer shape:

- `--class LOpCoverProbe;` matched **zero** classes because the filter accepted only one of
  the three spellings (`LOpCoverProbe;` / `LOpCoverProbe` / `OpCoverProbe`) — output read
  exactly like a class that is not in the file.
- `.source` printed `"<string_idx 34748 out of range>"`: `source_file_idx` sits at
  `class_def_item + 16`, not `+ 20` (that is `annotations_off`).
- Methods rendered without access flags, so the skeleton was not readable as smali.

## 6. What was not done

- **No hardening platform was contacted.** The entire submission link of the chain is
  `unverified`, and its cost estimate in the reference file is reasoning about how those
  services are distributed (accounts, rate limits, download-page delivery, possible refusal
  of a synthetic fixture), not a measured upload. This is the pass's largest gap and it is
  not closeable from this machine.
- **No real VMP sample was used.** `tools/_work/bench/repos/DexPatcher/assets/ezAndroid.apk`
  is recorded in `ENV.md` as a real Dex-VMP challenge sample and was **not** opened in this
  pass; the differential route needs a *matching hardened counterpart of the same build*,
  which no available artifact provides.
- **The engine-behaviour assumption is inferred**: that a real VMP substitutes per-opcode
  at stable instruction length. `simulate` implements the weakest form of that assumption
  deliberately — it is the only form this harness can check itself against.
- **Table stability across inputs is unverified.** Whether one fixture's table applies to
  another build of the same app, or survives a vendor version change, was not tested and is
  the reason the reference file says to re-derive per target.
- **The `stripped` detector path did not fire** (see §4).
- `--mode shrink` writes a structurally inconsistent dex by design; `dexutil.Dex.check()`
  will not reject it because it does not range-check `insns` against the file. It is a
  detector probe, is labelled as such in `--help`, and must not be treated as a build.
