# LSPosed modules — when to deliver a hook instead of a patched APK

Load this when the honest answer to "patch the APK" is *no*: the target checks its own bytes, derives
keys from its signature, re-downloads what you removed, or is simply cheaper to hook than to rebuild.
A module is a different **deliverable**, not a different way to analyse — it changes what you ship, how
it survives upgrades, and who has to install it.

This file covers the module route end to end: choosing it, the smallest project that works, the
Gradle-free build chain, deployment and verification, what hides it from the target, and what it
cannot reach at all.

**Route honesty first.** A module does not modify the APK, so it cannot be "the patched build". If the
user asked for an installable standalone APK, a module is not that artifact, and this file will not
make it one.

## Step 0 — pick the route deliberately

Three routes ship three different things. Choose on **who runs it and for how long**, not on which one
you enjoy more.

| Route | Deliverable | Runs when | Survives target update | Cost |
|---|---|---|---|---|
| **Frida** (attach/spawn) | a script, driven by you | while a server process is alive on the device | it does not; you re-run it | lowest to start, highest per-session |
| **LSPosed module** | an installable APK the user keeps | every process start, automatically, after the module is enabled and scoped | usually yes — the hook targets classes/methods, not offsets | mid: one project, no repackaging of the target |
| **Repackaged APK** | a modified, re-signed APK | whenever the app runs | no — every update needs rework | highest: integrity, signature, packing, repack |

Reach for a module when **any** of these is true:

- the target verifies its own signature or APK digest, so a repackaged build dies on arrival
  (`references/signature-derived-keys.md`, `references/native-tamper-and-suicide.md`);
- the change must persist across restarts without your laptop being attached;
- attaching a debugger/injector is itself detected, but a startup-time hook is not
  (`references/detection-and-anti-analysis.md`);
- you need a Java-level behaviour change only, and the target's own code is reachable from Java.

Do **not** reach for a module when the logic you need lives in native code or in an AOT-compiled
runtime: see *What this route cannot reach* below.

## What the module can and cannot change

| Layer | Module can reach it? | Where to go instead |
|---|---|---|
| Java/Kotlin app code (incl. classes loaded late by a packer's ClassLoader) | yes, once you have the right `ClassLoader` | — |
| `Application` / `Activity` / framework lifecycle | yes | — |
| Java SDK internals (OkHttp, ad SDKs, HTTP clients) | yes | — |
| Pure native logic inside a `.so` | no — Java hooks see only the JNI boundary | `references/native-and-so.md`, `references/native-dbi-and-deobfuscation.md` |
| Extracted / virtualised dex (instruction-抽取, dex VMP) | no — the original method bodies may not exist as dex at all | `references/advanced-unpacking.md` |
| Flutter / Dart AOT business logic | no — Dart is not Java; the Java layer only hosts the shell | `references/dart-aot.md` |
| Behaviour that is *decided* server-side | irrelevant — a hook cannot remove a server rule | `references/server-api.md`, `references/server-config-and-updates.md` |

The Flutter row is the one that most often surprises: hooking every Java entry point in a Flutter app
still leaves all business logic behind `libapp.so`. Confirm which layer owns your target before
building a module for it (`references/dart-aot.md`).

## How injection actually works

The mechanism matters because every failure mode below is a consequence of it.

- LSPosed ships as a **Zygisk module** (`zygisk_lsposed`). Zygisk loads into `zygote`, so every app
  process forked from it is a candidate for injection. [inferred: standard Magisk/Zygisk design]
- A module is **not** injected everywhere. For each forked process LSPosed asks its daemon (`lspd`)
  whether this package is in the module's **scope**, and only then loads the module. Scope is therefore
  the real gate; anything inside the module that filters on package name is a second, weaker gate.
- Module code is loaded **from memory**, not from a file mapping — the module's dex is read out of the
  installed APK and handed to an in-memory ClassLoader. This is why a target scanning `/proc/self/maps`
  for path names finds nothing (`references` below, *What detects you anyway*).
- The entry point is the class named in `assets/xposed_init`, and it receives
  `handleLoadPackage(XC_LoadPackage.LoadPackageParam)` **before the application's own `Application`
  object is attached** — the earliest Java-visible moment in the process. [measured: the injection
  point is why `Application.attach` and `Activity.onCreate` hooks installed from here fire even under a
  packer]
- `LoadPackageParam.classLoader` is the **application's** loader (the packer's stub loader when the APK
  is packed). It is the handle you use to find classes the app loads later, and it is also the object
  anti-Xposed code counts — see *What detects you anyway*.

## Minimal module anatomy

Four files. Nothing else is required — no `res/`, no launcher Activity, no permissions.

| File | Why it is required |
|---|---|
| `AndroidManifest.xml` with `<meta-data android:name="xposedmodule" android:value="true"/>` | without this key the APK installs as an ordinary app and never appears in the module list |
| same manifest: `xposeddescription`, `xposedminversion` (`82`) | shown in the manager UI; `82` is the classic XposedBridge API level and is accepted by LSPosed |
| `assets/xposed_init` | one line: the fully qualified entry class. A typo here produces a module that loads and silently does nothing |
| the entry class implementing `IXposedHookLoadPackage` | the only class LSPosed instantiates for you |

`scripts/lsposed_scaffold.py` writes exactly this set, plus a README containing the build chain below,
so the project is reproducible without Gradle:

```sh
lsposed_scaffold.py --package com.example.probe --name "Example probe" \
    --hook-target com.example.target --out ./module
```

The generated entry class logs on **every** scoped process load before anything else, and hooks
`Application.attach` / `Activity.onCreate`. Both are diagnostics first: the first line proves injection,
the second names the real Activity classes (under a packer, these are the *unpacked* classes, not the
manifest's stub).

## Building without Gradle

There is no resource to compile and no dependency resolution to do, so the whole toolchain is five
commands. [measured on a Windows bench, JDK 17, build-tools 34.0.0, Android API 28 android.jar,
Xposed api-82 stub jar; end-to-end 5.3 s for a one-class module]

```sh
BT=/path/to/build-tools/34.0.0
AJ=/path/to/android.jar          # platforms/android-28/android.jar
API=/path/to/api-82.jar          # de.robv.android.xposed:api:82
OUT=build

javac -encoding UTF-8 -source 8 -target 8 -nowarn -cp "$AJ:$API" \
      -d "$OUT/classes" src/com/example/probe/MainHook.java      # 850 ms
jar cf "$OUT/classes.jar" -C "$OUT/classes" .                     # 259 ms
"$BT/d8" --min-api 24 --lib "$AJ" --output "$OUT" "$OUT/classes.jar"   # 1143 ms -> classes.dex
"$BT/aapt2" link -o "$OUT/base.apk" -I "$AJ" --manifest AndroidManifest.xml \
      --min-sdk-version 24 --target-sdk-version 28 -A assets      # 126 ms
cp "$OUT/base.apk" "$OUT/unsigned.apk"
cp "$OUT/classes.dex" .                                           # must sit next to the apk
(cd "$OUT" && "$BT/aapt" add unsigned.apk classes.dex)            #  97 ms
"$BT/zipalign" -f -p 4 "$OUT/unsigned.apk" "$OUT/aligned.apk"     #  76 ms
"$BT/apksigner" sign --ks mod.keystore --ks-pass pass:android --key-pass pass:android \
      --v2-signing-enabled true --out "$OUT/module.apk" "$OUT/aligned.apk"   # 1794 ms
"$BT/apksigner" verify --print-certs "$OUT/module.apk"            # 725 ms -> v2/v3 OK
```

Four traps, all measured rather than guessed:

- **`d8` rejects a directory.** Pointing it at `build/classes/` fails with *Unsupported source file
  type*. Jar the classes first and pass the jar.
- **`aapt add` resolves its argument relative to the current directory and stores the same name.** Run
  it from the output directory with `classes.dex` present there; a path like `dex/classes.dex` lands
  inside the APK as `dex/classes.dex` and the module never loads.
- **`jar` and `keytool` are frequently not on `PATH` even when `javac` is.** Oracle's `javapath` shim
  exposes only `java`/`javac`; call the JDK's `bin` directory explicitly.
- **`-bootclasspath` no longer exists on JDK 9+**, so the Android API comes from `-cp` together with the
  Xposed stub jar. `-source 8 -target 8` keeps the class-file version low enough for `d8`.

The generated README carries the same chain in copy-paste form, including the Windows variants
(`.bat` wrappers, `;` classpath separator).

## Deploy, enable, and verify

**There are two independent switches.** Getting one right and not the other is the single most common
"I built a module and nothing happens" report.

| Switch | Where | What it actually controls |
|---|---|---|
| package enabled state | `pm enable <module>` / `pm disable <module>` | whether Android allows the package's components to run at all |
| module enabled | LSPosed Manager (module list) | whether LSPosed loads the module into scoped processes |
| scope | LSPosed Manager (module → scope) | *which* packages the module is injected into |

[measured: a freshly installed module can be in the module database yet disabled — the package
manager reported `enabled=0` for the module and `pm enable` flipped it to `enabled=1`, while the
LSPosed-side enable flag was still 0 in its own database]

A third, device-level gate sits on vendor ROMs: the *install* itself can be intercepted by the ROM's
security centre. The shape is a shell-identity `pm install` returning a bare `Failure [-99]` while the
vendor security app takes the foreground, and the **same APK installing cleanly as root**
(`su -c 'pm install -r <apk>'`). If a module APK "will not install" on a phone that is otherwise
healthy, try root before suspecting the APK. [measured; the extension record has the transcript]

Verification has **two channels**, and on a device with a broken platform log only one of them works:

```sh
# 1. the platform log — where the module's line normally appears
adb logcat -s <TAG>              # then start the target app; do NOT clear the buffer first
# 2. LSPosed's own module log — where it appears when logd is broken
adb shell "su -c 'cat /data/adb/lspd/log/modules_<timestamp>.log'"
```

The expected first line in either channel is the one the scaffold writes on entry — it fires before
any app code:

```
<TAG> injected: <target.package>/<process> cl=<loader>@<hash>
```

[measured] On a device whose `logd` route is broken, channel 1 is **completely empty** — not merely
`logcat -s <TAG>`, but `logcat -s LSPosed-Bridge` and a full-buffer search for the tag as well — while
channel 2 shows a complete, successful injection for every process start. A ROM whose LSPosed log
opens with `Logd maybe crashed (err=Socket operation on non-socket)` is exactly this case, and it had
nine successful injections in it while logcat showed nothing at all. Debugging with `logcat` alone
there produces the confident and wrong conclusion "the module never ran".

Decision order when that line is missing — stop at the first hit:

1. module enabled in LSPosed Manager?
2. target package present in the module's **scope**?
3. module APK still installed (`pm path <module>`)?
4. **was the target process started after the scope change?** Scope is read for newly forked
   processes; a process that was already running keeps the decision it got at fork time.
   [external, matches LSPosed behaviour reported independently: a scope change takes effect on the
   target's next start, no device reboot required — 看雪 thread-291750]

The LSPosed-side state is inspectable from a root shell:

| Path | Contents |
|---|---|
| `/data/adb/lspd/config/modules_config.db` | SQLite: `modules(mid, module_pkg_name, apk_path, enabled)`, `scope(mid, app_pkg_name, user_id)`, `configs(...)` [measured] |
| `/data/adb/lspd/log/` | `modules_<timestamp>.log`, `verbose_<timestamp>.log`, `kmsg.log`, `props.txt` [measured] |
| process `lspd` | the daemon that serves scope decisions; it is a separate process from the target [measured] |

Two measured caveats about that log directory, because both waste time:

- `modules_*.log` **is** the module log: it is the file LSPosed appends your `XposedBridge.log()` lines
  to. It may *also* contain `Logd maybe crashed (err=Socket operation on non-socket), retrying in 1s...`,
  which means the platform log channel is unavailable — not that your hook failed. Check this file
  **and** `logcat -s <TAG>`; a device can deliver one and not the other. [measured: nine successful
  injections were in this file while logcat showed nothing]
- `verbose_*.log` is a *logcat snapshot* that includes the whole system, so it is useful for
  correlating a system-side event with your run, and useless as a module log.

**Do not kill `lspd` to force a configuration reload.** [measured] On the bench it is started by
`/data/adb/modules/zygisk_lsposed/service.sh`, which runs `unshare -m sh -c "$MODDIR/daemon --from-service &"`;
the `daemon` script ends in `exec /system/bin/app_process ... org.lsposed.lspd.Main`. Magisk runs
`service.sh` once per boot, so an externally killed `lspd` is not restarted by anything you can see
from a root shell. The consequence is worse than a dead daemon: newly forked processes stop getting
scope decisions. Configure scope through the manager, which talks to the running daemon.

The same reasoning applies to editing `modules_config.db` by hand: the file is the daemon's
**persisted** state, while the decisions actually served to `zygote` come from the daemon's live copy.
A hand-edited row is not wrong — it is simply not read until the daemon reloads it, and there is no
supported way to make it reload. [inferred from the storage layout and the daemon lifecycle; the
manager path is the one that updates both]

## Hiding the framework from the target

Injecting a Java hook is trivial to detect **if the target is allowed to see the root/Zygisk
environment at all**. On a rooted device the hiding layer is a separate module, and the two common
choices differ in exactly one operational detail: how they learn which apps to hide from.

| | Zygisk Assistant | Shamiko |
|---|---|---|
| source | open | closed-source, LSPosed project |
| target selection | Magisk **DenyList** entries (or KernelSU profiles); no UI of its own | also reads Magisk's DenyList, **but requires DenyList enforcement to be OFF** |
| extra mode | — | creating `/data/adb/shamiko/whitelist` switches to whitelist mode without a reboot; documented as costly in memory/performance and test-only |
| mechanism | unmounts root-related paths and masks Zygisk presence for the selected process | same family of process-level hiding, plus its own mount/`maps` handling |

[external: Zygisk Assistant module description and Shamiko README]

**The DenyList/enforcement distinction is where people lose afternoons.** Enforcement is Magisk's own
feature that unmounts Magisk-provided files for listed processes; the *list* is shared, the *enforcement
toggle* is not the same thing. Shamiko wants the list without enforcement; Zygisk Assistant is
documented to work with the list as configured.

[measured on the bench: the DenyList was **enforced but empty** — `magisk --denylist status` reported
`Denylist is enforced`, `magisk --denylist ls` printed nothing, `/data/adb/shamiko` did not exist, and
Zygisk Assistant v2.1.4 was installed. So on that device nothing was being hidden from any app, while
LSPosed and `lspd` were running normally. If a target seems to know it is on a rooted device, check
this before blaming the module.]

Practical rules:

- **Keep the scope minimal.** Every extra scoped package is both an extra place your hook can break
  something and an extra ClassLoader in that process (next section).
- Hiding and hooking are separate problems. A module that is perfectly hidden can still be detected by
  the ClassLoader count; a target that never checks cannot see either.
- If the target is the *only* app you care about, scoping to it alone is both the smallest blast radius
  and the least observable configuration.

## What detects you anyway

Traditional Java-level anti-Xposed checks — `Class.forName("de.robv.android.xposed.XposedBridge")`,
exception-stack scanning for Xposed frames, reflection on `findAndHookMethod`, enumerating
in-memory-ClassLoader instances — are all **query interfaces**, and hiding layers exist precisely to
falsify their answers. They are no longer a reliable signal that a module is present or absent.

The check that does not depend on a query interface is the **ClassLoader count**. [external: 看雪
thread-291750, which reports a clean baseline of 3 versus 12 with a module injected, threshold ≥9; the
original idea is traced there to thread-289567]

The reason it works, in one paragraph: ART's `ClassLinker` keeps a `class_loaders_` list of every live
ClassLoader, and that list is part of GC reachability. A module's loader must stay on that list or the
GC will collect the module's code and the hook dies. So a module cannot both remain alive and be absent
from a structure the runtime itself walks. Hiding layers can fake lookups; they cannot remove a node
from a GC-traversal list without unloading the module.

The same source reports two further native-side traces of the same injection, which are worth knowing
because they are independent of ClassLoader counting: the module's dex shows up as **anonymous
executable memory** (it is loaded from memory, so no file mapping exists), and Zygisk's patching of
`libart` leaves **private-dirty pages** in the library's executable segments.

Engineering consequences for anyone choosing this route:

- **Scope discipline is detection hygiene.** Fewer scoped packages means fewer injected processes; a
  multi-module stack inflates the same count. The number is per-process, so a clean device elsewhere
  does not help this process.
- **A count check needs a calibrated baseline.** On complex hosts (WebView, split APKs, plugin
  frameworks, other modules) the clean count is already high, and the threshold has to be measured per
  host, never copied. [external: same source]
- **Detection of the framework is not the same as detection of your change.** If the target reacts to
  the count by refusing to run, that is an environment finding to report
  (`references/detection-and-anti-analysis.md`), not something to escalate against indefinitely.
- If the target's check is native and inline-hooks *your* detector's counterpart, you are in DBI
  territory: `references/native-dbi-and-deobfuscation.md`.

## LSPosed vs Frida — the division of labour

They are not competitors; they are the two answers to "how long must this hook exist".

| Need | Frida | LSPosed module |
|---|---|---|
| Understand a flow once, now | **yes** — interactive, no build step | no: build + install + restart per iteration |
| Ship something that works every launch, unattended | no: needs a server process | **yes** |
| Hook a `.so` function directly | **yes** (`Interceptor`, Stalker) | no: Java hooks stop at JNI |
| Survive a target that kills external injectors | weak: `ptrace`-based attach is the thing being detected | **stronger: no external process, no attach, no port** |
| Replace a method's return value in app code | yes | yes |
| Be re-runnable after a target update | yes (re-attach) | usually yes (class/method names auto-update far better than byte offsets) |
| Need no root on the target device | no | no |

The productive pattern is to use **both in sequence**: Frida to discover which class and method matter
and what the real call chain is (`references/dynamic-frida.md`), then a module to make that finding
permanent without touching the APK. Rebuilding a module for every question is the expensive way to
explore; exploring with an interactive script and only then writing the module is the cheap way.

A third option exists when the goal is *calling* target code rather than changing it — exporting a
native function over RPC: `references/emulation-and-rpc.md`.

## Failure modes

| Symptom | Most likely cause | Check |
|---|---|---|
| module never appears in the manager | `xposedmodule` meta-data missing/mistyped after manifest merge | `aapt2 dump xmltree` the built APK, or re-read the manifest |
| module listed, no `injected:` line in either channel | module disabled in manager, package not in scope, **target process not restarted** after the scope change, or you looked at only one channel | the four-step order above, then the two-channel check |
| the platform log is empty but the module log is not | the ROM's `logd` route is broken; the module is working | the tell is `Logd maybe crashed (err=Socket operation on non-socket)` at the top of the module log |
| `injected:` line present, but `TARGETS` gate skips the process | in-module gate, not the framework | read the module's own log line, then its gate |
| hook installed, method never fires | wrong class/loader: packers and plugin frameworks hold several ClassLoaders | resolve the loader at runtime; enumerate `/proc/<pid>/maps`-independent evidence via `references/dex-patching.md` |
| target dies right after injection | target side: ClassLoader counting or anonymous-memory heuristics (above); device side: ROM behaviour | instrument-free control run first (`references/detection-and-anti-analysis.md`) |
| `pm enable` had no effect on injection | `pm` state and LSPosed state are different switches | the two-switch table above |
| `d8` fails on a directory / `aapt add` cannot find the dex / `keytool` not found | build-chain traps, all three measured | the four traps above |

## Verification for the record

- which module APK, its hash, and what it was built from (scaffold output or hand-written);
- the build commands and whether `apksigner verify` passed;
- `pm path`/`dumpsys package` output for the module (installed, enabled state);
- the scope list actually configured;
- the target process start time relative to the scope change;
- the module's logcat lines, in order, showing injection and any hook installs;
- whether the target misbehaved, and the instrument-free control result for the same build.

## See also

- `references/dynamic-frida.md` — the exploration half of the workflow above
- `references/detection-and-anti-analysis.md` — when the target fights back and when to stop
- `references/native-and-so.md`, `references/native-dbi-and-deobfuscation.md` — the layer a Java hook stops at
- `references/dart-aot.md` — the layer that owns a Flutter app's logic
- `references/advanced-unpacking.md` — extracted dex and the VMP boundary
- `references/repack-and-sign.md`, `references/signature-derived-keys.md` — what you are avoiding, and why it is sometimes unavoidable
- `references/on-device-tooling.md` — MT Manager and the rest of the on-device kit
- `references/verification.md` — what "done" means, including the control-build rule
- `scripts/lsposed_scaffold.py` — generates the project skeleton described here
