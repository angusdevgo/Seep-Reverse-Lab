# Extension verification — split APK / App Bundle sets

Covers the pass that added split-set support to `scripts/repack.py` and wrote
`references/split-apk.md`. Strength labels as defined in this directory's README:
**observed** (exact command + output reproduced here), **inferred** (follows from observed
facts, step not executed), **unverified** (assumed or externally reported, not independently
confirmed).

Reference environment for this pass: Windows 11 host, Python 3.14.0, Java 17.0.4.1
(`keytool` NOT on PATH — it was passed explicitly as
`<jdk>/bin/keytool.exe`), `apksigner` 0.9 run from `lib/apksigner.jar`, `zipalign.exe` from the
same build-tools layout. **No `uber-apk-signer` anywhere on the machine**, which is the condition
that made the signing-route fallback a requirement rather than a nicety. Target: one rooted physical
Android 11 (API 30) arm64-v8a device, written `<DEVICE>` throughout.

All package names, application directory names and file names are replaced with placeholders
(`<PKG>`, `<SET>`, `<SET_A>`, `<SET_B>`). The measurements, byte counts, entry counts and outputs
are unchanged; only the identifiers are.

Fixtures: two **real split sets already installed on the device**, copied out read-only
(`adb pull` of the system directory; nothing on the device was uninstalled, replaced or modified).
They were chosen because one exercises each side of the merge/resign decision:

| | Members | Shape |
|---|---|---|
| Set A | 8 | base + 7 density splits, every density split carrying its own resources |
| Set B | 9 | base + 1 ABI split (native libraries only) + 7 density splits that carry a placeholder table and nothing else |

Neither set is third-party: `pm list packages -3` reported **zero** split sets among ~40 installed
third-party packages, while four preinstalled Google components were split. That distribution is
recorded because "pick a third-party split app off the device" is not reliably available.

## 1. Reading a set: what the members actually contain — observed

`pm path <PKG>` on each package returned one line per member (8 and 9 lines respectively), which is
how the targets were identified in the first place:

```
$ adb shell 'pm path <PKG>'
package:/system/priv-app/<DIR>/<SET>.apk
package:/system/priv-app/<DIR>/<SET>-arm64_v8a.apk
package:/system/priv-app/<DIR>/<SET>-hdpi.apk
... (one line per member)
```

`scripts/repack.py --split-mode analyze` over set A (identifiers replaced):

```
== split set: 8 apk(s), 6629510 bytes total
  density    <SET_A>-hdpi.apk                        49623 B  split=config.hdpi        res=39 entries arsc=9392
  density    <SET_A>-ldpi.apk                        45501 B  split=config.ldpi        res=39 entries arsc=9392
  density    <SET_A>-mdpi.apk                        45501 B  split=config.mdpi        res=39 entries arsc=9392
  density    <SET_A>-tvdpi.apk                       74227 B  split=config.tvdpi       res=78 entries arsc=15124
  density    <SET_A>-xhdpi.apk                       53754 B  split=config.xhdpi       res=39 entries arsc=9432
  density    <SET_A>-xxhdpi.apk                      57878 B  split=config.xxhdpi      res=39 entries arsc=10324
  density    <SET_A>-xxxhdpi.apk                     57876 B  split=config.xxxhdpi     res=39 entries arsc=11200
  base       <SET_A>.apk                           6245150 B  split=-                  dex=classes.dex res=581 entries arsc=1924488 assets=1
[plan] base = <SET_A>.apk (package=<PKG>)
[plan] MERGE BLOCKED: merging is not legal for 7 of 7 splits: config.hdpi, config.ldpi, config.mdpi,
config.tvdpi, config.xhdpi, config.xxhdpi, config.xxxhdpi carry their own resources, and folding those in
means merging resources.arsc (a resource-compiler job). Use --split-mode resign, or pass
--drop-split-resources to accept losing exactly those resources
[plan] resign = legal: one keystore for all 8 members, install the set with
[result] analyze only: nothing was written. Pass --split-mode merge|resign|auto to act on this set.
```

And over set B:

```
== split set: 9 apk(s), 1411272 bytes total
  abi        <SET_B>-arm64_v8a.apk                  255861 B  split=config.arm64_v8a   libs=arm64-v8a
  density    <SET_B>-hdpi.apk                        16797 B  split=config.hdpi        arsc=40
  ... (6 more density members, all 16797 B, all arsc=40)
  base       <SET_B>.apk                           1037832 B  split=-                  dex=classes.dex res=2 entries arsc=71316 assets=1
[plan] base = <SET_B>.apk (package=<PKG>)
[plan] note: every non-base split carries only code/native libraries, so a merged single APK is legal
[plan] note: config.arm64_v8a provides libs for arm64-v8a -- keep only the ABIs the target device runs,
selected with --abi
[plan] merge  = legal: 8 member(s) fold into the base
```

Four facts this pass established with those numbers, and that the reference file now depends on:

- **The ABI member carries no `resources.arsc` at all** (set B: `libs=arm64-v8a`, no arsc column).
  Its two `.so` files are the whole payload. This is the member that folds cleanly.
- **Each density member carries its own table and its own `res/` entries** (set A: 39-78 entries,
  9.0-15.1 KB tables). `resources.arsc` is per member, not per set — the base's 1.88 MB table does
  not contain the density variants.
- **A `resources.arsc` can be a 40-byte placeholder.** All seven density members of set B carry
  `arsc=40` and zero `res/` entries, while still being legally required to carry a table. A
  "has an arsc → owns resources" test would have blocked a merge that is entirely legal here, which
  is why the script's test is *`res/` entries or a table over 1 KB*.
- **Base and split share one package name**, read from the binary AXML `package` attribute of every
  member, and the base is identifiable as the member whose manifest carries **no `split` attribute**
  (set A: `split=-`).

## 2. Unified re-signing — observed

`--split-mode resign` over set A with one keystore, run through the new `apksigner` route:

```
$ python skills/apk-reverse/scripts/repack.py --split-dir <SET_A>/ --split-mode resign \
    --split-out-dir signed_set/ --ks key.jks \
    --keytool <jdk>/bin/keytool.exe --apksigner <build-tools>/lib/apksigner.jar \
    --zipalign <build-tools>/zipalign.exe
[resign] signer route: apksigner
[resign] <SET_A>-hdpi.apk -> signed_set/<SET_A>-hdpi.apk (41298 bytes)
[resign] <SET_A>-ldpi.apk -> signed_set/<SET_A>-ldpi.apk (37202 bytes)
[resign] <SET_A>-mdpi.apk -> signed_set/<SET_A>-mdpi.apk (37202 bytes)
[resign] <SET_A>-tvdpi.apk -> signed_set/<SET_A>-tvdpi.apk (61642 bytes)
[resign] <SET_A>-xhdpi.apk -> signed_set/<SET_A>-xhdpi.apk (41337 bytes)
[resign] <SET_A>-xxhdpi.apk -> signed_set/<SET_A>-xxhdpi.apk (49563 bytes)
[resign] <SET_A>-xxxhdpi.apk -> signed_set/<SET_A>-xxxhdpi.apk (49577 bytes)
[resign] <SET_A>.apk -> signed_set/<SET_A>.apk (4172089 bytes)
[result] OK: 8 members, one certificate (sha256 1eb31d9c…2c44)
```

Every member's independent `apksigner verify --print-certs --verbose --min-sdk-version 21
--max-sdk-version 34` returned `Verifies` with:

```
Verified using v1 scheme (JAR signing): true
Verified using v2 scheme (APK Signature Scheme v2): true
Verified using v3 scheme (APK Signature Scheme v3): true
Signer #1 certificate DN: CN=apkreverse, OU=dev, O=dev, L=NA, ST=NA, C=NA
Signer #1 certificate SHA-256 digest: 1eb31d9c9c81104367a66a0201125aa91d28a6a09eb1dcb5029c36bc0bde2c44
```

All eight printed the **same** SHA-256 — that, not per-file `Verifies`, is the acceptance
criterion for a set, and it is the check the run performs explicitly.

**The signing-route fallback is the load-bearing part of this section.** With no
`uber-apk-signer` on the machine, the pre-change script could not sign anything at all: it exited
with `signer jar not found`, naming a jar the user never had. The new `--signer auto` resolves to
`zipalign -p -f 4` + `apksigner sign --v1 --v2 --v3`, which produced the output above. `--apksigner`
accepts `apksigner.bat` (verified: `rc=0`, `--version` → `0.9`), a `lib/apksigner.jar` value run
through `java -jar` (verified: same), and the extensionless shell wrapper (which is a shell script
and does not run on Windows — that is a fact about the wrapper, not about this script).

### The signing route this pass actually used — and why it had to change

`uber-apk-signer` is `repack.py`'s default signer, and it is **not installed on this machine**
(no `uber-apk-signer.jar`, `APK_SIGNER_JAR` unset). Before this change that made every signed build
impossible here: the script exited with `signer jar not found` and named a jar the user never had.
What actually ran in all four measured routes:

| Item | Value used |
|---|---|
| signer | `zipalign.exe` + `apksigner`, the latter run from `lib/apksigner.jar` through `java -jar` |
| `--apksigner` | `<build-tools>/lib/apksigner.jar`. A `.bat` value was also tested and works (`rc=0`, `--version` → `0.9`); the extensionless wrapper in the same layout is a shell script and does not run on Windows |
| `--zipalign` | `<build-tools>/zipalign.exe` |
| `--keytool` | `<jdk>/bin/keytool.exe` — **not on PATH**, and signing aborts without a way to create the keystore, so this flag is mandatory on such a machine |
| scheme flags | `--v1-signing-enabled true --v2-signing-enabled true --v3-signing-enabled true` |

Alignment is handled **per member, and in this order**:

1. the script writes the archive itself, keeping `AndroidManifest.xml` and `resources.arsc` STORED
   and 4-byte-aligning `resources.arsc` plus uncompressed `lib/**`, then re-reads the file and
   prints the gate (`== alignment gate: resources.arsc STORED and 4-byte aligned (OK)`);
2. `zipalign -p -f 4` runs over that output (`-p` adds the page alignment the loader wants for
   `extractNativeLibs="false"` libraries);
3. `apksigner sign` runs **last** — it adds signature entries without reshuffling the archive,
   whereas a `jarsigner`-style rewrite after aligning destroys the alignment and the install is then
   refused with `[-124]`.

For a split set this is repeated for every member, which is why `resign_split_set()` de-signs and
re-aligns each member individually before signing it: a single member whose `resources.arsc` is
compressed or unaligned is refused by the installer on its own, and the resulting error names that
member's package rather than the set.

## 3. Merging — observed, including the refusal

Set B, where every non-base member is code or native libraries:

```
$ python skills/apk-reverse/scripts/repack.py --split-dir <SET_B>/ --split-mode merge \
    --out merged.apk --abi arm64-v8a --ks key.jks --apksigner <...>/lib/apksigner.jar
[merge] + lib/arm64-v8a/lib<name>_compat_libc++.so  (18944 bytes <- <SET_B>-arm64_v8a.apk)
[merge] + lib/arm64-v8a/lib<name>utilsjni.so       (206680 bytes <- <SET_B>-arm64_v8a.apk)
[merge] folded: dex=0 libs=2 assets=0 conflicts=0
[merge] DROPPED 7 entry/ies. This is a DOWNGRADED build -- say so when you deliver it:
[zip]   classes.dex 872160 bytes method=8 crc=<...>
[zip]   resources.arsc                           STORED                 offset=0x581fc    aligned
== alignment gate: resources.arsc STORED and 4-byte aligned (OK)
[sign:zipalign] rc=0
[sign:apksigner] rc=0
[out] merged.apk (603824 bytes)
[verify:apksigner] rc=0  Verifies / v1 true / v2 true / v3 true
[result] OK
```

`dex=0` is correct rather than suspicious: the base owns `classes.dex` and no member of this set
carries a second one, so no renumbering was needed. The `libs=2` fold is the whole point — a
one-file APK that now carries the native libraries the ABI member used to provide separately.

Set A, where merging is **not** legal, refuses rather than producing a broken artifact:

```
$ python skills/apk-reverse/scripts/repack.py --split-dir <SET_A>/ --split-mode merge \
    --out merged.apk --no-sign
error: refusing to merge <SET_A>-hdpi.apk -- it carries its own resources (39 res entries,
arsc=9392 bytes).
  Folding it in would require merging resources.arsc, which this script does not do.
  Either use --split-mode resign (recommended for a resource split), or pass
  --drop-split-resources to accept that the resources it owns are lost.
exit code 1
```

This is the enforcement the reference file promises: the refusal happens **before** any output is
written (the `--out` path does not exist afterwards), and the escape hatch is explicit, printed, and
required. The mechanism is **observed**; whether a build produced through that hatch merely loses
its density variants or misrenders is **inferred** — it was not exercised, because the only sets
available were a legal-merge set and a refused set, and manufacturing the third case would have
meant hand-editing a resource table.

## 4. Single-APK behaviour is unchanged — observed

Both pre-existing paths were re-run through the same new signing route, on an unmodified sample
APK from `tools/_work/bench/apks/`:

- **zero-change roundtrip** (`--apk … --out … --ks …`, no `--dexdir`): the run dropped exactly the
  three original signature artifacts (`META-INF/CERT.RSA`, `META-INF/CERT.SF`, `META-INF/MANIFEST.MF`),
  wrote a 60964-byte unsigned archive, signed to 70647 bytes, reported `== alignment gate:
  resources.arsc STORED and 4-byte aligned (OK)` and `[result] OK` with v1/v2/v3 all `true`;
- **explicit dex replacement** (`--dexdir` supplying the same `classes.dex`, 5528 bytes):
  `[repl] classes.dex<-…/classes.dex`, the entry re-added at the same size and CRC, alignment gate
  OK, `[result] OK`.

Both were run with `--no-sign` as well, which exits 0 and reports `UNSIGNED (--no-sign)`. `--help`
works, exits 0, and carries the split examples and the route-decision text; `--split-mode analyze`
exits 0; a merge refusal exits 1; a failed verification would exit 2.

The output fix worth recording: `AndroidManifest.xml` used to be printed as `NOT ALIGNED` in the zip
layout (it only has to be STORED, unlike `resources.arsc`). It now prints `-` for entries that need
no alignment, so the report cannot be misread as a failing gate.

## 5. Install and launch on the device — **unverified**

**Not executed.** The device was held by a concurrent device experiment for the whole window
available to this pass (`python tools/_work/devlock.py status` reported the lock held by another
teammate for 1417 s, note naming its own install/launch and Frida work), and the lead's decision was
to ship this gap labelled rather than wait for it. Heavy device work must be serialised
(`tools/_work/ENV.md`), so the honest label for everything below is **unverified** — a claim about
installability that was never installed is exactly the failure `references/verification.md` exists
to prevent.

Prepared, and not run — the sequence is the one in `references/split-apk.md` §4, against the
re-signed renamed fixture:

```
adb install-multiple -r <signed_set>/*.apk
adb shell cmd package resolve-activity --brief <PKG>
adb shell am start -n <PKG>/<launcher-activity>
adb shell 'dumpsys activity activities | grep -m2 ResumedActivity'
adb exec-out screencap -p > launch.png
```

What the pass *did* establish without a device, and what each fact does not cover:

- **The artifacts are installable in principle, not in fact.** All eight members of the re-signed set
  verify with v1/v2/v3 `true` and one identical SHA-256 (§2), and the merged single APK verifies the
  same way (§3, §4). Uniformity of the certificate and a passing `apksigner verify` are necessary
  conditions for a set install; the platform installer accepting the set is the step that was not run.
- **The negative control was not run either.** The signature-conflict text quoted in
  `references/split-apk.md` §6 (a pulled set reinstalled under its own package name) is the
  platform's documented shape and the shape a competing tool reports; no captured output from
  `<DEVICE>` backs it.
- Every statement about **what the archives contain** — split roles, arsc ownership, the 40-byte
  placeholder tables, the fold set, the refusal — is **observed** and device-independent.
- Every statement about **what the package manager does with them** is **inferred**.

**What closing it needs:** one device window that is not shared, then the sequence above (about three
minutes of device time). The two things most likely to show up there, and already accounted for in
the script: an OEM installer interception on `adb install-multiple` (there is a root
`pm install-multiple` path for it) and a launcher activity that needs resolving rather than guessing.

## 6. Maintenance gate — observed

Run at the repository root with the change in place:

```
$ python check_repo.py
== result: 1 problem(s)
  - skills/apk-reverse/scripts/dex_strpatch.py --help crashed:

$ python check_refs.py
== section references: 242 reachable ==
== result: 0 dangling, 0 warning(s)
```

`check_refs.py` is clean, which covers the three `references/repack-and-sign.md` §-references the new
file adds, and `check_repo.py` reports one problem in a **different** file belonging to a different
task; `repack.py` parses and answers `--help` with exit 0.

`check_repo.py` requires every `references/*.md` to be named in `SKILL.md` or the root `README.md`,
and this task was not permitted to edit either, so the reachability step was pre-checked in a **copy**
of the repository (`tools/_work/repo-check/`, workbench only, never in the tree) by running the gate
twice on one snapshot with the index lines as the only variable:

```
without the index lines:  == result: 5 problem(s)   ... UNLISTED references/split-apk.md
with the index lines:     == result: 4 problem(s)   ... (the UNLISTED line is gone)
```

The new file therefore contributes nothing to the gate once listed. The listing itself was added to
`README.md` by the lead, and the run quoted above is the result.

## 7. Deliberately not done — and what stays unverified

- **No `.aab` was processed.** A bundle input would need `bundletool` (absent here, and it is the
  tool that owns the correct resource merge). This pass only ever handled maps of an *installed* set.
- **No fixture was hand-built with `aapt2`/`d8`.** Those became available on this machine only after
  the fixtures were chosen (a build-tools archive was unpacked late in the round), and the two real
  sets already exercised both branches of the decision. Building a minimal split set by hand remains
  the cheapest way to reproduce this topic on a machine with no installed bundle and no device, and
  the route is **inferred** — it was not attempted here. It would not change the resource-merge
  boundary either: `aapt2 link` merges resources when it *builds* an APK from sources, not when it is
  handed two finished ones.
- **No resource merge was implemented or attempted**, by design
  (`references/split-apk.md` §5). The consequence is that a bundle whose resources live in splits
  cannot be reduced to one faithful APK by anything in this repository.
- **`apktool` was not exercised, because it is not usable on this machine.** Measured:
  `apktool.bat d …` fails with `Error: Unable to access jarfile <missing-path>`, while
  `lib/apksigner.jar` and `zipalign.exe` in the same layout work. Any manifest edit that needs
  `apktool` is therefore **unverified** here, and AXML attributes are read-only in this pass (the
  script parses the string pool and the root element's attributes; nothing writes AXML).
- **Feature splits (`isFeatureSplit`) were not measured.** Neither available set has one. The
  handling of `isFeatureSplit` / `configForSplit` in the reference file is **inferred** from the
  platform's documented semantics plus the fact that both attributes are readable through the same
  AXML reader that was verified against real manifests.
- **Split APKs that are not App-Bundle-derived** (the older per-density `-hdpi.apk` naming style,
  or an OEM's own module set) were not available; both sets here use the standard `config.<qualifier>`
  split names, and the reader accepts either because it reads the manifest attribute rather than the
  file name.
- **A XAPK/APKS archive** (a store bundle of bundles, usually a zip holding the split set plus
  `manifest.json`) was not processed. The script's `--split-dir` recursion handles a *directory* of
  APKs, so an unpacked XAPK works; the archive itself is not read.
