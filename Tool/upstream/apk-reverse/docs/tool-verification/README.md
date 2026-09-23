# Tool verification record

This directory is the **evidence record for the `apk-reverse` skill measured against real
targets**, kept separate from the skill itself so the Coverage statement in `SKILL.md` can be
checked against the runs behind it, and so a later reader can tell which claims were *observed*,
which were *inferred*, and which are still *unverified*.

It is **not** a set of target-specific notes kept for reuse, and it deliberately carries **no target
identity**. The measurements are about the **tools and the skill**; they stay valid whichever APK
produced them. Where a concrete figure was needed to make a point (a class count, a file size, a
build time) the figure is kept and the target is named generically.

Targets measured: Flutter AOT applications, multi-dex, mid-size native library sets, no packer.

The APKs themselves are **not** in this repository (`.gitignore` excludes `*.apk`, and `tools/`).

**Workbench paths are an operation record, not a pointer.** A record may say a run happened *at*
`tools/_work/...` so the command can be judged; `.gitignore` excludes `tools/`, so that path is not
something a reader can open. Anything a reader is *meant* to follow is named under
`docs/tool-verification/` or inside the skill — that rule is why a reference document never cites a
`tools/` path as its evidence, even when the work happened there.

## Strength labels

Every claim carries one of three labels, used the same way `references/verification.md` uses them:

- **observed** — reproduced here, with the exact command and its output.
- **inferred** — follows from observed facts, but the step itself was not executed.
- **unverified** — assumed or reported by a tool and not independently confirmed.

## Index

| File | Covers |
|---|---|
| `TOOL-VERDICTS.md` | One verdict per tested script and external toolchain, with the independent cross-check behind it |
| `FINDINGS.md` | Findings about the skill itself: defects, contradictions, boundary evidence |
| `REPO-DECISIONS.md` | What changed in the repo as a result, and what deliberately did not |

## Extension-pass record

The extension pass (the six coverage gaps named in the external review: module ecosystem, extraction
shells and VMP, emulation/RPC, native DBI, kernel-level environment, protocol layers) keeps its
evidence here, one file per topic, in the same three labels:

| File | Covers |
|---|---|
| `EXTENSION-device-run.md` | The on-device run against a hardened Flutter sample: the two control runs, the frida refusals, the **twice-corrected** pid-drift attribution, the failed-dump artefacts checked with `dex_dump_validate.py`, and a shared-device hazard measured with Stalker |
| `EXTENSION-unpacking.md` | Extraction-shell diagnosis by trivial-body ratio, `dex_dump_validate.py` against a fixture derived from the sample's own shell dex, and the tool's own defect found during the run |
| `EXTENSION-rootdump.md` | The root-side `/proc/<pid>/maps` + `mem` route that does not use frida: 17 real dex images recovered, the shell skeleton they are not, four device-shell traps, and the negative result on anonymous/ART-heap scanning |
| `EXTENSION-lsposed.md` | Module route: the gradle-free build chain with timings, three build traps, LSPosed config-DB anatomy, the module that could never have worked, and the root-hiding configuration the device actually has |
| `EXTENSION-emulation-rpc.md` | ASC/`ddc` measured on a hardened APK, Frida-RPC exercised end to end on a live device, and the unidbg build repair |
| `EXTENSION-native-dbi.md` | Stalker: the zero-event boundary, the crash from following a hot libc export, and an offline protobuf round-trip that caught a defect in its own decoder |
| `EXTENSION-kernel-ondevice.md` | The MT Manager APK MCP probe, the module-environment facts it could verify, and the kernel routes that this device's 4.14 kernel puts out of reach |

## Benchmark-pass record

The benchmark pass put **public targets** under the documented routes — `tests/benchmark.md` is the
matrix, and these files are the evidence behind its rows. Same three labels. Several of these rows
came back negative, and four of them overturned a conclusion this repository had already recorded;
those are called out in the matrix rather than buried here.

| File | Covers |
|---|---|
| `EXTENSION-benchmark-l1-l3.md` | The first two matrix rows: the L1 equal-length patch -> repack -> re-sign chain with its on-screen behaviour change and its zero-change control, and the L3 time-to-death baseline, the two spawn/patch/detach orderings that cannot work, and the terminate path that patching the obvious death site does not stop |
| `EXTENSION-extraction-shell-bench.md` | `dex_dump_validate.py` against an 11-variant skeleton set: the trivial-body ratio as a bimodal result rather than a threshold, the three script defects the variants exposed, and the ranking that pointed at a modified image until independent review caught it |
| `EXTENSION-stalker-exclude.md` | Stalker exclusion measured across three arms: the no-follow baseline, the follow that kills the process, and the follow with 20 modules excluded that survives but still delivers zero events |
| `EXTENSION-java2c.md` | Java2C against JNI sinking: native-declaration density roughly 2000x apart, why a `Java_*` symbol search fails silently, and the Dex-to-C build chain no toolchain on this host could complete |
| `EXTENSION-vmp-diff.md` | The known-plaintext differential: a 218-of-224-opcode coverage fixture, a closed-loop check that recovered 218/218 mappings with zero fabrications, and the one link that cannot be automated |
| `EXTENSION-kernel-weapons.md` | The generated KernelSU/APatch scaffold and its three kernel-side templates, all shipped unbuilt, plus the structural correction that a userspace module cannot change a syscall return value |
| `EXTENSION-split-apk.md` | Two real split sets through both branches: unified re-signing, the merge that is refused by design, the merge that succeeds, and the signer chain this host actually needs |
| `EXTENSION-reconstruction.md` | The reconstruction pass: the doctor capability closure (a JDK-only PATH used to report "can re-sign", now `BLOCKED` with a next action), the zip rebuild that stops dropping per-entry metadata (`zipalign -c -v 4` fails the old output and passes the new), and `check_commands.py` catching a documented flag that does not exist |
| `EXTENSION-test-harness.md` | The executable half of the evidence: what `tests/` asserts and what it measured, the `dex_patch_bytes` regression reproduced byte-for-byte, the 153 skips and 26 xfails that form the exit-code work order, the device-bound exclusion forced by an incident where the suite drove a real phone, and CI written but never run |
| `EXTENSION-rasc.md` | The Rust ASC measured against the Python one: identical class-definition sets on two archives, the speedup per scenario, the build (no prebuilt artifact exists, and a 32-bit MinGW cannot link it), and **the enum shape whose method bodies it drops with no warning** |
| `EXTENSION-protobuf-raw.md` | A schema-free decoder cross-checked against the official runtime and a real DataStore container, with the packed-boundary and proto3-zero ambiguities reproduced on real bytes |

## Absorption-pass record

A later pass absorbed mechanics from external skill repositories (`reverse-skill`,
`awesome-game-security`, `android-reverse-engineering-claude-skill`, `MobileRE-Skill`), keeping each
project's own discipline: only the phase, the checklist and the command pattern cross over, with the
source URL and the access date recorded, and nothing vendored as a runtime dependency. These files
live here rather than in the skill because two of them corrected a claim the repository had already
written down.

| File | Covers |
|---|---|
| `EXTENSION-desensitization.md` | The leak scanner's rules and exemptions, its four `RESULT=` states and exit codes, the escaping false positives, and **the pass that found its own evidence file leaking 26 strong hits** — the fixture's literal match values, quoted to prove the rules fire |
| `EXTENSION-dart-aot-formats.md` | Two string-table claims tested against a real dual-ABI Flutter app: the arm64 packed scheme confirmed against literal tag bytes, and the assumed armv7 `len*2`/UTF-16 form **refuted** — the 32-bit record is `[header u32][byte-count u32le][UTF-8]`, and the extractor's zero is a format mismatch rather than an empty table |
| `EXTENSION-detection-pipeline.md` | Naming the check that fires: three arms on a public MASTG target (control alive, probe arm dead in ≈300 ms via `strstr("frida")`, with the `TracerPid=0` versus 4-frida-mappings asymmetry), `svc_scan.py`'s two decoders agreeing on an identical 214-site set, the layered Java-to-svc descent, and the ptrace-free dump boundary on targets whose dex is deflated inside the APK |

## Adding a run

Record the tools, versions and exact commands, and label each claim. Keep target-specific facts out:
what belongs here is what a future reader can apply to a *different* APK — a defect, a measured
cost, a method that did or did not work, and the cross-check that settled it.
