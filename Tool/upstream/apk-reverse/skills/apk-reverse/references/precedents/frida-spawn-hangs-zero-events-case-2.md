# A zero-event trace was manufactured by the harness, not by the target

## Metadata
| Field | Value |
|---|---|
| Context | instruction-level tracing with Frida Stalker on Android 11 / arm64-v8a, on system processes, to test whether `Stalker.exclude()` fixes the community-reported zero-event and crash behaviour |
| Cost | three arms plus one harness correction; the two defects below both produce a *believable* zero-event trace, so they would have been read as a target finding |
| Outcome | the crash half has a clean cause (`exclude` fixes it); the zero-event half does not, and is now an explicit warning in the script rather than a silent empty log |
| Evidence | `references/evidence-summary.md` §The capability matrix; `references/evidence-summary.md` §The capability matrix (device attempts A and B) |
| Related | `references/native-dbi-and-deobfuscation.md`; `scripts/stalker_trace.js`, `scripts/stalker_report.py`; `pitfalls.md` P26 |

## Assertions and grade
| # | Assertion | Grade | Evidence |
|---|---|---|---|
| 1 | A follow with an **empty** exclusion list killed the target process; the same process survived an attach + resume with no follow at all | observed | three-arm run: `baseline alive=True`, `control alive=False err=script has been destroyed`, `treatment alive=True` |
| 2 | Excluding 20 system modules kept the process alive through the follow window | observed | `treatment … DONE\|reason=timeout` with the process still running, `EXCL\|excluded=20/20 […] not-loaded=3` |
| 3 | Exclusion did **not** restore event delivery | observed | `treatment` still reported `blocks=0 blk=0 calls=0 truncated=0` after the full 6 s window |
| 4 | The zero-event warning added to the script fires correctly | observed | `treatment` emitted `WARN\|zero events 1500ms after follow … -- the pipeline is NOT proven`; `control` could not, because its process was already gone |
| 5 | `CONFIG.autoStart` defaults to `true`, so loading the script starts a follow with default options before any runtime configuration can land | observed | the design section of `references/evidence-summary.md` §The capability matrix; the harness patches it to `false` and asserts the patch count |
| 6 | `frida` spawns a process **suspended**: without an explicit `device.resume(pid)` the followed thread executes nothing and the run reports zero events | observed | the same design section, and the `DONE … blocks=0` transcript in `references/evidence-summary.md` §The capability matrix |
| 7 | `Process.getMainThreadId()` returned a tid that was **not** the pid on Android (26261 for a pid of 19938), so the script's default thread selection watched the wrong thread | observed | `TRIG following tid=26261 (main-thread follow (pid=19938))` |
| 8 | Re-running with the real main thread `start(19938)` produced the same zero | observed | `DONE reason=timeout blocks=0 blk=0 calls=0` |
| 9 | A hot-function trigger (`malloc` in `libc.so`) produced 201 complete follow cycles with zero blocks in any of them | observed | 609 log lines, 201 follows, 201 `DONE`s, `nonzero_blk = 0` |
| 10 | A per-call follow/unfollow cycle on that hot function crashed a system process | observed once | `systemui` pid `18030 → 26932`, `SIGSEGV` with frame `#00` in an anonymous executable region and the return path into `libart` |
| 11 | The crash is the explanation for the zero-event results | **observed negative** — those runs produced their zeros before any death, on two other processes, and one never touched an export trigger | the separation stated in the same native-DBI evidence file |
| 12 | Why events do not arrive | **unverified** | the measurement says it is not the exclusion list; it does not identify the cause |

## Execution chain (including the dead ends)
1. The question was framed as a two-claim question, which is why it resolved: does `exclude` stop
   the crash, and does it restore events? Three arms, one device, one package, one module, one
   follow window, exactly one variable moving between them.
2. The `baseline` arm exists purely to make a death attributable: without it, "following killed it"
   and "the app dies under frida anyway" are the same observation.
3. Two harness defects had to be removed **before** the measurement meant anything, and both were
   found by noticing that an arm produced the *expected* result for the wrong reason:
   - `CONFIG.autoStart: true` followed once at `load()` time with default options, which is neither
     the control nor the treatment, and therefore contaminated both.
   - spawn leaves the process suspended, so with no explicit `device.resume(pid)` the followed
     thread ran nothing at all.
4. Result: the crash half is answered with a cause, and the zero-event half is answered as a
   **negative** — exclusion is not its fix, and the community framing that lists "no events" among
   the symptoms `exclude` cures is contradicted by this measurement.
5. Independent corroboration that the pipeline itself was healthy: the export-trigger run produced
   201 complete follow cycles. A trigger that never fired would look different; a filter that
   dropped everything would look the same, which is exactly why the claim is limited to "events do
   not arrive" rather than "Stalker is broken".

## Pits
| Pit | Cost | What it was mistaken for |
|---|---|---|
| `autoStart` following at `load()` | it invalidated two arms at once | a legitimate treatment result |
| No `device.resume()` after spawn | a whole arm's worth of zero events | the target refusing instrumentation |
| Reading a zero-event log as "the code did not run" | the reason the `WARN\|zero events` line was added to the script this pass | a finding about the target |
| `Process.getMainThreadId()` trusted as "the main thread" | one wasted run | a mis-selected thread |
| A system process died mid-run from the trigger pattern | one attribution round | an unrelated crash that could have been folded into the wrong conclusion |

## Reusable pattern
- **A negative result needs its own control arm.** `baseline` (attach, resume, never follow) is
  what converts "it died" into "the follow killed it".
- **Engineer the harness's own failure modes out before measuring.** Both defects here produced the
  exact shape under investigation; a run that reports the expected symptom is not yet a run that
  measured anything.
- **Make a dead pipeline announce itself.** A warning line the moment the follow window ends with
  zero events turns an ambiguous empty log into a labelled observation — and it is testable, because
  the arm whose process died cannot print it.
- **Separate "the follow is unsafe" from "the follow observes nothing".** Two arms, two conclusions,
  never one.

## Write back to the repository
- [ ] `references/native-dbi-and-deobfuscation.md` §6 — keep the two measured boundaries; add the
      harness-defect paragraph if absent, because a reader who reproduces a zero event will
      otherwise attribute it to the device.
- [ ] `scripts/stalker_trace.js` — already carries the zero-event warning; ensure the `autoStart`
      comment says *why* the default is dangerous (it is a trap, not a convenience).
- [ ] `references/precedents/README.md` — indexed as case 2; move assertion 12 to `observed` only if
      a future pass identifies the cause.
