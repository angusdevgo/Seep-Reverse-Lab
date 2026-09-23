# Extension verification — native DBI/deobfuscation and protocol reverse engineering

Covers the 2026-09 extension pass that added `references/native-dbi-and-deobfuscation.md` and
`references/protocol-reverse.md`. Strength labels as defined in this directory's README:
**observed** (exact command + output here), **inferred** (follows from observed facts, step not
executed), **unverified** (assumed or externally reported, not independently confirmed).

Reference environment for this pass: Windows 11 host, Python 3.14.0, host frida 16.7.19
(frida-tools 13.7.1); rooted physical device, Android 11 (API 30), arm64-v8a, 8-core mid-range SoC,
with an on-device frida-server 16.7.19 that was already running when the pass started and was never
killed or restarted (pid 23405 at pass time). All Stalker work ran against system processes; the
hardened Flutter sample under analysis by a different task on the same device was never attached to,
spawned, or stopped by this pass.

**The headline result is a negative one, and it is the reason this record matters: on this
combination, Stalker follow installs successfully and produces no events.** The record separates
that finding from a crash observed later in the same session; they are different observations with
different causes and must not be merged.

---

## 1. Scripts under test — observed

`skills/apk-reverse/scripts/stalker_trace.js` (456 lines) and
`skills/apk-reverse/scripts/stalker_report.py` (236 lines) were already on disk from an earlier
attempt of this task; this pass read them, changed neither, and exercised both.

```
$ node --check skills/apk-reverse/scripts/stalker_trace.js
syntax check exit = 0

$ python skills/apk-reverse/scripts/stalker_report.py --help
usage: stalker_report.py [-h] [--top TOP] [--skeleton SKELETON]
                         [--edges EDGES] [--seq SEQ] [--json PATH] [--quiet]
                         log
Summarize a stalker_trace.js log into a block histogram, a first-visit CFG
skeleton, and call-edge tables.
```

Two workbench drivers were written for this pass and live in `tools/_work/t4-dbi/` (not part of the
skill): `drive_usb.py`, which attaches over USB and calls
`rpc.exports.config(...)` / `start(tid)` explicitly, and `pb_selftest.py` (§7).

Why a second driver was needed at all: `scripts/run_probe.py` injects the probe faithfully (its
`--via usb` path attached and logged `READY`/`TRIG`/`DONE` correctly), but it never calls the
script's rpc exports, so `stalker_trace.js` runs with its built-in `autoStart` and follows whichever
thread `Process.getMainThreadId()` reports. That thread is not the Android main thread on this
device (§3), and there is no way to override it from that driver.

## 2. Report parser validated against a hand-written fixture — observed

`tools/_work/t4-dbi/synthetic.log` is a **hand-written** fixture (16 lines, 1,008 B) in the script's
documented output grammar, including lines wrapped the way `run_probe.py` wraps them. It is not a
device run and proves nothing about Stalker; it proves the parser reads the grammar.

```
$ python skills/apk-reverse/scripts/stalker_report.py tools/_work/t4-dbi/synthetic.log \
      --top 4 --skeleton 6 --edges 4 --seq 8
  module libdemo.so               base=0x7abc000000 size=1048576 (target)
  unique blocks first-seen (BB) : 3
  block executions (BLK)        : 7
  call edges (CALL)             : 2
  DONE reason=timeout truncated=0 (device-side counts: bb=3 blk=7 call=2)

== execution histogram: top 4 (dispatcher candidates) ==
  rank   count    pct     block                        firstSeen
  1      4         57.1%  libdemo.so+0x9f6c0           #1
  2      2         28.6%  libdemo.so+0x9f710           #2
  3      1         14.3%  libdemo.so+0x9f800           #5

== call edges (top 4 of 2) ==
  1        0x7ab3001020 -> libdemo.so+0x9f6c0
  1        libdemo.so+0x9f800 -> libdemo.so+0x9f710

== collapsed execution sequence (first 6 runs of 6) ==
  libdemo.so+0x9f6c0 -> libdemo.so+0x9f710 -> libdemo.so+0x9f6c0 -> libdemo.so+0x9f800 ->
  libdemo.so+0x9f6c0*2 -> libdemo.so+0x9f710
```

The four reductions the reference promises — histogram, first-visit skeleton, call edges, collapsed
sequence — all behave as documented, including the `*N` repeat collapse that makes a
dispatcher/real-block rhythm legible. `--quiet` and `--json` paths were exercised too (§3, §4).

## 3. Device attempt A — follow a chosen thread, zero events (observed)

Two system processes, each attached for 8 s with `followMs=4000`, target module `libc.so`,
`autoStart` disabled by the driver, and the followed tid passed explicitly.

```
$ python tools/_work/t4-dbi/drive_usb.py --js skills/apk-reverse/scripts/stalker_trace.js \
      --pid <settings pid> --seconds 8 --log tools/_work/t4-dbi/run2_settings_main.log
READY stalker_trace loaded; target=libc.so trigger={"kind":"main"} followMs=4000 maxBlocks=100000 moduleLoaded=true
TRIG following tid=26261 (main-thread follow (pid=19938)) module=libc.so base=0x721be88000
TRACE MOD libc.so base=0x721be88000 size=999424 path=/apex/com.android.runtime/lib64/bionic/libc.so
DONE reason=reconfig blocks=0 blk=0 calls=0 truncated=0
TRIG main trigger armed (autoStart=false); call start()
[rpc] start(19938) -> {"following": true, "followingTid": 19938}
DONE reason=timeout blocks=0 blk=0 calls=0 truncated=0
```

Facts worth keeping separate from the interpretation:

- `Process.getMainThreadId()` returned **26261** for a process whose pid is **19938**. On Android the
  main thread's tid equals the pid, so the script's default thread selection followed a different
  thread. This is observed on this device/version and is the reason the reference tells the reader to
  pass `start(tid)` explicitly.
- Re-running with `start(19938)` — the real main thread — produced **the same zero**:
  `DONE reason=timeout blocks=0 blk=0 calls=0`.
- A third run against a system UI process (`run3_systemui_libc.log`, same `followMs=4000`)
  reproduced it identically. `stalker_report.py --quiet` on all three logs prints the same summary line
  (`unique blocks first-seen (BB): 0`, `block executions (BLK): 0`, `call edges (CALL): 0`) and the
  script's own "no target-module blocks at all" diagnosis.

**Interpretation: unverified as to cause.** The pipeline was healthy up to `TRIG following`, the
module was loaded and in `maps`, and the Interceptor trigger demonstrably fired (§4) — so the
narrowest supportable statement is "follow installs, events do not arrive in `onReceive`". Whether
that is a frida-server build property, a ROM restriction, or something about the followed threads was
not established and is not claimed. No trace was successfully recorded on this device during this
pass.

## 4. Device attempt B — hot-function export trigger, zero events (observed)

The `export` trigger kind was exercised with `malloc` in `libc.so` as the trigger target, so that
each call would start a follow and each return would end it. The trigger fired repeatedly for the
whole window.

```
$ python tools/_work/t4-dbi/drive_usb.py --js skills/apk-reverse/scripts/stalker_trace.js \
      --pid <systemui pid> --seconds 6 --log tools/_work/t4-dbi/run4_systemui_malloc.log \
      --cfg '{"targetModule":"libc.so","trigger":{"kind":"export","module":"libc.so","export":"malloc"},"followMs":1000,"maxBlocks":20000}'

$ lines = 609   follows = 201   done_lines = 201   nonzero_blk = 0
# per-firing shape:
TRIG following tid=18915 (trigger 0x721becbbf0) module=libc.so base=0x721be88000
DONE reason=trigger-leave blocks=0 blk=0 calls=0 truncated=0
```

This is the strongest evidence for the §3 statement: **201 fully-formed follow cycles, each with a
clean `DONE`, and not one reported block in any of them.** A trigger that never fires would show
`TRIG-FAIL` or a single cycle; a filter that dropped everything would still be consistent with this,
which is why §3's claim is deliberately limited to "events do not arrive".

## 5. Device attempt C — a system UI process died during the hot-trigger run (observed)

Same run as §4, minutes later, on the same pid. The process died and was restarted by the system.

```
$ adb shell pidof com.android.systemui
18030            # before
26932            # after

$ adb shell "su -c 'logcat -b crash -d -t 80'"
09-21 20:22:25.327  ... F DEBUG :     pc  00000070cf8ae464  pst 0000000040001000
09-21 20:22:25.719  ... F DEBUG : backtrace:
09-21 20:22:25.719  ... F DEBUG :       #00 pc 000000000001f464  <anonymous:70cf88f000>
09-21 20:22:25.719  ... F DEBUG :       #01 pc 00000000004d0b64  /apex/com.android.art/lib64/libart.so
                                            (art::Reference_getReferent(_JNIEnv*, _jobject*)+44)
09-21 20:22:25.719  ... F DEBUG :       #03 pc 000000000008220c  boot.oat (art_jni_trampoline+124)
09-21 20:22:25.719  ... F DEBUG :       #08 pc 0000000000714240  boot-framework.oat (android.os.Looper.loop+2176)
```

Reading of the record, stated as an attribution hypothesis rather than a proven mechanism: frame
`#00` sits in an **anonymous executable region** (`<anonymous:70cf88f000>`), which is the shape of a
DBI's translated-code cache rather than of a file-backed library, and the return path leads into
`libart`. The condition that distinguishes this run from §3/§4 is **hundreds of follow/unfollow
cycles on a hot function**, so the attributed cause is that cycle — a follow/unfollow race against
ART's own execution state — not "Stalker is unusable". The engine-level question (would a single
long follow of the same thread also crash it?) was not tested and remains **unverified**.

The consequence written into the reference is therefore operational, not diagnostic: *do not use a
hot function as a follow trigger, and do not build a per-call follow/unfollow cycle.* Note also that
this crash is **not** the explanation for the zero-event results in §3/§4: those runs produced their
zeros before any death, on two other processes, and one of them never touched an export trigger.

## 6. Cross-task contamination on a shared device — observed (reported by the Lead)

While §3–§5 were running, the device's `load average` was **34.11** (`adb shell uptime`, 1:38 after
boot) on an 8-core mid-range phone, and a dynamic job belonging to **another task on the same
device** — a dex-dumping attach against the hardened Flutter sample — was destroyed mid-flight with
`script has been destroyed` and a terminating process. Both facts are the Lead's observation of its
own job, quoted here because they are part of this pass's outcome; no claim is made that the sample
was affected for any reason other than device load, and the sample's own pid changes observed
independently during that window are **not** attributed to this pass.

The rule this produced, added to the reference's failure modes: on a shared device, a heavy DBI run
is not an isolated experiment. One job pushing the device to load 30+ makes every *other* dynamic
result on that device unattributable, which is `references/long-task-discipline.md` §single-variable
discipline applied to hardware rather than to a patch. Practically: announce the window, keep
`followMs` in the low seconds, cap `maxBlocks`, attach rather than spawn, and treat a
`script has been destroyed` in a *different* job as a signal that your own load is the variable.

## 7. Protobuf wire format self-test — observed

`tools/_work/t4-dbi/pb_selftest.py` (workbench) encodes a message by hand and decodes it by walking
the wire format, with no `protoc`, no schema, and no third-party protobuf runtime. It exists to give
`references/protocol-reverse.md` §1 an output behind its claims.

```
$ python tools/_work/t4-dbi/pb_selftest.py
== canonical varint check ==
  varint(0     ) = 00       ok
  varint(150   ) = 9601     ok
  varint(300   ) = ac02     ok
  varint(86942 ) = 9ea705   ok

== fixture bytes ==
  nested payload (5 B): 0801120178
  packed payload (6 B): 038e029ea705
  message         (29 B): 089601120774657374696e671a0508011201782206038e029ea7052800

== schema-free decode (the shape protoc --decode_raw produces) ==
field 1   varint             150
field 2   len-delimited(7)   str 'testing'
field 3   len-delimited(5)   nested message:
  field 1   varint             1
  field 2   len-delimited(1)   str 'x'
field 4   len-delimited(6)   hex '038e029ea705'
field 5   varint             0

== what the decode cannot tell you ==
  explicit 0 at field 5 : 2800
  field 5 never written : b''
  -> proto3 cannot distinguish these two on the wire; a decoded "0" is not evidence the sender set the field.
  -> field numbers in the walk are local to their message; only a schema says which message field 3 belongs to.

== re-encode round trip ==
  rebuild from the walked rows equals original: True
```

Two of the reference's claims are now measured rather than repeated: the packed repeated field
(`3, 270, 86942`) is reported by a schema-free decode as opaque hex because element boundaries need a
schema, and an explicitly written proto3 zero is byte-identical to an absent field. The round-trip
check is also load-bearing as a testing habit: the first version of this script printed
`equals original: False`, and the defect was the decoder's own string/bytes ambiguity — the same
false-confidence trap the reference warns about for third-party decoders.

## 8. Not run, and therefore unverified

Everything below is stated in the references as inferred or unverified, and was **not** exercised in
this pass:

- Any successful Stalker trace. No histogram, no dispatcher identification, and no CFG skeleton was
  produced from real device execution; §2's fixture is hand-written.
- Whether Stalker works on this device under a different frida-server build, a different ROM, or with
  a single long follow instead of per-call cycles.
- `events.exec` and `events.ret` (the per-instruction and return-edge paths) — never enabled.
- QBDI / frida-qbdi, angr, Triton, unidbg, Unicorn: not installed, not run. §4/§5 of
  `native-dbi-and-deobfuscation.md` are method descriptions.
- Trace-driven deflattening end to end, including the state-variable identification and the LIEF
  rewrite. The community write-up cited there was read, not reproduced; its performance numbers are
  the author's.
- `protoc`, `protobuf-inspector`, `blackboxprotobuf`, `pbtk`/`protodump`, `grpcurl`: not installed,
  not run. The schema-recovery routes in `protocol-reverse.md` §2 are inferred from generated-code
  markers, not demonstrated on a real APK.
- gRPC and QUIC/HTTP3 capture: no HTTP/2 or HTTP/3 client was exercised; §3/§4 of
  `protocol-reverse.md` are unverified.
- `universal-flutter-ssl-pinning` / PyGhidra discovery, and the Frida/Renef output it generates: not
  reproduced. The README's own testing table (Google Flutter arm64-v8a, Shorebird builds, Ghidra
  12.x, Frida 16.x/17.x) is the only evidence behind that section.
- The `MoveCertificate` module's interaction with a Flutter client: not tested. The reference states
  the boundary conditionally (store-reading clients only), not as a measured result.

## 9. What this pass licenses

It licenses the following statements and nothing wider: the trace/report toolchain is syntactically
sound and its parser is verified against its documented grammar; an Android 11 arm64 device with
frida-server 16.7.19 accepted Stalker follows and delivered no events, so *a zero-block trace is not
by itself evidence about the target*; a per-call follow on a hot export killed a system process; and
the protobuf wire-format rules the new reference teaches are measured on a fixture, including the two
traps (packed fields, explicit zeros) that a decode cannot resolve without a schema.
