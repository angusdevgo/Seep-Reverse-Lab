# Differential hardening (the known-plaintext route to a private opcode table)

Load this when the dump is a **real Dex VMP** — bodies present, decoding as nonsense to a
dalvik disassembler, a native interpreter loop behind them — and you have decided the
private opcode space is worth attacking rather than walking away from. The neighbouring
file owns the diagnosis (`advanced-unpacking.md` §The honest boundary: real Dex VMP) and
the sentence that sends you here. This file owns what happens next, and — more of it than
is comfortable — what does not.

**Strength note, read before trusting any number here.** Every mechanism below was
exercised on locally built fixtures, and the closed loop is measured: `simulate` relabels
a fixture through a known bijection and `compare` re-derives that table **exactly, 218 of
218 emitted opcodes, zero wrong entries, zero fabricated entries** (`references/evidence-summary.md` §The capability matrix).
What was **not** exercised is the other half of the premise: **no third-party hardening
platform was contacted**. The assumption that a real engine performs a per-opcode
substitution at stable instruction length is **inferred** from public VMP write-ups and is
exactly the assumption this method can fail on. The cost table's platform column is
therefore reasoning from how those platforms are distributed, not from a measured upload.

## 1. The method, and the one thing it needs to be true

The hardened body cannot tell you where its instruction boundaries are: its opcodes are
private, so the format specification's length table does not apply to it. That is the
whole obstacle — a disassembler that cannot decide where instruction *n* ends cannot name
instruction *n+1*.

The differential dissolves it with an oracle you control. Compile a fixture whose every
instruction you know; get the same platform to harden it; then **take the original's
instruction boundaries and project them onto the hardened bytes**. Original offset
`0x14` was a `mul-int` occupying 2 code units, so hardened bytes `0x14..0x17` are the same
instruction, re-encoded. Read the hardened opcode byte at each projection and you have a
`(original opcode → private byte)` sample. Aggregate over thousands of instructions and
the substitution table falls out.

Three preconditions, and they are not negotiable:

| Precondition | Why it must hold | What it looks like when it fails |
|---|---|---|
| **The hardened body keeps the same length** | The projection is a stencil; a length change slides every boundary after the first edit | `compare` reports `resized` for the whole method and refuses the run |
| **The substitution is per-opcode, not per-method** | One private byte per original opcode is what makes the table a table | Every original opcode claims the same private byte (`compare` → `NOT-USABLE`, stub shape) |
| **The body is still in the dex** | Alignment needs two byte streams | Method has `code_off == 0` (`compare` reports `stripped`) |

The third is the one that kills the method most often in practice: a VMP that *extracts*
bodies to a native interpreter leaves nothing to align. The differential route then has no
input at all, and no amount of clever fixture design creates one. Check for it before
spending any time here.

## 2. Cost table — which links can be automated, and which cannot

This is the part the method's public descriptions leave out. The chain is six links; two
of them are unavoidably human, and pretending otherwise is how a "harness" ships that has
never once been run against a real target.

| # | Link | Automation | Where a human must stand | Time cost | Failure mode |
|---|---|---|---|---|---|
| 1 | Compile the coverage fixture into a dex + APK | **Full** — `scripts/vmp_diff_harness.py build`, measured | none | ~40 s on this machine (javac + d8 + aapt2), ~1 s of it the script | toolchain absent or version-drifted; `d8` rejects a non-existent `--output` directory, `aapt2 link` rejects `android:` attributes without `android.jar` |
| 2 | **Submit to the hardening platform** | **None. Not automatable.** | 100 % — a browser, an account, sometimes a queue and a review | minutes to **days**; the platform decides | **the binding constraint of the whole route.** No public API; per-account rate limits; uploads are frequently gated behind registration; the artifact often comes back as a download page rather than a file path. A synthetic fixture may simply be **refused** (no real app shape, no certificate, no package identity) |
| 3 | Retrieve the hardened output and extract its dex | Partial — if the output is an APK, `unzip` + `dexutil.load_dex` handles it | download and hand-off | seconds, once the file exists | output is an APK whose dex is *also* encrypted, or the platform returns only a repacked APK with a native loader and no readable dex |
| 4 | Derive the correspondence | **Full** — `compare`, measured end to end | none | **sub-second** on a 3,065-instruction fixture | alignment slips (see); engine is not a pure relabelling |
| 5 | Prove the derived table | Partial — the mechanical half is scripted and measured; the judgement is not | decide whether the held-out check was passed or merely not attempted | minutes | a table that is *self-consistent* but describes a stub () |
| 6 | Render Smali from the restored stream | Full — `emit-smali`, measured | none | sub-second | table has holes; restored stream decodes short of the method end |

**Conclusion, stated plainly: do not build a fully automatic pipeline.** Link 2 is
irreducibly manual — the platform has no interface a script can drive, and its output
cadence is not one a pipeline can wait on. The right shape is what this repository ships:

- links 1, 4 and 6 as **reliable local tools** (they are deterministic and were measured);
- link 5 as **a checklist plus one scripted test** () — the judgement stays human;
- link 2 as **a documented manual step**, with its cost stated up front, so nobody writes
  an orchestrator that waits forever on a web form;
- and links 4–5 **self-verifiable without the platform at all**, which is what `simulate`
  exists for. You can prove your comparison logic against a known table today; you cannot
  prove the engine's behaviour until a human uploads a fixture.

The practical consequence: the deliverable of this route is an **analysis report with a
stated boundary**, not a pipeline. Say so before starting.

## 3. The coverage fixture — what a compiled probe can and cannot reach

A Java-compiled fixture reaches **218 of the 224 named opcodes in this repository's format
table (97.3 %)** — that number is measured, not estimated, and the six it misses are
structural rather than incidental. The reason to care is direct: **an opcode your fixture
never emits leaves no known plaintext, so its substitution is unreadable by construction.**

| Missed opcode | Why a javac + d8 fixture cannot reach it |
|---|---|
| `const-string/jumbo` (0x1b) | needs a `string_ids` index > 65535, i.e. a fixture shipping 65,536+ string constants |
| `goto/32` (0x2a) | needs a >32767-code-unit backward jump; javac refuses the method first with `error: code too large` — its own 64 KB per-method bytecode cap. **Measured** on a generated 33,000-statement loop |
| `const-method-handle` (0xfe), `const-method-type` (0xff) | no Java-language literal exists for these constants; reachable only via hand-written smali or direct dex construction |
| `move-object/16` (0x09) | needs **both** registers ≥ 256; the object frame pushes the source past 256 but d8 encodes that as `move-object/from16` |
| `invoke-custom/range` (0xfd) | d8 emitted the 35c form for every lambda shape tried, including a six-parameter one |

What the fixture **does** cover, by construction, and the design decisions that get it
there (each of these was a measured gap before it was closed):

- **Three-register forms.** javac emits the `/2addr` form whenever the destination is one
  of the operands, so `sub-int`, `div-int`, `rem-int`, `and-int`, `or-int`, `xor-int`,
  `shl-int`, `shr-int`, `ushr-int` and their long/float/double counterparts are **absent**
  from ordinary code. Three distinct locals per operation is what forces them into the
  stream; the `/2addr` forms then need the accumulator spelling. Both are wanted.
- **Literal widths.** `div-int/lit16` needs a divisor in 128..32767; `and-int/lit8` needs a
  mask inside −128..127. Writing `& 255` produces `and-int/lit16` and silently skips the
  lit8 form.
- **Per-type field access.** `iget-wide`, `iget-object`, `iget-boolean`, `iget-byte`,
  `iget-char`, `iget-short` and the `sget` set all appear only when the load targets a
  **fresh local**. Accumulating into an existing register is where d8 narrows the access.
- **`/range` invokes.** The 35c invoke forms carry at most five argument registers, so a
  seven-register call (`this` plus six ints) is what makes the `/range` encoding the only
  legal one.
- **Wide registers and long jumps** — `move/16`, `move-wide/16`, `move-object/from16`,
  `goto/16` — have **no hand-written form at all**. They exist only past a register-number
  (≥256) or branch-distance (>127 code units) threshold, so the generator emits bulk
  source: 300 int locals, 140 long locals, 160 object locals, a 200-statement loop body.
  Measured yield: `move/16` ×46, `move-wide/16` ×20, `move-object/from16` ×161, `goto/16` ×1.
- **Payloads and structure**: `packed-switch`/`sparse-switch` with their payload blocks,
  `fill-array-data`, `filled-new-array/range`, try/catch ranges with `move-exception`,
  `monitor-enter`/`monitor-exit`, `instance-of`/`check-cast`, and `invoke-custom` /
  `invoke-polymorphic` (which is why `d8 --min-api 26 --no-desugaring` is the default —
  desugaring replaces lambdas with synthetic classes and the two opcodes disappear).

**Report the coverage every time.** `build` prints it, `audit` recomputes it for any dex.
A differential run whose coverage is 60 % produces a table that is 40 % missing, and
nothing in the output will say so unless you look at this number.

## 4. Extracting the correspondence

`compare ORIGINAL HARDENED` does four things, and the first three are diagnostics that
decide whether the fourth is meaningful:

1. **Pair methods** by `(class, name, descriptor)` and classify each pair. `aligned` means
   both sides have a `code_item` of **identical `insns_size`** — the only state in which
   projection is legal. `resized` means the length moved. `stripped` means the hardened
   method has `code_off == 0`. `missing`/`added` mean the method set itself moved.
2. **Project and sample.** For each aligned pair, walk the original's decoded instruction
   list; for instruction at original offset *o*, read the hardened byte at
   `hardened.insns_off + (o − original.insns_off)`. Record `(original opcode → hardened
   byte)` with a count.
3. **Aggregate and audit the aggregate.** Per original opcode: one candidate byte and the
   row is `high`; more than one and the row is a `conflict`. Then the **reverse
   direction** — build `private byte → set of original opcodes` and flag every private byte
   claimed by more than one original. This reverse pass is not a nicety; it is the only
   thing that catches the stub shape ().
4. **Emit a run-level verdict**, because a table is dangerous without one: `usable`,
   `partially-usable`, `not-usable`, or `not-applicable` with the reason. A `not-applicable`
   run exits non-zero.

Unreadable opcodes are reported as `undetermined` with the reason — either the fixture
never emitted them () or the dex slot is unallocated. They are **not** guessed at.

## 5. Proving the table — the part that decides whether any of this is real

A candidate table is a hypothesis. Four checks, in increasing order of what they can
falsify:

**a. Closed-loop regression — measured, and the strongest available without a platform.**
`simulate` relabels a fixture's opcodes through a bijection whose ground truth it writes
out; `compare` must re-derive that table from the two dexes alone. Measured on this
repository's fixture: **218 rows derived, 218 of 218 emitted opcodes recovered, zero
entries wrong, zero entries fabricated, zero non-injective private bytes, verdict
`usable`.** Any change to the comparison logic that breaks this check is a regression, and
the check needs no platform, no device and no network.

**b. Injectivity — the check that catches a confident wrong answer.** Every private byte
must be claimed by exactly one original opcode. Measured against the stub shape (bodies
replaced by an equal-length `return-void` fill): per-opcode reading looks *perfect* — 218
rows, all `high`, zero conflicts — because every original opcode maps to the same byte.
Only the reverse direction exposes it: one private byte claimed by **218** originals →
`NOT-USABLE`. A table produced without this check would have been silently worthless.

**c. Held-out consistency.** Derive the table from one subset of methods, then use it to
disassemble a **different** subset that contributed nothing to the derivation. A correct
table restores the instructions such that the walk lands exactly on
`insns_off + insns_size × 2` and every branch target lands on an instruction boundary. A
wrong or incomplete table desynchronises and says so. `emit-smali`'s
`instructions restored` / `unmapped-opcode stops` counters are the readout: on the measured
fixture, 3,065 restored and 0 stops.

**d. Cross-check against a second, independent recovery.** The same private opcode space
observed through a *different* route — an in-memory dump of the original dex alongside the
hardened one, or the `/proc/<pid>/mem` route in
`advanced-unpacking.md` §Dumping when frida is refused — is the only evidence that the
platform's transformation is the one you assumed. **Not done here**; it requires a real
VMP sample and a real platform, and is the honest gap in this file.

Note what none of these checks establish: that the engine's substitution is *stable across
inputs*. Fixture-derived tables have been reported in public work to drift per
vendor-version and per hardening pass. Re-derive per target; never cache a table.

## 6. Generating Smali from a restored stream

`emit-smali HARDENED_DEX --table TABLE.json` restores opcode bytes through the table and
renders method bodies as an annotated smali **reading skeleton**:

- Boundaries come from the table itself — once a byte maps back to a standard opcode the
  standard length table applies to that instruction, so the walk is self-bootstrapping.
  A byte with no table entry stops that method's walk, and the count of such events is
  printed as the honest coverage measure.
- `.class` / `.super` / `.source` / `.method` headers are real, with access flags decoded
  from `access_flags`, so the skeleton is readable as smali rather than as a hex dump.
- Payload blocks (`packed-switch-payload` etc.) are stepped over by their own layout, not
  treated as opcodes.

**It is explicitly not assembliable, and the output says so in its first ten lines.**
Recovered: instruction boundaries and opcode names. Not recovered: register numbers,
field/method/string indices as the engine rewrote them, and any register re-allocation —
**no map for those exists in this method at all.** Feeding the skeleton to a smali
assembler produces an empty method, which looks like success and is not.

## 7. When this route does not work — the honest retreat

| What `compare` reports | What it means | Do this |
|---|---|---|
| `verdict: not-applicable`, `stripped` > 0 | bodies left the dex for a native interpreter | the differential has no input. Stop. Return to `advanced-unpacking.md` §The honest boundary: real Dex VMP and price the island honestly |
| `verdict: not-applicable`, `resized` > 0 | the engine's stream has its own length table | the projection premise is false. Stop rather than guessing boundaries |
| `verdict: not-usable`, one private byte shared by many originals | bodies replaced by a common stub | the engine did not relabel per-opcode here. Stop |
| `verdict: partially-usable`, conflicts ≤ 30 % | partial relabelling, or alignment slipping on some methods | usable only for the `high` rows; say so and stop at the unreadable ones |
| `usable`, but coverage was low | a complete table over an incomplete opcode set | usable, with the uncovered opcodes named as unreadable |

And the retreat that outranks all of them: **the cheaper question is whether the behaviour
you need exists outside the virtualized island.** A hook at the method's Java boundary, an
emulated call to the routine rather than a reading of it
(`emulation-and-rpc.md`), or a server-side answer frequently reaches the goal without ever
paying for the island. Weeks of table recovery is the expensive way to ask a question a
boundary hook answers in an hour.

## 8. Decision summary

| Observation | Action | Where |
|---|---|---|
| Bodies present, decode as nonsense | Diagnose real VMP before anything else | `advanced-unpacking.md` §The honest boundary: real Dex VMP |
| Need the private opcode mapping | Build the coverage fixture, then submit it by hand | `scripts/vmp_diff_harness.py build`; §2 of this file |
| Asked to "automate the whole chain" | Say which link cannot be automated and what it costs | §2 — the platform step is manual, by construction |
| Fixture coverage below ~90 % | Add the missing opcode classes before submitting |, and the `audit` report |
| Two dexes in hand | Derive the candidate table, read the verdict first | `scripts/vmp_diff_harness.py compare` |
| About to trust a derived table | Run the closed loop, the injectivity check and a held-out subset | §5 — a/b/c are scripted |
| Table complete | Render the skeleton; expect operands, not registers | `scripts/vmp_diff_harness.py emit-smali` |
| `resized` / `stripped` / stub verdict | Stop and say so | §7 |
