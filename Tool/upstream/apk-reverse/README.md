# apk-reverse

An Agent Skill for Android APK reverse engineering, debloating, ad removal, surgical
dex patching, repacking, and runtime/server analysis.

It is a **skill**, not a tutorial: it is written to be loaded by an agent (Claude Code,
Codex, or any harness that supports the Agent Skills format) while it works, so it is
organized for progressive disclosure — a short decision-oriented `SKILL.md`, detailed
references loaded only when a step needs them, and parameterized scripts you can run
directly.

## How an agent is expected to consume this

`SKILL.md` is deliberately written as a **procedure with gates** rather than as advice, because the
observed failure mode is not ignorance — it is a model reading the whole thing, agreeing with it, and
then reasoning from first principles anyway.

So there are four things in the body that are meant to be *acted on*, not read:

- **Four override rules (R1–R4).** Where they conflict with the current plan, they win until evidence
  overrides them.
- **A symptom index.** Each row is a failure that has already been paid for. **A matching row is a
  stop signal**: load that file before running another command, rather than after a few more attempts.
  Reasoning past a known symptom is how the same hours get spent twice.
- **Four gates (G1–G4),** each an action with a pass criterion. "I understand the idea" does not clear
  a gate. They exist so that classification, environment truth and a control build happen *before*
  the first patch, not after the third failure.
- **A two-strike rule and stop conditions.** Two failures of the same shape mean the model is wrong,
  not the parameters. The third variant of a hypothesis that already failed twice is where rounds go
  to die.

And one thing at the end that is meant to be *withheld*: **"done"** has a definition (six items). A
clean log is not one of them. Anything short of all six is a checkpoint, and should be reported as a
checkpoint with what remains.

If you are an agent reading this: the cheapest possible first command is
`python skills/apk-reverse/scripts/doctor.py`. It tells you which of these tools exist here, which
scripts can actually run, and whether something in the environment is already poisoning your
measurements.

## What it is good at

- Deciding **fast** whether a request is even achievable client-side, instead of
  burning hours on a paywall that is enforced by a server.
- Deciding **what form the deliverable must take** before any work starts — an
  unrooted, self-contained artifact is a different problem from "make it work on this
  machine", and confusing the two is the most expensive drift in this domain.
- Choosing the **safest patch layer** for a given change, and avoiding the layers that
  break the app.
- Catching the repack failure that looks like success: an app that installs, launches and
  renders perfectly while **every signed request is rejected**, because the client derives its
  request-signing key from its own signing certificate.
- Separating **your own mistakes from the app's or the server's problems** — a
  feature-scoped failure (login, registration, payment) is often a TLS/certificate issue on
  one code path, not a consequence of the patch you just built. Device state, a dead device
  server and clock drift masquerade the same way.
- Establishing **which architecture and which library are actually executing**, rather
  than trusting what the manifest ships or what the device claims.
- Working through **packed/hardened targets**: identifying the packer, unpacking, and turning a
  memory dump back into a patched, installable APK.
- Handling a **hardened library that terminates the process on purpose** — including the
  deliberate-crash shape (`fault addr 0x4`) that looks exactly like an ordinary null-dereference
  bug, and the "neutralise it, but never by making it *not return*" rule that decides whether the
  fix works or freezes the whole app in a way that looks nothing like the cause.
- Knowing **which tools to reach for and where each one lies** — including the ones that only
  exist as a GUI, so you ask for a human instead of silently substituting a weaker method.
- Making a patched build **stay** patched: neutralising version checks, forced-upgrade dialogs and
  self-update installers so the work cannot be switched off remotely — and recognising the
  hot-update/remote-config channel that can quietly undo it without any version change.
- Separating a **client-side sign-in gate** (patchable) from an **account-scoped resource** (empty
  because the server has nothing to answer with), and knowing that forging a session produces a state
  worse than being signed out.
- Keeping a **long task honest**: a live record, graded conclusions, calibrated timeouts, and
  bounded waits, so progress is not lost and the same mistake is not made twice.
- Avoiding the specific mistakes that produce an APK that builds perfectly and dies at
  runtime.
- Deciding **what the deliverable should be when an APK is not an option** — a repack refused by
  several independent checks is *blocked*, not expensive, and the fallback ladder is a system-level
  module, a local RPC service, or an honest report with a stated boundary.
- Telling a **real memory dump from an extraction-shell skeleton**, and knowing which recovery route
  applies — including the root-side dump for when `frida` itself is refused. What the measurement can
  and cannot see is in `skills/apk-reverse/references/advanced-unpacking.md`.
- **Calling a routine instead of reversing it** when reversing costs more than invoking: emulated
  execution on the host, or a live function service-ified over Frida RPC.
- Reading **instruction-level execution evidence** when a native function has been flattened into a
  state machine by OLLVM — including the two ways Stalker was measured to bite back on a real device.
- Recognising when **userspace hooking cannot reach the check at all** (raw `svc` syscalls,
  `init_array`-early detection), what the next layer up and down can actually do, and when escalating
  is the wrong answer.
- Working **protocols that are not REST** — protobuf without a schema, gRPC, QUIC/HTTP3 — and
  native-side certificate pinning that ignores the system trust store.
- Working **from the phone itself**: MT Manager's edit/repack/sign flow and its APK MCP surface,
  LSPosed Manager, and on-device data inspection, alongside the PC toolchain rather than instead of it.
- Telling **Java2C apart from an extraction shell** before spending hours hunting a decrypted DEX that
  does not exist at any point in the process lifetime — the code was compiled into a `.so`.
- Handling a build that arrives as a **split APK / App Bundle set**: reading the set off a device,
  signing every member with one keystore for `pm install-multiple`, or merging code/native members
  into a standalone APK when that is legal.
- Working a **real Dex VMP** with the known-plaintext differential — which links can be automated and
  which cannot, what a compiled fixture can and cannot reach, and how to *prove* a derived
  private-opcode table instead of asserting one.
- **Publishing what it learns without publishing the target** — a scanner that reports identity
  shapes with their context, an explicit list of what must *not* be redacted (tools, libraries,
  protocol fields, CVEs, hardening products, public crackmes) because redacting those destroys the
  reusable part, and exit codes that gate a commit.
- Reading a **precedent** before repeating work this repository already converged on: the positive
  half of the record, with the route including its dead ends, a grade on every assertion, and the
  files the case says to write back to.

## Structure

`SKILL.md`, `references/` and `scripts/` are all inside the skill directory, `skills/apk-reverse/`.
Everything at the repository root is maintenance tooling shared across skills, not part of an
installed skill.

```
SKILL.md                  a procedure with gates, not background reading:
                          how-to-use  -> four override rules (R1-R4)
                          symptom index (a matching row is a stop signal)
                          four gates (G1-G4, actions with pass criteria)
                          thirteen classification questions
                          the workflow, with a per-step skip condition and a two-strike rule
                          what "done" means  ->  stop conditions  ->  constraints  ->  indexes
references/               loaded on demand, one topic each
  recon.md                    identify packer, SDKs, code location, tamper checks; unpacking
  server-config-and-updates.md
                              the most common shape of "ad" and the one usually mis-diagnosed:
                              the server supplies UI the client renders (launch screen, popup,
                              announcement, tab set). The two-layer fetch that proves it, how to
                              find the config DTOs by the field names data classes keep, why you
                              patch the decision and not the data, deciding the scope of "remove",
                              and remote re-enable / cached config durability
  byte-level-patching.md      equal-length byte edits: why they beat method rebuilding (measured),
                              locating an instruction's exact offset without scraping listings,
                              the instruction width traps that desynchronise a decode, neutralise
                              a branch vs redirect it, dex header integrity field order, and the
                              verifier's move-result rule
  packers.md                  hardened targets: rejection signals, measuring the validation
                              boundary with single-variable tests, choosing a native host
  code-virtualization-and-custom-linkers.md
                              the layer between "packed" and "clean": whole classes turned into
                              `native` declarations, a private loader whose SONAME does not match
                              its filename, an embedded self-decrypting payload, a Java-layer
                              "signature killer" that logs success while a native check kills you.
                              The keep-it/drop-it deadlock, how to separate the *checker* from the
                              *implementation*, and the string-redirect technique that ends it
                              without neutralizing anything
  framework-runtimes.md       Flutter / React Native / Unity: which layer owns the UI, and how to
                              find logic when there are no symbols (string encoding traps)
  dart-aot.md                 Dart AOT in depth: version pinning and building a matching decompiler,
                              the object pool and reference indexes, register/boolean conventions,
                              the three signatures that identify business logic, locating, patching.
                              Begins with the snapshot-decoding front end it depends on (aotopsy or
                              blutter) because the pool listing is an input, not something this skill
                              produces itself
  native-and-so.md            .so hosts, DT_NEEDED vs JNI_OnLoad, relocation limits,
                              relocation-free bootstrapping, replacing Java methods natively,
                              and which ABI/library is *actually loaded and executing*
  native-tamper-and-suicide.md  how a hardened library kills its own process: the visible
                              mechanisms, how to tell which one actually fires, how to find the
                              site, forged section headers, function boundaries from
                              PT_GNU_EH_FRAME, scanner traps, and neutralising safely
  detection-and-anti-analysis.md  when the app fights back or the tool cannot run here: telling
                              detection apart from a broken environment, deciding by cost instead
                              of escalating, recognising an environment where dynamic analysis
                              simply does not work, and keeping the "blocks my analysis" question
                              separate from "blocks the deliverable"
  toolchain.md                what to install, how to invoke it non-interactively, which tools
                              are GUI-only, version-alignment traps, working offline,
                              **"not on PATH" is not "not installed"**, and which signer to use
  long-task-discipline.md     live record, conclusion grading, drift control, timeout and
                              wait calibration, deliverable-form drift, captures-you-never-looked-at,
                              long-context decay, handover
  ad-removal.md               ad taxonomy, wrapper mapping, callback trap, global gates, verification
  updates-and-forced-upgrade.md  keeping a patched build alive: locating the version check, the
                              two-layer patch (no-op the routine, neutralise the comparison), what not
                              to touch (manifest version, installer permission, host blocking),
                              self-update and hot-update/remote-config channels, verifying that no
                              version request is issued at all
  account-gates.md            sign-in walls, forced phone binding, guest mode: telling a client-side
                              gate (patchable) apart from an account-scoped resource (not), why
                              fabricating a session is worse than staying signed out, and the
                              unavoidable session loss after a reinstall
  signature-derived-keys.md   when the app's own signing certificate is used as key material:
                              detection greps, why offline extraction is unreliable, the
                              hardcode-then-verify procedure
  membership-and-limits.md    server vs client authority; what is and is not patchable
  server-api.md               probe an app's API; prove who owns the gate
  tls-and-cert.md             feature-scoped network failures: expired certs, dual trust chains
  third-party-builds.md       auditing a "cracked"/"modded" APK before trusting it
  dex-patching.md             patch-layer table + dexlib2 technique in depth
  patch-audit.md              proving a patch *landed* and is *legal*: length-vs-bytes
                              comparison, the equal-length-replacement blind spot, verifier-level
                              legality (move-result adjacency) checked statically, text-matching
                              patch traps, and reporting a missing patch
  repack-and-sign.md          repack rules, unpack-and-repack, signing, post-install hazards
  runtime-data.md             DataStore / SharedPreferences / SQLite / protobuf; when the app
                              rewrites your edit, and decoding a value that looks encrypted
  dynamic-frida.md            Frida setup, version pinning, the four-layer probe, hook strategy
  environment.md              device/emulator setup, root, ADB, offline devices, log signals,
                              emulator console control and recovery, preflight, look-at-the-screen
  verification.md             the claim ladder; what "done" means
  desensitization-and-leak-scans.md
                              publishing discipline: what must be desensitized and what must stay,
                              the do-not-anonymize list, the leak scanner and its exit states, and
                              the entry-point file as a prompt surface
  precedents/                 the positive case library: route including dead ends, a grade per
                              assertion, measured pit-falls, and the write-back checklist
  routing.md                  the on-demand inventory: every reference with when to load it, every
                              script with what it does, and a mirror of the symptom index
  rasc-and-droidsaw.md        the Rust re-implementation of the ASC indexer: measured speedup and
                              identical class sets, the enum shape where it silently drops bodies,
                              and how to build and verify it
  evidence-summary.md         the condensation that ships with the skill: capability, one-line
                              conclusion, strength, and the evidence you can actually open in an
                              installed copy

  ../evals/                   NOT a spec directory either, but the location the Agent
                              Skills guidance recommends: `evals.json` holds the
                              with-skill / without-skill cases this skill has **not** run,
                              with the method for running them written into the file
  ../evidence/                NOT a spec directory: the machine-readable companions to the evidence
                              summary reference above -- `capability-matrix.json` (the same rows with
                              more fields), `tested-tool-versions.json` (versions and the probe behind
                              each), `known-limitations.md` (the installer-facing limit list). Shipped
                              inside the skill so an installed copy can answer "was this verified, and
                              how strongly" without the repository
  pitfalls.md                 the failure catalogue -- read before building
  advanced-unpacking.md       the dump landed but the bodies are empty: extraction-shell diagnosis by
                              trivial-body ratio, FART-style active invocation and why its classic hooks
                              died on Android 12-16, code_item splicing, the root-side dump for when
                              frida itself is refused, and the honest VMP boundary
  lsposed-and-modules.md      the repack is refused, so deliver a system-level hook module instead:
                              module anatomy, a gradle-free build chain, scope configuration and how to
                              verify injection, and the layer a Java module cannot reach
  emulation-and-rpc.md        call the routine instead of reading it: Unidbg/Unicorn emulation and its
                              environment-filling cost, versus service-ifying a live function over Frida RPC
  native-dbi-and-deobfuscation.md
                              OLLVM shapes, Frida-Stalker traces, the trace-to-CFG route, the
                              Stalker/QBDI/emulation decision, and two measured boundaries (a follow that
                              delivers no events, and a crash from following a hot libc export)
  protocol-reverse.md         protobuf without a schema, schema recovery from decompiled code, gRPC frame
                              capture, the QUIC/HTTP3 limit, and native-side certificate pinning
  kernel-and-environment-hardening.md
                              userspace hooking provably cannot reach the check: raw `svc`, init_array-early
                              detection, what each root scheme hides, the kernel-route map with its version
                              gate, and when to stop escalating
  on-device-tooling.md        working from the phone itself: MT Manager edit/repack/sign and its APK MCP,
                              LSPosed Manager, Termux+frida, on-device data inspection
  java2c-and-jni-sinking.md   Java2C and JNI sinking, the two hardening shapes most easily confused
                              with an extraction shell: the table that separates landing shell /
                              extraction shell / VMP / Java2C / JNI sinking, why the code is in the
                              `.so` and *never* in a dumped dex, and why a `Java_*` symbol search
                              comes back empty (dynamic registration, `-fvisibility=hidden`)
  split-apk.md                App Bundle / split APK sets: what the set is, pulling it off a device,
                              merging into one APK vs signing the set as a unit, the install refusals
                              and what each means, and making an installable fixture from a pulled set
  vmp-differential-analysis.md
                              the known-plaintext differential for a real Dex VMP: which links can be
                              automated and which cannot (the upload is the bottleneck), the coverage a
                              compiled fixture can reach, how to *prove* a derived private-opcode
                              table, smali generation, and when the route is closed
  coverage-and-limits.md      the claim ladder applied to the skill itself: the evidence behind each
                              covered item, the dependencies this skill does not ship, and what was
                              never exercised
  handoff-boundaries.md       where this skill ends and another discipline begins: the JNI form
                              table, the packer-versus-loader split, and what "verified" means for
                              each of the four deliverable forms
scripts/                  parameterized, path-agnostic
  doctor.py                   run this first: capability report + per-script runnability, finds
                              tools installed off-PATH or as runnable jars, and surfaces the
                              environment facts that poison experiments (clock skew, leftover
                              adb forward / proxy, a device-side frida process already running)
  dexutil.py                  dependency-free dex reader: structural walk + exact instruction
                              decode, dex header recompute/verify (correct checksum/signature
                              order), branch-target and operand helpers. Library shared by the
                              dex scripts, also runs standalone to dump one method with offsets
  dex_find_insn.py            locate an instruction by decoded semantics and print its exact byte
                              offset with context and both sides of any branch -- how you find a
                              patch site instead of guessing offsets
  dex_patch_bytes.py          equal-length byte patches from a JSON spec: semantic match, polarity
                              pin via expect_next, equal-length enforcement, verifier check, dex
                              header recompute, re-decode to prove it landed (--dry-run first)
  dex_check_verifier.py       tier-3 check: does any conditional branch target a move-result
                              (bypassing its producer)? Compares two builds and separates
                              pre-existing findings from regressions your patch introduced
  coldstart.py                cold-launch capture: timed screenshot burst + logcat signals +
                              installed-build facts + launch timing, and warns when the foreground
                              activity is not your app
  so_constpatch.py            same-length in-place rewrite of an isolated string constant, for
                              redirecting a library load instead of defeating a check
  smtool.py                   baksmali/smali wrapper with a configurable classpath
  dexpatch/                   dexlib2 method-level rewriter (for changes that need new instructions)
  patch_smali.py              method-body replacement in a smali tree
  dex_strpatch.py             byte-level string patch with a string_ids ordering guard
  dex_classdiff.py            prove a dex edit was surgical
  dex_strings.py              strings/URLs/SDK markers without a decompiler
  dart_pool_strings.py        recover literals from a Dart AOT snapshot (framed entries, the
                              one-byte vs UTF-16 split, file offsets, run-length noise filter)
  dart_pprefs.py              build/query the object-pool -> code-site index for a Dart snapshot
  dart_disasm.py              annotated windowed disassembly of Dart AOT code + B/BL caller index
  find_refs.py                count callers of a method before patching it
  repack.py                   rebuild APK, strip only signatures, keep META-INF/services/, write a
                              4-byte-aligned archive (resources.arsc STORED+aligned), sign, verify;
                              also split APK / App Bundle sets: inventory, sign every member with one
                              keystore, or merge code/native members into a standalone APK
  devsh.py                    quoting-safe ADB shell helper
  usb_net_proxy.py            give an offline device network over USB
  datastore_inject.py         encode/inject AndroidX DataStore preferences safely
  probe_api.py                probe an HTTP API with the right headers
  grab_crash.py               recover stacks hidden by a crash-reporter SDK
  install_test.py             install + launch health check with logcat signal scan
  frida_probe.js              four-layer runtime probe (app net layer + OkHttp + java.net + exceptions)
  run_probe.py                inject the probe, stream it to a log file, stay resident
  tls_check.py                strict certificate check for one or more hosts
  preflight.py                environment check before every experiment block (device, root,
                              ABI/translation, clock skew, leftover proxy/forwards, dead server)
  lib_map.py                  what is *actually mapped* into a live process: per-library path,
                              base, architecture, and whether it came from the APK or was
                              materialized at runtime
  elf_plt.py                  resolve a PLT stub to its imported symbol (x86_64 + aarch64) from
                              the relocation table; list a symbol's callers; byte-diff two
                              libraries and name the symbol each changed stub belongs to
  apk_diff.py                 entry-level diff of two builds: changed / added / removed, by
                              content hash so same-size replacements are caught
  native_crash.py             locate a native death from a log or tombstone: signal, fault
                              address, registers, frames split app vs system, the faulting
                              instruction, and a flag when the fault looks *arranged*
  blob_decode.py              search, don't guess, the framing of a stored value
                              (base64/hex x rotation x deflate); re-encode the edited payload
  snap.py                     bounded burst screenshots + control-tree capture with a stall
                              detector, and a verdict on whether the tree is usable at all
  sig_probe.py                find the exact signatures[0].toCharsString() value — offline
                              candidates from an APK, or the authoritative read from a device
  spawn_patch_detach.py       spawn under a Frida probe, detach, then launch and capture: under
                              spawn mode the Activity stack often never comes up, and memory
                              writes survive detach while hooks do not
  hook_patch_only.js          the minimal probe for spawn_patch_detach.py — neutralise one native
                              death site by offset and report PATCHED
  dex_dump_validate.py        dedupe, validate and rank a directory of dumped dex images: sha256
                              grouping, header integrity, the trivial-body ratio that separates a real
                              dump from an extraction-shell skeleton, and a most-likely-original ranking
                              (--trim for page-aligned /proc/<pid>/mem captures)
  dex_mem_scan.py             search memory captures for embedded dex images and extract each at the
                              size its own header declares -- for a decrypted dex sitting in an
                              anonymous mapping no maps entry names
  lsposed_scaffold.py         generate a minimal LSPosed/Xposed module project (manifest with the
                              xposed meta-data, assets/xposed_init, hook class, gradle-free build notes)
  frida_rpc_serve.py          bridge a Frida script's rpc.exports to a local caller with reconnect
                              handling, so a live native function can be called rather than reversed
  rpc_template.js             the editable companion to frida_rpc_serve.py
  stalker_trace.js            instruction-level tracing with Frida Stalker: configurable targets,
                              trigger selection, the event stream, and output-size rules
  stalker_report.py           reduce a stalker_trace.js log to block histograms and call sequences,
                              with an explicit diagnostic for the measured zero-event case
  mt_mcp_probe.py             probe MT Manager's on-device APK MCP (Streamable HTTP, port 8787):
                              JSON-RPC handshake plus the grouped tool inventory
  java2c_probe.py             collect the evidence that separates Java2C from an extraction shell, a
                              VMP and ordinary JNI sinking: native density and stub ratio from the dex,
                              JNI_OnLoad / dynamic registration / toolchain strings from the `.so`,
                              each item labelled strong/medium/weak
  protobuf_decode_raw.py      schema-free protobuf decode: hex / file / stdin to a JSON tree, every
                              length-delimited field kept as a candidate set with ties labelled rather
                              than guessed, plus a byte-exact re-encode to check a round trip
  vmp_diff_harness.py         build a labelled opcode-coverage fixture, derive a candidate private-
                              opcode map from an original/hardened dex pair, verify the comparison in a
                              closed loop, and render a restored stream as a smali skeleton
  kernelsu_syscall_mask.py    generate a KernelSU/APatch syscall-masking scaffold: an installable
                              userspace module skeleton plus KPM/LKM/eBPF kernel-side templates, each
                              with its version gate and an explicit unverified label
  rasc_build.py               build and verify rasc, the Rust ASC re-implementation:
                              --check what is present, --build clone plus cargo, --verify an APK
                              against droidasc and fail on any class-set difference
  scan_leaks.py               scan a repository for target identity before publishing it: bundle ids
                              in manifest / `pm` / `ps` contexts, serial-shaped tokens, PATs, inline
                              appkey assignments, literal endpoints, host user paths. Exemptions for
                              everything that must stay (tools, libraries, CVEs, hardening products,
                              public crackmes, placeholders), findings carry their context,
                              `--show-exempt` prints why a hit was suppressed, exit 0/1/2
  svc_scan.py                 name the syscall behind an inline `svc` and the segment it sits in,
                              which decides whether a libc-level hook can observe the call at all;
                              `--context` shows neighbours because a byte scan also matches data
  anti_detect_probe.js        observer-only Frida probe (patches nothing): path/loader/thread/kill
                              hooks with caller module + offset, an environment self-report
                              (`TracerPid`, frida-named mappings), and live streaming so a sub-second
                              self-destructing target still yields evidence
```

The repository also carries an **executable** test layer, which is a different thing from the
evidence record: `tests/` asserts what the scripts do (unit, CLI contract, no-device
integration) and `tests/benchmark.md` records what a route did on a real target. `tests/README.md`
states the split, and `.github/workflows/ci.yml` runs the gates plus the suite.

## Install

This repository is a **skills repository**: the skill lives at `skills/apk-reverse/`, which is the
layout the `skills` CLI resolves, and it is installed by name rather than by copying a directory:

```
npx skills add newliver666/apk-reverse              # install every skill in the repo
npx skills add newliver666/apk-reverse --list       # list what is here, install nothing
npx skills add newliver666/apk-reverse --skill apk-reverse -y
npx skills use  newliver666/apk-reverse@apk-reverse # use it once, without installing
```

The CLI symlinks the skill into your agent's skills directory by default (`--copy` makes independent
copies instead), and `-g` installs for every project rather than the current one. With one skill in
the repository, `--skill apk-reverse` is redundant today; it is written out here because it is what
selects a single skill once a second one exists.

Once installed, the agent loads `SKILL.md` when a task matches its description, and pulls in
`references/*` only as needed. No global state, no machine-specific paths, and no build step.

## Requirements

Nothing is mandatory; each script checks what it needs. `skills/apk-reverse/scripts/doctor.py` reports
which of these are present here, which scripts can therefore run, and — usefully — which tools exist
somewhere other than PATH.

If your toolchain lives outside PATH (a project-local `tools/` directory, a versioned SDK folder, a
runnable `.jar` instead of a command), set `APKREV_TOOLS` to one or more directories and `doctor.py`
will find them:

```
set APKREV_TOOLS=<dir>;<dir>                     # Windows, e.g. an SDK or project-local tools dir
export APKREV_TOOLS=<dir>:<dir>                  # POSIX
```

The scripts themselves are plain `python3` and are intended to work identically on Windows, macOS and
Linux; where a snippet is POSIX-only it is labelled. Nothing here assumes a Unix shell.

| Tool | Used for |
|---|---|
| Python 3.9+ | all scripts |
| **`droidasc`** (ASC) (**optional but strongly recommended — install this first**) | whole-APK cross-reference index: `findrefs` / `listclass` / `getclass` / `getmanifest`. One `pip install droidasc`, no JVM, no SDK, no index build. Turns "which of N thousand classes mentions this string" into a sub-second query, and it is the only route to a class whose name R8 mangled. **This is the tool an agent should reach for before any full decompile** — see `skills/apk-reverse/references/toolchain.md` §droidasc (ASC) — ask an APK "who references this?", in one query |
| `ddc` (optional but strongly recommended) | single-binary dex→Java decompiler with query subcommands (`info`, `findrefs`, `strings --with-locations`, per-class decompile). No JVM. **Reads** what ASC **locates**; also reports package identity reliably — see `skills/apk-reverse/references/toolchain.md` §ddc — dex-to-Java with query subcommands (worth adopting) |
| `baksmali` / `smali` + `dexlib2` jars | disassembly, assembly, surgical patching |
| JDK (`javac`, `java`) | building/running the dexlib2 patcher; also provides `keytool`/`jarsigner` |
| Android SDK build-tools (`aapt`, `zipalign`, `apksigner`) | manifest info, alignment, signing. **`apksigner` is the signer to use** — `jarsigner` rewrites the archive and breaks the alignment Android R+ requires |
| `uber-apk-signer` (optional) | one-step align + sign |
| ADB | device work |
| Frida (host package + matching on-device server) | dynamic analysis |
| a rooted device or emulator | anything beyond static analysis |

None of these need to be on `PATH`: every script accepts an explicit path for the
tools it shells out to, and `skills/apk-reverse/references/toolchain.md` covers finding
an install that `PATH` does not know about (the common case for `apksigner` and
`keytool`).

## Read this first

**This project is published for learning, research and authorized security testing only.** It ships
no exploit payloads, no target data and no third-party binaries — it is a method, a set of scripts
and an evidence record. You are responsible for having the right to analyze whatever you point it at;
see **Disclaimer** at the end of this file.

`skills/apk-reverse/references/pitfalls.md`. It is the most valuable file here — every entry is a
failure that produced a broken artifact while looking completely healthy.

The four that hurt most:

1. Stripping the whole `META-INF/` during a repack deletes ServiceLoader registrations
   and the app dies at startup with an error that names an unrelated library.
2. Patching a byte-level string without preserving `string_ids` ordering gets the whole
   dex rejected, while checksums and signatures verify perfectly.
3. Rebuilding a dex with a whole-tree smali round-trip damages R8 output invisibly —
   class tables compare clean, and it only blows up at runtime.
4. Neutralising a native terminate path by making it **not return**. A spinning stub does not
   suppress the check; it freezes the caller and every thread behind it. The app hangs with *no
   crash record at all*, and the eventual death gets blamed on whatever killed the frozen process.

## Scope

Built for working on your own applications, on samples you are authorized to analyze,
and in CTF/competition sandboxes. It contains no vendored third-party binaries and no
target-specific data.

What it covers, and what it deliberately does not, is stated at the top of `SKILL.md`
under **Coverage**. The short version: Android only (no iOS), and deep on the layers
that have been worked through for real — dex patching, repacking, packers and custom
loaders, native tamper response, and Flutter/Dart AOT. An extension pass added a second
tier of documented routes: **module-side delivery** when a repack is blocked,
**extraction-shell recovery** and its VMP boundary, **emulation and live RPC** for
calling rather than reading, **instruction-level tracing** against OLLVM, **protocol
reversing** beyond REST, the **kernel-side route** map for when userspace hooking is
provably out of reach, and **on-device tooling**. A **benchmark pass** then put public
targets under those routes (`tests/benchmark.md`): it added **Java2C discrimination** (the
misdiagnosis that sends an agent hunting a decrypted DEX that never exists), **split APK /
App Bundle handling**, **schema-free protobuf decoding**, a **Dex-VMP differential** harness,
and **kernel-module templates with their version gates** — and it corrected two earlier claims
whose measurements disagreed with them. Unity/IL2CPP logic recovery,
React Native/Hermes bytecode internals, and defeating a server-side authority are **not**
covered, and the skill is written to say so and stop rather than apply the nearest
documented procedure to a target it was not written for.

Four qualifications that the Coverage section states in full and that belong here too:

- **Flutter/Dart AOT analysis has a dependency.** The workflow begins at a pool listing
  (`pp.txt`-class output). Producing that needs a snapshot-decoding decompiler — aotopsy (a static
  binary, no toolchain) or blutter (built from source, ~80 s) — and this repository does not contain
  one. It is named as a prerequisite rather than left implicit.
- **Not every claim in this repository has a run behind it.** `docs/tool-verification/` records
  what was actually measured, on which target, and with which independent cross-check; anything not
  covered there is documented from experience and should be read as *inferred*, per this skill's own
  claim ladder.
- **The extension pass is recorded separately and is mostly *inferred*.** Its evidence lives in
  `docs/tool-verification/EXTENSION-*.md`, one file per topic, with its own strength note. The
  common shape there is *the tool was measured, the route was not* — so read those files before
  treating any of the newer documents as a verified path.
- **The benchmark pass is recorded per row, with that row's own strength.** `tests/benchmark.md`
  names each public target, the scripts the row exercises, what actually happened (including the
  rows that failed and the rows nobody ran), and how strong the evidence is. Rows marked
  `unverified` are statements about the evidence in this repository, not about the mechanism.

## Repository maintenance

Four tools live at the root and are not part of the installed skill:

```
check_repo.py      every skill discovered, frontmatter valid, scripts runnable,
                   documented paths resolve, README paths explicit and existing,
                   and -- on the tracked surface only -- no target identity
                   (delegates the rules to skills/apk-reverse/scripts/scan_leaks.py
                   so there is one place to argue with the exemption list)
check_refs.py      every cross-reference that names a section of another
                   document reaches a real heading in that document
check_routing.py   the on-demand inventory still matches the entry point: the
                   symptom mirror agrees with SKILL.md, every reference file is
                   named in skills/apk-reverse/references/routing.md, and every
                   script is too
check_commands.py  every command a document tells you to run is checked against
                   the script's own argparse table -- a documented flag that does
                   not exist is a drift the anchor checks cannot see
check_budget.py    keep the always-loaded part from creeping: SKILL.md's whole
                   body (index lines included, because they load too) measured in
                   lines and tokens, index-row length, long files with no
                   navigable head, and hedged rules reported as a trend
build_scripts.py   audit for machine-specific leftovers (absolute paths, credentials)
```

Consistency has a natural counter-pressure -- a broken path fails loudly, and someone fixes it.
Bloat has none, which is why the third tool exists: every pass adds a reference, an index row and
a coverage claim, and without a measurement nothing in the repository notices.

`tests/benchmark.md` holds the **regression matrix**: dimension -> public target -> the scripts the
row exercises -> measured result -> strength label. It is the checklist to re-run before trusting
any claim under `docs/tool-verification/`. Samples are downloaded into `tools/_work/` and are never
committed, so each row names its public source and records the hash it was run against.

`docs/tool-verification/` is not part of the installed skill either. It is the evidence record
for one measurement pass against a real target: what each script actually did, which independent
method confirmed it, which defects were found, and which scenarios the target could not exercise.
It exists so the **Coverage** claims in `SKILL.md` can be checked against runs instead of trusted,
and so the gaps are written down where the next person will find them.

---

Proudly supported by the [LINUX DO](https://linux.do) community.

## Disclaimer

**For learning, research and authorized security testing only.** Every script, reference and
recorded result in this repository exists to explain *how* Android application analysis works, so
that practitioners can reason about the tools they already own. Nothing here is a service, a
product, or an endorsement of any particular use.

- **Authorized targets only.** Use this on applications you own or have been explicitly permitted to
  analyze, on public CTF/challenge material, or in a sandbox you control. Analyzing software you have
  no right to analyze may be unlawful where you live, and that determination is yours to make, not
  this repository's.
- **No warranty, no fitness for any purpose.** The material is provided *as is*, without warranty of
  any kind. Results are recorded as they were measured on one machine at one time; nothing here
  promises that a route will work on your target, your device, your toolchain or today's app version.
- **Verify before you trust; back up before you act.** Several scripts modify artifacts (dex, APK,
  `.so`, stored app data) and some operate on a rooted device. Keep your own copies, work on
  duplicates, and read `SKILL.md`'s gates before running anything against something you care about.
- **Your use is your responsibility.** The authors and contributors accept no liability for any loss,
  damage, legal consequence or service interruption arising from the use or misuse of this
  repository, and are not affiliated with, endorsed by, or acting on behalf of any application,
  vendor or platform it may be used to examine.
- **Test data is not distributed here.** Samples, dumps and device artifacts are deliberately absent
  from the tree (`.gitignore` excludes them) and live only in a local, ignored workspace. Anything you
  obtain to follow along is yours to keep safe and to delete when you are done with it — follow your
  local rules and the terms that came with the sample. What this repository *does* publish is the
  method and the evidence, with all target identity removed.
- **No affiliation.** Names of tools, libraries, hardening products and public challenge targets
  appear only to make the material reusable; they belong to their respective owners and this project
  is not connected to them.
