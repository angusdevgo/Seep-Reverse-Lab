# Evidence summary — what is proven, how strongly, and where to look

Load this when a claim's strength decides whether you trust it, and the command that produced it is
not in front of you. It is the condensation that travels with the skill: `npx skills add` installs
`skills/apk-reverse/` only, so the run records, the tool verdicts and the public-target benchmark
matrix stay behind at the repository root. Every row below therefore answers four questions inside an
installed copy — **is it proven, how strongly, which capability is blocked, and which files to open
next** — and points at the one section that says "the full record is elsewhere, and here is its name".

## How to read this file

- **Status** is one of `ok` (route carried out on a real target, result recorded), `partial` (a
  decisive step — usually install, launch, or a second independent producer — was not run), or
  `blocked` (the route depends on something this skill does not ship, or nothing here is evidence
  either way).
- **Strength** is the repository's three-tier label: `observed` (a command was run and its output
  exists behind the claim), `inferred` (follows from a documented mechanism or a neighbouring
  measurement), `unverified` (assumed or reported elsewhere, not reproduced here). `observed` is
  reserved strictly.
- **Evidence** names files that exist in your install. When a claim's full record does not ship, this
  file says so once, in one place, instead of scattering dead paths through the table.
- Machine-readable companions: `evidence/capability-matrix.json` (the same rows, with more fields),
  `evidence/tested-tool-versions.json` (versions and the probe behind each), and
  `evidence/known-limitations.md` (the installer-facing limit list).

## The capability matrix

| Capability | What is proven, in one line | Status | Strength | Evidence in this install |
|---|---|---|---|---|
| Equal-length dex surgical patch | 2 bytes rewritten in a 5,528-byte dex; whole-file diff is those 4 bytes plus header bytes 8..32; the written file reproduces both header integrity fields | ok | observed | `references/byte-level-patching.md`, `references/patch-audit.md`, `scripts/dex_patch_bytes.py` |
| Dex method-level rewrite (dexlib2) | Documented, not measured: the smali round-trip blind spot is real and a tree round trip can pass every table check and still fail at load | partial | unverified | `references/dex-patching.md`, `references/patch-audit.md` |
| Dex header integrity and verifier legality | Recompute order proven on one written file; `dex_classdiff` passing is necessary, not sufficient — it cannot see code-item damage | ok | observed | `references/patch-audit.md`, `scripts/dexutil.py`, `scripts/dex_check_verifier.py` |
| Dex string-constant patch | Equal-length only; the shipped script refuses unequal lengths, so a different-length edit is a different, unmeasured route | partial | unverified | `references/byte-level-patching.md`, `scripts/dex_strpatch.py` |
| Repack, sign, install (single APK) | End to end: STORED and 4-byte-aligned `resources.arsc`, v1+v2+v3 true, install succeeded, on-device hash matched the local build, control build still fails the old way | ok | observed | `references/repack-and-sign.md`, `references/verification.md`, `scripts/repack.py` |
| Split APK / App Bundle sets | Analyze, unified re-sign and merge measured on two real sets; merge correctly refuses a member carrying its own `resources.arsc` | partial | observed | `references/split-apk.md`, `scripts/repack.py` |
| Third-party build audit | Not measured: the APK differ is on the list of scripts no pass has run | partial | unverified | `references/third-party-builds.md`, `scripts/apk_diff.py` |
| Extraction-shell detection (trivial-body ratio) | The ratio is bimodal, not thresholded; the old "tens of percent" rule was wrong and was deleted | ok | observed | `references/advanced-unpacking.md`, `scripts/dex_dump_validate.py` |
| Dex-VMP declaration boundary | Static criteria can rule a VMP out, never in; a hand-written opcode table produced a VMP verdict on ordinary dalvik with zero structural errors | partial | observed | `references/advanced-unpacking.md`, `references/code-virtualization-and-custom-linkers.md` |
| VMP differential opcode map | Closed loop re-derived 218 of 218 emitted opcodes with zero fabrications; no hardening platform was ever contacted | partial | observed | `references/vmp-differential-analysis.md`, `scripts/vmp_diff_harness.py` |
| Java2C versus JNI sinking | Native-declaration density separates the shapes by about 2000x and `Java_*` symbols matched dex counts 1:1; no Dex-to-C compiler output was ever built here | ok | observed | `references/java2c-and-jni-sinking.md`, `scripts/java2c_probe.py` |
| Neutralising a native terminate path | Tooling works, patch does not: writes land and survive detach, and the target still dies at the same site | partial | observed | `references/native-tamper-and-suicide.md`, `scripts/spawn_patch_detach.py`, `scripts/hook_patch_only.js` |
| Instruction-level tracing (Stalker) | Exclusion keeps the target alive; it does not restore event delivery, which stayed at zero | partial | observed | `references/native-dbi-and-deobfuscation.md`, `scripts/stalker_trace.js`, `scripts/stalker_report.py` |
| Library mapping and PLT resolution | Mapping verified on a real target; the PLT script was broken and fixed after a false negative on a symbol that exists and is called | ok | observed | `references/native-and-so.md`, `scripts/lib_map.py`, `scripts/elf_plt.py` |
| Native crash triage and swallowed stacks | Unmeasured, including on the one target whose crash reporter hid exactly the stack the tool claims to recover | partial | unverified | `references/native-tamper-and-suicide.md`, `scripts/native_crash.py`, `scripts/grab_crash.py` |
| Runtime analysis with Frida | Instrumentation is a variable: attaching is what kills some targets, and exclusion is what keeps others alive | ok | observed | `references/dynamic-frida.md`, `references/environment.md`, `scripts/run_probe.py` |
| Local runtime data (DataStore and friends) | One real container round-tripped byte-exact and an edited value was read back; SharedPreferences and SQLite edits have no equivalent measurement | partial | observed | `references/runtime-data.md`, `scripts/datastore_inject.py` |
| Anti-instrumentation triage | The check was named and timed, and the `TracerPid=0` versus four frida-named mappings asymmetry was recorded; reproducibility is bounded to a sub-second window | ok | observed | `references/detection-and-anti-analysis.md`, `scripts/anti_detect_probe.js` |
| Emulation and Frida-RPC | The RPC bridge ran end to end on a live device, but the route itself is classified inferred: no target library was emulated | partial | inferred | `references/emulation-and-rpc.md`, `scripts/frida_rpc_serve.py` |
| Schema-free protobuf decode | 26/26 built-in fixtures, 21/21 against the official runtime, 8/8 framing checks, one real container byte-exact | ok | observed | `references/protocol-reverse.md`, `scripts/protobuf_decode_raw.py` |
| Server API probing and TLS scope | Determines who owns a gate, not how to break it; the native-pinning row was never run because it needs a toolchain this host lacks | partial | inferred | `references/server-api.md`, `references/tls-and-cert.md`, `scripts/probe_api.py` |
| Dart AOT analysis (given a dump) | Decoded identically to an independent disassembler (32/32, 96/96) and re-derived a caller index with a symmetric difference of 0 | partial | observed | `references/dart-aot.md`, `scripts/dart_disasm.py`, `scripts/dart_pprefs.py` |
| Dart AOT string-table format | arm64 packed form confirmed at the byte level; the documented armv7 UTF-16 form is refuted, and the extractor's zero is a format mismatch | partial | observed | `references/dart-aot.md`, `scripts/dart_pool_strings.py` |
| Producing a Dart AOT snapshot dump | Blocked: no resolver ships with this skill and none can be synthesized here | blocked | unverified | `references/dart-aot.md`, `references/coverage-and-limits.md` |
| Packer and custom-loader identification | Never exercised end to end; the target that was measured has no packer, so the tooling was recorded as not applicable | partial | unverified | `references/packers.md`, `references/code-virtualization-and-custom-linkers.md` |
| Module delivery instead of a repack | The scaffold builds end to end, but the delivery route has no public-target measurement and needs a device with the framework active | partial | inferred | `references/lsposed-and-modules.md`, `scripts/lsposed_scaffold.py` |
| Kernel-side syscall answer forging | Blocked on the kernel side: the generator is measured, no kernel artefact was compiled or loaded, and a userspace module cannot change a return value | blocked | unverified | `references/kernel-and-environment-hardening.md`, `scripts/kernelsu_syscall_mask.py` |
| `svc` site scanning | Two independent decoders agreed on an identical 214-site set; a byte scan also matches data, so neighbour context decides | ok | observed | `references/kernel-and-environment-hardening.md`, `scripts/svc_scan.py` |
| On-device tooling (MT Manager MCP) | The service-down path is measured; the connected path needs the service started by hand | partial | observed | `references/on-device-tooling.md`, `scripts/mt_mcp_probe.py` |
| Client-side ads and server-issued UI config | Measured on a real mid-size target's ad chain, with a repacked build's on-screen change confirmed | ok | observed | `references/ad-removal.md`, `references/server-config-and-updates.md` |
| Is a membership or paywall gate client-enforceable? | The decision framework is documented; no gate-shaped public target was put through it here | ok | inferred | `references/membership-and-limits.md`, `references/account-gates.md` |
| Update and forced-upgrade neutralisation | Documented, no measurement; the failure shape is a build that installs, runs and fails every signed request | partial | inferred | `references/updates-and-forced-upgrade.md`, `references/signature-derived-keys.md` |
| Signature-derived keys | Documented only: neither the offline candidate path nor the live read has a public-target measurement here | partial | unverified | `references/signature-derived-keys.md`, `scripts/sig_probe.py` |
| Publishing sanitisation and leak scanning | Every rule fired on a planted corpus with zero false positives on the do-not-anonymize list, and the scan found 26 strong hits in its own evidence file | ok | observed | `references/desensitization-and-leak-scans.md`, `scripts/scan_leaks.py` |
| Unity / IL2CPP, React Native / Hermes, iOS | Outside this skill: the runtime can be identified, the logic recovery is not covered | blocked | unverified | `references/framework-runtimes.md`, `references/coverage-and-limits.md` |
| Defeating a server-side authority | Out of scope by design; report it as a residual rather than patching harder | blocked | unverified | `references/server-api.md`, `references/handoff-boundaries.md` |

## Where the full record lives — repository root, not shipped

Six entries, deliberately: everything the table needs beyond your install is here, and nothing else
in this skill should point outside itself. **All six sit at the repository root and are not installed
by `npx skills add`; their paths are names, not openable files, in your copy.**

- `docs/tool-verification/README.md` — the index of the evidence record (repository root, not shipped)
- `docs/tool-verification/TOOL-VERDICTS.md` — one verdict per script and external toolchain, with the independent cross-check behind it (repository root, not shipped)
- `docs/tool-verification/FINDINGS.md` — defects, contradictions and boundary evidence about the skill itself (repository root, not shipped)
- `docs/tool-verification/REPO-DECISIONS.md` — what changed as a result, and what deliberately did not (repository root, not shipped)
- `docs/tool-verification/EXTENSION-*.md` — one file per topic, each with its own strength note and the exact commands (repository root, not shipped)
- `tests/benchmark.md` — the B1–B13 public-target regression matrix: what happened, including the negative results (repository root, not shipped)

The reference documents still cite those paths where the detail matters, because a repository reader
can open them. The labels, the one-line verdicts and the blocked list are all here, so an installed
copy never has to fail silently at a path it cannot open.

## When the evidence does not reach your case

| Your situation | Do this |
|---|---|
| The row you need says `observed`, but for a different target shape | Treat it as a reason to try the route first, not as proof it will work. Keep your own control build. |
| The row says `inferred` | The mechanism is documented or borrowed from a neighbouring measurement. Budget one cheap experiment that would make it `observed` before building on it. |
| The row says `unverified` | Nobody here has paid for the counters. Do not cite this skill as support; run the step and label your own result. |
| The row says `blocked` | Do not improvise a route. State the missing dependency, and name the cheapest experiment that would identify whether it is the real blocker. |
| The step needs install or launch, and the row stops before it | The route is not end-to-end. Install it, launch it, and exercise the feature before calling it done. |

## Failure modes

- Reading "the tool ran" as "the tool is right". One script here produced a false negative on a symbol
  that exists and is called; another answers "no references" for input it cannot read at all.
- Reading a confident paragraph as `observed`. The label decides, not the prose.
- Reading `unverified` as a refutation. It is an absence of evidence here, not evidence of absence.
- Treating silence in `evidence/known-limitations.md`'s never-exercised list as support for a route.
- Presenting a route as verified when the artifact that was verified is not the artifact being handed
  over — the claim ladder in `references/verification.md` exists for exactly this gap.
