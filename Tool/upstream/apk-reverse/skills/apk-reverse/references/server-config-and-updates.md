# Server-driven UI config — promos, popups, tab bars, and remote re-enable

Many apps ship a **remote configuration endpoint** that decides what the client
renders: a launch screen image, a popup, an announcement, which tabs exist. This is
the single most common shape of "ad" in a modern app, and the one most often
mis-diagnosed, because there is no ad SDK anywhere in the package to find.

Two consequences that change the whole plan:

- **Searching for an ad SDK finds nothing, and that is arithmetically correct.** No
  amount of further SDK hunting will help. Recognise the shape early and stop.
- **The behaviour can be re-enabled server-side without shipping a new client.**
  Any patch that just leaves the config unread is a patch the operator can undo.
  The durable fix is in the client's decision path, not in the data.


**Load this when:** a launch screen, popup, announcement or tab set must go, and there is no SDK to find. It gives the server-issued-config shape, how to tell it from a client-side flag, and the remote re-enable that undoes your patch.

## 1. Two-layer fetch: local default, then remote override

The most useful diagnostic — and it is a runtime observation, not a static one — is
that the config object **changes value once during startup**:

```
before the network round-trip:  SplashConfig(enabled=true, duration=5, image=<built-in drawable>)
~1s later (config response):    SplashConfig(enabled=true, duration=5, image=https://<cdn>/<promo>.png)
```

Seeing this pair proves three things at once: the screen is config-driven, the
built-in asset is only an offline fallback, and the content actually shown came
from the server. **Capture both states before designing any patch** — a
hook on the config type's constructor/factory plus its `toString()` is usually
enough (data-class `toString()` keeps the real field names even after R8, which is
why it is such a convenient anchor).

If you only ever see the built-in default, you are looking at an offline or
pre-config state and have not observed the real behaviour yet.

## 2. Locate the config surface

The DTOs are usually the easiest anchor in the entire app, because data classes
serialise their own field names.

```
ddc findrefs app.apk string "SplashConfig"      # or any of the field names below
ddc strings app.apk -f "enabled" --with-locations
```

Field names worth grepping, in the plural because they recur:

```
splash, splashImage, splashSkip, splashLogo, launchScreen, bootAd
noticePopup, announcementPopup, updatePopup, forceUpdate, upgradeDialog
tabbar, tabs, items, enabled, showMode, startAt, endAt, showOnce
promo, promotion, banner, bannerList, featured, sponsored
```

A `*Config` / `*Popup` / `*Banner` suffix with an `enabled` boolean is the signal
you are in this layer. **The `enabled` flag's polarity is not guaranteed by its
name** — see.

Then find the **consumption point**, which is where you patch: the method that
reads the flag and decides. The DTO itself is usually immutable and shared, so
editing it is both fragile and unnecessary.

## 3. Patch the decision, not the data

Ordered from most to least durable:

| Approach | Durable? | Why |
|---|---|---|
| Neutralise the client-side branch that consumes `enabled` | **yes** | The server can send anything; the client no longer acts on it |
| Force the config field to its "off" value at parse time | partly | Works until a second parse path or a cache exists |
| Block or 404 the config endpoint | **no** | Usually breaks the screen that shares the request (see `pitfalls.md` P5) |
| Delete the local fallback asset | no | Only affects the offline case |

**How to neutralise a branch correctly** is in `byte-level-patching.md`: replace the
conditional branch with `nop`s so execution takes the fall-through path, rather
than redirecting the branch. Forcing a specific side by redirection adds a control
flow edge and can trip the verifier.

**Mandatory before editing: decode both sides of the branch and write down what
each one does.** Field names lie. In one real case the field was named `enabled`,
and the branch structure was:

```
iget-boolean v, obj -> Config.enabled
if-nez v, :countdown        ; enabled == false jumps AWAY
invoke  startMainScreen()   ; fall-through: straight into the app
:countdown   ...            ; branch target: show the promo for N seconds
```

so `enabled == true` was the value that **skipped** the promo. Taking the name at
face value and "enabling the skip" produces a build that shows the ad on every
launch — and it starts cleanly, so nothing catches it until someone looks at the
screen.

## 4. Decide the scope of "remove" before you edit

Serve-side config usually controls several things at once, and they are not all
ads. Classify each field the same way you would a UI element:

| Field shape | Usually is | Usually not |
|---|---|---|
| Launch screen image + countdown with no dismiss | promotional | a functional splash |
| Popup with a channel/group link and `showOnce` | promotional | |
| Popup with changelog + `force` + an external URL | update nag → `updates-and-forced-upgrade.md` | |
| Tab bar item with `enabled=false` | absent by operator choice | |
| Announcement that is off server-side | nothing to remove | |

If the user asked for "no ads", removing a genuine brand splash is a judgement
call, not an automatic win — a self-owned logo screen with no third-party content
is arguably not an ad. State which one you removed; if the request was ambiguous,
the safer default is to remove only the server-sourced promotional content and
leave a purely local brand screen alone. See `long-task-discipline.md` on not
substituting your own goal for the stated one.

## 5. Verify at three levels, not one

A config-driven behaviour needs more evidence than a log line:

1. **Screen, before and after, frame by frame** — `scripts/coldstart.py`. The
   observable is a visible change plus a change in time-to-first-meaningful-screen.
2. **The config object's own values at runtime** — if the app logs or you can hook
   it, show the value it received. This separates "the server stopped sending it"
   from "the client stopped obeying it", which are different claims.
3. **Correct negative**: if the flag arrives `enabled=true` and nothing happens,
   that is the strong result. If it arrives `enabled=false`, you have verified
   nothing about your patch.

## 6. Remote re-enable: the durability question

Two channels can undo client-side work without a version bump:

- **The config endpoint itself.** Your patch must be in the decision path so a
  future `enabled=true` is still ignored (see). A patch that reads the flag and
  happens to work today is not durable.
- **A hot-update / dynamic-resource channel** (a downloaded bundle, a patch dex, a
  remotely loaded layout). Look for a cache directory that is not the config cache,
  or a download-then-load path during startup. If one exists, the patch has to
  survive it — which usually means the patched decision is the right place anyway,
  because remote resources rarely replace compiled logic.

Also check whether the config is **cached to disk** (`SharedPreferences`, a JSON
snapshot, a DataStore file). A cached copy means the app can exhibit the old
behaviour offline for one launch after your change, which looks like a failed
patch. Clear the cache as part of the experiment, and say so when reporting.

## 7. Reporting template

```
Promo/popup surface: <field> (<DTO class>)  | source: server config at <endpoint or unknown>
Observed before: <exact values, incl. whether enabled was true/false>
Observed after:  <exact values / absence>
Patch:           <class#method, byte offset, bytes before -> after>
Durability:      <why a future server-side change cannot restore it>
Not removed:     <fields deliberately left, with reason>
Side effects:    <what shares the same config or code path>
Unverified:      <anything not directly observed>
```
