# TLS and certificate failures

**Symptom class:** after a repack, login or registration fails with a TLS error while the rest of the app behaves normally. This is the most common way a *correct* patch gets blamed for a *pre-existing, server-side* condition. Work the five steps below before changing a single byte of the app.


**Load this when:** one feature fails at runtime -- login, registration, payment, an API-backed screen -- while the rest of the app works. It gives the five steps that separate a real TLS/certificate problem from the patch you just built.

## Fast path

| # | Action | Evidence |
|---|---|---|
| 1 | Read the full exception chain, prove it is a date rule | `THROW` events from the probe, or logcat |
| 2 | Validate the certificate from a host you trust | `python scripts/tls_check.py <host>` |
| 3 | Compare another host from the same app, and the device clock | same script, `adb shell date` |
| 4 | Decide which trust chain owns the failing request | `RAW-URL` vs `OKHTTP` probe events |
| 5 | Only then patch the system-trust path | fix template below |

## Symptoms

- Login or registration reports a generic network failure: `Network request failed: Chain validation failed`.
- Everything else works: home, feed, images, playback, guest browsing.
- The full chain, visible only if something captures swallowed exceptions:

```
javax.net.ssl.SSLHandshakeException: Chain validation failed
  caused by: java.security.cert.CertificateException: Chain validation failed
    caused by: java.security.cert.CertPathValidatorException: timestamp check failed
```

- `timestamp check failed` is the decisive token. The validator rejected the chain on a **date rule**, not on an untrusted issuer or a hostname mismatch. Exactly two conditions produce it: the certificate is expired or not yet valid, or the **clock of whoever performs the check is wrong**.

## Step 1: get the real host out of the runtime

Never trust a host recovered from strings alone; a build config can hold dead or staging hosts. Get the host the app actually connects to:

- Run the four-layer probe: `scripts/frida_probe.js`, launched and streamed to a log by `scripts/run_probe.py` (setup, version alignment, and hooking strategy: `dynamic-frida.md`). Three event labels carry what you need.
- `RAW-URL`: the request went through `java.net.URL.openConnection` / `openStream`, the system trust path.
- `OKHTTP`: the request went through the app's own OkHttp client, a different trust path.
- `THROW`: the original text of an exception an upper layer caught and swallowed. This is where the real TLS message appears when the UI only shows a generic network error.

Output you need: the exact URL, its host, and which label logged it.

## Step 2: validate the chain out of band (no app involved)

This step is independent of the app, the patch, and the device. It runs on a host whose clock you trust:

```bash
python scripts/tls_check.py <host>              # strict verification + certificate detail
python scripts/tls_check.py <host> <host2>      # compare hosts in one run
python scripts/tls_check.py <host> --json       # machine-readable; exit 2 if any host fails
```

The script validates strictly (system CAs, expiry, hostname) and, when verification fails, still decodes the peer certificate locally, so a failure arrives with a reason instead of a stack trace:

```
EXPIRED            certificate has expired
NOT-YET-VALID      certificate is not valid yet
HOSTNAME-MISMATCH  chain is fine, the name does not match
UNTRUSTED-CA       self-signed, or issuer not in the trust store
CHAIN-BROKEN       bad signature / invalid CA / incomplete chain
```

Interpretation:

- `EXPIRED` reported from a trustworthy clock is proof that the chain is rejected by the certificate itself, not by the device, the network, or your patch.
- A clean pass means the certificate is fine and the failure is a client-side trust decision or a clock problem. Go to Step 3.
- Non-443 endpoint, or an address that needs a different SNI name (an IP connect, a CDN edge): `--port <port>` and `--sni <host>`. Getting this wrong produces a `HOSTNAME-MISMATCH` that has nothing to do with the real problem.

Minimal equivalent, if the script is not at hand:

```python
import socket, ssl
ctx = ssl.create_default_context()              # strict: system CAs, expiry, hostname
with socket.create_connection(("<host>", 443), timeout=10) as raw:
    with ctx.wrap_socket(raw, server_hostname="<host>") as tls:
        print("OK", tls.version())
# on failure: ssl.SSLCertVerificationError: ... certificate has expired
```

Dates, subject, and issuer in one line, if you prefer no script at all:

```bash
openssl s_client -connect <host>:443 -servername <host> </dev/null 2>/dev/null \
  | openssl x509 -noout -subject -issuer -dates
```

## Step 3: compare another host, and check the device clock

Run the same check against every host you extracted from the app, then compare:

- A very common shape: the business API host is expired while the config, image, or CDN host is valid. Same app, same network, same machine, different certificates. That pattern exonerates the network path and points at one certificate.
- Check the device clock; it costs one command:
  ```bash
  adb shell date          # compare against a known-correct time source
  ```
  If Step 2 passes but the device fails, the cause is the device clock, not the certificate. Correcting the clock and relaxing the trust policy are different decisions; do not do both silently.
- Check the **unpatched original** in the same environment. See `verification.md` §the control build rule and `pitfalls.md` P9. If the original fails identically, the patch is not the cause, and no amount of dex work will fix it.

## Step 4: which trust chain owns the failing request

One app can carry two independent trust chains, which is exactly why "login is broken but everything else works".

| Path | Client | Trust configuration | Failure signature |
|---|---|---|---|
| OkHttp | OkHttp / Retrofit, via `newCall` | app-supplied `SSLSocketFactory` + `HostnameVerifier`, often pinning | pin-related messages (`CertificatePinner`, pin verification failed), or nothing at all if the app relaxed it |
| `java.net.URL.openConnection()` | `HttpsURLConnection`, also used by many image loaders, downloaders, and legacy HTTP wrappers | **platform default** trust store and default verifier (`HttpsURLConnection.setDefault*`) | `Chain validation failed` / `timestamp check failed`, the signature above |

Discriminating, in increasing order of certainty:

1. **Probe events.** The failing request appears under exactly one label from Step 1: `RAW-URL` (system path) or `OKHTTP` (app client). This is a fast screen, not proof.
2. **Trust-manager attribution (definitive).** Hook every `X509TrustManager.checkServerTrusted` implementation and print the instance class name plus a short `new Exception().getStackTrace()`. If the caller frames sit in `okhttp3.*`, or in a custom class the app installs on its own client, the OkHttp path owns the failure. If they sit in a platform trust manager reached through `HttpsURLConnection` / `SSLSocket` internals, the system path owns it. Wording alone is version-dependent, so trust the caller frames, not the message.
3. **Cross-check with the fix below.** If OkHttp owns the failing request, the template does nothing for it: that path never reads `HttpsURLConnection` defaults and needs a client-level change (`SSLSocketFactory` / `HostnameVerifier` / pinner; see `dex-patching.md` §where to patch).

Why the asymmetry exists: the app configured its own trust behavior for OkHttp (a relaxed verifier or a pin), so that path never consults the platform date rule, while the legacy `HttpsURLConnection` path still validates against the system trust store and rejects the expired chain.

## Step 5: fix template (system path only)

Install permissive TLS defaults for the `HttpsURLConnection` path at the earliest point of `Application.onCreate()`:

```java
// Call from Application.onCreate() before any other initialization.
private static void installPermissiveTlsDefaults() {
    try {
        javax.net.ssl.SSLContext ctx = javax.net.ssl.SSLContext.getInstance("TLS");
        ctx.init(null, new javax.net.ssl.TrustManager[]{
            new javax.net.ssl.X509TrustManager() {
                public void checkClientTrusted(java.security.cert.X509Certificate[] c, String a) {}
                public void checkServerTrusted(java.security.cert.X509Certificate[] c, String a) {}
                public java.security.cert.X509Certificate[] getAcceptedIssuers() {
                    return new java.security.cert.X509Certificate[0];
                }
            }
        }, new java.security.SecureRandom());
        javax.net.ssl.HttpsURLConnection.setDefaultSSLSocketFactory(ctx.getSocketFactory());
        javax.net.ssl.HttpsURLConnection.setDefaultHostnameVerifier(
            new javax.net.ssl.HostnameVerifier() {
                public boolean verify(String hostname, javax.net.ssl.SSLSession session) { return true; }
            });
    } catch (Exception ignored) {
        // Leave platform defaults in place: pre-patch behavior, no new failure mode.
    }
}
```

Land it as a small utility class plus its inner classes in smali, or as a dexlib2 rewrite that inserts the call at the head of `Application.onCreate` (`dex-patching.md`). Keep it inside the app's own package; do not edit third-party classes.

Why this shape is correct:

- It changes **one** trust decision: the default `HttpsURLConnection` factory and verifier. OkHttp derives its trust manager through `TrustManagerFactory` and its own socket factory, so app-side pinning and verifier behavior is untouched. You are not silently weakening a control the app deliberately added.
- Call it **before any other initialization**. Globals set after the first `HttpsURLConnection` use still apply, but a library that cached a factory reference earlier keeps the old one, which produces a confusing partial fix.
- The scope is still wider than "login". **Every request that goes through `URL.openConnection()`** inherits it, including image loaders, download managers, and older push or analytics SDKs. State that in the report instead of implying you touched one endpoint.
- The `catch` that leaves platform defaults alone is deliberate: the worst case is the behavior you started with.
- This is a **client-side workaround for an external condition**. The correct fix is renewing the server certificate. Say so, and do not present the patch as the fix.

Do not: change the device clock, install your own CA into the device trust store (device-side, harder to roll back, and not part of a shippable artifact), rewrite the request host to a different domain, or reach for `System.setProperty` tricks. Each of them either misses the actual cause or widens the change far beyond the failing flow.

## If OkHttp is the failing path

Then the failure is about the app's own client configuration, not the platform defaults. Typical causes: a pin that no longer matches, a hostname verifier rejecting a changed host, or a custom `SSLSocketFactory` built from a bundled keystore. Locate it the same way (Step 4, item 2) and patch at the client construction site instead of applying the template above. `dynamic-frida.md` covers finding the real construction site; `dex-patching.md` covers the patch layer.

## Method notes

- **Order of investigation is the lesson.** Every piece of evidence above comes from the server, the network, or the platform before anything is attributed to your patch: full exception chain, real host, out-of-band validation, second-host comparison, control build. Only when all of them point at a client trust decision is a patch justified. `pitfalls.md` P16 is this mistake written up as a failure.
- **This is a control-build case, not a patch case.** `verification.md` §the control build rule applies directly: same pipeline, zero patches. If the control fails the same way, stop debugging the patch.
- **Report the residual honestly.** "The server certificate is expired; the client patch relaxes validation on the `HttpsURLConnection` path only, OkHttp is unchanged, the proper fix is on the server" is the useful statement. "I fixed login" is not.
- **Claim strength.** This evidence chain reaches rung 6 on the `verification.md` claim ladder: the mechanism is proven, not merely observed. Say which rung you reached.

## Triage checklist

```
[ ] Full exception chain captured, contains "timestamp check failed"
[ ] Exact host and URL obtained from a runtime probe (not from strings)
[ ] Standalone strict validation run: EXPIRED / clean pass
[ ] A second host from the same app compared (isolates the certificate)
[ ] Device clock checked against a known-correct source
[ ] Original unpatched build reproduces the same failure (control build)
[ ] Failing request attributed to a trust manager implementation, not to a message
[ ] If system path: permissive defaults installed at the top of Application.onCreate
[ ] If OkHttp path: client-level config is the patch target instead
[ ] Delivery notes state the client-side scope and the server-side root cause
```
