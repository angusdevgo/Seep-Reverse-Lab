# Toolchain — What to Use, How to Invoke It, and Where It Lies

Load this when you are choosing tools, when a tool produces an answer that smells wrong, or when
something is not installed. It is a map, not a tutorial: each entry says what the tool is *for*, how
to drive it non-interactively, and the failure mode that wastes time.

**Prefer tools you can drive from a command line.** An agent cannot click. A tool that ships only a
GUI is not automatically out of reach — check for a headless or MCP path first, which is an
install-and-set-up step rather than a reason to substitute the tool. When no such route exists, ask
for a human instead of stalling or silently downgrading to a weaker method.

## Tier 0 — present on almost any machine, no install

Use these before reaching for anything heavier. They answer structure questions in seconds and
cannot be broken by a missing dependency.

| Tool | Use it for |
|---|---|
| `file`, `readelf -h/-l/-d/-r`, `objdump -d`, `nm -D`, `strings` | ELF structure, program headers, dynamic section, relocations, dynamic symbols |
| `unzip -l`, `zipinfo` | what is actually inside an APK, entry sizes and compression |
| `sha256sum` / `Get-FileHash` | identity. **Always hash before and after; never trust "it should be the same file"** |
| `xxd` / `hexdump` | byte-level ground truth when a tool disagrees with another tool |
| `python3` | all the scripts here; the standard library alone covers most parsing |

`readelf`/`objdump` walk **section** headers. If a target's section table is forged (see
`native-tamper-and-suicide.md` §Forged section headers) they will print confidently wrong output —
cross-check with the program headers.

## Tier 1 — dex and Java

| Tool | Invoke | Why this one |
|---|---|---|
| `baksmali` / `smali` (jars) | `java -cp <jars> org.jf.baksmali.Main d <dex> -o <dir>` | round-tripping, reading a method precisely |
| `dexlib2` | small Java program | method-level rewrite, leaves everything else untouched (`dex-patching.md`) |
| **`rasc`** (Rust ASC) | `rasc findrefs app.apk string <S>` | **the same index, 4–15× faster**, no Python runtime, a Rust DEX decompiler behind `getclass`. Reach for this FIRST when it is built — its one blind spot is documented in `rasc-and-droidsaw.md` |
| **`droidasc`** (ASC) | `droidasc findrefs app.apk string <S>` | the original Python index, one `pip install` away, and the cross-check for `rasc`. Reach for it FIRST when `rasc` is not built |
| **`ddc`** | `ddc app.apk -c <Class>` | **fastest read of dex as Java, plus query subcommands** — reach for this SECOND, to *read*. See below |
| `apktool` | `java -jar apktool.jar d/b` | whole-app decode including resources |
| `jadx` | `jadx --no-res -d <out> <apk>` | readable Java for orientation; **not** a source of truth, and **not** a recon entry point (see below) |
| `aapt2` | `aapt2 dump badging <apk>` | manifest facts, package name, versions |
| `zipalign`, `apksigner` | from build-tools | alignment and signing |

### rasc — the same index in Rust, when you have built it

`rasc` is the `rust` branch of the same project (`MG1937/ASC`). Same CLI shape — `classes`,
`manifest`, `getclass`, `findrefs {string,type,method,field}` — no Python at all, and a 2.13 MB
binary. **Measured on this repository's archives: identical class-definition sets on both a 1.4 MB
MASTG challenge and a 34.8 MB app (30,768 classes, 0 differences either way), at 4.0–4.7× for
`classes` and up to 14.7× for `findrefs`.**

It must be built — there is no release asset and no crate — so the kit wraps that:

```bash
python scripts/rasc_build.py --check            # what is present
python scripts/rasc_build.py --build            # needs git + rustup; ~2 min
python scripts/rasc_build.py --verify app.apk   # compares class sets against droidasc, fails on a difference
```

**It is a registered capability, so G2 does not have to guess:** `doctor.py` reports `dex_index_rust`
as `OK` when a binary is present (PATH, `APKREV_TOOLS`, or the work-area path `rasc_build.py` builds
into) and `BLOCKED` with that build command as the next action when it is not — alongside
`dex_index_python` for the `pip install` route. A machine with neither is not stuck: the Python
indexer is one command away, and the two are cross-checked against each other by
`rasc_build.py --verify`.

**The one thing to know before trusting its `getclass`:** on an `enum` whose constants override an
abstract method, the outer class is printed as a bare constant list and the per-constant bodies are
**not inlined** — no warning, and none in the Python tool either, because both leave those bodies in
their own subclasses. They are one query away (`Lpkg/Enum$1;`, and both tools decompile those fully);
`droidasc`'s outer-class listing is simply richer (2,170 B vs 314 B on the measured class, carrying
`$VALUES`, `$values()` and the constructors). Sampling 20 app-like classes from a real app, 17 were
judged by the JADX-parity harness and 16 agreed literal for literal; the one that differed was exactly
this shape. Use it to *locate* and to read ordinary classes, and read the constants when an enum shows
no bodies. The measurements and the failing class are in `references/rasc-and-droidsaw.md`.

### droidasc (ASC) — ask an APK "who references this?", in one query

Install it in one line. No JVM, no Android SDK, no GUI, no first-run indexing:

```bash
pip install droidasc          # provides the `droidasc` CLI
```

It treats the artifact as a **read-only database** instead of exporting a source tree: it probes the
deflate stream in place and rebuilds only the minimal dex it needs, in memory, for the one class you
asked about. Nothing is inflated to disk; there is no index-building phase to wait through. (Design
and measurements are the author's; the BlackHat EU 2026 Arsenal abstract is the reference.)

```bash
droidasc findrefs app.apk string "/data/app/"        # every site that mentions a literal
droidasc findrefs app.apk string com.example/sdk      # a channel name, a URL fragment, a field name
droidasc findrefs app.apk type   com/foo/Bar         # who references a type
droidasc findrefs app.apk method notify --class MainActivity --fuzzy-class
droidasc listclass app.apk --prefix com/poc          # what classes exist (28210 classes: seconds)
droidasc listclass app.apk -o classes.txt
droidasc getclass  app.apk Lcom/poc/Main; -o Main.java
droidasc getmanifest app.apk -o AndroidManifest.xml
```

Each hit names the **class and method** it sits in. That is the whole value: it turns "which of 28,000
classes mentions this string" from a crawl over an exported tree into one sub-second query, and it works
straight off the APK you were handed.

**What it is for, and where it stops.** ASC answers *location* questions. It is not where you read a
method body, and it does not replace the kit's dex tooling for patching. Its place is the first ten
minutes of recon plus every later "where else is this used?" — the questions that otherwise send you
grepping a hand-exported smali tree.

**Three limits, and one of them is a trap.**

- **A non-ASCII needle is not trustworthy through a shell.** A `findrefs string` query for a non-ASCII
  literal returned nothing under Windows/PowerShell, and **an empty result is indistinguishable from a
  broken argument encoding.** Many non-ASCII literals genuinely live in a native library rather than in
  dex, so "nothing came back" is a plausible answer — which is exactly what makes the unverified
  negative dangerous. Confirm it another way before recording it: search the dex bytes directly with a
  `\u`-escaped needle, or run a control query you know must hit (a path fragment, a package name you
  already read in the manifest) in the same session.
- **A mangled class name may return only resources.** `listclass apk --prefix <the plugin's package>`
  can come back with nothing but `R$anim` / `R$string` / `R$style` entries, which is **not** a dead end:
  it is evidence the real class was renamed by R8. `findrefs string <the plugin's channel name>` still
  hands you the obfuscated class implementing it. This is the single situation where ASC is not an
  alternative to `ddc` but the only route — `ddc -c <FQCN>` needs the post-R8 name to start with.
- **A hit is a *reference*, not a *call*.** `findrefs` proves a literal or type is mentioned in a method;
  whether that method runs on the path you care about is a different question, and the answer comes from
  the disassembly or from runtime (`dynamic-frida.md`).

The division of labour is worth stating plainly: **ASC locates, `ddc` reads.** Running a full `ddc`
export first, then grepping it, is the slow path this tool exists to replace.

**Measured in the extension pass** (droidasc `0.1.1.post1`, installed with `python -m pip install
droidasc`; dependency is androguard only, no JVM, no SDK):

| Command | Result on a 38.7 MB hardened APK |
|---|---|
| `getmanifest` | 0.44 s → 32,345 B of complete XML |
| `findrefs … string jiagu` | 0.42 s → hits inside the shell class's `<clinit>` and `attachBaseContext` |
| `getclass com/stub/StubApp` | 0.33 s → 22,802 B of Java |
| `listclass` (whole APK) | 0.18 s → **4 classes** |

Two facts from that run are worth carrying into any recon: the CLI name is **`droidasc`**, not `asc`
(there is no `asc` binary, and `asc --version` is simply "command not found" — `python -m droidasc`
also works), and on a packed APK a full `listclass` returning four classes is not a broken tool: the
business dex is not in the file. Reaching for `getclass` on a class that is not there exits **1** with
`Class … not found in APK.` — treat ASC as a manifest-and-shell inspector on hardened input, and take
the business-logic question to a different layer.

### ddc — dex-to-Java with query subcommands (worth adopting)

A single-file Rust binary, no install, no JVM. Two things make it more useful than
"a decompiler":

```bash
ddc info app.apk                     # label, package, version, launcher, sdk, per-dex counts
ddc findrefs app.apk string "SomeToken"    # every reference site, class#method
ddc strings app.apk -f "splash" --with-locations
ddc app.apk -c com.example.Foo       # one class as Java
ddc app.apk -o out/                  # full decompile, a few seconds for a normal APK
```

Measured on a 4.7 MB APK (4,070 classes / 30k methods): `info` ~0.13 s, `findrefs`
~0.11 s, one class ~0.25 s, full decompile ~2.8 s producing ~4,000 files.

**Measured in the extension pass** (ddc `0.1.8`, a single Rust binary — on Windows `bin/ddc.exe`,
1,028,096 B, **not on PATH** and carrying no PE version resource, so `ddc -V` is the only way to read
its version; source: the project's GitHub releases):

| Command | Result on a 38.7 MB hardened APK |
|---|---|
| `ddc info` | 0.24 s → label / package / version / application / launcher / sdk / size / md5, plus per-dex class, method, field and string counts |
| `ddc findrefs <apk> string jiagu` | 0.13 s → tabulated `dex | kind | class | method | refs` |
| `ddc strings -f jiagu --with-locations` | 0.14 s → strings mapped to the methods that hold them |

**The trap on this one is the exit code.** Asked for a class that is not present, `ddc` exits **2**
*and still prints its help text to stdout* — so a wrapper that tests "did anything come back?" reads a
usage error as an answer. Branch on the exit code, never on output emptiness. The same run also
confirms the layered picture from the other direction: `info`'s per-dex counters report 4 classes and
29 methods with code for the whole 8.9 MB shell dex.

Why the query subcommands matter more than the speed: **string cross-referencing
becomes a lookup instead of a crawl.** Asking "which class mentions this config
field name" is a sub-second command here and easily an hour of smali grepping by
hand. That single property is what turns "find the convergence point" from
exploration into a query.

`info` also **prevents a specific, costly mistake**: reading the package identity
out of the binary manifest by hand. Hand-extracted AXML strings are ambiguous —
class-name fragments look exactly like package names, and picking the wrong one
sends every later `pm`/`dumpsys`/data-dir query to a package that does not exist.
Let the tool report `package`, `label` and `launcher`, and cross-check with
`aapt2 dump badging` when available.

Limits to plan around: types are erased (no generics); R8 short names stay short,
so you still need string cross-references to infer meaning; output is a **reading
aid, not compilable source** (occasional declaration/use ordering is inverted, and
numeric resource ids appear as decimal integers); very large methods produce
thousands of lines and are better approached via `findrefs`/`getmethod` first.

Two more, both measured on a 28,210-class R8-flattened Flutter APK:

- **`-c <FQCN>` cannot reach a renamed class, and `listclasses <pattern>` cannot recover it either.**
  Asking for the plugin's documented name returned `class not found`; asking for its package prefix
  returned only `R$anim` / `R$string` / `R$style` resources. The implementing class existed under a
  short R8 name, reachable only by string cross-reference. **Plan for `droidasc` to close this gap** —
  it is not a nicety, it is the difference between locating the class and not.
- **A decompiled body can be semantically wrong, not merely ugly.** In one 9 KB helper class the
  compiler emitted a `return 0;` inside a method declared to return `String`, reordered field
  assignments, and produced empty `if/else` branches. None of that is safe to reason *about* control
  flow without checking smali or bytecode. Treat a surprising construct as a decompiler artifact until
  the bytecode agrees.

**Use `findrefs` to locate, `-c`/`getmethod` to read, and the bytecode to decide.** Reading order
matters: a full `ddc <apk> -o out/` export is a reasonable thing to *have*, but grepping that tree is
not a substitute for one indexed query, and it is the slower of the two by a wide margin on any APK
worth analyzing.

**Classpath gotcha.** `baksmali`/`smali` need their dependency jars on the classpath together
(`smali`, `antlr-runtime`, `stringtemplate`, `baksmali`, `dexlib2`, `util`, `jcommander`, `guava`).
Missing one produces `ClassNotFoundException` that reads like a broken target. `scripts/smtool.py`
carries the classpath so you pass it once.

**Entry-point gotcha.** The main class has moved between versions — `org.jf.*` in older builds,
`com.android.tools.smali.*` in newer ones. If `ClassNotFoundException` names the **main class**, it
is a version mismatch, not a missing jar.

**jadx is for reading, not for concluding.** Decompiled Java reorders and rewrites control flow;
line numbers and even which branch is which can differ from the bytecode. When a decision depends on
it, verify in smali or at runtime. `jadx` writing `(unknown)`/empty method bodies means it failed,
not that the method is empty.

**`smali` assembling can abort silently** — the tree produces no dex while the process still exits
0. Never treat exit code as proof of a build. Assert the artifact exists, is fresh, and is non-empty
(`patch-audit.md`).

## Tier 2 — native

| Tool | Invoke | Notes |
|---|---|---|
| `radare2` / `rizin` | `r2 -q -c '<cmds>' file` | scriptable disassembly/analysis; the practical choice when no GUI is available |
| `Ghidra` (headless) | `analyzeHeadless <proj> <name> -import <file> -postScript <s>` | decompiler without a GUI; slower to script but far better output than a raw disassembler |
| `capstone` (python) | library | decoding in your own scripts — see the silent-stop trap below |
| **`svc_scan.py`** | `python scripts/svc_scan.py libfoo.so [--context 3]` | **names the syscall behind an inline `svc`** and reports which PT_LOAD segment each hit is in. Use it *before* planning a libc-level hook: a module with its own `exit`/`kill` `svc` sites is not observable through libc, and one without them means a missing event is a finding about your hook. Read the neighbours (`--context`) — a byte scan for `svc` also matches inside data. Measured on the test device: device `libc.so` = 4 termination sites (its own exports), a shell library's 21 hits = all data |
| `keystone` (python) | library | assembling a short patch when you are editing bytes by hand |
| `pyelftools` (python) | library | **section-based — unreliable on hardened targets.** Prefer hand-walking `PT_LOAD`/`PT_DYNAMIC`, as `scripts/elf_plt.py` does |
| IDA Pro | GUI, **or headless via `idalib-mcp`** | the strongest decompiler output. Do not assume it needs a human in front of it — a headless MCP server exists (see *MCP tool servers* below). Ask for a human only when that setup is genuinely unavailable |
| `x64dbg` | GUI, Windows | human-driven live debugging of a native Windows target |
| `gdb` / `lldb` | CLI | live debugging where a device or emulator allows it |

**capstone can stop silently.** Decoding a buffer that does not begin at an instruction boundary may
return a few instructions and then nothing, with no error. A scan built on that reports "no matches"
for a library full of matches. Use byte-pattern search or a resynchronising scan for anything where
completeness matters (`native-tamper-and-suicide.md` §Scanner traps).

**Disassembler output is a hypothesis.** Fixed-width architectures (aarch64) decode almost any
4-byte window into *some* instruction, so a wrong start offset yields plausible-looking garbage.
Bound your window with a known entry point or a known call site.

**A decoder is a decoder, not an oracle.** Two independent decoders agreeing is the signal worth
having (measured: a hand-written word scan for the `svc` encoding and the `capstone`-based scan in
`svc_scan.py` returned the identical 214-site set on a device `linker64`, set difference empty); one
decoder's disagreement with itself is not. **`dexdump`** (from build-tools, e.g.
`E:\tools\android-14\dexdump.exe`) is the cheap independent reader for the dex half of this: use it
to count a dump's class and method records rather than trusting a self-written parser, the same way
`advanced-unpacking.md` §Establish "the bodies do not decode" with a decoder you did not write
requires.

### Ghidra — the decompiler for a target whose decisive layer is aarch64

The recurring shape: the app is fine, the dex is readable, and the layer that actually decides
behaviour is a stripped aarch64 `.so`. A disassembler gives you instructions; only a decompiler gives
you control flow. **Hand-walking an OLLVM control-flow-flattened function with `capstone` is the single
most expensive route available**, and it is what you fall into when no decompiler is installed.

Ghidra is free, runs headless, and decompiles aarch64. Setup is unzip plus a JDK (11+), which is why
"there is no decompiler on this box" is normally an install step rather than a finding about the target
(§Closing a capability gap).

```bash
# one-time: unzip the release; point Ghidra at a JDK (JAVA_HOME or the launch script)
# headless: import, auto-analyse, run a post-script, discard the project
analyzeHeadless <proj_dir> <proj_name> -import target.so \
    -postScript DumpFunction.java <addr_or_symbol> -scriptPath <dir> -deleteProject
```

Three caveats learned the hard way:

- **`analyzeHeadless` is slow and its auto-analysis is not free.** Import plus analysis of a 6 MB
  stripped library is minutes, so it is exactly the kind of run that needs an explicit timeout. Budget
  it once and reuse the project; do not re-import per question.
- **Flattened control flow defeats the decompiler as well.** A `br x8` dispatcher with four constant
  arithmetic operations in every function header is OLLVM flattening, and the output is a state machine
  that resembles the program without being readable. **Removing the flattening is the work**
  (`code-virtualization-and-custom-linkers.md`), not a prerequisite you can skip.
- **A decompiler cannot go where the data is not.** When a library's strings and action names are
  **encrypted in the file and exist only once the module is mapped in memory**, no static tool recovers
  them by reading harder — escalate to runtime (`dynamic-frida.md`) instead of escalating the static
  toolchain. Telling "install a decompiler" apart from "the decompiler cannot help here" is worth real
  time: the two look identical from the outside, and only the first has a static answer.

## Closing a capability gap — installing the tool IS the task

A missing tool for the layer you must work in is not a constraint to design around. It is the next
step. The measured cost of installation is almost always smaller than the cost of the workaround, and
the workaround is what produces "we could not determine X" reports on targets where X was decidable.

**The decision is not "can I do without it" — it is "how long does installing it take".** Three real
numbers, from one Windows box working an R8-flattened Flutter target:

| Gap | Install cost | What the workaround would have cost |
|---|---|---|
| No whole-APK cross-reference index | `pip install droidasc` — one command, seconds, no JVM, no SDK | hours of `grep` over a hand-exported smali tree, **per question asked** |
| No arm64 decompiler | Ghidra — unzip plus the JDK already present; minutes | a manual ELF/`capstone` walk over an OLLVM control-flow-flattened 6 MB library, per function |
| No Dart AOT snapshot front end | `aotopsy` — unzip and run (pure Go, no toolchain); or `blutter`, measured **≈78 s** end to end | "pool offsets can never be mapped", which turned out to be false |

The third row is the instructive one. The documented cost ("tens of minutes for the first build") was
about **30× pessimistic**, and the documented toolchain requirement was overstated. **A tool's stated
prerequisites are a claim, not a measurement**, and the cost of checking is one attempt.

Rules that follow:

1. **Write the capability down before spending against it.** "arm64 decompilation — absent — install
   Ghidra" is a task item. "arm64 decompilation — absent" with nothing after it is how a route gets
   written off for the wrong reason.
2. **Check off-PATH before declaring anything absent** (§"not on PATH" is not "not installed").
   `APKREV_TOOLS` exists so a project-local tools directory or an SDK folder resolves.
3. **Install, do not substitute.** A weaker tool's output presented as equivalent to the stronger
   tool's output is a wrong conclusion with a clean audit trail — worse than an admitted gap.
4. **Report the gap only when it is real.** "No arm64 decompiler exists here and it cannot be installed
   because `<reason>`" is a valid finding. "I used `readelf` instead" is a different statement, and it
   is not a finding about the target.
5. **"Paid" and "GUI-only" are questions, not walls.** IDA has a headless MCP path; Ghidra has
   `analyzeHeadless`; both are set-up steps. Ask a human only after that route is genuinely
   unavailable.
6. **One real disqualifier.** A decompiler cannot go where the data is not: if a target's strings and
   action names are **encrypted in the file and only exist in memory**, then no static tool recovers
   them by reading harder. Recognise that shape early and move the effort to runtime
   (`dynamic-frida.md`) instead of escalating the static tools — that distinction is the difference
   between "install a decompiler" and "the decompiler cannot help here", and they look identical from
   the outside.

## Where to get a tool we do not ship — a sourced gap list, not a link dump

The list below exists because "install the tool" needs a *source*, and searching for one on a target's
clock is how a ten-minute install becomes an hour. **Two grades are used here and they are different
claims:** `URL verified` means the repository was resolved on the date given; `tool unverified` means
nobody has run it here. Most rows are `URL verified / tool unverified` — treat them as leads with a
date on them, not as recommended tools, and check the row's own prerequisites when you install it
(§Closing a capability gap — installing the tool IS the task). Rows marked `measured` have been used here.

| Gap | Source | Grade / what is actually known |
|---|---|---|
| Decompiler for dex/Java | `https://github.com/skylot/jadx` | URL verified 2026-09-21; tool unverified here (not installed). The kit's route is `droidasc`/`ddc` for queries and jadx only to *read* a class already located |
| Repacking beyond `scripts/repack.py` | `https://github.com/iBotPeaches/Apktool` | URL verified 2026-09-21; tool unverified. Not installed on this host, and the `apktool.bat` in `E:\tools\bin` is a dead link — do not trust a `.bat` to mean the tool works |
| smali round-trip outside the bundled dexlib2 kit | `https://github.com/JesusFreke/smali` | URL verified 2026-09-21, **last upstream push 2024-01-17** — maintenance status is a fact to check before adopting it for a new dex version |
| Anti-detection on the frida side (patched server plus a script surface aimed at RASP) | `https://github.com/CrackerCat/strongR-frida-android` | URL verified 2026-09-21; tool unverified. A patched `frida-server` is an **environment** change: record it in the task record, because results obtained under it are not comparable to a run without it |
| A dex dumper that does not use `ptrace` | `https://github.com/index-login/MobileRE-Skill` (`.kilo/skill/rev-dex-dumper/`) — `panda-dex-dumper`, `mem-dex-dumper` + C source | **Partly measured**: both ELF images were inspected here and neither imports a `ptrace` symbol (`panda` = aarch64 `ET_DYN`, 48 symbols; `mem` = aarch64 static, stripped), so the *claim* is consistent at the symbol layer; the **dump behaviour was not run here**. Our own `/proc/<pid>/mem` read is `advanced-unpacking.md`'s root-side route and is measured |
| eBPF-based dex extraction | `https://github.com/LLeavesG/eBPFDexDumper` | URL verified 2026-09-21; tool unverified, **and unusable on `<DEVICE>` anyway** — kernel 4.14 against a 5.10+ requirement (`kernel-and-environment-hardening.md`). Listed so the next reader does not re-derive the version gate from scratch |
| Decompilation/deobfuscation/unpacking without a JVM | `https://github.com/adam-040/Enigma`, `https://github.com/1-3-7/disrobe` | URLs verified 2026-09-21; tools unverified. Both are interesting precisely because they remove the JVM/IDE dependency a Ghidra or IDA route carries — evaluate prerequisites before adopting |
| Java2C generation to *build* a fixture | `https://github.com/amimo/dcc` | **Partly measured here**: `dcc` itself was run in a previous pass, but the C compile needs an NDK this host does not have, so no Java2C artifact was ever produced (`java2c-and-jni-sinking.md`) |
| Building an LSPosed module without gradle, or comparing against a maintained template | `https://github.com/Jordan231111/lsposed-universal-template` | URL verified 2026-09-21; tool unverified. Its layout is gradle-based, which this host cannot build — useful as a **manifest/scope reference** only. (`mabbcoll13/xposed-module-kit` no longer resolves: HTTP 404 on 2026-09-21, which is why this row's date is worth writing down) |
| Dart AOT snapshot front end | see the §Closing a capability gap table above | measured here: `aotopsy` runs with no toolchain; `blutter` measured ≈78 s end to end on this host |

Two habits that keep this list from rotting: **write the access date next to a URL** (a dead link with
no date reads as a current recommendation — one row above is already 404), and **promote a row only
when someone runs the tool**, so `URL verified` never silently becomes "we use this".

## MCP tool servers — an external dependency, not a tool on the shelf

An MCP server is neither a CLI tool nor one of the scripts here. It is a **separate installation plus
a running process**: something to install, a service to start, usually an extension to load, often an
authorization step. Listing one beside `readelf` would imply it is already present. Declare it as a
dependency with its prerequisites, and check whether it is actually available *before* planning work
that needs it — discovering this mid-task is the "missing tool" failure again.

### IDA Pro, headless

IDA does **not** require a human at a GUI. `mrexodia/ida-pro-mcp` ships `idalib-mcp`, a headless MCP
server that drives an IDA database with no GUI process at all:

```sh
uv run idalib-mcp --host 127.0.0.1 --port 8745 path/to/executable   # open a binary up front
uv run idalib-mcp --host 127.0.0.1 --port 8745                      # open databases on demand
uv run idalib-mcp --stdio                                           # for stdio-based clients
```

Prerequisites, all of which must be arranged before the first call: IDA Pro 8.3+ (9 recommended;
**IDA Free is not supported**), a Python 3.11+ that `idapyswitch` can select, `uv`, and an `idalib`
activated globally via `py-activate-idalib.py`. Each open database lives in a worker process that
outlives the supervisor and is adopted transparently by a later supervisor on the same host, so
several sessions can share one analysis. Every tool call carries an explicit `database` argument —
there is no implicit "current database" — and `idb_open` returns the session id you must pass.

The GUI-plugin variant of the same project is deprecated upstream in favour of `idalib-mcp`; do not
set that up for agent work.

### Ghidra

`LaurieWired/GhidraMCP` is a Ghidra **extension** plus a separate Python bridge, not a headless
analysis server: Ghidra must be running with the plugin loaded (its HTTP server defaults to
`127.0.0.1:8080`) and the bridge is another process your client starts. Treat it as requiring an
interactive GUI session. For unattended work the shape that actually runs without a GUI is
`analyzeHeadless` with a post-script.

### The boundary: deobfuscate before you hand the binary to a model

Both are LLM-driven, and they inherit the model's weaknesses. The IDA MCP authors say it plainly in
their own README: **"LLMs will not perform well on obfuscated code"**, and they advise removing
string encryption, import hashing, control flow flattening, code encryption and anti-decompilation
tricks *before* asking a model to solve anything.

That matters more here than in most domains, because it is precisely the shape of the targets this
skill deals with. An OLLVM-style or virtualized binary is not a job for a model reading decompiler
output; the deobfuscated version is a *different binary*, and producing it is the work already
described in `code-virtualization-and-custom-linkers.md` and
`native-tamper-and-suicide.md`. The same advice has a second half: resolve library code first
(FLIRT/Lumina) so the model is not asked to reason about `memcpy` as if it were the program.

Two consequences worth carrying into the plan:

- Ask a model for **navigation and reading** — rename, comment, summarise a function, convert an
  immediate — and verify anything that decides the patch against the disassembly yourself.
- If the server is not installed, that is a **missing dependency to report**, not a licence to present
  a weaker tool's output as equivalent (`packers.md`).

## Tier 3 — runtime and network

| Tool | Invoke | Notes |
|---|---|---|
| `frida` (host) + `frida-server` (device) | `frida -U -f <pkg> -l script.js` | **host and device versions must match** — skew produces errors that look like a broken target (`pitfalls.md` P15) |
| `objection` | `objection -g <pkg> explore` | quick Java-layer poking on top of Frida |
| `mitmproxy` | `mitmproxy --mode regular` | request/response inspection; a device proxy is usually faster to set up than a transparent one |
| `HaE` (Burp extension) | load into Burp, then read its rule set | **traffic *triage*, not traffic capture.** See below |
| `adb` | everything | the primary device interface |

**HaE is a reader, not a capture tool, and it is not always the right next step.** HaE (Highlighter and
Extractor, `overspace-labs/HaENet`) is a Burp Suite extension that tags and extracts fields from HTTP
messages — tokens, IDs, secrets, endpoints, fingerprints — so that a large session becomes readable
without hand-scanning every request. It is genuinely useful when the bottleneck is *"there is traffic
and I cannot see the parts that matter."*

It is the wrong tool when the bottleneck is one of these three, and reaching for it there costs rounds:

- **The requests never leave the client.** No capture tool can display a request that was never built
  (`code-virtualization-and-custom-linkers.md` §what the native check actually reads). **Establish
  whether traffic exists before buying tooling to read it** — a DNS/`connect`-level probe answers that
  in a single run, and on the measured target it was the observation that ended the investigation
  branch, not a capture.
- **The body is encrypted by the app**, so the capture is ciphertext (`server-api.md`).
- **Certificate pinning defeats the proxy**, in which case the empty capture is itself the finding
  (`tls-and-cert.md`).

Ordering that follows: **first prove there is readable traffic, then choose the reader.** `mitmproxy`
captures; HaE triages; neither substitutes for the DNS/connect check that decides whether there is
anything to triage. Treat "install a Burp plugin" as a step that must be justified by an existing
capture, not as recon.

Version alignment for Frida is a **hard gate**, not a nicety. Check both sides before writing a
script, and check the device architecture — the server binary is per-ABI.

## Tier 4 — cross-platform runtimes

| Runtime | Identifier | Tool |
|---|---|---|
| Flutter / Dart | `libflutter.so` + `libapp.so` | `blutter` (needs the **matching Dart version**) — `dart-aot.md` |
| Unity / IL2CPP | `libil2cpp.so` + `global-metadata.dat` | Il2CppDumper + a native decompiler |
| React Native | `libhermes.so` / `index.android.bundle` | Hermes bytecode tooling, or plain JS if the bundle is unminified |
| Cordova / hybrid | WebView + `assets/www` | read the JS directly; Java layer is usually thin |

**A version mismatch here wastes the most time of any tool in this file.** A Dart decompiler built
for a different engine version produces output that is subtly wrong rather than obviously broken.
Pin the version first (`dart-aot.md`) and do not "try it and see".

## Using the kit's scripts instead of writing your own

The scripts exist so that the *expensive, generic* parts of this work — decoding a dex instruction at an
exact offset, recomputing a dex header in the right order, writing a 4-byte-aligned archive, resolving a
PLT stub, bursting screenshots with evidence attached — are not re-derived per task.

Re-deriving them is not neutral. A hand-rolled instruction decode that silently loses sync, or a
hand-rolled repack that quietly drops alignment, produces **a confident wrong answer**, which is the
exact failure class this skill exists to prevent. The cost shows up later, as a patch that "had no
effect" or an install refused with a bare numeric code.

**The rule: before writing a script, check whether one here already does it.** The index is in
`SKILL.md`; the entry points that matter most are `doctor.py` (what can run here),
`dex_find_insn.py` (get an exact offset instead of guessing one), `dex_patch_bytes.py` (apply and prove
an equal-length patch), `apk_diff.py` (prove your own build was surgical), `repack.py` (aligned rebuild)
and `snap.py` / `coldstart.py` (look at the screen with the evidence attached).

**When a script here is genuinely wrong, that is a finding to fix and report — not a reason to quietly
route around it.** Two live examples of the difference:

- A decoder utility in this kit carried an **opcode name/width table misaligned by one entry across
  `0x16`–`0x2C`** (23 rows). Everything decoding through that range **silently lost sync** and produced
  offsets that were plausible and wrong — no exception, no warning. It was found by comparing against an
  independent decoder and noticing a disagreement. **If two tools disagree, the disagreement is the
  product**; it is the cheapest bug signal in this domain and the easiest to throw away by picking the
  answer you preferred.
- Conversely, a *tool's* negative result is not a finding about the target (§the general trap below).
  Establish that the tool could have found the thing before recording that the thing is absent —
  especially for string searches, where an empty result is exactly what an unfound string looks like.

**Corollary for reporting.** "The kit's script X reported Y, and I cross-checked it against Z" is a
conclusion. "I wrote my own parser because the script was awkward" is a gap you introduced, and it
should be reported as one.

## "Not on PATH" is not "not installed"

`doctor.py` and `preflight.py` report whether each tool resolves on `PATH`. That
is a statement about `PATH`, not about the machine, and the difference has cost
real time: a full custom zip writer was built to work around a missing
`apksigner` that was already installed in an SDK directory nothing had added to
`PATH`.

**Before treating a tool as absent, search the filesystem once:**

```bash
# POSIX
find / -name apksigner -o -name zipalign -o -name baksmali.jar 2>/dev/null | head

# Windows (PowerShell) -- list every drive letter first, then search each
(Get-PSDrive -PSProvider FileSystem).Root |
  ForEach-Object { Get-ChildItem -Path $_ -Recurse -Depth 5 -ErrorAction SilentlyContinue `
      -Include apksigner.bat,zipalign.exe,keytool.exe }
```

Common places that are *not* on `PATH`:

| Artefact | Typical location |
|---|---|
| `apksigner`, `zipalign`, `aapt2` | any `build-tools/<ver>/` under an Android SDK, and portable tool bundles |
| `apksigner.jar` | inside those same directories (runnable as `java -jar`) |
| `keytool`, `jarsigner`, `javac` | a JDK install whose `bin` was never added to `PATH`; `java -XshowSettings:properties -version 2>&1 \| grep java.home` reveals the JDK root even when `keytool` does not resolve |
| `uber-apk-signer.jar`, `baksmali*.jar` | bundled with portable APK toolkits |

Record the resolved absolute paths once, in your running notes, and pass them to
the scripts that accept `--apksigner` / `--zipalign` / `--ks` style flags. Every
script in this repository takes an explicit path for this reason.

**A useful asymmetry:** missing `apksigner` is survivable (a v2-only signature
block can be appended without reordering the archive), but missing `zipalign` is
not a reason to hand-roll alignment either -- write the archive aligned in the
first place, as `scripts/repack.py` does. Prefer producing a correct archive over
repairing one afterwards: post-hoc alignment tools rewrite the file, which
changes every offset and can break a target that fingerprints its own layout.

## Signing: pick the signer deliberately

Two signers, and the choice changes the output bytes:

- **`apksigner`** (build-tools) appends the v2/v3 signature block after the zip
  content. It does **not** reorder entries, so a carefully aligned archive stays
  aligned. This is the default choice.
- **`jarsigner`** (JDK) rewrites the archive as a side effect of adding the v1 JAR
  signature, which recompresses entries and **destroys the alignment** that
  Android R+ requires. A build signed this way can fail to install with
  `Failure [-124] ... resources.arsc ... aligned on a 4-byte boundary` even though
  the same archive installed fine moments earlier, and `jarsigner -verify` reports
  success. If you have run `jarsigner` on an archive and a previously-working
  install starts failing, re-pack and sign with `apksigner` before investigating
  anything else.

Enable **v1 + v2 + v3**. v1 keeps very old devices working; v2/v3 are what modern
platforms actually verify, and v1-only builds are rejected in more configurations
than people expect.

## The general trap: a tool's failure is not a finding about the target

A missing jar, a version skew, a forged section header, and a genuinely absent symbol all produce
**empty or partial output**. The output looks the same; the conclusions are completely different.

Before reporting "there is nothing there", confirm the tool was actually capable of finding it:

- Did it read the file at all? (entry count, segment count, non-zero output somewhere)
- Does a **known-present** item show up? (search for something you already know exists — a symbol
  you saw in the dynamic table, a string you read in the hex dump)
- Would a different method see it? (byte pattern vs decoded scan)

**This is `pitfalls.md` P25 and P26 in tool form.** A self-built analyser that fails quietly reads
exactly like a clean target, and it removes routes from consideration for free.

## Working without a network

Assume nothing can be downloaded. What still works, in order of usefulness:

1. Tier 0 in full, plus the Python standard library — enough for structure, strings, hashing, and
   most ELF/dex parsing.
2. Whatever jars and binaries are already present. **Locate them once and reuse the paths** rather
   than re-searching on every command.
3. A local package cache or an offline mirror, if the environment has one.

If a tool genuinely cannot be obtained, say which step is blocked and **what a substitute would
give up** — do not silently substitute a weaker method and report its result as equivalent.

## Recording the toolchain actually used

When you report, name the tools and versions that produced each finding. Two agents with different
tool versions will reach different conclusions about the same binary, and without the version that
difference is unresolvable later.
