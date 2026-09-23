# Byte-level dex patching — equal-length edits, and the traps that make them fail

`dex-patching.md` covers rewriting a **method body** with dexlib2. This file covers the other
technique: rewriting **a few bytes in place**. Reach for it whenever the change can be expressed as
"make this branch do the other thing" or "make this constant a different constant", because it is
strictly safer than rebuilding a method — but only if you respect the constraints below, which are
not optional and are not obvious.


**Load this when:** the change fits in an existing instruction slot or constant, and you want nothing to move (no offset, try/catch or debug pointer invalidated). It gives the equal-length edit, its legality rules, and where it silently fails.

## Why equal-length, in numbers

A method-level rebuild is not free. Measured on one R8-processed sample (4.32 MB single dex):

| | original | after a 2-method dexlib2 rewrite |
|---|---|---|
| dex size | 4.32 MB | **7.73 MB** |
| `debug_info` table | 924 bytes | **22,828 bytes** |
| class set / access flags | — | identical (zero drift) |

The class table is unchanged, so the rebuild is *correct* — but dexlib2 does not reuse R8's shared
`debug_info` entries and the file grows ~80%. That is the real cost of "surgical" method rewriting,
and it matters because it changes the byte layout of everything after the edited methods.

An equal-length edit changes **only the bytes you chose**. No offset moves, so no try/catch block,
no debug-info pointer, and no branch displacement anywhere in the file can be invalidated by
construction. That property is worth more than the convenience of writing smali.

**Decision rule:** if the change fits in an existing instruction slot or a constant, patch bytes. If
it genuinely needs new instructions or a different register allocation, rebuild the method — and do
it in a copy so you can diff the tables.

## Locating the exact byte offset of an instruction

This is the part that eats hours if you improvise. Three approaches, worst to best.

**Do not reconstruct offsets from a `.line` listing.** baksmali emits one `.line` per *source* line,
and one source line can be attributed to several consecutive instructions. The `.line` values
therefore repeat and do not map 1:1 to offsets. A listing walker built on `.line` silently produces
zero candidates for a branch you can see with your eyes.

**Do not match on a guessed byte sequence.** Instruction encodings vary with register numbers and
operand widths; a pattern that looks right (`38 xx`) can be a different instruction than you think
(`0x38` is `if-test`, 22t and 4 bytes — **not** `if-testz`).

**Do this instead: walk the dex structure to the method, then decode.** Resolve class → `class_data_item`
→ method (`code_off`) → `code_item` → instruction stream, and decode forward with a complete format
table. Then match on *decoded semantics* ("an `iget-boolean p1` immediately followed by `if-nez p1`
whose target reads field `X`") rather than on bytes. `scripts/dex_find_insn.py` does this; the
decoder in `scripts/dexutil.py` is the reusable part.

Three details in the walk that silently produce wrong answers:

- **`class_data_item` member indices are *diffs*.** `field_idx`, `method_idx` are encoded as deltas
  against the previous entry in the same list and must be accumulated. Reading a raw uleb as an
  absolute index gives you real-looking wrong members — you will "find" a method that is not the one
  you asked for and not notice.
- **Payload `nop`s are not `nop`s.** dalvik encodes switch/array payloads as `00 <ident> <size>` with
  `ident` in 1..3. A plain `00 00` is an ordinary one-unit `nop`. Treating every `00` as a payload
  swallows the next instruction and desynchronises the whole rest of the method.
- **The header field order is not what you remember.** After `magic(8) + checksum(4) + signature(20)`,
  the offsets are `file_size 0x20, header_size 0x24, endian 0x28, link_size 0x2C, link_off 0x30,
  map_off 0x34, string_ids_size 0x38, string_ids_off 0x3C, type_ids 0x40/0x44, proto_ids 0x48/0x4C,
  field_ids 0x50/0x54, method_ids 0x58/0x5C, class_defs 0x60/0x64, data 0x68/0x6C`.
  Print the parsed sizes and compare against the file before trusting anything downstream.

## Instruction format table (the part that must be right)

An operand width wrong by one byte desynchronises the decode from that point on, and the failure looks
like "the instruction I want does not exist". These are the groups that matter in practice:

| opcode range | format | code units |
|---|---|---|
| `01 04 07 0A 0B 0C 0D 0E 0F 10 11 12` | 12x / 11x / 11n / 10x | 1 |
| `13 15 16 17 19 1B 20 21 23 24` | 21s/21h/21c/22c/35c/3rc | 2 |
| `14 18 1A 22 25 27 28 29 2A 2B` | 31i/31c/31t/30t/20t/switch | 3 |
| `02 05 08` | 22x | 2 |
| `03 06 09` | 32x | 3 |
| `2C`–`31` | 23x | 2 |
| **`32`–`37`** | **22t if-test** (2 regs + int16) | **2** |
| **`38`–`3D`** | **21t if-testz** (1 reg + int16) | **2** |
| `44`–`51` | 23x aget/aput | 2 |
| `52`–`5F` | 22c iget/iput | 2 |
| `60`–`6D` | 21c sget/sput | 2 |
| `6E`–`72` / `74`–`78` | 35c / 3rc invoke | 3 |
| `7B`–`8F` | 12x unop | 1 |
| `90`–`AF` | 23x binop | 2 |
| `B0`–`CF` | 12x binop/2addr | 1 |
| `D0`–`D7` | 22s binop/lit16 | 2 |
| `D8`–`E2` | 22b binop/lit8 | 2 |

**Self-check that costs nothing:** decode the whole method and assert you land **exactly** on
`insns_off + insns_size*2`. If you overshoot or undershoot, the table is wrong somewhere and every
offset you derived is suspect. Also scan the decoded register numbers: a method whose `registers`
count is 12 cannot use `v13`, so any `v13+` in the output is proof of desync.

**Long conditional branches are two instructions.** A conditional jump has a 16-bit displacement, but
when you see `if-nez vX, :label` in smali and `:label` is far away, the assembler may have emitted
`if-*` followed by a separate `goto`. When hunting a branch, do not assume the pattern is
"branch → target"; confirm by decoding.

## Neutralise a branch, do not redirect it

Once you have decided which side of a condition you want, the safest edit is to **remove the branch**,
not to point it somewhere else.

| Edit | When it is right | Risk |
|---|---|---|
| `if-*` → `nop` pair (**preferred**) | You want the **fall-through** path | None. No new control-flow edge is created |
| `if-*` → `goto` (+ same displacement) | You want the **branch-taken** path | Introduces an edge. It may land on a `move-result*`, which the verifier rejects |
| flip the sense (`if-nez` → `if-eqz`) | Polarity is the only problem | Same edge as above, different destination |

The `move-result` rule: `move-result*` must be **immediately preceded by its producing invoke** in the
instruction stream. A branch whose target is a `move-result` bypasses the producer and the class fails
to load with `VerifyError: ... copyRes vN <- result0 type=Undefined`. A linear "is the previous
instruction the producer" check does **not** catch this — you need the CFG view: *does any branch
target this `move-result`?* `scripts/dex_check_verifier.py` answers that question directly.

A `nop` pair cannot create that problem, which is why it is the default choice.

**Polarity is the other silent killer.** Field names lie about intent often enough that you must read
the *branch structure*, not the name. In one real case the config field was `enabled`, the smali was
`if-nez v, +6`, and the fall-through was `startActivity(main)` while the branch target was the
countdown block. So `enabled == true` was the value that *skipped* the promo — the opposite of the
literal reading. **Always decode both sides of the branch and name what each one does before editing.**
Getting this backwards produces a build that does the exact opposite of the goal and still starts
cleanly, so it survives casual testing.

## The dex header has two integrity fields, and order matters

Any edit to a dex body invalidates both header integrity fields. Recompute them **in this order**:

```
bytes 12..32 = sha1(data[32:])        # signature first
bytes  8..12 = adler32(data[12:])     # checksum last — it covers the signature bytes
```

Writing them in the reverse order produces a header that looks plausible and never verifies, because
the adler32 was taken while the signature field was still zeroed.

**Why this is dangerous rather than merely broken:** Android logs
`Failure to verify dex file ...: Bad checksum (computed, expected)` — note that the *real* adler32
appears as the "expected" value, which reads backwards — and then falls back to interpreting the dex.
The process may still start, but the class loader can fail to resolve ordinary classes
(`ClassNotFoundException: <your Application class>`), so the symptom is "the APK I built is broken"
rather than "two header fields are stale".

**Aggravating detail:** some producers ship a dex whose `signature` field is **all zeros** (a known
R8/optimiser artifact). On such a file the wrong order is self-consistent until the first patch, so
the bug is invisible until you edit something — and then looks like your edit caused it.

`scripts/dex_patch_bytes.py` recomputes both fields in the correct order and refuses to write if the
result does not self-verify.

## Worked shape of a patch script

Keep these properties; they are what make the edit auditable a month later:

1. **Locate by structure + decoded semantics**, never by a hard-coded offset alone.
2. **Assert the old bytes** before replacing, and abort on mismatch. A silent mismatch means the
   sample changed or your understanding did.
3. **Equal length in, equal length out.** Assert `len(new) == len(old)`.
4. **Recompute both header fields**, then assert `adler32(data[12:]) == header_checksum` and
   `sha1(data[32:]) == header_signature` on the bytes you are about to write.
5. **Re-decode the patched method** and print the instruction you changed, plus confirm the
   instruction that should follow it still does. Two instructions of output is enough to catch the
   "landed on the wrong site" class.
6. **Report the size delta** (should be 0) and before/after hashes of both the dex and the APK.

## Verification specific to byte patches

`patch-audit.md` covers the general audit. Two checks matter more here:

- **Assert the instruction count and every branch target are unchanged.** Compare a decoded listing of
  the whole method before and after: same instruction count, same offsets, same targets. If the count
  changed, you replaced a 4-byte instruction with a 4-byte *pair* and the extra decode boundary is
  expected — but say so explicitly rather than letting a diff tool surprise the next reader.
- **`VerifyError` is a class-load failure, not a startup failure.** If the app starts and one screen
  is dead, or a secondary class is missing, suspect a verifier violation in the method you edited.
  `logcat` shows it as `E/dalvikvm` or `E/art` with the class name; it does not always surface as a
  crash dialog.

## When not to use this technique

- The change needs new instructions, a new register, or a different call — go to method rewriting.
- The change is a **short string constant** whose new value is a different length — you cannot grow the
  string in place. Equal-length string swaps work (`pitfalls.md` P2 on the string-id ordering guard).
  **A different-length value is not a byte patch at all**: `scripts/dex_strpatch.py` enforces equal
  length and will refuse it, so the work belongs to method rewriting (`references/dex-patching.md`)
  or a full rebuild — do not look for a "different-length byte patcher" in this kit, there isn't one.

- The target is a **multi-dex** app and you intend to move code between dexes. Byte patching stays
  inside one dex by definition.
