# Coverage and limits — the evidence behind each claim

`SKILL.md` §Coverage states **what this skill covers and what it does not**, because the failure
worth preventing is not ignorance but *a confident wrong answer produced by applying the nearest
available procedure to a target it was never written for*. That statement has to stay short: it is
read on every task, before any routing decision.

This file carries the part that is read **only when you need to weigh a claim** — the evidence
behind each covered item, the exact footing of the unverified ones, and the historical record of
what was and was not exercised. Load it when a claim's strength decides whether you trust it.


**Load this when:** a claim's strength decides whether you trust it, or you are about to quote this skill's coverage. It gives the evidence behind each covered item, the dependencies this skill does not ship, and the routes nobody has run.

## Strength labels

- **observed** — a command was run and its output is recorded in the evidence record condensed in `references/evidence-summary.md` §Where the full record lives.
- **inferred** — follows from documented mechanism or from a neighbouring measurement; the step
  itself was not executed.
- **unverified** — assumed, or reported by someone else, and not reproduced in this repository.

Reserve `observed` strictly (`references/long-task-discipline.md` does). "I reasoned it out" is
`inferred`. The distinction is load-bearing, not cosmetic: an `inferred` route may still be right,
but nobody here has paid for the counters yet.

## Covered, by verified mechanisms — the evidence

- **Client-side ads, promos and splash/popup/tab configuration**, including the server-issued UI
  config that has no SDK to find (`ad-removal.md`, `server-config-and-updates.md`).
- **Deciding whether a membership, paywall or feature gate is client-enforceable at all**, and
  saying so plainly when it is not (`membership-and-limits.md`, `account-gates.md`).
- **dex-level surgical patching**: equal-length byte edits and dexlib2 method rewrites, plus the
  header, verifier and alignment rules that decide whether the build loads (`dex-patching.md`,
  `byte-level-patching.md`, `patch-audit.md`).
- **Repacking, signing, installing**, and the install refusals that look like a broken build
  (`repack-and-sign.md`).
- **Packers, custom loaders and code virtualization**: identifying them, measuring the validation
  boundary, and the routes that survive it (`packers.md`,
  `code-virtualization-and-custom-linkers.md`).
- **The native layer**: `.so` hosts, tamper-triggered self-termination, forged ELF structure, and
  neutralising a terminate path without freezing the process (`native-and-so.md`,
  `native-tamper-and-suicide.md`).
- **Flutter / Dart AOT**: analysing and patching `libapp.so` **given a snapshot dump** —
  pool-reference counting, disassembly windows, caller indexing, patch-site choice (`dart-aot.md`).
  Measured on a real Dart 3.6.0 build: `dart_disasm.py` decoded identically to capstone (32/32 and
  96/96), the caller index was re-derived independently with a symmetric difference of 0, and a
  specific business logic site was located end to end. **The snapshot dump is a dependency, not a
  detail** — see the next section.
- **Runtime analysis with Frida, server-side API probing, feature-scoped TLS failures, update and
  forced-upgrade neutralisation**, and the verification discipline everything above rests on.

### Added by the benchmark pass, and measured against public targets

Each of these has a row in the benchmark matrix (`references/evidence-summary.md` §The capability matrix) naming its target, its strength and the evidence
file behind it.

- **Java2C versus JNI sinking versus an extraction shell.** Native-declaration density separates the
  shapes by roughly 2000x: **0.03–0.04%** on three real JNI samples against **82.76%** on a
  Java2C-shaped fixture, with `Java_*` symbols matching dex native-method counts 1:1 per ABI. A
  symbol search fails *silently* on real Java2C — `dcc` emits `-fvisibility=hidden`, and C++
  `jni.h` inlines `RegisterNatives` so it leaves no symbol at all
  (`java2c-and-jni-sinking.md`, `scripts/java2c_probe.py`). **No Dex-to-C compiler output was ever
  built here** (no NDK, no host clang, no device clang, WSL unavailable), so every Java2C-specific
  criterion is `inferred`; the JNI-sinking side and the discrimination itself are `observed`.
- **Split APK / App Bundle sets.** Inventory, unified re-signing for `pm install-multiple`, and a
  merge of code/native members into one APK — the merge **refuses by design** when a member carries
  its own `resources.arsc` (`split-apk.md`, `scripts/repack.py`). Measured on two real sets pulled
  from a device; `adb install-multiple` and launch confirmation were **not** executed.
- **Schema-free protobuf decoding**, cross-checked against the official runtime
  (`scripts/protobuf_decode_raw.py`, `protocol-reverse.md`). 26/26 built-in fixtures, 21/21 against
  the official runtime, and a real DataStore container round-tripped byte-exact.
- **Differential hardening for a real Dex VMP** — a labelled opcode-coverage fixture, a closed-loop
  verification of the derived map, and an explicit cost judgement that the upload link cannot be
  automated (`vmp-differential-analysis.md`, `scripts/vmp_diff_harness.py`).
- **Kernel-module templates with their version gates**
  (`kernel-and-environment-hardening.md`, `scripts/kernelsu_syscall_mask.py`). The generator is
  measured; **no kernel-side artefact was compiled or loaded** — see the record below.

## Covered by documented routes — inferred rather than measured

Written from public work and from whatever the extension pass could exercise; each document carries
its own strength note at the top.

- **Module-side delivery instead of a repack** — what to do when the client-side logic is reachable
  but a rebuilt APK is refused (`lsposed-and-modules.md`).
- **Extraction shells and the VMP boundary** — how to *measure* that the bodies are empty instead of
  guessing, why the classic active-invocation hooks stopped working on Android 12–16, and where
  recovery honestly stops (`advanced-unpacking.md`, `scripts/dex_dump_validate.py`).
- **Calling the target instead of reading it** — emulated execution and live Frida-RPC
  service-ification (`emulation-and-rpc.md`).
- **Instruction-level tracing and de-obfuscation** — the OLLVM shapes, a Stalker trace, the
  trace-to-CFG route, and the measured boundaries in `native-dbi-and-deobfuscation.md`.
- **Protocol reversing beyond REST** — protobuf without a schema, gRPC frame capture, the QUIC/HTTP3
  limit, native-side certificate pinning (`protocol-reverse.md`).
- **What to do when userspace hooking provably cannot reach the check** — raw `svc` syscalls,
  `init_array`-early detection, and the kernel-route map with its version gate
  (`kernel-and-environment-hardening.md`).
- **Working from the phone itself** — MT Manager, its APK MCP surface, LSPosed Manager, on-device
  data inspection (`on-device-tooling.md`, `scripts/mt_mcp_probe.py`).

## Dependencies this skill does not ship — name them before the workflow starts

- **Dart AOT analysis needs a snapshot dump.** `dart-aot.md`'s workflow begins at `pp.txt`;
  producing it requires a snapshot container resolver this skill does not contain and cannot
  synthesize. `dart_pool_strings.py` reports **file** offsets while `pp.txt` and `dart_pprefs.py`
  speak in **pool** offsets, and the mapping between the two spaces is not a constant: over the
  4,241 strings present in both, a measured run found 4,237 distinct deltas. Ship a pinned front end
  (aotopsy — pure Go, no toolchain) or build blutter (~80 s, needs a C++ toolchain). **Say which one
  you are using and why, because the two report different Dart version labels for the same binary.**
  Do not describe the object pool as something this skill decodes on its own.

## Not covered — say so rather than improvise

- **Unity / IL2CPP logic recovery.** `framework-runtimes.md` identifies the runtime and establishes
  that the dex is not the battlefield; it does not carry the IL2CPP equivalent of `dart-aot.md`.
  There is no verified recipe here for locating a method inside `libil2cpp.so` plus
  `global-metadata.dat`.
- **React Native / Hermes bytecode** and Cordova/hybrid internals, beyond runtime identification and
  the generic "find the string, then find what references it" approach.
- **iOS / `.ipa` of any kind.** Every device, signing and packaging instruction here is Android.
- **Defeating a server-side authority.** `server-api.md` determines *who owns a gate*, not how to
  break an authorization the server performs.
- **An off-the-shelf unpacker, and an anti-detection arms race.** `advanced-unpacking.md` routes the
  problem — measure the ratio, name the recovery mechanism, stop when the target is a real VMP — but
  ships no modified ART runtime, no private-bytecode decompiler and no opcode-mapping derivation,
  and says so rather than presenting a memory dump as a recovery. `detection-and-anti-analysis.md`
  decides by cost and often concludes "switch to static"; it is not a catalogue of evasion. It now
  also carries an order of search, plus a measurable environment self-report and an observer-only
  probe — and the boundary that keeps those from becoming an evasion project is stated in the same
  file (its Step 2B, two boundaries this file adopts): observers and interceptors stay separate
  modules, and the cost of each added module is what decides when to leave for static.
- **Kernel development.** `kernel-and-environment-hardening.md` maps the kernel-side route and names
  the version gate that decides whether it exists on your device; building and shipping a kernel
  module is outside this skill.
- **A working Stalker trace on every device.** Two boundaries are measured and one of them is now
  better understood: exclusion keeps the target alive but does **not** restore event delivery
  (`references/evidence-summary.md` §The capability matrix). Treat the zero-event case as a boundary to
  identify, not a recipe to follow.

## Historical verification record

This is the part that grows every pass, which is why it does not live in `SKILL.md`. Read it before
trusting any "this was measured" statement above.

**The first verification pass measured, against a real target:** a mid-size Flutter AOT application
with no packer — the Dart work above, library mapping, and the environment facts. It **did not
exercise** the packer, code-virtualization, custom-linker, integrity-check-redirection or
tamper-suicide scenarios: that target has none of those features and its unmodified build already
fails to start, which removes the repack-and-regress loop those scenarios need. Nothing in
the evidence record condensed in `references/evidence-summary.md` §Where the full record lives is evidence either way about them.

**Scripts the first pass did not run** — they carry no measurement from that pass, and any
conclusion drawn from them should be labelled accordingly: `native_crash.py`, `apk_diff.py`,
`snap.py`, `grab_crash.py`, `install_test.py`, `repack.py`, `dex_patch_bytes.py`,
`dex_find_insn.py`, `dex_check_verifier.py`, `dex_classdiff.py`, `dex_strpatch.py`,
`patch_smali.py`, `smtool.py`, `datastore_inject.py`, `probe_api.py`, `run_probe.py`,
`tls_check.py`, `usb_net_proxy.py`, `devsh.py`, and the `dexpatch/` java rewriter. Absence from
that record is not a verdict on them. Note that `grab_crash.py` claims to recover stacks hidden by
a crash-reporter SDK — the exact situation that target presented — and was not tried, so that claim
remains **unverified**. **The benchmark pass has since run some of these**: `repack.py`,
`dex_patch_bytes.py`, `dex_dump_validate.py`, `dex_mem_scan.py`, `spawn_patch_detach.py` and
`stalker_trace.js` now have measurements, with the failures recorded alongside the successes in
the benchmark matrix (`references/evidence-summary.md` §The capability matrix).

**The extension pass shipped its own scripts, each with its own status** — read the matching
the per-topic files named in `references/evidence-summary.md` §Where the full record lives before relying on one: `dex_dump_validate.py` (measured
against a fixture derived from a real hardened sample, and against that sample's own shell dex),
`lsposed_scaffold.py` (its generated project was built end to end, toolchain timings recorded),
`frida_rpc_serve.py` (the `rpc.exports` bridge was exercised on a live device),
`mt_mcp_probe.py` (the "service is down" path is measured; the connected path needs the service
started by hand), and `stalker_trace.js` / `stalker_report.py` (two boundary results, no successful
trace of a real target).

**The extension pass's claims are mostly `inferred`.** Its evidence lives in
the per-topic files named in `references/evidence-summary.md` §Where the full record lives, one file per topic, each with its own strength note. The
common shape there is *the tool was measured, the route was not* — read those files before treating
any of the newer documents as a verified path.

**The detection pass added two tools and three boundaries, and its evidence is mixed.** Recorded in
`references/evidence-summary.md` §The capability matrix:

- `svc_scan.py` — **measured**, and its whole claim is cross-checked: two independent decoders
  (a hand-written word scan and the capstone-based scan) returned an identical 214-site set on a
  device `linker64`, set difference empty. That agreement is what makes its output usable as
  evidence about a *target's* library rather than about the scanner.
- `anti_detect_probe.js` — **measured, observer-only by contract** (it patches nothing, so a run
  that uses it still describes the target it was pointed at). On a public MASTG challenge target it
  recorded `strstr("frida")` at ~300 ms of process life followed by a clean self-exit, and it
  reported the target's own view of the environment (`TracerPid=0` while **four** frida-named
  mappings were visible in `/proc/self/maps`). The same arm captured the full sequence **once out of
  three runs** — on a target that dies in ~300 ms the window is sub-second and not arm-to-arm
  reproducible, which is why the reference labels it that way rather than as a pipeline.
- `scan_leaks.py` — **measured against a planted corpus and against this repository**. On the corpus
  every rule fired (30 findings across 6 categories) and the exemption list produced zero false
  positives on identifiers that must stay (tool names, SDK packages, dex constant identifiers, CVEs,
  hardening products, public crackme names, placeholders). On this repository it found **26 strong
  hits on its own evidence file**, which is the strongest evidence available that the class of leak it
  targets is not visible by hand. `observed`.
- **The Dart AOT string-table formats** — the arm64 packed scheme is confirmed at the byte level
  (tag byte equal to `0x80|(len<<1)` at every literal checked, 4,980 chained pool entries), and the
  previously documented armv7 form is **refuted**: the 32-bit record is
  `[header u32][byte-count u32le][UTF-8 payload]`, and the extractor's zero for that ABI is a format
  mismatch rather than an empty table. `observed` for the formats; `unverified` for an end-to-end
  patched build, because none was repacked and installed in that pass.
- **`observed`:** for the `ptrace-free` route, byte-identity between two *read paths*
  (`/proc/<pid>/mem` versus the backing file) on the same byte range, and the route's negative
  boundary — a target whose dex is deflate-compressed inside its APK has **no** named dex mapping to
  export (`named_dex=0` on both MASTG targets), so the route yields nothing there for reasons that
  say nothing about protection.
- **`unverified`:** byte-identity between two independent *dumpers*. The second producer
  (`frida-dexdump`) is refused by this repository's hardened sample, whose usable lifetime collapsed
  to ~2 s this pass, and the clean targets have no whole-image dex for any dumper to find. The
  weaker read-path check is what was run instead, and the distinction is stated in the evidence file
  rather than papered over.

**Where the record lives.** The full record is `docs/tool-verification/` at the **repository root, not
shipped** with the skill; `references/evidence-summary.md` is the condensation that does travel, and
`references/routing.md` is the inventory. Neither the per-topic records nor the public-target
regression matrix ships inside an installed skill, so an installed copy carries the claim but not its
evidence file — which is why the strength label is stated here rather than left to be looked up.
