# EXTENSION — rasc (the Rust ASC) measured against the Python one

Evidence for `skills/apk-reverse/references/rasc-and-droidsaw.md`. Every number below has the command
that produced it.

## What was measured

| Claim | Grade | Result |
|---|---|---|
| `rasc` builds from the `rust` branch on this host with no prebuilt artifact | **observed** | rustc 1.98.1 (gnu host) + MinGW-w64 gcc 16.1.0; `cargo build --release` **117 s**; binary 2,236,416 B |
| It is faster than the Python `droidasc` on the same archives | **observed** | 4.0–5.6× for `classes`, up to 16.2× for `findrefs` (tables below) |
| It returns the same answers | **observed** | **identical class-definition sets**, 30,768 / 30,768 with **0 differences in either direction**; `findrefs string` identical on one sample, `type` a superset (390 vs 384) |
| Its `getclass` decompiles ordinary classes correctly | **observed** | 16 of 17 JADX-judged classes matched literal-for-literal, 0 reorderings |
| **Its outer-class view of an enum does not inline the constant bodies, and says nothing** | **observed — and the first write-up of this row over-claimed; see §The blind spot** | JADX inlines the three anonymous subclasses; `rasc` prints a bare constant list. Both tools decompile `PasswordConverter$1/2/3` **fully** (404–407 B, containing `convert`/`getType`), so what is missing is an inlining step, not the code |
| Its own benchmark's 8.0× geometric mean reproduces here | **not reproduced, and explained** | that figure is from a 343 MiB / 567k-class archive; on a 34.8 MB / 30,768-class app the ratio is 4×. Both are real; the small-archive figure is what a normal task hits |

## Environment

Host Windows 11. Device not involved. Toolchain installed for this pass, into the gitignored
`tools/_work/`:

```
rustup-init (x86_64-pc-windows-gnu)  -> rustc 1.98.1, cargo 1.98.1
winget install BrechtSanders.WinLibs.POSIX.UCRT -> gcc 16.1.0 (x86_64-w64-mingw32, UCRT)
```

The 32-bit MinGW already on this host (`C:\MinGW`, gcc 6.3.0, target `mingw32`) **cannot** link a
64-bit binary — `gcc -m64` reports `sorry, unimplemented: 64-bit mode not compiled in`, and the Rust
GNU target needs a 64-bit linker. E:\vs2022 has no VC tools (`cl.exe` / `link.exe` absent), and the
WSL2 Ubuntu distribution is registered but `HCS_E_SERVICE_NOT_AVAILABLE`, so no Linux path either.

```
$ python skills/apk-reverse/scripts/rasc_build.py --check
toolchain : git=E:\Git\cmd\git.EXE cargo=...\rust\cargo\bin\cargo.EXE rustc=...\cargo\bin\rustc.EXE gcc=C:\MinGW\bin\gcc.EXE(mingw32)
rasc      : E:\apk-reverse\tools\_work\rust\target\release\rasc.exe  rasc 0.1.0
result    : ok
```

## Speed and agreement

Fastest of 3 runs (1 run on the largest), same machine, `PYTHONUTF8=1` for the Python side.

```
$ python tools/_work/compare_asc.py tools/_work/bench/apks/UnCrackable-Level3.apk --repeat 3
scenario               rasc s       py s  speedup   result agreement
classes                 0.025      0.138      5.6   equal            rasc=1396 py=1396
manifest                0.017          -        -   not comparable
findrefs string         0.022      0.341     15.6   overlap 100%     rasc=3 py=3
findrefs type           0.022      0.358     16.2   overlap 98%      rasc=390 py=384
```

Rounded to whole numbers in the reference file (4.7–14.7× there vs 5.6–16.2× here) because these are
two independent runs of the same measurement; both are in the observed range, and the run-to-run
spread on a sub-100 ms command is the honest resolution.

On a real 34.8 MB application (`MT-Manager.apk`, 30,768 classes):

```
$ python -c "... rasc classes vs droidasc listclass, set comparison ..."
rasc     : 0.048 s  30768 classes
droidasc : 0.190 s  30768 classes
speedup  : 4.0x
identical set : True
only in rasc  : 0   only in droidasc: 0
```

`python skills/apk-reverse/scripts/rasc_build.py --verify tools/_phone-modules/MT-Manager.apk` runs
the same comparison and reports `{'result': 'ok', 'rasc_classes': 30768, 'droidasc_classes': 30768,
'only_rasc': 0, 'only_droidasc': 0}`, so the check travels with the kit rather than living in a note.

**A defect found on the Python side during this work:** `droidasc listclass` exits 1 with
`'gbk' codec can't encode character` on an app whose classes contain non-Latin identifiers, when the
console encoding is not UTF-8. With `PYTHONUTF8=1` it completes. `rasc` was unaffected. That is a
one-variable difference in the environment, not a property of either tool, and it is recorded because
it cost a round here.

## The blind spot, verified rather than reported

The `rasc` repository ships `bench/jadx_parity.py`, which treats a string literal JADX has and `rasc`
does not as lost code, and refuses to judge a class JADX itself could not decompile cleanly. Its own
class sampling takes every-nth entry from `rasc classes`, which on a real app lands mostly on
obfuscated names where JADX produces nothing — 8 of 10 picked that way were unjudgeable here, so the
sample measures the sampler. `tools/_work/parity_fair_sample.py` filters to app-like classes first
(ASCII, dotted, no inner class, not `R`/`BuildConfig`) and feeds those to the unmodified harness:

```
$ python tools/_work/parity_fair_sample.py tools/_phone-modules/MT-Manager.apk 20
classes in APK: 30768
app-like candidates: ...
judged 17 class(es) where JADX was clean; literals rasc lost: 1; reorderings: 0
```

The one finding, checked by hand with `tools/_work/verify_parity_finding.py`:

```
class        : org.bouncycastle.crypto.PasswordConverter
jadx literals: ['ASCII', 'PKCS12', 'UTF8']
rasc literals: []
missing      : ['ASCII', 'PKCS12', 'UTF8']
  'ASCII'      appears in rasc output as an identifier: True
  ...
VERDICT: form difference (enum constants printed as a list, literals not re-emitted)
```

**The automated verdict understates it, and the hand check then overstated it. Both corrections are
kept.** The harness counts literals, and the literals in JADX's output belong to the anonymous
subclasses it inlines; `rasc`'s outer-class view prints a bare constant list. The first write-up here
said "the method bodies are gone". **That was wrong, and the way it was wrong is worth recording: the
subclasses were never queried.** They exist as their own classes and both tools decompile them fully:

```
$ rasc getclass    <apk> 'Lorg/bouncycastle/crypto/PasswordConverter$1;'   -> 404 B, has convert(/getType(
$ droidasc getclass <apk> 'Lorg/bouncycastle/crypto/PasswordConverter$1;'   -> 460 B, has both
$ ... $2 and $3 the same shape, 406-407 B vs 462-463 B
```

So the accurate finding is narrower than the first version and narrower than the harness's phrasing:
**`rasc` does not inline enum-constant bodies into the outer class view, and it does not say so** —
the bodies are one `getclass` away, on the subclass JADX itself names in a comment
(`// from class: ...PasswordConverter.1`). Neither does the Python tool inline; `droidasc`'s outer
listing is just richer (2,170 B vs 314 B, with `$VALUES`, `$values()` and the constructors explicit).

The general lesson this left behind, and the reason the episode stays in the record: a harness that
counts one artefact (literals) can point at a real difference while misdescribing it, and a hand
check that stops at the first comparison can convert that into an overstated claim. The corrective was
to query the classes the tool we were comparing against had named — which cost one command.

## Not established

- **No whole-APK parity run.** The comparison is on class sets, sampled `getclass` output and one
  `findrefs` family per sample. `bench/corpus_parity.py` and `bench/jadx_parity.py` exist for a fuller
  run and were used on one archive, not on a corpus.
- **`findrefs` on a large corpus was not run to completion.** On the 34.8 MB app, `findrefs string
  http` returned 0 rows on both sides — a query with no hits is not a parity result, and a query that
  does hit was only compared on the small archive.
- **`getclass` was judged on 17 classes of one app.** The enum blind spot is confirmed; whether other
  class shapes (inner classes, synthetic bridges, `invokedynamic`) diverge the same way is untested.
- **No device or Android-side use.** `rasc` reads archives on the host; nothing here exercises it as a
  device tool, and the reference file makes no claim about that.
- **The 8.0× upstream figure was not reproduced**, because the archive it was measured on (343 MiB,
  567k classes) is not available here. The direction and the smaller ratio were measured.
