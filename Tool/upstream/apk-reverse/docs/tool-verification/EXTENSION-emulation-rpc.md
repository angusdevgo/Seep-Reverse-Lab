# Extension verification — offline emulation (unidbg) and Frida RPC

Covers the 2026-09 extension pass that added `references/emulation-and-rpc.md`,
`scripts/frida_rpc_serve.py` and `scripts/rpc_template.js`. Strength labels as defined in this
directory's README: **observed** (exact command + output recorded here), **inferred** (follows from
observed facts, step not executed), **unverified** (assumed or externally reported, not independently
confirmed here).

Reference environment for this pass: Windows host, Python 3.14.0, host `frida` 16.7.19 +
`frida-python` 16.7.19 (frida-tools 13.7.1), `adb` 37.0.1, JDK 17.0.4.1 (with `JAVA_HOME`
**unset** in the shell — see §5). Device `<DEVICE>`: Android 11 / API 30, arm64-v8a, rooted
(Magisk), on-device frida-server 16.7.19. Workbench artifacts live in `tools/_work/t3-rpc/` (not part
of the skill).

**Device-exclusivity constraint during this pass**: another task was unpacking the hardened Flutter
sample on the same device. This pass never attached to, spawned or force-stopped that sample's
process, and never killed or restarted the device-side frida-server. All RPC work targeted unrelated
processes (system apps and third-party apps). De-identification: the sample's package label, real
package name and md5 are elided in this document as `com.example.app` / `<label>`; command shapes,
counts, class names and timings are verbatim.

---

## 0. Summary of what this pass established

| Claim | Label |
|---|---|
| `droidasc` 0.1.1.post1 and `ddc` 0.1.8 both run on this host; both read the hardened sample's shell dex | observed |
| Both tools see only the 4 shell classes in the APK's dex; business classes are absent (shell dex only) | observed |
| `frida_rpc_serve.py` `--help`, all three modes, reconnect, spawn and attach-by-pid work against a live device | observed |
| Attach **by package name** fails on this ROM while attach **by pid** succeeds for the same process | observed |
| The device-side server may be (re)started on a non-default port; `--remote HOST:PORT` recovers, device-serial lookup does not | observed |
| unidbg 0.9.10-SNAPSHOT builds and boots an Android emulator on this host after a pom fix; one bundled test suite passes | observed |
| Any target `.so` actually emulated under unidbg | **not done** (unverified) |
| frida 17 compatibility of `rpc_template.js` export lookup | unverified (host has 16.7.19 only) |

---

## 1. ASC (`droidasc`) — observed

### 1.1 Install and version

```
$ python -m pip show droidasc
Name: droidasc
Version: 0.1.1.post1
Summary: ASC is a super FAST python Android Decompiler for Agents/Mobile Researchers
License-Expression: Apache-2.0
Location: C:\Python314\Lib\site-packages
Requires: androguard
```

Install line used (recorded after the fact; the package was already present on this host):
`python -m pip install droidasc`. Distribution metadata declares only `androguard` as a dependency —
**no JVM is required** (unlike the `asc` successor tooling in the upstream MG1937/ASC repository,
which is a separate project). The console script is named **`droidasc`**, not `asc`: there is no
`asc.exe` in `C:\Python314\Scripts`, and `asc --version` fails with
`The term 'asc' is not recognized...`. `python -m droidasc` is the equivalent entry point.

### 1.2 Subcommands

```
$ python -m droidasc --help
usage: python.exe -m droidasc [-h]
                              {getclass,listclass,getmanifest,findrefs} ...
ASC tooling entry.
positional arguments:
  {getclass,listclass,getmanifest,findrefs}
    getclass     Locate the target class in APK, extract one DEX in memory, then decompile.
    listclass    List classes across all DEX entries; use --prefix to filter by package/class prefix.
    getmanifest  Decode AndroidManifest.xml from APK and print it as XML.
    findrefs     Find code references for string/type/method/field across all DEX entries in APK.
examples:
  droidasc app.apk --gui
  droidasc getclass app.apk Lcom/poc/Main; -o Main.java
  droidasc listclass app.apk --prefix com.poc
  droidasc getmanifest app.apk -o AndroidManifest.xml
  droidasc findrefs app.apk string token -o string_refs.txt
```

`--gui` and the bundled `asc_client` web UI were **not** exercised (unverified, headless pass).

### 1.3 Measured against the sample

```
$ droidasc getmanifest <sample>.apk -o asc-manifest-verify.xml          # 0.44 s, 32,345 B
<manifest ... package="com.example.app" platformBuildVersionCode="34" ... android:versionCode="1143"
          android:versionName="0.9.0" android:compileSdkVersion="34" ...>
  <uses-sdk android:minSdkVersion="19" android:targetSdkVersion="28"/>
  <uses-permission android:name="android.permission.INTERNET"/>
  ... (permissions list follows; manifest decodes cleanly)

$ droidasc findrefs <sample>.apk string jiagu -o asc-findrefs-jiagu.txt  # 0.42 s
classes.dex | Lcom/stub/StubApp;-><clinit> | matched=(libjiagu)
classes.dex | Lcom/stub/StubApp;->attachBaseContext | matched=(/.jiagu; jiagu; jiagu_x86)

$ droidasc getclass <sample>.apk com.stub.StubApp -o asc-StubApp-verify.java   # 0.33 s, 22,802 B
package com.stub;
public final class StubApp extends android.app.Application { ... }

$ droidasc listclass <sample>.apk --prefix com.stub                       # 0.23 s
Lcom/stub/StubApp;

$ droidasc listclass <sample>.apk -o asc-listclass-all.txt                # 0.18 s, 4 lines
Lcom/stub/StubApp;
Lcom/tianyu/util/Configuration;
Lcom/tianyu/util/DtcLoader;
Lcom/tianyu/util/a;
```

`findrefs` reports the shell's own strings (`libjiagu`, `jiagu_x86`, `/.jiagu`) — i.e. the packer
signature is visible without unpacking, but nothing of the application is.

### 1.4 Limits hit

```
$ droidasc getclass <sample>.apk com.example.app.MainActivity -o asc-mainactivity.java
Error: Class Lcom/example/app/MainActivity; not found in APK.
exit = 1
```

**This is the limit that matters for this sample class:** the full class listing is 4 classes, so on
a packed APK ASC is a manifest + shell-inspector, not an application decompiler. The application code
lives in that shell's payload (`assets/`, the native unpacker and the AOT/Flutter layer), which ASC
does not touch. ASC still earns its place in the flow: `getmanifest` in under half a second is the
fastest manifest pass measured in this repository's tool set, and `findrefs` on shell class names is
how the packer was identified here.

Observed behaviours worth knowing: `droidasc` prints per-command timing nowhere, writes to `-o` only,
and returns a clean `Error: ...` line plus exit 1 when a class is missing.

---

## 2. ddc — observed

### 2.1 Version and acquisition

```
$ bin/ddc.exe -V
ddc 0.1.8 — DEX → Java decompiler
https://github.com/ejfkdev/ddc
```

`ddc` is a Rust binary (upstream: [ejfkdev/ddc](https://github.com/ejfkdev/ddc)); the Windows build
used here is `tools/_work/t3-rpc/bin/ddc.exe`, 1,028,096 B, **not on `PATH`** and with no version
resource in the PE header (`VersionInfo` empty), so `ddc -V` is the only way to learn its version.
No JVM, no Python. Subcommands advertised by `ddc help`: `info`, `listclasses`, `manifest`,
`mainactivity`, `res`, `strings`, `findrefs`, `callers`, `members`, `hierarchy`, `largest`, `disasm`,
`getclass`, `getmethod`, plus a full-decompile mode (`ddc <INPUT>... [OUTPUT]`).

### 2.2 Measured against the sample

```
$ bin/ddc.exe info <sample>.apk                                     # 0.24 s
label        <label>
package      com.example.app
version      0.9.0 (1143)
application  com.stub.StubApp
launcher     com.example.app.MainActivity
sdk          19–28
size         36.9 MB (38688120 bytes)
md5          1a037a045205184d4e8272092997334f

     image       dex     classes     methods     fields     strings
<sample>!classes.dex       035           4         266         23         481
total: 1 image(s), 4 classes

$ bin/ddc.exe findrefs <sample>.apk string jiagu                    # 0.13 s
dex         kind          class method refs
classes.dex  const-string  com/stub/StubApp <clinit>()V  "libjiagu"
classes.dex  const-string  com/stub/StubApp attachBaseContext(...)V  "jiagu_x86"; "jiagu"; "/.jiagu"

$ bin/ddc.exe strings <sample>.apk -f jiagu --with-locations        # 0.14 s
dex         string  used-by
classes.dex  "/.jiagu"  com/stub/StubApp attachBaseContext(Landroid/content/Context;)V
classes.dex  "jiagu"  com/stub/StubApp attachBaseContext(Landroid/content/Context;)V
classes.dex  "jiagu_x86"  com/stub/StubApp attachBaseContext(Landroid/content/Context;)V
classes.dex  "libjiagu"  com/stub/StubApp <clinit>()V
```

`ddc info` reaches the same conclusion as ASC by a different route (class/method/string counts per
dex image) and adds the resources-derived label and the launcher verification; `findrefs` output is
tabular and one line per (method, string) pair, which is directly pasteable into a report.

### 2.3 Limits hit

```
$ bin/ddc.exe getclass <sample>.apk com.example.app.MainActivity
ddc: class com.example.app.MainActivity not found in the selected image(s)
       (try `ddc listclasses <input> <pattern>`)
exit = 2
```

Exit codes measured on this build: `info` → 0, `-V` → 0, `getclass` with a missing class → **2**.
The missing-class path also reprints the full help text on stdout, so a wrapper that only checks
"did anything print" will misread it as success — key off the exit code. As with ASC, the packed APK
exposes only the shell dex; `ddc` cannot see application classes either, which is a property of the
artifact, not of the tool.

---

## 3. Prior-attempt outputs under test — and the defects found

`skills/apk-reverse/references/emulation-and-rpc.md`, `scripts/frida_rpc_serve.py` and
`scripts/rpc_template.js` were already on disk from an interrupted attempt of this task. This pass
read all three, ran the script, and fixed four defects. `rpc_template.js` needed no change.

| # | Defect (observed) | Fix |
|---|---|---|
| 1 | `RpcBridge._teardown()` never detached the session and used `obj.off(...) if obj is self.session else None` / `obj.unload() if hasattr(obj, "unload")` — a script object has `unload()`, a session has `detach()`, so the expression released only the script. Every `reload()`/reconnect cycle leaked one attached session on the device. | Rewritten to unload the script, remove the `detached` handler and `session.detach()` explicitly. |
| 2 | `list_exports()` called `Script.list_exports()`, which frida 16.7.19 answers with `DeprecationWarning: Script.list_exports will become asynchronous in the future, use the explicit Script.list_exports_sync instead` (printed on every `list` command). | Tries `list_exports_sync` first, then the old name, then local introspection. |
| 3 | `--mode call` raised out of `main()`: an unknown export produced `frida`'s own `unable to find method 'x'` and a raw Python traceback; a bad `--args` value dumped a `JSONDecodeError` traceback. Scripted callers got a stack trace instead of a result. | `run_call_mode()` now returns one JSON object (`{"ok": false, "error": ...}`) and exit code 1 for both cases; `call()` consults the advertised export list first so the message is `no such rpc export: nope (available: add ping ...)`. |
| 4 | `frida.TimedOutError` was absent from the retry whitelist. It is **not** a `TransportError` subclass (`frida.TimedOutError.__mro__` → `(TimedOutError, Exception, BaseException, object)`), so a device that timed out during attach produced a traceback in an otherwise recoverable situation — reproduced live (§4.4). | Retryable types are now collected by name into `RETRYABLE` (TransportError, NotSupportedError, ServerNotRunningError, ProcessNotFoundError, InvalidOperationError, TimedOutError) and used by both `ensure()` and the initial connect in `main()`. |

Post-fix evidence:

```
$ python skills/apk-reverse/scripts/frida_rpc_serve.py --remote 127.0.0.1:27043 --pid 19938 \
      --script skills/apk-reverse/scripts/rpc_template.js --mode call --export add --args "[40, 2]"
{"ok": true, "export": "add", "result": 42}                       exit = 0
$ ... --mode call --export nope
{"ok": false, "export": "nope", "error": "no such rpc export: nope
   (available: add ping getpackagename callnative callnativeaddr)"}   exit = 1
$ ... --mode call --export add --args "not-json"
{"ok": false, "error": "--args is not valid JSON: Expecting value: line 1 column 1 (char 0)"}
                                                                   exit = 1
```

Known cosmetic behaviour left as is: in `--mode call` the bridge connects before `--args` is parsed,
so a bad-args invocation still performs a device attach.

## 4. Frida RPC against the live device — observed

### 4.1 Attach path: by name fails, by pid works

Attach **by package name** failed for every package tried, with the process demonstrably alive in
both `frida-ps -Uai` and `ps -A`:

```
$ python ...frida_rpc_serve.py --device-serial <DEVICE> --package com.android.settings ...
[bridge] connect failed (unable to find process with name 'com.android.settings'); retry 1 in 1.0s
... (5 attempts) ...
initial connect failed: could not (re)connect after 5 attempts
$ python ... --package io.github.vvb2060.magisk ...
[bridge] connect failed (unable to find process with name 'io.github.vvb2060.magisk'); retry 1 in 0.5s
initial connect failed: could not (re)connect after 1 attempts
```

The same processes attach normally by pid:

```
$ python ... --pid 19938 --mode call --export getpackagename
{"ok": true, "export": "getpackagename", "result": "com.android.settings"}
$ python ... --pid 21493 --mode call --export getpackagename
{"ok": true, "export": "getpackagename", "result": "com.android.email"}
```

So the gap is in the **name→pid lookup** the server serves, not in injection: `--pid` definitely
does bypass it. `references/emulation-and-rpc.md` had claimed the opposite ("`--pid` does not bypass
a gap that hides the process from the server's own table"); that row was corrected in this pass, and
the corrected wording is what the reference now carries.

### 4.2 The transport itself

| # | Command (pid 19938 = `com.android.settings`, unrelated to the sample) | Result |
|---|---|---|
| 1 | `--mode call --export add --args "[40, 2]"` | `{"ok": true, "result": 42}` |
| 2 | `--mode call --export ping` | `{"ok": true, "result": "pong"}` |
| 3 | `--mode call --export getpackagename` | `{"ok": true, "result": "com.android.settings"}` |
| 4 | `--mode call --export callnative --args '["libc.so","getpid","int",[],[]]'` | `{"ok": true, "result": 19938}` (matches the pid — `NativeFunction` wrapping works) |
| 5 | `--mode repl`, feeding `list` / `reload` / `list` / `add [40, 2]` / `nope` | `add ping getpackagename callnative callnativeaddr`; `reloaded`; same list; `42`; `error: no such rpc export: nope (available: ...)` |
| 6 | `--mode http`, `GET /exports` | `{"ok":true,"exports":[...5 names...]}` |
| 7 | `--mode http`, `POST /call {"export":"add","args":[40,2]}` | `{"ok":true,"result":42}` |
| 8 | `--mode http`, `POST /call {"export":"getpackagename","args":[]}` | `{"ok":true,"result":"com.android.settings"}` |
| 9 | `--mode http`, `POST /call` with an unknown export | HTTP 502 + `{"ok":false,"error":"no such rpc export: nope (available: ...)"}` |
| 10 | `--mode http`, `POST /reload` then `POST /call add [1,2]` | `{"ok":true}` then `{"ok":true,"result":3}` — the re-attach path works, and no `DeprecationWarning` is printed any more |
| 11 | `--spawn --package io.github.vvb2060.magisk --mode call --export getpackagename` | `{"ok": true, "result": "io.github.vvb2060.magisk"}` (spawn → script load → resume → RPC) |

Every script load also delivered the template's own liveness message:
`[script] {"ev": "RPC-READY", "exports": ["add","ping","getpackagename","callnative","callnativeaddr"]}`.
That line is the cheapest health check for a session and is worth grepping for in automation.

### 4.3 The server's port moved under us

Mid-pass, `--device-serial <DEVICE>` began failing on attach while `frida-ps -U` kept working:

```
$ python ... --device-serial <DEVICE> --pid 19938 ...
[bridge] connect failed (unable to connect to remote frida-server: closed); retry 1 in 1.0s
... (3 attempts) ...

$ python -c "import frida;d=frida.get_device('<DEVICE>');d.attach(19938)"
attach failed: ServerNotRunningError unable to connect to remote frida-server: closed

$ adb -s <DEVICE> shell 'su -c "ps -A"' | Select-String 'svc16|frida'
root  1876  1  2227684  55288  do_sys_poll  S  .svc16            # only this instance alive
$ adb -s <DEVICE> shell 'su -c "netstat -ltnp"' | Select-String 2704
tcp  0  0  0.0.0.0:27043  0.0.0.0:*  LISTEN  1876/.svc16          # nothing on 27042
```

The visible `frida-server` process (pid 23405) was gone; a disguised copy (`.svc16`, pid 1876) was
listening on **27043 only**. `frida-ps -U` still worked because frida's USB transport probes a range
of ports, while the scripted device-serial path landed on a dead default port. Recovery, with the
forward already present (`adb forward --list` shows `tcp:27043 tcp:27043`):

```
$ python ... --remote 127.0.0.1:27043 --pid 19938 --mode call --export getpackagename
{"ok": true, "result": "com.android.settings"}
```

This pass neither started nor killed any server instance; it only observed that the instance changed
and switched to the explicit `--remote` form. That form is now the recommended one in the reference's
failure table.

### 4.4 A third-party process that refuses the handshake

```
$ python ... --remote 127.0.0.1:27043 --pid 19984 --mode call --export getpackagename
frida.TimedOutError: unexpectedly timed out while waiting for signal from process with PID 19984
```

An ordinary third-party app process (`com.xunmeng.pinduoduo`, listed by `frida-ps -Uai`) simply did
not answer the agent handshake within frida's timeout. Pre-fix this surfaced as a traceback; post-fix
the bridge treats it as retryable and reports `initial connect failed: ...` with exit 2. This is an
app-side property, not a bridge property — for connectivity probes prefer a system or stable app
process.

### 4.5 Device state after the pass

`frida-ps -U` and `frida-ps -Uai` both still answer; the sample's process was never touched; the
device-side server was never killed or restarted by this pass.

---

## 5. unidbg — observed (build/boot) and unverified (target emulation)

### 5.1 Build

```
$ git clone --depth 1 https://github.com/zhkl0228/unidbg.git      # version 0.9.10-SNAPSHOT
$ .\mvnw.cmd -B -pl unidbg-android -am -DskipTests compile
Error: JAVA_HOME not found in your environment.                   # JAVA_HOME was unset on this host
...
[ERROR] Failed to execute goal ...maven-compiler-plugin:3.3:compile on project unidbg-api:
[ERROR] .../AbstractARMDebugger.java:[79,43] reference to Module is ambiguous
[ERROR]   both com.github.unidbg.Module and java.lang.Module match
```

The shipped pom pins `<source>8</source><target>8</target>` with `maven-compiler-plugin` 3.3. On
JDK 9+ that pair does **not** select the JDK 8 API, so `java.lang.Module` stays visible and every
unqualified `Module` in `AbstractARMDebugger` becomes ambiguous — the build dies in `unidbg-api`.
Two local work-copy changes fix it (recorded in `tools/_work/t3-rpc/unidbg/pom.xml`, not part of the
skill and not committed):

```
maven-compiler-plugin 3.3   -> 3.8.1        # 3.13 is rejected: the bundled wrapper is Maven 3.5.4,
                                            # and 3.13 requires Maven >= 3.6.3
<source>8</source><target>8</target> -> <release>8</release>   # hides java.lang.Module
```

Result with `JAVA_HOME=C:\Program Files\Java\jdk-17.0.4.1`:

```
$ .\mvnw.cmd -B -pl unidbg-android -am -DskipTests compile
[INFO] unidbg-api ......... SUCCESS [ 40.838 s]
[INFO] unidbg-android ..... SUCCESS [  4.941 s]
[INFO] BUILD SUCCESS  (total 48.4 s, after a one-off dependency download)
```

### 5.2 Boot check

The pom sets `<maven.test.skip>true</maven.test.skip>`, so `-Dmaven.test.skip=false` is required to
run anything:

```
$ .\mvnw.cmd -B -pl unidbg-android -am -Dmaven.test.skip=false \
      -Dtest=MemoryTrackerTest -DfailIfNoTests=false test
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
Backend: DynarmicBackend64
=== Memory Leak Report === ... Address: 0x12000000, Size: 4096 ...
[INFO] BUILD SUCCESS
```

This proves the toolchain end to end at the *environment* level: emulator construction, memory
allocator, backend selection (Dynarmic, with Hypervisor and Unicorn2 factories registered) and
Android 11 (`AndroidResolver(23)`-style) library resolution all execute on this host.

### 5.3 What was **not** done — unverified

* Loading and calling **any** target `.so`, including this sample's `libjiagu*.so` or `libapp.so`.
  No `createDalvikVM`, `loadLibrary`, `callJNI_OnLoad` or `AbstractJni` stub was exercised.
* Consequently every per-library statement in `references/emulation-and-rpc.md` §Part A — which JNI
  callbacks a hardened library demands, how many stub rounds it costs, which `/proc` or signature
  checks it runs — remains **inferred** from the library's shape and community practice. The
  reference's "Measured here" section was rewritten in this pass to say exactly that.
* Note for anyone porting an older tutorial: `emulator.createCode()` / the `Assembly` helper class
  do **not** exist in 0.9.10-SNAPSHOT (no `Assembly*.java` under the tree, no `createCode` symbol in
  any module). Recipes that assemble raw ARM machine code through that API need the current
  backend/JNI entry points instead.
* `unidbg-android`'s bundled demos (`TTEncrypt`, `SignUtil`, `QDReaderJni`, …) each expect their own
  `.so`/APK to be placed first; none were run, so the demo names in the reference are pointers, not
  verified commands.

---

## 6. Consolidated list of things that did **not** work (for the pass summary)

1. Attach by package name on this ROM (both `com.android.settings` and `io.github.vvb2060.magisk`
   failed while listed by `frida-ps -Uai`). Workaround: pid, from `frida-ps -U` / `pidof`.
2. Device-serial attach once the device's server came back on 27043 — `ServerNotRunningError:
   unable to connect to remote frida-server: closed`. Workaround: `adb forward` + `--remote`.
3. Attach by pid to `com.xunmeng.pinduoduo` — `frida.TimedOutError`; the process never answered the
   handshake.
4. `asc` as a command name (the console script is `droidasc`), and `mvnw` without `JAVA_HOME`.
5. unidbg out of the box on JDK 17 (`Module` ambiguity) and unidbg tests out of the box
   (`maven.test.skip=true`).
6. Application-class decompilation of a packed APK by either ASC or ddc (nothing to fix — the dex
   simply is not there; this is the case that justifies the whole emulation/RPC route).

## 7. Artifacts produced by this pass

`tools/_work/t3-rpc/` (not committed): `asc-manifest-verify.xml`, `asc-StubApp-verify.java`,
`asc-listclass-all.txt`, `asc-listclass-stub.log`, `asc-getmanifest.log`, `asc-findrefs.log`,
`asc-findrefs-jiagu.txt`, `asc-getclass.log`, `ddc-info-verify.txt`, `ddc-findrefs-jiagu.txt`,
`ddc-strings-jiagu.txt`, `rpc-*.log` (one per command in §4), `bin/ddc.exe`, `unidbg/` (patched work
copy).

Files changed in the repository by this pass: `references/emulation-and-rpc.md` (corrected failure
table, corrected unidbg build recipe, corrected "Measured here" labelling, and a stale section
reference repointed to `SKILL.md` §Stop conditions) and `scripts/frida_rpc_serve.py` (the four fixes
in §3).
