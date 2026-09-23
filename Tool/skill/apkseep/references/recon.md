# Recon — build the picture before touching anything

Ten minutes here prevents hours of wrong work. Answer the five questions from `SKILL.md` with concrete evidence.


**Load this when:** starting any new sample. It gives identity, packer detection, embedded SDKs, ABI, and where the app's own code lives -- the ten minutes that prevent hours of wrong work.

## 1. Identity

```bash
# Without a full decompiler (fast, works everywhere):
aapt dump badging app.apk | head -20
# or, from the extracted manifest:
#   package name, versionName, versionCode, sdkVersion, targetSdkVersion
# or, if you have ddc (no JVM, single binary, also gives the launcher):
ddc info app.apk
```

Record: package name, version name/code, min/target SDK, all requested permissions, all declared components.

**Do not hand-parse the package name out of the binary manifest as your primary
source.** Real AXML string tables are full of class-name fragments that look
exactly like package names — in one sample, the strings visible without a real
parser suggested `com.<app>.offline` (a service class prefix) while the actual
package was `com.<vendor>.app`. Every later `pm list packages`,
`dumpsys package`, `/data/data/<pkg>` and `pm install` command depends on this
value, so getting it wrong sends the whole recon down a path where nothing is
found and the natural conclusion is "the tool is broken".

Cross-check two independent sources and require agreement:

- `ddc info app.apk` → `package`, `label`, `launcher`
- `aapt2 dump badging app.apk | head -1` (or `aapt dump badging`)

If they disagree, resolve it before proceeding. A single `label` value is also
worth having: it is what appears on the launcher, which makes device-side
identification unambiguous later.

**Note:** some `aapt` builds choke on non-ASCII paths. Normalize sample paths to ASCII before running tooling.

## 1b. Snapshot the config surface early

If the app has a remote-config endpoint, its DTOs are the cheapest thing in the
package to find, because data classes serialise their own field names into strings
that survive R8:

```bash
ddc findrefs app.apk string "SplashConfig"       # or Config, Popup, Banner, Tabbar...
ddc strings app.apk -f "enabled" --with-locations
```

Do this during recon rather than later: it tells you immediately whether the
launch screen, popups and tab set are **client decisions** or **server data**,
which is the difference between a five-minute patch and a dead end. See
`server-config-and-updates.md`.

## 2. Is it packed?

Read `AndroidManifest.xml` → `application android:name`.

| What you see | Meaning |
|---|---|
| The app's own class (e.g. `com.example.app.App`) | **No packer.** Dex is directly editable. |
| A vendor class (`com.stub.StubApp`, `com.secneo...`, `com.tencent.StubShell`, `s.h.e.l.l.*`, `com.nagain.*`, …) | **Packed.** Unpack first. |
| A short meaningless name that does not match the app's package (e.g. `com.bc41`), plus `android:appComponentFactory` pointing at another short class | **Dex-level whole-APK packer.** The shell registers its own Application/proxy under names unrelated to the app. |
| `classes.dex` is only tens of KB and holds nothing but shell classes | The real code is not on disk. |
| A shell library in `lib/<abi>/` (`libDexHelper.so`, `libjiagu*.so`, `libshell*.so`, …) | Native half of the shell: decrypts and loads the payload. |
| One or more large high-entropy `assets/` blobs, possibly **disguised as JPEG** (valid magic bytes, no decodable image) | Encrypted payload. |
| `assets/` contains a second `.apk` or `.jar` | Wrapped/loader build. |

**A clean shape is also a result: record it and move on.** An app whose
`application android:name` is its own class, with a single plain `classes.dex` and
no native libraries, is directly editable — and that finding is what lets you skip
the entire packer/unpack branch of this skill. It is worth one explicit line in the
record ("no packer: application is the app's own class; dex readable; no lib/") so
that later steps cannot re-open a question that was already answered. Most real
targets are this shape; the packer material in this repository exists for the rest.

Decide from sizes and structure, not from names:

```bash
unzip -l app.apk | sort -k1 -n | tail -20   # biggest entries: assets? libs? dex?
```

**Loaded-shell check (highest fidelity):** if the app runs and its own classes are reachable, it is unpacked *at runtime* regardless of what the manifest says. If the app's own code is not among the dex classes, it is packed on disk.

### Unpacking a dex-level packer

**1. Map payload → dumped dex by length.** If the shell uses **length-preserving** encryption, each encrypted `assets/` payload has **exactly the same byte count as the plaintext dex** it decrypts to. That equality is the strongest single discriminator for "which dump is a real original dex" — far more reliable than sorting dumps by size. Measure it per file before trusting any dump.

**2. Check how the real dex is loaded.** A log line like `InMemoryDexFile[cookie=[0, ...]]` means the dex is built in memory from the payload and never written to disk, so there is no dropped file to find. Use a **memory-scanning** dumper (`frida-dexdump`, or your own script walking the class loaders) instead of hunting for artifacts under the app's data directory. See `references/dynamic-frida.md`.

**3. Two dumper caveats that cost real time.**
- `-D <device-id>` does **not** accept a remote device (`Device '<id>' not found`). Register a remote device with `-H <host>:<port>`; keep `-D` for local/USB ids.
- The `-o <dir>` output directory **must already exist** — the tool does not create it. Otherwise every dex write fails and the run still ends with `All done`, which reads exactly like a successful dump of nothing. `mkdir -p out` first, and judge the result by the file count, never by the final message.

**4. Filter the dumps before using any of them.** A memory dump contains three kinds of garbage:
- **Duplicate copies of one dex.** Identical byte count does **not** imply identical content — files of the same size have been measured to differ in ~73% of their bytes, carry a different dex version, and fail to parse. Dedupe by **content hash**, never by size.
- **SDK plugin dexes downloaded at runtime**, which were never part of the APK.
- **Structurally broken dexes** whose header and body disagree.

Cheap header check that catches the third class, plus the hash used for the first:

```python
import struct, hashlib
d = open(p, 'rb').read()
assert d[:4] == b'dex\n'                                # magic
assert struct.unpack_from('<I', d, 32)[0] == len(d)     # file_size == actual size
assert struct.unpack_from('<I', d, 36)[0] == 112        # header_size
sha = hashlib.sha256(d).hexdigest()
```

Then confirm survivors actually parse (`baksmali`/dexlib2) or load on device. Header consistency alone is not proof of a usable dex.

**5. Which dump is the app's own business dex.** Count string-feature hits per dump instead of trusting file order:

```bash
python scripts/dex_strings.py <dump_dir> --find 'Lcom/example/app/' --per-file
python scripts/dex_strings.py <dump_dir> --find 'Lcom/example/adsdk/' --per-file
```

Heuristic: the business dex mixes the app's package prefix (hundreds of hits) with an ad-SDK prefix (thousands of hits). A pure SDK plugin dex has one vendor prefix at its maximum count and **zero** app-package hits. Zero app-package hits means it is not the app.

## 3. Where does the app's own code live?

| Indicator | Code location |
|---|---|
| Plain `classes*.dex`, app classes visible in them | **Dex** — patchable with dexlib2/smali |
| `libflutter.so` + `libapp.so` | **Flutter (Dart AOT)** — dex contains only a thin shell |
| `libil2cpp.so` + `assets/bin/Data/` | **Unity (IL2CPP)** — native |
| `libmono*.so` + `assets/bin/Data/Managed/` | **Unity (Mono)** — managed DLLs under `assets/` |
| `libreactnativejni.so` + `assets/index.android.bundle` | **React Native** — JS bundle under `assets/` |
| `libhermes.so` | **Hermes bytecode** |
| Almost everything in `.so` | **Native** — different toolchain entirely |

For a **Kotlin/Java app**, note the module layout: app code often lives in a small subset of dex files while large SDKs occupy the rest. Finding which dex holds the app's package is a huge time-saver:

```bash
python scripts/dex_strings.py <dex_dir> --find 'Lcom/example/app/' --per-file
```

Consequence for editing: you usually only need to replace **one or two dex files**, which keeps the repack minimal. When the app is packed, run this check against the **dumped** dexes, not the ones on disk ().

## 4. SDK and library inventory

Extract strings across all dex and group by vendor markers. This reveals ads, analytics, crash reporting, attribution, and any anti-tamper SDK, in one pass.

```bash
python scripts/dex_strings.py <dex_dir> --urls
python scripts/dex_strings.py <dex_dir> --find 'anythink|openadsdk|com.qq.e|umeng|bugly|crashsdk'
```

What to look for:

- **Ad networks / aggregators**: `openadsdk` `TTAdSdk` `Pangle` `com.qq.e` `GDTAd` `anythink` `ATSDK` `ksad` `mobads` `sigmob` `bdxadsdk`
- **Analytics / crash / attribution**: `umeng` `bugly` `crashsdk` `appsflyer` `adjust` `UMCrash`
- **Identity / device id**: `oaid` `msa` `SupplementaryDID` `freemme`
- **Anti-tamper / root / hook detection**: `libsgcore` `libInno` `libqmcheat`, strings like `frida` `xposed` `magisk` `substrate`, `/system/xbin/su`
- **Media stack**: `libmpv` `libavcodec` `libplayer` `libgdx`

Important distinction: **a vendor marker in the string table does not mean the app uses that feature**. Presence of `xposed`/`frida` strings is often just an SDK's own detection list. Decide based on *behavior*, not on strings (`references/verification.md`).

## 5. Signature and tamper checks

Search the app's **own** packages only (ignore third-party SDKs) for:

- `getPackageInfo`, `PackageInfo`, `signatures`, `GET_SIGNATURES`, `Signature` → app-side signature verification
- hardcoded SHA-1/SHA-256 hex constants, base64 license blobs → certificate pinning to the original signer
- `checkSignature`, `verifySignature`, `signCheck` → a named check

**Beware false positives.** `SignatureCheck` and `verifySignature` exist inside `okhttp3` (`SuppressSignatureCheck`, `BasicCertificateChainCleaner.verifySignature`) — TLS plumbing, not app tamper checks. Likewise a native `lib*.so` named like a security library may be an ad SDK's payload decryptor, not a shell.

Confirm by checking whether **app code** references it. If the only callers are library-internal, it is not your problem.

## 6. API surface

```bash
python scripts/dex_strings.py <dex_dir> --urls
```

Collect: base URLs, DoH/DoT lookups, path constants, CDN hosts, custom headers.

Treat **unique** strings as navigation aids — they can often be searched byte-wise in the dex to find the owning class (see `references/dex-patching.md` §finding-the-call-site).

Two patterns worth recognizing early:
- **Dynamic gateway**: the real API host is fetched at runtime (e.g. via a DNS TXT record over DoH). The hardcoded host in dex may be only a fallback. This affects server-side analysis, not patching.
- **Minimal headers / no request signing**: if auth is just `Authorization: Bearer` plus a static app-name header, then a repackaged client is not distinguishable to the server by request signature — which matters for `references/server-api.md`.

## Recon output

Write a short profile before patching. Minimum:

```
package / version / ABI
packed? (evidence)
if packed: packer family, unpack method, kept dumps + sha256
code location (dex / flutter / native)
app code in which dex files
ad SDK(s) and the app's wrapper class
analytics/crash SDKs
anti-tamper: present? where? app-side or library-internal?
API base + notable endpoints
device plan (rooted real device / emulator / static only)
```
