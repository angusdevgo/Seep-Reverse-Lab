# Third-party builds — auditing a "cracked" or "modded" APK before trusting it


**Load this when:** the input is a "cracked" or "modded" APK you did not produce. It gives the audit that tells you what was injected, and why such a build is never a patching workbench.

## Why this exists

A modded build of the exact app you are targeting is the most tempting shortcut available:
it appears to prove the goal is achievable, and it may already contain the patch you were
about to write. It is also the single most common source of wasted hours and of real risk,
for two reasons.

1. **It is usually not editable.** Authors who redistribute mods protect them, often with
   more layers than the original app ever had. You cannot treat someone else's build as a
   patching workbench.
2. **Its target-audience behaviour is unverified.** The binary may carry injected components,
   extra endpoints, or embedded credentials. "It runs and the ads are gone" tells you nothing
   about what else it does.

Treat a third-party build as an **untrusted sample to be audited**, never as a baseline.
The useful output of an audit is a decision plus evidence — not a binary you start from.

## Step 1: Can you even edit it?

Find the app's own package prefix (the one that appears in its own class definitions, e.g.
`com/<vendor>/<app>/`) and count how many times it appears as a **defined class** in each
plaintext dex.

```
business-prefix hits per dex:
  classes.dex    0        <- shell
  classes2.dex   0
  classes3.dex   0
  classes4.dex   0
```

Zero everywhere means the business code has been **moved out of the plaintext dexes** — the
build is protected at a level you cannot patch directly, even though it launches and works.
Stop here and treat it as a black box.

Also check the reported dex count against the file count: a manifest-declared app with only
library classes present is the same signal.

## Step 2: How many protection layers does it carry?

Mods frequently stack protection from multiple vendors, sometimes because the author
re-protected an already-protected app. Look for independent, coexisting families:

| Layer kind | Typical static evidence |
|---|---|
| Commercial packer | shell `Application`/`appComponentFactory` in the manifest, a `lib*protect*.so`, encrypted assets, `assets/*.jar` with near-maximal entropy |
| DEX-to-native (dex2c) | a "stub" `lib*.so` containing the tool's name, `EntryPoint`/`protect`-style symbols, and **business class names as strings** alongside a near-empty dex layer |
| Anti-debugging / RASP | strings such as `TracerPid`, `ptrace`, `NoNewPrivs`, `CheckPtraceSelf`, `AntiFrida`, plus a self-protection log path |
| Generic hardening marker files | small text files under `assets/` naming a protection vendor and a protection timestamp |

The practical consequence of an anti-debugging layer is that Frida-based dynamic work will hit
a self-check before it hits your hook. Note it, and prefer static conclusions on such a sample.

## Step 3: What did the author ADD?

This is where the audit earns its keep. Diff against the **original build of the same version**
(referenced as `<original>` below).

### New components

Build the set difference of `activity` / `service` / `receiver` / `provider` declarations,
then check whether each new class name actually exists in the plaintext dexes.

- Class exists and is readable → you can judge its purpose.
- Class name appears **nowhere** in plaintext but shows up inside a native library's strings →
  the logic is in the native/dex2c layer, purpose unknown. Say so.
- Nothing registered with an implicit-launch intent-filter (`BOOT_COMPLETED`, `MAIN`) → it cannot
  be started implicitly, which limits (but does not eliminate) the risk.
- A provider with an `authorities` value containing a package-name rewrite (a suffix/prefix that
  is not the current package) is a strong hint the build was produced by **repackaging or app
  cloning**, not by editing the original.

### New outbound endpoints

Extract every URL/domain/IP from the modded build's `lib/*.so`, `assets/*`, and dex strings,
and subtract the original's set. Any domain that exists **only** in the modded build is the most
important finding in the audit.

Rank what you find:
- A domain that also serves install attribution or update checks is explainable.
- A domain paired with an authorization-looking path (e.g. a `GET...`-style endpoint name
  nearby in the same string neighbourhood) is *not* explainable by de-ad work.

### Embedded secrets

Search native libraries and assets for private-key markers:
```
-----BEGIN ... PRIVATE KEY----- , PRIVATE KEY , PKCS#8 , RSA PRIVATE
```
A **private key shipped inside a client artifact** means its "authorization" or "integrity"
path is not a security boundary — anyone can extract the key. Report it as a red flag on the
build's trust claims, regardless of intent.

## Step 4: Capability picture — read both sides

A native library's import table is only half the story.

- **What it does not have** is meaningful: no `socket`/`connect`, no `execve`/`fork`/`system`,
  no `ptrace`, no installer-session strings → no direct evidence of command execution or
  silent install.
- **What it references** can override that impression: string references to Java-layer
  `java/net/Socket`, `InetSocketAddress`, reflection entry points, or executor services mean the
  capability exists **through the Java layer**, off the native import table.

State findings as "capability present / no evidence of use" rather than "safe" — an import table
is evidence of shape, not of intent.

## Step 5: The verdict

Do not hand back a binary. Hand back a decision with evidence and explicit unknowns.

```
VERDICT: use / use with caution / do not use
EVIDENCE:
  - business code plaintext?           yes/no  (+ counts)
  - protection layers                  list
  - injected components                list, each with purpose known/unknown
  - endpoints present only in this build   list
  - embedded credentials               yes/no
UNCONFIRMED:
  - <each item you could not establish, stated plainly>
```

"Use with caution" is the honest answer whenever a build is un-analysable **and** carries new
endpoints or unknown injected components. Do not upgrade it to "safe" because it launches
cleanly, and do not call it malicious without evidence — both are guesses.

## Using the audit result

Two legitimate outcomes:

1. The audit shows the mod is an honest de-ad of the same version → you may use it to **learn the
   approach** (diff its patch points against the original), but still rebuild from the original
   yourself so the artifact you ship has a known provenance.
2. The audit shows it is re-protected, injected, or un-analysable → discard it and do the work on
   the original. That is usually faster than reverse-engineering someone else's protection *and*
   your target's at the same time.
