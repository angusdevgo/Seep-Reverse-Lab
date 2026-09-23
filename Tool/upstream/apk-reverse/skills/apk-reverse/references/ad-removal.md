# Ad removal

Goal: ads stop appearing, and **nothing else breaks**. Read `pitfalls.md` P5 and P6 before patching anything here.


**Load this when:** an ad, promo, splash or rewarded video must stop appearing, or an ad-related SDK was found in recon. It gives the enumeration step that decides *which* layer the ad lives on, then the removal per layer.

## Step 1: enumerate what "ads" means in this app

Do not assume "ads" is one thing. Enumerate first.

**SDK-integrated ads** (the app calls an SDK):
- Search dex strings for SDK markers: `openadsdk`, `TTAdSdk`, `TTAdNative`, `Pangle`, `pangolin`, `com.qq.e`, `GDTAd`, `gdt_plugin`, `anythink`, `ATSDK`, `ATRewardVideoAd`, `bdxadsdk`, `sigmob`, `ksad`, `mobads`, `beizi`.
- **Aggregators** (AnyThink, TopOn, and similar) are wrappers: the ad networks underneath are *their* adapters, not app code. Patching an individual network's class is usually pointless; the aggregator still runs and still reaches the network.
- The app almost always funnels every call into **one wrapper class**. That class is the patch surface (Step 2).

**Dynamic-plugin ad SDKs** (the SDK is not in the APK). Aggregators increasingly ship as a runtime plugin: the app downloads an APK on first launch into its private directory and loads it through a plugin classloader.

```
/data/data/<app.package>/files/<sdk>_p/<plugin.pkg>/version-*/apk/base-1.apk
/data/data/<app.package>/files/<sdk>_p/<plugin.pkg>/version-*/lib/<abi>/*
```

- Consequence: **deleting bundled `assets/`, `lib/*.so`, or the SDK's classes from the dex does not kill this SDK.** The loader re-downloads on the next launch, and a half-deleted plugin is worse than an intact one.
- The kill switch is the **init gate** (Step 2). Killing init also prevents the working directory from ever being created, which is the strongest verification signal available (Step 4).
- The plugin may also be bundled. Two copies still means one init gate; patch that, not the payload.

**Server-driven ads / sponsored content** (the server returns the ad, the client renders it):
- **This is the most common shape in a modern app, and it is usually the EASIEST to
  remove — not the hardest.** Go to `server-config-and-updates.md` for the full
  procedure. The short version: the client keeps a complete "do not show it" branch
  so the operator can turn the slot off, so neutralising that one branch is a
  small, local edit.
- Look for endpoints like `/adverts`, `/adv`, `/banner`, `/config`, and DTOs named
  `Advertisement*`, `Advert*`, `Banner*`, `Promotion*`, or — more common in practice
  — a generic `*Config` payload carrying per-feature blocks (`splash`, `noticePopup`,
  `updatePopup`, `tabbar`, `banner`).
- The client renders whatever the list contains. If the list is empty there is nothing
  to show, but see `pitfalls.md` P5 on **how not** to empty it: never make a shared
  request fail.
- Sponsored cards that look like content (a VPN promo, a network-accelerator card, a
  third-party product) are usually exactly this.

**A note on what "no SDK found" means.** If you have grepped the dex, enumerated the
loaded classes at runtime, and counted the SDK log tags in a capture, and all three
are zero (see Step 1), then there is no SDK, and continuing to search for one is a
dead end rather than a thorough approach. Re-classify against this list instead. A
zero result on all three signals is a strong positive finding about where the
behaviour lives, and it should move you to the server-config path immediately.

**Legit content that looks like an ad.** Verify before acting. A `/adverts?position=banner` response containing anime titles and poster images is the home-page carousel, not an advertisement. Removing it removes real functionality.

## Step 2: find the single convergence point

Almost every ad-enabled app wraps one SDK in a **single singleton helper**: `init`, `loadSplash`, `loadBanner`, `loadFullScreen`, `loadReward` all live in the same class. Find that class, and patch nothing else if you can.

```
helper.init(Application)              -> Sdk.init(appId, appKey); Sdk.start()   // plus plugin download
helper.showSplash(Activity, ViewGroup, onClose: () -> Unit)
helper.showInterstitial(Activity)
helper.showReward(Activity, onStart: () -> Unit, onFinish: (Boolean) -> Unit)
helper.preload*(Activity)
helper.canShow*(Activity): Boolean    // == isReady / isLoaded / isAdReady
```

**Preferred play: readiness always false + init is a no-op.**

1. Make the readiness predicate constant `false` (`isReady` / `canShow*` / `isLoaded` / `isAdReady`).
2. Make `init` an empty method (`return-void`) so the SDK never builds a network stack and never requests a plugin.
3. Only then touch show/load methods, and only for slots that bypass the readiness predicate.

Why this order works:
- Callers of a readiness predicate **already own a "no ad available" branch**, and the app ships and tests it. Returning `false` routes every slot through that existing path: no crash, no hang, no new code path.
- Killing init removes the SDK's network, cache, and download activity entirely. That is the difference between "the ad is hidden" and "the ad subsystem never started", and only the second claim is provable (Step 4).
- Per-slot patching (splash this week, interstitial next) leaves the SDK alive and downloading. Avoid it unless a slot ignores the predicate.

Method classification, once the helper is located:

| Method | Contains | Patch |
|---|---|---|
| Init | `Sdk.init(...)` + `Sdk.start()`, plugin download | body -> `return-void` |
| Readiness / gate | `isAdReady`, `canShow`, `isLoaded` | return `false` / `0` |
| Show splash / interstitial | constructs an ad object, `loadAd()` / `show()` | `return-void`, **but preserve the completion callback** |
| Show reward | same, plus success/failure lambdas | `return-void`; decide deliberately whether to grant the reward |
| Preload / warm-up | `RewardVideoAutoAd.init(...)`, cache priming | `return-void` |

### The callback trap (this one breaks startup)

A splash/loading ad usually takes a **completion lambda** as a parameter, and the app's startup state machine waits for that lambda before dismissing the splash screen.

**If you replace the method with a bare `return-void`, the lambda never fires and the app hangs on the splash screen forever.** A patch that "removed the ad" and produced a frozen splash is this bug, not a repackaging bug.

Correct shape, skip the ad and still complete:

```
.method public final showSplash(Landroid/app/Activity;Landroid/view/ViewGroup;Lkotlin/jvm/functions/Function0;)V
    .registers N
    invoke-interface {p3}, Lkotlin/jvm/functions/Function0;->invoke()Ljava/lang/Object;
    return-void
.end method
```

**Before patching, prove the contract.** Read the listener class the method constructs and find which callback triggers the completion lambda (`onAdDismiss`? `onAdError`? `onAdLoadTimeout`?). That tells you whether to call it on success, on failure, or unconditionally.

For a reward ad whose lambdas are `(onStart, (Boolean) -> Unit)`, granting the reward client-side is a choice: `onFinish(true)` makes the app treat the reward as earned. Check whether the reward is validated server-side before promising it.

### Global timestamp gates (one write, many slots)

Some "free reading + ads" apps do not gate ads per slot. They store one local timestamp and every slot, cooldown, and interval check reads it: splash, chapter-break interstitial, unlock prompt, "next ad in N minutes". Patching call sites one by one always misses some.

- **Find it:** dump the app's preference keys and filter for ad-ish names (`ad`, `free`, `cooldown`, `interval`, `end_time`, `expire`, `next_`). Then hook `SharedPreferences.getLong/getInt/getString` and watch which key is read immediately before a slot appears. The key read across several screens is the gate.
- **Patch it:** in `Application.onCreate()`, write a far-future value as early as possible (for example `4102444800000L`). Avoid `Long.MAX_VALUE`: implementations often compute `end - now` and can misjudge an extreme value. One write disables every reader at once, which is far more stable than editing each consumer.
- **If the app overwrites it later:** observe what it writes back under different start sequences. A single startup write is not automatically permanent for keys the app re-asserts; then patch the writer or the reader instead.
- **Same technique, two key semantics:** "ad-free until `<date>`" keys and "cooldown/interval" keys both respond to this, but the value differs. For a cooldown key, a far-future value means "next ad is never due", which is what you want, while a progress/check-in flow reading the same key may behave oddly.
- **Side effects are mandatory in the delivery notes.** The same key is often reused as a business field (the anchor for a new-user ad-free window, a remaining-quota counter). Forcing it to a far-future value changes those business judgements. Usually harmless for a de-ad goal, but state it explicitly and confirm the related screens do not show a broken state.
- With DataStore instead of SharedPreferences, a write inside `Application.onCreate` needs a coroutine or a blocking write; see `runtime-data.md`, and never block the main thread on persistence.

### "Ads" vs ad-gating UI

Some blocking dialogs contain no ad slot at all ("watch an ad to unlock", skip/continue prompts, cooldown notices). If the goal is "the app is usable", they count as ads and must be handled too. Handle them by letting the gate pass, not by deleting the dialog view.

- Where the gate reads the timestamp key above, the timestamp patch already covers it.
- Where it reads a boolean or a `canUnlock()` method, patch that predicate.
- **Business-coupled entrances need a check first.** "Watch a video to earn benefits" may be a real feature. Decide with evidence: find the callers (`scripts/find_refs.py`) and see whether the entrance leads to a **server request** or a **local entitlement write**. A server-issued entitlement cannot be created client-side, so releasing the gate only fools the UI while the server still refuses; an entrance that changes purely local UI state is safe to release.

## Step 3: choose the patch layer

From safest to riskiest (full technique table in `dex-patching.md`):

1. **Kill SDK init** (Step 2) — the SDK never starts; its networks, caches, and plugin downloads never happen. Highest-value single patch. Verify nothing else silently depended on init.
2. **Neutralize the readiness gate** — `isReady`/`canShow` return false; routes existing "no ad" branches.
3. **No-op the show/preload methods** — only when 1 and 2 are insufficient, always preserving callbacks.
4. **Global gate state** — one startup write covers every reader (timestamp / preference keys above).
5. **Filter server-issued ad data at the consumption layer** — drop entries for the target position before they reach UI state.
6. *(avoid)* **Renderer-level suppression** — only if the component is genuinely ad-exclusive. Check `pitfalls.md` P6 first.
7. *(avoid)* **Transport-level blocking** — see `pitfalls.md` P5.

## Step 4: verify — three independent kinds of evidence

Logcat silence alone is weak evidence. A credible "ads are gone" claim needs all three, plus the neighbours:

1. **UI, screen by screen** — splash, home banner, detail page, reader/player, reward button, unlock prompt. Capture before/after screenshots (`verification.md` §screenshot discipline).
2. **Logs** — the SDK's characteristic tags are **entirely absent**, not merely quiet: `anythink`, `ATSDK`, `Pangle`, `TTAd`, `GDT`, `ksad`, and so on.
   Make this a **count, not an impression**. Aggregators log a recognisable burst while they probe which networks are wired in (a "SDK id N not integrated" style line, once per network). Capture the same fixed window on the original and on your build and compare numbers: `8 -> 0` is a measurement; "I did not see it" is not. A tag that goes quiet without reaching zero usually means the SDK still starts and simply failed to load an ad this run — a different, weaker result than "the subsystem never started".
3. **Filesystem, the strongest signal** — the app's private directory contains **no ad SDK working directory at all**:
   ```bash
   adb shell "su -c 'ls -la /data/data/<app.package>/files/'"
   ```
   For a dynamic-plugin SDK, an absent `<sdk>_p` tree proves the init gate never ran. It is not an artifact you can fake by hiding a view. If the tree exists, something still initializes the SDK: the init patch did not take effect, or a second init path exists.

Additional cheap evidence:
4. **DNS / socket level** — a runtime `InetAddress` hook. Before: a burst of ad/tracker domains. After: none. Many ad SDKs bypass the system proxy, so a proxy log can miss them while this does not.
5. **Exercise the screens that had ads** and confirm nothing unrelated regressed: images, playback, lists, pagination, downloads, login.
6. **Clean install** — uninstall first, then install. Data left from a previous run can hide a failed init patch (`pitfalls.md` P11).

Frame the result at the right strength: *"the ad was hidden"* vs *"the ad subsystem never started"*. Only evidence 3 and 4 support the second (`verification.md` §the claim ladder).

## Step 5: what is usually NOT removable

Be honest about residual ads rather than breaking the app to chase them:

- **Content promos embedded deep in a feature's own data payload**, where the screen's
  load depends on the same request. Distinguish this from a *dedicated config block*:
  if the promo arrives in its own `splash` / `banner` / `popup` field with its own
  `enabled` flag, it is removable (Step 1, server-driven). It is only genuinely hard
  when the same list is both the content and the ad, with no marker separating them.
- **Ads delivered as content** (a sponsored "article" or a native card with no SDK marker)
  — indistinguishable from real content without runtime tracing.
- **Ads whose SDK init also enables other features.** Removing init can break
  functionality that silently depended on it. Verify before shipping; a working app with
  one residual ad beats a broken app.
- **Server-issued entitlements gated behind watching an ad.** The gate can be opened
  client-side, the entitlement cannot be created client-side.
- **A purely local brand launch screen.** If all you see is the app's own logo, no
  third-party image and no network-sourced content, that is a splash screen, not an ad.
  Removing it is a judgement call about the user's stated goal — say which one you
  removed rather than silently treating "startup screen" as "ad".

If a residual ad cannot be removed without breaking something, say so, and say exactly
which coupling caused it. That is a better deliverable than a broken APK.
