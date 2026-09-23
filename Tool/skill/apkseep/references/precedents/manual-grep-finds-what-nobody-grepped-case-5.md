# The leak nobody grepped for, found by hand and only after the fact

## Metadata
| Field | Value |
|---|---|
| Context | this repository's own history: a complete verification pass was recorded, reviewed and merged, and the target identity in its evidence files was found afterwards |
| Cost | a manual sweep, and the omission survived at least one pass that produced evidence files |
| Outcome | a desensitization convention (`<PKG>` / `<DEVICE>` placeholders, target identity absent by policy) **and** an automated scan (`scripts/scan_leaks.py`), added in the same pass that recorded this case |
| Evidence | `references/evidence-summary.md` §The capability matrix; `references/evidence-summary.md` §The capability matrix (its identifier-convention and injection-line sections); `references/evidence-summary.md` §The capability matrix (its environment section) |
| Related | `references/desensitization-and-leak-scans.md`; `references/long-task-discipline.md` §Keep a live record, not a log; `references/verification.md` §Reporting |

## Assertions and grade
| # | Assertion | Grade | Evidence |
|---|---|---|---|
| 1 | Identity was found by a human grep after the material had already been written, and the files had to be corrected | observed as this repository's stated history; the correction itself is visible in the convention every evidence file now opens with | the environment section of `references/evidence-summary.md` §The capability matrix: *"Target identity is deliberately absent. The sample is referred to as the sample, and its package identifier appears as `<PKG>`"* |
| 2 | The convention was enforced per file, by hand, at write time | observed | the identifier-convention section of `references/evidence-summary.md` §The capability matrix normalises every occurrence of the package identifier and its sub-package prefixes, and states that the transcripts are otherwise verbatim |
| 3 | Verbatim transcripts were kept, and that is deliberate | observed | the same section keeps the hook-reported class names, "those are what make the evidence checkable" |
| 4 | No structural gate could have caught it | observed | `check_repo.py` validates layout/frontmatter/`--help`; `check_refs.py` validates section anchors; neither reads content for identity. Both passed on the material that had to be corrected |
| 5 | An automated scan would have caught it | **inferred** — the scanner was built and measured against a planted corpus, but it was never run against the historical, pre-correction tree | `references/evidence-summary.md` §The capability matrix, the planted-corpus and repository-scan sections |
| 6 | The scan finds the four classes that actually occur here — bundle ids in `pm`/`ps`/`manifest` contexts, 16-character serial-shaped tokens, inline key assignments, host user paths | observed | planted corpus: 30 findings across 6 categories, every rule firing |
| 7 | The scan's first run against the real tree was overwhelmingly false positives, and each one was a shape that legitimately appears in this documentation | observed | the repository-scan section of `references/evidence-summary.md` §The capability matrix: 40 findings when the file above was still being written, of which 26 were `strong`/`certain` — and every one of those 26 was inside that pass's own evidence file. After the correction: 0 strong, 4 weak (RFC 5737 usage examples) across 129 files |
| 8 | Over-redaction is the failure on the other side, and it is not hypothetical here | observed | the do-not-anonymize list in the reference file is derived from identifiers that a shape-only scanner flagged in this tree: tool names, SDK packages, dex constant identifiers, public crackme names |
| 9 | The ratio, not the count, decides whether a gate survives | observed from this case | the pass that produced 27-of-28 false positives also had to fix 26 real ones in its own report on the same day. Both numbers moved the design: exemptions for the shapes that legitimately appear, and a split exit code so the remaining documentation-range hits do not make the gate permanently red |

## Execution chain (including the dead ends)
1. The convention existed and was written down per evidence file: identity absent, placeholders for
   the package, the device serial and the host paths, verbatim transcripts otherwise.
2. It was enforced by hand, at write time, by whoever wrote the file. **This is the dead end**: a
   convention enforced by attention has no failure signal. The omission was invisible until someone
   went looking, and by then the material was already in the tree.
3. The correction happened after the fact, which is why this case exists at all. A search for the
   shape — not for the value — is the only route that scales, because the value is exactly what you
   do not yet know.
4. The scan was then built, and the interesting result was **not** "it finds leaks" (that was the
   easy part). It was that a first run over the real tree produced 28 findings of which 27 were
   legitimate documentation: a JDK version that looks like an IPv4 literal, tombstone hex tokens
   that look like serials, a public crackme's package name, a `probe.synthetic.*` fixture, a
   property lookup. A scanner that shipped in that state would have been ignored within a week, and
   the leak it exists to catch would have gone with it.
5. The final state separates the two decisions: the scanner reports shapes and admits known-benign
   explanations **with a printed reason** (`--show-exempt`), and a human makes the identity call
   from the context window the report already contains.

## Pits
| Pit | Cost | What it was mistaken for |
|---|---|---|
| A convention with no automated check | one manual sweep after the fact | adequate coverage |
| Searching for the *shape* after the fact, rather than during the write | it only works if you already suspect | a finished pass |
| A shape-only scanner | 27 false positives in 28 findings on this tree alone | a working gate |
| Suppressing the false positives by blocking whole address ranges | it would also have hidden the one real weak hit (`scripts/tls_check.py`'s RFC 5737 example) | noise reduction |

## Reusable pattern
- **Desensitize at write time, and verify by shape, not by value.** The value you have to remove is
  the one you cannot enumerate in advance; the shape is the thing you can write a rule for.
- **Decide in code what is exempt, and let the code print why.** An exemption list that cannot be
  audited is indistinguishable from an exemption list that is too broad, and only one of those is
  visible in review.
- **Keep the transcripts verbatim and replace the identity with a placeholder.** Redacting the
  *evidence* destroys the thing that makes the record checkable; redacting the *identifier* costs
  nothing.
- **Measure the scanner against your own tree before trusting it.** The false-positive ratio, not
  the true-positive count, decides whether anyone will keep running it.

## Write back to the repository
- [ ] `references/desensitization-and-leak-scans.md` — the reasoning, the split rule, and the
      failure-mode table; this case is its motivating evidence.
- [ ] The evidence record's own index — `docs/tool-verification/README.md` at the **repository root,
      not shipped** — carries the topic entry. The in-skill condensation is
      `references/evidence-summary.md`.
- [ ] `references/precedents/README.md` — indexed as case 5.
- [ ] **Closed in this pass**: `scripts/scan_leaks.py` is wired into the repository workflow (run it
      over the tree before a commit) and the `RESULT=` convention is documented in
      `references/long-task-discipline.md` §Every script answers with a token, not with prose.
- [ ] **The scanner caught its own first pass.** The tool written to prevent this class of leak found
      26 `strong`/`certain` hits on the day it was written, all of them inside its own evidence file —
      the fixture's literal match values, quoted to prove the rules fire. The fix was to keep the
      location, rule, category and grade for all 30 findings and replace every literal with a shape
      description. Boundary that makes it a rule rather than a scare: **the corpus may contain values;
      the published surface may not.** Evidence and transcripts: the "self-leak this file carries" and
      "inherited versus post-fix" sections of `references/evidence-summary.md` §The capability matrix.
      This is the strongest available argument for the gate — the author of the rule needed it on the
      same day, and did not see it by hand.

