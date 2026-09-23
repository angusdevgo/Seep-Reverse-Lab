# Routing tables — the on-demand inventory behind `SKILL.md`

This file is the **lookup layer**. `SKILL.md` loads in full when the skill activates, so it carries
only what has to be one hop there: the symptom index (recognising a failure must not become a two-hop
lookup) and the four gates with their pass criteria.

Everything you consult *after* deciding to work lives here, and one load gets all of it:

| You want | Table |
|---|---|
| every reference file, and when to load it | **Reference index** |
| every script this skill ships, and what it does | **Script index** |
| the symptom table as part of a whole-inventory read | **Symptom index** (mirror — the live copy is in `SKILL.md`; edit it there) |

Coherence is enforced: `python check_routing.py` fails when this file and `SKILL.md` disagree, when a
reference file is not named here, or when a script is not named here.

## Symptom index


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

_54 row(s) below the header._

## Reference index (no longer inline in `SKILL.md`)


| File | Load when |
|---|---|
| `references/recon.md` | Starting any new sample; identifying packer, SDKs, code location, ABI |
| `references/server-config-and-updates.md` | **The launch screen, a popup or the tab set is server-sent**; no ad SDK was found; a removed promo came back; anything controlled by a `*Config`/`*Popup` DTO with an `enabled` flag |
| `references/byte-level-patching.md` | You want to change behaviour by editing a few bytes rather than rebuilding a method — equal-length patches, locating an instruction's exact offset, dex header integrity fields, branch polarity, verifier legality |
| `references/packers.md` | The app is packed/hardened, or an edit makes it die before your code runs. Also load before discarding any route as "blocked by the shell" |
| `references/code-virtualization-and-custom-linkers.md` | **No packer, dex is readable, and a re-signed build still dies** — whole classes turned `native`, a private loader with a mismatched SONAME, a self-decrypting payload, a Java-layer "signature killer", and the keep-it/drop-it deadlock |
| `references/java2c-and-jni-sinking.md` | **Whole classes are bare `native` declarations and you are about to hunt for a decrypted DEX** — Java2C has none, ever; the code is in a `.so`. Also the JNI boundary: why a `Java_*` symbol search fails silently |
| `references/vmp-differential-analysis.md` | Method bodies are present but decode as **private opcodes** — a real Dex VMP: the known-plaintext differential, which links can and cannot be automated, how to *prove* a derived opcode table, smali generation, and when the route is closed |
| `references/framework-runtimes.md` | The UI is not native (Flutter / React Native / Unity / Cordova), or Java-layer hooks fire zero times while the UI clearly works |
| `references/dart-aot.md` | The logic lives in a Dart AOT snapshot (`libapp.so`): pinning the Dart version, building a matching decompiler, the object pool and reference indexing, register/boolean conventions, locating and patching Dart code |
| `references/native-and-so.md` | Patching in a `.so`, needing code to run before the app's own code, hand-built native payloads that crash inside the linker, or **deciding which library/ABI is actually loaded and executing** |
| `references/native-tamper-and-suicide.md` | The process dies on its own (no Java stack, or a native crash that looks like a bug); you are about to neutralise a `kill`/`exit`/`abort` path; or a hardened library's sections/function boundaries look wrong |
| `references/detection-and-anti-analysis.md` | The app fights back: it dies after you attach, refuses to run, detects root/hook/debugger. **Cost-first (A/B/C), plus the order of search** (see its Step 3 stage funnel) and when to go static |
| `references/toolchain.md` | Choosing or invoking tools, something is not installed (including "not on PATH but present on disk"), a tool's output smells wrong, or you need to know which tools exist only as a GUI |
| `references/ad-removal.md` | Task involves ads, trackers, sponsored cards, splash/interstitial/reward |
| `references/updates-and-forced-upgrade.md` | The patched build must **keep working over time**; the app has any version check, forced-upgrade dialog, self-update installer, or hot-update/resource channel. Load this for essentially every build you intend to ship. |
| `references/account-gates.md` | Task mentions "no login required", "don't force sign-in", "skip phone binding", "guest mode"; or a screen/feature is unreachable signed-out. Also load before promising that an account-scoped screen will show anything |
| `references/membership-and-limits.md` | Task involves VIP, subscription, paid content, unlock, "fully cracked" |
| `references/server-api.md` | The behavior is decided by a response, or you need to know if a patch can even matter |
| `references/dex-patching.md` | Any actual editing of dex/smali, choosing a patch layer, choosing a tool |
| `references/patch-audit.md` | Proving a patch **landed**, or that it is **legal**: length-vs-bytes comparison, the equal-length blind spot, verifier-level legality (`move-result*` adjacency), text-matching patch traps, and how to report a missing patch |
| `references/repack-and-sign.md` | Rebuilding, signing, installing, or a repacked app misbehaves |
| `references/signature-derived-keys.md` | The app reads `signatures[0]`/`toCharsString()`, or a rebuilt APK installs and runs but every signed request fails (`sign`/`_p`/`uth` empty or `-1`) |
| `references/runtime-data.md` | Local state matters: DataStore, SharedPreferences, SQLite, protobuf caches, tokens — **or your data edit keeps being reverted, or a stored value looks encrypted** |
| `references/dynamic-frida.md` | Frida setup, hooking strategy, tracing caller chains, finding the real call site |
| `references/environment.md` | Device/emulator setup, root, ADB, networking, offline devices, emulator console control and recovery, **the preflight check to run before every experiment block** |
| `references/verification.md` | Defining what "done" means; building the evidence chain |
| `references/tls-and-cert.md` | One feature fails at runtime (login, registration, payment, an API-backed screen) while the rest of the app works |
| `references/third-party-builds.md` | The input is a "cracked"/"modded" build you did not produce — audit it before trusting it |
| `references/long-task-discipline.md` | The task will run long, or you are resuming one. Live record, conclusion grading, drift checkpoints, **deliverable-form drift (rooted-only vs shippable)**, bound-your-waits, **captures-you-never-looked-at**, **long-context decay**, handover |
| `references/pitfalls.md` | Always worth a skim before building. This is the failure catalogue. |
| `references/coverage-and-limits.md` | You need to weigh a claim before trusting it: the evidence behind each covered item, the dependencies this skill does not ship, and the record of what was never exercised |
| `references/coverage/route-inventory.md` | You must answer "**can this skill actually do X**" in one pass: the per-route inventory — covered by verified mechanism, covered only by a documented route, the dependencies not shipped, and what is out of scope |
| `references/evidence-summary.md` | You need to know **whether a route was verified and how strong the evidence is**, from inside an installed copy: capability → one-line conclusion → strength → where the evidence lives |
| `references/routing.md` | You want the **whole inventory in one load**: every reference file with when to load it, every script with what it does, and a mirror of the symptom index |
| `references/desensitization-and-leak-scans.md` | You are about to publish anything derived from real work — evidence, a transcript, a README — or a leak scan reports a hit: what must be desensitised versus kept, the do-not-anonymize list, and how the scan gates a commit |
| `references/precedents/` | You are about to do a kind of work this repository has already converged on — a hardened Flutter target, a zero-event trace, a module whose log is silent, an equal-length patch taken to the device. Positive cases with graded evidence and dead ends |
| `references/handoff-boundaries.md` | A routing decision is about to cross into another discipline: the JNI form table, the packer-versus-loader split, and what "verified" means for each of G1's four deliverable forms |
| `references/advanced-unpacking.md` | **The dump landed but the bodies are empty** (an extraction shell), or decode as private opcodes: the stub-ratio measurement, why FART's hooks died on Android 12-16, the root-side dump, its **boundary**, the layered descent, and where recovery stops |
| `references/lsposed-and-modules.md` | The client-side logic is reachable but **a rebuilt APK is refused**: delivering a system-level hook module instead, its gradle-free build chain, scope configuration and verification, and the layer a Java module cannot reach |
| `references/emulation-and-rpc.md` | You need to **call** a routine rather than change the app — a signing routine, a token, a cipher: emulated execution (Unidbg/Unicorn) with its environment-filling cost, versus service-ifying the live function over Frida RPC |
| `references/native-dbi-and-deobfuscation.md` | A native function is an OLLVM state machine, or you need instruction-level execution evidence: Stalker traces, the trace-to-CFG route, the Stalker/QBDI/emulation decision, and the **measured** zero-event and crash boundaries |
| `references/protocol-reverse.md` | The traffic is protobuf without a schema, gRPC, or QUIC/HTTP3; or a proxy sees TLS while the app still fails — schema recovery, frame capture, and native-side certificate pinning (Flutter/BoringSSL) with its boundaries |
| `references/kernel-and-environment-hardening.md` | Userspace hooking provably cannot reach the check — raw `svc` syscalls, `init_array`-early detection: what each layer can still do, the kernel-route map with its version gate, and when escalating is wrong |
| `references/on-device-tooling.md` | Working **from the phone itself**: MT Manager edit/repack/sign and its built-in APK MCP, LSPosed Manager, Termux+frida, and on-device data inspection |
| `references/split-apk.md` | The target is a **split APK / App Bundle set** (`base.apk` + `split_config.*.apk`), or `pm path <PKG>` returned several files: reading a set, merge versus unified re-signing, and the install refusal each mistake produces |

_43 row(s) below the header._

## Script index (no longer inline in `SKILL.md`)


| Script | Purpose |
|---|---|
| `scripts/doctor.py` | **Run this first.** Script inventory is scanned from the directory (`registered/checked = N / N`, unjudgeable entries counted as `unknown`, never skipped) and capability is resolved as a real requires-closure — so it reports BLOCKED with the missing piece and an installable next step instead of inferring "can re-sign" from the presence of a JVM |
| `scripts/dexutil.py` | **Dependency-free dex reader**: structural walk, exact instruction decode, `fix_dex_header`/`verify_dex_header` in the correct order, branch/operand helpers. Shared by the dex scripts; also dumps one method with offsets standalone |
| `scripts/dex_find_insn.py` | Locate an instruction by **decoded semantics** and get its exact byte offset, with context and both sides of any branch. This is how you find a patch site without guessing offsets or scraping listings |
| `scripts/dex_patch_bytes.py` | Apply **equal-length byte patches** from a JSON spec: semantic match, polarity pin via `expect_next`, equal-length enforcement, verifier legality, dex header recompute, re-decode to prove the edit landed. `--dry-run` first |
| `scripts/dex_check_verifier.py` | Tier-3 check: does any **conditional branch target a `move-result*`** (bypassing its producer, so the class fails to load)? Compares two builds and distinguishes pre-existing findings from regressions your patch introduced |
| `scripts/coldstart.py` | Cold-launch and capture a **timed screenshot burst + logcat signals + installed-build facts + launch timing**, and warn when the foreground activity is not your app |
| `scripts/smtool.py` | baksmali/smali wrapper with a bundled classpath (assemble/disassemble dex) |
| `scripts/patch_smali.py` | Method-body replacement in a smali tree, matched by signature |
| `scripts/dex_strpatch.py` | Byte-level string constant patch with **string_ids ordering guard** |
| `scripts/dex_classdiff.py` | Compare two dex class tables (set + access flags) to prove a patch was surgical |
| `scripts/dex_strings.py` | Dump/extract strings and endpoints from dex without a decompiler |
| `scripts/dart_pprefs.py` | Build/query the object-pool offset -> code-site index for a Dart AOT snapshot (arithmetic decode; seconds, not minutes) |
| `scripts/dart_pool_strings.py` | Recover string literals from a Dart AOT snapshot: framed entries, the one-byte vs UTF-16 split, file offsets, and a run-length noise filter |
| `scripts/dart_disasm.py` | Annotated windowed disassembly of Dart AOT code (pool + boolean annotations) plus a B/BL caller index |
| `scripts/find_refs.py` | Count and list callers of a method/field (blast-radius check). Takes a smali tree, a `.dex`, a directory of either, or an `.apk`. Always prints what it scanned, so "the input was unreadable" cannot be mistaken for "nothing references it" |
| `scripts/repack.py` | Rebuild an APK: replace dex, strip only signatures, keep `META-INF/services/`, write a **4-byte-aligned** archive, sign, verify. Also **split sets**: `--split-dir`, `--split-mode resign`/`merge`, `--signer auto/jar/apksigner` |
| `scripts/dexpatch/` | dexlib2 method-level rewriter (for changes that genuinely need new instructions) + build notes |
| `scripts/devsh.py` | Quoting-safe ADB shell helper for rooted devices |
| `scripts/usb_net_proxy.py` | Give an offline device network over USB (adb reverse + local proxy) |
| `scripts/datastore_inject.py` | Encode/inject AndroidX DataStore preferences (protobuf) safely |
| `scripts/probe_api.py` | Probe an app's HTTP API with correct headers, report status/shape |
| `scripts/install_test.py` | Install a build and run a launch/health check with logcat signal extraction |
| `scripts/frida_probe.js` | Four-layer runtime probe: app network layer + OkHttp + java.net + swallowed exception messages |
| `scripts/run_probe.py` | Inject a probe, stream it to a timestamped log file, stay resident while you operate the app |
| `scripts/tls_check.py` | Strict certificate check for one or more hosts (expired / wrong host / untrusted CA) |
| `scripts/preflight.py` | Read-only environment check before every experiment block: device, root, ABI/translation, clock skew, leftover proxy/forwards, dead device server. Run this before blaming a patch. |
| `scripts/lib_map.py` | What is **actually mapped** into a live process: per-library path, base, architecture (`ELF e_machine`), and classification (system / from-APK / runtime-materialized). Answers "which library and which ABI is really executing". |
| `scripts/elf_plt.py` | Resolve a PLT stub to its imported symbol (x86_64 + aarch64) from the **relocation table**, list a symbol's callers, and **byte-diff two libraries naming the symbol each changed stub belongs to**. Run before patching any stub |
| `scripts/so_constpatch.py` | Same-length rewrite of an isolated string constant, for **redirecting a library load instead of defeating a check**. Enforces equal length, refuses substrings of longer identifiers, reports constant-pool hits, patches inside an APK or a bare `.so`. **APK rebuild preserves per-entry zip metadata** (STORE stays STORE, `extra`/`external_attr`/`create_system` untouched, `resources.arsc` STORED and 4-byte aligned) and **refuses by default** when `extractNativeLibs="false"` or the arsc is not STORED+aligned — pointing at `repack.py`; only `--unsafe-rebuild` forces it |
| `scripts/apk_diff.py` | Entry-level diff of two APKs by content hash: changed / **added** (injection candidates) / removed. Audits a third-party build and proves your own was surgical |
| `scripts/native_crash.py` | Locate a native death from a log or tombstone: signal, fault address, registers, frames split app vs system, the faulting instruction — plus a flag when the fault looks **arranged** rather than accidental |
| `scripts/grab_crash.py` | Recover a stack that a crash-reporter SDK swallowed, when the log shows the app died but prints no backtrace of its own. |
| `scripts/blob_decode.py` | Decode an opaque stored value by searching the parameter space (base64/base64url/hex × rotation × deflate/zlib/gzip) instead of guessing, then re-encode an edited payload with the same parameters. |
| `scripts/snap.py` | Bounded burst screenshot + control-tree capture, with a stall detector and an explicit verdict on whether the accessibility tree is usable at all. Use it so you *look* at the screen instead of driving blind. |
| `scripts/sig_probe.py` | Find the exact `signatures[0].toCharsString()` value: offline candidates from an APK (`--apk`), or the authoritative read from a live package (`--live`) |
| `scripts/spawn_patch_detach.py` | **Spawn under a probe, detach, then drive the UI.** Under spawn the Activity stack often never comes up; memory writes survive detach while hooks do not. Ordering matters: resume *before* waiting for `PATCHED` |
| `scripts/hook_patch_only.js` | The minimal probe for `spawn_patch_detach.py`: neutralise one native death site by offset and report `PATCHED`. `MODULE_NAME`, `FILE_OFFSET`, `PATCH_BYTES`; the replacement must be an equal-length "return" epilogue |
| `scripts/dex_dump_validate.py` | Dedupe, validate and rank dumped dex images: sha256 grouping, header integrity, extraction-shell discrimination via the **trivial-body ratio** (bimodal, not a threshold — `advanced-unpacking.md`), ranking, `--json`, `--trim` for page-aligned captures |
| `scripts/dex_mem_scan.py` | Find embedded dex images in memory captures and extract each at the size **its own header declares**: chunked scanning, magic validation, sha256 dedupe, `--dump DIR`, `--keep-partial` |
| `scripts/lsposed_scaffold.py` | Generate a minimal LSPosed/Xposed **module project skeleton**: manifest with the xposed meta-data, `assets/xposed_init`, the hook class, and build notes for a gradle-free toolchain (javac → d8 → aapt2 → zipalign → apksigner) |
| `scripts/frida_rpc_serve.py` | Bridge a Frida script's `rpc.exports` to a local caller with reconnect handling, so a live native function can be **called** instead of reversed |
| `scripts/rpc_template.js` | The editable companion to `frida_rpc_serve.py`: an `rpc.exports` skeleton plus a native-function call placeholder |
| `scripts/stalker_trace.js` | Instruction-level tracing with Frida Stalker: configurable module/offset targets, trigger selection, the event stream, output-size rules, and `transform` customisation |
| `scripts/stalker_report.py` | Reduce a `stalker_trace.js` log into block histograms and call sequences, and print an explicit diagnostic for the measured **zero-event** case |
| `scripts/mt_mcp_probe.py` | Probe MT Manager's on-device APK MCP (Streamable HTTP, `127.0.0.1:8787/mcp`): JSON-RPC handshake plus grouped `mt_apk_*` tool inventory; prints start-it-by-hand instructions and exits 2 while the service is down |
| `scripts/java2c_probe.py` | The evidence that separates **Java2C** from an extraction shell, a VMP and JNI sinking: per-class `native` density and stub ratio from the dex, plus `Java_*` / `JNI_OnLoad` / registration evidence from the `.so` |
| `scripts/protobuf_decode_raw.py` | **Schema-free protobuf decode**: hex / file / stdin to a JSON tree, every length-delimited field as a candidate set with ties labelled; `--reencode --check` for a byte-exact round trip |
| `scripts/vmp_diff_harness.py` | Differential hardening for Dex-VMP: build a labelled opcode-coverage fixture (**218 of 224 opcodes, measured**), derive a candidate private-opcode map from an original/hardened dex pair, verify it in a closed loop, render smali |
| `scripts/kernelsu_syscall_mask.py` | Generate a KernelSU/APatch syscall-masking scaffold: an installable userspace module plus KPM/LKM/eBPF kernel-side templates, each with its version gate and an explicit unverified label. **A userspace module cannot change a syscall return value** |
| `scripts/capabilities.py` | The capability registry `doctor.py` reads: per capability the requires-closure, what is present, what is missing, an install hint and an estimated cost — so "can this machine do X" is computed rather than guessed |
| `scripts/device_shell.py` | Shared device-side command construction: POSIX single-quote escaping for `su -c`, argv arrays rather than string concatenation, and Android identifier validation (`--pkg`, components) so a malformed value is rejected here instead of being parsed by the device shell |
| `scripts/scan_leaks.py` | Scan a repository for target identity before it is published: bundle ids in manifest/`pm`/`ps` contexts, serial-shaped tokens, PATs, inline appkey assignments, literal endpoints, host user paths. Built-in do-not-anonymize exemptions, context-bearing findings, `--show-exempt` prints why a hit was suppressed, `--fail-on strong\|any`, exit 0/1/2 with a `RESULT=` token |
| `scripts/svc_scan.py` | Name the syscall behind an inline `svc` and the segment it sits in — which decides whether a libc-level hook can observe the call at all. `--context` shows neighbours, because a byte scan also matches data |
| `scripts/anti_detect_probe.js` | Observer-only probe (patches nothing): path/loader/thread/kill hooks with **caller module + offset**, an environment self-report (`TracerPid`, frida-named mappings), and live streaming so a sub-second target still yields evidence |

_53 row(s) below the header._
