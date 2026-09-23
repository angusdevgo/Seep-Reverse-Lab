# Extension verification — LSPosed module route

Covers the 2026-09 extension pass that added `skills/apk-reverse/references/lsposed-and-modules.md`
and `skills/apk-reverse/scripts/lsposed_scaffold.py`. Strength labels as defined in this directory's
README: **observed** (exact command + output here), **inferred** (follows from observed facts, step
not executed), **unverified** (assumed or externally reported, not independently confirmed).

Reference environment for this pass: rooted physical device, Android 11 (API 30), arm64-v8a,
Magisk alpha + Zygisk, LSPosed v1.9.2 (7024) activated, Zygisk-Assistant v2.1.4 installed, MT Manager
2.26.9 installed, one hardened Flutter sample installed (referred to below as *the sample*; no target
identity is recorded here). Host: Windows, JDK 17.0.4.1, Android build-tools 34.0.0, API 28
`android.jar`, Xposed `api-82` stub jar.

**Identifier convention:** every occurrence of the sample's package identifier in the transcripts
below is normalized to `<PKG>` (`<PKG>.MainActivity`, `<PKG>.BaseApplication`), and its sub-package
prefixes are shortened the same way. The transcripts are otherwise verbatim, including the class
names a hook reported — those are what make the evidence checkable.

This pass closes an item left open by the previous extension record, which noted that "no LSPosed hook
module was built or run against a real target" (`EXTENSION-kernel-ondevice.md` §4). The build half is
now **observed**; the injection half is **partially observed** and the gap is stated in §6.

---

## 1. Scaffold script — observed

### 1.1 `--help` and generation

```
$ python skills/apk-reverse/scripts/lsposed_scaffold.py --help
usage: lsposed_scaffold.py [-h] --package PACKAGE --name NAME
                           [--hook-target TARGETS] --out OUT
                           [--class-name CLASS_NAME] [--tag TAG]
                           [--description DESCRIPTION] [--min-sdk MIN_SDK]
                           [--target-sdk TARGET_SDK] [--hook-class HOOK_CLASS]
                           [--hook-method HOOK_METHOD]
                           [--hook-params HOOK_PARAMS] [--force]
```

Generation of a throwaway module, **observed**:

```
$ python skills/apk-reverse/scripts/lsposed_scaffold.py \
      --package com.example.probe --name "Example probe" \
      --hook-target com.example.target \
      --hook-class com.example.target.Helper --hook-method check \
      --hook-params "java.lang.String" --out <work>/scaffold-gen
[+] <work>/scaffold-gen/AndroidManifest.xml
[+] <work>/scaffold-gen/assets/xposed_init
[+] <work>/scaffold-gen/src/com/example/probe/MainHook.java
[+] <work>/scaffold-gen/README.md
```

`assets/xposed_init` contains exactly one line, `com.example.probe.MainHook` (**observed**). Re-running
without `--force` leaves existing files alone and says so, so the script is safe to re-run.

### 1.2 The generated source compiles as written

The point of the scaffold is that its output builds, so this was checked rather than assumed —
**observed**, exit code 0, four class files (entry class plus three anonymous hook classes):

```
$ javac -encoding UTF-8 -source 8 -target 8 -nowarn -cp "<android.jar>;<api-82.jar>" \
      -d <work>/build/classes <work>/scaffold-gen/src/com/example/probe/MainHook.java
$ echo $?
0
MainHook.class  MainHook$1.class  MainHook$2.class  MainHook$3.class
```

## 2. Gradle-free build chain — observed end to end

Built with a parameterised driver that reproduces the chain documented in the reference. Times are
wall-clock on the host above; the module is one class.

| Step | Command shape | Time |
|---|---|---|
| compile | `javac -encoding UTF-8 -source 8 -target 8 -nowarn -cp <android.jar>;<api-82.jar> -d build/classes src/**/*.java` | 850 ms |
| jar | `jar cf build/classes.jar -C build/classes .` | 259 ms |
| dex | `d8.bat --min-api 24 --lib <android.jar> --output build build/classes.jar` | 1143 ms |
| link | `aapt2.exe link -o build/base.apk -I <android.jar> --manifest AndroidManifest.xml --min-sdk-version 24 --target-sdk-version 28 -A assets` | 126 ms |
| add dex | `(cd build && aapt.exe add unsigned.apk classes.dex)` | 97 ms |
| align | `zipalign.exe -f -p 4 build/unsigned.apk build/aligned.apk` | 76 ms |
| sign | `apksigner.bat sign --ks build/test.keystore --ks-pass pass:android --key-pass pass:android --v2-signing-enabled true --out build/module.apk build/aligned.apk` | 1794 ms |
| verify | `apksigner.bat verify --min-sdk-version 24 --print-certs build/module.apk` | 725 ms |
| | **total** | **5.27 s** |

Resulting artifact, **observed**: `module.apk` 12,745 bytes, `classes.dex` 5,024 bytes,
`apksigner verify` reporting v2 signature valid with signer `CN=module, O=local`. APK entry list
(**observed**, read back with zipfile):

```
AndroidManifest.xml   1680
resources.arsc          40
assets/xposed_init      27
classes.dex           5024
META-INF/MANIFEST.MF   375
```

A second, independent build of a hand-written one-class module (different package, different source)
produced the same shape and also verified, so the chain is not specific to the scaffold's output.

### 2.1 Three build-chain traps, all measured rather than assumed

These are the failures that cost time, quoted from the actual runs:

1. **`d8` rejects a directory as program input.** Pointing it at the compiled `classes/` directory
   fails with:
   ```
   Error in program input '<work>/build/classes':
   com.android.tools.r8.internal.Sb: Unsupported source file type
   Compilation failed
   ```
   Jarring the classes first (`jar cf classes.jar -C classes .`) and passing the jar succeeds. This is
   the opposite of what several command-line guides imply.
2. **`aapt add` fails with `Unable to add 'classes.dex' to 'unsigned.apk': file not found`** when the
   dex is not in the current working directory. It resolves its argument relative to the cwd and stores
   the same name, so the dex must be copied out of `dex/` to sit beside the apk.
3. **`jar` and `keytool` are not on `PATH` even where `javac` is.** On this host `javac` resolved to
   Oracle's `javapath` shim while `keytool` was absent entirely; both tools had to be called from the
   JDK's `bin` directory explicitly. A build script that assumes they are on `PATH` breaks on a
   working machine.

Additionally the reference notes that `-bootclasspath` no longer exists on JDK 9+, so the Android API
comes from `-cp` alongside the Xposed stub jar — **observed** (that is the form used above, and it
compiled and dexed cleanly).

## 3. Module state on the device — observed

A previously built probe module was already installed on the device from an earlier pass. Its state
was read, not modified, except where noted:

```
$ adb -s <serial> shell "pm path com.t1.lsphook"
package:/data/app/~~<hash>==/com.t1.lsphook--<hash>==/base.apk

$ adb -s <serial> shell "dumpsys package com.t1.lsphook | grep -E 'User 0|enabled'"
    User 0: ceDataInode=35322 installed=true ... stopped=true notLaunched=true enabled=0 ofs=0 ...
```

`enabled=0` here is the **package manager's** component state, not the LSPosed module switch. Enabling
the package was the one state change this pass made on the device:

```
$ adb -s <serial> shell "pm enable com.t1.lsphook"
Package com.t1.lsphook new state: enabled
$ adb -s <serial> shell "dumpsys package com.t1.lsphook | grep 'User 0'"
    User 0: ... enabled=1 ...
```

LSPosed itself, **observed**:

```
$ adb -s <serial> shell "su -c 'cat /data/adb/modules/zygisk_lsposed/module.prop'"
id=zygisk_lsposed
name=Zygisk - LSPosed
version=v1.9.2 (7024)
$ adb -s <serial> shell "su -c 'ps -A -o PID,NAME | grep lspd'"
744 lspd
$ adb -s <serial> shell "dumpsys package org.lsposed.manager | grep versionName"
    versionName=1.9.2
```

### 3.1 The installed module could never have run — observed

Before reusing that module for an injection attempt, its internals were checked. `assets/xposed_init`
declared one entry class while the dex in the same APK contained a different one:

```
$ python -c "... zipfile.ZipFile('installed-module.apk').read('assets/xposed_init') ..."
com.t1.lsphook.MainHook

$ dexdump -f installed.dex | grep 'Class descriptor'
  Class descriptor  : 'Lcom/example/t1probe/ProbeHook$1;'
  Class descriptor  : 'Lcom/example/t1probe/ProbeHook$2;'
  Class descriptor  : 'Lcom/example/t1probe/ProbeHook$3;'
  Class descriptor  : 'Lcom/example/t1probe/ProbeHook;'
```

The entry class named in `xposed_init` does not exist in that dex (`MainHook` appears nowhere in the
string table; `ProbeHook` does). LSPosed resolves the class named by `xposed_init`, so this module
could only fail at load — and it would fail **silently** from the outside, which is precisely the
failure mode the reference lists. Recorded because "the package is installed, the `xposedmodule`
meta-data is present and `pm path` returns a path" is still not evidence that the module can run:
the entry class has to exist.

Two consequences measured in the same check:

- A second APK produced by that earlier pass **did** contain the matching class, but was signed with a
  different key — signer DN `O=local` against the installed build's `O=tools`, SHA-256
  `892c18be…` against `9c86f386…`. Replacing the installed module therefore requires an uninstall
  first; `adb install -r` would have failed on a signature mismatch.
- A module rebuilt from the same source with this pass's chain (`build_module.ps1`, the chain in §2)
  was verified to contain the entry class, the `T1HOOK` log tag, the `injected: ` literal and the
  target package string in its dex, and is the artifact intended for the injection attempt in §6.
  Building it took 5.07 s and produced 12,745 bytes.

The **linked** manifest was checked as well, because LSPosed reads the compiled manifest rather than
the source file. `aapt2 dump xmltree <apk> --file AndroidManifest.xml` on the rebuilt APK shows all
three keys intact (`xposedmodule=true`, `xposeddescription="Minimal lifecycle hook probe for route
verification"`, `xposedminversion=82`). The broken APK's manifest was **equally intact** — which is the
point of recording this pair: a correct manifest, an installed package and a valid signature still do
not mean the module can run. Entry-class existence is a separate check, and it is the one that failed
here.

### 3.2 Replacing it, and an install failure that belongs to the ROM — observed

The broken module was removed and the rebuilt one installed. The install path is worth recording
because it failed for a reason that has nothing to do with LSPosed:

```
$ adb -s <serial> uninstall com.t1.lsphook
Success
$ adb -s <serial> install module.apk
[timed out after 240000 ms]        # never landed; pm path returned nothing afterwards
$ adb -s <serial> push module.apk /data/local/tmp/<work>/module.apk
$ adb -s <serial> shell "pm install -r /data/local/tmp/<work>/module.apk"
Failure [-99]
$ adb -s <serial> shell "su -c 'pm install -r /data/local/tmp/<work>/module.apk'"
Success
```

Three findings from that sequence:

- `Failure [-99]` from a shell-identity `pm install`, with logcat showing the ROM's own security
  centre (`com.coloros.safecenter`) taking the foreground from `com.android.packageinstaller` at the
  same moment. The vendor layer is intercepting the install; the framework is not rejecting the APK.
- The same APK installs without complaint as **root**. That is the working path on this ROM, and the
  one used here.
- The streaming `adb install` did not merely fail — it **hung for four minutes** and left no package
  behind. Retrying as root is cheaper than waiting that out.

Installed state afterwards, **observed**:

```
$ adb -s <serial> shell "pm path com.t1.lsphook"
package:/data/app/~~c7aQQNK-GiP3BKd1g1iEvw==/com.t1.lsphook-<hash>/base.apk
$ adb -s <serial> shell "pm enable com.t1.lsphook"
Package com.t1.lsphook new state: enabled
$ adb -s <serial> shell "dumpsys package com.t1.lsphook | grep 'User 0'"
    User 0: ... installed=true ... enabled=1 ...
```

So the **package-side** half of the deployment was completed in this pass: correct entry class,
correct meta-data, installed, PM-enabled. The scope half did not happen, for the reason in §6.

## 4. Where LSPosed keeps module and scope state — observed

The configuration database was copied off the device (three WAL files) and parsed read-only:

```
$ adb -s <serial> shell "su -c 'cp -f /data/adb/lspd/config/modules_config.db* /data/local/tmp/<work>/'"
$ adb -s <serial> pull /data/local/tmp/<work> ...
```

Schema and contents, **observed** (SQLite):

```
CREATE TABLE modules (mid integer PRIMARY KEY AUTOINCREMENT, module_pkg_name text NOT NULL UNIQUE,
                      apk_path text NOT NULL, enabled BOOLEAN DEFAULT 0 CHECK (enabled IN (0,1)))
CREATE TABLE scope   (mid integer, app_pkg_name text NOT NULL, user_id integer NOT NULL,
                      PRIMARY KEY (mid, app_pkg_name, user_id), ...)
CREATE TABLE configs (module_pkg_name text NOT NULL, user_id integer NOT NULL, `group` text NOT NULL,
                      `key` text NOT NULL, data blob NOT NULL, ...)

== table modules ==
  (1, 'lspd', '/data/adb/modules/zygisk_lsposed/manager.apk', 0)
  (2, 'com.t1.lsphook', '/data/app/~~<hash>==/com.t1.lsphook--<hash>==/base.apk', 0)
== table scope ==
  (no rows)
== table configs ==
  ('lspd', 0, 'config', 'misc_path', <blob>)
```

Three facts worth keeping from this, because each maps to a documented failure mode:

- `enabled` in the LSPosed database is a **separate** bit from the package manager's `enabled` state.
  Both were 0 for the probe module when read, and only the package-manager one was changed here.
- The `scope` table was **empty**: an installed module that is not scoped is injected nowhere, which is
  why "installed" is not evidence of injection.
- `sqlite_sequence.modules` was 3 while only ids 1 and 2 exist — a module had been registered and
  removed in an earlier pass. The ids are not a count of what is loaded.

## 5. lspd lifecycle — observed from its own startup scripts

Read from the installed module directory, **observed**:

```
$ adb -s <serial> shell "su -c 'cat /data/adb/modules/zygisk_lsposed/service.sh'"
...
unshare -m sh -c "$MODDIR/daemon --from-service $@&"

$ adb -s <serial> shell "su -c 'cat /data/adb/modules/zygisk_lsposed/daemon'"
...
exec /system/bin/app_process $java_options /system/bin --nice-name=lspd org.lsposed.lspd.Main "$@"
```

`service.sh` is Magisk's late-start service script, which runs once per boot. **Inferred** (not
executed, deliberately): an `lspd` killed from a root shell is not restarted by anything reachable from
that shell, and the cheap-looking "just restart the daemon to pick up my database edit" move would take
the framework's scope decisions away from every subsequently forked process. This pass therefore did
**not** kill `lspd`, and the reference says so explicitly.

Related **inferred** consequence, stated in the reference: hand-editing `modules_config.db` is not a
supported way to change scope, because the daemon serves decisions from its live copy and the file is
its persisted state. The manager path updates both.

## 6. Injection: the framework had to be repaired first, then it worked — observed

With the module installed and PM-enabled, the next step was LSPosed Manager: enable the module there
and add the sample to its scope. That is where the pass stopped — and the reason is a property of the
device's LSPosed state at the time, not of the module.

Manager opened normally but reported the framework as **not installed**. Observed both on screen and in
the dumped node tree:

```
node: "未安装" / "LSPosed 未安装"          (overview status card)
node: "API 版本"        -> "未安装"
node: "Xposed API 调用保护" -> "未安装"
node: "Dex 优化器包装"   -> "未安装"
bottom navigation: 仓库 / 概览 / 设置       # there is no module-list tab in this state
```

The daemon was still alive (`ps -A` → `744 lspd`), so this is not "LSPosed is absent". Two further
observations pin down what it actually is:

- **`lspd` stopped updating its own configuration.** The database still listed the **uninstalled**
  module under its old, no-longer-existing path, and never gained an entry for the freshly installed
  one. Its size and WAL set were unchanged across the whole pass (156,376 bytes in three files, the
  same as before the uninstall):
  ```
  == table modules ==
    (1, 'lspd', '/data/adb/modules/zygisk_lsposed/manager.apk', 0)
    (2, 'com.t1.lsphook', '/data/app/~~wiGaHYIZn5j3Am2JrJvA5g==/com.t1.lsphook-<hash>/base.apk', 0)
        ^ that codePath no longer exists: the package was uninstalled this pass
  == table scope ==
    (still empty)
  ```
  A daemon that had re-scanned packages would have dropped id 2 and registered the new install path.
- **Its log records the framework bridge dying and never recovering.** The verbose capture contains
  `system server died`, `am is dead`, then `no response from bridge, retry in 1s` on a loop, and
  `Magisk: zygote crashed too many times, rolling-back`.

`[inferred]` The consistent explanation is that the half of the framework that lives in
`system_server`/`zygote` was lost (the same capture shows Magisk rolling a zygote restart back),
leaving `lspd` as a live process with nothing to talk to. Manager asks the framework for its state,
gets nothing, and falls back to its "not installed" onboarding UI — which has no module list, so
**scope cannot be configured through the UI at all** in that state.

Recorded consequences, deliberately not worked around:

- Scope was **not** configured, so no module was injected into any process, so no `T1HOOK` line could
  appear. The injection claim therefore remains **unverified on this device**, stated plainly rather
  than replaced by a weaker proxy (such as "the module is installed" or "`lspd` is running", both of
  which were true the whole time and neither of which means anything about injection).
- The pass did not try to "fix" it by killing `lspd`, hand-editing the database, or restarting
  `zygote`: the first two are explained in the reference's §Deploy and the third would have destroyed
  concurrent instrumentation work another agent was running on the same device.
- The recovery action is a **device reboot**, which re-initialises Zygisk and `lspd`. It was not taken
  because the device was shared and under heavy load. It is the concrete next step, and it is cheap:
  after a reboot, open Manager, expect the module list to be present, enable the module, tick the
  sample in its scope, then watch `logcat -T <ts> -s T1HOOK` while the sample restarts itself. Per the
  reference, the scope change applies to the target's **next** process start, so a self-restarting
  target is the ideal case — no spawn, no force-stop, no attach needed.
- Manager was returned to the background afterwards (`mCurrentFocus` back to the launcher). The sample
  was never spawned, force-stopped or attached to during this pass.

### 6.1 The repair — observed

A reboot was approved and taken. It is the whole fix, and it is cheap:

```
$ adb -s <serial> reboot
[  0 s] boot_completed=''      ... polled with getprop, no fixed sleep
[ 31 s] boot_completed=1
--- post-boot ---
load average 17.40 4.37 1.46          (was 29.58 31.87 33.61 before)
   746 lspd                            (new pid; was 744)
MoveCertificate  zygisk-assistant  zygisk_lsposed   (all three modules present)
```

Manager then reported the framework normally, and the **module tab appeared** — the recovery
criterion. Observed on the overview page: `已激活 / 1.9.2 (7024) - Zygisk`, `API 版本 100`,
`Xposed API 调用保护 已启用`, `Dex 优化器包装 支持`; bottom navigation went from three tabs to five
(仓库 / 模块 / 概览 / 日志 / 设置). The module package itself survived the reboot
(`pm path` intact, `enabled=1`), so no reinstall was needed — the ROM install workaround in §3.2 only
matters on a fresh install.

### 6.2 Configuring scope through the UI — observed

Done strictly by reading coordinates out of a `uiautomator dump`, never by tapping a guess:

| Step | What was read from the dump | Coordinate tapped | Result |
|---|---|---|---|
| module tab | `[216,2160][432,2293]` | (324, 2260) | module list opened |
| module row | `T1 LSPosed probe`, row `[48,611][1008,793]` | (528, 702) | detail page |
| enable switch | switch node `[804,651][972,795]` | (888, 723) | `checked=true` |
| scope row | `<PKG>`, row `[252,1855][591,1912]` | (528, 1878) | `checked=true` |

The scope list had to be scrolled five screens to reach the target (the list is alphabetical by
display name, not by package). The database then confirmed the change, and — for the first time in
this whole exercise — **`lspd` wrote to it**:

```
== table modules ==
  (2, 'com.t1.lsphook', '/data/app/~~c7aQQNK-GiP3BKd1g1iEvw==/com.t1.lsphook-<hash>/base.apk', 1)
                                                                                    enabled ^ = 1
== table scope ==
  (2, '<PKG>', 0)
```

The database file grew from 156,376 to 201,696 bytes across the pass. Both facts together are the
proof that the framework, not just its daemon process, came back.

### 6.3 The injection line, and where it actually appears — observed

The target was launched once with `am start`, and the module fired on **every** subsequent process
start. Nine consecutive target starts produced nine full injection blocks:

```
Loading legacy module com.t1.lsphook from /data/app/~~c7aQQNK-GiP3BKd1g1iEvw==/.../base.apk
  Loading class com.t1.lsphook.MainHook
T1HOOK injected: <PKG> / <PKG> cl=dalvik.system.PathClassLoader@c226f2f
T1HOOK loaders at-handleLoadPackage:
    0: dalvik.system.PathClassLoader c226f2f
    1: java.lang.BootClassLoader 8454a72
T1HOOK hook installed: Application.attach
T1HOOK hook installed: Activity.onCreate
T1HOOK hook installed: Application.onCreate
T1HOOK Application.attach #1 this=<PKG>.BaseApplication cl=dalvik.system.PathClassLoader@c226f2f
T1HOOK Application.attach #2 this=com.stub.StubApp            cl=dalvik.system.PathClassLoader@c226f2f
T1HOOK Application.onCreate this=com.stub.StubApp
T1HOOK Application.onCreate this=<PKG>.BaseApplication
T1HOOK Activity.onCreate -> <PKG>.MainActivity
T1HOOK injected: com.google.android.webview / <PKG> cl=dalvik.system.PathClassLoader@141f448
T1HOOK Activity.onCreate -> com.qq.e.ads.PortraitADActivity
```

**The verification criterion had to be corrected, and this is the most transferable finding of the
pass.** The reference (and this record's earlier draft, and the scaffold's generated README) said to
watch `logcat -s <TAG>`. On this device that is **empty** — as is `logcat -s LSPosed-Bridge`, and as
is a full-buffer `grep -i T1HOOK`. The module's output exists only in

```
/data/adb/lspd/log/modules_<timestamp>.log
```

which is the same file that earlier appeared to contain nothing but `Logd maybe crashed (err=Socket
operation on non-socket), retrying in 1s...`. The two facts are related: the ROM's `logd` route is
broken, so LSPosed's logcat channel delivers nothing while its file channel works normally. Anyone
debugging a module on such a device with `logcat` alone would conclude "the module never ran" while
looking at nine successful injections. Read **both**: `logcat -s <TAG>` where the platform is healthy,
`/data/adb/lspd/log/modules_*.log` always. The evidence file for this pass is 201 lines, of which 126
are `T1HOOK`.

Three further observations from the same log, none of which needed any extra instrumentation:

- **The packer's double Application is visible in the hook order.** `Application.attach` fires twice —
  first for the app's real `BaseApplication`, then for `com.stub.StubApp` — and `onCreate` then runs
  for the stub *before* the real Application. Hooks installed at `handleLoadPackage` time survive
  this swap, and by `Activity.onCreate` the classes reported are the **unpacked** ones
  (`<PKG>.MainActivity`), not the stub's. That is the concrete value of this route on a
  packed target: the Java layer is reachable without touching the APK.
- **Scope is per app, not per process.** The module also injected into the app's WebView process
  (`com.google.android.webview / <PKG>`) and reported the ad SDK's activity
  (`com.qq.e.ads.PortraitADActivity`) — worth knowing before scoping a module widely.
- **The target's self-restart cycle is unaffected by injection.** Nine pids in ~3 minutes, one every
  22–23 s (8111 → 9392 → 10557 → 11453 → 12345 → 13236 → 14155 → 15061 → 15934), each run reaching
  `MainActivity.onCreate`, the WebView process and an ad activity before ending. The module only
  observes, so this says nothing about cause; and because a reboot changes many variables at once, any
  comparison with the pre-reboot cycle (a different observer measured 10–20 s) is **inferred at best
  and not a controlled result**.

## 7. Log surfaces — observed, and one trap

```
$ adb -s <serial> shell "su -c 'ls -la /data/adb/lspd/log/'"
kmsg.log                          993690
modules_2026-09-21T18:44:31.523.log  401
props.txt                          46937
verbose_2026-09-21T18:44:31.518.log 178482
```

The `modules_*.log` file is **not** module output. Its entire content, **observed**:

```
----part 1 start----
Logd maybe crashed (err=Socket operation on non-socket), retrying in 1s...
   (repeated)
```

`verbose_*.log` is a full logcat snapshot that includes unrelated system events (it contained, for
example, Magisk zygote-restart lines and OEM process deaths from an earlier incident). Useful for
correlating a run with system state; useless as a module log. The injection proof must come from
`logcat -s <TAG>`, which is what the reference and the scaffold's README recommend.

## 8. Root-hiding layer — observed

```
$ adb -s <serial> shell "su -c 'cat /data/adb/modules/zygisk-assistant/module.prop'"
id=zygisk-assistant
name=Zygisk Assistant
version=v2.1.4 (1013f8a-release)
description=A Zygisk module to hide root.

$ adb -s <serial> shell "su -c 'magisk --denylist status'"
Denylist is enforced
$ adb -s <serial> shell "su -c 'magisk --denylist ls'"
   (no output)
$ adb -s <serial> shell "su -c 'ls /data/adb/shamiko'"
ls: /data/adb/shamiko: No such file or directory
```

So at pass time the DenyList was **enforced but empty**: no process was being hidden from anything,
while LSPosed and `lspd` were running normally, and Shamiko was not installed. Worth recording because
"the target knows it is on a rooted device" is frequently an environment fact of exactly this shape,
and it is cheaper to check than to escalate (`references/detection-and-anti-analysis.md`).

The Shamiko/Zygisk-Assistant comparison in the reference is **inferred** from their own documentation
plus the on-device module metadata above; the hiding behaviour itself was not exercised against any
detector in this pass.

## 9. Not run / open items

- **Injection is not verified, and the blocker is now identified rather than unknown.** §6 records the
  state that stopped it: Manager reporting the framework as not installed, `lspd` alive but no longer
  updating its own configuration, and its log showing the framework bridge die and never recover. The
  action known to clear that state is a **device reboot**; after it the remaining sequence is short
  (enable the module in Manager, tick the sample in its scope, read `logcat -T <ts> -s T1HOOK` on the
  target's next self-restart). Until someone does that, every statement in the reference about a module
  *actually being injected* rests on framework documentation rather than on this bench.
- Editing `modules_config.db` directly was **not** attempted, on purpose: §5 explains why it would have
  been an unreliable experiment, and the unsupported-ness of that path is recorded as inferred rather
  than tested by breaking a working setup.
- Killing/restarting `lspd` was **not** attempted, for the same reason.
- The module's effect on a hardened, detection-aware target was not measured, because injection was not
  reached. Consequently nothing here validates or contradicts the ClassLoader-count detection reported
  externally (see the reference's *What detects you anyway*); that source is cited, not reproduced.
- The vendor install interception (§3.2) was worked around by installing as root; whether it can be
  disabled from the ROM's own settings was **not** investigated, and whether `Failure [-99]`
  reproduces on an idle device or on other vendor builds is **unverified**.
- `scaffold.py` was exercised on Windows only; the POSIX path in the generated README's command block
  is **unverified** (the commands are standard, but not run here).

## 10. Reproduction one-liners

```
python skills/apk-reverse/scripts/lsposed_scaffold.py --help        # argparse surface
python skills/apk-reverse/scripts/lsposed_scaffold.py --package <pkg> --name "<name>" \
    --hook-target <target.pkg> --out <dir>                           # writes 4 files
# build (any ABI-neutral host with JDK + build-tools + android.jar + api-82.jar)
javac -source 8 -target 8 -cp "<android.jar>:<api-82.jar>" -d build/classes src/**/*.java
jar cf build/classes.jar -C build/classes .                          # d8 needs a jar, not a dir
d8 --min-api 24 --lib <android.jar> --output build build/classes.jar
aapt2 link -o build/base.apk -I <android.jar> --manifest AndroidManifest.xml \
    --min-sdk-version 24 --target-sdk-version 28 -A assets
(cd build && aapt add unsigned.apk classes.dex)                      # dex must be in the cwd
zipalign -f -p 4 build/unsigned.apk build/aligned.apk
apksigner sign --ks build/test.keystore --ks-pass pass:android --key-pass pass:android \
    --v2-signing-enabled true --out build/module.apk build/aligned.apk
apksigner verify --print-certs build/module.apk

adb -s <serial> shell "pm path <module.pkg>"                         # installed?
adb -s <serial> shell "dumpsys package <module.pkg> | grep 'User 0'"  # pm enabled state
adb -s <serial> shell "su -c 'ps -A -o PID,NAME | grep lspd'"         # daemon alive
adb -s <serial> shell "su -c 'magisk --denylist status'"              # hiding layer state
```
