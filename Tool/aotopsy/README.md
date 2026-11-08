# AOTopsy

[![CI](https://github.com/BroNils/aotopsy/actions/workflows/ci.yml/badge.svg)](https://github.com/BroNils/aotopsy/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/BroNils/aotopsy?sort=semver)](https://github.com/BroNils/aotopsy/releases)
[![License](https://img.shields.io/badge/license-BSD--3--Clause-blue.svg)](LICENSE)

A Dart AOT snapshot analyzer. Turns `libapp.so` — the compiled Dart code inside a Flutter release APK — into function names, class layouts, call graphs, behavioral signals, and readable pseudocode. No Dart VM, no SDK compilation, no runtime fallback.

> **Fork notice:** AOTopsy is a fork of **unflutter**, originally by **Anthony Zboralski**. The original `zboralski/unflutter` repository is no longer available (removed by the author); a community continuation exists at [`KristijanZic/unflutter`](https://github.com/KristijanZic/unflutter). All credit for the original snapshot parser, cluster deserializer, ARM64 disassembly pipeline, and Ghidra/IDA integration belongs to the original author. AOTopsy extends it with x86_64 support, a native decompiler, whole-program type inference, Frida script generation, and comprehensive documentation.

## What It Recovers

| Output | What it is |
|--------|-----------|
| Function names | The original Dart name for each compiled function |
| Class structures | Field names, byte offsets, inheritance chains |
| Call graph | Direct (BL) and indirect (BLR/dispatch) call edges with provenance |
| String references | Which functions load which string literals from the object pool |
| Behavioral signals | Crypto, network, gambling, SIM, location, WebView, blockchain keyword classification |
| Pseudocode | Architecture-neutral decompiled output from ARM64 or x86_64 machine code |
| Dart Source Export | Whole-project modular `.dart` files reconstructed with classes, fields, and methods |

Supports **ARM64** and **x86_64**. Covers **Dart 2.10 through 3.13** (3.13.2 is the current stable frontier) — every modeled version parses cleanly on both architectures, see [COVERAGE.md](COVERAGE.md) (93 sample builds, 0 failures).

## Accuracy & Honesty

AOTopsy is measured against ground truth, not asserted. Two properties are enforced by
the test suite on every change:

| Metric | Value | What it means |
|--------|-------|---------------|
| **Name-recovery agreement** | **90.2%** overall (81.3% worst band, ≥ 0.81 gate floor) across 44 ground-truth builds | Recovered function names compared against each build's own ELF `.symtab`, the external ground truth — `TestSymtabDifferential`. Full per-build scoreboard: [BENCHMARK.md](BENCHMARK.md) (`make bench`). |
| **Decompiler syntax validity** | **100%** valid Dart | Every emitted pseudocode function parses as Dart — `TestDecompileQualityCorpus`. |
| **Fabrication rate** | **0%** | The §2 rule: never emit a guessed name, type, or call target as fact. Unknowns render honestly (`indirectCall`, `<unknown>`, `dynamic`). |

The ground-truth twins are real production builds we cannot redistribute, so those
differential gates run **locally**; public CI validates build, vet, `gofmt`,
`staticcheck`, unit tests (shuffled) and a coverage floor across the platform
matrix. `samples/` is not redistributable and is gitignored, so sample-dependent
tests skip there — but only when the corpus is absent entirely; a corpus that is
present and missing a registered sample fails, because those mean opposite
things. How every number here is measured (ground truth, metric definitions, reproduction): [METHODOLOGY.md](METHODOLOGY.md). See
[SECURITY.md](SECURITY.md) for release-binary verification and the honest scope below.

## Quick Start

```bash
make build
./aotopsy libapp.so                    # full pipeline
./aotopsy doctor libapp.so             # quick diagnostic
./aotopsy export-dart --lib libapp.so --out ./lib  # reconstruct entire Dart source project
./aotopsy _debug decompile-native --lib libapp.so --find MyClass  # find and decompile a function
```

See [DEMO.md](DEMO.md) for a five-minute walkthrough on a real snapshot, or `WORKFLOW.md` for the step-by-step methodology when you have a raw APK and don't know where to start.

## How It Works

AOTopsy treats the Dart AOT snapshot as a deterministic binary grammar. Every byte has exactly one correct interpretation given the right constraints (ELF structure, snapshot magic, version hash, CID table, cluster encoding). The parser applies constraints until only one interpretation survives — no heuristics, no guessing.

The pipeline runs in stages, each a pure function from bytes to structured data:

```mermaid
flowchart TD
    A[libapp.so] --> B[ELF parse]
    B --> C[snapshot region extraction]
    C --> D[version detection]
    D --> E[cluster alloc<br/>object census]
    E --> F[cluster fill<br/>field values, names, strings]
    F --> G[instructions table<br/>code ranges, stub boundaries]
    G --> H{architecture?}
    H -->|ARM64| I[ARM64 disassembly]
    H -->|x86_64| J[x86_64 disassembly]
    I --> K[CFG + call edges<br/>register provenance]
    J --> K
    K --> L[type inference<br/>BLR receiver type resolution]
    L --> M[signal classification<br/>behavioral keyword matching]
    M --> N[JSONL + HTML + DOT<br/>pseudocode output]
```

Two independent backends share the same front half (ELF through cluster fill), then split by architecture: `internal/disasm` for ARM64, `internal/disasm/x86.go` for x86_64. The decompiler (`internal/decompiler`) handles both architectures through a unified IR.

```mermaid
flowchart LR
    subgraph "Shared front half"
        A[elfx] --> B[snapshot]
        B --> C[cluster]
    end
    subgraph "ARM64 backend"
        C --> D1[disasm ARM64]
        D1 --> E1[callgraph]
        E1 --> F1[signal]
    end
    subgraph "x86_64 backend"
        C --> D2[disasm x86_64]
        D2 --> E2[callgraph]
        E2 --> F2[signal]
    end
    subgraph "Decompiler (both archs)"
        C --> G[decompiler IR]
        G --> H[pseudocode]
    end
```

## Comparison With Blutter

```mermaid
flowchart LR
    subgraph Blutter
        direction TB
        B1[libapp.so] --> B2[Compile matching<br/>Dart SDK]
        B2 --> B3[Embed Dart VM]
        B3 --> B4[Deserialize via<br/>VM internal APIs]
        B4 --> B5[Perfect fidelity]
    end
    subgraph AOTopsy
        direction TB
        A1[libapp.so] --> A2[Parse binary format<br/>directly]
        A2 --> A3[No VM, no SDK]
        A3 --> A4[Version-specific<br/>format modeling]
        A4 --> A5[Portability + speed]
    end
```

[Blutter](https://github.com/worawit/blutter) embeds the Dart VM to deserialize the snapshot through its own code paths. Perfect fidelity, but requires compiling a matching Dart SDK for every target version — and it is ARM64-only, with no static x86_64 support. AOTopsy is the only static, version-independent analyzer with a native pseudocode decompiler and published ground-truth accuracy.

AOTopsy parses the binary format directly. No VM, no SDK. The tradeoff: every format change across Dart versions must be modeled explicitly. There is no runtime to handle it automatically.

## Commands

### Full pipeline

```bash
aotopsy libapp.so              # disasm + call edges + signal + metadata (ARM64: + Ghidra/IDA)
aotopsy signal libapp.so       # same, skip metadata
aotopsy libapp.so --graph      # also build call graph DOT files
```

Flags: `--out <dir>` (default: `<basename>.aotopsy/`), `--quiet`, `--strict`, `--max-steps <n>`, `--k <n>` (signal context depth, default 2), `--decompile`.

`--decompile` writes per-function Dart pseudocode to `<out>/dart/`. It is off by
default because it roughly triples the output directory; every run without it
says so, so the capability is discoverable rather than merely present.

### Diagnostic

```bash
aotopsy doctor libapp.so       # Dart version, pointer size, support status, build features
aotopsy find-libapp --apk app.apk  # locate libapp.so inside an APK
```

### Whole-Project Dart Source Export

Reconstructs all classes, fields, methods, getters, setters, and constructors into modular `.dart` files mapped by original library URIs:

```bash
aotopsy export-dart --lib libapp.so --out ./reconstructed_lib/   # full project export
aotopsy export-dart --lib libapp.so --out ./lib/ --app-only      # filter out core/flutter framework
aotopsy export-dart --lib libapp.so --out ./lib/ --filter Auth   # targeted export by name
```

### High-Level Native Decompiler (ARM64 + x86_64)

Produces clean, idiomatic Dart code directly from binary machine instructions:
- **Structural Control Flow**: `for-in` iterators, `while`, `for`, `try-catch-finally` with exact PC bounding.
- **Async/Await Linearization**: Unwraps `_SuspendState` state machines into linear `await future` and `await for`.
- **Lambda Inlining**: Synthesizes arrow callbacks `(item) => process(item)` directly at call sites.
- **Type Lattice**: Propagates concrete Dart types (`String`, `int`, `UserModel`) across SSA values without running a live VM.
- **Dart Idioms**: Null-aware (`?.`, `??`, `??=`), cascade (`..`), Set/List/Map literals, string interpolation (`"${a}${b}"`).

```bash
aotopsy _debug decompile-native --lib libapp.so --find MyClass         # locate by name
aotopsy _debug decompile-native --lib libapp.so --func 0x1a92728       # one function at a VA
aotopsy _debug decompile-native --lib libapp.so --from-main --out out/ # reachability from app entry
aotopsy _debug decompile-native --lib libapp.so --all --filter MyClass # bulk, filtered
```

Warning: `--all` without a small `--max` can require ~64GB RAM on a real app. Prefer `--find`/`--func`/`--from-main`.

### Ghidra / IDA (ARM64 only)

```bash
aotopsy ghidra libapp.so        # headless Ghidra with metadata injection
aotopsy ida libapp.so           # headless IDA via idalib
```

Both reject x86_64 input. Use `decompile-native` for x86_64 pseudocode.

### Frida script generation

```bash
aotopsy _debug decompile-native --lib libapp.so --func 0x1a92728 --gen-frida --gen-frida-out hooks.js
frida -U -f com.example.app -l hooks.js --no-pause
```

See `FRIDA.md` for the full guide.

### Cross-referencing and tracing

```bash
aotopsy _debug strings --lib libapp.so --find "X-Signature" --xref   # which function loads this string?
aotopsy _debug ffi-trace --lib libapp.so --filter MyClass            # dart:ffi call sites
aotopsy _debug dispatch-table --lib libapp.so --filter MyClass       # dispatch table entries
aotopsy _debug fingerprint --lib libapp.so                           # build-id and version markers
aotopsy _debug funcdiff --old old.so --new new.so                    # function set diff
aotopsy _debug symbolmap --stripped lib.so --unstripped debug.so     # resolve stripped targets
```

### Corpus tools

```bash
aotopsy inventory --dir samples/                    # catalog APKs
aotopsy parity --samples samples/ --out out/        # cross-version parse report
aotopsy _debug thr-audit -lib libapp.so -out thr.jsonl  # THR access scan
```

## Output Artifacts

| File | Contents |
|------|----------|
| `functions.jsonl` | Name, address, size, owner, param count per function |
| `call_edges.jsonl` | BL/BLR edges with resolved targets and provenance |
| `classes.jsonl` | Field names, offsets, instance sizes per class |
| `string_refs.jsonl` | String references from object pool loads |
| `dispatch_table.jsonl`| Inferred dispatch table receiver types and target mapping |
| `signal.html` | Behavioral signal report with context graph |
| `dart_meta.json` | Snapshot metadata, compressed pointers flag, THR layout |
| `flutter_meta.json` | Unified metadata for Ghidra/IDA (ARM64 only) |
| `aotopsy.sarif` | SARIF 2.1.0 security finding report (for GitHub Code Scanning) |
| `evidence.jsonl` | Unified evidence model with confidence and provenance per call site |
| `asm/*.txt` | Annotated disassembly per function |
| `asm/*.bin` | Raw instruction bytes per function (both architectures) |
| `dart/*.dart` | Per-function decompiled pseudocode (with `--decompile`) |
| `cfg/*.dot` | Per-function CFGs (with `--graph`) |

## Package Layout

```
cmd/aotopsy/          CLI entry point and command handlers
internal/
  analysis/           Pipeline orchestration, snapshot loader, and analysis engines
  sdk/                Dart VM ground-truth facts, register mappings, and predicates
  vmtables/           Versioned THR field offsets, stub names, and stub orders
  thraudit/           Thread-relative memory access audit and classification
  arch/arm64/         Centralized ARM64 bitmask instruction decoders
  arch/x86/           Centralized x86_64 decode primitives and register helpers
  naming/             Central pool lookups, name resolution, and stub builders
  elfx/               ELF validation and symbol extraction
  snapshot/           Snapshot region extraction, version profiles
  dartfmt/            Dart VM variable-length integer encoding
  cluster/            Two-phase snapshot deserialization (alloc + fill)
  disasm/             ARM64 + x86_64 decode, CFG, call-edge provenance
  callgraph/          Call graph construction and DOT rendering
  signal/             Behavioral string and malware signal classification
  render/             HTML/DOT/SVG visualization
  output/             JSONL and SARIF 2.1.0 serialization
  decompiler/         Dart-AOT pseudocode decompiler (both architectures)
  typetrack/          Whole-program type inference and receiver recovery
  fingerprint/        Build-id and version marker identification
  funcdiff/           Function-set diffing between builds
  symbolmap/          Stripped-vs-unstripped symbol resolution
  ffitrace/           Static dart:ffi call-site tracing
  strxref/            String-to-function cross-referencing
  strutil/            Dart syntax sanitization and metadata serialization
  jsonutil/           Generic JSONL stream readers and writers
  evidence/           Unified evidence model with confidence and provenance
  frida/              Frida runtime hook and probe generation
  cli/                ANSI color helpers for CLI output
tools/                Standalone utilities (THR table extractor and validator)
ghidra_scripts/       Ghidra integration (Python)
ida_scripts/          IDA integration (Python)
```

See `ARCHITECTURE.md` for the deep dive into each package.

## Build

Requires Go 1.25+.

```bash
make build      # build ./aotopsy
make install    # install to ~/.aotopsy/bin, plus the Ghidra/IDA integration
                # assets into ~/.aotopsy/ghidra_scripts and ~/.aotopsy/ida_scripts
make test       # run tests
make bench      # regenerate BENCHMARK.md (needs local ground-truth twins)
make coverage   # regenerate COVERAGE.md (needs local corpus samples)
make analyze    # cross-check export-dart output against `dart analyze`
```

Integration tests resolve their input from `internal/samplecorpus`, which looks for a `samples/` directory; there is nothing to set. `samples/` is gitignored, so a checkout without one skips those tests — but a checkout that *has* a corpus and is missing a registered sample fails, because a drifted corpus and an absent one mean different things.

Public CI runs `gofmt`, `staticcheck`, build, vet and shuffled unit tests across linux/amd64, darwin/arm64 and windows/amd64, plus a race+coverage job with a coverage floor.

## Releases & Branches

AOTopsy uses a two-branch model:

| Branch | Role |
|--------|------|
| `main` | **Stable.** Every commit is a squash-merged, gate-verified release candidate. Tagged releases (with prebuilt cross-platform binaries) are cut from here. |
| `develop` | **Rolling / nightly.** Where day-to-day small commits, features, and research land first. May be unstable between merges. Batched into `main` via a squash-merge PR once the gates are green. |

Contribute against `develop`; open a PR into `main` only when a batch of work is gate-verified.

Prebuilt binaries for Linux, macOS, and Windows (amd64/arm64) are attached to each
[GitHub release](../../releases). AOTopsy is pure Go, so `make build` cross-compiles cleanly for any target.
Each release archive also carries `ghidra_scripts/` and `ida_scripts/` next to the
binary, which is the layout `aotopsy ghidra` and `aotopsy ida` discover — so those
commands work straight from an unpacked download, with no checkout needed.

## Limitations & Scope

AOTopsy states plainly what it does and does not recover. Some limits are engineering
scope; others are **hard AOT-format floors** — information the Dart compiler removes in
release (PRODUCT) builds, verified against the SDK source. We document floors rather than
fabricating over them.

**Hard AOT floors (verified — do not expect these to improve):**
- **Instance field names are ~97–99% absent.** `Precompiler::DropFields` keeps field
  names only under `#if !defined(PRODUCT)`; a real app has ~233 named `Field` objects vs
  ~16k synthetic. Accessor-based recovery (`get:`/`set:` still carry the name) pierces
  this partially (−11–22%, deterministic, never guessed); the rest is genuinely gone.
- **Local and captured variable names are gone.** Rendered as `local_*` / `tN`.
- **Truly polymorphic dispatch targets are not statically resolvable.** BLR through a
  dispatch table / dynamic `Closure` object is an AOT limit, not an analysis gap; these
  render honestly as `indirectCall` / `dynamicCall`. See [METHODOLOGY.md](METHODOLOGY.md#limits-of-this-method-honestly).

**Engineering scope:**
- **AOT only.** No JIT support.
- **Ghidra/IDA decompilation is ARM64-only.** x86_64 is rejected with a clear error — use `decompile-native` instead (the only static x86_64 Flutter decompiler).
- **`--all` decompilation can crash the host.** A real full-size app needs ~64GB RAM for unbounded `--all`. Use targeted modes (`--find`, `--func`, `--from-main`) or cap with `--max`.
- **Virtual dispatch is invisible to `--from-main` reachability.** Widget lifecycle callbacks go through Flutter's framework dispatch, not direct call instructions. A class-touch heuristic recovers some, but it's an over-approximation. Use Frida for the rest.
- **Every Dart version change must be modeled.** There is no VM to handle format changes automatically. The snapshot carries a git-derived hash, not a version number, so support is structure-based. Currently modeled: Dart 2.10 → 3.13.
- **Ground-truth twins are not redistributable** (real production builds), so the
  name-recovery differential runs locally, not in public CI.

## License

BSD-3-Clause. CID tables, THR field offsets, and stub names are derived from the [Dart SDK](https://github.com/dart-lang/sdk) (also BSD-3-Clause). See `LICENSE` and `NOTICE`.
