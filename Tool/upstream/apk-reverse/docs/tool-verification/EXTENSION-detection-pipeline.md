# Extension verification — detection pipeline, layered descent, ptrace-free dumping

Covers the pass that added the §Step 3 locating pipeline and the §Step 2B boundaries to
`references/detection-and-anti-analysis.md`, and the §What this route cannot do /
§Is this dex image real / §Layered descent sections to `references/advanced-unpacking.md`.
It also ships `scripts/svc_scan.py` and `scripts/anti_detect_probe.js`.

Strength labels, as defined in this directory's README:

- **observed** — reproduced here, with the exact command and its output.
- **inferred** — follows from observed facts, but the step itself was not executed.
- **unverified** — assumed, or reported by a tool and not independently confirmed.

**Target identity is deliberately absent.** The hardened sample appears as `<PKG>`; the
public MASTG challenge apps appear by their package names because they are public
published targets, not a user's app. No keys, signatures or user data are recorded.

## 0. Environment and what was decided before measuring

| Item | Value |
|---|---|
| Device | Android 11 (API 30), arm64-v8a, kernel **4.14.186**, Magisk alpha + root, toybox shell |
| Host | frida 16.7.19 / frida-tools 13.7.1; capstone; lief; pyelftools |
| Instrumentation server | **a `frida-server` was already running on the device** (`frida-server -l 0.0.0.0:27099`, pid 31859) with a leftover `adb forward tcp:27099` |
| Decision taken | **Reuse it rather than restart it.** A restart is a device-wide variable and the process had a live abstract socket (`unix:abstract=/frida-...)`; it was never started by this pass, so nothing about it is attributed here. Cost: the server's listening port and its path are part of the environment a detector can see — see §4, where a probe confirms frida artefacts *are* visible in the target's own maps |
| Root hiding | `magisk --denylist status` = *enforced*, list **empty** → no app had root hidden. Not changed in this pass |

`frida-ls-devices` cannot be used as a liveness check in this harness (it requires a
Windows console and dies with `NoConsoleScreenBufferError`); the Python binding is the
reliable route, and that is what every measurement below used:

```python
dev = frida.get_device_manager().add_remote_device('127.0.0.1:27099')
dev.query_system_parameters()
# {'arch': 'arm64', 'os': {'version': '11', 'id': 'android'}, 'api-level': 30, 'access': 'full'}
```

## 1. `scripts/svc_scan.py` — measured, with the count cross-checked

`--help` works; a real call was made on five inputs. T3 cross-check first, because the
whole script is a decode claim:

```
json sites        = 214
hand word-scan    = 214
set difference    = []
```

The hand word-scan is a 6-line script that matches the `svc` encoding
(`(w & 0xFFE0001F) == 0xD4000001`) with no dependency on capstone, so the two readings
are genuinely independent implementations. **observed.**

Device libraries, scanned from copies pulled with `su -c cp`:

| Input | Sites | by_group | Notable |
|---|---|---|---|
| `/apex/…/bin/linker64` (1,451,392 B) | 214 | termination=4, evasion=5, discovery=8, unresolved=6 | the 4 termination sites are `exit`/`exit_group` at `0xda284`/`0xda2a4` |
| `/apex/…/lib64/bionic/libc.so` (1,193,024 B) | 215 | termination=4, evasion=6, discovery=8, unresolved=6 | `kill @0xc5b94`, `tgkill @0xc5bb4`, `ptrace @0xc5bd4`, `mprotect @0xc5f54`, `exit_group @0xc7054`, `exit @0xc7074` |
| `assets/libjiagu_a64.so` from the sample (1,171,896 B) | 21 | **unresolved=21** | every site is inside `scvtf`/`udf`/NEON byte soup — data, not instructions |
| `assets/libjiagu.so` (32-bit, 861,436 B) | 11710 | unresolved=11116 | scanning both PT_LOAD segments mixes code and data; the site count is not usable without inspecting neighbours |

**The interpretation that matters, and it is the reason the script exists:** the four
termination sites in `libc.so` are libc's *own* exported implementations, so a hook on
`exit`/`kill` does see callers that go through libc. The shell library has **no**
termination site and 21 data artefacts — so on this target a libc-level hook is *not*
structurally excluded, and a missing exit event would be a finding about the hook.
**observed.**

Two defects were found by running it and both are fixed in the shipped script:

- `capstone` raises `CS_ERR_DETAIL` unless `detail = True` is set; the first run died on the
  first hit (`AttributeError`-equivalent at `insn.operands`).
- `pf_x` is **not** usable as a filter on this platform. The ROM's own `libc.so` and
  `linker64` carry `pf_x` set on their code segment but a first version of the probe read
  `p_flags` from the wrong struct offset (reading `p_offset`'s low word instead), which
  reported `pf_x=0` for everything. The shipped version reports per-segment `pf_x` and does
  not filter on it by default: `--code-only` is opt-in precisely because a device that
  clears the flag would otherwise return zero hits silently.

## 2. The hardened sample: what it does now, and why nothing was dumped from it

The previous pass recorded this sample as a clean self-exit on a 7-18 s cycle with no
tombstone. **That is no longer the shape.** Measured this pass, twice, 20 samples at 1 Hz
after `monkey` launch:

```
22:28:19.923 D/OppoExSurfaceFlinger: hecate traverse … Splash Screen com.gentle.ppcat#0
22:28:21.684 W/ActivityManager: Process ProcessRecord{… 14905:com.gentle.ppcat/u0a623} failed to attach
22:28:21.686 I/ActivityManager: Killing 14905:com.gentle.ppcat/u0a623 (adj -10000): start timeout
```

- **observed:** the platform kills the process on **`failed to attach` / `start timeout`**
  roughly **2 s** after start, i.e. the app never finishes starting.
- **observed:** an attempt to harvest memory inside that lifetime failed on both tries —
  `RESULT=NO_PID` and `RESULT=NO_PID` with `t_pid=9.99`, so a 10 s window is already longer
  than the process lives. Two strikes, no third variant: **the ptrace-free dump was not
  obtained from this sample and this file does not claim one.**
- **observed, and a new signal rather than a repeat:** a tombstone is now produced, and its
  fault is not in the packer's own code but in the runtime, reached from JIT output:

```
signal 11 (SIGSEGV), code 2 (SEGV_ACCERR), fault addr 0x75f16ff028
backtrace:
      #00 pc 0000000000574028  /apex/com.android.art/lib64/libart.so
                               (art::Runtime::SetJavaDebuggable(bool))
      #01 pc 0000000000022d58  /memfd:jit-cache (deleted)
```

  A self-terminating `SIGABRT` would be the expected shape for an anti-analysis kill; a
  `SEGV` in `Runtime::SetJavaDebuggable` reached **from JIT-compiled Java** is not, and the
  honest reading is limited: **the app now crashes during startup, in the runtime, on a
  path a Java method entered.** Whether that is the packer's environment check firing or a
  consequence of the kill arriving mid-startup is **unverified** — the sample's own
  start/stop behaviour changed between passes and no control run with root hiding
  configured was made, because changing root-hiding state is a device-wide variable this
  pass deliberately did not touch.

## 3. Clean-target baseline: state, liveness, and a harness artefact avoided

- **observed:** `owasp.mstg.uncrackable1` launched with `monkey` stayed alive at pid 15310
  for **more than a minute** of repeated checks — the stable baseline every dynamic
  experiment needs, and the reason the arms below were run on it and on L3 rather than on
  the hardened sample.
- **observed:** `owasp.mstg.uncrackable3` runs two processes (zygote64 + 32-bit), had its
  own integrity log line, and stayed up.
- **observed, and the most expensive-looking failure that turned out to be free:** the
  first attach to L1 hung and then failed —
  `attach/spawn failed: unexpectedly timed out while waiting for signal from process with PID 15310`
  — and a second attach said `process not found`. The process was still in `ps` and
  `dev.enumerate_processes()` still listed it, but:

```
$ adb shell 'cat /proc/15310/stat | cut -d" " -f3'
D
```

  **`D` (uninterruptible disk sleep)** is why. A userspace attach needs the process to run.
  The one-line control that settled it in a single command: attaching to a *different* pid
  from the same device succeeded (`attach 15974 OK`). **observed** — the failure was the
  environment, not a detector, and this is now Stage 0 of the reference's pipeline.

**Harness self-check applied before interpreting anything** (the discipline that a spawn
which is never resumed produces zero events and reads as a hang): the driver
(`tools/_work/detect/run_anti_detect_probe.py`, a work-file, not shipped) resumes
**explicitly** after the script is loaded, and records whether it did. Both arms below
report `resumed=True`, so "no events" cannot be an un-resumed spawn here.

## 4. The three arms, on one target — and the detection actually found

All arms: `owasp.mstg.uncrackable3`, `--spawn`, script loaded before resume.

| Arm | Script | Result |
|---|---|---|
| **A. baseline** | none (launch, no instrumentation) | process alive and stable across a minute of sampling (§3) |
| **B. control** | attached/spawned, resumed, **no script loaded** | **`alive_at_end=True`**, survived the full window |
| **C. experimental** | `scripts/anti_detect_probe.js` (observer-only) | **`alive_at_end=False`**, process gone before the first heartbeat |

Control vs. experimental differs in exactly one variable — the probe script — so the death
is attributable to instrumentation. Then the observer's own stream named the check:

```
t=0      [armed]        script armed
t=207ms  [thread_create] pthread_create entry=0x76dc031d78
t=238ms  [strcmp_probe]  strcmp("Ldalvik/system/ClassExt;")
t=245ms  [env_probe]     open("/system/fonts/Roboto-Regular.ttf")
t=254ms  [loader]        android_dlopen_ext("…/oat/arm64/base.odex")
t=303ms  [strstr_probe]  strstr("frida")        <-- the check
t~350ms  process gone, heartbeats=0, no tombstone, no crash/ANR record
```

- **observed:** the target **searches for the string `frida`** (`strstr("frida")`) at ~300 ms
  of its life. This is the "detection really did happen" datum the task asked for: not an
  inference from a death, a recorded call with a timestamp.
- **observed:** an earlier arm of the same shape also captured the kill itself —
  `[termination] raise(...) <- …` at **t=352 ms**, i.e. a signal-based self-abort roughly
  50 ms after the `strstr`. No tombstone was written and no `has died: crash` record
  appeared, which is the clean-self-exit signature.
- **observed, and the reason the arm is reported as unstable:** three attempts at the same
  arm produced *one* full sequence, then two runs where the script received **zero**
  messages before the process died (`live=0, messages=0, heartbeats=None`). On a target that
  kills itself in ~300 ms the observable window is sub-second and **not reproducible arm to
  arm**. One successful attribution is therefore not a pipeline, and the reference says so.

What the probe also recorded about the *environment*, before any check ran:

```
tracerpid=0   frida_named_maps=4   (four mappings whose names match /frida/i)
status: Name: tg.uncrackable3 ; State: S (sleeping) ; Seccomp: 2
/proc/net/tcp  -> Permission denied     /proc/self/task -> Is a directory
```

**observed:** the target's own `/proc/self/maps` contains **four frida-named mappings** while
`TracerPid` reads **0**. So a `TracerPid`-only check would pass while a maps-or-thread-name
check would not — which is exactly the "what can this process actually see" question the
Stage 1 self-report exists to answer, and it is why the probe reports both.

**One defect in the probe, fixed once and then left:** caller attribution printed
`bt-unavailable: cannot read property 'context' of undefined` on every line. Cause: the
`this` binding inside the anonymous `Interceptor` callback was not what the helper assumed;
the fix is to pass `this.context` explicitly. The measured consequence is worth stating
because it is a *plumbing* failure that reads like a hooking failure: the events and their
timings were correct throughout, only the "which module called this" half was missing, and
one of the three arms still showed no events at all. `observed`.

## 5. ptrace-free dumping: the route, its boundary, and a cross-check that passed

### 5.1 What the route yields when the target has a whole dex in memory

Not re-measured here: the earlier pass's 17 ART dex mappings exported from `/proc/<pid>/mem`
without any instrumenter present (`docs/tool-verification/EXTENSION-rootdump.md`). This pass
adds the **negative boundary** the earlier pass could not state, and it needed a clean
target to state it:

```
# both public MASTG targets, ~2,400 map lines each, one adb round-trip
owasp.mstg.uncrackable1: maps_lines=2427  named_dex=0  apk_views=2
owasp.mstg.uncrackable3: maps_lines=2377  named_dex=0  apk_views=2
```

- **observed:** `named_dex=0`. Neither target produces an
  `[anon:dalvik-classes.dex extracted in memory from …]` mapping, so the filename-driven
  export has **nothing to export** — and this says nothing about those targets being
  protected.
- **observed, the explanation:** their `classes.dex` is **deflate-compressed inside the
  on-device APK** (`compress_type=8` read from the APK pulled off the device), so the
  `dexopt` "map the dex directly" mechanism cannot apply to it.
- **observed:** the `r--s` views that *do* exist point at APK **file offsets**, and the
  bytes there are the APK's own bytes — at `0x11000` on L1 that content is the ZIP
  **central directory** (`PK\x01\x02`), not a dex.
- **observed, and a trap that produced a false "DIFFERENT":** on L3 the view
  `76dc28e000-76dc299000` has file offset `0x15a000` = 1,417,216 B, while the mapping is
  44 KiB (45,056 B) long — so the range reaches 1,462,272, i.e. **past the end of the
  1,460,555-byte APK**. The file-side read came back short (1,015 B) and the two sha256s
  described different byte counts. Compute the length before suspecting the target.

### 5.2 The reproducibility cross-check, which passed

Two independent read paths over the same address range must agree byte-for-byte before a
capture is evidence:

| Range | Read via `/proc/<pid>/mem` | Read from the file | Verdict |
|---|---|---|---|
| L3 `765a89c000-765a8de000` (264 KiB, file offset `0x6000`) | `sha256=2eafd7cca73630c05d0b0c1b4a7709f21ee24540b5f2ba388ad3467af645aa75` | same | **IDENTICAL** |
| L1 `76dfb14000-76dfb15000` (4 KiB, file offset `0x11000`) | `sha256=74846b8cb02a764efef158194745466cf0c8ad2c1c3fecbb2bcf7cf9c58b6465` | same | **IDENTICAL** |

**observed.** The comparison is only meaningful because both sides covered the same byte
count; the one range that differed was the one whose length exceeded its backing file.

### 5.3 The cross-check that was **not** run, and why it is not silently absent

The task's cross-validation requirement is satisfied for `svc_scan.py` by two independent
decoders agreeing on an identical 214-site set (§1). For a **dump**, the equivalent check
needs two producers that emit the *same* artifact. What this pass has is `/proc/<pid>/mem`
(successful, §5.2) and, on the hardened sample, `frida-dexdump` — which was **refused** by
that sample in the previous pass (`script has been destroyed`,
`docs/tool-verification/EXTENSION-device-run.md`). The sample's lifetime then shrank to ~2 s
(§2), so the second producer could not be obtained on any target here:

| Second-producer option | Status |
|---|---|
| `frida-dexdump` on the hardened sample | **unverified** — refused in the earlier pass; not retried here on a 2 s process |
| `frida-dexdump` on L1/L3 | **unverified, and expected to be empty** — `named_dex=0`, so there is no whole image for any dumper to find |
| `process_vm_readv(2)` as a second backend | **not run** — the on-device helper would have needed a second binary on the device, and the byte-identity question it answers was already answered against the file path |

**Statement of the gap, so the next reader does not have to infer it:** the byte-identity
check between two *dumpers* is **unverified** in this repository. What is `observed` is
byte-identity between two *read paths* on the same bytes, and a 214-site decode agreement
between two independent decoders. Those are weaker claims than "two dumpers cross-checked",
and they are the ones this file makes.

**A related statement that is deliberately negative:** two dumpers agreeing is not evidence
of *recovery*. Against an extraction shell, two agreeing dumps are two copies of the same
skeleton. The judge for that is the platform decoder, per
`advanced-unpacking.md` §Establish "the bodies do not decode" with a decoder you did not write.

## 6. What was not established

- **Not** a recovered payload from the hardened sample. Its process lives ~2 s and never
  reaches a state where its payload is loaded; the attempt hit the two-strike limit and was
  re-routed to the stable targets.
- **Not** a fix for the sample's startup failure. Root hiding was left alone — configuring
  `magisk --denylist` is a device-wide change and this pass was the only lock holder, which
  is not the same as being free to change every shared variable.
- **Not** a reproducible end-to-end anti-instrumentation pipeline on a fast detector. The
  full sequence was captured once out of three arms and the reference labels it that way.
- **Not** a general claim about `strstr("frida")` being the only check, or about MASTG
  challenges, or about Android 11. One device, one ROM, one session, with other experiments
  sharing the device.
- **Not** a kernel-layer result. Kernel 4.14.186 < 5.10 closes the eBPF route; the layered
  descent in the reference stops at the `svc` boundary and says so.

## 7. Reproduction one-liners

```
python skills/apk-reverse/scripts/svc_scan.py tools/_work/detect/libc.so --context 2
python skills/apk-reverse/scripts/svc_scan.py tools/_work/detect/linker64.bin --json

adb shell 'su -c "sh /data/local/tmp/apkmaps.sh owasp.mstg.uncrackable3"'      # named_dex / apk_views shape
adb shell 'su -c "sh /data/local/tmp/apkviews_verify.sh owasp.mstg.uncrackable3"'
adb shell 'su -c "sh /data/local/tmp/detlaunch.sh <pkg> /data/local/tmp/dd1"'

python tools/_work/detect/run_anti_detect_probe.py --pid <pid> --watch-ms 8000 --out arm.json
python tools/_work/detect/run_anti_detect_probe.py --pkg owasp.mstg.uncrackable3 --spawn \
    --script skills/apk-reverse/scripts/anti_detect_probe.js --out arm_probe.json
```

The on-device helper scripts (`apkmaps.sh`, `apkviews_verify.sh`, `detlaunch.sh`) and the
driver live under `tools/_work/detect/` and are **work files, not shipped deliverables** —
they exist so the commands above are reproducible, and their content is summarised in the
sections that cite them. The two shipped scripts are `scripts/svc_scan.py` and
`scripts/anti_detect_probe.js`.
