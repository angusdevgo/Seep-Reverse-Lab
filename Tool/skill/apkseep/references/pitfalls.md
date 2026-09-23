# Pitfalls — the failure catalogue

Every entry here cost real time and produced a **silently broken artifact**. Skim this before building. When you lose more than thirty minutes to something new, add it here.

Each entry: **symptom → root cause → why it is hard to see → what to do instead.**

---


**Load this when:** before building anything, and again when a failure looks familiar. It is the failure catalogue: symptom, root cause, why it is hard to see, and what to do instead. Skim it; do not read it linearly.

## P1. Stripping the whole `META-INF/` breaks the app at startup

**Symptom**
```
java.lang.IllegalStateException: Module with the Main dispatcher is missing.
Add dependency providing the Main dispatcher, e.g. 'kotlinx-coroutines-android'
```
App dies immediately on launch. Sometimes a different `ClassNotFoundException` for an unrelated library class.

**Root cause**
`META-INF/` is not only signatures. It holds **ServiceLoader registrations** that Android reads at runtime. Deleting the directory to prepare for re-signing deletes them too.

Real examples found in one APK (framework entries first — these are the ones that produce the
confusing `ClassNotFoundException`; note that **third-party libraries register the same way**, so the
list is not limited to well-known frameworks):
```
META-INF/services/kotlinx.coroutines.internal.MainDispatcherFactory  -> kc
META-INF/services/io.ktor.client.engine.HttpClientEngineContainer    -> OkHttpEngineContainer
META-INF/services/io.ktor.serialization.kotlinx.KotlinxSerializationExtensionProvider
META-INF/services/kotlinx.coroutines.CoroutineExceptionHandler       -> wc
META-INF/services/<third-party-package>.<SomeInterface>              -> <impl class>
META-INF/services/<third-party-package>.<SomeListener>               -> <impl class>
```
The last two are the general shape, not a coincidence: a downloader, an HTTP engine, a serialization
provider or a plugin SPI shipped as a library all land here, and any of them can be the one whose
absence kills startup.

**Why it is hard to see**
The error message names Kotlin coroutines, not your repack. You will spend an hour blaming the dex.

**Do instead**
Strip **only** signature artifacts, and only at the top level of `META-INF/`:

```python
SIG = ('MANIFEST.MF',)
SIG_EXT = ('.SF', '.RSA', '.DSA', '.EC')

def is_signature_entry(name):
    if not name.upper().startswith('META-INF/'):
        return False
    rest = name[len('META-INF/'):]
    if '/' in rest:          # services/, androidx/, native-image/ ... keep
        return False
    up = rest.upper()
    return up in SIG or up.endswith(SIG_EXT)
```

`scripts/repack.py` already does this.

---

## P2. Byte-level string patching without an ordering check rejects the whole dex

**Symptom**
App cannot load any class:
```
ClassNotFoundException: Didn't find class "<App.Application>" on path: DexPathList[[zip file ".../base.apk"]]
```
`Application` construction fails, process never starts.

**Root cause**
Dex requires the `string_ids` table to be **sorted**. Replacing a string with an equal-length string keeps all offsets valid, but changes where that entry *should* sit in the sorted order. If the new value crosses its neighbours, the loader rejects the entire dex.

Concrete case: `/app/adverts` sat between `/api/v1/crashtrack/upload?chk=` and `/app/configs/`. Replacing it with `/app/noadver` put `n` after `c` → out of order → whole dex rejected. Replacing with `/app/blocked` (`b < c`) was accepted.

**Why it is hard to see**
`checksum` (adler32) and `signature` (SHA-1) recompute perfectly, so every integrity check passes. `baksmali` parses the file fine. Only the runtime loader cares about ordering.

**Do instead**
Always run the ordering guard: `scripts/dex_strpatch.py` looks up the target's neighbours in `string_ids` and refuses any replacement outside `(prev, next)`. Pick a candidate that stays inside the interval.

---

## P3. Whole-tree smali round-trip damages R8-optimized dex

**Symptom**
App installs, then dies with:
```
java.lang.IncompatibleClassChangeError: Found interface io.ktor.client.engine.HttpClientEngine,
but class was expected
    at io.ktor.client.engine.HttpClientEngine.access$checkExtensions(...)
```
(or `VerifyError`, or a class-load failure in an unrelated library)

**Root cause**
`baksmali` → `smali` rebuild does not faithfully reproduce R8's synthetic access bridges / optimization artifacts. The class is still declared as an interface, but the bridge method that ART expects to find as a class member is gone.

**Why it is hard to see**
A structural diff of `class_def` entries shows **nothing**: same class count, zero `ACC_INTERFACE` mismatches, zero access-flag differences. The damage is at the code-item / reference level, invisible to table-level checks. It only appears at runtime.

**Do instead**
Use **method-level surgical rewriting** with dexlib2 — read the dex, replace only the target method's implementation, write it back. See `scripts/dexpatch/`. Never rebuild the whole tree for a one-method change.

---

## P4. Rewriting the same dex twice makes ART refuse to start the process

**Symptom**
```
E/ActivityManager: Failure starting process <pkg>
I/ActivityManager: Force stopping <pkg> appid=... user=0: start failure
```
No Java exception anywhere. `logcat` shows a splash screen appearing then vanishing. `baksmali` still parses the dex, and `smali` re-assembles it fine.

**Root cause**
Serializing a dex a second time loses metadata that the first serialization preserved. Chaining two patch tools over the same file (`patch A → patch B → repack`) triggers this.

**Why it is hard to see**
Both intermediate files look valid and round-trip cleanly. Only ART rejects the final one.

**Do instead**
**Combine all edits to one dex into a single read/write pass.** One program, one `loadDexFile`, apply every change, one `writeDexFile`.

---

## P5. Killing an endpoint to hide a UI element takes the whole screen down

**Symptom**
Home screen becomes the app's generic error state ("something went wrong / retry"), or a blank screen, after redirecting or 404-ing an ad endpoint.

**Root cause**
The ad request is a **child request** of the screen's main data load. When it throws, the parent load fails with it.

Concrete case: `/app/adverts` was redirected to a nonexistent path. That endpoint is requested from inside `MainScreenStore.loadData` as a sub-request, so the home screen's entire data load failed.

**Why it is hard to see**
Removing ads *sounds* like it should only remove ads. The coupling is invisible until runtime.

**Do instead**
Suppress at the **data-consumption** or **render** layer, not at the transport layer. Let the request succeed and discard/ignore the result. Never make a shared endpoint fail.

---

## P6. Patching a shared helper breaks unrelated features

**Symptom**
Images stop loading, video playback fails, or downloads break — after patching something that looked ad-specific.

**Root causes, two variants**
- Patching a generic utility: a `Long.valueOf`-style boxing helper had **30+ callers** across player, download, paging and history sync. Patching it would have broken all of them.
- Patching a "card" renderer you assumed was ad-only: the composable's signature was `(itemModel, ColorScheme, Modifier, onClick, ContentScale, Shape, Composer, II)` — a **generic image card** shared by normal content. Making it `return-void` killed all cover art and the player pipeline.

**Why it is hard to see**
The class name and the model type it consumes suggest it is ad-specific. It is not.

**Do instead**
Before patching any method, **count its callers** (`scripts/find_refs.py`). If it has many, or if its parameters look content-generic (image/graphics/`Modifier`/`ContentScale` parameters), it is not specific to your target. Also check whether the parameter model type is shared with non-ad content.

---

## P7. Client-side VIP forgery breaks the app instead of unlocking it

**Symptom**
Blank screen; or logged in, but playback fails.

**Root cause**
The authoritative gate is server-side. Real access is granted by an API response. Forcing the client's local `isVip()` to `true` makes the client believe it has rights the server will not honor, so it walks a path that assumes data it never receives.

Concrete case: `/v2/sections/{id}/play-url` returns **401** with no token and **401** with a forged `Bearer` token; metadata endpoints returned 200 but deliberately omitted any play URL. Patching local VIP state produced a white screen.

**Do instead**
Determine server authority **before** patching. See `references/membership-and-limits.md`. If the gate is server-side, the honest deliverable is "not achievable client-side", plus any genuinely client-side wins (unlocking UI, removing ads).

---

## P8. DataStore / protobuf hand-editing fails silently

**Symptom**
App dies with a bare `uncaughtException` and **no stack trace** (a crash-reporter SDK swallowed it). Or the app launches but ignores your injected value.

**Root cause (encoding)**
AndroidX `Preferences` maps are protobuf `map<string, Value>` fields. An entry needs **two** levels of tag:

```
outer : 0A <len(entry)>
inner : 0A <len(key)> <key>  12 <len(value)> <value>
```

Writing only the inner part produces a file `DataStore` cannot deserialize.

**Root cause (lifecycle)**
`DataStore` caches in memory and writes back. Editing the file while the app runs is either ignored or overwritten. Also the file is owned by the app's uid — a file written as root with the wrong owner is unreadable to the app.

**Do instead**
- Encode with `scripts/datastore_inject.py` (implements both tag levels).
- `force-stop` the app first, write, then start.
- Preserve ownership: write via `su`, then `chown` to the app uid (or `cp -f` over the existing file, which keeps its owner).
- If a value must survive a **fresh install**, code-level patching is the only way — runtime data is not part of the APK.

---

## P9. Blaming the patch when the device or environment is broken

**Symptom**
Every build fails, including a completely unmodified original.

**Root causes seen in practice**
- Device in a bad state: `Failure starting process` for *all* builds (including stock). **A device reboot fixed it.**
- Offline device: app shows a generic network error, easily mistaken for a server rejection or signature problem.
- App data directory uid mismatch after reinstall: crashes in a database-init path (`Cannot open database ... Directory ... doesn't exist`). Fix with `chown -R <uid>:<uid> /data/user/0/<pkg>`.
- Emulator that cannot run the app at all (different ABI, missing platform pieces). A working emulator is not evidence about a real device.

**Do instead**
**Always run a control.** Install and launch the **unmodified original** under the exact same conditions. If the original fails too, stop debugging your patch.

---

## P10. Trusting static decompilation over runtime behavior

**Symptom**
You patch what the decompiler showed, and nothing changes; or the app crashes in a path you did not know existed.

**Root cause**
Decompiler output is a guess reconstructed from bytecode. Interface/class relationships, inlined code, and obfuscated bridges are regularly misrepresented. Also, dead code and shadowed branches look identical to live ones.

**Do instead**
Rank evidence: **live runtime behavior > captured network traffic > served assets > current process/config state > persisted state > generated artifacts > source > comments and dead code.** Use source to *explain* runtime, not to *override* it.

---

## P11. Assuming a repackaged APK ships runtime data

**Symptom**
A fix verified on the target device does not work after a fresh install.

**Root cause**
Some fixes are **runtime data**, not code: a DataStore value, a preferences file, a cached token. Those live in `/data/data/<pkg>/` and are gone on a clean install.

**Do instead**
Ask, for every fix: *is this in the APK or in app data?* If it is app data and the deliverable is an APK, re-implement it as a **code-level** change (patch the read path so it always yields the desired value).

---

## P12. PowerShell (or any shell) eats device-side commands

**Symptom**
`adb shell "su -c '...'"` fails with host-side path or parsing errors: "Could not find a part of the path", "Missing type name after '['", unexpanded `$VAR`, or a regex that got mangled.

**Root cause**
The host shell expands `$`, `|`, `>`, and quotes **before** adb sees them. Windows PowerShell additionally mangles `$var:`, `[^"]` and `$(`.

**Do instead**
Never build device commands inline in the host shell. Either:
- call adb from a small script file (`scripts/devsh.py`), or
- put the device-side logic in a script that you push and execute.

Same rule for `javac`: always pass `-encoding UTF-8` when sources contain non-ASCII, or the compiler reads them as the platform default and fails.

---

## P13. Trusting `apksigner verify` output at face value

**Symptom**
You signed with v1+v2+v3 explicitly enabled, then verification reports:
```
Verified using v1 scheme (JAR signing): false
Verified using v2 scheme (APK Signature Scheme v2): false
Verified using v3 scheme (APK Signature Scheme v3): true
```
Looks like v1/v2 silently did not happen, so you go re-engineer the signing step.

**Root cause**
`apksigner verify` decides **which schemes it is meaningful to check from the APK's own `minSdkVersion`**. When `minSdkVersion >= 24`, v1 is not required for install, and the tool reports it as `false` rather than "not applicable". The signatures are present and valid.

**Why it is hard to see**
Nothing in the output says "skipped because of minSdk". It reads exactly like a failure.

**Do instead**
Always verify with an explicit range so every scheme is evaluated:
```
apksigner verify --print-certs --verbose --min-sdk-version 21 --max-sdk-version 34 <apk>
```
Cross-check the fact independently: a real v1 signature means `META-INF/*.SF` and `META-INF/*.RSA` exist in the zip.

---

## P14. Treating same-size dex dumps as duplicates

**Symptom**
You deduplicate a memory dump by file size, keep one of each, and later find the kept dex is unusable (or silently wrong).

**Root cause**
Two dumps from the same process can have **identical byte length but different content** — different classes, even different dex version headers. One may additionally be structurally broken (header fields inconsistent with body, parser walks off the end of a table).

**Why it is hard to see**
Size equality is a tempting shortcut and is usually right for *file* duplicates. Here it is coincidence: two distinct dex objects were allocated to equal-length blocks.

**Do instead**
- Deduplicate by hash, never by size.
- Validate every candidate before trusting it: check the `dex\n0xx` magic, then sanity-check the reported `file_size` / `header_size` / map offsets against the actual byte length.
- Cross-check against the packing format when possible: with length-preserving encryption, **the encrypted payload's byte length equals the plaintext dex's byte length** — that mapping is the strongest signal for which dump is the original.

---

## P15. Frida version skew produces errors that look like a broken target

**Symptom**
Attach fails or the script dies immediately with errors such as:
```
unable to locate Android dynamic linker
Java is not defined
```
on a device where Frida is clearly running.

**Root cause**
A host `frida` package newer than the device's `frida-server` (or the reverse) is unsupported. Additionally, some newer host versions dropped the built-in Java bridge, so `Java.perform` is undefined unless you inline the bridge yourself.

**Why it is hard to see**
The error names the linker or a missing global, not a version mismatch. It reads like an Android compatibility problem or an anti-instrumentation defense.

**Do instead**
- Pin host package and device server to the **identical** version before debugging anything else. Print both versions side by side first.
- If the target is an older Android release, prefer the oldest version that still supports your API needs rather than the newest.
- On a device with multiple attached targets, do not rely on automatic USB selection — see `references/dynamic-frida.md`.

---

## P16. Blaming your own patch for a server-side TLS failure

**Symptom**
After repacking, the app launches and browsing works, but **login / registration** fails with a network error. The obvious suspect is the new signature breaking the API contract, so you start hunting for a signature check in the client.

**Root cause**
The failure is at the TLS layer, not the application layer: the API host's certificate is expired (or the chain does not validate), and that particular request path validates against the **system trust store**. Shipping a different signature is irrelevant.

Crucially, one app can carry **two independent trust chains**: requests through the app's own HTTP client (which may install a permissive `SSLSocketFactory` and `HostnameVerifier`) succeed, while requests through `java.net.URL.openConnection()` use the system defaults and fail. That is why "some features work" and "login does not".

**Why it is hard to see**
The user-visible message is a generic "network error". The real exception is usually swallowed by the app's own `try/catch`. And a client-side patch is the most recent change, so it gets blamed by default.

**Do instead**
- Capture the whole exception chain before theorizing. The give-away is
  `CertPathValidatorException: timestamp check failed` → `CertificateException: Chain validation failed` → `SSLHandshakeException: Chain validation failed`.
- Confirm independently of the app: strictly validate the host's certificate from your host machine and check `notAfter` against the device clock. See `references/tls-and-cert.md`.
- Run the control: does the **unmodified original** fail the same way on the same device and network? If yes, it was never your patch.

---

## P17. Trusting UI automation to prove whether a patch worked

**Symptom**
Your script taps a button, nothing happens, and you conclude the patch broke the control. Or you tap, see no visible change, and conclude the feature is dead.

**Root cause**
Device input and screenshots are far less reliable than they look:
- `input tap` can silently fail on specific widgets even with correct coordinates (ROM-dependent).
- `input` needs `INJECT_EVENTS`; under a plain shell it fails quietly.
- `screencap` can return a **zero-byte** file on some ROMs.
- Form submission can be rejected by local validation before any request is made, so "the button does nothing" is a validation failure, not a broken handler.

**Why it is hard to see**
All of these produce the same observable: nothing happens. A zero-byte screenshot often goes unnoticed and is treated as "no change".

**Do instead**
- Read back the widget tree (`uiautomator dump`) instead of trusting pixels: it gives real `bounds`, control text, and **field contents with lengths**. Verify every field is populated correctly *before* submitting.
- Compare field values, not just presence — one case that burned an hour was two password fields of different length, causing local validation to `return` before any network call.
- Treat "no visible change" as unproven, not as a negative result: confirm with an independent signal (logcat, a runtime probe, or a server-side request appearing in the capture).
- If a tap does not register, fall back to launching the Activity directly or invoking the handler, rather than retrying coordinates.

---

## P18. The package manager reported success, but the build was never installed

**Symptom**
Every install logs `Success`, so you run the next experiment and read its result — but the app being
tested is still the previous build. Screenshots show stale UI or the launcher, and results look
"unchanged".

**Root cause**
On many ROMs a package installer interposes its own confirmation. The install command can return success
for the *request*, while the actual install waits on a prompt — sometimes a password or account
confirmation — that nobody fills in. The app stays at its old version indefinitely.

This is the most expensive failure in this skill's history: because the command "succeeded", the stale
behaviour was measured across many rounds, and each measurement looked like a genuine negative result.

**Why it is hard to see**
The success signal is real; it just answers a different question than the one you asked. Nothing in a
normal install/launch script distinguishes "installed" from "install requested".

**Do instead**
- After installing, **prove the artifact changed**: compare `dumpsys package <pkg> | grep -E 'versionName|lastUpdateTime'` before and after, or hash the on-device APK and compare it to what you built.
- If a confirmation UI exists, drive it explicitly (type the credential, press the confirm control) and then re-verify.
- Make the check a precondition of the run, not an afterthought: if the version did not change, **abort** rather than measuring.
- Keep build artifacts named after the change they contain so a stale install is obvious from a screenshot.

---

## P19. Substituting an internal signal for the user-visible outcome

**Symptom**
An error disappears from the log, no crash is recorded, and you report the problem solved. The user
immediately shows you the same problem still on screen.

**Root cause**
The internal signal and the user-visible outcome are different claims. Suppressing one error path does
not remove the symptom if the symptom is produced by a **different** path — and a blocking dialog often
is. The log going quiet proves that one code path was affected; it says nothing about whether the user's
problem is gone.

**Why it is hard to see**
The signal is specific, measurable, and genuinely changed. It is a true statement being used to support a
false one.

**Do instead**
- Define "done" as the **user-visible behaviour**: the blocking UI is gone, the app reaches its normal
  screen, the feature works. Nothing else counts.
- Treat the absence of a log line as absence of evidence, never as evidence of success.
- When a symptom persists after an internal signal improves, assume there is **another** producer of the
  symptom and go find it, rather than assuming your fix is merely incomplete.
- Also verify the opposite direction: confirm the original symptom is reproducible **before** you patch,
  so you know what disappearing would even look like.

---

## P20. "I did not capture it" treated as "it is not there"

**Symptom**
Screenshots taken every few seconds after launch show no blocking dialog, so the dialog is declared gone —
then it turns out to be present the whole time.

**Root cause**
Sampling is not observation. A transient state that appears and is then covered (a second window, a
navigation, a system prompt) can fall entirely between samples. The modal appears, gets occluded, and
every frame you happened to take shows something else.

**Why it is hard to see**
The captures are real and consistently show the same thing, which feels like corroboration. Conviction
grows with the number of frames, even though all of them share the same blind spot.

**Do instead**
- For anything time-sensitive, capture **continuously** (recording) or in a dense burst immediately after
  launch, not on a fixed slow interval.
- **Look at every frame**, not only at file sizes. A byte-size cluster that "looks familiar" is not a
  reading.
- State conclusions with their sampling: "not observed in N consecutive seconds of recording" is honest;
  "does not occur" is not.
- When something is reported present by a human who is looking at the screen, believe the screen. Your
  capture gap is the more likely explanation.

---

## P21. Changing two things at once, then attributing the result

**Symptom**
A build fails, and you conclude that the mechanism you were most curious about is the culprit — then
exclude it from consideration for a long time. Later, a clean experiment shows it was the other change
all along.

**Root cause**
Two edits, one observation, no attribution. The failure is real; the explanation is invented. Worse, the
invented explanation survives because it sounds plausible and no one re-tests it.

**Why it is hard to see**
The experiment "worked" in the sense that it produced a result. Acting on a wrong attribution feels
exactly like acting on a right one until much later.

**Do instead**
- One variable per install-and-launch cycle. Where a combination is unavoidable, add a third run that
  isolates each half.
- Write the attribution into your notes **with the run that proves it**. An unproven cause is a
  hypothesis; keep it labelled as one.
- When a route is about to be discarded, re-check whether the evidence was actually single-variable. A
  discarded route with compound evidence should be re-opened before being abandoned.
- Prefer semantically inert controls (a change nothing reads) to prove "edits of this class are allowed"
  separately from "this specific edit is allowed".

---

## P22. Waiting for something that requires a human to advance

**Symptom**
An automation loop polls for minutes or longer, waiting for a state that never arrives on its own. Time
is consumed while nothing at all can change.

**Root cause**
The awaited state is gated on a human action — a consent prompt, a permission dialog, an installer
confirmation, a captcha. No amount of waiting resolves it. Automated polling is the wrong instrument for
a state whose transition is external.

**Why it is hard to see**
Polling is cheap-looking and the loop reports progress (timestamps, unchanged screenshots), which creates
an impression of work being done.

**Do instead**
- Before waiting on a state, ask what would cause it to change. If the answer is "a person", stop waiting
  and either perform the action programmatically or hand it back.
- Bound every wait with a deadline and an explicit failure branch that **does something different**, not
  just a longer timeout.
- Detect stalls by change, not by elapsed time: if N consecutive samples are identical, break out.
- Prefer driving the prompt to completion over waiting it out — the same prompt usually recurs, so
  automating it once pays back immediately.

---

## P23. The fix lives in a file the app rewrites

**Symptom**
You change a value in the app's data, the write succeeds, the file reads back correctly — and after
the next launch the value is back to what it was. Often byte for byte identical, which makes it look
like nothing happened at all.

**Root cause**
The stored value is a **cache, not a source of truth**. Either the app re-fetches it and re-persists
it, or it rewrites the file from its own defaults on every start. Your edit was never authoritative.

Compounding it: the intuitive way to protect the file — a restrictive mode or a changed owner — **does
not work**, because the app does not open-and-write the existing file. It **deletes the file and
creates a new one**, and a new file is created with the app's own mode and owner. Nothing is inherited,
so `chmod`/`chown` are silently ineffective.

**Why it is hard to see**
Verification is usually done immediately after writing, while the file is still correct. The rewrite
only happens on the next start, which is one step further along than you looked. And the "fix" that
seems obviously right (tighten permissions) fails without any error.

**Do instead**
- **Verify after a relaunch, not after the write.** The write succeeding is not the finding; surviving
  a restart is.
- **Distinguish the two causes with one offline launch.** If the value survives with the network down,
  it came from the server. If it does not, the app is regenerating it locally — and then a data edit is
  the wrong layer entirely; patch the read path instead.
- To make a data edit stick, use the **immutable attribute** and confirm it took effect:
  ```bash
  su -c "chattr +i <file>"; su -c "lsattr <file>"     # expect the 'i' flag
  ```
  It is enforced by the filesystem against the delete itself, which is why it holds where permissions
  do not. Undo with `chattr -i`.
- Then **exercise the feature**, not just the value. A blocked write the app depends on can make it
  misbehave; "the file still has my value" is not "the app still works".
- Remember a lock is **device state, not artifact state** — it does not travel with an APK. Record it
  as an environment requirement. The only form that ships is a code patch (`runtime-data.md`).

---

## P24. The artifact changed, but the wrong one is executing

**Symptom**
The build differs from the original, the pipeline reports success, the file on disk is genuinely
modified — and the app behaves exactly as before. Or a native hook reports nothing while the feature
plainly runs.

**Root cause**
Something other than your edit is being used at runtime:

- **Wrong ABI.** A fat APK ships several `lib/<abi>/` directories; the package manager extracts and
  loads **one**. Editing `arm64-v8a` while the device loads `armeabi-v7a` produces a byte-different,
  behaviorally identical build.
- **The library is not from the APK at all.** Some libraries are written into the app's data directory
  at runtime rather than extracted from the package. Patching the APK copy changes a file nobody loads.
- **Multiple processes.** The work was done in, or the check lives in, a different process than the one
  you are observing.
- **A stale install.** The package manager reported success for a request that did not replace what is
  on disk (`P18`).

**Why it is hard to see**
Every local indicator agrees: the diff is non-empty, the build is signed, the install returned success.
Nothing in the *build* pipeline can detect this, because the build is fine. The contradiction only
exists at runtime.

**Do instead**
- **Ask the running process what it loaded**, before editing: `scripts/lib_map.py --pkg <pkg>`.
  Libraries whose path is not under the installed APK's lib directory were materialized at runtime
  and belong to whatever produced them.
- Confirm the ABI the package manager actually chose (`dumpsys package <pkg> | grep primaryCpuAbi`)
  rather than the one you assumed from the manifest.
- **If the library you patched is not in the live mapping, stop.** No amount of re-patching helps; the
  plan is wrong.
- Treat a behaviorally identical rebuild as **positive evidence that your edit is not being loaded**,
  not as "the change had no effect". Those are different conclusions and only one of them is actionable.

---

## P25. "The search found nothing" treated as "the data is not there"

**Symptom**
You scan an artifact for a known-present value — a UI label, a marker string, an endpoint — get zero
hits, and conclude the content is stripped, encrypted, or otherwise unavailable. A route gets written
off on that basis.

**Root cause**
The search used the wrong representation. A byte scan for UTF-8 text returns nothing against content
that is stored as UTF-16, or compressed, or framed inside a container, or split across fragments. The
data is present; the needle was encoded differently from the haystack.

**Why it is hard to see**
"Zero results" is a clean, confident-looking output. It feels like a measurement, so it gets recorded
as a finding, and findings propagate into the plan.

**Do instead**
- **Before concluding absence, search more than one encoding.** UTF-8 and UTF-16LE will between them
  cover most text storage:
  ```python
  blob.find(needle.encode('utf-8')), blob.find(needle.encode('utf-16-le'))
  ```
- **Search the shortest distinctive fragment.** Text is often assembled from pieces or templates, so a
  full sentence can be absent while its parts are present.
- **Try the value without its framing.** A hit rate of zero is also the expected result for content
  that is inside a compressed or encoded container — decode the container first (`runtime-data.md`,
  `scripts/blob_decode.py`).
- **State a negative result with its scope**: "no UTF-8 or UTF-16LE literal match in this artifact"
  is a finding. "The string does not exist" is a guess wearing a finding's clothes.

## P26. A self-built analysis script fails in a way that reads as a target finding

**Symptom**
A purpose-written script emits something that looks like a result -- an offset table, a count, a
"no matches" verdict -- and it is wrong. Nothing in the output says so, so it gets recorded as a
finding and the plan is built on top of it.

**Root cause**
Three variants, all hit in a single project:

- **A silent arithmetic error.** `(w >> 10) & 0xFFF << 12` binds as `& (0xFFF << 12)` in Python, so
  the intended mask silently became a different one. The script ran clean and printed a plausible
  table; every offset in it was wrong.
- **A helper script shadowing a stdlib module.** A local file named `dis.py` captures any
  `import dis` performed inside a third-party package. The symptom appears as a circular-import
  error *inside that package*, which reads like a broken dependency rather than a local name clash.
- **Measuring against an incomplete reference.** A "precision" number computed against a partial
  listing reports the reference's gaps as your errors. Here it scored a working extractor at ~30%
  when the reference itself was the incomplete side.

**Why it is hard to see**
The tool is trusted by default, because you wrote it for this exact job. Its output is well-formed
and arrives fast, which reads as competence.

**Do instead**
- **Sanity-check the shape before the content.** A ratio or distribution that is implausible for the
  domain is a bug signal -- e.g. an average of 31 references per offset when the rest of the picture
  implies ~3.
- **Cross-check against an independently built artifact.** Two independent producers agreeing to
  ~99% is evidence; one producer's own output never is.
- **Histogram before choosing a threshold, and re-measure after changing it.** If moving a knob does
  not move the metric, the knob is not doing what you think (a run-length filter here barely changed
  accuracy across a 10x range, which is how it was caught).
- **Exercise any fallback path against a case whose answer is already known.** An accuracy claim
  derived only from the tool's own output means nothing.
- **Name helpers so they cannot shadow a module** (`dart_disasm.py`, not `dis.py`), and keep a
  timeout on every scan (SKILL.md).

---

## P27. Every request fails after a repack because the signing certificate *is* the key

**Symptom**

The rebuilt app installs, launches, and draws its shell — but every API-backed screen shows a
generic network error. Computed request parameters (`sign`, `_p`, `uth`) come out as `-1`,
empty, or null. No Java exception anywhere, and the app's own UI still looks healthy.

**Root cause**

The client uses **its own APK signing certificate as key material**: it reads
`PackageInfo.signatures[0]` and hands that value to a native HMAC/DES routine which produces the
request signature. Re-signing changed the certificate, so the derived key changed, so the server
rejects every signed request. This is not "the server checks the signature" — the *client* is
computing with it, and the server was built against the original key.

**Why it is hard to see**

It reads as a server problem or a bad patch. The artifact is valid, the patch is correct, the
build verifies, and the app runs — so the natural conclusion is "a client patch is not possible
here", which sends you back into static analysis for hours. A naive fix also survives inspection:
hardcoding *a* signature value produces correct-looking smali and a clean build, and nothing
complains until a request is actually sent.

A second trap sits inside the first: `signatures[0].toByteArray()` is **not** the
`META-INF/*.RSA` file. On modern Android it is a certificate DER taken from inside the PKCS#7
chain. Hardcoding the whole `.RSA` content (1199 bytes in one measured sample) instead of the
runtime value (777 bytes) yields a build in which every signing parameter is `-1`.

**Do instead**

1. **Detect it before repacking.** Grep the decompiled sources for `toCharsString()`,
   `getPackageInfo(..., 64)` and `signatures[0]`. If the value feeds a native method that also
   does HMAC/AES/DES, this pitfall applies.
2. **Read the real value from the device**, not from the file —
   `python scripts/sig_probe.py --live <pkg>`. Cross-check the candidate list from
   `scripts/sig_probe.py --apk <original.apk>`; the runtime length decides which candidate is
   correct.
3. **Hardcode it at every read site** (there is usually more than one), then assert the remaining
   site count is zero.
4. **Prove it differentially.** Print the computed signing parameter for the same startup request
   on the original build and the rebuilt one. Same shape ⇒ consistent. `-1`/empty ⇒ the key is
   still wrong.
5. **Check the OAID/device-id path too** — it frequently hashes the same certificate separately.

Full treatment: `references/signature-derived-keys.md`.

---

## P28. `logcat -c` does not clear the events buffer, so the previous build's crash looks like this build's

**Symptom**

After installing a fix, a search for the crash signature returns a hit. It looks like the fix did
not work — and the "hit" is convincing, because it is the exact exception and the exact frame you
were fixing.

**Root cause**

`adb logcat -c` clears `main`, `system` and `crash` **by default — not `events`**. The
system's own crash record (`am_crash`, `am_proc_died`) lives in `events`. Reading `-b all`
therefore pulls in the previous build's crash, which was never cleared.

**How to tell it apart**

Correlate **PID and wall-clock time** against the current process:

- The PID in the record belongs to a process that is no longer running.
- The timestamp **predates** the current process's start.

Both together mean history, not a finding. (In the observed case the stale record's PID was the
previous build's, and its timestamp was minutes before the current process started.)

**Do instead**

Pick one, and say which you used:

- Bound the query by timestamp — accept only records after the current process started, or
- Judge per buffer — `crash` is a fresh window after `-c`; `events` requires PID/time correlation.

**The evidence window is itself a claim that needs support.** An unexamined stale window turns
"fixed" into "still broken", and this one is invisible in the log's own text.

---

## P29. The patch landed and changed nothing, because the static data it edited is not the data the UI consumes

**Symptom**

Build is green. The patch is verifiably present in the artifact. The behaviour is unchanged.

**Root cause**

**The same type had two construction sites** — one for a static/default template, one inside the
runtime conversion of a server response — and only the second one feeds the UI. Editing the first
is a no-op that verifies cleanly and audits cleanly.

**How to see it before shipping**

From the type's constructor, count the call sites (`scripts/find_refs.py`), then ask of each:

> **Is this one on the path the UI actually reads?**

"It is constructed here" is not "it is consumed here". Two constructors of the same type can have
completely different fates.

**Do instead**

- Patch the **consumer** — the loop that converts response items into the UI model — not the
  static table.
- Prefer a predicate over a **semantic discriminator** (a business code, a task type) rather than
  a display string. The literal in the template is **not** necessarily the literal the server
  sends: the string you want to match may not exist anywhere in the response.
- If you cannot confirm the server-side value, **predicate on both candidate fields** rather than
  betting on one.

---

## P30. Two observations that cannot distinguish the hypotheses, reported as a result

**Symptom**

A verification step "passes" or "fails" while having tested nothing.

**Root cause**

The observable is identical under both hypotheses, so the measurement carries no information.
Real instance: a promotional banner was absent in the logged-in state, and that run was used to
"verify" its removal — but the same banner is also absent in the logged-out state. Neither run
could distinguish an effective patch from a no-op, and the second one was skipped as
"uninformative" — correctly, since it could not have been informative either.

**Do instead**

Before running a verification, ask:

> **What would this look like if the patch were absent?**

If the answer is the same, the measurement is void. Record it as **"not applicable under this
condition"**, never as "passed".

Two close variants of the same error:

- Treating **"the entry point is unreachable"** as proof of removal. The honest test is whether
  the **request is still issued**: a UI element that no longer renders can still fire its network
  call from elsewhere. Verify at the layer the behaviour actually lives on.
- Treating **"the screenshot hash changed"** as proof that something rendered. A hash proves
  *change*, never *what* changed — and it never proves *absence*. Look at the images: a status-bar
  clock tick or a line of text reflowing changes the hash while a full-screen overlay would not
  have been missed if the frames had actually been inspected.

---

## P31. Neutralising a terminate path by making it "not return" freezes the whole process

**Symptom**

The app hangs with **no crash record at all**, then disappears. Or an external process kills it —
`Force stopping … from uid 0`, an app-restart loop — and nothing in the log says "crash".

**Root cause**

A terminate routine (a shell's `kill`/`exit`/`abort` stub, or a self-terminating function entry)
was replaced with something that **never returns**: a self-branch, an infinite loop, a spinning
stub. The caller was written expecting the process to be gone. Instead control never comes back,
whatever lock it held is never released, and unrelated threads wedge behind it.

**Why it is hard to see**

There is no exception, no signal, and no tombstone, because nothing failed — it stopped. Absence of
a crash record reads as "it is still fine", and the eventual death is attributed to whatever the
killer happened to be. The tell is a **uid-0 killer**: an app cannot spawn a root-owned executioner,
so the executioner is outside the app, which means the app froze rather than died.

**Do instead**

**Return. Always return.** A `ret`, or a stub that loads 0 and returns.

- Callers commonly inspect the return value, so make the suppressed call **succeed (0)** rather
  than fail (-1) — failure can push the caller into an error branch that tries a *different* way
  to terminate.
- Do not touch the ordinary-path symbols: `pthread_exit`, `exit`, `abort`, `snprintf`, `closedir`,
  `android_set_abort_message`. Freezing `pthread_exit` wedges every thread that finishes; freezing
  `snprintf` wedges the first log line. A five-stub patch intended for terminate symbols has hit
  exactly those symbols before.
- If the fix is a delay-loop watchdog, the *faulting store*, not the loop, is the thing to remove.

Full treatment, including how to tell which mechanism is actually firing:
`native-tamper-and-suicide.md`.

---

## P32. Rewiring a stub without resolving which symbol it belongs to

**Symptom**

A patch meant to suppress one check breaks something entirely unrelated — often before that check
would even have run.

**Root cause**

PLT stubs are laid out back to back. A patch recipe that names offsets, or that assumes a fixed
stub width, is one arithmetic slip away from rewriting its neighbour. Real outcome of one such set:
five stubs intended to be terminate symbols resolved to **five different symbols on each
architecture**, including a string formatter and a directory call — so the app froze on its first
log line instead of suppressing anything.

**Why it is hard to see**

The offsets and the symbol names usually come from different sources (a note, a previous round, a
generated table) and nothing cross-checks them. The damage then presents as an unrelated stability
problem, and the real cause is two rounds back.

**Do instead**

Resolve every stub to its symbol **before** writing the patch, from the **relocation table** —
never from a comment, a position, or an assumed width.

`scripts/elf_plt.py` prints `stub address -> symbol` for both x86_64 and aarch64, and
`--diff --name-regions` names the symbol each changed stub belongs to, which is the right way to
audit a patch set you inherited.

**The aarch64 stub is 16 bytes (four instructions), not four.** Assuming the short form pushes you
into borrowing the next slot, which belongs to a different symbol — and a 16-byte stub is exactly
what makes a clean two-instruction replacement (`mov x0, #0; ret`) possible without touching
anything else.

---

## P33. "The scan found no call sites" — from a decoder that stopped early

**Symptom**

A scan for call sites, stubs, or a byte pattern reports zero matches, and that zero becomes a
finding: "this library never calls `kill`", "there is no second site", "the payload is absent".

**Root cause**

A linear disassembler handed a buffer that does not start on an instruction boundary can return a
few instructions and then **stop, silently**. No error, no warning — and its partial output is
indistinguishable from a complete negative. On a fixed-width architecture, decoding from the wrong
offset also produces plausible garbage rather than failing.

**Why it is hard to see**

Zero is a comfortable answer. It usually agrees with what you were hoping ("the check is not
there"), so nothing prompts a second look. (See also P25 — same shape, different mechanism.)

**Do instead**

Never conclude absence from a scan whose coverage you cannot describe.

- Prefer **byte-pattern search** for a sequence you already know, taken from a crash or a known
  call site.
- For instruction classes with regular encoding, use a **bit-pattern scan** — branch instructions
  are the useful ones, and this finds every occurrence without depending on linear decoding.
- Otherwise use a **resynchronising** scan (advance one instruction unit — 4 bytes on aarch64,
  1 on x86_64 — and retry).
- State which method you used and what it can miss.

---

## P34. A deliberate crash read as an ordinary bug

**Symptom**

`SIGSEGV`, a real tombstone, `fault addr 0x4` (or `0x0`/`0x8`), `Cause: null pointer dereference`.
It looks like a plain null-dereference defect, so you go looking for the defect.

**Root cause**

There is no defect. A hardening layer that wants the process dead **without calling anything it
imports** arranges a fault — load a small constant, use it as a pointer:

```
mov  x0, #4
mov  w1, #1
str  w1, [x0]        ; fault addr = 0x4
```

**Why it is hard to see**

The tombstone is genuine, the signal is genuine, and `null pointer dereference` is the runtime's
honest description. Nothing distinguishes it from a real bug except the *shape* of the fault — and
"it crashes on a small address" reads like sloppy target code, which is exactly what it is
imitating.

**Do instead**

Read the fault address and the registers **together**:

- Is the fault address a small integer rather than a plausible pointer?
- Does some register hold exactly that value?
- Does the instruction at the faulting `pc` load that constant a few instructions earlier, in the
  same basic block?
- Is there a delay loop immediately above it (`sleep` repeated N times)? That is a watchdog, and it
  explains why the death always comes "a little while after launch" rather than at once.
- Does the block sit right before a normal epilogue (canary check + `ret`)? The intended exit is
  right there.

If all of that holds, **nop the faulting store** and leave the surrounding arithmetic alone — the
thread then falls through into the epilogue and returns normally.

`scripts/native_crash.py` extracts the frames, registers and faulting instruction, and flags this
shape explicitly.

---

## P35. Blocking one termination mechanism and calling the check suppressed

**Symptom**

The `kill` stub now returns success, the import table is clean, the patch is verifiably present —
and the app still dies, with the same signal at the same time.

**Root cause**

A hardening library terminates through **several independent mechanisms that share no choke
point**: an imported `kill`, an imported `exit`, `abort()`, and a **deliberate crash that calls
nothing at all** (P34). A PLT-level fix covers the first two and has literally no effect on the
last one, because no imported symbol is involved.

**Why it is hard to see**

"It imports `kill`, so `kill` is how it dies" is a satisfying and often correct-sounding story. A
*correct* patch to a *real* mechanism produces no visible change when a second mechanism fires
first — so the conclusion drawn is "the patch did not work / the approach is wrong", and a working
route gets discarded.

**Do instead**

Enumerate the mechanisms before patching, then **measure which one actually fires**. The signal
splits the space, and the tombstone confirms it:

| Observation | Mechanism |
|---|---|
| `SIGKILL`, no exit code, **no tombstone** | an imported terminate call |
| `SIGSEGV`, small fault address | arranged crash — no imported symbol involved |
| `SIGABRT` + tombstone | usually a genuine assertion |
| process survives a repack but the library is absent from `maps` | the patch never ran |

**Then verify against the observed time-to-death.** If it died ~40 s after launch before, a
30-second test proves nothing, and a run that survives 45 s has not yet passed.

---

## P36. Parsing a hardened ELF through its section headers

**Symptom**

A tool reports that a library imports one symbol, or has a 200-byte `.text`, or contains no
functions. You build a plan on that.

**Root cause**

Hardened libraries ship **forged section headers**: `.text` sized to a token value, `.dynsym`
truncated, sections overlapping. Anything that walks the section table returns confidently wrong
output — and because the output is well-formed, the wrongness is invisible.

**Why it is hard to see**

A truncated result and a genuinely minimal library look identical. The tool has no way to report
that it was lied to, so the failure is attributed to the target rather than the method.

**Do instead**

Work from the **program headers**, which the loader itself uses and which therefore cannot lie
about what gets mapped:

- `PT_LOAD` → the real segments, their file offsets and their permissions.
- `PT_DYNAMIC` → `DT_STRTAB` / `DT_SYMTAB` / `DT_STRSZ` / `DT_SYMENT` / `DT_JMPREL` /
  `DT_PLTRELSZ`, walked by hand.
- Translate any virtual address to a file offset through the containing `PT_LOAD`.

A library that yields a full import list this way is fine. One that still yields almost nothing
means the hardening is deeper than the section table — **say that**, rather than reporting the
truncated answer as a finding.

For **function boundaries**, use `PT_GNU_EH_FRAME` when it survived: it is authoritative and
complete, and it costs a few lines to parse. Do not reverse-decode backwards looking for a prologue
— on aarch64 almost any 4-byte window decodes as *something*, so a naive scanner reports hundreds
of fictional entry points — and prologue pattern-matching yields a plausible set with no
completeness guarantee.

---

## P37. A byte patch lands, and the app dies with `Bad checksum` and a missing normal class

**Symptom**

After editing a dex by a few bytes and repacking, the app fails to start, and logcat shows an
ordinary class failing to resolve — the Application class, or a small AndroidX component:

```
W/<pkg>: Failure to verify dex file '.../base.apk': Bad checksum (eacdc11c, expected 6456b6b5)
E/LoadedApk: java.lang.ClassNotFoundException: Didn't find class "<AppClass>" on path: ...
E/AndroidRuntime: FATAL EXCEPTION: main
    java.lang.RuntimeException: Unable to instantiate application <AppClass>: java.lang.ClassNotFoundException: ...
```

**Root cause**

Every dex header carries two integrity fields that cover the rest of the file, and **they must be
recomputed in a specific order**:

```
bytes 12..32 = sha1(data[32:])        # signature — computed FIRST
bytes  8..12 = adler32(data[12:])     # checksum — covers the signature, so LAST
```

Computing them in the reverse order leaves the adler32 taken while the signature field was still
zeroed, so the header never verifies. Note also that in the log line above the **real** adler32 is
printed as "expected" and the header's stale value as the computed one, which reads backwards and
sends you looking at the wrong number.

Two properties make this expensive:

- **Android may still start the process**, falling back to interpreting the dex instead of using a
  verified/optimized image. So the failure is not "rejected", it is a *different* failure, and it
  appears as a class-resolution problem in a component unrelated to your edit.
- **Some producers ship a dex whose signature field is all zeros.** On such a file the wrong order
  is self-consistent, so the bug stays invisible until the first edit — and then looks like your
  edit caused it.

**Do instead**

Recompute both fields on every dex you touch, in the order above, and assert the result:

```
adler32(data[12:]) == header_checksum   and   sha1(data[32:]) == header_signature
```

`scripts/dexutil.py` provides `fix_dex_header()` (correct order) and `verify_dex_header()`;
`scripts/dex_patch_bytes.py` runs both and refuses to write a header that does not self-verify.
When you see `Bad checksum`, check the header before investigating the class it named.

---

## P38. `[-124]` on install after a repack: `resources.arsc` must be STORED *and* aligned

**Symptom**

An APK that was previously installed fine, rebuilt with only a dex change, is refused:

```
Failure [-124: Failed parse during installPackageLI: Targeting R+ (version 30 and above)
requires the resources.arsc of installed APKs to be stored uncompressed and aligned
on a 4-byte boundary]
```

**Root cause**

Two independent requirements are compressed into that one sentence: the entry must be **STORED**,
and its **data offset** must be divisible by 4. A `zipfile`-based repack can satisfy the first and
still fail the second, because Python's zip writer gives you no control over entry offsets.

An aggravating factor: this is exactly the class of defect a *signing* step can introduce.
`jarsigner` recompresses entries as a side effect of adding the v1 JAR signature, so an archive that
was correctly aligned before signing is not aligned after — and `jarsigner -verify` still reports
success. If a build that installed a minute ago now returns `[-124]`, suspect the signer first.

**Do instead**

- Write the archive aligned **while writing it** (`scripts/repack.py` emits local headers itself and
  pads the local extra field), rather than repairing alignment afterwards.
- Know the padding arithmetic trap: a zip extra area is a sequence of `(id, size, payload)` records,
  so its minimum useful length is 4 bytes — **a required pad of 1-3 bytes cannot be expressed**.
  Insert a stored filler entry of exactly that size instead.
- Sign with **`apksigner`** (v1+v2+v3), which appends the signature block without reordering the zip.
- Verify by reading the archive, not the tool's exit code: for each gated entry, parse the local
  header, compute `header_offset + 30 + namelen + extralen`, and check `compress_type == 0` and
  `offset % 4 == 0`.

---

## P39. Install fails with a bare numeric code and no `INSTALL_FAILED_*` constant

**Symptom**

```
Performing Streamed Install
adb.exe: failed to install app.apk: Failure [-99]
```

The APK installs fine through the device's own file manager, and the same build installs on another
device. There is no symbolic `INSTALL_FAILED_*` name, so there is nothing to look up.

**Root cause**

Some OEM ROMs route `adb install` through their own security/verification service. The failure is
**not about your APK**; a device process is declining to accept an ADB-initiated install. The device
log names the real actor:

```
ColorPackageInstallInterceptManager: <VENDOR>_ADB_INSTALL_CANCEL ... packageName=<pkg>
```

**Do instead**

Recognise the shape: numeric-only failure, no symbolic constant, installs fine via the device UI,
and a vendor package-installer/security process in logcat. Then bypass ADB's install path with root:

```bash
adb -s <serial> push app.apk /data/local/tmp/app.apk
adb -s <serial> shell "su -c 'pm install -r -g -d /data/local/tmp/app.apk'"
```

Do **not** start rebuilding the APK, and do not remove permissions or components to "make it
installable" — the artifact was never the problem. Search the device log for the install attempt
before touching the build again.

---

## P40. The screen you captured is not your app

**Symptom**

A launch capture sequence shows a consistent, plausible screen, and conclusions are drawn from it.
Later, the app is discovered never to have been in the foreground at all. The captured frames show,
for example, a vendor package-installer confirmation bearing a package name from an unrelated
earlier attempt.

**Root cause**

An install that went through a UI prompt or an OEM interception can leave the **installer window as
the foreground activity indefinitely**. From then on:

- `am start` on your app appears to do nothing; the other window owns the display.
- Screenshots of your supposed launch show the installer instead.
- `am start -W` — which waits for a first frame — can block past any reasonable timeout, because
  that frame never arrives. This presents as "the tool hung", not as "the wrong window is up".

The insidious part is that the frames are **mutually consistent**, which feels like corroboration.
Consistency is not corroboration when every frame shares the same blind spot.

**Do instead**

- Check the foreground before trusting any capture, and again at the end of the sequence:
  ```bash
  adb -s <serial> shell "dumpsys activity activities | grep -m1 ResumedActivity"
  ```
  If the component is not your package, the frames are evidence about something else.
- Clear the stray window (`am force-stop <installer pkg>`, or a HOME key event) and re-capture.
- Prefer a launcher-driven capture over `am start -W`: derive the time line from captures plus
  logcat instead of blocking on a first frame.
- Treat byte-identical consecutive frames as a **finding** (a hang, a dialog awaiting input), not as
  a capture artefact.

`scripts/coldstart.py` performs the foreground check and warns; see also
`long-task-discipline.md` §captures you never looked at are not evidence.

---

## P41. A patched branch does the opposite of what was intended, and starts cleanly

**Symptom**

The patch targets a boolean config gate. The build installs, launches, and never crashes — and the
behaviour is exactly inverted: the thing that was supposed to be suppressed now appears every time,
or vice versa. Nothing in the logs indicates a problem.

**Root cause**

The **polarity of the branch was read from the field name instead of from the control flow.**
Field names describe intent, not branch layout.

```
0x151304  iget-boolean v11, v0 -> Config.enabled
0x151308  if-nez v11, :far         ; enabled == false jumps AWAY
0x15130c  invoke ...startMain()    ; fall-through: straight into the app
0x151314  :far  iget v11, v0 -> Config.duration   ; the "show it" path
```

Here `enabled == true` is the value that **skips** the promo — the opposite of the literal reading.
A patch that "enables the skip" forces the promo to display on every launch.

The second, equally quiet variant: redirecting a conditional branch (`if-*` -> `goto`) to force one
side. That introduces a new control-flow edge, which can land on a `move-result*` and make the class
fail to load with `VerifyError` — a class-load failure that does not always surface as a crash
dialog.

**Do instead**

- **Decode both sides before editing**, and write one line naming what each one does. If you cannot
  describe the fall-through and the target, you are not ready to patch.
- Prefer **neutralising the branch** (`if-*` -> `nop` pair) over redirecting it. Removing an edge is
  safe; adding one is not.
- Pin the polarity in the patch specification itself: assert which instruction must immediately
  follow the branch. `scripts/dex_patch_bytes.py` fails the patch if `expect_next` does not hold,
  which makes this mistake impossible to commit silently.
- Audit verifier legality after the edit instead of trusting that it launched
  (`scripts/dex_check_verifier.py`).

---

## P42. A decode desynchronises, and every offset after that point is wrong

**Symptom**

An instruction you can see in a smali listing is not found by your own decoder, or is reported at an
offset that does not match the disassembler. Sometimes the decode still produces plausible-looking
instructions, just shifted, so "no match" is reported for something that is definitely present.

**Root cause**

**One wrong instruction width desynchronises everything after it.** Common offenders, each with its
own trap:

- `0x32`-`0x3D` (`if-test` 22t / `if-testz` 21t) are **2** code units, not 1. Treating them as 1
  unit invents a fake second instruction at every branch.
- `0x1A` (`const-string/jumbo`) appears in real toolchains as a **4-byte** form (op, register,
  uint16 string index), not the 6-byte 31c shape its format name suggests. Counting it as 3 units
  shifts the rest of the method by one unit per occurrence.
- `0x28` is `goto` (10t, **1** unit); `0x29` is `goto/16` and `0x2A` is `goto/32`.
- A `nop` payload is encoded `00 <ident> <size>` with `ident` in 1..3; a plain `00 00` is an ordinary
  one-unit `nop`. Treating every `00` as a payload swallows the following instruction.
- dalvik encodes a distant conditional jump as `if-*` **plus** a separate `goto`, not a single
  instruction.

**Why it is hard to see**

The decoder reports what it decoded. A shifted stream looks like a method that simply does not
contain the instruction you want, which reads as a finding about the target — the same failure shape
as P25/P26/P33, and it removes viable patch sites for free.

**Do instead**

- **Assert the walk ends exactly on `insns_off + insns_size*2`.** If it overshoots or undershoots,
  the width table is wrong somewhere and every offset derived from that method is suspect. One
  comparison catches all of the above.
- **Cross-check register numbers.** If the method's `registers` count is 12 and the listing mentions
  `v13`, the decode has drifted.
- **Cross-check one known instruction** against a disassembler before trusting offsets you derived.
- Build the width table from the format groups in `references/byte-level-patching.md` rather than
  from memory, and keep the width logic in one place so a fix applies everywhere.
