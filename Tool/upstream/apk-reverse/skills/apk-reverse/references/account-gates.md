# Account gates: sign-in walls, forced binding, guest mode

Load this when the task mentions "no login required", "don't force me to sign in", "skip phone
binding", "guest mode", or when a screen is unreachable without an account — and also **before**
promising that any account- or membership-derived feature will work offline.

This file is mostly about **telling apart two things that look identical in the UI and are completely
different in reality**:

- a **client-side gate** — code that refuses to proceed. Patchable.
- an **account-scoped resource** — the screen is empty because the server sent nothing, because the
  request was made without a valid identity. **Not** patchable.

Confusing the two is how a task ends up "done" while the user stares at an empty page.

## Step 1: classify what you are looking at

| Symptom | Most likely cause | Can a client patch help? |
|---|---|---|
| A dismissible dialog / bottom sheet asking to sign in, then the app works | client-side gate | **yes** |
| A full-screen wall with no dismiss, app unusable | client-side gate | **yes** |
| Screen renders its frame but the list is empty and a "log in to see" hint is drawn | **account-scoped data** | no — the data does not exist locally |
| A specific action (comment, favourite, follow, download) refuses | client-side gate | usually yes |
| The action succeeds locally but reverts on restart / never reaches the server | **server-side identity** | no |
| "Binding required" before an action | client-side gate | **yes** |
| An entitlement appears then disappears | server-side authority | no |

**The deciding question is never "is there a login screen?" — it is "does the thing I want exist
without an identity?"**

Ask it before patching:

- If the content is **fetched per-account** (subscriptions, favourites, reading history, purchased
  items), a patch changes the gate and nothing else. The list stays empty because the server was asked
  for *this account's* items and there is no account.
- If the content is **public** and merely hidden behind a prompt (a reader, a catalogue, a settings
  page), the patch is real and the feature becomes usable.

Reading the code tells you which: follow the "sign in" prompt to what it guards, then look at whether
that guarded path issues a request carrying a token, or touches only local state.

## Step 2: find the convergence point

Sign-in checks are usually concentrated, because a UI cannot meaningfully enforce login at thirty
call sites. Look for a small number of helpers with names in this family:

```
checkLogin*   ensureLogin*   requireLogin*   needLogin*   isLogined*   isLoggedIn*
checkBind*    ensureBind*    requireBind*    needBind*
showLogin*    openLogin*     loginSheet*     loginDialog*
```

and, on the state side, a **login-state field or stream** that every helper reads
(`isLogin`, `loginedStream`, an `Rx<bool>`, an auth-state enum, a credential store wrapper).

**Rule: patch the predicate, not the prompt.** Making the sheet not appear is cosmetic — the caller
still treats the answer as "not signed in" and takes its else-branch, which is usually where the real
feature got skipped. The durable fix is to make the *verdict* come back as "signed in / no sign-in
needed", so the caller takes its happy path.

Two useful shapes, both better than editing the dialog:

| Target | Change | Effect |
|---|---|---|
| the gate predicate used by many callers | return "ok / already signed in" unconditionally | every caller proceeds; no new code path |
| the "should I prompt?" decision inside the helper | return "nothing to do" | the prompt never appears and callers proceed |

Prefer the first when callers branch on the result; prefer the second when the helper is fire-and-forget.

**Count the callers before choosing** (`scripts/find_refs.py`). A predicate with one caller is a
surgical target; a predicate with forty callers is a behavioural change you must reason about — it will
also release flows you were not asked to touch (settings, purchase, upload). That may be fine, but it is
a decision, not a side effect.

### Forced binding specifically

Phone binding is the same pattern with its own helper and usually **two** state checks in series
(bound-phone? and email-or-other-recovery?), because either satisfies the requirement. Patch the
combined verdict, not the first condition — a patch that only satisfies one branch still prompts on the
other.

Watch for a **"skip"/"later" path the app already has**, and for **which actions the binding actually
gates**. Binding is often required for a subset (password change, deletion, payment) while the rest of
the app is unaffected; releasing it globally changes what the app believes about account safety.

## Step 3: what NOT to do

These are the tempting moves that produce a worse artifact than doing nothing:

- **Do not fabricate a session.** Writing a dummy token, a fake credential blob, or a placeholder
  identity into the credential store makes the client *believe* it is signed in. It then calls
  identity-scoped endpoints with garbage, and the app enters a state that is **worse than signed out**:
  screens show an authentication-failure message, or silently return empty data with no explanation.
  A signed-out app that says "please sign in" is better than one that claims a session and fails.
  *(If you touch stored credentials at all, keep a backup and expect to have to restore it.)*
- **Do not delete the sign-in UI.** Removing the entry point does not change the verdict; it only makes
  the failure unexplainable when a caller does branch on it. Keep the entry point working — it is
  normally an explicit requirement ("signing in must still be possible").
- **Do not release gates that protect server-side operations.** If the action's result is an
  entitlement the server must grant (a purchase, a quota, a subscription), releasing the client gate
  only lies to the UI. See `references/membership-and-limits.md`.
- **Do not assume "guest can browse" means "guest can do everything".** Establish per feature which of
  the three states you are in: public, gate-only, or identity-required.

## Step 4: the session-loss problem (this one is unavoidable)

Any change to the signing identity — including a plain reinstall of *your own* build — can invalidate
stored credentials, because they may be sealed with a key held by the platform keystore rather than by
the app.

**What you observe:** the app opens fine, then one subsystem reports it cannot decrypt or unwrap
something, or the user is silently signed out.

**What it means:** the app's private data was carried across an uninstall/reinstall (or restored from a
backup), but the encryption key was destroyed with the app. The ciphertext is now unopenable by anyone.

**What to do:** treat "the user signs in once on the new build" as the expected, documented outcome — not
as a defect to fix. Put it in the delivery notes in one line, together with the fact that a later
upgrade over the *same* signing key can be installed without uninstalling, and therefore will not lose
the session.

**Do not** chase this into the keystore. Restoring the old key is not part of packaging a patched build,
and any workaround that keeps the *old* ciphertext alive while the key is gone is a dead end.

Related and worth knowing: an app may keep the same logical account in **two places** — a plain
preference blob and a sealed store. After a reinstall the plain one survives and the sealed one does
not, which shows up as an account that is half-present (identity fields populated, token empty). That
half-state is a useful diagnostic: it tells you the app reads its identity from the sealed store, which
is exactly the thing you must not try to forge.

## Step 5: verify

The claim to support is narrow and should be stated narrowly.

1. **The prompt does not appear** on a cold start and on the screens that used to show it.
2. **The feature behind it actually works**, not merely "no longer blocked": open the reader, the
   catalogue, the settings page — whatever the gate guarded — and confirm real content or real function.
3. **The sign-in entry still exists and is usable.** Signing in with a real account must still work; that
   is usually part of the request, and it is the thing that proves you patched a gate rather than broke
   authentication.
4. **Signed-in behaviour still works** for a real account, so you can tell the difference between
   "released the gate" and "broke the auth path".
5. **No fake-session artefact is left behind** — check that you did not write anything into the
   credential store or preferences. If you did, remove it and re-verify from a clean install.

State the result as: *"the gate no longer blocks X, from a signed-out state; **the content behind it is
public / the content behind it is per-account and therefore still empty when signed out**."* That second
clause is what stops a client patch from being mistaken for an account.

## Reporting template

```
Gate:             <sign-in sheet | binding prompt | action-scoped check>
Class:            client-side gate  /  account-scoped data (not patchable)
Patch:            <predicate or decision, not the prompt>
Signed-out state: <what works now, per screen>
Signed-in state:  <still works, listing what still requires an account>
Not achievable:   <per-account lists, entitlements — with the reason>
Session note:     sign in once after install; upgrade over the same key keeps the session
```
