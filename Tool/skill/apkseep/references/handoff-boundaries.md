# Hand-off boundaries — where this skill ends and another view begins

Four boundaries that are easy to walk into without noticing. Each names what the other side owns
rather than restating it, because two copies of the same advice drift apart. `SKILL.md` keeps the
one-line version of each so a routing decision can be made without loading this file; this file
carries the detail.

## 1. JNI — a Java `native` declaration and its implementation are two different views of one function

This skill reads the Java side (dex) and the native side (`.so`) with different tools, so the *join*
is where analyses go wrong.

| Form | What you see | How to find it |
|---|---|---|
| Static linkage | symbol `Java_<pkg>_<Class>_<method>` in `.dynsym` | search the dynamic symbol table. Under R8 the class name is a short name, so the symbol deforms with it and a search for the readable original finds nothing |
| Dynamic registration | **nothing** in the symbol table — binding happens at runtime | find `RegisterNatives` call sites, or hook it to read the binding table. Obfuscated targets prefer this, and a symbol search fails **silently** on it |
| Native → Java callbacks | native code pulling data back through Java | follow `FindClass` / `GetMethodID` / `CallObjectMethod` |

`FindClass`/`RegisterNatives` in a `.so` tell you a JNI boundary exists even when no `Java_*` symbol
does. **Strength note:** the three rows above are documented behaviour, not results from the first
verification pass, which did not trace a JNI boundary end to end; `FlutterJNI.loadLibrary` appearing
in a dex is the closest it came. Treat them as a map, not as a measurement.

**The benchmark pass then measured the failure the middle row predicts:** a real dynamically
registering library contains **zero `RegisterNatives` symbols**, because the C++ `jni.h` inlines the
call — so a symbol-based search fails structurally, not by bad luck. The combination that did fire
on a real library was *"exports `JNI_OnLoad` and zero `Java_*`"*. The authoritative treatment is
`references/java2c-and-jni-sinking.md` §The JNI boundary — why a symbol search fails silently; this
section is the pointer, not the source.

## 2. Hardening — a dex-side packer observation is a native-side implementation question

If the dex turns out to be a shell, the logic is behind a loader and the analysis moves to the `.so`
that performs the unpacking. `packers.md` owns the dex-side identification; the native deep dive
belongs on the other side of this boundary. **Not exercised by the first verification pass** — that
target had no packer, so this pointer carries no measurement from it. The benchmark pass measured the
*shape discrimination* on public samples but still did not run a live extraction shell
(the benchmark matrix (`references/evidence-summary.md` §The capability matrix) row B3).

## 3. The existing native boundaries — read native anomalies from the APK side, not from inside

`native-and-so.md` and `native-tamper-and-suicide.md` are deliberately scoped to what you can
conclude *from the APK side*: a repacked build that dies instantly with a null-looking fault, a
Java-layer check that reports success while the process dies, a terminate path you made not-return.
That judgement belongs here, because it is about deciding whether your *patch* caused the death. Deep
native work — restoring a symbol, rebuilding a call graph, reversing an OLLVM function — is a
different activity with a different toolchain. Point across rather than duplicating: if you need the
latter, say so instead of extending those two files into it.

## 4. When the deliverable stops being an APK, the verification question changes with it

`SKILL.md` §What "done" means is written for a rebuilt, installable artifact, and every word of it
assumes one. The other three forms in G1 each move the evidence somewhere else, and the failure mode
is quiet: **a privileged result gets reported in the language of a finished build.**

| Form | What "verified" now means | What is *not* evidence |
|---|---|---|
| **LSPosed / Xposed module** | The module was loaded into the target and its hook produced an observable effect **in the target's own log**, on a named build of the target | The module installed; `pm path` returned a path; the package was enabled in the manager. All three are true of a module whose entry class does not exist in its own dex |
| **Local RPC / emulation service** | A call returned the value the app itself would produce, from a named target build and a named device or emulated environment — and the harness survives a reconnect | "The script loaded"; a call that returned *something* without a reference value to compare against |
| **Analysis report with a stated boundary** | The evidence chain (commands, outputs, and the layer each conclusion belongs to) plus the boundary — what was **not** determined and why | Any implication that a route was exhausted when it was only abandoned |

The privileged-form drift R1 warns about lives here. `references/lsposed-and-modules.md`,
`references/emulation-and-rpc.md` and `references/verification.md` each carry the specific check; this
table is the reminder that changing the deliverable's form is a decision that must be re-stated out
loud, not a quiet downgrade of what counts as done.

**A fifth boundary, added by the benchmark pass:** when the deliverable is a **tool or a document in
this repository**, "verified" means an independent check exists — a second implementation, an
official disassembler, a byte-exact round trip. A tool's own self-test passing is not that check.
the benchmark matrix (`references/evidence-summary.md` §The capability matrix) records which rows have one and which do not.
