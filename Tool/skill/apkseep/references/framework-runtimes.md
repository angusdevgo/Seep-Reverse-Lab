# Cross-Platform Runtimes

Load this when the app's UI is not native, or when Java-layer hooks produce no hits at all.

Many apps ship a native shell plus a cross-platform runtime. Their business logic, their UI, and their
feature gates live **inside the runtime**, not in the dex. Patching the dex then does nothing — the Java
code you can see is mostly glue. Determine the runtime before choosing where to patch.

## Identify the runtime early

Signals in the APK:

| Runtime | Giveaways |
|---|---|
| Flutter | `libflutter.so`, `libapp.so`, `assets/flutter_assets/`, Dart snapshot |
| React Native | `libhermes.so` or `libjsc.so`, `index.android.bundle`, `assets/index.android.bundle` |
| Unity | `libunity.so`, `libil2cpp.so`, `assets/bin/Data/`, `globalgamemanagers` |
| Cordova / Ionic | `assets/www/`, `cordova.js` |
| Xamarin / .NET | `libmonodroid.so`, `assemblies/` in the APK |

A `classes.dex` that is small relative to the total payload is another strong hint that the real code
lives elsewhere.

## The layer trap

The expensive mistake: seeing a UI element (dialog, paywall, gate) and assuming it is a native control,
then spending a long time looking for it in the dex.

If it is drawn by the runtime, the dex contains only the bridge. Symptoms of being on the wrong layer:

- hooking the obvious Java dialog/Activity classes produces **zero** hits while the UI clearly appears;
- the classes that do appear in stacks are the runtime's own, with obfuscated names;
- hooking a Java method changes nothing about the visible behaviour.

Establish layer ownership **before** investing in a patch direction.

### How to tell which layer drew a given UI

1. Enumerate the Java dialog and presentation classes and hook their show/creation paths.
2. Reproduce the UI. If any hook fires, the caller stack names the detection and you are on the Java
   layer.
3. If nothing fires while the UI is on screen, the UI is runtime-drawn or native-drawn. Switch axis.
4. Expect runtime-owned windows to appear as ordinary system `Dialog`/`Presentation` objects used as
   **containers** for the runtime's surface. A hit on such a container is not evidence that the visible
   element is a native dialog — read the class name carefully before drawing conclusions.

## Flutter specifics

- Business logic is compiled ahead-of-time into **`libapp.so`**; UI is rendered by `libflutter.so` with
  no per-widget Java objects.
- **Widgets, dialogs, and paywalls are not Java views.** They will never appear in Java stack traces,
  and no Java hook can intercept them.
- The Java side is thin: one Activity, plus plugin classes. Calls cross the boundary through the
  platform-channel mechanism, whose class names are frequently obfuscated.
- Because channel classes may be renamed, locate them **by method signature and call shape**, not by
  class name.

### Where to intervene in a Flutter app

| Goal | Layer | Notes |
|---|---|---|
| Stop the app being killed / refused at startup | host native library | earliest point, see `native-and-so.md` |
| Observe what the runtime is told | platform channel | shows the messages that drive the UI |
| Change a decision permanently | `libapp.so` | most direct, hardest to locate |
| Change startup behaviour only | host native library constructor | survives runtime restarts |

Editing `libapp.so` is the most durable but locating Dart AOT code is genuinely hard. This subject is
large enough to have its own reference: **`references/dart-aot.md`** covers pinning the Dart version,
building a decompiler for exactly that version, the object-pool model and how to index it, the register
and boolean conventions, the three assembly signatures that identify most business logic, the locating
workflow, and how to patch this layer safely.

## Locating logic without symbols

- **Strings first.** User-visible text (dialog bodies, feature labels) is the cheapest anchor in any
  runtime. Find it, then find what references it.
- **Search them in the encoding the runtime actually uses, or you will conclude they do not exist.**
  This is the single most common false negative in cross-platform work. A runtime snapshot does not
  necessarily store text as UTF-8; UTF-16 (little-endian on these targets) is common and entirely
  valid. A UTF-8 search of such a snapshot returns **zero hits**, which reads as "the strings were
  stripped / encrypted, this route is dead" — and that conclusion is wrong.

  ```python
  blob = open('libapp.so', 'rb').read()          # or whichever artifact holds the snapshot
  for phrase in ('<feature label>', '<dialog title>'):
      print(phrase, 'utf-8:', blob.find(phrase.encode('utf-8')),
                    'utf-16le:', blob.find(phrase.encode('utf-16-le')))
  ```

  Try both, and try a short distinctive substring rather than a long phrase. Which encoding applies
  is predictable rather than random: in a Dart AOT snapshot ASCII literals are stored one-byte (a
  UTF-8 search finds them) while CJK / non-Latin literals are UTF-16LE (a UTF-8 search returns zero).
  `dart-aot.md` §7 gives the exact framing, and `scripts/dart_pool_strings.py --find` locates either
  encoding by file offset.
- **A phrase that is absent may simply never exist as one literal.** UI text is often assembled from
  fragments or templates, so "the whole sentence" can be missing while both halves are present.
  Search the shortest distinctive token, and expect the interesting anchor to be a *label* rather
  than a sentence.
- **Landing on a string tells you where the text lives, not which code decided to show it.** Treat the
  hit as an anchor for reference-hunting, not as the answer.
- **Compare two builds.** The same feature in a slightly different version often reveals the code path.
- **Watch the boundary, not the interior.** For cross-platform apps it is usually far cheaper to observe
  what crosses between layers than to reverse the interior of the runtime.
- **Do not assume the obfuscated names are stable or meaningful.** They are not, and treating them as
  identities leads to conclusions that break on the next build.
- **Obfuscated identifiers can be non-ASCII and invisible.** Renaming passes can replace class and
  member names with characters outside ASCII (combining marks, variant selectors and similar). If a
  class exists at runtime but "cannot be found" by the name you read from a decompiler, suspect
  encoding or normalisation in your tooling rather than a missing class. Resolve such members by
  **shape** — parameter counts, types, interface implementation — instead of by name, and prefer
  runtime enumeration of loaded classes over guessing identifiers.

## What this changes about your plan

- Budget for the runtime layer **up front**. If the app is Flutter/RN/Unity, the dex is not the main
  battlefield and a dex-only plan will stall.
- Any behavioural claim must be validated **through the runtime's own UI**, because that is what the
  user sees. A patch that changes internal state without changing the UI is not a fix.
- Keep the layer you are working in explicit in your notes. "Patched the paywall" is meaningless without
  saying which layer owned it.
