# Environment — device, emulator, tooling, networking


**Load this when:** before the first experiment on a device, and again whenever a failure surprises you. It gives device/emulator selection, root, ADB and networking, the preflight check, and how to look at the screen instead of driving blind.

## Pick your target

| Option | Pros | Cons |
|---|---|---|
| **Rooted physical device, native ABI** | Truest behavior; native libs load natively; Frida works well | One at a time; USB flakiness |
| **Emulator with root** | Disposable; snapshots; easy reset | Different ABI; some apps detect it or refuse to run; native ARM libs may need translation |
| **Static only** | No device needed | Cannot verify anything. Never claim success from static analysis alone. |

**Rule:** the artifact must be verified where the user will run it. An emulator that runs the app is **not** evidence about a physical ARM device, and vice versa.

**Important:** if the app ships only `arm64-v8a` native libraries and your emulator is x86_64, it may still run via ARM translation — but translation changes timing, and some native checks misbehave. Prefer a real ARM device for the final verification pass.

## ADB basics worth pinning down

```bash
adb devices -l
adb -s <serial> shell getprop ro.product.cpu.abi
adb -s <serial> shell getprop ro.build.version.release
adb -s <serial> shell getprop ro.build.version.sdk
```

Root:
```bash
adb -s <serial> shell "su -c id"
```
`pm grant` and `pm install` frequently require root on OEM builds; the `shell` user gets `SecurityException`.

**Always specify `-s <serial>` when more than one device is attached** — otherwise adb errors out or picks the wrong one.

## Shell quoting (a real time sink)

The host shell expands `$`, `|`, `>`, and quotes **before** adb sees them. Windows PowerShell additionally mangles `$var:`, `[^"...`, and `$(...)`.

Symptom: "Could not find a part of the path", "Missing type name after '['", "no closing quote".

**Fix:** never inline device commands in the host shell. Use a small helper that calls adb from a script file and passes the command as a single argument:

```python
subprocess.run([ADB, '-s', SERIAL, 'shell', 'su -c "%s"' % cmd])
```
See `scripts/devsh.py`.

Same class of bug: `javac` reads sources using the platform default encoding. Pass `-encoding UTF-8` or non-ASCII comments break the build.

## Giving an offline device network over USB

Use when the device has no usable network (broken Wi-Fi, no SIM, restricted network) but your host does. **`adb reverse` runs on the device's loopback, so it needs no device-side network interface at all.**

```bash
# 1) host HTTP/HTTPS proxy (CONNECT-capable)
python scripts/usb_net_proxy.py 8080 proxy.log

# 2) forward device-localhost:8080 to host:8080
adb -s <serial> reverse tcp:8080 tcp:8080

# 3) point the device at it
adb -s <serial> shell "su -c 'settings put global http_proxy 127.0.0.1:8080'"
```

Notes:
- `adb reverse` **does not survive a device reboot** — recreate it after any restart.
- Keep the host proxy process alive; if it dies, the device goes offline again.
- Some SDKs bypass the system proxy entirely (many ad SDKs do). Proxy logs therefore **undercount** traffic — do not conclude "no ad traffic" from proxy logs alone; confirm with a runtime DNS hook.
- Clean up when done: `settings put global http_proxy :0`.

## Preflight — run this before every experiment block

`scripts/preflight.py` checks, read-only, everything that silently fakes a failure: device
reachability, whether more than one device is attached without an explicit serial, root, the
runtime translation layer, device/host clock drift, a leftover device-wide proxy setting, stale
port forwards, a dead device server, the ABI the package manager actually chose, and the free
space left for installs.

```bash
python scripts/preflight.py --pkg <app.package> --expect-root
python scripts/preflight.py --cleanup      # also clears a leftover proxy and stale forwards
```

**The rule it exists to enforce:** *do not attribute a failure to your patch while preflight is
dirty.* A surprising fraction of "my change broke it" is a device that was already in a bad state.
Costing thirty seconds here is cheaper than costing several rounds to a wrong conclusion, and the
wrong conclusion is the one that gets written down and trusted later.

## Emulator notes

Emulators are the right place to iterate and the wrong place to conclude.

- **Verify the app can install at all.** INSTALL failures on emulators are common (ABI, min SDK,
  vendor checks, a stale copy with a different signature) and are usually **not** related to your
  patch. Get a clean install of the *unmodified* build working before you change anything.
- **Snapshot/rollback is the main advantage** — use it to A/B two builds quickly, and to get back
  to a known-good state after a destructive experiment.
- **Never quote emulator behavior as proof for a device-only question** (and vice versa). An
  emulator that runs the app is not evidence about a physical ARM device.
- **Most vendors ship a console binary that is far more reliable than the GUI.** Learn yours early;
  it is what you will need when the GUI is unresponsive and adb is already down.

  | Vendor | Typical console binary | Useful verbs |
  |---|---|---|
  | LDPlayer | `dnconsole.exe` (next to the player exe) | `list2`, `launch --index N`, `reboot --index N`, `quitall` |
  | MuMu | `MuMuManager.exe` | `info -v all`, `control -v N launch`, `control -v N shutdown` |
  | AVD / Android Emulator | `emulator.exe` | `-list-avds`, `@<avd>`, `-no-window` |
  | Genymotion | `gmtool` | `admin list`, `admin start` |

- **Recovery order when `adb devices` goes empty.** Do these in order; the first two are the ones
  people skip:

  1. `adb kill-server && adb start-server` — clears a wedged host daemon.
  2. Re-run `adb devices`. If still empty, check whether the **emulator process is actually alive**
     (`tasklist` / `ps`). A running process with **no listening port** means the VM never finished
     booting its adb bridge — restarting the *device* is the only fix.
  3. Restart the instance through the vendor console (`reboot --index N`). Restarting via the
     player binary's "launch" verb frequently leaves you with a process and still no adb.
  4. Only then consider that something is wrong with the host.

  Symptom worth memorising: **the emulator process exists but nothing is listening on the adb
  port.** Distinguishing "not running" from "running but not booted" is what makes step 2 worth
  doing — they have different fixes and only one of them needs the GUI.

- **Root is a per-vendor setting, not a given.** Most emulators expose it as a toggle in their
  settings ("root permission" / "ROOT 权限"); some ship a separate rooted image. Always verify
  rather than assume:

  ```bash
  adb -s <serial> shell "su -c id"     # want: uid=0(root)
  ```

  A rooted emulator is usually the fastest environment for everything in this skill, which makes it
  easy to forget that it is also the *least representative* one.

- **Running two instances.** Different serials make two emulators genuinely disjoint, which is
  useful for holding a clean control (original build, untouched state) alongside your workbench.
  Keep them labelled, always pass `--serial`, and **do not run the same experiment on both** — the
  value of a second device is independence, and duplicating work destroys it. Operate one at a
  time; the other is a reference point, not extra throughput.

- **Apps can detect the emulator** and change behaviour or refuse to run. If the app behaves
  differently here than on hardware, that is a finding about the emulator, not about the app. Note
  it and move the question to a real device.

## Which architecture is actually executing

Device selection and architecture are the same question. `getprop ro.product.cpu.abi` reports what
the device claims; it does **not** report what is executing. Read `native-and-so.md` §Cross-architecture
before you choose which library to patch, and `scripts/lib_map.py` to see the live truth.

## Install / reinstall

```bash
adb -s <serial> shell "su -c 'pm uninstall <pkg>'"
adb push out.apk /data/local/tmp/x.apk
adb -s <serial> shell "su -c 'pm install -r -t -d /data/local/tmp/x.apk'"
```
- `-r` reinstall (keep data, same signing key) · `-t` allow test-only · `-d` allow downgrade
- Different signing key than the installed app → must uninstall first (data is lost)
- Vendor installers may reject `adb install`; pushing + `su -c pm install` usually works

**After reinstalling:** if you restored a data directory, fix ownership, or the app crashes in a DB-init path:
```bash
su -c "chown -R <uid>:<uid> /data/user/0/<pkg>"
su -c "restorecon -R /data/user/0/<pkg>"
```
`<uid>` from `dumpsys package <pkg> | grep userId=`.

## Driving the UI from adb

Automated UI interaction is where verification loops usually break, and most of the breakage looks like a bug in your script. Most of it is not.

### `input tap` may simply not work on a given control

On some OEM ROMs `input tap <x> <y>` is silently ignored for certain controls while working fine for others at neighboring coordinates. **Do not conclude that your automation is wrong.** Before doubting the script:

```bash
adb -s <serial> shell "su -c 'uiautomator dump /sdcard/ui.xml'"
adb -s <serial> pull /sdcard/ui.xml
# bounds="[x1,y1][x2,y2]" -> tap the center: ((x1+x2)/2, (y1+y2)/2)
adb -s <serial> shell "su -c 'input tap <cx> <cy>'"
```

If the control still does not react, bypass the UI path entirely — `am start -n <app.package>/<activity>`, or invoke the logic from Frida. A finished task needs the *code path*, not the tap.

`input` requires `INJECT_EVENTS`, which the plain `shell` user does not have. An unprivileged `input` **fails silently** — no error, no effect. Always wrap it: `su -c 'input tap ...'`.

`input text` additionally mangles or drops non-ASCII input. For CJK text, either install an ADB-driven helper IME or set the field from a runtime call rather than typing.

### Look at the screen — do not drive and wait blind

The most expensive habit in device work is: tap a coordinate, sleep, tap again, sleep, conclude
something about the app. A screen that is *looked at* answers in one step what coordinate-guessing
cannot answer in five — the layout shifted, a different dialog came up, a countdown is frozen, the
button is disabled, the text on screen says exactly why.

**Treat a look as a routine step, not a debugging last resort.** Capture:

- **immediately before** anything time-dependent, so you know the starting state;
- **during** a wait, at intervals — state changes are the information, and a single sample at the end
  cannot distinguish "it progressed" from "it never moved";
- **at every decision point**, before choosing the next action;
- **on any surprise**, before forming a theory about it.

`scripts/snap.py` does this with sane bounds, and tells you which kind of evidence you actually got:

```bash
python scripts/snap.py --out shots --tag before
python scripts/snap.py --out shots --tag waiting --count 6 --interval 3
```

**Use the stall detector.** If consecutive samples are byte-identical, nothing is happening and more
waiting cannot help. Stop, and go find out why — that is a different investigation from waiting
longer.

### Two kinds of screen evidence, and which one is trustworthy here

| Evidence | What it gives you | When it is the right one |
|---|---|---|
| **the image** | exactly what is rendered: layout, which dialog, disabled states, drawn text | always available; the **only** evidence for runtime-drawn UI |
| **the control tree** (`uiautomator dump`) | precise `bounds`, exact text, diffable | only when it actually has content |

The tree is more convenient *when it exists* — it gives you tap coordinates and text you can diff. But
**verify it has content before planning around it**:

```bash
adb -s <serial> shell "su -c 'uiautomator dump /sdcard/ui.xml'"
adb -s <serial> pull /sdcard/ui.xml
grep -c '<node' ui.xml          # 0 nodes -> the tree is useless for this screen
```

**A runtime-rendered UI frequently exposes no real controls at all.** Cross-platform runtimes, web
views and canvas-drawn surfaces often produce an empty (or text-free) tree, which is why a plan built
on "read the bounds out of the XML" stalls on exactly those apps — and also why tapping a control that
"should be there" silently does nothing. When the tree is empty, the image is the **primary** evidence,
not a fallback, and you read it directly rather than trying to derive coordinates from a tree that does
not exist.

`screencap` itself returns a 0-byte file on some ROMs. Write on-device and pull instead:

```bash
adb -s <serial> shell "su -c 'screencap -p /sdcard/x.png'" && adb -s <serial> pull /sdcard/x.png
```

If that is also empty, do not fight it — but note that **a 0-byte capture is not evidence the screen is
blank** (`pitfalls.md` P20). And if `uiautomator dump` fails with `could not get idle state`, retry once;
a paused animation is usually the cause.

### Verify form input by reading it back

Filling a form and tapping submit is **not** a verified interaction. Read the actual field contents and lengths back first:

```bash
adb -s <serial> shell "su -c 'input text <value>'"       # no literal spaces; %s encodes one
adb -s <serial> shell "su -c 'uiautomator dump /sdcard/ui.xml'"
adb -s <serial> pull /sdcard/ui.xml
grep -o 'text="[^"]*"' ui.xml                            # every populated field
```

A whole class of "the button does nothing" is really a local validation rejecting the input — two password fields of different length, a required field empty, a format check. The app returns **before** issuing any request, so a network probe stays silent and the tap looks broken. Compare the lengths you read back, fix the input, retry.

### ROM background freezing kills your hooks

Aggressive ROMs freeze backgrounded apps; the logcat signature is a process state transition `state: R -> F` (running to frozen). Once frozen, hooks stop firing and network calls stop, which looks exactly like a broken probe.

```bash
adb -s <serial> shell "su -c 'dumpsys deviceidle whitelist +<app.package>'"
adb -s <serial> shell "su -c 'cmd appops set <app.package> RUN_IN_BACKGROUND allow'"
```

While debugging, **do not press HOME** — backgrounding the app is what triggers the freeze. Return to it with `am start -n <app.package>/<activity>` and keep it in the foreground for the whole session.

## Signal extraction (what to actually read)

```bash
adb -s <serial> logcat -c                                  # clear before the run
adb -s <serial> shell "am start -n <pkg>/<activity>"
adb -s <serial> logcat -d -v brief | grep -E '<pkg>|FATAL|VerifyError|IncompatibleClassChange|uncaughtException'
```

Failure signatures worth memorizing:

| Log line | Likely cause |
|---|---|
| `FATAL EXCEPTION` + Java stack | App-level crash — read the stack |
| `VerifyError` / `IncompatibleClassChangeError` | Damaged dex (round-trip or bad rewrite) → `pitfalls.md` P3 |
| `Failure starting process` (no stack, by `ActivityManager`) | ART refused the dex, or device state is broken → `pitfalls.md` P4, P9 |
| `ClassNotFoundException: <App.Application>` | Dex rejected wholesale (ordering / structure) → `pitfalls.md` P2 |
| `uncaughtException` with **no stack**, right after launch | A crash-reporter SDK swallowed it. Check whether the process is gone, and look for the SDK's own log file under the app's data dir |
| App alive but nothing rendered | A swallowed exception in the UI path; hunt the crash-reporter's log file |

**Crash-reporter SDKs hide your stack traces.** When an app installs a global uncaught-exception handler (友盟/UCrash/Bugly etc.), the Java stack never reaches `logcat` — only a line like `uncaughtException time: ...`. Three ways to get the stack:
1. **Frida**, hooking `Thread.setDefaultUncaughtExceptionHandler` or the handler class (most reliable).
2. **Race the reporter's log file**: it writes a file under `<app data>/<sdk>/...` then uploads and deletes it. Poll it every ~0.2 s from the device shell and copy on sight:
   ```bash
   while [ $i -lt 400 ]; do
     for f in <dir>/*.log; do [ -f "$f" ] && cp -f "$f" /data/local/tmp/capture.log; done
     i=$((i+1)); sleep 0.2
   done
   ```
3. Run a build with the reporter disabled (not always possible).

## Determinism

Before concluding anything from a failure: **reboot the device and retry**, and **run a control build with zero patches**. A surprising share of "my patch broke it" turns out to be device state (`pitfalls.md` P9).
