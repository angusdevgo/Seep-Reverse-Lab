# Auditing your own patch — proving it landed, and proving it is legal

Two independent questions, and they fail independently:

1. **Did the edit land?** Did the bytes you intended actually reach the artifact?
2. **Is the result legal?** Will the runtime's verifier accept it?

A patch can land and be illegal (the class fails to load). It can also fail to land while every
build step reports success. Both are silent, and each needs its own check.


**Load this when:** you must prove the edit landed **and** that it is legal. It gives the length-versus-bytes comparison that catches equal-length blind spots, verifier-level legality, and how to report a patch that did not apply.

## 1. Did it land? Compare *length*, not bytes

The naive check is a byte-level diff of the target method against the original.
**It produces a flood of false positives.** A disassemble→reassemble round-trip rebuilds the
string pool — the assembler **de-duplicates identical strings** — which shifts every later
string index by a small delta. Hundreds of methods then look "changed" while their behaviour is
identical.

Observed shape of that noise: **~800 methods reported as differing, 84% of them by only 1–4
bytes**, all of them constant-pool index shifts, with the method byte-length unchanged.

**Use instruction-stream length as the first-order predicate.** A real patch that changes control
flow or constant structure changes the method's `code_item.insns_size`. Pure index shifts and
debug-info reordering do not.

### The blind spot, and how to close it

**An equal-length replacement changes nothing measurable by length.**

Examples that bite: `move-result vX` → `const/4 vX, 0x0` (both one code unit); swapping one
`const` for another of the same width; any edit that keeps the instruction count identical.

Length-only auditing therefore **silently under-reports**: an audit reported 20 changed methods
on a build whose patch set actually touched 24 — the four missing ones were all equal-length
replacements.

**Two-tier rule:**

1. **Tier 1 (length):** scan every method. This yields candidates with essentially zero false
   positives.
2. **Tier 2 (opcode-level):** compare the two versions opcode by opcode **for every method the
   patch set declares as a target** — not merely the Tier-1 candidates.

**Tier 2's input cannot come from Tier 1's output.** Equal-length replacements produce no Tier-1
candidate at all, so the only reliable index of "what to check at Tier 2" is the patch set's own
declarations.

⇒ **Corollary, which is really a documentation requirement: every patch must declare its target
method signature.** A patch that is both equal-length and undeclared is invisible to both tiers;
finding it requires opcode-comparing every class, which is possible but expensive.

### A sharper Tier-2 shape for equal-length replacements

Compare the **position set of one opcode** inside the method:

```
target method, `move-result` (0x0a) position sets
  original : [25, 43, 66, 72, 216, ... , 899]   (16 entries)
  patched  : [25, 43,     72, 216, ... , 899]   (15 entries)   <- exactly one removed, pc=66
```

This proves two things at once: the intended site was hit, **and** the other same-shaped call
sites in that method were not. Asking "did anything differ" cannot distinguish those.

## 2. Is it legal? The verifier is a layer static checks cannot see

An assembler accepting your smali proves the file is **syntactically** valid dex. It does not run
the bytecode verifier. A build can pass assembly, pass every class-table check, and still be
rejected at class load:

```
java.lang.VerifyError: Verifier rejected class X: void X.<clinit>() failed to verify:
  [0x1C8] copyRes1 v0<- result0 type=Undefined
```

**Root cause in the observed case:** padding instructions were inserted **between** a producer and
its `move-result`. DEX requires `move-result*` to **immediately follow** the instruction that
produces the result (`invoke-*`, `filled-new-array*`). The padding broke adjacency, the result
type became `Undefined`, and the whole method — and therefore the class — failed to verify.
The length arithmetic ("the shorter form plus two padding units preserves the total") was
**correct** and still produced an illegal method.

**Four layers, cheapest first:**

| Layer | Check | Catches |
|---|---|---|
| 1 | assembler exit code | syntax, register overflow, bad labels |
| 2 | class-table diff (`scripts/dex_classdiff.py`) | class-set / access-flag drift |
| 3 | **predecessor legality of `move-result*`** | result consumers detached from their producer |
| 4 | device: first execution of that method | everything above, plus real semantics |

**Layer 3 is a set-difference, not an absolute count.**

- For both builds, collect every `move-result*` whose immediately preceding instruction is **not**
  a producer → the "offenders" set.
- Compare the sets. **New offenders must be 0.**
- **Never use the absolute size as a signal.** A perfectly healthy build can show hundreds of
  offenders under this definition — payload pseudo-instructions (`packed-switch-payload`,
  `fill-array-data-payload`, …) are normally read as ordinary instructions by a naive linear
  scan — so the absolute number is dominated by scanner artifacts. Only the delta means anything.

Worked consequence: a build whose sole new offender was one `move-result` following padding
crashed at class load on device. After moving the padding to **after** the `move-result`, the
delta returned to 0 and the same build ran. **The delta predicted the device result before the
device was touched.**

## 3. When patches are applied by text matching

Some toolchains apply patches by literal match against a text form (smali) rather than through a
dex API. The failure modes are textual and unforgiving:

- **Whitespace is content.** A fragment indented with 5 spaces will not match a file using 4.
  There is no fuzzy matching; one misplaced space is a zero-hit.
- **Line endings.** If the reader normalises CRLF→LF and the writer does not restore it, the
  patched file becomes LF-only. A later byte-level comparison against the CRLF source then shows
  the *entire file* as changed. Diff with an ignore-CR-at-EOL option, or compare structure.
- **Instruction names must be complete.** `move-result vX` and `move-result-object vX` are
  different instructions; an anchor missing the suffix matches the wrong thing or nothing.
- **Operand punctuation matters.** `instance-of p3, p0, LType` is not the source text when the
  source reads `LType;`.
- **Uniqueness is a hard requirement.** A matcher that finds several hits must fail loudly rather
  than patch the first. When a one-line anchor is not unique, extend it with a second unique line;
  **when the *combination* is still not unique, add a third anchor that discriminates the
  homographs** — usually the branch target label, since identical call shapes often differ in
  where they jump.
- **A re-emitted old fragment is not a failed write.** A patch may legitimately re-emit the old
  text inside the new one (inserting a guard *before* the lines it matched). A read-back check
  asserting "the old text is gone" then reports failure on that patch forever. Assert instead
  that the **new, unique** part of the replacement is present.
- **One patch document, one patch block.** A parser that treats every fenced block as a candidate
  will apply an *example* diff as a real patch — silently cancelling the real one, or editing
  unrelated code. Keep examples in prose, never in the same fence format.

## 4. Audit the patch set, not a patch

For a multi-patch build:

```
expected = every method declared as a target by the patch set
tier1    = methods whose insns_size changed
tier2    = methods whose opcode stream differs        (run over `expected`)
missing  = expected - (tier1 U tier2)                 # must be empty
```

**`missing` is the number that matters.** A build can be green on every build step and still be
missing a patch. Report `missing` explicitly; do not report the total as if the total were the
goal.

**And re-verify the artifact, not the intent.** If the tool says "applied" but the build on the
device is unchanged, you have a stale build, a second copy, or the wrong file
(`pitfalls.md` P24). A patch tool's success message describes the tool, not the artifact.
