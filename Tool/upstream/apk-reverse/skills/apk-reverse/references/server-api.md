# Server-side analysis — deciding whether a patch can even matter

If the behavior you want to change is produced by a response, patch the client all you like: nothing real changes. Establishing server authority early is the cheapest high-value step in any "crack this" task.

## Harvest the API surface from the client

```bash
python scripts/dex_strings.py <dex_dir> --urls
python scripts/dex_strings.py <dex_dir> --find 'https?://'
```

Collect: base URL(s), path constants, auth headers, and any dynamic-gateway mechanism.

Two patterns to watch for:

- **Static base URL** — straightforward.
- **Dynamic gateway** — the real host is fetched at runtime (commonly a DNS TXT record over DoH, or a small config endpoint). The hardcoded host may be a fallback. Symptom: requests go to a host that differs from anything in the dex.
  ```bash
  # TXT lookup, the usual shape:
  #   https://<doh-provider>/resolve?name=<domain>&type=txt
  # returns something like  "https://<gateway-host>"
  ```
  This is an anti-blocking technique; it does not block repacking, but it means your static host guess may be stale.

## Reproduce requests faithfully

```bash
python scripts/probe_api.py --base <base_url> --path /some/path --header 'X-App-Name: <value>'
```

Rules that make the difference between 403 and 200:

- **Send the app's real headers.** A single custom header (e.g. an app-name header) frequently decides whether a WAF lets the request through. The header value is a string constant in the dex.
- **`User-Agent` matters** — often `okhttp/x.y.z` or a runtime-specific default (e.g. `ktor-client`).
- **Watch for a CDN/WAF in front.** A 403 with an HTML body naming a WAF means your request shape is wrong, not that the endpoint is gone. Compare with what the app sends (capture it from the device).
- **Beware your own egress.** If your host goes through a proxy/VPN, a WAF may block by geography while the device succeeds. Do not conclude "the server rejects the app" from a host-side 403.
- **`/health`-style endpoints are gold** — a 200 with a small JSON body proves the backend and its response envelope are alive before you debug anything else.

## Response envelope

Most apps wrap responses uniformly, e.g. `{"code":0,"msg":"","data":{...}}`. Learn it once, then read endpoints by shape rather than guessing:

- `code != 0` + a message → business error, and **the message often enumerates valid inputs** (this is how an ad `position` whitelist was discovered).
- `data:null` with HTTP 200 → soft failure.
- `401` with a null envelope → auth gate.

## Prove who owns the gate

Run this matrix and record it. It is the single most decisive artifact for a paywall or entitlement question.

| Request | Expected if client-owned | Expected if server-owned |
|---|---|---|
| protected endpoint, no credentials | would still succeed | **401 / 403** |
| same, with a forged token | would still succeed | **401 / 403** |
| metadata endpoint | — | 200, often **omitting** the protected field |
| list/config endpoints | — | 200 with data |

If the valuable field is simply **absent** from an otherwise-200 metadata response, no client change can invent it. Say so, with the evidence.

## Also test the *unknown input* case

When you plan to change a request parameter (a path, a `position`, an id), probe what the server does with an **invalid** value first:

- A `400` with a validation message tells you the field is whitelisted, and hands you the full list of valid values.
- A `404` tells you the path is exact.

**This matters before you patch**: redirecting a parameter to an invalid value may produce an error status that the client treats as fatal (`pitfalls.md` P5). Knowing the failure mode in advance prevents breaking the app.

## Behaviors that help you and behaviors that do not

**Repack-friendly (do not block you):**
- Minimal auth: `Authorization: Bearer <token>` and a static app-name header, with **no request signing, no nonce, no HMAC**.
- No client-certificate pinning to the app's own signature.

**Repack-hostile (will break a re-signed client):**
- Signature/certificate checked server-side, or pinned in native code.
- Request signing derived from the APK signature — the client computes with its own
  certificate, so re-signing changes the key. Silent and easy to misdiagnose; detection,
  extraction and the differential test are in `references/signature-derived-keys.md`.
- Device attestation (Play Integrity / SafetyNet, OEM attestation).

Determine which you face **before** shipping a repack. A client that authenticates fine on first launch but silently fails features later is the classic signature-validation symptom — and when computed signing parameters (`sign`, `_p`, `uth`) evaluate to `-1` or empty, it is the signature-derived-key case rather than a server decision.

## What to record

```
base url / gateway mechanism
required headers (exact values)
auth mechanism (token? signed? attested?)
response envelope shape
endpoints actually used, and their auth requirement
protected-asset endpoints, with status codes for: none / forged / (real if available)
invalid-input behavior for any parameter you plan to change
```
