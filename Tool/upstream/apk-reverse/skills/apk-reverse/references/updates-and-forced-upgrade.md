# Updates and forced upgrade

Load this whenever the deliverable is a patched build that must **keep working over time** — which is
almost always. A build that is correct on the day you ship it and dead a week later has failed, and the
cause is nearly always an update path you did not neutralise.

This is the file that decides whether a patch is *durable*, and it is cheap: the whole job is usually
one or two edits.

## Why this is not optional

Three independent failure modes, all of which present as "the mod stopped working" with no obvious link
to updates:

1. **Forced upgrade.** The app checks a version endpoint, sees a newer build, and blocks its UI behind a
   non-dismissible dialog until the user installs the official (unpatched) package. Your patch is gone.
2. **Self-update install.** The app downloads an APK and hands it to the package installer. Because the
   downloaded build is signed differently, the install either fails or — worse — succeeds and replaces
   your work.
3. **Silent "compatibility" downgrade.** The server decides the client version is too old and starts
   omitting fields or returning an error page. No local code changed, so nothing local looks broken.

A fourth case is a **resource / hot-update channel**: the app fetches a bundle (JS, a Dart/RN patch, a
config blob, a plugin APK) that can reintroduce the behaviour you removed. That is a separate code path
from version checking — handle it explicitly if the app has one (see §Step 5 below).

## Step 1: locate the check

There is usually exactly **one** update service. Find it before patching anything else.

**From the client's own vocabulary** (works on any runtime):

```
update / upgrade / new version / check version / force update
版本更新 / 检查更新 / 发现新版本 / 立即更新 / 强制更新
```

Search those in the app's string table and in class names; on heavy runtimes search the string pool,
remembering its encoding (see `framework-runtimes.md` §Locating logic without symbols — searching only one encoding
misses half your hits, and "nothing found" is usually the encoding, not an absence).

**Signals that a version check exists even if you cannot read the strings:**

- A network call early in startup whose response contains a version number, a download URL, and
  sometimes a `force` / `must` / `minimum` flag.
- A stored "last update check time" preference (throttling a check implies one exists).
- The app ships the package installer path or requests `REQUEST_INSTALL_PACKAGES`.
- A permissions/manifest entry for an "unknown sources" install intent.

**Also look for the *coupling*.** Update checks are frequently run from the same startup routine as ad
loading and splash dismissal, and a blocking update dialog often **suspends those siblings** — you may
find logging that literally says so ("update dialog showing, skipping X"). That tells you both where the
check lives and that your patch must not leave the dialog state machine half-finished.

## Step 2: classify the shape

| Shape | How it behaves | Where to cut |
|---|---|---|
| **Optional update** | a dismissible prompt with a download button | suppressing the dialog is enough |
| **Forced update** | non-dismissible; blocks the app | must be cut at the decision, not the dialog |
| **Silent version gate** | no dialog; features degrade or the server 400s | client-side is *not* fixable — see §the honest answer |
| **Self-update installer** | downloads and installs an APK | cut the check, and ideally the install path too |
| **Hot-update / resource patch** | fetches a bundle that can restore behaviour | separate route; treat as a data channel |

Assume **forced** until you have evidence otherwise, because that is the case that costs the user the
most when missed.

## Step 3: patch the decision, not the dialog

**Prefer the earliest safe exit over every downstream surface.** Supressing the dialog only hides it;
the download may still start, and a later code path may still act on the "new version" verdict.

Two layers, in this order:

**Layer 1 — make the check itself a no-op.** Replace the entry of the update routine so it returns
immediately. Nothing is requested, nothing is compared, no dialog state is created. This is the root fix
and it removes the network call entirely, which also makes verification trivial (Step 4).

**Layer 2 — neutralise the comparison.** Somewhere the client compares the server version against its
own and branches on the result. Force that branch to the "already current" side. This catches any path
that reaches the comparison without going through the entry you patched (a second caller, a manual
"check for updates" button, a settings screen).

Layer 2 alone is a valid minimal fix if Layer 1 is awkward; Layer 1 alone is valid if you have confirmed
a single entry. **Doing both is cheap insurance and is what makes the claim "this build cannot be
upgraded into uselessness" defensible.**

```
target routine:  <updateChecker>(...)          -> return immediately (no request, no state)
target branch:   <versionCompare> result       -> force the "no update" side
```

**Do not** patch the dialog itself as your primary fix, and **do not** patch the comparison to lie in
the *other* direction (claiming an update when there is none) — that produces exactly the blocking
dialog you are trying to avoid.

### What not to touch

- **Do not rewrite the app's own version number** in the manifest or in a version string. It is the
  cheapest-looking fix and it breaks things you are not looking at: server-side feature negotiation,
  analytics, cached asset keys, and the app's own self-comparison. Change the *decision*, not the
  identity.
- **Do not strip the installer permission** unless you have checked nothing else uses it.
- **Do not block the update hostname at the transport layer.** That is the same class of mistake as
  blocking ad hosts (`pitfalls.md` P5): it fails offline/online transitions, needs a helper on the
  machine, and is not a property of the artifact. It is also not required — the check is local code.

## Step 4: verify

Update paths are checked once at launch, so verification is a single clean cold start:

1. **Clear logs, cold start, and grep for the update vocabulary.** Expect **zero** hits. Not "quieter" —
   absent. If the routine still runs, the string will still appear.
2. **Watch the screen through startup.** The failure mode is a modal, so a sample you did not look at is
   not evidence (`environment.md` §look at the screen). A blocking dialog is unmistakable and it will be
   on screen for a long time.
3. **Check the network.** With the check disabled there should be **no request** to the version/update
   endpoint at startup. This is the strongest signal: it distinguishes "dialog suppressed" from "check
   never happened".
4. **Exercise the manual path** if the app has a "check for updates" entry in settings — that is the
   caller Layer 2 exists for.
5. **Confirm what you disabled is only updates.** The update routine sometimes shares a bootstrap with
   other startup work. If you no-op'd a routine rather than its decision, verify that splash dismissal,
   first-run setup, and the ad/consent flow still complete.

**Two-sample rule for the durability claim.** If you are asked whether the build *survives* a server-side
version bump, you cannot test that directly. What you can honestly claim is: *(a)* no version request is
issued at startup, and *(b)* the comparison no longer reaches its "newer" branch. State it in those terms
instead of asserting the future.

## Step 5: hot-update and resource channels

If the app can fetch a bundle at runtime, version checking is not the only way your change can be undone.

- **What to look for**: a startup fetch of a signed bundle/zip/config with a version or hash, a local
  unpack directory, a dynamic plugin loader, or a JS/Dart/RN patch channel.
- **Why it matters**: even with updates disabled, a remotely fetched config can re-enable a feature, and
  a fetched bundle can overwrite patched logic in the parts it owns.
- **Handle it like a data channel, not like an update**: identify what is fetched, whether the patched
  behaviour is inside that payload, and cut the consumption point if it is. If the patched logic lives in
  the shipped artifact and the fetched payload cannot override it, say so and move on — that is a
  finding, not a gap.

Note the flip side: a **server-issued configuration** is the same category. If the thing you removed was
driven by remote config, the client patch holds only while the server keeps sending that config — see
`references/server-config-and-updates.md` §6 and `references/membership-and-limits.md` for the general
rule that *client-side enforcement can be patched, server-side authority cannot*.

## The honest answer for silent version gates

If the app degrades because the **server** decides the client is too old — no local dialog, just missing
data or errors on some screens — then there is no client-side fix. The only honest report is:

- the version the client reports to the server (with evidence of where it is read),
- the endpoint that makes the decision (with the observed response),
- and a clear statement that this is server-side authority.

Do not paper over it by forcing the version string at random read sites. If you do change a reported
version as an experiment, label it experimental, and remember that a version number is used in more
places than the one you are looking at.

## Delivery note: always state what was disabled

Update suppression changes behaviour a user can observe ("it never tells me about new versions"). Put it
in the delivery notes, in one line, together with anything else you neutralised. If the app also has a
legitimate reason to update (security fixes), say that the build will not pick them up automatically.

## Step 6: when the check is not where you expect

Three shapes that break the "find the Java comparison and flip it" plan. Recognise them early,
because each has a different cheapest remedy.

### The check is native

Symptom: you grep the whole dex tree for the version-comparison routine, the update endpoint, or the
dialog text and find **the method declared, and zero callers**. A `static native` update entry point
with no Java caller means the invocation lives in a `.so` (`registerNatives` from a static block is
the usual giveaway — see `code-virtualization-and-custom-linkers.md`).

Options, cheapest first:

1. **Attack the response, not the check.** Block or rewrite the update endpoint at the network layer,
   or empty the version/config response. The native code still runs and still decides "no update".
   This needs no native work at all and survives a rebuild — check this before reaching for a
   disassembler.
2. **Send the check a version it likes.** If it compares against a value the app itself supplies
   (a config key, a stored preference, a build field), setting that value is a one-line change.
3. **Patch the native comparison.** Last, because it is the most expensive and the most fragile.

Do not conclude "unpatchable" from "no Java caller". The gate usually reads a value you *can* control.

### The update hands off to a browser or a WebView

Very common in this category: the dialog's button fires an `ACTION_VIEW` intent at a download URL,
or loads it in an in-app WebView. Two consequences:

- **You will not find an installer call** in the app, so searching for `PackageInstaller`,
  `REQUEST_INSTALL_PACKAGES` or a download service finds nothing. That is not evidence the dialog is
  harmless; the browser does the install.
- **Logcat truncates the URL.** `ActivityTaskManager` prints `dat=https://host/...` and elides the
  rest, so a naive grep gives you a host and no path. Do not build a plan on a truncated URL.

Ways to get the real URL, cheapest first:

| Approach | Notes |
|---|---|
| Hook `Intent` construction / `Context.startActivity` and log `intent.getDataString()` | Most reliable. A truncated log line is a *logging* limit, not a limit on what you can read |
| `dumpsys activity activities` / recents while the browser is still in the stack | Free; works only if the activity is still alive |
| The browser's own history database (root) | Survives the browser being closed; needs the right DB, and modern browsers may encrypt or prune it |
| Read the update *response* instead | Often easier: the URL came from a JSON field you can fetch or hook directly |

**Deliberately tapping the button is a legitimate probe** — but treat it as a measurement, not a
side effect: capture the intent (or the screen) in the same window, and know that on some devices a
second tap resumes an already-started download rather than re-issuing the intent.

### The gate is server-issued with a local fallback

`fetchEnabled()`-style helpers frequently **default to a local value on any failure** (non-200,
timeout, malformed body, signature mismatch). Two things follow:

- **Read the failure branch before you touch anything.** If failure ⇒ "no update" or "no ad", then
  merely making the request fail is a complete fix, and it is far cheaper and more robust than
  patching the comparison.
- **The fallback also tells you how to test offline.** Disconnect the device and relaunch: if the
  gate disappears, the fallback is benign and you have a zero-code workaround as well as a
  verification signal.

Conversely, if failure ⇒ "must update", failing the request makes things worse, and you must patch the
decision instead.

## Checklist

- [ ] Update vocabulary searched in **both** string encodings, in the right layer for the runtime
- [ ] The single update entry point identified (or its absence established, with evidence)
- [ ] Shape classified: optional / forced / silent / installer / hot-update
- [ ] Decision-level patch applied, not just the dialog
- [ ] Comparison branch neutralised as a second layer
- [ ] Manifest version and identity left alone
- [ ] Cold start: **zero** update log lines, no blocking modal, **no version request on the wire**
- [ ] Manual "check for updates" entry exercised
- [ ] Startup siblings (splash dismissal, ads, consent, first-run) still complete
- [ ] Hot-update / remote-config channel considered explicitly
- [ ] Delivery note states what is now disabled
