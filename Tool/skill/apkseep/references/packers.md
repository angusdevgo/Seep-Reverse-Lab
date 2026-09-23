# Hardened / Packed Targets

Load this when recon says the app's `Application` class is not the app's own, or when edits make the
app die before your code ever runs. Packing is the single most common reason a correct patch appears to
"do nothing", so treat it as its own phase with its own evidence standard.

**Not packed, and still dying?** That is a different layer and a different file:
`code-virtualization-and-custom-linkers.md`. There `Application` is the app's own, the dex is fully
readable, and yet whole classes are `native` declarations and a private loader carries an embedded
validation payload. The single most expensive recon error in this domain is reading "no packer" as
"the code is editable" — check for that shape explicitly before planning an edit.

## What a packer actually does

A shell (jiagu / weapon / leggu / 360 / ijiami / bangcle class) replaces the manifest's
`application android:name` with its own stub. At process start the stub:

1. loads its own native library from a directory it controls (often extracted at first launch),
2. decrypts and loads the real dex, usually from `assets/` or a same-named container,
3. optionally verifies that nothing about the APK, its own components, or the environment changed,
4. only then forwards to the app's real `Application`.

Consequences that shape every later decision:

- **Your code in the app's own dex may never run** if the shell aborts first.
- **The shell's native library is the gatekeeper**, and it is usually the only thing that decides
  "tampered vs clean".
- **The shell's own entry is native**, so Java-level reflection into it is usually a dead end.

## Reading the rejection signal

The most informative failure looks like this:

```
UnsatisfiedLinkError: JNI_ERR returned from JNI_OnLoad in "<app>/.jiagu/lib<shell>.so"
```

Read it precisely: the shell's **own** `JNI_OnLoad` returned `JNI_ERR`. That means the shell
**decided** to refuse — it is not a crash, not a missing library, not an ABI problem. Distinguish it from
the look-alikes:

| Message | Meaning |
|---|---|
| `JNI_ERR returned from JNI_OnLoad in <shell>.so` | shell actively refused (integrity or environment) |
| `dlopen failed: library "X" not found` | a dependency you added does not exist — **your** bug |
| `CANNOT LINK EXECUTABLE` / relocation errors | ELF you produced is malformed |
| `ClassNotFoundException` during `Application` init | a manifest component you renamed no longer resolves |

This distinction matters more than it looks: several classes of "the shell rejected me" are actually
self-inflicted. Always grep the crash for `linker`, `CANNOT LINK`, `dlopen` and `not found` **before**
concluding that the shell detected anything.

## Map the validation boundary with single-variable tests

Do not guess what the shell checks. Measure it. The only reliable method is one change at a time, each
with its own install-and-launch run:

1. **Baseline control** — repack with no changes at all, re-sign, install, launch. If this fails, stop:
   your pipeline is the problem, not the shell.
2. **Existing file, semantically inert change** — flip one byte in a section that nothing reads
   (a `.comment` string, a duplicated `DT_NEEDED` entry). Survives ⇒ edits to existing files of that
   class are allowed.
3. **New file added** — add one benign ELF under the native library directory. Very commonly this alone
   is enough to trip a check, which is a distinct policy from (2).
4. **Component rename in the manifest** — equal-length rename of one lazy component
   (an `activity`). Survives ⇒ you have a cheap way to neutralise features.
5. **Structural change** — move a program header table, add a segment, add a relocation.

Record every result. The boundary is usually **not uniform**: typical real outcomes are
"existing native libraries editable, new ones not", "activities renamable, providers not",
"this dex fingerprinted, that container ignored".

### Why one variable at a time is not optional

The most expensive mistake in this phase is testing two hypotheses in one build. If you both edit a
shell component **and** add a library, and the app dies, you have learned nothing — and you will likely
blame the wrong one, discard a viable route, and lose hours (or in this skill's history, dozens of
rounds) re-deriving what a cleaner experiment would have shown in one run.

### Component-type rules worth knowing up front

- **Providers are instantiated by the system during process start.** Renaming one so its class no
  longer resolves fails inside `Application.onCreate` and kills the process before anything else runs.
  Providers are therefore a poor rename target; prefer disabling the feature that consumes them, or
  hooking it.
- **Activities and services are resolved lazily**, only when actually used. Renaming them is a cheap,
  low-risk way to make a feature unable to display, and it survives most integrity checks because it
  changes nothing about the shell.
- **Equal-length renames** keep binary XML chunk structure valid, so no manifest re-encoding is needed:
  replace the name bytes in `AndroidManifest.xml` in place, size unchanged.

## Native libraries as a place to live

When the shell blocks dex-level changes, native libraries often remain open — but only some of them are
useful. A library is a valid host for your code **only if all three hold**:

1. **It is actually loaded** in the scenario you care about.
2. **It is editable** (per your boundary map above).
3. **Something in it is called early enough** to matter.

Condition 1 is the one people skip, and it is the one that wastes the most time. A library shipped in
the APK is not necessarily loaded. **Check `/proc/<pid>/maps`** after a real launch rather than assuming:

```
grep -o '/[^ ]*\.so' /proc/<pid>/maps | sort -u
```

Libraries belonging to optional SDKs are frequently lazy: they exist, they may even be unpacked to disk,
and they are never mapped during the startup path you are trying to influence. Unpacked-but-unmapped is
the signature of a lazy SDK, not evidence that your file was rejected.

Pick a host that is (a) present in `maps`, (b) exports a JNI entry point the runtime must call, and
(c) editable. A library that exports `JNI_OnLoad` and appears in `maps` is the strongest candidate,
because the runtime calls `JNI_OnLoad` on its own, without any trigger from you.

## Where integrity evidence actually comes from

Shells commonly check a mix of: APK signature, `AndroidManifest.xml`, their own native libraries, the
dex they load, and environment signals (root, emulator, hooking frameworks, debugging).

Practical consequences:

- **Your own re-signing is itself a detected change** in most signature-based schemes. Assume any
  signature check will see your build as tampered and plan around it rather than hoping otherwise.
- **The environment matters.** Hooking frameworks, debugging, and non-standard filesystems are commonly
  probed. A patch that works on a clean device may be refused on a rooted one, and vice versa.
- **Absence of a log line is not absence of a check.** A shell that fails silently looks identical to a
  shell that never checked.

## Locating what the dialog/detection is attached to

Blocking dialogs ("tampered", "third-party environment", "abnormal") are the usual user-visible symptom.
Establish **which layer draws it** before trying to suppress it:

- If it is a Java dialog, hooking the dialog class shows a caller stack that names the detection.
- If hooking the dialog classes produces **no** hits, the UI is likely drawn by a cross-platform runtime
  (see `framework-runtimes.md`) or by native code, and Java-level hunting is the wrong axis entirely.

The cheapest high-value experiment, and one that is routinely skipped: run the **unmodified official
build** and the **repackaged build** through the *same* probe and diff what differs. The difference is
your detection signal. Doing this early is far cheaper than enumerating candidate checks one by one.

**When the symptom is a death rather than a dialog** — the process disappears, hangs, or dies at a
roughly constant time after launch — the check is not drawing anything, it is terminating. The
question then becomes *which mechanism*, and the answer decides the whole approach:
`native-tamper-and-suicide.md` covers how to tell an imported terminate call from an **arranged
fault** (which calls nothing and therefore defeats every PLT-level fix), how to find the site, and
why making a routine "not return" freezes the process instead of suppressing the check.

## Reporting

State the boundary you measured, the evidence for each entry, and what remains untested. "The shell
rejects X" must always carry the run that proves it, including the exact failure string. An unverified
claim about integrity behaviour is worse than no claim, because it silently removes routes from
consideration.
