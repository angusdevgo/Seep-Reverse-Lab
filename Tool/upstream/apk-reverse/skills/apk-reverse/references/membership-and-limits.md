# Membership, paywalls, and the honest limits of client-side patching

Read this **before** investing hours. Most "unlock VIP / remove the paywall" requests cannot be satisfied by patching the client, and knowing that early is the most valuable output you can produce.

## First question: who decides?

| Signal | Owner | Client patch can... |
|---|---|---|
| A local boolean/int/string field in an app model, computed locally | Client | Fully determine the outcome |
| A field that comes from an API response and is merely *read* by the UI | Server | Change display only — not access |
| Download/stream/play URLs issued by an API | Server | Nothing. You cannot mint a valid URL. |
| Entitlement checked on every protected action with a server round-trip | Server | Nothing |
| A local cache of a server value | Server (cached) | Temporarily fool the UI until it refreshes |

**Decision rule:** if the thing you want (a media URL, a decrypted payload, premium data) is *delivered by the server*, the client is not the gate. The gate is server-side and is not patchable.

## How to prove it in minutes

Do not guess. Test the API directly (`references/server-api.md`).

```
1. Call the protected endpoint with no credentials.       -> 401/403 means auth-gated
2. Call it with an obviously forged token.                -> another 401 confirms it is validated
3. Call the metadata endpoint.                            -> often 200, giving you the shape,
                                                             but deliberately omitting the asset URL
4. Compare: is the valuable field simply absent?           -> then no client change can invent it
```

A concrete, real result pattern worth remembering:

- `GET /videos/{id}` → **200**, full metadata, cast list, source list — **but no playback URL at all**
- `GET /v2/sections/{id}/play-url` → **401** with no token
- same, with `Authorization: Bearer <forged>` → **401**
- `GET /user/me` with forged token → **401**

That combination is conclusive: metadata is public, the asset URL is server-minted, and the token is verified. **Client-side patching cannot unlock it.**

## What *is* legitimately achievable client-side

Don't overclaim, and don't underclaim either. Genuinely client-side wins:

- **Remove ads / SDKs.** Ads are a client behavior (`references/ad-removal.md`).
- **Remove a UI gate** where the underlying data is already delivered and only a local check hides it (a "locked" tab whose content is already fetched, a disabled button).
- **Skip promotional interstitials and self-promo popups** driven by local flags.
- **Unlock client-only features**: debug menus, extra player settings, higher local bitrate selection, gesture options.
- **Grant a client-side reward** only if the reward is neither validated nor authoritative server-side (check first — a reward that later fails server validation is worse than no reward).
- **Bypass a client-side trial timer** whose enforcement is purely local (but expect the server to re-assert on next sync).

## What is NOT achievable, and how to say so

- **Paid content whose URL comes from the server.** State it plainly and show the 401 evidence.
- **Server-validated rewards / purchases / credits.**
- **Anything the server re-checks on the next request.** The patch may look like it works for one screen and then silently revert.

Wording that is both honest and useful:

> The client cannot unlock this. Metadata is public, but the asset URL is issued by the server, and the endpoint returns 401 for both anonymous and forged credentials — so no local change can produce a valid URL. What *is* removable client-side is X, Y, Z. To actually get access you need a real account with the required entitlement.

## The fake-VIP trap

Forcing a local `isVip()`-style method to return `true` is the classic mistake. Two failure modes:

1. **Cosmetic only** — UI shows VIP styling, but protected actions still fail server-side.
2. **Actively harmful** — the client now believes it holds entitlements it does not, so it enters code paths that expect server data it never receives. Observed result: **blank screen** (process alive, nothing rendered, only a swallowed uncaught exception in the crash buffer).

If you patch such a method, patch it in a **conservatively correct** way, and verify all screens, not just the one you cared about:
- Do not fabricate entitlements that gate data fetching.
- Prefer patching *presentation* consumers of the flag over the flag's computation, if the flag is also used for access decisions.

## Local state vs code — the deliverable question

A value can be "fixed" in two places:

| Where | Survives fresh install? | Fits an APK deliverable? |
|---|---|---|
| Code (patched dex) | Yes | Yes |
| App data (datastore/prefs/db) | **No** | No — unless you also patch the read path |

If a fix works on your device but a user reports it gone after reinstall, this is why (`references/pitfalls.md` P11). Re-implement the fix by patching the **read path** so it always yields the desired value.

## Reporting template

```
Goal:            <what the user asked for>
Gate owner:      client | server | mixed        (evidence: ...)
Achievable:      <list, with evidence each>
Not achievable:  <list, with the 401/absent-field evidence>
Residual:        <what remains and the exact coupling that prevents removing it>
Verified on:     <device, build hash, what was exercised>
```
