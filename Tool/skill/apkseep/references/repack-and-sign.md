# Repack and sign

Rebuilding is the step where otherwise-correct patches die. Two mistakes account for nearly all of it: **stripping `META-INF/`** and **recompressing entries that must stay stored**.


**Load this when:** rebuilding, signing, installing, or a repacked build misbehaves. It gives the two mistakes that account for nearly all failures here, the STORED-and-aligned rule, and every install refusal that looks like a broken build.

## The rules

**1. Strip only signature artifacts, never the whole directory.**

`META-INF/` contains ServiceLoader registrations the app needs at runtime. Details and the exact failure in `references/pitfalls.md` P1.

```python
SIG_EXT = ('.SF', '.RSA', '.DSA', '.EC')
def is_signature_entry(name):
    if not name.upper().startswith('META-INF/'):
        return False
    rest = name[len('META-INF/'):]
    if '/' in rest:                 # keep services/, androidx/, native-image/ ...
        return False
    up = rest.upper()
    return up == 'MANIFEST.MF' or up.endswith(SIG_EXT)
```

**2. `AndroidManifest.xml` and `resources.arsc` must stay uncompressed (STORED).**

Recompressing them produces builds that fail to install or misbehave.

**2a. `resources.arsc` must ALSO be 4-byte aligned, and the failure is an install refusal.**

On Android 11+ (targetSdk 30+) the package manager rejects the install outright:

```
Failure [-124: Failed parse during installPackageLI: Targeting R+ (version 30 and
above) requires the resources.arsc of installed APKs to be stored uncompressed and
aligned on a 4-byte boundary]
```

Two independent requirements hide in that one sentence: STORED, and the entry's
**data offset** divisible by 4. Uncompressed `lib/*.so` follows the same rule.

A naive `zipfile.ZipFile(...).writestr(...)` loop satisfies neither reliably:
Python's zip writer gives you no control over entry offsets. `scripts/repack.py`
therefore emits local headers itself and pads the **local extra field** to reach
the boundary. The padding arithmetic has one trap worth knowing:

> A zip extra area is a sequence of `(id, size, payload)` records, so its minimum
> useful length is 4 bytes. A required pad of **1-3 bytes cannot be expressed**.
> When the natural pad falls in that range, insert a stored filler entry of
> exactly that size instead -- the filler has a computable size, so the following
> entry still lands on the boundary.

Verify by reading the archive, not by trusting the writer: for each entry Android
cares about, parse its local header, compute `header_offset + 30 + namelen +
extralen`, and check `compress_type == 0` and `offset % 4 == 0`.
`repack.py` prints exactly this ("alignment gate") and `check_alignment()`
returns the complaint list programmatically.

**Do not plan on repairing alignment with `zipalign` after the fact when you can
produce a correct archive directly.** A post-hoc pass rewrites the file; on a
target that fingerprints its own byte layout, that is a much larger change surface
than writing it correctly the first time. Keep `zipalign -c -v 4` as an
independent check when the tool is available.

**3. Keep the APK's zip entry metadata.** Preserve `compress_type`, `external_attr`, `date_time` for entries you copy through.

**4. Changing any dex changes nothing about resources.** If you only edited dex, do not touch `res/`, `assets/`, or `lib/`.

**4a. A full `apktool b` rebuild rewrites resource paths even when you edited none.** Decoding with
`apktool d` (without `-s`) and rebuilding re-encodes resources, and obfuscated short names are
expanded back to readable ones — an entry originally shipped as `res/-B.png` comes back as
`res/drawable-hdpi/<real-name>.png`. Expect an entry-level diff against the original to show on the
order of a thousand "removed + added" pairs that are **pure renames**, not content changes.

This is expected and usually harmless, but two consequences matter:

- **Never read that diff as "I broke something".** Compare by identity (rename-aware, or by content
  hash grouped by size) before drawing a conclusion. A toy diff that reports 1100 changes when you
  edited one method is a **tool** artifact and will send you hunting a bug that does not exist.
- **It changes the byte layout of the whole archive.** On a target that fingerprints its own file
  against a stored hash, or whose protection binds offsets into a container, a full rebuild is a much
  larger change surface than a dex-only swap. If your only edit is dex, prefer replacing the
  `classes*.dex` entries inside the original zip (`compress_type` preserved) over a full rebuild.
  Keep that dex-only path as a fallback for exactly this reason.

If you must avoid resource churn entirely, decode with `-s` (do not decode resources) and only
rebuild what you changed.

**5. Signing creates new `MANIFEST.MF`/`*.SF`/`*.RSA`.** That is expected — the check is that **no signature artifact from the ORIGINAL** survives, and **no non-signature entry was lost**.

**6. Any dex you edited must have its header integrity fields recomputed.**
Every dex carries two fields that cover the rest of the file:

```
bytes 12..32 = sha1(data[32:])        # signature — must be computed FIRST
bytes  8..12 = adler32(data[12:])     # checksum — covers the signature, so it is LAST
```

Skipping this does not always stop the app from starting, which is what makes it
dangerous. Android logs
`Failure to verify dex file ...: Bad checksum (computed, expected)` — the real
value appears as "expected", which reads backwards — and then falls back to
interpreting the dex instead of using a verified image. The visible symptom is an
unrelated startup failure such as `ClassNotFoundException` for an ordinary class
(the Application class, or a small AndroidX component), so the trail points at the
APK structure rather than at two stale header words.

`scripts/dexutil.py` exposes `fix_dex_header()` (correct order, plus
`verify_dex_header()` so you can assert the result), and
`scripts/dex_patch_bytes.py` runs both automatically before writing.

**7. `jarsigner` rewrites the archive; `apksigner` does not.**

Adding a v1 JAR signature with `jarsigner` recompresses entries as a side effect,
which **destroys the alignment from rule 2a**. The signature still verifies, so the
build looks correct until the install is refused with `[-124]`. Sign with
`apksigner` (v1+v2+v3) unless you have a specific reason not to.

## Repacking an unpacked (de-shelled) app

When the sample was packed, the dex you are about to patch came out of a memory dump while the APK still carries the shell. Build a **de-shelled base APK** first, then treat it as an ordinary APK for the rest of this document.

1. **Assemble the base.** Start from the original APK: replace `classes*.dex` with the dumped real dexes, and delete the shell library under `lib/<abi>/` plus the encrypted `assets/` payloads. Strip **only** signature artifacts — `META-INF/*.SF|*.RSA|*.DSA|*.EC` and the top-level `MANIFEST.MF`. Never delete the whole `META-INF/` (`references/pitfalls.md` P1).
2. **Decode with `apktool`.** `apktool d base.apk` gives the smali tree and a **readable text manifest**.
3. **Fix the manifest.** Point `application android:name` at the app's real Application class and **remove** `android:appComponentFactory`. Grep the decoded tree for leftover shell class references before building.
4. **Patch, then rebuild.** `apktool b` → `zipalign -p -f 4` → `apksigner` (v1+v2+v3) → install and verify against the checklist at the end of this file.

Why `apktool` rather than editing binary AXML in place: changing `android:name` in binary AXML means hand-editing the string pool and the attribute/chunk sizes around it, and a mis-sized chunk produces an APK that installs but throws far from the edit, typically in component lookup at startup. The text round-trip moves the risk to "did the rebuild preserve everything else", which item 5 of the checklist verifies directly.

## Pipeline

`scripts/repack.py` implements all of the above. Conceptually:

```
open original (zip)
  for each entry:
    skip entries that are signature artifacts (per rule 1)
    skip entries being replaced
    copy through, preserving compression + attributes
  write replacement entries
close
sign (v1 + v2 + v3)
verify
```

Usage:

```bash
python scripts/repack.py --apk original.apk --dexdir extracted_dex_dir --out out.apk
# or replace specific dex files:
python scripts/repack.py --apk original.apk --dexdir extracted_dex_dir \
  --dex "classes7.dex=patched/classes7.dex" \
  --dex "classes8.dex=patched/classes8.dex" \
  --out out.apk
```

`--dexdir` supplies the untouched dex files; `--dex name=path` overrides specific ones.

## Signing

Two viable routes.

**Route A — `uber-apk-signer` (handy, wraps zipalign + apksigner):**
```bash
java -jar uber-apk-signer.jar --apks in.apk --ks ks.jks \
  --ksAlias <alias> --ksPass <pass> --ksKeyPass <pass> -o out_dir
```
Known quirk: `-o` and `--overwrite` are mutually exclusive; passing both errors out. Also, it **silently skips already-signed APKs** (`0 processed`) — so de-sign first.

**Route B — `zipalign` + `apksigner` directly (most explicit):**
```bash
zipalign -p -f 4 unsigned.apk aligned.apk
apksigner sign --ks ks.jks --ks-pass pass:<pass> --key-pass pass:<pass> \
  --v1-signing-enabled true --v2-signing-enabled true --v3-signing-enabled true \
  --out signed.apk aligned.apk
apksigner verify --print-certs --verbose \
  --min-sdk-version 21 --max-sdk-version 34 signed.apk
```

Enable **v1 + v2 + v3**. v1 is needed for older Android; v2/v3 for modern verification.

Generate a keystore once:
```bash
keytool -genkeypair -v -keystore ks.jks -alias <alias> \
  -keyalg RSA -keysize 2048 -validity 36500 \
  -storepass <pass> -keypass <pass> \
  -dname "CN=<name>, OU=dev, O=dev, L=NA, ST=NA, C=NA"
```

## `apksigner verify` picks schemes from the APK's own minSdk

`apksigner verify` decides which signature schemes to check from the APK's own `minSdkVersion`. With `minSdk >= 24` it prints v1/v2 as `false` **by design**, even though `META-INF/*.SF` is present and the signature is valid. That output is indistinguishable from "signing did not apply" and sends you into a re-signing loop over a file that was never wrong.

Always pass the explicit range (Route B above) and read the scheme list from that run only. Never judge a build from a default-argument `apksigner verify`.

## Installing over an existing app

| Situation | Command |
|---|---|
| Same signing key as installed version | `pm install -r` — keeps app data (login state, caches) |
| Different signing key | `pm uninstall` first, then install. **App data is lost** — say so in the delivery notes |
| OEM installer refuses (`INSTALL_FAILED_*`, vendor restrictions, a bare negative code) | push the APK and install via root: `su -c 'pm install -r -d /data/local/tmp/app.apk'` |
| Downgrade needed | add `-d` |
| Test-only flag needed | add `-t` |

Useful detail: keeping the same keystore across builds lets you iterate with `-r` and **preserve a logged-in session**, which matters a lot when the feature you are testing needs auth.

### Vendor install interception (OEM shells)

Some ROMs route `adb install` through their own "security centre", which can return
a bare failure code while the APK itself is fine:

```
Performing Streamed Install
adb.exe: failed to install app.apk: Failure [-99]
```

The device log shows the real actor and reason, and it is not your build:

```
ColorPackageInstallInterceptManager: OPPO_ADB_INSTALL_CANCEL ... packageName=<pkg>
```

**The root path bypasses the interception**, which is why the table above lists it:

```bash
adb -s <serial> push app.apk /data/local/tmp/app.apk
adb -s <serial> shell "su -c 'pm install -r -g -d /data/local/tmp/app.apk'"
```

Recognise the shape: a numeric-only failure with no `INSTALL_FAILED_*` constant, an
APK that installs fine through the device's own UI, and a device process (package
installer / security centre) in the log. Attributing that to the patch is a
classic wasted hour.

### The installer may still own the screen afterwards

After an intercepted or UI-driven install, a vendor **installer confirmation window
can remain the foreground activity indefinitely** — sometimes showing a stale
package name from an unrelated earlier attempt. Consequences:

- `am start` on your app "does nothing", because another window owns the display.
- Screenshots of your supposed launch actually show the installer.
- `am start -W` can block past any reasonable timeout waiting for a first frame
  that will never come.

Clear it (`am force-stop <installer pkg>`, or a HOME key event) and re-launch. Before
trusting any capture, check the foreground component:

```bash
adb -s <serial> shell "dumpsys activity activities | grep -m1 ResumedActivity"
```

If it is not your package, the frames are evidence about something else.
`scripts/coldstart.py --expect-activity` performs this check automatically.

## Post-install / post-upgrade hazards

- **Data directory uid mismatch.** After reinstall the app uid increments; a restored `/data/user/0/<pkg>` directory owned by the old uid is unreadable. Symptom: crash in a DB-init path (`Cannot open database`). Fix:
  ```
  su -c "chown -R <uid>:<uid> /data/user/0/<pkg>"
  su -c "restorecon -R /data/user/0/<pkg>"
  ```
  Get `<uid>` from `dumpsys package <pkg> | grep userId=`.
- **Restoring a data backup can itself cause this.** Prefer `cp -f` over an existing file (preserves owner) rather than deleting and re-extracting.

## Verify the build, not just the signature

Signature verification proves the file is well-formed. It does **not** prove the app works. Always:

1. `apksigner verify` passes with the explicit SDK range above — a default-args run can report v1/v2 `false` on a perfectly valid signature.
2. Install succeeds.
3. Launch succeeds; process stays alive.
4. `logcat` shows no `FATAL EXCEPTION` / `VerifyError` / `IncompatibleClassChangeError` / `uncaughtException`.
5. `META-INF/services/*` count matches the original.
6. Unchanged dex files are byte-identical to the original (compare hashes); in a de-shelled build, compare against the de-shelled base instead.

Build a **control** at least once: same pipeline, zero patches. If the control fails, your pipeline or environment is at fault, not your patch (`references/pitfalls.md` P9).
