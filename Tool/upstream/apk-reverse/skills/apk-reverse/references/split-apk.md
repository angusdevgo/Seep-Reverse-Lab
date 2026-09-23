# Split APKs and App Bundles

A store build is frequently **not one file**. Play and most OEM stores ship App Bundles, and the
device receives a set: `base.apk` plus one `split_config.*.apk` per ABI, screen density and language
(and, for a dynamic-feature bundle, the feature modules as well). Every member carries **the same
package name and its own signature**, and the package manager treats the set as one package.

Two failures follow from treating such a set as an APK, and both look like a broken build when they
are nothing of the kind:

- Signing only the base leaves the set disagreeing about its certificate; the installer rejects the
  whole set and names the package, not the member you forgot.
- "Just merge them into one APK" is free *only* for members that carry code or native libraries. A
  member that carries resources cannot be folded into the base without merging `resources.arsc`,
  which is a resource-compiler job. A wrongly merged archive installs and then renders the wrong
  thing, or dies on the first resource lookup.

`scripts/repack.py` handles both routes and **refuses to guess**: it inventories the set, decides
which route is legal from what the members actually carry, prints the reason, and only then acts.

**Strength labels** (same three this repository uses everywhere): **observed** = reproduced with an
exact command and output; **inferred** = follows from observed facts, step not executed;
**unverified** = reported or assumed, not independently confirmed. The measurements behind this
file are recorded in `references/evidence-summary.md` §The capability matrix.


**Load this when:** the target arrives as `base.apk` plus `split_config.*.apk`, or a rebuild is refused as a set although every member verifies. It gives reading the set, merge versus unified re-signing, and the refusal each mistake produces.

## 1. What the set is

| Member | Manifest `split` attribute | Carries | Foldable into the base? |
|---|---|---|---|
| base | *(absent)* | all `classes*.dex`, the main `resources.arsc`, every resource not moved out, the real `<application>` | — it *is* the base |
| ABI split | `config.arm64_v8a`, `config.armeabi_v7a`, `config.x86_64`, … | `lib/<abi>/*.so` only | **yes** — entry names do not collide |
| density split | `config.hdpi` … `config.xxxhdpi` | its own `resources.arsc` **and** `res/` entries | **no** — requires a resource merge |
| language split | `config.en`, `config.zh`, … | its own `resources.arsc` (strings) | **no** — same reason |
| feature split | `feature_x` (+ `isFeatureSplit="true"`, `configForSplit="base"`) | its own `classes*.dex`, possibly resources | **code only**; its resources hit the same wall |

**Observed** on a real 9-member set pulled from a stock Android 11 device (arm64-v8a target):

- the base carried `classes.dex` (872 KB) and `resources.arsc` (71 KB);
- the ABI member carried two `lib/arm64-v8a/*.so` files and **no `resources.arsc` at all**;
- each density member carried its own `resources.arsc` and its own `res/` entries;
- a second, 8-member set's density members carried 39-78 `res/` entries each and 9-15 KB tables.

So "which member owns the resources" is answerable **from the zip entry list alone** — no device, no
resource compiler, no decompiler. Copy a set to disk and ask.

**A member can own a nearly empty table.** A split is *required* to carry a `resources.arsc`, so a
placeholder one is normal: on the same real set, eight density members carried a **40-byte** table
and no `res/` entries at all — they are placeholders, not resources. Treating "has an arsc" as "owns
resources" would block a merge that is perfectly legal. `repack.py` uses *entries under `res/` or a
table bigger than 1 KB* as the test.

## 2. Getting the set off a device

`pm path` prints **one line per member**; a package with several lines is a split set. This is how
you find one to copy, and it is also how you tell, before anything else, that the thing you are about
to patch is not a single APK:

```bash
adb shell 'pm path <PKG>'
package:/system/priv-app/<DIR>/<APP>.apk
package:/system/priv-app/<DIR>/<APP>-arm64_v8a.apk
package:/system/priv-app/<DIR>/<APP>-xxhdpi.apk
```

To enumerate every split set on a device (toybox shell — no `--time-style`, no bash arrays):

```bash
adb shell 'for p in $(pm list packages | cut -d: -f2); do c=$(pm path $p | wc -l); \
  if [ $c -gt 1 ]; then echo "$c $p"; fi; done'
```

Copy the whole directory out; the members live side by side:

```bash
adb shell 'su -c "ls -la /system/priv-app/<DIR>/"'
adb pull /system/priv-app/<DIR> <dest>/
```

Two traps, both **observed**:

- `adb pull <dir> <dest>` creates `<dest>/<dir>/` — the set arrives one level deeper than you expect.
  `repack.py --split-dir` searches recursively for exactly this reason.
- A **third-party** split set is rare on a stock ROM. On the device measured here, `pm list packages -3`
  returned **zero** split sets among ~40 third-party apps, while four preinstalled Google components
  were split. If you need a real set and the third-party list is empty, that is the normal
  distribution, not a mistake on your side.

**Do not test by reinstalling a pulled set under its own package name.** It is already installed on
that device, owned by the vendor certificate you do not have, so the install fails for a reason that
has nothing to do with your pipeline (). Either work on a set you own, or rename the pulled one
() to get an installable fixture.

## 3. The decision: merge or resign

Run this first — it writes nothing and answers with a reason:

```bash
python skills/apk-reverse/scripts/repack.py --split-dir <set>/ --split-mode analyze
```

| Situation | Route | Why |
|---|---|---|
| Every non-base member carries only code and/or `lib/` (a placeholder `resources.arsc` is fine) | **merge** | nothing that needs a resource table moves |
| Any member carries `res/` entries or a real table | **resign** | a resource merge rewrites the table; see §5 |
| You must keep the build installable **and** the app is distributed as a bundle | **resign** | this is what the store does; the set stays a set |
| You need one file to hand someone, sideload, or feed to a tool that takes an APK | **merge**, if legal | the only way to get a single artifact |
| The delivery must survive store updates, or the ROM's own installer refuses multi-APK installs | **resign** (`pm install-multiple`), or merge and accept a fixed build | — |
| A member declares `isFeatureSplit="true"` and ships `classes*.dex` **and** resources | **resign** | its code could fold, its resources cannot; a half-merged build is worse than either route |

Failure modes, one per route:

- **merge**, when a resource-carrying member is dropped to make it legal: the app starts and shows
  the base's resources. Missing density variants show up as blurry or missing images; missing
  language splits show as untranslated strings. This is a **downgraded** build and has to be
  delivered as one — `repack.py` prints `DROPPED n entry/ies` and refuses unless you pass
  `--drop-split-resources`, so the loss cannot be silent.
- **merge**, when the base still declares `isSplitRequired="true"`: install succeeds and start is
  refused (`INSTALL_FAILED_MISSING_SPLIT`,). The attribute has to be cleared first, and that is a
  binary-AXML edit.
- **resign**, when one member is missed: the set fails as a set, with a signature error naming the
  package. Sign the directory, not a list you typed by hand.
- **resign**, when the target ROM's installer is not the platform installer: `adb install-multiple`
  can be intercepted by an OEM security centre, exactly as single-APK installs are
  (`references/repack-and-sign.md` §Vendor install interception (OEM shells)). Use the root
  `pm install-multiple` path.

## 4. Unified signing — the route that always works

```bash
python skills/apk-reverse/scripts/repack.py \
    --split-dir <set>/ --split-mode resign \
    --split-out-dir <signed_set>/ \
    --ks key.jks --apksigner <path/to/apksigner>
```

Each member is de-signed (only the signature entries), rewritten as a 4-byte-aligned archive, and
signed with **one** keystore and **v1+v2+v3**; the run then verifies every member and prints the
signer fingerprint per file. The acceptance criterion is not "each file verifies" — it is **one
certificate across the whole set**:

```
[result] OK: 8 members, one certificate (sha256 1eb31d9c…2c44)
```

Then install the whole set, base included:

```bash
adb install-multiple -r <signed_set>/*.apk
adb shell "su -c 'pm install-multiple -r /data/local/tmp/set/*.apk'"   # when an OEM installer refuses the multi-APK form
```

**The signature must cover every member**, and `--abi`/density selection happens at install time, not
at signing time — sign them all, let the installer pick (see).

### Toolchain: `uber-apk-signer` is optional, `apksigner` is not

`repack.py`'s original signing route went through `uber-apk-signer` only, so a machine with a full
Android build-tools directory and no uber-apk-signer could not produce a signed build at all. The
script now picks the route itself:

- `--signer jar` — the uber-apk-signer path (used automatically when the jar exists);
- `--signer apksigner` — `zipalign -p -f 4` then `apksigner sign --v1 --v2 --v3`, which is the whole
  of what the jar was doing for us;
- `--signer auto` (default) — jar if present, else apksigner.

`--apksigner` accepts all three shapes a build-tools install ships: `apksigner.bat`, the `apksigner`
shell wrapper, or the bare `lib/apksigner.jar`. **On Windows pass the `.jar` or the `.bat`** — the
extensionless wrapper is a shell script and will not execute. A `.jar` value is run through
`java -jar`, so `--java` (or java on PATH) is required for it.

Order is load-bearing: **align, then sign**. `apksigner` adds signature entries without reshuffling
the archive; the v1 (JAR) path emulates `jarsigner`, whose rewrite of the zip would destroy the
alignment Android R+ requires of `resources.arsc`.

## 5. Merging into a single APK

```bash
python skills/apk-reverse/scripts/repack.py \
    --split-dir <set>/ --split-mode merge --out merged.apk \
    --abi arm64-v8a --ks key.jks --apksigner <path/to/apksigner>
```

What folds: `classes*.dex` (renumbered so a member's `classes.dex` becomes `classes2.dex`, keeping
the base's own dex intact), `lib/**`, `assets/**`. What does not, and why: `res/**` and
`resources.arsc`.

**Why resource merging is not attempted.** `resources.arsc` is an indexed table: a global string
pool plus type-spec and type chunks, with every resource identified by a `(package, type, entry)`
triple and every string referenced by pool offset. Folding a member's table into the base's means
rewriting pool offsets, type/entry counts and the alignment of every string, in both directions —
that is `aapt2 link`, not a byte-level edit. The failure it produces is the worst kind: the archive
is *structurally* valid, installs, and then resolves resource ids to the wrong entries or to nothing.
An APK that renders garbage is harder to diagnose than one that refuses to install.

If you genuinely need one standalone file for a bundle whose resources are split, the honest routes are:

1. **`bundletool build-apks --mode=universal`** (the vendor tool, needs the original `.aab`) — this is
   what merges resources correctly, and it is the only route that does.
2. **Keep the split set** and install it as a set ().
3. **Accept the downgrade** with `--drop-split-resources`, and say so in the delivery.

**Manifest constraints when you do merge — and when you patch any split at all.** These attributes
are the difference between "installs and runs" and an install or start refusal, and they are easy to
miss because they live in binary AXML:

| Attribute | Lives on | Effect if you get it wrong |
|---|---|---|
| `split="config.xxhdpi"` | `<manifest>` of a **split** | Identifies the member. A split whose `package` differs from the base's, or whose `split` name is duplicated, is refused as a set |
| `configForSplit="base"` | `<manifest>` of a split | Ties a configuration split to a feature module. Changing package/module names without updating it silently detaches the split |
| `isFeatureSplit="true"` | `<manifest>` of a feature split | Marks an install-time/on-demand module. A merge that folds code in but leaves the attribute declared describes a member that no longer exists |
| `isSplitRequired="true"` | `<manifest>` of the **base** | The platform refuses to start a base that believes it is incomplete. This is the one that breaks merged builds () |

Read them without a decompiler through `scripts/repack.py`'s own AXML reader (`--split-mode analyze`
prints the `split` name per member; `inspect_apk()` returns `package`, `split`, `configForSplit`,
`isSplitRequired`, `isFeatureSplit`). Changing any of them means editing the binary string pool and
the attribute chunks around it, which is what `apktool` is for — and note that a full
`apktool b` rebuild rewrites the whole archive
(`references/repack-and-sign.md` §Repacking an unpacked (de-shelled) app).

## 6. Install refusals, and what each one means

| Message | What it actually says | Attribution |
|---|---|---|
| `Failure [INSTALL_FAILED_INVALID_APK: ... signatures do not match previously installed version]` / `Package <PKG> signatures do not match` | The set you are installing is signed with a different certificate than the one already on the device | **Not** a malformed build. Either re-sign to the original key, or install to a package name that does not exist yet |
| `Failure [INSTALL_FAILED_ALREADY_EXISTS]` / `INSTALL_FAILED_UPDATE_INCOMPATIBLE` | Same package, different signer (or a downgrade without `-d`) | A pulled system component cannot be reinstalled over itself; see §7 |
| `Failure [INSTALL_FAILED_MISSING_SPLIT: Missing split for <PKG>]` | The base declares `isSplitRequired="true"` and the set is incomplete — or you merged it | The base is telling the truth: it expects members. Clear the attribute, or install the complete set |
| `Failure [INSTALL_FAILED_INVALID_APK: Failed to parse ... split ... has different signature]` | **One member** of the set is signed differently from the rest | This is the failure mode of signing only the base. Sign the whole directory |
| `Failure [-124: ... resources.arsc ... stored uncompressed and aligned on a 4-byte boundary]` | One member's `resources.arsc` is compressed or unaligned | Per-member, not per-set. `repack.py` reports it per member before signing (`references/repack-and-sign.md` §2a) |
| `Failure [-99]`, or a numeric-only code with no `INSTALL_FAILED_*` | An OEM installer interceptor rejected the request | Nothing to do with the set; use the root `pm install-multiple` path |
| `adb install-multiple` on a device that has no `install-multiple` support (very old `pm`) | Install each member with `pm install` in order, base last | Use `pm install-create` / `install-write` / `install-commit` explicitly |

`INSTALL_FAILED_INVALID_APK` in particular is a **family**, not one error: it covers stale
signatures, malformed base/split relationships, and alignment violations. Read the text after the
colon before attributing anything — the constant alone will send you looking at the wrong file.

## 7. Making an installable fixture from a pulled set

**Observed, and the reason this section exists:** a set pulled from the device is installed *on that
device*, under a name owned by the vendor certificate. Re-signed copies cannot be installed back
over it, so "does our signed set install?" cannot be answered with the pulled set as it stands.

The cheap, structure-preserving way out is an **equal-length package rename**: replace every
occurrence of the old package name in `AndroidManifest.xml`, `resources.arsc` and `classes*.dex`
with a new name of exactly the same length. Nothing moves — no length prefix, no string-pool offset,
no dex `string_ids` offset, no resource index — so the only field that must be recomputed is the dex
header's integrity pair (signature first, checksum last, see
`references/repack-and-sign.md` §Repacking an unpacked (de-shelled) app). Then run the ordinary
`--split-mode resign` over the renamed directory and install that.

A detail worth knowing before you touch a manifest: **a member's Java classes need not live under its
manifest `package` at all**. On the real set measured here, the manifest package was
`com.google.android.<name>` while all 677 class references in the dex were
`Lcom/android/<name>/...` — and every `<activity android:name>` was fully qualified. Renaming the
manifest package therefore left every component resolvable, with no dex edit needed. Assume the
opposite (that the two must match), and you will edit a dex for nothing.

## 8. ABI and density matching

The device tells you what it can run:

```bash
adb shell getprop ro.product.cpu.abilist     # e.g. arm64-v8a,armeabi-v7a,armeabi
adb shell getprop ro.product.cpu.abi         # the primary ABI
adb shell getprop ro.product.cpu.abilist32   # 32-bit list, on a 64-bit device
```

Match against the **split name**, not the file name, and mind the separator: split qualifiers use
**underscores** (`config.arm64_v8a`) while `lib/` directories use **hyphens** (`lib/arm64-v8a/`). The
mapping is a substitution, not a lookup — `arm64_v8a` → `arm64-v8a`, `armeabi_v7a` → `armeabi-v7a`;
`x86` and `x86_64` are unchanged. That is why `--abi arm64-v8a` matches a split named
`config.arm64_v8a`.

Four rules that decide ABI questions:

- **A 64-bit device still installs a 32-bit-only set**, and then runs it 32-bit. If the base carries
  no native code and only the `armeabi_v7a` split does, the app is a 32-bit app on that device.
- **The ABI split is selected by the installer, not by `repack.py`.** `--abi` exists for *merging*
  (where the choice is baked into one file); for `--split-mode resign`, sign every member and let
  `pm` pick.
- **Merging without `--abi` folds in every ABI member**, which makes one APK with two or three copies
  of the same library set. Legal, larger, and pointless on a single-device delivery.
- **`getprop` reports what the device claims**; what runs is a live mapping question
  (`scripts/lib_map.py`). A device that reports `arm64-v8a` first can still execute a 32-bit process.

Density is the same shape without the separator trap: `config.xxhdpi` matches
`res/drawable-xxhdpi/`, and the installer picks the closest variant the device's `ro.sf.lcd_density`
can use. There is nothing to select on your side.

## 9. Traps worth paying for once

- **`resources.arsc` belongs to whoever ships it.** In a split set it exists *per member*, and the
  base's table does not contain the density member's entries. Reading the base's table and concluding
  "the resource exists" is wrong; it exists in one configuration only.
- **`android:extractNativeLibs`.** If the base declares `extractNativeLibs="false"` (the default for
  modern targetSdk), the `.so` files are mmapped straight out of the archive, and they must be
  **uncompressed and page-aligned** — this is what `zipalign -p` exists for. Merging native members
  into a base and then writing the archive without that alignment produces an install that succeeds
  and a start that dies in the linker. `repack.py` writes uncompressed `lib/**` 4-byte aligned, and
  `zipalign -p -f 4` adds the page alignment the loader wants for them.
- **A placeholder `resources.arsc` is not a resource split** (). Blocking on "has an arsc" refuses
  legal merges.
- **Do not `zipalign` after signing to "fix" a member.** It rewrites the archive and invalidates the
  signature. Align, then sign.
- **`apktool` may not be usable even when a wrapper exists.** Measured on the pass machine: the
  `apktool.bat` wrapper pointed at a jar that was not on disk
  (`Error: Unable to access jarfile <missing>.jar`), while `apksigner.jar` and `zipalign.exe` in the
  same layout were fine. Check the wrapper's target before planning a manifest edit around it.
- **The AXML `split` attribute is a string-pool entry**, which is why an equal-length rename of it is
  safe and why a length-changing edit is not: the pool's own length prefixes and the attribute chunk
  sizes around it would both need recomputing.

## 10. What this file does not claim

- **It does not merge resources.** No route here reproduces `bundletool build-apks --mode=universal`.
  A bundle whose resources live in splits stays a set, or becomes a downgraded single APK by explicit
  choice.
- **It does not split a monolithic APK back into modules**, and it cannot turn a `.aab` into APKs —
  that is `bundletool`, and the `.aab` is the input it needs.
- **`--split-mode merge` covers code and native libraries only** (). Feature-split *code* folds;
  feature-split *resources* do not.
- The install-failure texts in §6 are the shape the platform produces; **the exact wording varies by
  Android version and by OEM installer**. Read the text after the constant, not the constant.
