# Extension pass — on-device run against a hardened Flutter sample

This file records the **device-side** half of the extension pass: what was actually executed against
a live, hardened sample, what the sample did in response, and which conclusions the evidence supports.

It follows the same three labels the rest of this directory uses:

- **observed** — reproduced here, with the exact command and its output.
- **inferred** — follows from observed facts, but the step itself was not executed.
- **unverified** — assumed, or reported by a tool and not independently confirmed.

**Target identity is deliberately absent.** The sample is referred to as *the sample*, and its package
identifier appears as `<PKG>`. The findings are about the tools and the methods, and stay valid
whichever hardened APK produced them.

## Environment (observed)

| Item | Value |
|---|---|
| Device | one physical arm64 device, Android 11 (API 30), kernel 4.14.186, Magisk root |
| Host | Windows 11, Python 3.14.0, frida 16.7.19, frida-tools 13.7.1, frida-dexdump 2.0.1, java 17, adb 1.0.41 |
| Device server | `frida-server` 16.7.19 (version-matched to the host by `frida-server --version`) |
| Sample | 360-jiagu hardened, `application android:name` = a third-party stub class; Flutter AOT payload |
| Host capability report | `python scripts/doctor.py` → static/repack/smali/native-patch/device/root/frida all OK; `28 / 28` scripts runnable |
| Pre-flight warnings | clock skew 3.32 s; leftover `adb forward` entries (8787, 8651, 65534, 27043); a device-side `frida-server` already running |

Two environment facts from `doctor.py` are worth carrying forward, because each of them silently
invalidates a measurement: the clock skew, and a **frida process already up on the device** — the
second one means the target may already be reacting to instrumentation before your first command.

## The measurement that mattered: the sample fights instrumentation

### (1) Control — the sample starts normally with no instrumentation (observed)

```
$ adb shell 'su -c "am force-stop <PKG>; sleep 1; am start -n <PKG>/.MainActivity"'
$ sleep 12 && adb shell 'su -c "ps -A | grep -i <PKG>"'
u0_a623  22691  17278  14123672  642488  SyS_epoll_wait  0 S <PKG>
```

Resident, 642 MB, healthy. **This is the control build the rest of the section is measured against.**

### (2) The pid drifts — but **not** because of frida (observed, corrected)

During the session the sample's pid changed repeatedly:

```
22691  →  23452  →  24267  →  27274  →  31284  →  32259  →  1368  →  8161
```

The natural reading is "the sample fights instrumentation", and the first write-up of this file said
exactly that. **The follow-up measurement refuted it.** With `frida-server` stopped and no attach of
any kind, the sample was restarted under observation for 90 seconds:

```
20:28:22 pid=[9961]  load=36.43 | Mem: 11484 total  11077 used   406 free
20:28:33 pid=[9961]  load=36.26 | Mem: 11484 total  10767 used   716 free
20:28:45 pid=[9961]  load=35.61 | Mem: 11484 total  10739 used   745 free
20:28:56 pid=[9961]  load=34.64 | Mem: 11484 total  10767 used   716 free
20:29:08 pid=[11246] load=34.91 | Mem: 11484 total  11151 used   333 free
20:29:19 pid=[11246] load=35.69 | Mem: 11484 total  11142 used   342 free
20:29:31 pid=[12238] load=35.14 | Mem: 11484 total  11131 used   353 free
20:29:42 pid=[13212] load=37.03 | Mem: 11484 total  11059 used   424 free
```

The pid changes with **no frida present**, roughly every 10-20 seconds, while the device sits at
300-750 MB of free memory out of 11.5 GB. The first correction to this file attributed that to memory
pressure. **That attribution was also wrong, and the device-side dumping run refuted it** with a
better instrument than sampling: `logcat`.

```
$ adb logcat | grep <PKG>
Process <PKG> (pid N) has died: fg TOP
Start proc <pid> for top-activity <PKG>
```

The process **dies as the foreground top activity, with no crash, no tombstone and no ANR record**,
and the platform immediately relaunches it — a clean self-exit in a loop, on a 7-18 second cycle. A
reclaiming device does not do that to a foreground process, and a memory-pressure kill leaves an
`lmkd` line and a low-memory record. What produces exactly this shape is the sample **checking its own
environment and quitting on purpose**.

And the environment it finds is decisive: on this device `magisk --denylist status` reports **enforced
with an empty list**, Zygisk-Assistant is installed but nothing is scoped, and
`/data/adb/shamiko` does not exist — so **no application on this device is hidden from root**
(`EXTENSION-lsposed.md`, observed). A hardened sample that refuses to run on a rooted device will do
exactly this, forever, and no amount of dump-retrying changes it.

**Reading, corrected twice:** the pid drift is an artefact of the **root environment**, not of
instrumentation and not of memory pressure. The practical consequence is the useful part — *before any
dynamic analysis of a hardened sample, configure root hiding and re-run the baseline*, because with
nothing hidden every dynamic result on this device is measured against a process that is trying to die.
The observer's first control run showed a "stable" sample for 12 seconds only because it happened to
sample inside one 17-second lifetime.

This is the skill's own rule applied twice to its own record: a conclusion was reopened each time a
measurement disagreed with it (`SKILL.md` §Stop conditions, last bullet). Two wrong attributions were
cheaper to delete than for a reader to inherit — and the second one only fell because a different
method (`logcat`, not sampling) was pointed at the same question.

The platform's own view of a failed launch was also captured, and is worth keeping as a *shape*:

```
W ActivityManager: Process ProcessRecord{…:<PKG>/u0a623} failed to attach
I ActivityManager: Killing <pid>:<PKG>/u0a623 (adj -10000): start timeout
```

A `start timeout` kill reads the same whether the cause is a slow shell init, a reclaiming device, or a
deliberate delay. It does not discriminate, and it is not evidence either way.

### (3) `frida-dexdump` cannot complete a memory dump — reproduced twice (observed)

Both spawn and attach were tried, with the parameter mistakes fixed between attempts:

```
$ frida-dexdump -U -f <PKG> -d -o <out>            # spawn
Failed to spawn: need Gadget to attach on jailed Android; its default location is: …gadget-android-arm64.so

$ frida-dexdump -U -f <PKG> -d 12 -o <out>         # 12 was parsed as an argv entry, not a delay
Failed to spawn: the 'argv' option is not supported when spawning Android apps

$ frida-dexdump -U -f <PKG> -d -o <out>            # corrected
Failed to spawn: unexpectedly timed out while waiting for app to launch

$ frida-dexdump -U -p <pid> -d -o <out>            # attach, twice, second run with the device idle
frida.InvalidOperationError: script has been destroyed: {'addr': '0x721e24c02c', 'size': 409556}
INFO:frida-dexdump:[*] All done... Process terminated
```

Attach was run twice. The **second** run was the clean one: no Stalker traffic anywhere on the device
(see the crash note below), the package enabled and verified running, the pid read immediately before
the attach, and a single variable changed relative to the control. It produced the same
`script has been destroyed` failure, and the sample's pid changed again in the aftermath.

**What the failed runs left behind, checked with the kit's own validator** (`observed`):

```
$ python skills/apk-reverse/scripts/dex_dump_validate.py <dump_dir>
== dex dump validation: 2 file(s), 2 parse, 0 rejected ==
name            size       sha256[:12]   ver  cksum  sig  class        noco  code  stub%
classes.dex        500    9461987e5464  035  BAD    BAD  1986754560   0     0     0.0%
                            walk stopped early: index out of range
classes02.dex   10285489   116d8b84b486  035  BAD    BAD  1986754560   0     0     0.0%
                            walk stopped early: index out of range
```

Both artifacts pass the magic check and then fail everything else: checksum and signature both BAD,
no classes recovered, the walk stopping on an out-of-range index. They are **memory fragments cut
short by the process dying mid-read**, not dex images — and this is exactly the case
`dex_dump_validate.py` exists for. A size-based heuristic would have kept the 10.2 MB file and
discarded the 500-byte one; both are worthless, and only a structural walk says so.

**Reading:** under these conditions the memory-dump route is refused by the target, not by the host
tooling. Two shape-identical failures on a single variable is the skill's own stop signal: the correct
move is to re-classify (`references/advanced-unpacking.md` §the four shapes, then
`references/detection-and-anti-analysis.md`), **not** to run a third variant of the same attach.

Two of the four failures above were the observer's own mistakes, and they are worth keeping because
they are cheap to repeat: `-d` is a switch, not a delay, and any extra positional argument reaches
`spawn(argv)`. `-n <name>` on this version of `frida-dexdump` also still routes through the spawn
path, so "attach by name" does not exist as a way around the spawn refusal — use `-p <pid>`.

### (4) What the sample looks like at the moment it is attacked (observed)

```
$ adb shell 'su -c "top -n 1 -b"'
  PID USER      PR NI  VIRT   RES   SHR S[%CPU] %MEM   TIME+ ARGS
31284 u0_a623   10 -10  13G   561M  268M S  439   4.8   0:05.52 <PKG>
154   root     20   0     0     0     0 S 66.6   0.0   0:02.18 [kswapd0]
17638 system   18  -2   12G   590M  419M S 60.6   5.1   1:15.93 system_server
```

A Flutter application in its startup window saturates several cores (439 % CPU) while the Dart VM
initialises, and the device — 11.7 GB RAM with 357 MB free at that moment — runs its reclaim thread at
two thirds of a core. **The load on this device during the experiment was the sample's, not the
observer's instrumentation.** That matters for attribution: "the device is slow, so the dump failed"
is not available as an explanation here, because the failing command is a *protocol* failure
(`script has been destroyed`) rather than a timeout.

## The device's own framework was already damaged (observed)

Recorded here because it is a **third candidate mechanism** for "things keep restarting", alongside the
sample's self-exit and the memory pressure — and because it invalidates any dynamic result that
depends on the hooking framework:

- `LSPosed Manager` opened to **"LSPosed is not installed"**, with no modules tab, while the `lspd`
  daemon was still alive.
- The LSPosed configuration database had not been updated since **19:37** — it still pointed at the
  `codePath` of an app that had been uninstalled, and never registered the replacement.
- `logcat` showed a loop: `system server died`, `am is dead`, `no response from bridge`, and
  `Magisk: zygote crashed too many times, rolling-back`.

A zygote in a crash-and-rollback cycle restarts application processes by itself, so **"the pid changed"
had at least three independent possible causes on this device** (the sample exiting, reclaim, and a
broken framework). That is exactly why the corrected §2 attributes the drift to *instability of the
observation target* rather than to any single mechanism, and why a dynamic result needs its device's
framework state recorded next to it — `scripts/preflight.py` reads device state for the same reason.

Recovery is a reboot (Magisk re-initialises Zygisk and `lspd` at `late_start`; the LSPosed daemon is
started once and does not return if killed). Whether the framework came back after the reboot, and
whether the sample's self-exit behaviour changed with it, is recorded in
`EXTENSION-lsposed.md` — and any change there must stay **inferred**, because a reboot moves several
variables at once.

## A shared-device hazard, measured (observed)

While the run above was in progress, a second agent on the same device used **Frida Stalker** against
`com.android.settings` and `com.android.systemui`, including a `libc` `malloc` export trigger that
entered and left `follow` hundreds of times. Result:

- `Stalker.follow` on the main thread reported `blocks=0`, `blk=0`, `calls=0` — **the follow installed
  and no events arrived**.
- `systemui` then died with `SIGSEGV`, the faulting frame sitting in gum's anonymous code cache and
  the backtrace continuing into `libart` at `art::Reference_getReferent`; the process restarted
  (`18030 → 26932`).
- Device load average reached **34.11** on an eight-core phone.

**Reading:** two conclusions, kept separate on purpose. First, on this ROM + `frida-server` 16.7.19
combination a Stalker follow produced no events — that is a *boundary* for
`references/native-dbi-and-deobfuscation.md`, not a contradiction of Stalker's documentation. Second,
high-frequency `follow`/`unfollow` on every `malloc` entry crashed a system process — a measured
failure mode for the pattern, and one worth stating before anyone puts it in a shipped script.

The third conclusion is about method rather than about Stalker: **instrumentation on a shared device
is a shared variable.** The concurrent load damaged the *other* experiment's validity — the dumped-run
above could not be attributed until it was repeated with the device idle, and the repeat is what
turned "maybe the load broke it" into a reproducible protocol refusal. R2 (one variable at a time)
applies across agents, not only within one script.

## Conclusions, graded

| Claim | Label |
|---|---|
| The sample runs healthy with no instrumentation on the device | observed |
| The sample's pid drifts repeatedly during an experiment, roughly every 10-20 s | observed — **cause not instrumentation**: reproduced with `frida-server` stopped, under 300-750 MB free memory (§2) |
| `frida-dexdump` spawn refuses (jailed / argv / timeout) and attach fails with `script has been destroyed`, reproduced twice with the parameter mistakes fixed | observed |
| The attach failure is deliberate armour rather than a host-tool bug | **unverified** — memory pressure leaving the process an unstable target is a competing explanation this pass did **not** rule out; the single-variable repeat eliminated *concurrent* load, not *baseline* load |
| The shipped shell `classes.dex` is 8.9 MB and defines only 4 classes / 29 methods with code | observed (recorded in `EXTENSION-unpacking.md`) |
| Recovering the real bodies needs a route other than a `frida` memory dump on this target | inferred |
| Stalker follow delivers no events on this ROM with this frida-server version | observed, single sample, `unverified` as a general rule |
| High-frequency follow/unfollow on `malloc` can crash a system process | observed, once |
| No app on this device is currently hidden from root (`magisk --denylist status` enforced, list empty; Zygisk-Assistant installed but nothing configured) | observed (recorded in `EXTENSION-lsposed.md`) — offered here because a hardened sample's sensitivity to a rooted device has a configuration, not just a cause |

## What this pass did **not** establish

- **Not** a successful end-to-end unpack of the sample. The memory-dump route was refused, and the
  pass stopped at the skill's own two-strike rule instead of escalating into an evasion arms race.
- **Not** evidence that the sample is un-unpackable. The routes that do not use `frida` on the device
  — root-side `/proc/<pid>/mem` extraction, the module route in `references/lsposed-and-modules.md`,
  and the static route already recorded for the Flutter payload — were not exhausted here.
- **Not** a general claim about 360-jiagu, Flutter, or Android 11. Everything above is one device,
  one ROM, one server version, one sample.
