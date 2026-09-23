# Coverage inventory — the per-route list behind `SKILL.md`'s Coverage section

`SKILL.md` states the rule: **do not apply the nearest available procedure to a target it was never
written for**, and label every claim `observed` / `inferred` / `unverified`. This file is the list that
rule needs — which routes are covered, by what, and how strong the evidence actually is.

Load it when the question is "**can this skill actually do X**", or before quoting a coverage claim
as if it were verified. `references/coverage-and-limits.md` carries the same material as a claim
ledger with the per-item evidence; this file is the inventory you can read in one pass.

## Covered, by verified mechanisms

These have a command and an output behind them somewhere in the evidence record (repository root,
the evidence record condensed in `references/evidence-summary.md` §Where the full record lives, **not shipped with the skill**).

| Area | Route, in one line | Where it lives |
|---|---|---|
| Client-side ads, promos, splash/popup/tab config | includes server-issued UI config that has no SDK to find | `ad-removal.md`, `server-config-and-updates.md` |
| Membership / paywall / feature gates | decide whether it is *client-enforceable* at all, and say so when it is not | `membership-and-limits.md`, `account-gates.md` |
| dex-level surgical patching | equal-length byte edits, dexlib2 method rewrite, header/verifier/alignment rules | `dex-patching.md`, `byte-level-patching.md`, `patch-audit.md` |
| Repack, sign, install | including the install refusals that look like a broken build | `repack-and-sign.md` |
| Packers, custom loaders, code virtualization | identification, the validation boundary, the routes that survive it | `packers.md`, `code-virtualization-and-custom-linkers.md` |
| Java2C vs extraction shell vs JNI sinking | the misdiagnosis that sends you hunting a decrypted DEX that never exists | `java2c-and-jni-sinking.md`, `scripts/java2c_probe.py` |
| Native layer | `.so` hosts, tamper-triggered self-termination, forged ELF, neutralising a terminate path | `native-and-so.md`, `native-tamper-and-suicide.md` |
| Flutter / Dart AOT | analysing and patching `libapp.so` **given a snapshot dump** | `dart-aot.md` |
| Runtime and server side | Frida analysis, API probing, feature-scoped TLS failures, update/forced-upgrade neutralisation | `dynamic-frida.md`, `server-api.md`, `tls-and-cert.md`, `updates-and-forced-upgrade.md` |
| Verification discipline | the claim ladder, control builds, capture-and-look, bounded waits | `verification.md`, `long-task-discipline.md` |

## Also covered, by documented routes — mostly *inferred* rather than measured

Read the qualification, not just the name: for these the **mechanism is documented and the end-to-end
route was not measured on this repository's evidence**. Treat them as leads with a stated boundary.

| Area | What it gives you |
|---|---|
| Module-side delivery | an LSPosed/Xposed module when a repack is refused — `lsposed-and-modules.md` |
| Extraction shells and the VMP boundary | how to *measure* that the bodies are empty, and where recovery stops — `advanced-unpacking.md` |
| Calling a routine instead of reading it | emulation (Unidbg/Unicorn) versus service-ifying the live function over Frida RPC — `emulation-and-rpc.md` |
| Instruction-level tracing | Stalker traces and the trace-to-CFG route against OLLVM, with its measured boundaries — `native-dbi-and-deobfuscation.md` |
| Protocols beyond REST | schema-free protobuf, gRPC frames, QUIC/HTTP3 limits, native-side pinning — `protocol-reverse.md` |
| When userspace hooking cannot reach the check | raw `svc`, `init_array`-early detection, the kernel-route map and its version gate — `kernel-and-environment-hardening.md` |
| Split APK / App Bundle sets | reading a set, merge versus unified re-signing, the install refusal each mistake produces — `split-apk.md` |
| Dex-VMP differential analysis | the known-plaintext route, what it can and cannot automate — `vmp-differential-analysis.md` |
| Kernel-module templates | a scaffold **and** its version gate; a userspace module cannot change a syscall return value — `kernelsu_syscall_mask.py` |
| Working from the phone itself | MT Manager edit/repack/sign and its APK MCP, LSPosed Manager, Termux — `on-device-tooling.md` |
| Publishing without publishing the target | the leak scanner, the do-not-anonymize list, and the graded precedent library — `desensitization-and-leak-scans.md`, `scripts/scan_leaks.py`, `precedents/` |

## Dependencies this skill does not ship

Each of these is a **fence**, not a caveat: the route above it stops here unless you obtain the
dependency yourself.

- **Dart AOT analysis needs a snapshot dump**, and which front end produced it matters (`dart-aot.md` §1–2).
- **`smali` round-trip needs baksmali/smali/dexlib2 jars** — not bundled; `APKREV_JARS` points at them.
- **Repack-and-sign needs `zipalign` + `apksigner`** (or `uber-apk-signer`); a JVM alone is not enough,
  which is exactly what `scripts/doctor.py` now refuses to report as OK.
- **Device work needs `adb` plus a device the app does not object to**; dynamic work additionally needs
  a `frida-server` matching the host version.
- **A kernel-side answer needs a module and a kernel that accepts it** — the version gate is in
  `kernel-and-environment-hardening.md`.

## Not covered — say so rather than improvise

Unity / IL2CPP logic recovery · React Native, Hermes bytecode and Cordova internals · iOS of any kind ·
defeating a server-side authority · an off-the-shelf unpacker · an anti-detection arms race · building
and shipping a kernel module · a Stalker trace guaranteed on every device.

Each has a reason and, where one exists, an evidence boundary — in `references/coverage-and-limits.md`.
**Silence in that record is not support**, and a route that is only "documented" is not a route that
was measured.
