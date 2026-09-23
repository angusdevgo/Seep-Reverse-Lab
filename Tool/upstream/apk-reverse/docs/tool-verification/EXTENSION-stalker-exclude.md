# Stalker `exclude` — what it fixes, and what it does not

**Question.** Community practice says a followed thread that runs through `libc`/`libart` on arm64
gives deadlocks, watchdog `SIGABRT`s and zero-event traces, and that `Stalker.exclude()` is the
remedy. This pass measured which of those two claims survives contact with a device.

**Strength summary:** the *crash* half is `observed` with a clean control; the *zero-event* half is
`observed` as a **negative** — exclusion did not change it. Every command and its output are below.

## Design

Three arms, one device, one package, one module, one follow window. Exactly one variable moves
between `baseline` → `control` → `treatment`.

| Arm | What it does | Why it exists |
|---|---|---|
| `baseline` | spawn, attach, inject the script, **resume, and never follow** | Without this arm a dead process cannot be attributed: "following killed it" and "the app dies under frida anyway" look identical |
| `control` | follow the main thread for 6 s with `excludeModules: []` | The shape that produced the earlier zero-event / `SIGSEGV` results |
| `treatment` | same follow, with the script's built-in list of 20 system modules excluded | The proposed remedy |

The harness also neutralises one trap in the script itself: `CONFIG.autoStart` defaults to `true`, so
loading `stalker_trace.js` starts a follow with *default* options before a runtime configuration can
land. Left alone, that run is neither the control nor the treatment and contaminates both. The
harness patches `autoStart` to `false` in the injected source and asserts the patch count.

For the same reason the harness resumes explicitly: `frida` spawns a process **suspended**, so
without `device.resume(pid)` the followed thread executes nothing and both arms report a zero-event
trace *manufactured by the harness*. That failure mode is indistinguishable from the one under
investigation, which is exactly why it has to be engineered out before the measurement means
anything.

## Result

```
baseline   alive=True    (no follow installed)
control    alive=False   err=script has been destroyed
           EXCL|excluded=0/0 []
treatment  alive=True    DONE|reason=timeout blocks=0 blk=0 calls=0 truncated=0
           EXCL|excluded=20/20 [libm.so,libdl.so,libart.so,libartbase.so,libnativehelper.so,…] not-loaded=3
           WARN|zero events 1500ms after follow (blocks=0 blk=0 calls=0) -- the pipeline is NOT proven
```

## What this settles

1. **A follow with no exclusion killed the target process, and the baseline arm rules out the
   alternatives.** The process survives an attach plus resume with no follow, and dies only when the
   follow is installed. That is `observed`, not inferred.
2. **Exclusion kept the process alive.** The treatment arm reached its normal `DONE|reason=timeout`
   with the process still running. Excluding the system libraries from a follow is not a style
   preference.
3. **Exclusion did not restore event delivery.** The treatment arm still reported
   `blocks=0 blk=0 calls=0` after a full 6-second window. The zero-event trace is therefore a
   **separate defect from the load problem**, and `Stalker.exclude()` must not be presented as its
   fix. This partially contradicts the community framing, which lists "no events" among the symptoms
   exclusion cures.
4. **The zero-event warning added to `stalker_trace.js` this pass fires correctly** — `treatment`
   emitted `WARN|zero events 1500ms after follow`, while `control` could not, because its process was
   already gone. A dead pipeline now announces itself instead of being read as "the code did not run".

## What this does not settle

- **Why events do not arrive.** This measurement says it is not the exclusion list. It does not
  identify the cause, and it does not distinguish "no events" from "the followed thread genuinely ran
  nothing in that window" — the per-arm control that would separate those (following a thread
  executing a known loop) was not run.
- **Whether the crash is reachable without a follow.** Only one package and one module were used, and
  the harness kills the process at the end of each arm, so nothing is claimed about a long-lived follow.
- **Anything about other ROMs, other frida versions, or armv7.** Single-device result.
- **The multiplier.** Nothing here measures the 20-50x cost figure; this is about survival and
  delivery, not throughput.

## Environment

`<DEVICE>` (Android 11 / API 30 / arm64-v8a, Magisk root), frida host 16.7.19, on-device
frida-server 16.7.19 reached over `adb forward tcp:27099`. Target: the MASTG `UnCrackable-Level1`
sample, package `<PKG>`, module `libc.so` followed on the main thread for 6 s per arm. Device
`load average` was ~30 throughout — high for an 8-core phone, and worth recording because the
earlier incident in `native-dbi-and-deobfuscation.md` §6 happened on a loaded device.

## Reproducing

```
python tools/_work/b6/stalker_ab.py --package <PKG> --module libc.so \
    --mode baseline|control|treatment --seconds 6 --device 127.0.0.1:27099 \
    --out tools/_work/b6/r_<mode>.json
```

The driver is a work artefact under `tools/_work/` (git-ignored), not part of the skill. Its three
arms and the two harness traps it neutralises are the reusable part.
