# "The module never ran" was an artefact of a broken log channel

## Metadata
| Field | Value |
|---|---|
| Context | verifying that an LSPosed hook module was actually injected into a hardened target, on a rooted Android 11 device |
| Cost | the verification criterion itself had to be corrected; `logcat` was empty across nine successful injections |
| Outcome | the injection is proven from `/data/adb/lspd/log/modules_<timestamp>.log`, and the read rule is now "both channels, always" |
| Evidence | `references/evidence-summary.md` §The capability matrix (the injection-line, log-surfaces and scope sections) |
| Related | `references/evidence-summary.md` §The capability matrix (the framework-damage section); `references/lsposed-and-modules.md`; `references/environment.md` |

## Assertions and grade
| # | Assertion | Grade | Evidence |
|---|---|---|---|
| 1 | The module was injected nine consecutive times, each run reaching the target's `MainActivity.onCreate`, the WebView process and an ad SDK activity | observed | nine full injection blocks; nine pids in ~3 minutes (`8111 → 9392 → 10557 → 11453 → 12345 → 13236 → 14155 → 15061 → 15934`) |
| 2 | `logcat -s <TAG>` was **empty**, as was `logcat -s LSPosed-Bridge` and a full-buffer `grep -i <TAG>` | observed | the injection-line section of the LSPosed evidence file, stated as the correction to the pass's own earlier draft |
| 3 | The module's output existed only in `/data/adb/lspd/log/modules_<timestamp>.log` | observed | the evidence file for the pass is 201 lines, of which 126 are `<TAG>` |
| 4 | The same file earlier appeared to contain nothing but `Logd maybe crashed (err=Socket operation on non-socket), retrying in 1s...` | observed | the log-surfaces section of the same evidence file quotes the entire content of an older `modules_*.log` |
| 5 | The ROM's `logd` route is broken, so LSPosed's logcat channel delivers nothing while its file channel works normally | **inferred** — the two observations above are consistent with exactly this, and the mechanism was not probed further |
| 6 | A reader debugging a module with `logcat` alone would conclude the module never ran, while looking at nine successful injections | observed (as a statement about the evidence), inferred (as a statement about other readers) |
| 7 | The target's double-`Application` packer swap is visible in the hook order, and hooks installed at `handleLoadPackage` time survive it | observed | `Application.attach` fires twice — the real `BaseApplication`, then the stub — and by `Activity.onCreate` the reported classes are the **unpacked** ones |
| 8 | Scope is per app, not per process | observed | the module also injected into the target's `com.google.android.webview` process and reported an ad SDK activity |
| 9 | The pre-reboot self-restart cycle (10–20 s) can be compared with the post-reboot cycle (22–23 s) | **inferred at best, and not a controlled result** — a reboot moves several variables at once | the injection-line section of the same evidence file |
| 10 | `verbose_*.log` is a full logcat snapshot, useful for correlating a run with system state and useless as a module log | observed | the log-surfaces section of the same evidence file |

## Execution chain (including the dead ends)
1. The module was built, installed, PM-enabled, and scoped through LSPosed Manager's UI — read from
   `uiautomator dump` coordinates, never tapped by guess. The scope change was confirmed in the
   framework's own SQLite database (`scope` gained `(2, '<PKG>', 0)`, `modules.enabled` flipped to
   `1`, and the database file grew from 156,376 to 201,696 bytes), which is what proves the
   framework — not merely its daemon process — came back.
2. The pass then read `logcat -s <TAG>` and found nothing. **Dead end:** the criterion in the
   reference file, in the pass's own earlier draft, and in the scaffold's generated README all said
   to watch `logcat`.
3. Rather than conclude "injection failed", the other channel was read: LSPosed's file log. Nine
   full injection blocks.
4. The correct criterion was written down, and it is the transferable part: read **both** channels.
   `logcat -s <TAG>` where the platform is healthy; `/data/adb/lspd/log/modules_*.log` always.
5. The reason the two disagree on this device is a broken `logd` (`Socket operation on non-socket`),
   which is also visible in unrelated incident lines from the same window (`system server died`,
   `am is dead`, `no response from bridge, retry in 1s`, `Magisk: zygote crashed too many times,
   rolling-back`).

## Pits
| Pit | Cost | What it was mistaken for |
|---|---|---|
| Trusting one log channel on a ROM whose log daemon is damaged | it would have produced a false negative on a working feature | "the module never loaded" |
| `logcat` silence read as absence of evidence *for* the target's behaviour | the verification criterion itself was wrong, not just the reading | a statement about the module |
| The same silent-failure shape appears twice in the pass | once for the module channel, once for the framework's own state | two different "not installed"-looking states, one of which was real |

## Reusable pattern
- **Before accepting a silence as a finding, ask whether the instrument could have spoken.** This is
  `pitfalls.md` P26's rule pointed at a *log channel* rather than at a script: check that the channel
  has ever delivered for a healthy case.
- **Prefer a channel that is a file over a channel that is a daemon.** `logcat` depends on `logd`;
  a file in the module's own directory depends on the module.
- **Verify the verifier.** The scope change was confirmed in the framework's own database rather
  than in the manager's UI reflecting it back — a UI can render a cached state, and the file is the
  state.
- **On a packed target, a Java-layer hook is reachable without touching the APK**: the double
  `Application` swap is observable, and hooks installed before it survive it. That is a *capability*
  result, separate from the log-channel lesson, and it is the reason this route is worth the setup.

## Write back to the repository
- [ ] `references/lsposed-and-modules.md` — the verification section must name both channels and the
      exact file path pattern; a single-channel instruction is what this case disproves.
- [ ] `scripts/lsposed_scaffold.py` — the generated README's verification line should carry the same
      two-channel instruction, because it is the artifact a user reads first.
- [ ] `references/precedents/README.md` — indexed as case 3; assertion 5 stays `inferred` until the
      logd mechanism is probed directly.
