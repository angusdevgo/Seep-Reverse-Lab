# Extension verification — root-side memory dump (the route that does not use frida)

Covers the 2026-09 extension pass that added the §Dumping when frida is refused section
to `references/advanced-unpacking.md`. It is the follow-up to
`docs/tool-verification/EXTENSION-device-run.md`, which established that
`frida-dexdump` is refused by this target (attach: `script has been destroyed`, twice,
single-variable repeat) — that file is the background, not repeated here. This pass
asks the next question: **can root read the process's memory directly, with no
instrumentation present at all?**

Strength labels, as defined in this directory's README:

- **observed** — reproduced here, with the exact command and its output.
- **inferred** — follows from observed facts, but the step itself was not executed.
- **unverified** — assumed, or reported by a tool and not independently confirmed.

**Target identity is deliberately absent**; the package appears as `<PKG>`. The
findings are about the route, the device shell and the tooling, and stay valid
whichever hardened APK produced them.

## Environment (observed)

| Item | Value |
|---|---|
| Device | the same physical arm64 device as `EXTENSION-device-run.md`: Android 11 (API 30), kernel 4.14.186, Magisk root |
| Instrumentation | **none** — the device-side `frida-server` was left stopped for the whole pass; `ps -A \| grep -i frida` returned nothing before and after |
| Sample | 360-jiagu hardened, Flutter AOT payload, installed and untouched (no reinstall, no repack) |
| Root access | `adb shell 'su -c "…"` — full root, no `avc: denied` in any read attempt below |
| Device shell | toybox (`grep`, `dd`, `ps`, `stat`, `awk`, `sed`); no `findstr`, no `ls --time-style`, no `map_files` entries |

Two shell facts were measured before anything else, because both silently corrupt a
naive dump and neither announces itself:

```
$ adb shell 'su -c "grep --help"'      # → -a -b -o -z -E -F available
$ adb shell 'su -c "dd --help"'        # → iflag=skip_bytes,count_bytes available
```

## 1. The sample does not stay up, with or without frida (observed)

The control assumption going in was that the sample is stable when nothing is
attached. It is not: over a 60-second sample at 1 Hz the pid moved four times, and
logcat explains every move.

pid sequence, `ps -A -o PID,NAME | grep -w <PKG>` once per second:

```
20:31:02 16729 … 20:31:07 16729
20:31:08 17951 … 20:31:23 17951
20:31:26 20021 … 20:31:42 20021
20:31:43 21632 … 20:32:00 21632
20:32:01 (none)  20:32:02 22770 …
```

The platform's own record of two of those transitions:

```
09-21 20:31:43.327 I/ActivityManager: Process <PKG> (pid 20021) has died: fg  TOP
09-21 20:31:43.394 I/ActivityManager: Start proc 21632:<PKG>/u0a623 for top-activity {<PKG>/.MainActivity}
09-21 20:32:01.463 I/ActivityManager: Process <PKG> (pid 21632) has died: fg  TOP
09-21 20:32:01.555 I/ActivityManager: Start proc 22770:<PKG>/u0a623 for top-activity {<PKG>/.MainActivity}
```

- **observed:** each process lives **7-18 s**, then dies as a *foreground, top*
  process, and is started again by `ActivityManager` because the activity stack is
  still on top. Lifetime is not constant.
- **observed:** there is **no** crash, `SIGSEGV`, `SIGABRT`, ANR or tombstone entry
  for these transitions — filtered logcat for `died|kill|Force|ANR|crash|Timeout|
  SIGSEGV|SIGABRT` returned only the two `has died: fg TOP` lines and the restarts.
  A clean self-exit, not a platform kill.
- **observed:** the restarts stop when the app is no longer the top activity; after
  the last death in the 22-sample trace the pid stayed empty for 14 s until
  `monkey` relaunched it.
- **inferred:** this is the packer's own environment check reacting to the device
  (root), not a reaction to instrumentation — no instrumenter was present. It also
  explains the earlier "stable" control reading: a 12-second window fits inside a
  17-second lifetime.
- **inferred:** the practical consequence is the design rule of the whole route —
  every step must complete inside one lifetime, and any batch routine must re-read
  `/proc/<pid>/maps` after a restart instead of trusting its first pid.

## 2. The map is the cheapest source of dex images (observed)

`/proc/<pid>/maps` for the live sample: 522,795 bytes, 5,617 regions. ART names the
dex images it holds, so no search is needed for those:

```
7129d8c000-712a60f000 r--p  [anon:dalvik-classes.dex extracted in memory from /data/app/~~…/base.apk]
6f9ba03000-6f9be2b000 r--p  [anon:dalvik-classes.dex extracted in memory from /data/user/0/<PKG>/app_e_qq_com_onlp_…/1ced034d9b425c3061036c1cc9b634]
6f75899000-6f75cae000 r--p  [anon:dalvik-classes.dex extracted in memory from /data/user/0/<PKG>/app_sodler/com.kwad.components.tachikoma/5.6.10.1/base-1_apk]
… 17 such regions in total
```

Export command actually used (decimal offsets; see §4 for why not hex):

```
dd if=/proc/<pid>/mem iflag=skip_bytes,count_bytes skip=<DEC_START> count=<SIZE> \
   of=/data/local/tmp/t2dump/dexNN.bin bs=64k
```

All 17 regions exported; 16 of 17 completed inside one lifetime, two of the trailing
regions were cut short by the restart described in §1 and came back as 0-byte files —
which is the failure mode to expect, and the reason the batch must be re-entrant.

## 3. Validation: what the exported images actually are (observed)

The dumps are page-aligned and therefore 0..4095 bytes longer than the image they
carry, so all 17 were **rejected on first validation**:

```
== dex dump validation: 7 file(s), 0 parse, 7 rejected ==
dalvik-classes.dex_…base.apk.dex  8925184  REJECTED: file_size=8923752 actual=8925184
```

Trimming each file to the `file_size` field at dex-header offset 32 (dropped 68 …
3,724 bytes per file) then gave a clean run:

```
== dex dump validation: 17 file(s), 17 parse, 0 rejected ==
name        size      sha256[:12]   ver  cksum   sig    class  noco   code   stub%
dex16.bin   122460    3fc5581d6eb3  035  ok      BAD      103   207   8974    1.1%   (ksad dynamic apk)
dex08.bin  1069516    613cfef811ab  035  ok      BAD     1285   432   8929    0.9%   (kwad ksdp)
dex14.bin  8923752    1497590d0a24  035  ok      BAD        4   160     29    3.4%   (from /data/app/…/base.apk)
dex01.bin  3212480    fb61a3f085f5  035  ok      ok      3169   785  15924    1.0%   (pangle live-lite classes6)
… 17 images, stub% 0.9 – 3.4, 17/17 unique by sha256

ranking (most likely original first):
  1. dex08.dex  stub%=0.9  cksum=ok  sig=BAD  classes=1285
  …
 17. dex14.dex  stub%=3.4  cksum=ok  sig=BAD  classes=4
```

**What this means, and what it does not:**

- **observed:** the route produces *real, parseable dex* from a hardened app's process
  memory without any instrumentation — 17 images, one class count 103 up to 10,148,
  `stub%` in the low single digits. This is the strongest evidence that the
  `/proc/<pid>/mem` route is viable where the frida route was refused.
- **observed:** the image that came from the app's own `base.apk` defines **4
  classes** on an 8.9 MB file (`sig=BAD` on the untouched image). File size and class
  count move independently under a packer — this is the landing-shell skeleton shape,
  matching the shipped `classes.dex` recorded in `EXTENSION-unpacking.md`.
- **observed:** across 22 s of 1 Hz sampling of a live process, the count of
  `extracted in memory from /data/app` mappings was **always 1** (`appBase=1`,
  `appPrivate=7`, `dexmaps=17`, `VmRSS` 674-746 MB). No second application dex mapping
  ever appeared.
- **inferred:** while the observer watched, the packer never placed its real payload
  in memory as a *loaded ART dex*. Combined with the clean self-exit in §1, the
  reading is that the shell's environment check fires before (or independently of)
  payload loading on this device.
- **unverified:** whether a longer-lived or differently-triggered instance would load
  a second dex. No attempt was made to defeat the check, by task instruction.

## 4. Searching memory for a decrypted dex: what the device shell does to you

Two blind searches were run for the pattern the payload would leave if it were sitting
in a native or heap buffer rather than a loaded dex.

**Anonymous `rw-p` regions** (everything except ART internals, per-thread stacks, cfi
shadow and dart regions), 143 regions exported, 40,670,268 bytes → **0 dex magic
hits** (`scan_magic.py`, `dex\n03x` with `file_size` cross-check).

**ART main space (`dalvik-main space (region space)`, 1 GB reservation)** sampled in
64 MB windows from the start of the space → **0 dex magic hits** in the 192 MB
covered, at **~10 MB/s**:

```
maps_line=12c00000-52c00000 rw-p … [anon:dalvik-main space (region space)]
region_space_base=314572800
off=0          abs=314572800 secs=6  hits=[]
off=134217728  abs=448790528 secs=7  hits=[]
PID_DEAD before off=268435456
```

**inferred:** at 10 MB/s a full 1 GB heap sweep is ~100 s — several process
lifetimes — so heap search is not a plan for a sample with this restart cadence.
Named ART dex mappings are free; a heap sweep is not.

Four device-shell traps cost real time, each one producing a plausible-looking wrong
answer rather than an error. All four are **observed**:

| Trap | Observed behaviour | What worked |
|---|---|---|
| mksh arithmetic is 32-bit | `$((16#7129d9a000))` → `702128128` (the low 32 bits); `dd skip=702128128` then read an unrelated address and the "dump" was zeros | convert with `awk` (`48-bit` values exact in double): `awk 'BEGIN{…n=n*16+v…; printf "%d", n}'` |
| VMA page alignment | 17/17 dumps rejected with `file_size=… actual=…`, excess 68…3724 B | trim to header `file_size` before validating |
| `grep` is line oriented | `grep -F` with a real newline in the pattern matched only `035` at the wrong offset; `-E` with a literal newline matched nothing | `grep -z -a -o -b -E 'dex.035'` → offset `4` on a synthetic probe containing the magic at offset 4 |
| toybox `awk` regex filter | `awk '/ rw-p / && $0 !~ /dalvik-\|…/'` selected all **808** map lines, including `r--p` system libraries, so the candidate list was meaningless | filter with `grep -aE '^[0-9a-f]+-[0-9a-f]+ rw-p '` plus `grep -av`, keep `awk` for arithmetic only |

**`/proc/<pid>/map_files/` is not a shortcut on this ROM** (observed): the directory
exists, is `dr-x------ root root`, and lists **no entries**, so
`dd if=/proc/<pid>/map_files/<start>-<end>` yields 75 bytes of `can't open … No such
file or directory`. The `mem` + decimal-offset form is the one that works.

**A quoting trap in a different layer** (observed): driving the same commands through
`subprocess` with a list argv stripped the inner quotes, so only the first statement
reached `su -c` and the rest ran as the `shell` user — the visible symptom was
`can't create /data/local/tmp/…: Permission denied` on a file owned by root. Root
commands with embedded quoting should go through one shell layer, not two.

## 5. Leftover dumps in the work directory — what they are (observed + inferred)

`/data/local/tmp` carried `.so` files from earlier sessions. They were verified rather
than trusted:

| File | Size | sha256[:16] | ELF | Sections |
|---|---|---|---|---|
| `L_libapp.so` = `d_libapp.so` = `libapp.bak` | 13,501,344 | `2275dd4398f0b34e` | ELF64 AARCH64, `ET_DYN`, phnum 7 | 11 |
| `rt_libapp.so` | 13,501,344 | `8b490512258ba1c8` | ELF64 AARCH64, `ET_DYN`, phnum 7 | 11 |
| `libapp.so` | 12,256,160 | `4cfec2762c25539b` | ELF64 AARCH64, `ET_DYN`, phnum 7 | 11 |
| `ll.so` | 6,230,040 | `20f2d12b5049f238` | ELF64 AARCH64, `ET_DYN`, phnum 9 | 26 |

- **observed:** all four are structurally valid ELF64/AARCH64 shared objects with a
  **complete section header table**, and the three `libapp` variants contain the Dart
  AOT `snapshot` marker (3 occurrences each).
- **observed:** the `libapp.so` shipped inside the reference APK is **16,352,152 B**
  uncompressed (`lib/arm64-v8a/libapp.so`), i.e. ~2.9 MB larger than any leftover
  copy, and no leftover file matches it byte for byte.
- **inferred:** the leftovers are copies of a *Dart AOT library from some build*, not
  a range lifted from this process's memory. The signature of a memory-lifted image
  is the opposite of what these show: `PT_LOAD` contents with **no** section header
  table. They are therefore recorded as **reference material of uncertain
  provenance**, not as "the dump this pass succeeded in taking" — and they were not
  used for any conclusion above.

## 6. Conclusions, graded

| Claim | Label |
|---|---|
| Root can read `/proc/<pid>/maps` and `/proc/<pid>/mem` on this device with no `avc` denial and no instrumenter present | observed |
| 17 ART dex mappings were exported from a live hardened process and, after trimming to header `file_size`, all 17 parsed as valid dex | observed |
| The dex mapping sourced from the app's `base.apk` defines 4 classes on 8.9 MB (landing-shell skeleton); the other 16 are real SDK dexes, `stub%` 0.9-3.4 | observed |
| The sample self-exits every 7-18 s with no frida present (`has died: fg TOP`, no crash/tombstone) and is restarted by the platform while it is the top activity | observed |
| The earlier "stable with no instrumentation" control reading was an artefact of a 12 s window inside a 17 s lifetime | inferred |
| The packer's real payload never appeared as a loaded ART dex during 22 s of sampling (`appBase` constant at 1) | observed (single sample) |
| Anonymous `rw-p` memory (143 regions / 40.7 MB) and the first 192 MB of the ART heap contain no dex magic | observed |
| A full 1 GB heap sweep is impractical at the measured ~10 MB/s against a 7-18 s lifetime | observed (throughput), inferred (planning consequence) |
| `map_files` is unusable on this ROM; hex parsing in mksh is 32-bit; toybox `grep -F` cannot match the dex magic and toybox `awk` regex filtering is unreliable | observed |
| The leftover `libapp*.so` files are unrelated to this process's memory; provenance unverified | observed (structure/size), inferred (provenance) |

## 7. What this pass did not establish

- **Not** a recovered payload. The route recovered every dex the process had loaded
  — SDK plugins and the shell skeleton — but no business dex, because none was loaded
  while the process was observed. The Flutter payload itself (`libapp.so`, Dart AOT)
  is a separate target and is not reached by a dex-oriented dump.
- **Not** an evasion. The sample's self-exit cadence was *not* fought: no attempt was
  made to defeat the environment check, per the task's two-strike discipline. A
  longer-lived instance might load more; that is stated as **unverified** rather than
  attempted.
- **Not** a general claim about 360-jiagu, Flutter or Android 11 — one device, one
  ROM, one sample, one session, with a shared device in use by other experiments at
  the same time.
- **Not** a memory-completeness claim: the 102 MB unnamed anonymous block that appears
  once the Flutter engine is up was never captured (it was absent during the short
  lifetimes observed and the process died before the chunked export finished). It is
  recorded here as an uncovered region, not as a scanned-clean one.
