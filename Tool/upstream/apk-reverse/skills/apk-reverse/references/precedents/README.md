# Precedent library — what a pass got right, and how it got there

`pitfalls.md` is the negative catalogue: what went wrong. This directory is the other half —
**cases where the work actually converged**, recorded so the route can be walked again instead
of re-derived. The two do not overlap on purpose: a case here points at `pitfalls.md` by entry
number rather than restating the failure, and a pitfall that already has a case does not need a
second copy in prose.

Read a case when you are **about to do this kind of work again** — not when you are stuck. A case
answers "what sequence produced a defensible result, and what did it cost"; when you are stuck
the symptom index in `SKILL.md` is the faster route.

## Why this exists at all

This repository's most expensive recurring loss is not ignorance. It is **a conclusion that was
correctly retracted and then re-adopted**, because the retraction lived in a conversation while
only the original claim was ever written to a file. Three of the cases below are exactly that
shape: an attribution that was wrong, corrected by measurement, and corrected again. In each one
the *wrong* version is the one that reads as more coherent, which is why it is the one that would
be believed by a reader who only saw the summary.

A case therefore records the execution chain **including the dead ends** — the wrong turn, and
the measurement that killed it. Without that part, the case is a success story, and success
stories teach nothing that survives the next surprise.

## The cases

| Case | Route it establishes | Strongest claim in it | Grade |
|---|---|---|---|
| `flutter-plus-shell-case-1.md` | classify a hardened Flutter sample before trusting any dynamic result: a pid that keeps moving has to be attributed before it is explained | the same drift was attributed to frida, then to memory pressure, then to the sample's own root-environment check — only the third survived | observed (drift and its cause), unverified (that this generalises) |
| `frida-spawn-hangs-zero-events-case-2.md` | a harness can manufacture the very negative result it is looking for: `spawn` leaves the process suspended, and `CONFIG.autoStart` follows before your configuration lands | a zero-event trace was produced by two independent harness defects, not by the target | observed (the mechanism, and the warning that now fires) |
| `logd-broken-module-never-ran-case-3.md` | decide whether a hooking module ran at all, on a device whose log daemon is broken | nine successful injections produced **zero** `logcat` lines; the only evidence was a file under `/data/adb/lspd/log/` | observed (both channels), inferred (the framework-bridge explanation) |
| `l1-equal-length-patch-case-4.md` | the full chain from a two-byte dex edit to a visible change on screen, with a control build | the dialog disappeared **and** the control build failed the same way first, which is what makes the four bytes responsible | observed end to end |
| `manual-grep-finds-what-nobody-grepped-case-5.md` | why a leak scan is a gate and not a document, told from this repository's own near-miss | a shipped pass had to be corrected after the fact for identity a human grep found | observed (the omission and the correction), inferred (that a scanner would have caught it) |

Each case ends with an action checklist naming the **repository files that should be written
back to** if you hit the same thing. A case that does not produce a file edit has not finished.

## Template

Copy this skeleton. Keep the headings — the read-back check depends on them, and the grade
column is the part that stops a hypothesis from drifting upward into a fact.

```markdown
# <Title> — one line naming the conclusion, not the activity

## Metadata
| Field | Value |
|---|---|
| Context | what was being done, in one line |
| Cost | what it cost before it converged, measured |
| Outcome | what artifact or conclusion exists now |
| Evidence | the evidence files, by path |
| Related | `pitfalls.md` entries, and the neighbouring reference files |

## Assertions and grade
| # | Assertion | Grade | Evidence |
|---|---|---|---|
| 1 | ... | observed / inferred / unverified | exact command, file, or line |
Reserve `observed` for a claim with a command and its output behind it. An assertion whose
evidence is "the mechanism implies it" is `inferred`, and saying so is not hedging.

## Execution chain (including the dead ends)
The wrong turn, the measurement that killed it, and only then the route that held. Numbered,
because the order is the information: a reader who starts from the conclusion will pick the
wrong sequence.

## Pits
| Pit | Cost | What it was mistaken for |
|---|---|---|
| ... | measured number, or a count of re-runs | ... |
Use a cost you measured. "Two round trips" is a measurement; "a while" is not.

## Reusable pattern
The part that transfers to a different target with no editing. If it needs this target's names,
it belongs in the chain above instead.

## Write back to the repository
- [ ] `<file>` — <what to add to it, so the next reader does not pay this again>
- [ ] `<file>` — <index line, if a new file was created>
```

## Rules

- **Grade every assertion, and grade it down when in doubt.** `observed` means a command was run
  and its output is in the evidence record condensed in `references/evidence-summary.md` §Where the full record lives. "I reasoned it out" is `inferred`. This is the
  same standard `references/long-task-discipline.md` §Grade your own conclusions sets for a live
  record, and it is the reason a case is worth reading a year later.
- **Record the retraction with the claim.** If an earlier conclusion was wrong, both versions
  belong in the case: the wrong one, why it was wrong, and what replaced it. Deleting the mistake
  loses the most transferable thing here.
- **Do not restate `pitfalls.md`.** Point at the entry. A duplicated failure mode drifts out of
  sync with its original and then contradicts it.
- **One case, one route.** A case that establishes three unrelated things establishes none of
  them; split it.
- **A case with no write-back checklist is a diary entry.** The last section is what makes it
  knowledge the repository holds rather than knowledge the author had.
