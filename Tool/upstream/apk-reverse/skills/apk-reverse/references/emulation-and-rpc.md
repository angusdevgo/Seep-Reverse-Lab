# Emulation and RPC — running the target's code on your terms

There is a class of target where neither reading nor patching is the bottleneck: the code you need
is *inside* a hardened `.so`, statically unreadable (OLLVM, string encryption, VMP) or only
decrypted in memory, and what you actually want is its **output** — the signature it computes, the
blob it decrypts, the token it mints — not its source. Two routes give you that without winning the
unpacking war first:

- **Unidbg** — emulate the `.so` on your PC, feed it inputs, read outputs. Offline, batch, no
  device, no detector. You pay in *environment*: everything the library touches must be faked.
- **Frida RPC** — let the real process run its own hardened code, and call it from Python through a
  resident session. High fidelity (it is the real environment), no faking required. You pay in
  *stability*: the process must tolerate injection, and the session must survive.

This file is about choosing between them and driving both. The unpacking itself is
`references/packers.md` and `references/advanced-unpacking.md`; the hooking mechanics live in
`references/dynamic-frida.md`. What is new here is treating the target's own crypto as a **callable
function** instead of a thing to understand.


**Load this when:** you need the *output* of a routine rather than a change to the app -- a signature, a token, a cipher. It gives emulation with its environment-filling cost, against service-ifying the live function over Frida RPC.

## When emulation or RPC is the right move

Reach for this file when any of these holds:

- The algorithm you need lives in a hardened `.so` and reverse-engineering it (weeks against OLLVM
  or VMP) costs more than *calling* it (hours of environment work).
- You need **many** calls — fuzzing an input format, brute-forcing a key schedule, generating
  signed request batches — where hand-driving a device per call is hopeless.
- The function's output depends on environment state (files, system properties, other libraries)
  that a static read cannot evaluate.
- The gate you care about is a *computed value* (sign header, encrypted body) rather than a branch
  — `references/server-api.md` told you the server checks it, and the client computes it in native
  code (`references/signature-derived-keys.md`).

Do **not** reach for it when a two-byte dex patch or an LSPosed module solves the problem —
`references/dex-patching.md` and `references/lsposed-and-modules.md` are cheaper and more durable.
Emulation and RPC are for when the code that matters must keep *running*.

## The decision table

| | Unidbg (offline emulation) | Frida RPC (live process) |
|---|---|---|
| Environment fidelity | fake — you build it | real — the device provides it |
| Works without a device | yes | no (device or emulator required) |
| Works against anti-injection | **yes** — the code never knows | **no** — injection is the entry ticket |
| Batch throughput | thousands of calls/min | tens of calls/sec, process-bound |
| Setup cost | Java + maven + per-library env work | frida already installed, minutes |
| Maintenance cost | every missing JNI/syscall is a new stub | reconnect logic, process lifecycle |
| Reproducibility | deterministic (you control time/random) | real time, real randomness |
| Best for | signing algorithms, crypto, parsers | anything entangled with live app state |
| **Priority when either could work** | second — the environment bill below is real and routinely underestimated | **first** — the device already owns the environment |

The two-strike rule applies across the table: if a library refuses to run under unidbg after two
focused rounds of `DalvikVM` patching, stop emulating and move to RPC (or the reverse) instead of a
third round — a library that checks its own loading path or decrypts itself against device state
may simply not be worth emulating, and that is a finding, not a failure (`SKILL.md`
§Stop conditions).

### The environment bill — budget days, not hours

"Filling the environment" reads like a checklist and behaves like a project. The mistake this
section prevents is starting an emulation because the table says *works against anti-injection*, and
then discovering that this library's environment includes everything emulation cannot fake: an
Android `Context` backed by a real package manager, Binder round-trips into another process, a
`KeyStore` attestation that only succeeds on real hardware, or a self-check against device state
captured at install time. For a commercial native algorithm of that shape, "stub it until it runs"
is measured in **days, not hours** — each missing piece is discovered one fault at a time, and the
rounds do not get shorter.

Weigh it before starting:

| Question | If yes |
|---|---|
| Does it call through `Context` (package name, files dir, signature, `PackageManager`)? | a stub is often enough — cheap, keep going |
| Does it talk to another process (Binder service, bound SDK, remote provider)? | the stub surface grows fast; **prefer RPC** |
| Does it verify hardware (KeyStore, TEE, an attestation chain)? | emulation is likely a dead end — the value it wants cannot be produced here |
| Does it check its own loading environment (paths, maps, root, debugger, installer)? | readable and patchable *inside* the emulator, but budget one round per check |
| Must it be called thousands of times a minute? | the RPC throughput ceiling is real — this is the case that justifies the bill |

Default to **RPC first, emulation second**: the device already provides the environment, and
per-call cost only starts to matter once you need volume. The two claims in this subsection
(the day-scale cost of a Context/Binder/KeyStore-shaped library, and the RPC throughput ceiling)
are **inferred** from the mechanism and from community practice — this repository has not emulated a
commercial sample end to end, as `references/evidence-summary.md` §The capability matrix states.

## Part A — Unidbg

### What it is

Unidbg ([zhkl0228/unidbg](https://github.com/zhkl0228/unidbg), Java, Apache-2.0) emulates an
Android process on your PC:

- **CPU** — a `backend` layer over Unicorn (default) or Dynarmic/Hypervisor, executing the real
  arm/arm64 code of your `.so`.
- **Memory & linker** — it maps the ELF, resolves `DT_NEEDED` dependencies from a bundled Android
  system-library set (`AndroidResolver(apiLevel)`), and runs relocations.
- **JNI environment** — a Dalvik VM emulation (`emulator.createDalvikVM(apk)`) that answers the
  library's `FindClass`/`GetMethodInfo`/`CallObjectMethod` calls against either real classes from
  the APK's dex or **stubs you write in Java**.
- **Syscalls** — file IO, `mmap`, `pthread` primitives, system properties, `/proc` reads are
  emulated or redirected.

You write a Java main that wires those together, calls `JNI_OnLoad` (many hardened libraries do
their initialization there), then calls the target function with your inputs. The library's real
arm code executes; its output comes back as a Java value.

**This repository does not bundle unidbg** — it is a Java/maven project, not a script. To use it:

```bash
git clone --depth 1 https://github.com/zhkl0228/unidbg.git
cd unidbg
# Windows + JDK 17 (measured): the shipped pom pins -source/-target 8, and on JDK 9+
# the compiler resolves against the current API where `Module` is ambiguous
# (java.lang.Module vs com.github.unidbg.Module) — unidbg-api fails to compile.
# <release>8</release> selects the JDK 8 API and fixes it; the bundled Maven wrapper
# is 3.5.4, which rejects maven-compiler-plugin 3.13, so 3.8.1 is the version that
# both supports <release> and runs on that wrapper.
set JAVA_HOME=C:\Program Files\Java\jdk-17.0.4.1
mvnw.cmd -B -pl unidbg-android -am -DskipTests compile          # BUILD SUCCESS, ~48 s
# tests are skipped by <maven.test.skip>true</maven.test.skip> in the pom — override it:
mvnw.cmd -B -pl unidbg-android -am -Dmaven.test.skip=false \
    -Dtest=MemoryTrackerTest -DfailIfNoTests=false test         # Tests run: 3, Failures: 0
# first run downloads maven itself plus dependencies — minutes
```

Then pick the demo closest to your target under `unidbg-android/src/test/java` and adapt it; the
bundled demos (`TTEncrypt`, `SignUtil`, `QDReaderJni`, …) each need the `.so`/APK they reference
placed where the test expects it.

A library project that already uses maven/gradle can instead depend on the published artifacts
(group `com.github.zhkl0228`, artifacts `unidbg-android` + `unidbg-api`, on Maven Central) — the
clone-above route avoids version drift and gives you the test-suite demos to copy from.

### The minimal call template

Adapt this to your target — it is the shape every unidbg driver has (measured against the
0.9.x API; class names move rarely but do move, check a current test under
`unidbg-android/src/test/java` when something fails to resolve):

```java
import com.github.unidbg.AndroidEmulator;
import com.github.unidbg.LibraryLoader;
import com.github.unidbg.linux.android.AndroidEmulatorBuilder;
import com.github.unidbg.linux.android.AndroidResolver;
import com.github.unidbg.linux.android.dvm.*;
import com.github.unidbg.memory.Memory;
import java.io.File;

public class CallTarget {
    public static void main(String[] args) {
        // 64-bit or 32-bit must match the .so, not the PC.
        AndroidEmulator emulator = AndroidEmulatorBuilder.for64Bit()
                .setProcessName("com.example.app")   // some libraries check this
                .build();
        Memory memory = emulator.getMemory();
        memory.setLibraryResolver(new AndroidResolver(23)); // bundled system .so set

        // The APK gives the VM real classes for JNI calls; null is allowed if
        // you intend to stub everything yourself.
        VM vm = emulator.createDalvikVM(new File("target.apk"));
        vm.setVerbose(true);
        vm.setJni(new AbstractJni() {               // your JNI callbacks — see below
            // override methods as the target demands them
        });

        DalvikModule dm = vm.loadLibrary(new File("libtarget.so"), false);
        dm.callJNI_OnLoad(emulator);                // init: decrypts, registers natives

        // Calling a *statically exported* symbol:
        //   DvmObject<?> ret = dm.callFunction(...)
        // Calling a *JNI-registered* method by its Java name (most common for hardened SDKs):
        DvmClass<?> c = vm.resolveClass("com/example/NativeApi");
        DvmObject<?> result = c.callStaticJniMethodObject(emulator,
                "sign(Ljava/lang/String;)Ljava/lang/String;", "input");

        System.out.println(result.getValue());
    }
}
```

### Filling the environment — "supply what is missing"

A hardened library does not just compute; it *checks*. Every unidbg session converges on the same
loop: run, read the first unsupported callback or mapping fault, implement exactly that, repeat.
In order of frequency:

| The library wants | You supply |
|---|---|
| `JNI_OnLoad` → `FindClass`/`GetMethodID` on app classes | `AbstractJni` overrides (`callStaticObjectMethodV`, `getStaticObjectField`, …) returning canned values; or real classes from the APK via `createDalvikVM(apk)` |
| `Context` methods (`getPackageName`, `getFilesDir`, `getPackageManager` → signature!) | stubs — `vm.resolveClass("android/content/Context")` + your `AbstractJni` answers; a signature check wants the *original* APK's signature bytes, which `createDalvikVM(apk)` serves from that very file |
| file reads (`/proc/self/maps`, `/data/data/...`, config files) | `emulator.getSyscallHandler().addIOResolver(...)` redirecting to host files, or `virtualFileSystem` mounts; a `/proc/self/maps` check that looks for frida/xposed is satisfied by a clean canned maps file |
| other `.so` (cocos, tls, crypto) | `vm.loadLibrary` them first, in dependency order, or drop them beside the target so the resolver finds them |
| time / randomness | `emulator.getSyscallHandler` clock override; unidbg's deterministic RNG unless the target seeds from `/dev/urandom` (redirect it) |

Two structural rules that save hours:

- **Load order is init order.** `JNI_OnLoad` of the shell often registers natives and decrypts;
  calling a function before the init that populates it yields a null deref that looks like a bug
  in unidbg. Always `callJNI_OnLoad` first, and if the library has an explicit init/exported
  setup entry, call that next.
- **32 vs 64 must match the `.so`,** not your PC and not the device's preference
  (`references/native-and-so.md` §Cross-architecture applies here too: `for32Bit()`/`for64Bit()`
  mirror the ABI you extracted from `lib/`).

### Failure modes you will meet

| Symptom | Meaning | Move |
|---|---|---|
| `unsupported syscall` / `signal 11 (SIGSEGV)` at a stable address | the library touched something unidbg does not fake yet | read the unidbg log line above the fault — it names the syscall/JNI call; stub it |
| `JNI_OnLoad` returns non-zero or throws | self-check failed inside init | enable `vm.setVerbose(true)`, read which check it ran (often signature, path, or a system property), satisfy it via stub |
| works, but output differs from device | environment input differs (time, random, files, another lib's state) | diff the inputs: redirect and pin them; on-device RPC (Part B) is the ground truth to compare against |
| crashes deep in the library, no unsupported call logged | the code path is genuinely wrong (wrong calling convention, wrong args) — or the library decrypted itself against device state it cannot have here | recheck the prototype (arg types/order) against the dex `native` declaration; then consider RPC instead |
| library refuses to load: dependency not found | a `DT_NEEDED` `.so` you did not provide | `readelf -d` the target, load missing libs first |

Know when to stop: a library that validates its own decrypt key against server data, or that
refuses any environment it did not boot in, is **not worth emulating** — that is exactly the shape
where the decision table sends you to Part B. (Which anti-emulation checks exist and how common
each is: inferred from community experience, not measured here.)

### Measured here

See `references/evidence-summary.md` §The capability matrix for the exact commands and outputs behind
every label in this section. Measured in that pass: the repository builds on Windows/JDK 17 once
the compiler plugin is pointed at the JDK 8 API, the emulator boots, and one bundled test suite
passes on the Dynarmic backend. **No target `.so` was emulated yet** — every per-library claim above
(which JNI callbacks a hardened library asks for, which syscalls it hits, how many rounds of stubbing
it costs) is **inferred** from the library's shape and from community practice, not from a run
against this sample.

## Part B — Frida RPC

### The mechanism

A Frida script can export functions to its host: assign to `rpc.exports`, and every property
becomes callable from Python (`script.exports_sync.name(...)` after frida 16) with JSON-serializable
arguments and return values, synchronously, from outside the process. That is the whole trick:

```javascript
rpc.exports = {
  add: function (a, b) { return a + b; },
};
```

```python
script = session.create_script(code); script.load()
print(script.exports_sync.add(40, 2))      # -> 42
```

Everything else is packaging: keeping the session alive, finding the function address, converting
types across the NativeFunction boundary. The pattern for the case that matters — a hardened
library's signing function, exported or `RegisterNatives`-bound:

```javascript
// 1) exported symbol:
const addr = Module.findExportByName('libtarget.so', 'Java_..._sign');
// 2) dynamically registered (no export — the usual shape for hardened SDKs):
//    hook RegisterNatives once at startup, note the fnPtr for the name you care about
const sign = new NativeFunction(addr, 'pointer', ['pointer', 'pointer']);
rpc.exports = { sign: function (s) { return sign(env, jstring(s)); } };
```

Java-side functions are equally callable (`Java.perform` wraps the call), which is how the
harmless connectivity probe — `getPackageName` over RPC — works in the template below.

### The kit's tooling

`scripts/frida_rpc_serve.py` + `scripts/rpc_template.js` implement the full loop:

- three front ends: one-shot `--mode call`, interactive `--mode repl`, and a resident
  `--mode http` endpoint (`POST /call {"export": "...", "args": [...]}`, `GET /exports`,
  `POST /reload`);
- spawn or attach (by name or by pid — attach-by-name fails on incomplete process enumeration,
  `references/dynamic-frida.md` §Attach by PID);
- automatic reconnect: a detached session (app restart, killed server, ROM reaping the server)
  re-attaches, reloads the script and retries the call, with per-request retry cycles and
  exponential backoff; a killed-and-restarted device server is recovered by dropping the cached
  remote device before reconnecting;
- the template exports `add` (transport sanity), `getpackagename` (Java probe),
  `callnative(module, export, retType, argTypes, args)` and `callnativeaddr(module, offset, ...)`
  for wrapping any native symbol, with a frida-16/17-compatible export resolver.

Typical session (device server already running and forwarded, `references/dynamic-frida.md`
§Setup):

```bash
adb -s <serial> forward tcp:27043 tcp:27043
python scripts/frida_rpc_serve.py --remote 127.0.0.1:27043 --package com.example.app \
    --script scripts/rpc_template.js --mode repl
rpc> list
rpc> getpackagename
rpc> callnative ["libtarget.so","Java_com_example_Native_sign","pointer",["pointer","pointer"],[...]]
```

Then feed the recovered function into request generation the way `references/server-api.md`
describes — the RPC service turns "the server checks a signed header" into "I can compute that
header on demand", which is the whole reason this route exists.

### What the live route costs — measured failure modes

Every row below was hit against a real device during the verification pass behind this file
(exact outputs in `references/evidence-summary.md` §The capability matrix):

| Failure | What it looks like | Handling |
|---|---|---|
| **Hardened target kills injection** | attach: `process either refused to load frida-agent, or terminated during injection`, logcat `CRASH ... IterateRegisters found fp`; spawn: script loads, then every call dies with `script has been destroyed` | the shell's anti-instrumentation won; do not retry the same attach — switch route (unidbg for the crypto, or `references/lsposed-and-modules.md` / static patching), or fight the detector deliberately (`references/detection-and-anti-analysis.md`) |
| **ROM reaps the server** | `connection closed` mid-session, sometimes repeatedly | budget restarts, not re-analysis: the bridge reconnects once the server is back; check `pidof <server>` before every experiment block (`references/dynamic-frida.md`) |
| **Attach by name fails for processes the device can see** | `unable to find process with name 'com.example.app'` while `frida-ps -Uai` and `ps -A` both list it alive; reproduced for a system app and for a Magisk-manager process, for every package name tried | resolve the pid yourself and attach with `--pid`: measured on the same ROM, `device.attach(pid)` loaded the script and returned RPC results for the very processes whose *name* lookup failed (`--pid 19938` → `com.android.settings`, `--pid 21493` → `com.android.email`). Take the pid from `frida-ps -U`, `ps -A`, or `adb shell pidof <pkg>` |
| **The server comes back on a non-default port** | `frida.ServerNotRunningError: unable to connect to remote frida-server: closed` on attach even though `frida-ps -U` still works | the ROM or a watchdog reaped the visible server and a disguised copy returned elsewhere (measured: only `*.svc16` left alive, listening on 27043, nothing on 27042). Check the listening port, `adb forward tcp:27043 tcp:27043`, then `--remote 127.0.0.1:27043` — do not assume the default port |
| **Attach by pid times out on a busy process** | `frida.TimedOutError: unexpectedly timed out while waiting for signal from process with PID X` during attach (raised by an ordinary third-party app); it is not a `TransportError` subclass and escaped every handler | nothing is wrong with the tooling — the process did not answer the agent handshake; use another process for the connectivity probe, or retry once the app settles (the bridge now treats `TimedOutError` as retryable and fails with one line instead of a traceback) |
| **Short-lived processes** | the settings main activity process exits seconds after `am start` | pick a persistent process for connectivity tests; the business target only when it actually stays up |

The strategic point those rows make together: **on a hardened target, RPC is not guaranteed to be
available at all** — the injection ticket can be revoked by the target itself. That is the single
strongest argument for keeping the unidbg route warm, despite its environment cost: it is the one
route that works when the process refuses to be instrumented.

### Combining the routes

The routes compose rather than compete:

1. **RPC as oracle, unidbg as student.** When an emulated function's output must be trusted, diff
   it against the live process's output for identical inputs; disagreement localizes the missing
   environment piece far faster than reading the library (`Part A` §failure modes, "output
   differs").
2. **Dump via RPC, emulate after.** A live call that returns the decrypted key/table the library
   uses (`references/runtime-data.md`) can be replayed into the emulated run as a fixed stub.
3. **Batch offload.** Use the device session to discover the calling convention and to capture
   sample inputs/outputs (few calls), then run the bulk of the work offline under unidbg.

## What to record

- which route was chosen and why (one line, against the decision table)
- for unidbg: the API level resolver, the list of JNI stubs you had to write, what the library
  checked before it would compute (that list *is* the target's defense inventory)
- for RPC: server version vs host version, attach vs spawn, reconnect behaviour observed, and —
  decisive for a hardened target — whether injection survived at all
- inputs/outputs for at least one call verified against an independent source (device-side log,
  server response, or a known-answer test)
