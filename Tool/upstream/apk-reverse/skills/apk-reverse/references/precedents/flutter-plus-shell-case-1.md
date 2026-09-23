# A pid that keeps moving must be attributed before it is explained

## Metadata
| Field | Value |
|---|---|
| Context | dynamic analysis of a hardened Android sample (Flutter AOT payload behind a third-party application-stub) on a rooted physical device |
| Cost | three attribution corrections; two of them were written down as findings before being refuted |
| Outcome | the drift is attributed to the sample's own environment check, and the operational rule that falls out of it ("configure root hiding, then re-baseline") |
| Evidence | `references/evidence-summary.md` §The capability matrix (the pid-drift section and the frida-dexdump section); `references/evidence-summary.md` §The capability matrix (the root-hiding layer) |
| Related | `SKILL.md` §Stop conditions (last bullet); `pitfalls.md` P9, P18; `references/detection-and-anti-analysis.md` |

## Assertions and grade
| # | Assertion | Grade | Evidence |
|---|---|---|---|
| 1 | The sample starts and stays resident with no instrumentation attached | observed | `ps -A \| grep <PKG>` → `u0_a623 22691 … 642488 SyS_epoll_wait 0 S <PKG>`, 12 s after `am start` |
| 2 | During a session its pid changed repeatedly: `22691 → 23452 → 24267 → 27274 → 31284 → 32259 → 1368 → 8161` | observed | the same evidence file's pid-drift transcript |
| 3 | The drift reproduces with `frida-server` **stopped** and no attach | observed | a 90-second observation loop, four pid changes, with the frida process absent |
| 4 | The process dies as the **foreground top activity**, with no crash, no tombstone and no ANR record, and the platform relaunches it on a 7–18 s cycle | observed | `adb logcat \| grep <PKG>` → `Process <PKG> (pid N) has died: fg TOP` followed by `Start proc <pid> for top-activity <PKG>` |
| 5 | No application on the device was hidden from root at the time | observed | `magisk --denylist status` = enforced, `--denylist ls` printed nothing, `/data/adb/shamiko` absent (the root-hiding section of `references/evidence-summary.md` §The capability matrix) |
| 6 | The cause is the sample detecting its rooted environment and exiting on purpose | **inferred** — the mechanism fits every observation, but it was not proven by disabling the check |
| 7 | Memory pressure was **not** the cause | observed (refuted) | the drift continued at 300–750 MB free of 11.5 GB, and a reclaim kill leaves an `lmkd` line and a low-memory record — neither present |
| 8 | Instrumentation was **not** the cause | observed (refuted) | the `frida-server`-stopped control run |
| 9 | The device's own hooking framework was already damaged during the window (`lspd` alive but not updating its configuration, `zygote crashed too many times, rolling-back`) | observed | the framework-damage section of `references/evidence-summary.md` §The capability matrix |
| 10 | A `start timeout` kill line discriminates between these causes | **observed negative** — it reads identically for a slow init, a reclaiming device and a deliberate delay, so it is not evidence either way | the `ActivityManager` transcript quoted in the same evidence file |

## Execution chain (including the dead ends)
1. The control run looked healthy: start the sample with no instrumentation, wait 12 s, `ps` shows
   it resident at 642 MB.
2. Later the pid had changed eight times. The natural reading — *the sample fights instrumentation*
   — was written down as the finding. **Dead end 1.**
3. The control that killed it: stop `frida-server` entirely, restart the sample, observe for 90
   seconds. The pid still moved, roughly every 10–20 s. Instrumentation is out.
4. The replacement attribution: memory pressure while a Flutter app saturates the CPU during its
   startup window (439 % CPU, `kswapd0` at two thirds of a core were both measured). **Dead end 2.**
5. The measurement that killed it, and the reason it is worth recording: **a different instrument
   was pointed at the same question.** `logcat` — not pid sampling — showed
   `has died: fg TOP` with no crash record and an immediate relaunch. A reclaiming device does not
   do that to a foreground process, and a memory-pressure kill leaves different traces.
6. That left "the sample checks its own environment and quits", and the environment check was then
   findable: nothing on the device was hidden from root. A hardened sample that refuses to run
   rooted produces exactly this loop, forever.
7. Only after the attribution did the *practical* conclusion exist: re-run the baseline with root
   hiding configured, and treat every earlier dynamic result on that device as measured against a
   process that was trying to die.

## Pits
| Pit | Cost | What it was mistaken for |
|---|---|---|
| Sampling the pid instead of reading the platform's lifecycle log | two full attribution rounds | a target-resistance hypothesis, then a host-resource hypothesis — the log settled it in one command |
| A 12-second control window | it looked like a stable baseline | the sample's lifetime was 7–18 s, so a single sample can land inside one life and read as stability |
| A third candidate mechanism discovered mid-pass (a zygote in a crash-and-rollback cycle restarts app processes by itself) | it invalidated single-cause attribution for the whole window | it did not create the drift, but it means "the pid changed" had at least three independent causes on this device at that moment |
| Two refuted attributions already written into an evidence file | deletion cost, not re-measurement cost | each reads as more coherent than the truth, which is why they would have been believed |

## Reusable pattern
- **Attribute before explaining.** A target that dies, drifts, or restarts gets a *mechanism* from
  the platform's own record first (`logcat`, tombstones, `dumpsys`) — sampling tells you that it
  happened, never why.
- **Refute the cheapest alternative first, with a control that removes it entirely.** Stopping the
  instrumentation is one command; it eliminated the leading hypothesis in a single run.
- **When a measurement disagrees with a recorded conclusion, reopen the conclusion.** That rule
  (`SKILL.md` §Stop conditions) was applied twice to this pass's own record, and both times the
  record was the thing in the wrong.
- **Record the device's framework state next to any dynamic result.** This device could restart
  the target without the target being involved.

## Write back to the repository
- [ ] `references/detection-and-anti-analysis.md` — a "the target exits on a rooted device, and the
      environment is why" subsection: the `fg TOP` + immediate relaunch shape, the two kills that
      look like it and are not, and the re-baseline step.
- [ ] `references/precedents/README.md` — already indexed as case 1; update the grade column if a
      future pass proves assertion 6 by disabling the check.
- [ ] `references/pitfalls.md` — only if the *sampling-instead-of-logcat* mistake is not already
      covered there; if it is, extend that entry with this measured cycle length rather than adding
      a second one.
