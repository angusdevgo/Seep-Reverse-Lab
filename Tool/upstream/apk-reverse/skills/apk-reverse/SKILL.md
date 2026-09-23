---
name: apk-reverse
description: "Reverse engineer, debloat, de-ad, patch, or re-sign Android APKs, and analyze their runtime and server-side behaviour. Use for an .apk/.aab/.dex/.so sample, smali or dex patching, Frida hooking, repacking, ad or SDK removal, API probing, or deciding whether a client-side patch can work. Covers recon, anti-tamper, membership limits, surgical dex patching, repack pitfalls, device setup, and a failure catalogue."
license: MIT — see LICENSE at the repository root
compatibility: "Python 3.9+. Device work needs adb; dynamic analysis a matching frida-server; re-signing zipalign plus apksigner, not just a JVM. Static dex/ELF work and the leak scanner are offline. Run doctor.py --json for status."
metadata:
  version: "1.0"
  capability_registry: skills/apk-reverse/scripts/capabilities.py
  evidence_summary: skills/apk-reverse/references/evidence-summary.md
  last_reconstruction_pass: "2026-09-22"
  strength_labels: "observed | inferred | unverified"
---

# APK Reverse Engineering & Patching

Goal: reach a **verified, installable, still-working artifact** fast — and avoid the whole class of
mistakes that destroy an APK while looking completely healthy.

## Immediate — do these four things before anything else

This file is a **procedure with gates**, not background reading, and it is long enough that its middle
gets skimmed. So the four moves come first; everything below is the explanation for them.

**1. Classify before choosing a route.** Answer the thirteen questions in §Start here. **R4** decides
whether you are editing the right layer at all, and a wrong branch does not fail loudly — it produces
an artifact that builds, runs, and does the wrong thing.

**2. Clear the four gates, in order, with their pass criteria** (§Gates). G1 names the deliverable form
in one testable sentence *before* any work; G2 establishes what this machine can really do; G3 locates
the code; G4 records the baseline and the control. "I understand the idea" is not clearing a gate.

**3. A symptom you cannot explain is a stop signal, not a puzzle.** Search §Symptom index for the shape
**before your next attempt** and load the file that row names. Those rows exist because each one cost
hours — and in several cases the answer was already written down while it was being re-derived.

**4. Two strikes on one shape of attempt sends you back to classification**, not to a third variant
(§Stop conditions). And **never report done without the six items in §What "done" means.**

**Two rules about this file itself.** When a failure does not fit your plan, the symptom index is the
next action, not more reasoning. And when this file and your own reasoning disagree, **this file wins**
until you have evidence that overrides it: every rule here is the residue of a failure that cost
hours, and your current intuition is the intuition of someone who has not hit it yet.

## Four rules that override everything else

**R1 — Write the deliverable as a testable sentence before you touch the target.**
"It works" is not the goal; "it works under the stated constraint" is. Root-assisted, live-
instrumentation, host-proxy and patched-device results frequently do **not** satisfy a request for an
installable artifact that works on a normal phone — and it is easy to present such a result as
finished. Write the sentence, re-read it at every checkpoint, and if you cannot meet it, say so
plainly and label the privileged workaround a **fallback**, never the deliverable.
→ `references/long-task-discipline.md` §the most expensive drift

**R2 — Change one variable at a time, and keep a control build.**
An experiment that flips two things teaches nothing when it fails, and a failure you cannot attribute
will be attributed to the wrong cause. Every "the app rejects X" claim needs its own run, and every
patch needs a same-pipeline control that still fails the old way.
→ `references/long-task-discipline.md` §single-variable discipline

**R3 — Never ship or claim an unverified artifact.**
"It assembles" is not "it works"; "the process started" is not "the feature works"; "no error in the
log" is not "the check is gone". Install it, launch it, exercise the exact feature you changed, and
look at the screen. Prove the device is running the build you made — hash it, do not trust the
filename.
→ `references/verification.md`

**R4 — Identify the owning layer before patching, and re-classify when reality disagrees.**
Ads, paywalls, feature gates, integrity checks and update gates live in different layers (Java, dex,
native, Dart/Unity, server). Patching the wrong layer either does nothing or breaks the app. If a
patch "had no effect", the diagnosis was wrong — go back to classification instead of patching harder.
→ `references/recon.md`, then the layer-specific file the symptom index points at

## Tooling — reach for the right instrument, and check before declaring it absent

Most wasted rounds in this domain are not bad reasoning about the target. They are **the right question
asked of a tool too weak to answer it**: an hour of `grep` over a hand-exported smali tree where one
indexed query would do, a manual ELF walk where a decompiler was one `pip install` away. The failure is
invisible from the inside, because the weak route still produces output.

**Five obligations. These are instructions; a violation is a defect, not a preference.**

| Obligation | Do this | Cost of ignoring it |
|---|---|---|
| **Orient with an indexer, not an export** | Build the ability to *ask the artifact questions* before reading code: `droidasc findrefs` / `ddc findrefs` (string/type/method → every reference site, sub-second). A decompile reads a class you have **already located** — it is not how you locate it. `jadx` is a readable viewer of last resort, never the source of truth and never the entry point of a recon | hours of `grep` per question asked, over an export you paid for first |
| **Install the missing tool; it is part of the task** | A missing arm64 decompiler is the next step, not a constraint to route around. Ask a human only when installation is genuinely impossible | hours re-derived by hand for output a decompiler gives in minutes |
| **Name the gap before spending against it** | State the capability the blocker requires and whether this machine has it, **out loud**. This is a G2 item | designing around a tool that installs in ten minutes |
| **Reach for a shipped script before writing one** | Parsing, hashing, alignment and hot-plug probes are already written; a bespoke script in place of `scripts/dex_find_insn.py` is how offsets get **guessed instead of computed** | a wrong offset that decodes cleanly and behaves wrongly |
| **Pick the instrument for the layer the question lives on** | A dex in memory wants `dex_mem_scan.py` (find and cut) **plus** `dex_dump_validate.py` (judge), not a decompiler pointed at a fragment. An algorithm you only have to *call* wants `emulation-and-rpc.md`. "Does this class ever load at runtime" wants a hook that fires or does not | the heavier tool is not the safer one — it produces a *plausible* answer, which is worse than none |

**Run `python skills/apk-reverse/scripts/doctor.py --json` before concluding anything is unavailable.**
It reports per-capability closure — what is missing, what to install, and roughly how long that takes —
and a capability you have not checked for is not a capability you lack. **It is deliberately allowed to
report `BLOCKED`:** a machine with a JVM but no `zipalign`/`apksigner` cannot re-sign, and the report
says so rather than inferring capability from a tool that is merely present. Detail:
`references/toolchain.md`; the registry it reads is `scripts/capabilities.py`.

## Coverage — what this skill claims, and what it does not

The failure this section prevents is not ignorance. It is **a confident wrong answer produced by
applying the nearest available procedure to a target it was never written for.** A documented method
that almost fits is more dangerous than no method at all, because it arrives with a plan, a
vocabulary and a set of reassuring numbers.

**How strong these claims are — this is load-bearing, not cosmetic.** Every claim in this skill carries
one of three labels, and you must label your own results the same way:

| Label | Means | May it justify a decision? |
|---|---|---|
| `observed` | a command was run and its output exists | yes |
| `inferred` | follows from an observation, but the step is reasoned | provisionally |
| `unverified` | assumed, or reported elsewhere and never reproduced here | only as something to test |

**The inventory that replaces a guess:** the per-route list of what is covered and what is not — by
verified mechanism versus by documented-but-mostly-inferred route — is in
`references/coverage-and-limits.md`. Load it when the question is "can this skill actually do X".

**Partial coverage that is easy to over-read** — these are documented routes whose *dependency* this
skill does not ship, and each has a fence around it in the same file: Dart AOT analysis needs a
snapshot dump you must obtain elsewhere and naming the front end matters · extraction-shell recovery
stops at the VMP boundary · a Stalker trace is not guaranteed on every device · a kernel-side answer
requires a module this skill only scaffolds.

**Not covered — say so rather than improvise:** Unity / IL2CPP · React Native / Hermes / Cordova ·
iOS · defeating a server-side authority · an off-the-shelf unpacker or an anti-detection arms race ·
building and shipping a kernel module. Reasons and evidence boundaries are in
`references/coverage-and-limits.md`; **silence in that record is not support.**

**The fallback, as an instruction — this is a rule, not advice.** If the target does not match the
covered list, or no symptom-index row matches, then **stop and classify before choosing a branch**:
answer the thirteen questions (§Start here). If the shape still does not fit — an unknown runtime, a
mechanism you cannot name — **say exactly that and propose the cheapest experiment that would
identify it.** Do not take the closest documented route and apply it anyway. A wrong branch here does
not fail loudly: it produces an artifact that builds, runs, and does the wrong thing.

## Hand-off points — where this skill ends and another view begins

Four boundaries that are easy to walk into without noticing. Each names what the other side owns
rather than restating it, because two copies of the same advice drift apart. The JNI form table and
the per-form verification table live in `references/handoff-boundaries.md`.

1. **JNI** — a Java `native` declaration and its implementation are two views of one function, and
   this skill reads each with a different tool. A symbol search fails **silently** on dynamic
   registration. Authoritative treatment: `java2c-and-jni-sinking.md` §The JNI boundary — why a
   symbol search fails silently.
2. **Hardening** — a dex-side packer observation is a native-side implementation question.
   `packers.md` owns the dex-side identification; the deep dive belongs on the other side.
3. **Native anomalies** — read them *from the APK side*, because the judgement is whether your patch
   caused the death. Restoring a symbol or reversing an OLLVM function is a different activity with a
   different toolchain: point across instead of extending `native-and-so.md` into it.
4. **Deliverable form** — when the artifact stops being an APK, the verification question changes with
   it. G1's other three forms each move the evidence somewhere else, and the failure is quiet: a
   privileged result reported in the language of a finished build.

## Symptom index — a matching row is a stop signal

You arrive at a symptom, not at a file name. Each row below is a failure that has already been paid
for. **If any row matches what you are observing, load the file before your next command** — not after
your next three attempts. Reasoning from first principles at this point is how the same hours get
spent twice; more than one entry here is a lesson that was re-derived by hand while the answer sat
unread in this repository.

| What you observe | Load first |
|---|---|
| A repackaged/re-signed build **dies before your code runs**; `SIGSEGV`, all registers zero, `pc=0`, `fault addr` near `0x0` | `native-tamper-and-suicide.md` (deliberate crash), then `code-virtualization-and-custom-linkers.md` |
| **No packer** (Application is the app's own, dex readable) **and it still dies** | `code-virtualization-and-custom-linkers.md` §a loader is still a possibility; but if the same build also dies on a *second, unrelated* device you are looking at an ordinary startup fault, not a hardened one |
| The app dies at startup on **every** device, packed or not, with **no tombstone** while `crash_dump` says `already traced` and logcat says `exited cleanly (0)` | a bundled crash reporter has taken the signal handlers, so the platform's own trail is gone. Frida spawn-gating is the recovery route |
| A `FORTIFY: pthread_mutex_lock called on a destroyed mutex` abort in a Flutter app, on the **main** thread, before the first frame completes | `dart-aot.md` — check `libapp.so` is actually being loaded; Flutter's engine bootstrap is the usual place a native lifecycle fault surfaces |
| Log says a **Java-layer** signature/integrity check **passed**, yet the process dies | `code-virtualization-and-custom-linkers.md` §a Java-layer "signature killer" is a decoy |
| Deleting a library fixes validation but yields `UnsatisfiedLinkError: dlopen failed: library "X" not found` | `code-virtualization-and-custom-linkers.md` §the deadlock that eats hours |
| Whole classes appear as bare `native` declarations with no body | `java2c-and-jni-sinking.md` — read it **before** dumping memory: if this is Java2C there is no DEX to find, at any point in the process lifetime. A handful of `native` methods in an otherwise ordinary dex is JNI sinking, not this |
| A `Java_*` search over a hardened library returns nothing at all | `java2c-and-jni-sinking.md` §The JNI boundary — why a symbol search fails silently — dynamic registration, or `-fvisibility=hidden`. The check that works is "exports `JNI_OnLoad` and zero `Java_*`" |
| You are about to publish an evidence file, a transcript or a README that quotes real work | `references/desensitization-and-leak-scans.md` — run `scripts/scan_leaks.py` **before** it is committed; the hit list is a set of lines to look at, and `--show-exempt` is where the wrong suppressions show |
| A hooking module appears to have run but its log tag is silent, and you are about to record "it never loaded" | `references/precedents/logd-broken-module-never-ran-case-3.md` — a broken `logd` delivers nothing on `logcat` while the module's whole run sits in LSPosed's file log; read both channels |
| A library's **SONAME does not match its filename** | `code-virtualization-and-custom-linkers.md`, `native-and-so.md` |
| Your edit had **no effect at all**, with no error | `server-config-and-updates.md` §3 (the value may be server-sent), then `packers.md` §map the validation boundary |
| Process **hangs** with no crash record, or dies to a `uid 0` killer | `native-tamper-and-suicide.md` §the rule (you probably made a terminate path *not return*) |
| Death looks like an ordinary null dereference in a hardened library | `native-tamper-and-suicide.md` §deliberate-crash stubs |
| The app dies **only while you are attached/rooted** | `detection-and-anti-analysis.md`; run the unmodified original under identical conditions first |
| **Install fails with `[-124]` and mentions `resources.arsc` / alignment** | `repack-and-sign.md` §2a — STORED **and** 4-byte aligned, both required |
| **Install fails with a bare numeric code (e.g. `[-99]`) and no `INSTALL_FAILED_*`** | `repack-and-sign.md` §vendor install interception — a device-side interceptor, not your build. Use the root `pm install` path |
| **After an install, `am start` does nothing / screenshots show another app / `am start -W` hangs** | `repack-and-sign.md` §the installer may still own the screen |
| Log shows `Failure to verify dex file ...: Bad checksum` and a startup `ClassNotFoundException` for an ordinary class | `byte-level-patching.md` §the dex header has two integrity fields — order matters |
| An install "succeeded" but nothing changed, or the version did not move | `long-task-discipline.md` §keep the observation window clean |
| Evidence contradicts itself, or a capture looks like two states mixed | `long-task-discipline.md` §keep the observation window clean |
| You took screenshots but drew the conclusion from logs or from the patch itself | `long-task-discipline.md` §captures you never looked at are not evidence |
| You are about to re-run an experiment whose result you already recorded | `long-task-discipline.md` §long-context decay |
| A script will not start, or a tool "is missing" | `scripts/doctor.py`, then `toolchain.md` §"not on PATH" is not "not installed" |
| A hook or probe reports **no events at all**, and you are about to call it detection | `scripts/anti_detect_probe.js` for the environment self-report first, then `detection-and-anti-analysis.md` §Step 3: locating the check — the order of search from Stage 0 |
| `attach` hangs and then fails **while the process is still in `ps`** | `detection-and-anti-analysis.md` §Step 3 Stage 0 — check for `D` in `/proc/<pid>/stat`, and attach a *different* pid as a one-line control before blaming the target |
| The app exits with no tombstone, no crash and no ANR record | `detection-and-anti-analysis.md` §Step 3 — a clean self-exit means the check ran before your hooks existed; the branch conditions there say which Stage |
| A dump region validates as the wrong thing, or an `r--s` view of `base.apk` looks like a dex | `advanced-unpacking.md` §What this route cannot do, and how to tell before you spend the window |
| Feature-scoped network failure (login/register/pay) while the rest works | `tls-and-cert.md` — do not assume your patch caused it |
| Everything works but **every signed request fails** after repack | `signature-derived-keys.md` |
| A re-signed build **runs fine, renders its whole UI and logs no error — but one feature silently never loads**, and `dumpsys`/DNS/logcat show **no request for it at all** (not a rejected request: *no request*) | `code-virtualization-and-custom-linkers.md` §what the native check actually reads — refusing **before** the request is built. Not the row above: "sent and rejected" and "never sent" have different owners |
| You cannot tell whether a missing feature is **your patch's fault or the target's own behaviour** | `long-task-discipline.md` §single-variable discipline. Run the **zero-change control through the same pipeline**, and the decisive variant: the unmodified original with the patch applied **in memory only**, same device, same network |
| Under Frida `spawn`, the UI never appears — `mCurrentFocus` stays `null`, screenshots come back blank, the Activity stack never builds | `dynamic-frida.md` §spawn keeps the Activity stack down: write the patch into memory, **detach**, then start the Activity normally |
| `frida-server` keeps disappearing mid-experiment, or the device reboots itself while you are working | `dynamic-frida.md` §when the ROM hunts your instrumentation |
| Ads still appear after a patch that should have killed them | `server-config-and-updates.md` §6 (cached config / remote re-enable), then `ad-removal.md` §step 4 (count the SDK's own log lines; n -> 0, not "I did not see it") |
| A forced-update or "must update" gate blocks the build | `updates-and-forced-upgrade.md` §step 6 |
| The dialog is gone but the feature is still locked | `membership-and-limits.md` / `account-gates.md` — decide server vs client authority before patching again |
| You are about to discard a route as "blocked" | `packers.md` — re-read it before writing any route off; mis-attributed failures have removed viable routes for hours |
| The task has run long and you are unsure what is already proven | `long-task-discipline.md` §keep a live record |
| A dumped dex parses in full, the classes are all there, and most method bodies are `return-void` stubs or nop fills | `references/advanced-unpacking.md` — an extraction shell: measure the `stub%` with `scripts/dex_dump_validate.py` before trusting any of it, and know that recovering the bodies is a different route |
| Your `frida` dump dies mid-write (`script has been destroyed`), or the process you are dumping keeps changing pid | `advanced-unpacking.md` §dumping when frida is refused — rule out memory pressure first; a reclaim-and-relaunch needs no instrumentation |
| A repack is refused by several independent checks, or the build has to keep working through store updates | `references/lsposed-and-modules.md` — deliver a module instead of an APK; G1's form table says when |
| A hook module is installed, enabled and scoped, yet its log tag never appears — and you are about to conclude it never ran | `lsposed-and-modules.md` §Deploy, enable, and verify — **a `logcat`-only verdict has already been wrong here**: on one ROM `logd` is broken and output reaches only `/data/adb/lspd/log/modules_<ts>.log` |
| A module's entry class is missing from its own dex (so it can never load), yet the package installs, enables and looks healthy | `references/lsposed-and-modules.md` — check `assets/xposed_init` against the dex's actual classes; installation is not evidence of anything |
| You only need to **call** the target's own routine (sign, token, encrypt) rather than change the app | `references/emulation-and-rpc.md` — emulate it, or service-ify the live function over Frida RPC |
| A native function is a many-thousand-line `switch` state machine, or the decompiler's output is meaningless | `references/native-dbi-and-deobfuscation.md` — OLLVM shapes, a Stalker trace, and how far a trace actually gets you |
| `Stalker.follow` installs but no events arrive, or following a hot libc export crashes the process | `references/native-dbi-and-deobfuscation.md` §6 failure modes — this repository measured both |
| The traffic is protobuf/gRPC/QUIC, or a proxy sees TLS but requests still fail on a Flutter app | `references/protocol-reverse.md` — schema-less protobuf, frame capture, and native-side pinning |
| Userspace hooks land and the app still dies: the check reads `/proc/self/status` through a raw `svc`, or runs before `JNI_OnLoad` | `references/kernel-and-environment-hardening.md` — what the next layer up and down can actually do, and when to stop |
| You must edit, repack, sign or inspect the APK **from the phone itself** | `references/on-device-tooling.md`, `scripts/mt_mcp_probe.py` |
| A captured body decodes to nothing readable, or you cannot tell whether a length-delimited field is a string, a nested message or a packed array | `protocol-reverse.md`. Protobuf on the wire (measured) — run `scripts/protobuf_decode_raw.py`; the candidate list and its `tie:` lines are the answer |
| Method bodies are present but decode as **private opcodes**, and you need the mapping rather than an explanation of why VMP is hard | `vmp-differential-analysis.md`, then `advanced-unpacking.md` for the shape diagnosis |
| A store build arrives as `base.apk` + `split_config.*.apk`, or a rebuilt build is refused **as a set** although every file verifies on its own | `split-apk.md` — one keystore across every member for `pm install-multiple`, and check that a merge is legal before trusting a merged single APK |

## Gates — clear these before you patch, in order

Each gate is an **action with a pass criterion**. Do not proceed past a gate you have not cleared, and
do not treat "I understand the idea" as clearing it. Skipping a gate is not a shortcut; it is how the
work gets redone.

**G1 · Deliverable form — and the cost ceiling on it.** State, in one sentence you could hand to
someone else, what artifact must exist at the end and under what constraints (rooted or not,
installable on a stock device or not, must survive updates or not, online or offline). *Pass:* the
sentence names a testable constraint, not an activity. *Fail:* you are solving a problem in an
environment the deliverable will never see.

Then name the **form** that sentence implies. "A rebuilt, self-contained APK" is only one of four, and
this is where the choice belongs — not after the repack has already failed:

| Form | Right answer when | What it costs you |
|---|---|---|
| **Rebuilt, installable APK** | The client owns the behaviour; no multi-point integrity check; no extraction shell | Repack, re-sign, and a device to verify on |
| **LSPosed / Xposed module** | The logic is client-side but the app fights repacks (multi-point signature checks, shell self-verification), or the result only has to work on rooted devices you control | A rooted device, module scaffolding, and an app that must not detect the hooking framework → `references/lsposed-and-modules.md` |
| **Local RPC / emulation service** | You do not need to change the app — you need to **call** it: a signing routine, a token, an encryption function | A live device or an emulated loader plus a call harness → `references/emulation-and-rpc.md` |
| **Analysis report with a stated boundary** | The authority is server-side, or the target is a real VMP / extraction shell whose recovery cost exceeds the value of the task | Nothing ships — and that is the honest answer, not a failure → `references/advanced-unpacking.md`, `references/server-api.md` |

*Decision trigger for leaving the first column:* switch off "rebuilt APK" as soon as the evidence shows
**(a)** more than one independent integrity check that must all pass, **(b)** an extraction shell whose
method bodies exist only at invocation time, or **(c)** any body that decodes as private opcodes. At
that point the repack route is not merely expensive — it is blocked, and the deliverable sentence
should say which form replaced it. **A form chosen here and re-read at every checkpoint is the guard
against the most expensive drift in this skill** (`references/long-task-discipline.md`).

**G2 · Environment truth and capability inventory.** Run `scripts/doctor.py` (and `scripts/preflight.py`
if a device is in play). *Pass:* you know which toolchains and scripts can actually run here, you have
seen the environment warnings — clock skew, leftover `adb forward`/proxy, a device-side frida process
already running, a tool installed off-PATH — **and you have written down the capability this target will
demand against the capability this machine has.** Name the two or three layers the task will almost
certainly reach (for example "arm64 native decompilation", "Dart AOT snapshot dumping", "device-side
TLS inspection", "dex-wide cross-referencing") and mark each available / missing-but-installable /
genuinely out of reach. *Fail:* you are about to attribute to the target a failure caused by your own
setup — or to spend a day routing around a tool that installs in ten minutes. A layer whose tool is
missing is a **task item**, not a constraint to design around. → `references/toolchain.md` §Closing a
capability gap

**G3 · Code location.** From the manifest and dex, answer: is there a packer, where does the app's own
code live (dex / native / Dart / Unity / server), and is any of it virtualized to native. *Pass:* you
can name the class that owns the behaviour you intend to change, or you have an explicit plan to find
it. *Fail:* you are about to patch a layer you have not located. If recon says "no packer", still
check the virtualization shape — see the index rows above.

**G4 · Baseline and control.** *Pass:* you have a control run — the unmodified original, or a
zero-change repack through the same pipeline — and you have recorded the observed failure (including
**time-to-death**, if it dies). *Fail:* when the patched build misbehaves you will have nothing to
compare against, and every later measurement is unfalsifiable.


## Start here: classify the target in thirteen questions

**Answer these before touching a tool — all thirteen, in order. Each one changes the whole plan, and
a wrong answer here does not fail loudly: it produces an artifact that builds, runs, and does the
wrong thing.** The answer column names both the action and the file that owns the detail; load that
file before acting on the question.

| # | Question | What the answer changes | Load |
|---|---|---|---|
| 1 | **Is the app packed/hardened?** Read the manifest's `application android:name` | A third-party shell class rather than the app's own Application means you have a packer and must handle it **first** | `recon.md` |
| 2 | **Where does the behaviour actually live?** — ad SDK · **server-issued config for client-rendered UI** · membership/VIP · feature flag or debug switch · anything decided by an API response | Client-side and removable, versus server-supplied data the client decides with, versus server-authoritative where a client patch is cosmetic. **Decide this early**: hunting an ad SDK that does not exist costs hours, and the server-config shape has no SDK to find | `ad-removal.md`, `server-config-and-updates.md`, `membership-and-limits.md`, `server-api.md` |
| 3 | **Is the app's own code in plain dex, or moved to native / Flutter / Unity?** | Which toolchain the whole task uses. **Cheap runtime check before committing:** hook the obvious Java classes for the UI you care about and reproduce that UI. Hooks that fire mean Java owns it; hooks that fire **zero times** while the UI is plainly on screen mean the runtime or native code draws it, and a dex-only plan will stall. Do not keep hunting in dex after a zero-hit probe — the most expensive wrong turn in this skill's history | `recon.md` §Where does the app's own code live, `framework-runtimes.md` |
| 4 | **What must the deliverable be able to do?** Write it as a testable sentence and re-read it at every checkpoint | The most expensive drift in this skill: a runtime-only result (data edit, live hook, blocked hostname, host proxy) looks like success while failing the requirement. The axes: **privilege** (unrooted?), **modification form** (rebuilt artifact vs live instrumentation), **ABI/device class**, **network**, **persistence**, **distribution** (self-contained?). If the evidence already shows a deep extraction shell, a VMP, or more than one independent integrity check, **re-answer against G1's four forms** — the repack column may be blocked, not expensive | `long-task-discipline.md` §the most expensive drift |
| 5 | **Does the app verify its own signature, or does the server?** | App-side means you must bypass it; server-side means re-signing silently breaks the app later | `repack-and-sign.md`, `server-api.md` |
| 6 | **What is your device situation?** — rooted real device, rooted emulator, or no device | Whether Frida is usable at all, and whether the deliverable can be tested where it will run. **Run `scripts/preflight.py` before your first experiment** and again whenever a failure surprises you — device state, a dead device server, a leftover proxy and clock drift all masquerade as a broken patch | `environment.md`, `pitfalls.md` P9 |
| 7 | **Which architecture is actually executing?** | `getprop` reports what the device claims and `primaryCpuAbi` what the package manager chose — **neither is what runs**. Only the live mapping is ground truth. An unmapped library, a translator in play, or a different ABI than assumed changes the plan more than any patch will | `native-and-so.md` §Cross-architecture, `scripts/lib_map.py` |
| 8 | **Is one *specific* feature failing at runtime** (login, registration, payment, an API-backed screen) while the rest works? | A feature-scoped network failure is very often a **TLS/certificate problem on one code path**, not your patch. An app can carry two independent trust chains, so "other requests work" proves nothing. Rule this out in minutes before hunting a signature check | `tls-and-cert.md` |
| 9 | **Was the input a build you did not produce** (a circulating "cracked"/"modded" APK)? | Such builds are frequently re-protected — sometimes with *more* layers than the original — and may carry injected components or endpoints. **Never use one as a patching workbench** | `third-party-builds.md` |
| 10 | **Does the client sign its requests with its own signing certificate?** | Grep for `toCharsString()` / `signatures[0]` / `getPackageInfo(..., 64)` **before the first repack**. If that value feeds a native HMAC/DES routine, the rebuilt APK must hardcode the *original* certificate value at every read site, or every signed request fails while the app still launches and looks healthy. The single most expensive silent failure in a repack, and 15 minutes of grep prevents it | `signature-derived-keys.md` |
| 11 | **Does the app die on its own after a while** — no Java stack, or a native crash that looks like a bug? | A hardened library rarely calls `kill`; it more often **arranges a fault** (load a small constant, use it as a pointer) so the death looks like an ordinary defect. Two rules before touching anything: **enumerate which mechanism actually fires** (signal and tombstone split them apart), and **neutralise by returning, never by making it not return** — a spinning stub freezes the process and produces a symptom that looks nothing like the cause | `native-tamper-and-suicide.md` |
| 12 | **Will this build still be usable in a week?** | Any version check, upgrade prompt or self-update path means an unpatched build can be switched off or replaced remotely. This is one or two edits and it decides whether the work is durable — part of the build, not a follow-up. Also check for a **hot-update / remote-config** channel, which restores removed behaviour with no version change at all | `updates-and-forced-upgrade.md` |
| 13 | **Does the request touch sign-in or phone binding** ("no login required", "skip binding", "guest ok")? | Separating a **client-side gate** (patchable) from an **account-scoped resource** (the screen is empty because the server has no account to answer for — not patchable). Classify first; and **never fabricate a session** to satisfy a gate, which produces a state worse than being signed out | `account-gates.md` |

**Long-task rule (a condition, not advice):** if this is likely to run long, open
`references/long-task-discipline.md` **now** and keep its record updated as you go. Re-read its
refuted-conclusions and dead-routes sections before starting any experiment. Losing earlier findings
is the most expensive failure in this skill, and it is entirely preventable.

## The workflow, end to end

Steps are ordered. **Skip a step only when its stated skip condition is met** — "it seems
unnecessary" is not a condition, and it is the reason most of the failures in `pitfalls.md` happened.

**Two-strike rule.** If the *same kind* of attempt fails twice, stop and go back to classification.
Do not run a third variation of a hypothesis that has already failed twice. Two failures of one shape
means the model is wrong, not that the parameters need tuning — and the third attempt is where an
entire round gets spent confirming what the first two already said. Re-read the symptom index at that
point; it exists for exactly this moment.

1. **Preflight, then Recon** — `scripts/doctor.py` is the cheapest possible first command: it reports which toolchains and scripts can actually run here, and surfaces the environment facts that poison experiments (clock skew, leftover `adb forward`/proxy, a device-side frida process already running, a tool installed off-PATH). Then `scripts/preflight.py` before anything else if a device is involved (it takes seconds and prevents a whole class of false conclusions), then `references/recon.md`. Manifest, package name, version, ABI, dex count, packer, embedded SDKs, where the app's own code lives. Ten minutes here saves hours. **If it is packed, unpack before anything else** (`references/recon.md` §unpacking): you cannot patch code you cannot read, the encrypted payload lengths tell you which dumped dex is the original, and a memory dump must be de-duplicated by hash and structurally validated before any of it is trusted.
   **If recon says there is no packer but a re-signed build still dies**, you are in the layer `references/code-virtualization-and-custom-linkers.md` covers — do not proceed on the assumption that "no packer" means "editable".
   **If the app already dies on its own** — especially at a roughly constant time after launch, or with a native crash — locate the mechanism *before* planning any patch (`references/native-tamper-and-suicide.md`, `scripts/native_crash.py`). Record the observed time-to-death: it is the baseline every later attempt is measured against, and without it a surviving run cannot be told from a changed schedule.
   *Skip condition:* never skipped. G2/G3 in §Gates are cleared here or not at all.
2. **Extract strings and endpoints** — build a picture of the app's API surface and SDK inventory from the dex string tables. No decompiler needed for this, and it is fast. Scripts: `scripts/dex_strings.py`.
3. **Trace to the owning class** — find the class that wraps the behavior (the app almost always wraps third-party SDKs in one helper). Reverse-lookup instructions: `references/dex-patching.md` §finding-the-call-site.
4. **Decide the patch layer** — client SDK call / client rendering / client data consumption / server contract. See the table in `references/ad-removal.md`.
5. **Patch surgically** — `references/dex-patching.md` and `references/byte-level-patching.md`.
   Two techniques, and picking the right one is a decision, not a preference:
   **equal-length byte edits** (`scripts/dex_patch_bytes.py`, located with
   `scripts/dex_find_insn.py`) when the change fits in an existing instruction slot
   or constant — nothing moves, so no offset, try/catch block or debug pointer can
   be invalidated. **dexlib2 method rewriting** (`scripts/dexpatch/`) only when the
   change genuinely needs new instructions. Whole-tree smali round-trip damages
   R8-optimized dex in ways that only show up at runtime; a method rebuild also
   inflates the file (measured: `debug_info` 924 B -> 22.8 KB, dex 4.32 MB ->
   7.73 MB on one sample). Whichever you use, recompute the dex header integrity
   fields (**signature first, checksum last**) — `references/byte-level-patching.md`
   §the dex header has two integrity fields.
6. **Repack and sign** — `references/repack-and-sign.md`. **Do not strip the whole `META-INF/`.** This single mistake destroys otherwise-correct builds.
6b. **Neutralise the update path — before you call the build done.** If the app checks for updates at all, add the two-layer patch (`references/updates-and-forced-upgrade.md`): no-op the update routine's entry, and force the version comparison to its "no update" side. A build that can be switched off or replaced remotely is not a deliverable, and this costs minutes here versus a rebuild later. Do the same for any **remote-config or hot-update** channel that could restore the behaviour you removed.
6c. **Handle account gates only after classifying them** — if the request mentions sign-in or binding, apply `references/account-gates.md` and state plainly which guarded screens become usable and which stay empty because their content is account-scoped.
7. **Verify on device** — `references/environment.md` + `references/verification.md`. Check: launches, the changed behavior actually changed, nothing unrelated broke, and **the app reaches its normal UI with no blocking dialog**. First prove the artifact actually changed on the device -- a package manager reporting success does not prove an interposed confirmation was accepted (P18). Capture continuously for the first ~20 seconds after launch, **and look at the captures** — sampling gaps are how a blocking modal goes unseen (P20), and a burst of images that were never inspected is not evidence. If the accessibility tree is empty, the image is the primary evidence rather than a fallback.
8. **Log what you learned** — if a failure cost you more than thirty minutes, add it to `references/pitfalls.md`. That file is the most valuable artifact in this skill.

## What "done" means — do not claim it earlier

Every item below must be true before you report completion. Anything less is a **checkpoint** and must
be labelled as one, out loud, with what remains. Premature "done" is the most damaging thing you can
report, because it ends the investigation while the user believes the problem is solved.

1. **The artifact exists and its identity is recorded** — path plus hash, not a filename.
2. **It was installed and launched on the environment the deliverable sentence names** (G1/R1). If
   that environment was not available to you, say so and label the result accordingly.
3. **The behaviour you changed is verified changed** — by direct observation of the feature, not by
   the absence of an error message. "The log is clean" is not evidence; "the screen shows X" is.
4. **The features it touches still work.** You exercised them. A build that starts but whose affected
   feature is dead is not a result.
5. **The original limitation is stated if any survives** — with the coupling that causes it, so the
   next person can decide whether to accept it.
6. **Nothing you did leaves the target or the device in a broken state** unless that was the goal, and
   any privileged workaround is labelled a fallback rather than the deliverable.

If items 1–4 hold but the environment was wrong, you have a **prototype**, not a deliverable. Say
"prototype" and name the gap.

## Stop conditions — halt and re-classify, do not retry

These are moments where continuing to push forward is the wrong move. Each has cost hours somewhere.

- **The same shape of attempt failed twice.** See the two-strike rule above.
- **A patch had no effect and you were about to try a third variant of it.** No effect means the
  diagnosis was wrong, not that the patch was unlucky. Re-classify the layer.
- **A new failure has no place in your current model.** That is the symptom index's trigger condition.
- **You are about to write off a route as "blocked"** without a control build proving the block is
  the app's doing rather than your pipeline's. Mis-attributed blocks have removed viable routes.
- **You are about to claim success on absence of errors.** See §What "done" means.
- **A measurement disagrees with a conclusion you already recorded as settled.** Re-open the
  conclusion; do not explain the measurement away.

## Non-negotiable constraints

**These are defects when violated, not preferences.** Each row states the check that catches it, so
"did I comply" is a command you can run rather than a judgement you make about yourself.

| Constraint | Why it is absolute | The check |
|---|---|---|
| **Inputs are read-only.** Work on copies; keep a known-good baseline | an edited original destroys the only reference you can diff against | `git`/hash the original before the first edit; `scripts/apk_diff.py` for entry-level proof |
| **One variable at a time**, with a control build (same pipeline, **zero** patches) | a compound change that fails teaches nothing, and the failure will be attributed to the wrong cause | a control run exists and its result is recorded |
| **Verify structure after every dex edit** | a patch that assembles and dies at load looks like a patch that worked | `scripts/dex_classdiff.py`: zero differences in class set and access flags for classes you did not intend to change |
| **Never patch a widely shared method.** Count callers first | a `Long.valueOf`-shaped helper with 30 callers is not an ad-specific hook | `scripts/find_refs.py` on the method you are about to touch |
| **Never make an API fail to suppress a UI element** | a 404/400 an endpoint's other features depend on takes the whole screen with it — measured as a build that never leaves the launch screen | suppress at the data-consumption or render layer instead; if a request's path changes, that is the bug |
| **Neutralise a native terminate path by returning, never by making it not return** | a spin stub freezes the caller **holding its lock**; unrelated threads wedge and the symptom (hang, external kill, restart loop) looks nothing like the cause, with no crash record | return a benign value, prefer success (`0`) over failure (`-1`), never touch `pthread_exit`/`exit`/`abort`/`snprintf`/`closedir`. `native-tamper-and-suicide.md` |
| **Look before you conclude, and look while you wait** | a screen that is actually looked at answers in one step what coordinate-guessing cannot answer in five | capture **and inspect**; byte-identical samples mean nothing will change. `scripts/snap.py`, `environment.md` §look at the screen |
| **Bound every command, and calibrate the bound from a measurement** | an unbounded call turns a stall into "still working", which is indistinguishable from progress | time the operation once, record it, derive the deadline from it. `long-task-discipline.md` §Bound every wait |
| **Every claim carries a label — `observed`, `inferred` or `unverified`** | "probably", "should be" and "in theory" are not findings, and an unlabelled guess propagates as a fact | `observed` requires a command **and its output**; nothing else may be written as established |
| **"Done" means the user-visible outcome** | a blocking dialog still on screen means the task is not done, however clean the log is | §What "done" means, all six items; absence of a log line is never evidence of success |
| **Never discard a route on compound evidence** | if a failure followed two simultaneous changes, the attribution is a hypothesis — mis-attributed failures have removed viable routes for hours | re-run the abandonment single-variable before writing it down |
| **Prove the device changed before measuring anything** | install success describes the *request*, not the app on disk | hash the on-device artifact against your build; otherwise every later observation describes the previous build |
| **Attribute a failure to the right layer before patching again** | a feature-scoped network failure is frequently the app's own TLS/certificate problem, and chasing a signature check that does not exist burns hours | run the **unmodified original** on the same device and network first (`tls-and-cert.md`) |

## Reference index and script index

**Both tables live in `references/routing.md`** — one load gets you every reference file with when to
load it, and every script with what it does. They are deliberately not duplicated here: this file is
loaded in full every time the skill activates, and those two tables are about 140 rows of lookup data
that nobody needs until they have already decided what to do.

The symptom index above stays, because **symptom to file has to be one hop**: when something fails you
are not choosing a file, you are recognising a failure, and a two-hop lookup at that moment is exactly
how a stop signal gets skipped.

`references/evidence-summary.md` is the one reference that answers the claim-strength question from
inside an installed copy: capability → one-line conclusion → `observed`/`inferred`/`unverified` → the
evidence that ships with the skill. Load it when a claim's strength decides whether you trust it and
the run record is not in front of you.

`python check_routing.py` checks that this file and `references/routing.md` still agree, that every
reference file is named there, and that every script is named there. CI runs it.
