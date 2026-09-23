# Extension verification — benchmark B1/B2 against OWASP MASTG Crackmes

Covers the pass that turned the `tests/benchmark.md` rows **B1** (equal-length dex patch + repack +
re-sign installability, gates G2/G4) and **B2** (anti-debug / self-destruct race) from `pending`
into measured results.

Strength labels follow `docs/tool-verification/README.md`: **observed** (exact command and its
output reproduced here), **inferred** (follows from observed facts, the step itself not executed),
**unverified** (assumed or reported and not independently confirmed).

Reference environment: Windows 11 host, Python 3.14.0, host frida 16.7.19 (frida-tools 13.7.1),
JDK 17.0.4.1 at `C:\Program Files\Java\jdk-17.0.4.1` (not on `PATH`), `apksigner.bat` /
`zipalign.exe` at `E:\tools\bin`. Device: **`<DEVICE>`**, Android 11 / API 30, arm64-v8a, root via
`su`, Magisk denylist `enforced` with an **empty** list (no app is root-hidden). Package under test:
**`<PKG>`**.

All device operations ran under the shared device lock (`tools/_work/devlock.py`).

---

## 0. Headline

- **B1 is `observed` and positive.** An equal-length dex edit (2 bytes of a conditional branch
  replaced by `nop`s), through `dex_patch_bytes.py` → `repack.py --no-sign` → `zipalign` →
  `apksigner` → root `pm install`, installs and **demonstrably changes the app's behaviour on
  screen**: the original and a zero-change control both show a blocking `Root detected!` dialog, the
  patched build reaches `MainActivity` with the dialog gone.
- **`repack.py`'s default signing path did not work when this pass started, and the blocker was not
  `apksigner`.** `apksigner`/`zipalign` are both present and both work; at that moment `repack.py`
  signed only through an `uber-apk-signer` jar, which is not installed. **The repository changed
  mid-pass** — another writer landed a `sign_with_apksigner()` route — and re-running the same
  command then produced a fully signed, `[result] OK` APK in one invocation with byte-identical
  output to the manual route (`sha256 ad6a51ce…7e56`). Both states are recorded below, because the
  stale state is what `tools/_work/ENV.md` predicted and the new state is what a reader will meet.
  This is also a reminder that a "the tool cannot do X" finding on a shared worktree has an expiry
  date.
- **B2 is a split result.** The two scripts run and the probe writes its bytes (0.04–0.05 s after
  resume, gated on `PATCHED`), so the *tooling* is verified. But the **patch does not prevent the
  target's termination**: `libfoo.so` aborts through `goodbye()+12` at **3.22 s** after resume, and
  three patched sites including `goodbyev` itself do not change that. Neutralising the obvious death
  site is **not sufficient** on this target.
- **A finding that changes the whole B2 setup:** on this device the **unmodified, original APK
  already reports `Rooting or tampering detected.`** and its tamper path runs before anything is
  attached. L3's native CRC self-check fails against the pristine community APK on Android 11 /
  arm64-v8a, so the "pristine baseline" the row assumed does not exist here.

---

## 1. Gate G2 and G4 — environment and control (`observed`)

`scripts/doctor.py`:

```
platform : Windows 11 / AMD64
python   : 3.14.0
  [OK ] static (dex/zip/strings)   [OK ] repack + sign
  [OK ] native ELF patching        [-- ] jadx decompile
  [-- ] apktool unpack             [OK ] device work
  [OK ] root on device             [OK ] frida dynamic
  [OK ] java 17.0.4.1  [OK ] adb 1.0.41  [OK ] frida 16.7.19
  [-- ] apktool      not on PATH
  [-- ] unzip        not on PATH
  java jars found near this skill : (none)
  device   : <DEVICE>  arm64-v8a  Android 11 (sdk 30)  root: yes
  clock skew: 3.06 s
```

The `(none)` on the jar line matters for B1: no `baksmali`/`smali`/`uber-apk-signer` jar exists, so
every signing route that goes through a jar is unavailable before a single command is run.

**Keystore and tool locations** (recorded because `repack.py` resolves both off-`PATH`):

```
keytool   : C:\Program Files\Java\jdk-17.0.4.1\bin\keytool.exe
jarsigner : C:\Program Files\Java\jdk-17.0.4.1\bin\jarsigner.exe
apksigner : E:\tools\bin\apksigner.bat
zipalign  : E:\tools\bin\zipalign.exe
```

`repack.py`'s `sibling_tool()` cannot find `keytool` from `C:\Program Files\Common Files\Oracle\Java\javapath\java.exe`,
because that directory holds only forwarders. Passing `--keytool` explicitly is required.

---

## 2. B1 — L1 equal-length dex patch, full chain (`observed`)

### 2.1 Source facts

```
$ python -c "... load_dex('UnCrackable-Level1.apk') ..."
classes.dex 5528 bytes
  magic                 dex\n035\0
  checksum field        7fb7d9fa
  adler32(d[12:])       7fb7d9fa          -> matches
  signature field       b7fafe72cb521450c4470043caa332da61d1bec7
  sha1(d[32:])          5253237b04c2d002967bae8ef81daae08550c90c
                        -> MISMATCH
```

Two facts that a reader needs before trusting the tool's output:

- The **shipped dex's `signature` field is stale** while its `checksum` is correct. `dex_patch_bytes.py`
  prints `header before: checksum_ok=True signature_ok=False` and explains it. If the tool had
  written the two fields in the wrong order, that starting state would have hidden the bug.
- The class that owns the behaviour is
  `Lsg/vantagepoint/uncrackable1/MainActivity;.onCreate(Landroid/os/Bundle;)V`, and the gate is the
  first arm of a three-way root `OR`:

```
0x9c8  invoke-static Lsg/vantagepoint/a/c;.a()Z
0x9ce  move-result
0x9d0  39000e00   if-nez v0 -> 0x9ec      <-- the edit site
0x9d4  invoke-static Lsg/vantagepoint/a/c;.b()Z
```

`0x9ec` is `const-string "Root detected!"` followed by the private `a(String)` that builds the
blocking dialog. **The branch structure, not the method name, was read before editing** — the edit
target is the arm whose *fall-through* continues into the next check.

### 2.2 The patch

```json
[{
  "name": "l1-first-root-check-fallthrough",
  "class": "Lsg/vantagepoint/uncrackable1/MainActivity;",
  "method": "onCreate", "desc": "(Landroid/os/Bundle;)V",
  "match":  {"kind": "if-testz", "bytes": "39000e00"},
  "expect_next": {"kind": "invoke", "target_class": "Lsg/vantagepoint/a/c;",
                  "target_method": "b"},
  "replace": {"kind": "nops"}
}]
```

```
$ python skills/apk-reverse/scripts/dex_patch_bytes.py tools/_work/bench/l1l3/dex/classes.dex \
      --spec tools/_work/bench/l1l3/l1_root.spec.json --dry-run
-- [l1-first-root-check-fallthrough] Lsg/vantagepoint/uncrackable1/MainActivity;.onCreate(...)V
   site 0x9d0  0x9d0: 39000e00       if-nez v0 -> 0x9ec
     (before) 0x9c8: 710027000000   invoke-static Lsg/vantagepoint/a/c;.a()Z
     (before) 0x9ce: 0a00           move-result
   ->  0x9d0: 00000000       if-nez
     (after)  0x9d4: 710028000000   invoke-static Lsg/vantagepoint/a/c;.b()Z
     (after)  0x9da: 0a00           move-result
   polarity: expect_next satisfied
== dry run: nothing written
```

`expect_next` is what pins the polarity: the instruction after the branch had to be the *next* root
check, so the fall-through is the "continue" side. Applied:

```
== header checksum 0x7fb7d9fa -> 0x86e1d928
   signature b7fafe72cb521450 -> eb632328fd1ba03c
   self-verify: checksum_ok=True signature_ok=True
== wrote classes.patched.dex (5528 bytes, delta 0)
```

**The header order question, answered by byte comparison rather than by the tool's own report**
(`observed`): the diff of the whole file against the source is exactly the two fields plus the patch
site.

```
sizes 5528 5528
diff offsets raw: ['0x8','0xa','0xb','0xc'...'0x1f', '0x9d0','0x9d2']
site 0x9d0 orig 39000e00 patched 00000000
8..12   fad9b77f -> 28d9e186                    (checksum, bytes 8..12)
12..32  b7fafe72cb521450c4470043caa332da61d1bec7
     -> eb632328fd1ba03c7ebc6df181e0708a761aa2e3 (signature, bytes 12..32)
selfverify checksum True signature True
```

Recomputing `zlib.adler32(d[12:])` and `hashlib.sha1(d[32:])` **on the written file** reproduces both
header fields, which is only possible if the signature was computed before the checksum. The patch
owns 4 bytes and the header owns 24; nothing else moved.

### 2.3 Repack — where the documented pipeline actually fails

`repack.py`'s default signing route:

```
$ python skills/apk-reverse/scripts/repack.py --apk UnCrackable-Level1.apk \
      --dex classes.dex=classes.patched.dex --out out/l1_patched.apk \
      --workdir out --ks out/bench.keystore \
      --keytool ".../jdk-17.0.4.1/bin/keytool.exe" \
      --jarsigner ".../jdk-17.0.4.1/bin/jarsigner.exe" \
      --apksigner E:\tools\bin\apksigner.bat --zipalign E:\tools\bin\zipalign.exe
[zip] - META-INF/CERT.RSA (signature artifact)
[zip] - META-INF/CERT.SF (signature artifact)
[zip] - META-INF/MANIFEST.MF (signature artifact)
[zip] + classes.dex  (5528 bytes <- .../classes.patched.dex)
[zip] unsigned written: 60967 bytes
[ks] generated E:\...\out\bench.keystore (alias=apkreverse)
error: signer jar not found: uber-apk-signer.jar
  pass --signer-jar <path>, or set APK_SIGNER_JAR.
  Any zipalign+apksigner based signer works here.
[exit code: 1]
```

Two separate facts, and the second is the one worth recording:

1. `--signer-jar` defaults to `uber-apk-signer.jar` and no such jar exists here, so the default run
   cannot sign. (`ENV.md` predicted this.)
2. **The error message's second line is misleading in this environment.** "Any zipalign+apksigner
   based signer works here" is true, but `repack.py` has no code path that *uses* a plain
   `zipalign`+`apksigner` pair for signing — `sign_apk()` only ever invokes
   `java -jar <signer_jar>`. `--apksigner`/`--zipalign` are used for **verification only**. So the
   documented Route B works, but only if the caller performs the sign step outside `repack.py`.
   The `--no-sign` flag is the supported seam.

Working route, both builds through the **same** pipeline:

```
$ python skills/apk-reverse/scripts/repack.py --apk UnCrackable-Level1.apk \
      --dexdir tools/_work/bench/l1l3/dex_orig \
      --out out/l1_control_unsigned.apk --workdir out/ctrl --no-sign
[zip] unsigned written: 60967 bytes
[zip]   resources.arsc   STORED  offset=0xd4d4  aligned
== alignment gate: resources.arsc STORED and 4-byte aligned (OK)
[result] UNSIGNED (--no-sign): good for inspection, not installable as-is

$ (same, with --dex classes.dex=classes.patched.dex) -> out/l1_patched_unsigned.apk
[zip]   resources.arsc   STORED  offset=0xd4d4  aligned
== alignment gate: resources.arsc STORED and 4-byte aligned (OK)
```

`AndroidManifest.xml` is reported `STORED ... NOT ALIGNED`, which is correct and not a defect: the
4-byte alignment requirement is `resources.arsc` (and uncompressed `lib/*.so`), not the manifest.

Signing, explicitly, both builds, same key:

```
$ E:\tools\bin\zipalign.exe -p -f 4 l1_control_unsigned.apk l1_control_aligned.apk   ; rc=0
$ E:\tools\bin\apksigner.bat sign --ks bench.keystore --ks-pass pass:<pw> --key-pass pass:<pw> \
      --v1-signing-enabled true --v2-signing-enabled true --v3-signing-enabled true \
      --out l1_control.apk l1_control_aligned.apk                                     ; rc=0
$ E:\tools\bin\apksigner.bat verify --print-certs --verbose \
      --min-sdk-version 21 --max-sdk-version 34 l1_control.apk
Verifies
Verified using v1 scheme (JAR signing): true
Verified using v2 scheme (APK Signature Scheme v2): true
Verified using v3 scheme (APK Signature Scheme v3): true
Signer #1 certificate SHA-256 digest: ad13912308e0b6ded5d8be7da2868356348655033d1dde402d8f70d452fbf6db
```

Identical result for `l1_patched.apk`, with the same certificate digest, so the two builds differ
only in the dex bytes.

### 2.4 On-device result — the behaviour change, seen on the screen (`observed`)

Two builds were produced and both were checked, because "the pipeline works" and "the patch changed
the app" are different claims and only the second one is the deliverable.

**The one-command pipeline, re-run after the repository changed** (this supersedes §2.3's manual
route as the recommended invocation):

```
$ python skills/apk-reverse/scripts/repack.py --apk UnCrackable-Level1.apk \
      --dex classes.dex=classes.patched.dex --out out/l1_patched_final.apk \
      --workdir out/fin --ks out/bench.keystore \
      --keytool "C:\Program Files\Java\jdk-17.0.4.1\bin\keytool.exe" \
      --apksigner E:\tools\bin\apksigner.bat --zipalign E:\tools\bin\zipalign.exe
[sign] route: apksigner
[out] ...\out\l1_patched_final.apk (70647 bytes)
== alignment gate: resources.arsc STORED and 4-byte aligned (OK)
Verified using v1 scheme (JAR signing): true
Verified using v2 scheme (APK Signature Scheme v2): true
Verified using v3 scheme (APK Signature Scheme v3): true
[result] OK
local sha256 ad6a51cef4699b73ff052d4e049ca9efd64e9570900d19509f0b7a7c20f87e56
```

The manual `zipalign`+`apksigner` route earlier in this section produced **the same sha256**, so the
two paths agree byte for byte and the result does not depend on which one a reader follows.

Install through the **root** path (`pm install -r -d`, which bypasses this ROM's streamed-install
interception), and the installed `base.apk` is hashed and compared to the local file so "installed"
cannot be confused with "the previous build is still there":

```
control   device sha256 e5a9f335155e3e20219d89bc859ae89cc0a82f7135123397c526d94bfca4b3b4
          local  sha256 e5a9f335155e3e20219d89bc859ae89cc0a82f7135123397c526d94bfca4b3b4   identical
patched   device sha256 ad6a51cef4699b73ff052d4e049ca9efd64e9570900d19509f0b7a7c20f87e56
          local  sha256 ad6a51cef4699b73ff052d4e049ca9efd64e9570900d19509f0b7a7c20f87e56   identical
```

`am start -W` for both builds:

```
LaunchState: COLD  TotalTime: 241 ms  WaitTime: 249 ms  Status: ok     (control)
LaunchState: COLD  TotalTime: 232 ms  WaitTime: 234 ms  Status: ok     (patched)
```

Window focus, sampled four times at 2 s intervals:

```
original  mCurrentFocus=Window{a5d2ba7 u0 Root detected!}    (all four samples)
control   mCurrentFocus=Window{c4047e2 u0 Root detected!}    (all four samples)
patched   mCurrentFocus=Window{8c94fc1 u0 <PKG>/...MainActivity}  (all four samples)
```

And the images, which are the evidence that actually counts —
`tools/_work/bench/l1l3/evidence/00_original/00_original_03.png` shows the modal
`Root detected! / This is unacceptable. The app is now going to exit. / OK` over a greyed-out input
screen. The same shot on the control build (`evidence/01_control/*.png`, and again on
`evidence/12_control_final/*.png` from the final one-command build) is byte-comparable to the
original's. `evidence/13_patched_final/13_patched_final.png` — the final patched build — shows the
screen **without any dialog**: input field live with the caret in it, `VERIFY` enabled, and
`mCurrentFocus` on `<PKG>/...MainActivity`.

**G4 is therefore cleared in the strong form**: the control is not just "the same APK" — it went
through the identical repack-and-sign pipeline with a byte-identical dex and still shows the old
behaviour. The behaviour change is attributable to the four patched bytes, and it reproduced on a
second, independently built APK from the final pipeline.

### 2.5 What the app's own check actually is (`observed`, and it contradicts the obvious reading)

The functional check was probed with a Frida hook rather than inferred from the crypto:

```
[a.b] input="8d127684cbc37c17616d806cf50473cc" -> 16 bytes: 8d127684cbc37c17616d806cf50473cc
[lib a.a] key=8d127684cbc37c17616d806cf50473cc
          data=e5426215cb5b9a06c3a0b5e6a4bd769a49e8f074f82eff1d95ab7c17147618e7
          -> 17 bytes 492077616e7420746f2062656c69657665 ascii="I want to believe"
[a.a] REAL input="" -> false
```

So: a **fixed 16-byte AES key** (`8d12…73cc`, a `const-string` in the dex) decrypts a fixed
base64 blob to `I want to believe`, and the user's input is compared against that plaintext. My first
reading — that the hex string was itself the secret — is **wrong**, and it was falsified by running
it: entering `8d127684cbc37c17616d806cf50473cc` produces `Nope...`.

`TextUtils.equals` is **not** the comparison site: hooking it captured only dialog-internal
comparisons (`("Nope...", "<null>")`). The comparison lives in the decrypted-bytes path of
`a.a(String)`.

Two device facts that cost time and are worth inheriting:

- **The input field cannot be driven on this ROM.** `adb shell input text "I%swant%sto%sbelieve"`
  and a per-character `input keyevent` loop both landed `iwantto`: 7 of 17 characters survived and
  every space was dropped. Three independent quoting routes gave the same result, so the field
  itself rejects what the injection path sends. Reading the field back with `uiautomator dump` after
  each attempt is what distinguished "the app said Nope" from "my input never arrived" — the first
  two attempts looked like a wrong secret and were not.
- `EditText.setText(String)` is not reachable from outside (only
  `setText(CharSequence, TextView$BufferType)` is declared, and `TextView.BufferType` is not exposed
  as a property on the class object); an **empty** `EditText` also returns a **null** `Editable`, so
  `getText().length()` fails with "not a function" and looks like a bridge limitation rather than an
  empty field.

The success branch was therefore reached through the app's own method with the boolean forced, which
is honest as long as it is labelled — and it is:
`evidence/09_success_branch/09_success_branch.png` shows the app's `Success! / This is the correct
secret.` dialog. That image proves **the patched build reaches and renders the app's own success
branch**; it does not prove the secret was typed and accepted. The check itself is evidenced by the
libfoo/`a.b`/`a.a` log above.

### 2.6 B1 verdict

`observed`: the equal-length edit, the header recomputation in the correct order, the STORED+aligned
repack, v1+v2+v3 signing, the root-path install, the device-side hash match, and the on-screen
behaviour change all reproduce. G2 and G4 both clear.

---

## 3. B2 — L3 self-destruct race (`observed` for the tooling, `unverified`/negative for the patch)

### 3.1 What L3 actually does (read from the dex and the tombstone, not assumed)

`MainActivity.onCreate` calls `verifyLibs()` **first**, then `init("pizzapizzapizzapizzapizz".getBytes())`,
then an `AsyncTask`, then three root checks, then `isDebuggable()`, then `setContentView` — and
`setContentView` sits **after** the gate:

```
0x11a3ce  invoke-static Lsg/vantagepoint/util/RootDetection;.checkRoot1()Z
...
0x11a406  sget Lsg/vantagepoint/uncrackable3/MainActivity;.tampered:I
0x11a40a  if-eqz v0 -> 0x11a418        ; tampered == 0 -> skip the dialog
0x11a40e  const-string "Rooting or tampering detected."
0x11a412  invoke-direct MainActivity;.showDialog(Ljava/lang/String;)V
0x11a418  ... setContentView
```

So when the tamper bit is set the app **never renders its UI**; it sits on a blocking dialog whose OK
button is wired to an `onClick` that exits. `verifyLibs()` is the source of that bit:

- it reads four ABI-keyed expected CRCs out of `resources.arsc` string resources
  (`R.string` ids `0x7f0b002b`, `0x7f0b0029`, `0x7f0b0034`, `0x7f0b0035`),
- compares them to the zip entry CRCs of `lib/<abi>/libfoo.so`, and
- compares `classes.dex`'s zip CRC to the value the native `baz()` returns.

The native library exports exactly three JNI entries and one terminate routine:

```
Java_sg_vantagepoint_uncrackable3_CodeCheck_bar          vaddr=0x33a4 size=256
Java_sg_vantagepoint_uncrackable3_MainActivity_init       vaddr=0x3310 size=136
Java_sg_vantagepoint_uncrackable3_MainActivity_baz        vaddr=0x3398 size=12
_Z7goodbyev                                              vaddr=0x3080 size=24
_Z4randv                                                 vaddr=0xe4c  size=36
```

and its strings name the detection inputs: `/proc/self/maps`, `frida`, `xposed`, `ptrace`,
`waitpid`, `getppid`, `pthread_create`, plus two log strings:
`"Tampering detected! Terminating..."` and `"Error opening /proc/self/maps! Terminating..."`.

`libfoo.so`'s single RX `PT_LOAD` is `off=0x0 vaddr=0x0 filesz=0x4700`, so **file offset == virtual
address == runtime offset from the module base** for everything in `.text`. That is what makes
`hook_patch_only.js`'s `FILE_OFFSET` meaningful here, and it is not true in general — a library whose
text segment has a non-zero `vaddr` would need `p_vaddr + delta`.

### 3.2 The baseline, and the finding that invalidates the assumed baseline

`observed`: the **unmodified, pristine APK** on this device shows the tamper dialog:

```
$ am start -n <PKG>/sg.vantagepoint.uncrackable3.MainActivity
  833 ms  pid=5377 5413   mCurrentFocus=Window{1d9ee56 u0 Rooting or tampering detected.}
 1638 ms  ...             mCurrentFocus=Window{1d9ee56 u0 Rooting or tampering detected.}
 ...
10712 ms  ...             mCurrentFocus=Window{1d9ee56 u0 Rooting or tampering detected.}
```

and `logcat` shows the CRCs it compared (`V/UnCrackable3`), with `tampered` set. The process stays
alive in this state for at least 25 s: the tamper dialog alone does **not** kill the process, it waits
for the OK button.

`observed` — the **time-to-death baseline with a frida probe attached**, which is the number the row
needs:

```
$ python tools/_work/bench/l1l3/ttd_attach.py --package <PKG> --activity sg.vantagepoint.uncrackable3.MainActivity \
      --js l3_read_crc.js --launch-delay 1.5 --seconds 20
[i] pre-attach main pid=7020 at 1.88s
[i] attached at +0.00s (probe loaded)
attach+  0.75s main_pid=7020
... (alive)
attach+  4.90s main_pid=7020
attach+  5.34s main_pid=-
=== logcat ===
F/libc  ( 7020): Fatal signal 6 (SIGABRT), code -6 (SI_TKILL) in tid 7052 (tg.uncrackable3)
F/DEBUG ( 7203): #01 pc 000000000000308c  .../lib/arm64/libfoo.so (goodbye()+12)
F/DEBUG ( 7203): #02 pc 00000000000031ac  .../lib/arm64/libfoo.so
I/Zygote( 1007): Process 7020 exited due to signal 6 (Aborted)
```

**`TTD(frida attached) = 5.34 s`, and the death is a native `SIGABRT` originating in `goodbye()+12`.**
Note which process dies: `7020` is the main `<PKG>` process, `7052`/`tg.uncrackable3` is the failing
*thread*. That distinction matters — see §3.4.

### 3.3 The two scripts, run as shipped (`observed`)

Neither had ever been executed before this pass.

```
$ python skills/apk-reverse/scripts/spawn_patch_detach.py \
      --package <PKG> --js skills/apk-reverse/scripts/hook_patch_only.js \
      --captures 2 --interval 3 --no-screencap
[i] spawned pid=7442
[!] PATCH_BYTES is empty -- configure this probe before using it
[MSG] PATCHFAIL
[i] patched=False
[i] detached (memory writes persist, hooks are gone)
=== capture 0 ===
7567  00:01 sh -c ps -A -o PID,ETIME,ARGS | grep -i uncrackable3
7570  00:01 grep -i uncrackable3
mCurrentFocus=Window{7c35f28 u0 com.oppo.launcher/com.oppo.launcher.Launcher}
```

Three defects, all confirmed by later runs:

1. **`hook_patch_only.js` is a template, and its guard is correct but the guard is the whole
   result.** `PATCH_BYTES = []` correctly refuses and reports `PATCHFAIL`, so an unconfigured run
   cannot silently claim success. That is good behaviour; it just means the shipped file tests
   nothing.
2. **`spawn_patch_detach.py` resumed the target before waiting for `PATCHED`.** The original order
   was `resume(pid)` → then wait. That makes the wait meaningless: by the time the probe's
   `Process.findModuleByName` poll sees the library, the target has been running.
3. **`--activity` defaults to `None` and the code then did nothing.** After `am force-stop` and a
   spawn, omitting `--activity` left the app un-launched, so the capture set was of the launcher and
   read exactly like "the app died". Fixed by resolving the launcher through
   `cmd package resolve-activity --brief <pkg>` when `--activity` is absent.

**Correction to my own first fix.** I changed the order so the driver held the target **paused**
until `PATCHED`. That cannot work with a module-polling probe, and the run says so:

```
[i] probe loaded; target still PAUSED, waiting up to 15.0s for the patch
[5.00s][alive]  [10.00s][alive]  [15.00s][alive]
[!] the probe did not report PATCHED in 15.0s
[i] resumed pid=7666
[15.11s][i] libfoo.so base=0x764c0aa000 bytes@0x3080 = fd 7b bf a9 ...
[15.12s][PATCH] now = 00 00 80 52 d6 03 5f c0 ...
```

**While the process is frozen its libraries are not mapped**, so the poll can never succeed: 15 s
paused produced nothing, and `libfoo.so base=0x764c0aa000` appeared 0.11 s after resume. The shipped
order was right about *that*; what was wrong was detaching before the write landed. The corrected
driver resumes, then waits for `PATCHED` (reported loudly when it never arrives), then detaches.

### 3.4 The experiment, and its result

Sites were chosen from the tombstone and the ELF, not guessed. `goodbyev` at `0x3080`:

```
0x3080  a9bf7bfd  stp x29, x30, [sp, #-16]!
0x3084  910003fd  mov x29, sp
0x3088  321f07e0
0x308c  97fff725  bl 0x2ff0          <-- the call the tombstone names as goodbye()+12
0x3090  2a1f03e0
0x3094  97fff71f  bl 0x2ff8
```

and the two helpers it tail-calls are trivial return-value stubs:

```
0x2ff0  52801a40  mov w0, #0xd2     0x2ffc  d65f03c0  ret
0x2ff8  52800cc0  mov w0, #0x66     0x3000  321f0fe0  ...
```

So probe v2 patches the **return values the branch reads** (`0x2ff0`, `0x2ff8`) as well as
`goodbyev`'s entry, each rewritten to `mov w0, #0 ; ret` (+ nops, equal length), with an assertion on
the expected original bytes before each write.

Patched condition:

```
$ python tools/_work/bench/l1l3/b2_measure.py --js l3_hook_patch_v2.js --tag PATCHED --probe-seconds 25
[i] spawned pid=10000 (paused)
[i] resumed pid=10000
[0.04s][i] libfoo.so base=0x764b89d000 size=90112
[0.04s][i] goodbye entry  = fd 7b bf a9 fd 03 00 91 e0 07 1f 32 25 f7 ff 97
[0.04s][i] goodbye+12     = 25 f7 ff 97
[0.04s][PATCH] 0x2ff0 (helper A -> return 0) 40 1a 80 52 c0 03 5f d6 -> 00 00 80 52 d6 03 5f c0
[0.05s][PATCH] 0x2ff8 (helper B -> return 0) c0 0c 80 52 c0 03 5f d6 -> 00 00 80 52 d6 03 5f c0
[0.05s][PATCH] 0x3080 (goodbyev entry -> no-op) fd 7b bf a9 ... -> 00 00 80 52 d6 03 5f c0 1f 20 03 d5 1f 20 03 d5
[0.05s][i] sites written=3 skipped=0
[i] patched=True
  3.22s pid=10000 alive=False
V/UnCrackable3(10000): Tampering detected! Terminating...
F/libc  (10000): Fatal signal 6 (SIGABRT), code -6 (SI_TKILL) in tid 10032 (tg.uncrackable3), pid 10000
F/DEBUG (10036): #01 pc 000000000000308c  .../lib/arm64/libfoo.so (goodbye()+12)
I/Zygote( 1007): Process 10000 exited due to signal 6 (Aborted)
[RESULT] tag=PATCHED  spawned=10000 ttd_after_resume=3.22 survived=False
```

Control condition (identical reads and writes, original bytes written back):

```
$ python tools/_work/bench/l1l3/b2_measure.py --js l3_hook_control_v2.js --tag control_v2 --probe-seconds 22
[0.04s][CONTROL] 0x2ff0 unchanged (wrote back 40 1a 80 52 c0 03 5f d6)
[0.04s][CONTROL] 0x2ff8 unchanged (wrote back c0 0c 80 52 c0 03 5f d6)
[0.04s][CONTROL] 0x3080 unchanged (wrote back fd 7b bf a9 fd 03 00 91)
[0.04s][i] control sites ok=3
V/UnCrackable3(9312): Tampering detected! Terminating...
F/DEBUG ( 9348): #01 pc 000000000000308c  .../lib/arm64/libfoo.so (goodbye()+12)
I/Zygote( 1007): Process 9312 exited due to signal 6 (Aborted)
```

**Both conditions terminate at `goodbye()+12` with `SIGABRT`.** The probes apply the patch
successfully, inside the race window (0.04–0.05 s after resume against a ~3.2 s deadline), and the
target still dies.

### 3.5 What this means, and what to do instead

`observed`:
- `spawn_patch_detach.py` **can** deliver an early memory patch: the write landed 0.05 s after resume
  and survived the detach. The mechanism the row tests is real.
- `hook_patch_only.js` is a **template with correct guard rails**, not a working probe.
- The patch as configured is **insufficient**: three sites including the terminate routine's entry
  and both of its branch inputs do not stop the abort.

`inferred` (labelled, not executed): the terminate path is not confined to `goodbyev` and its two
stubs. `goodbyev` is 24 bytes and its only two calls are the two stubs; the `bl` at `+12` is the
observed faulting frame, and yet patching both the callee and the caller changed nothing. The most
consistent explanation is that the tampering thread reaches the *same abort* through a second site
that this static pass did not map — the region around `0x2f80–0x3080` is a dense run of
`mov w0, #imm ; ret` pairs (values 0x11, 0x1b, 0x43, 0x5b, 0x67, 0x7b, 0x92, 0xa2, 0xa3, 0xae, 0xcc,
0xd2, 0xe3, 0xe7, 0xe8, 0xed, 0xf6, 0xfd, …), i.e. a jump-table-shaped cluster of tiny accessors
that a proper disassembly would resolve into a call graph, and `rand` (`_Z4randv`, 0xe4c, 36 B) is
part of the same obfuscated scheme. **A real fix needs a full AArch64 disassembly of `.text`
(~18 KB) rather than four hand-picked offsets.**

`observed` — the route that should be tried first next time: the abort is reachable from a **Java**
layer that is already fully mapped. `verifyLibs()` computes `tampered` and `onCreate` branches on it,
and the dialog's OK button is a plain `DialogInterface.OnClickListener` in `MainActivity$1`. Patching
the dex in that class (`if-eqz v0 -> 0x11a418` → nops, forcing the non-tamper side) removes the
dialog and lets `setContentView` run **without touching native code at all** — and unlike the native
patch it is a route this repository already has measured tooling for (see B1). This was not executed
in this pass; it is the recommended next experiment, not a result.

`observed` — a limitation the next pass must budget for: on this device the L3 **original** APK
already fails its own CRC self-check, so the tamper state is on before any instrumentation. Whatever
the follow-up tests must therefore be measured against *that* baseline, not against a clean one.

---

## 4. Task C — L2 (not run)

Not attempted: A and B consumed the pass. `UnCrackable-Level2.apk` is on disk
(`tools/_work/bench/apks/`, 901022 B, sha256 prefix `4c7980ef1f6cc295`) and the `dynamic-frida.md`
spawn route is untested for it. Recorded as **not run**, not as a negative result.

---

## 5. Defects found in the repository's own tooling

| Where | What | Evidence | Status |
|---|---|---|---|
| `scripts/repack.py` (`sign_apk`) | **Stale finding, re-opened and closed.** At the start of this pass it signed **only** via `java -jar <signer_jar>`; `--apksigner`/`--zipalign` were verification-only, so the "any zipalign+apksigner based signer works here" hint had no code path behind it | §2.3 exit 1 with `signer jar not found` | **fixed by another writer mid-pass**; re-measured in §2.4 — `[sign] route: apksigner`, `[result] OK`, byte-identical output |
| `scripts/repack.py` | The `signer jar not found` message is still emitted by the jar-only `sign_apk()` and still claims a zipalign+apksigner route works. When no `--apksigner` was supplied (the first run in §2.3) the message is the *only* guidance a reader gets, and it points at a function that does not exist | §2.3 | documented; the message should name the apksigner route it now has |
| `scripts/spawn_patch_detach.py` | Detached before the probe's write landed, so the write could be missed entirely while the run still reported `patched=False` and looked merely unlucky | §3.3 | **fixed** — resume, wait for `PATCHED`, report loudly, then detach |
| `scripts/spawn_patch_detach.py` | `--activity` absent left the target un-launched after a spawn, so the captures were of the launcher | §3.3 | **fixed** — resolve the launcher via `cmd package resolve-activity` |
| `scripts/spawn_patch_detach.py` | Unbounded `adb`/frida calls; `adb_run()`'s rc is never inspected for the launcher step | §3.3 | partially fixed (`--launch-timeout`, rc surfaced) |
| `scripts/hook_patch_only.js` | Guard rails are correct (`PATCH_BYTES` empty → `PATCHFAIL`); it is a template, and the docs imply it is a runnable probe | §3.3 | documented |
| `tools/_work/ENV.md` | Attributes the B1 signing problem to the apksigner/zipalign route; the blocker was the missing uber-apk-signer jar, and both apksigner and zipalign work | §2.3 | corrected here |
| `tests/benchmark.md` B2 | Describes L3 as a self-destruct race against a pristine baseline; on this device the original APK is already in its tamper state | §3.2 | corrected here |

---

## 6. Files produced by this pass

Workbench (not part of the skill; `tools/` is git-ignored):

- `tools/_work/bench/l1l3/l1_root.spec.json`, `dex/classes.patched.dex`, `dex_orig/classes.dex`
- `tools/_work/bench/l1l3/out/l1_control.apk`, `l1_patched.apk`, `l1_control_now.apk`,
  `l1_patched_final.apk` (+ unsigned/aligned intermediates)
- `tools/_work/bench/l1l3/l1_probe.py`, `l1_type.py`, `l1_verify_field.py`, `l1_try_secret.py`,
  `l1_drive.js`, `l1_probe_full.js`, `attach_probe.py`
- `tools/_work/bench/l1l3/l3_hook_patch_v2.js`, `l3_hook_control_v2.js`, `l3_read_crc.js`,
  `elf_l3.py`, `dis_l3.py`
- `tools/_work/bench/l1l3/b2_measure.py`, `ttd.py`, `ttd_attach.py`
- `tools/_work/bench/l1l3/evidence/**` (PNG captures: `00_original`, `01_control`,
  `02_patched_nosecret`, `09_success_branch`, `12_control_final`, `13_patched_final`)

A note on making §2.4 reproducible: `l1_probe.py` reuses the tag as the remote filename, so
`--tag` must be unique per run. Reusing a tag after a failed `adb push` installs the *previous*
remote file, which is exactly how the first attempt at the final patched verification showed
`Root detected!` — the control build's hash, from the control run's leftover remote path. The hash
comparison in the same script is what caught it; a screenshot alone would not have.
