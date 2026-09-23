# Java2C and JNI Sinking — the dex is not where the code is

Load this when the dex shows method bodies missing or replaced by `native` declarations, and
you are about to go looking for a decrypted DEX in memory. **Decide which of the two shapes you
have before you spend anything**, because one of them has no DEX to find at any point in the
process lifetime, and the search for it is unbounded.

Two neighbouring routes have historically folded this shape into one: `advanced-unpacking.md`'s
dump-shape table and the SKILL.md symptom index both point "whole classes are bare `native`
declarations" at `code-virtualization-and-custom-linkers.md`. That file is about protection which
leaves the code **reachable** — a private container, a loader, a private opcode interpreter, all of
which you can dump and measure. **Java2C is not reachable, because it was never bytecode.** This
file splits that row and owns both halves of it; the virtualization file stays what it is.

**Strength note, read this first.** The measurements below are **observed** — every number was
produced by `scripts/java2c_probe.py` against a real sample during this pass, recorded in
`references/evidence-summary.md` §The capability matrix. But no Java2C library exists in this repository and
none could be built here (no NDK, no clang, WSL unavailable — see that record), so **the
Java2C-specific identification criteria are inferred, not observed end to end**. What *is*
observed is the discriminating measurement that separates Java2C from JNI sinking, and the JNI
boundary behaviour. Treat the type table as a map; label your own conclusions the same way.

## The five shapes — one table, because the wrong row costs days

| Shape | Static shape in dex | What is in memory at runtime | Route | Cost of the wrong row |
|---|---|---|---|---|
| **Landing shell** | `Application` is a third-party class; dex is a small stub | A full, decrypted DEX | Dump memory, filter, patch | Cheap if you notice the stub `Application` |
| **Extraction shell** | Reads as a normal dex until you measure it; bodies are stubs | A DEX whose bodies are filled in **on invocation** | Dump, measure `stub%`, FART-style active invocation | Medium — you keep dumping, and every dump is a skeleton |
| **VMP** | Dex parses; bodies are *present* but decode as nonsense | A DEX containing **private opcodes** interpreted by a native VM | Measure, then usually stop and report | Medium — recovery cost usually exceeds task value |
| **Java2C** | Whole classes are `native`; **no code_item at all** for them | **Never a DEX.** The translated methods exist only as compiled C in a `.so` | Read the `.so`; rebuild the JNI call chain | **Highest in this table** — you hunt a decrypted DEX that is never produced, then blame your dump tooling, then your anti-detection assumptions |
| **JNI sinking** | A handful of `native` declarations; the rest of the dex is ordinary Java | A normal DEX | Locate the Java call site; reverse one or a few native functions | Low — but you may widen the job to the whole app if you read it as Java2C |

The one question that decides the table: **does the artifact ever hold dex bytecode for the
methods you care about?**

- Landing shell, extraction shell, VMP: **yes** — the bytecode is there, in some state, and the
  work is recovering or interpreting it.
- Java2C: **no** — a translated method is a `native` declaration plus an entry in a registration
  table. Nothing is decrypted, so nothing can be dumped. `[inferred]` as a runtime claim: it
  follows from the translation mechanism, and this pass did not observe a live Java2C app.
- JNI sinking: **yes** — the dex was never damaged.

## Identification

### The discriminating measurement is native density

This is the single most useful number and it separates the two shapes by roughly three orders of
magnitude. Measured on real samples with `scripts/java2c_probe.py` `[observed]`:

| Sample | dex methods | `native` methods | native ratio |
|---|---|---|---|
| JNI-sinking target A (MASTG L2) | 5081 | 2 | **0.04 %** |
| JNI-sinking target B (MASTG L3) | 11182 | 3 | **0.03 %** |
| App carrying a real JNI library | 23603 | 7 | **0.03 %** |
| Java2C-shaped fixture | 29 | 24 | **82.76 %** |

A JNI *sink* is by definition surgical: a few hot methods are moved out and the rest of the app
stays in Java. **A JNI sink is not "the app is native".** When the density is in the tens of
percent, and whole classes have zero Java methods left, you are looking at a translation pass.

`[observed]` in the same runs: two of the fixture's three classes were native-dominated (>= 70 %
of >= 3 named methods), against **zero** such classes in any of the three real targets. Note that
constructors are excluded from that test — a translation pass leaves `<init>`/`<clinit>` in Java
in practice, so "every method native" is an essentially unreachable test and should not be used.

### Native-layer signatures

| Evidence | Strength | Why |
|---|---|---|
| `.so` exports `Java_*` symbols whose count is roughly 1:1 with the dex native-method count | **strong** | Measured 2:2 (sample A) and 3:3 (sample B) `[observed]`. It is the signature of a *static-linkage* translation or sink. Note it does **not** distinguish Java2C from JNI sinking — only the density does |
| The `.so` contains one C function per Java method, each beginning `JNIEnv *env, jobject thiz, ...` | **strong** | Observed in generated, uncompiled output: every translated method became exactly one function with those leading parameters |
| Toolchain strings: `Dex2C`, `dynamic_register_compile_methods`, `ScopedLocalRef`, `well_known_classes` | **strong** | These are the runtime header and entry-point names a Dex-to-C toolchain emits. `[observed]` in generated sources; `[inferred]` that they survive compilation into the shipped `.so` |
| `JNI_OnLoad` present | **weak** | Present in nearly every JNI library. Measured true on a system library with zero `Java_*` symbols `[observed]` — it told us registration was dynamic, not that anything was hardened |
| `RegisterNatives` **string** anywhere in the `.so` | **weak** | See the boundary section: NDK's C++ headers do not emit this symbol at all |
| `libc++_shared.so` / `c++_static` | **weak** | An ordinary NDK C++ setting. The Dex-to-C toolchain read here does ship `APP_STL := c++_static`, but so do countless unrelated libraries `[observed]` |
| `classes.dex` byte-count per class far below the app's own pre-hardening build | **weak, uncalibrated** | Bodies leaving the dex should shrink it. Measured 584 B/class on the fixture versus 1152–1386 B/class on the real Java targets `[observed]` — but there is no population baseline for "normal", so this only compares an app against **itself** before and after |

`java2c_probe.py` prints every one of these with its strength attached, and prints the weak ones
as an explicit warning block. A weak hit is not a verdict and must not be reported as one.

## The route: read the .so, not memory

For Java2C the analyst's instinct — dump memory and find the dex — is not merely expensive, it is
**unbounded**, because the success condition can never occur.

1. **Do not dump.** There is no target artifact. If you dump anyway, you will recover a dex that
   still shows the same `native` declarations you started with, and the natural (wrong) reading is
   "the dump failed".
2. **List the translated functions.** With static linkage, `Java_<PKG>_<Class>_<method>__<proto>`
   names map the `.so` back onto the dex one for one. Use the dex as the index and the `.so` as
   the library.
3. **Rebuild the chain backwards.** A translated function calls *out* to Java constantly. The
   strings `FindClass` / `GetMethodID` / `GetStaticMethodID` / `Call*Method` / `NewObject` /
   `GetFieldID` inside it are the reverse edges. Following them reconstructs what the original
   Java method did, which is the only way the logic comes back.
4. **Expect a register-machine shape.** Generated code declares a slot per dex register up front
   and assigns them in sequence. Reading it as if a human wrote it wastes hours; read it as a
   linearizer output, matching each call site against the JNI signature it passes.

The decompiler choice matters less here than for obfuscated code: the generated functions are
long but flat and unoptimized, which is precisely the shape a decompiler handles well.

## The JNI boundary — why a symbol search fails silently

Two independent mechanisms erase the symbol that a reader would search for. Both are real; the
second was measured this pass.

**1. Dynamic registration.** Nothing named `Java_*` is exported. Binding is performed at runtime
by a registration table built in a JNI entry point. A grep over the symbol table returns nothing,
exits zero, and looks like a legitimate answer.

**2. `-fvisibility=hidden`, and an inline `RegisterNatives`.** The Dex-to-C toolchain read here
ships `APP_CPPFLAGS += -fvisibility=hidden` in its `Application.mk` `[observed]`, which hides the
generated functions from the dynamic symbol table — so even a statically-named translation can
present as "no `Java_*` symbols". Compounding it: NDK's C++ `jni.h` implements `RegisterNatives`
as an **inline member that calls through the function table**, so calling it emits *no*
`RegisterNatives` symbol either `[observed]`: a real system library exporting `JNI_OnLoad` and
zero `Java_*` symbols contains zero literal `RegisterNatives` symbols. A rule that greps for that
name is structurally incapable of firing.

**The check that does work** `[observed]`: a library that **exports a JNI entry point and exports
zero `Java_*` symbols** is registering dynamically. That combination is affirmative evidence, and
it fired on a real library in this pass.

**Confirming it at runtime.** Hook the registration entry point (`JNI_OnLoad`) and read the table
it builds, or hook the class-load path and enumerate the class's methods' native backing. Do not
conclude "no JNI boundary" from an empty symbol table; conclude "the binding is not visible in the
symbol table" and go find where it happens.

## Failure modes

| What you see | What it is not | What it is |
|---|---|---|
| Whole classes are `native`, you dump memory and find the same `native` declarations | "The dump failed" / "the tool is broken" | The translation moved the code out of dex permanently. Re-read the dex shape and open the `.so` |
| `grep Java_ .dynsym` returns nothing | "There is no native implementation" | Dynamic registration, or hidden visibility — see the boundary section |
| A library exports `JNI_OnLoad` and nothing else you recognise | "It is a loader" | It may be an ordinary dynamically-registering JNI library. A loader normally also has an `init_array` entry and a payload to map |
| Native density is high but every class still has Java methods | Java2C | Could be a JNI sink applied widely, or an R8-stripped app. Check whether the `native` methods have matching `Java_*` symbols before concluding |
| The dex looks completely unremarkable on a sample you were told is hardened | "Nothing is hardened" | A VMP whose payload is decrypted at runtime has an ordinary static dex. Measured this pass: a VMP-labelled sample had 7 native methods out of 23603 and a 4 % stub ratio `[observed]`. **Static dex metrics cannot see runtime-only hardening** — that needs a runtime check, not more reading |

## Where this file stops

- **It does not decompile the generated C.** That is ordinary native reversing; `native-and-so.md`
  and `native-dbi-and-deobfuscation.md` own it.
- **It does not recover a VMP.** Private-opcode interpretation is a different mechanism with a
  different cost model (`advanced-unpacking.md`).
- **The Java2C runtime claim is inferred.** That no dex bytecode exists in memory for a translated
  method follows from the mechanism, not from a measurement made here. If you get a live Java2C
  sample, that is the first thing to verify, and it is cheap: attach, force the class to load, and
  ask whether the method resolves to Java bytecode or to a registered native entry.
