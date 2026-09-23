# rasc and droidsaw — the Rust ASC, and what it changes about the indexer-first workflow

Load this when: you are about to reach for `droidasc` (ASC) to locate classes or references, or when
the Python indexer is the bottleneck on a real archive. It states what the Rust re-implementation is,
how it was measured here, and **the one class shape where it silently loses code** — which is the
part that decides whether you use it alone or keep a second tool next to it.

**When to prefer it, in one line:** `rasc` is the same interface with the same answers, several times
faster, and one measured blind spot; use it as the indexer, keep `droidasc` and JADX as the
cross-checks the rest of this skill already requires.

## What it is

`MG1937/ASC` has two implementations on different branches. `main` is the Python tool this skill
already documents (`pip install droidasc`). The **`rust` branch is `rasc`**, a re-implementation that
keeps the CLI shape and drops the Python runtime:

| | Python `droidasc` main | `rasc` (rust branch) |
|---|---|---|
| Runtime | CPython + androguard | none — one static-ish binary, **2.13 MB** |
| Decompiler behind `getclass` | androguard's | **`droidsaw-dex 2.0.0`** (pure Rust; its project advertises byte-identical DEX re-emission on F-Droid) |
| Install | `pip install droidasc` | **must be built** — no release asset, no crate (`cargo install rasc` fetches an unrelated maths parser) |
| Commands | `listclass` `getmanifest` `getclass` `findrefs` | `classes` `manifest` `getclass` `findrefs` |
| Flags | `--prefix` on `listclass` | `--filter` on `classes` (case-insensitive substring, not a prefix) |
| Shared flags | `--threads/--thread`, `-o/--output`, `--debug` | same, plus `--debug` prints phase timings on stderr |

`scripts/rasc_build.py` wraps the build and the verification, because **a build only one machine has
performed is a build nobody else can reproduce**: `--check` reports what is present, `--build`
clones and compiles, `--verify <apk>` compares the class-definition sets against `droidasc` and fails
if they differ.

## Measured here

Environment: Windows 11, rustup `stable-x86_64-pc-windows-gnu` (rustc 1.98.1), MinGW-w64 gcc 16.1.0
(UCRT, 64-bit) as the linker. Build from a clean checkout: **117 s**, `cargo build --release` with
FatLTO. Binary `rasc` 0.1.0, 2,236,416 bytes, sha256 `1becdb86b444fe7910589f8ade5bccf13794de9f2b466a1c07748b5669c0264b`,
from `MG1937/ASC@e809c7b4b454ebc8eb4467f56d44a82e6139472b` (rust branch).

Two archives, fastest of N runs, same machine, `PYTHONUTF8=1` for the Python side:

| Archive | Scenario | rasc | droidasc | ratio | answers |
|---|---|---|---|---|---|
| MASTG `UnCrackable-Level3.apk` (1.4 MB) | `classes` | 0.025 s | 0.116 s | 4.7× | **identical set** (1396 / 1396) |
| | `findrefs string http` | 0.021 s | 0.299 s | 14.0× | identical (3 / 3) |
| | `findrefs type String` | 0.021 s | 0.307 s | 14.7× | rasc superset (390 vs 384) |
| | `getclass` ×2 real classes | 0.086 / 0.082 s | 0.297 / 0.267 s | 3.3–3.5× | both emitted Java |
| a real 34.8 MB app (30,768 classes) | `classes` | 0.048 s | 0.190 s | **4.0×** | **identical set**, 0 differences both ways |

The speedup is smaller than the upstream README's geometric mean of 8.0× because that figure was
measured on a 343 MiB archive with 567k classes, where startup cost disappears; on a mid-size app the
Python runtime's import time keeps the ratio near 4×. Both are real, and the small-archive numbers are
the ones a normal task hits.

`python skills/apk-reverse/scripts/rasc_build.py --verify <apk>` reproduces the class-set comparison
and is the check to run after any rebuild.

## The blind spot: `getclass` on the outer enum does not inline the constant bodies

`bench/jadx_parity.py` from the `rasc` repository compares **string literals** between JADX and `rasc`
per class, counting a literal JADX has and `rasc` does not as a lost-code signal. Run here on a fair
sample — app-like classes, no obfuscated identifiers, since the harness itself refuses to judge a
class JADX cannot decompile — **20 classes picked, 17 judged, 1 with a difference, 0 reorderings**.

The one difference is `org.bouncycastle.crypto.PasswordConverter`, an enum whose constants each
override an abstract method. JADX inlines each constant's anonymous subclass; `rasc` prints the
constant list:

```java
// JADX
public enum PasswordConverter implements CharToByteConverter {
    ASCII { // from class: ...PasswordConverter.1
        @Override public byte[] convert(char[] cArr) { ... }
        @Override public String getType() { return "ASCII"; }
    },
    ...
```

```java
// rasc -- getclass on the OUTER class
public enum PasswordConverter implements org.bouncycastle.crypto.CharToByteConverter {
    ASCII, UTF8, PKCS12;
    public PasswordConverter() { }
    public PasswordConverter(PasswordConverter$1 v3) { }
}
```

**What is actually lost, measured directly on the constants.** The bodies live in their own classes,
so the question is whether they survive as their own classes. They do:

| class | `rasc getclass` | `droidasc getclass` |
|---|---|---|
| `PasswordConverter$1` | 404 B, contains `convert(`/`getType(` | 460 B, contains both |
| `PasswordConverter$2` | 407 B, contains both | 463 B, contains both |
| `PasswordConverter$3` | 406 B, contains both | 462 B, contains both |

So the correct severity is **a missing inlining step in the outer-class view, not unrecoverable code**:
the source is one `getclass` away, on the anonymous subclass JADX names in its own comment
(`// from class: ...PasswordConverter.1`). This reference said "the method bodies are gone" when this
row was first written, and that was wrong — the subclasses were never queried. The two Python-visible
symptoms are the same in both tools (neither inlines), so the difference here is JADX's convenience,
not a `rasc` regression against the Python implementation.

`droidasc`'s outer output is nevertheless richer than `rasc`'s for the same class — 2,170 B against
314 B, carrying the synthetic `$VALUES`, `$values()` and the constructors explicitly — which matters
when the enum's *shape* is the thing you are reading.

The rule, now proportional to what was measured:

- **Use `rasc getclass` for locating and reading ordinary classes.** That is what it was measured on.
- **When the class is an `enum` with constant-specific bodies, read the constants.** A collapsed enum
  is visible on sight (bare constant list, no bodies). Either query the anonymous subclasses directly
  (`Lpkg/Enum$1;`) or use `droidasc`, whose outer-class listing is more complete.
- **Never treat a single decompiler's output as the definition of what exists.** The same rule the VMP
  section states about opcode tables, applied to a class body.

Frequency for calibration: 1 of 17 judged classes here, and the other 16 agreed literal for literal.
Adopt it, and keep the cross-check — but do not describe this as lost code.

## What it does not change

- **The workflow.** The indexer is the same *stage* it always was: `rasc` answers *location*
  questions, and reading a class you have already located is what a decompiler is for. It does not
  decompile a whole APK into a project, and neither does the Python tool.
- **The verification discipline.** Every claim above is a measurement with a command behind it;
  where `rasc` and `droidasc` disagree in the tables, the disagreement is recorded rather than
  averaged away.
- **Packer behaviour.** On this repository's hardened sample both tools correctly return 4 classes —
  the payload is encrypted inside the shell and is not in any DEX either tool can read. A small class
  count on a hardened target is the target, not the tool.

## Building it yourself

```bash
python skills/apk-reverse/scripts/rasc_build.py --check          # what is present
python skills/apk-reverse/scripts/rasc_build.py --build          # clone + cargo build --release
python skills/apk-reverse/scripts/rasc_build.py --verify app.apk # compare against droidasc
```

Requirements and the traps measured here:

- **Rust 1.93+** (the crate is `edition = "2024"`; this build used 1.98.1) and `git`.
- On Windows, the **GNU host toolchain needs a 64-bit MinGW-w64 gcc**. A 32-bit MinGW fails at link
  with `sorry, unimplemented: 64-bit mode not compiled in` — the fix is a 64-bit distribution (this
  build used winlibs gcc 16.1.0), not a flag.
- The build fetches crates from crates.io; `vendor/` in the repository only carries the two patched
  crates (`axmldecoder`, `droidsaw-dex`), so `--offline` fails with `no matching package named anyhow`.
- `cargo`/`rustc` installed to a non-default `CARGO_HOME` are invisible to a non-interactive PATH;
  `rasc_build.py` prepends the known locations rather than reporting the toolchain as absent.

## Provenance

`https://github.com/MG1937/ASC` (branch `rust`, commit `e809c7b`), retrieved 2026-09-22.
`https://github.com/droidsaw/droidsaw` and `https://crates.io/crates/droidsaw-dex` (2.0.0),
consulted 2026-09-22. The Python implementation is `pip install droidasc` (0.1.1.post1 seen here;
0.1.1.post2 published 2026-09-21). Nothing from either project is vendored into this repository —
`rasc_build.py` clones it into the gitignored `tools/_work/` and the measurements above name the
commit they came from.
