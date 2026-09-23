# Known limitations — what an installed copy cannot do, and what was never measured

This file exists because of how the skill is delivered. `npx skills add` installs `skills/apk-reverse/`
and nothing else, so the evidence record this skill was measured against — which sits at the
repository root — is **not present in your install**. Every claim in `SKILL.md` and in `references/`
still carries a strength label; this file and `references/evidence-summary.md` are what let you read
that label without the record it came from.

Read this before treating any "this was measured" statement as covering the route you are about to
take. Silence in this list is not support for a route; it means nobody here paid for the counters yet.

## Strength labels

- **observed** — a command was run and its output exists behind the claim.
- **inferred** — follows from a documented mechanism or a neighbouring measurement; the step itself
  was not executed.
- **unverified** — assumed, or reported by someone else, and not reproduced in this record.

A row whose strength is `unverified` is a statement about *this skill's evidence*, not about the
mechanism's truth. It means nobody has yet put a command and its output behind it here.

## Dependencies this skill does not ship — name them before the workflow starts

- **Dart AOT analysis needs a snapshot dump.** The workflow begins at a snapshot text file; producing
  it needs a snapshot container resolver this skill does not contain and cannot synthesize. Ship a
  pinned front end (`aotopsy`, pure Go, no toolchain) or build `blutter` (about 80 s, needs a C++
  toolchain) — and **say which one**, because the two report different Dart version labels for the
  same binary. The two offset spaces are not a constant offset apart: one tool reports file offsets
  while the pool index speaks pool offsets, and a measured run found 4,237 distinct deltas over 4,241
  shared strings. Never describe the object pool as something this skill decodes on its own.
- **The Android build-tools are not on PATH here.** `aapt2`, `D8`, `apksigner`, `zipalign`, `dexdump`
  and `split-select` all live in a build-tools directory and must be passed explicitly. The measured
  signing order is zip, then `zipalign -p -f 4`, then `apksigner.jar --v1 --v2 --v3`; reversing it is
  refused by the installer. There is no `uber-apk-signer` on this class of host, and no `apktool`,
  `jadx`, `gradle`, NDK, host or device clang, `android.jar`, or smali/baksmali jar.
- **The runtime routes need a real device.** Hooking, dumping, install-then-launch verification and
  the module route all require a rooted device; several of them additionally require a framework the
  device must have active.
- **The evidence record and the benchmark matrix do not ship.** Their paths appear in older
  documents as if they were openable files. They resolve only in the repository they were written in.

## Capabilities with no footing in an installed copy

These are not "hard"; they are paths where nothing in this record is evidence either way, so a plan
built on them has nothing to check itself against.

- **Producing a Dart AOT snapshot dump.** This skill ships no resolver for it. See the dependency
  section above.
- **Kernel-side syscall answer forging.** The generator is measured; **no kernel-side artefact was
  ever compiled or loaded**. The tested kernel is 4.14.186 (eBPF needs 5.10+), the host has no
  `aarch64` cross-compiler, `make` or `ndk-build`, and there is no kernel source. One structural
  correction survives without a measurement and is worth more than the templates: **an ordinary
  KernelSU module is a userspace module and cannot change a syscall return value.**
- **Unity / IL2CPP logic recovery, React Native / Hermes bytecode and Cordova internals, and every
  iOS or `.ipa` workflow.** The runtime can be identified; the logic recovery is not covered, and
  there is no verified recipe for locating a method inside `libil2cpp.so` plus `global-metadata.dat`.
- **Defeating a server-side authority.** This skill determines *who owns a gate*, not how to break an
  authorization the server performs. Report it as a residual instead of patching harder.

## Routes that were never exercised

- **The packer, code-virtualization, custom-linker, integrity-check-redirection and tamper-suicide
  scenarios were never run end to end.** The target used for the first verification pass has none of
  those features, and its unmodified build already fails to start — which removes the
  repack-and-regress loop those scenarios need. The packer tooling was recorded as *not applicable to
  that sample*. The benchmark pass measured **shape discrimination** on public targets; it did not run
  a live extraction shell. Anything you read here about a protected target is `inferred` unless it
  says otherwise.
- **Scripts from the first pass that carry no measurement** (absence is not a verdict on them):
  the crash tools, the APK differ, the screenshot tool, the installer test, the repacker, the
  equal-length patcher, the instruction finder, the verifier checker, the class differ, the string
  patcher, the smali tools, the DataStore injector, the API prober, the TLS checker, the USB network
  helper, and the device shell helper. The benchmark pass has since run some of these; the rest are
  still unmeasured, and the references say so where it matters. `grab_crash.py` is the sharpest
  example: it claims to recover a stack a crash-reporter SDK swallowed, and it was never tried — on
  the one target that presented exactly that situation.
- **Steps that a route needs but that were not executed**, so the route is not end-to-end:
  installing a re-signed split set and confirming it launches; installing, launching or getting a
  refusal from the VMP-boundary sample; the native certificate-pinning row (it needs a gradle+NDK
  build this host cannot do); an end-to-end Dart string patch repacked and installed; and byte
  agreement between two independent dumpers.
- **No real OLLVM trace and no trace pipeline verified on a device.** Exclusion keeps a target alive
  but does not restore event delivery, and a zero-event trace is a boundary to identify rather than a
  recipe to follow.

## Conclusions that changed — an older copy may still state the old one

Each of these was a claim this skill used to make and no longer does. If you are reading a copy or a
cached page that states the old version, the old version is wrong.

- **"Tens of percent means an extraction-shell skeleton."** Deleted. The ratio is **bimodal, not
  thresholded**: a real skeleton reads about 100 %, a zero-change control 1.9 %, nop-cleared bodies
  0.0 %, throw stubs 1.9 %.
- **A VMP verdict withdrawn.** A hand-written opcode table reported 1,393 of 22,424 bodies as
  undecodable and that was read as private opcodes; the platform decoder found 34,566 instruction
  decodes and **zero structural errors** on the same file. The surviving rule: never declare a VMP
  without an official disassembler's failure count.
- **"Exclusion fixes the zero-event trace."** It does not. Exclusion is what keeps the target alive;
  delivery stayed at zero in the treatment arm.
- **"`repack.py` has no apksigner signing path."** That conclusion expired mid-pass when the path was
  added; the signing chain was then measured end to end.
- **The armv7 Dart string-table form is UTF-16 with a `len*2` length.** Refuted at the byte level:
  the 32-bit record is `[header u32][byte-count u32le][UTF-8 payload]`, and the extractor's zero for
  that ABI is a format mismatch rather than an empty table.
- **A documented tool flag that does not exist, and a documented tool class that does not match the
  shipped script.** Where a reference names a command or a tool class, check it against
  `scripts/` in this install before running it — the script is the measurement, and a reference line
  can lag behind it.

## What an installed copy can answer, and what it cannot

| Question | Answerable here | Not answerable here |
|---|---|---|
| Is this capability proven, and how strongly? | `references/evidence-summary.md`, `evidence/capability-matrix.json` | The exact commands and captured output behind it |
| Which capability is outright blocked? | `evidence/capability-matrix.json` rows with status `blocked` | Whether the mechanism would work on your target |
| Which tool versions was this measured on? | `evidence/tested-tool-versions.json` | Versions this skill was never measured on — that list is there too, but it is a list of gaps, not of results |
| What does the skill deliberately not cover? | `references/coverage-and-limits.md` | — |
| What is the exact output of a past run? | — | The record at the repository root, which does not ship |

## Failure modes this file exists to prevent

- Reading "a command was run" as "the command was correct". A tool that runs without error is not a
  tool that is right: one script here produced a false negative on a symbol that exists and is called,
  and another returns a clean "no references" answer for input it cannot read at all.
- Reading `inferred` as `observed` because the surrounding prose is confident.
- Reading `unverified` as a refutation. It is an absence of evidence here, not evidence of absence.
- Reading silence in the "never exercised" list as support for a route.
- Calling a route verified when the install step was never run. Several routes in this skill stop
  exactly there, and an artifact that installs is not the same artifact as one that launched.
- Treating a documented version requirement as a measured one. The version table lists what was read
  off the tools, and separately lists the versions nothing here has ever run on.
