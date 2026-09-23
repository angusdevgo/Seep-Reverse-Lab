# Extension verification — schema-free protobuf decoding

Covers the pass that added `skills/apk-reverse/scripts/protobuf_decode_raw.py` and the measured half
of `references/protocol-reverse.md` §1 ("The decoder that ships here"). Strength labels as defined in
this directory's README: **observed** (exact command + output recorded here), **inferred** (follows
from observed facts, step not executed), **unverified** (assumed or externally reported, not
independently confirmed here).

Reference environment for this pass: Windows host, Python 3.14.0, `protobuf` **6.33.6**. No device
was used (see §7) — every result below is host-side, offline, and reproducible with the standard
library alone. Workbench artifacts live in `tools/_work/t5-proto/` (not part of the skill, and
`tools/` is gitignored).

The delivered script imports **no** third-party module. `google.protobuf` is used here for one
purpose only: to *generate* reference bytes from a real schema, so the hand-written decoder is
checked against the reference implementation instead of against itself.

---

## 0. Summary of what this pass established

| Claim | Label |
|---|---|
| `protobuf_decode_raw.py` `--help`, `--selftest`, hex/file/stdin inputs, `--json`, `--max-depth`, `--reencode` all run on this host | observed |
| 26/26 built-in known-answer checks pass (field decode **and** byte-exact round trip) | observed |
| The decoder agrees field-by-field with a message serialized by `google.protobuf` 6.33.6, and its re-encode is byte-identical to `SerializeToString()` | observed |
| A real AndroidX DataStore file written by `scripts/datastore_inject.py` decodes to the correct structure and round-trips byte-identically | observed |
| Editing one value in the JSON tree and re-encoding produced a file that `datastore_inject.py` read back as the edited value | observed |
| proto3 zero semantics: an implicit (no-presence) field set to 0 writes **nothing**; a presence-carrying field set to 0 writes its tag plus a zero byte | observed |
| A packed field and a nested message are **both** legal readings of the same length-delimited bytes (measured on real encoded bytes, not argued) | observed |
| `--split varint-length` is protobuf's `writeDelimitedTo` framing; handed a gRPC frame it silently produced 5 frames instead of failing | observed |
| Decoding a **device-side** protobuf file (real app data read over adb) | **not done** (device lock held by another agent; §7) |
| Any protobuf payload recovered from the benchmark APKs | **not done** — the one APK scanned carries no `.pb`/`.proto` resource (§7) |
| `blackboxprotobuf` / `protobuf-inspector` behaviour | unverified (not installed on this host; the reference still says so) |

---

## 1. Input forms, measured

```
$ python skills/apk-reverse/scripts/protobuf_decode_raw.py --help
usage: protobuf_decode_raw.py [-h] [--hex STR] [--json] [--max-depth N]
                              [--no-expand] [--split {none,varint-length}]
                              [--reencode JSON] [--out PATH] [--check PATH]
                              [--selftest]
                              [input]
...                                                                    exit = 0
```

Hex text, a binary file and stdin are all accepted, and the two stdin shapes are told apart without
a flag:

```
$ '0a220a176578616d706c655f6578706972795f65706f63685f6d7312072080b08fe6b277' \
      | python skills/apk-reverse/scripts/protobuf_decode_raw.py -
input: stdin (hex text), 36 byte(s)
frame 0  bytes 0..36  (36 B)  status=end_of_buffer
  f1  len-delimited(34)  view=nested_message
      ...

$ cmd /c "python skills\apk-reverse\scripts\protobuf_decode_raw.py - < tools\_work\t5-proto\ds.preferences_pb"
input: stdin (raw bytes), 81 byte(s)
frame 0  bytes 0..81  (81 B)  status=end_of_buffer
```

Separators and escapes, in one command (two frames, `0x` prefixes, spaces, a `\xNN` escape):

```
$ python skills/apk-reverse/scripts/protobuf_decode_raw.py --hex "0x08 0x96 0x01 | \x12\x07testing"
frame 0  bytes 0..3  (3 B)  status=end_of_buffer
  f1  varint  150
frame 1  bytes 3..12  (9 B)  status=end_of_buffer
  f2  len-delimited(7)  view=utf8_string
      ...
      string: 'testing'
```

`08,96,\n01` (commas and a newline) and the single token `0x089601` both decode to the same field.
**This command is the one that found the script's first real defect — see §6.**

---

## 2. Known-answer fixtures: `--selftest`

Twelve fixtures are built byte by byte inside the script (no external file, no schema), covering a
canonical varint, a multi-byte varint, `uint64` maximum, two-level nesting, a packed field, fixed64
and fixed32, an explicit zero, a deprecated group, a non-canonical varint, a 10-byte overflow, two
top-level messages in one stream, and varint-length framing. Each is decoded with an expected value
**and** passed through the round trip.

```
$ python skills/apk-reverse/scripts/protobuf_decode_raw.py --selftest
== known-answer fixtures (bytes produced by hand in this script) ==
  canonical varint 150                          089601
    field 1 varint value                   PASS   150
  unsigned max uint64                           08ffffffffffffffffff01
    field 1 varint value                   PASS   18446744073709551615
  nested two levels                             089601120774657374696e671a060801120210072206038e029ea705...
    field 3 nested child count             PASS   2
  deprecated group 3/4                          43080544
    field 8 has children                   PASS   1
  non-canonical varint                          08968100
    field 1 varint value                   PASS   150
  10-byte varint overflow                       08ffffffffffffffffff7f
    field 1 varint overflow                PASS   True
  ...
== round trip: decode -> re-encode -> byte comparison ==
  canonical varint 150                          MATCH  (1 fields, 1 identical)
  nested two levels                             MATCH  (7 fields, 7 identical)
  non-canonical varint                          MATCH  (1 fields, 0 identical) re-encode emits the minimal
                                                       form 089601, original 08968100, and the report states why
  varint length framing                         MATCH  (7 fields, 7 identical)

== the two wire-format traps ==
  explicit zero bytes 2800 decodes to value 0; absent field decodes to no fields at all: PASS
  packed payload 038e029ea705 offers live=['bytes', 'packed_varint'], rejected=['nested_message',
  'utf8_string'] -> view=packed_varint : PASS

selftest: 26/26 PASS                                                   exit = 0
```

The non-canonical fixture is the one deliberate exception: the re-encode is *expected* to differ
(`08968100` -> `089601`, the minimal form), and the tool reports the difference with its reason
rather than normalising it away silently. That is the honest form of "round trip": a difference that
is explained is evidence; a difference that is not is a bug.

---

## 3. Cross-check against the official protobuf runtime

`tools/_work/t5-proto/official_ref.py` builds a real `FileDescriptorProto` (`Outer` with int64 /
string / message / repeated int32 (packed) / fixed64 / float / enum / proto3-optional / bytes /
fixed32 fields, plus a nested `Inner`), serializes it with `SerializeToString(deterministic=True)`,
and then asks the hand-written decoder to reproduce it.

```
$ python tools\_work\t5-proto\official_ref.py
== official runtime bytes (protobuf 6.33.6) ==
  58 B: 089601120774657374696e671a0508011201782206038e029ea705290807060504030201350000c03f380240004a06038e029ea70555efbeadde

== field-by-field agreement with the schema ==
  field 1 count == 150                                 PASS  decoded 150
  field 2 name == "testing"                            PASS  decoded 'testing'
  field 3 inner walked as a nested message             PASS  view=nested_message children=2
  field 4 nums read as packed [3,270,86942]            PASS  view=packed_varint values=[3, 270, 86942]
  field 5 stamp fixed64 hex 0807060504030201           PASS  0807060504030201
  field 6 ratio fixed32 hex 0000c03f (1.5f)            PASS  0000c03f
  field 7 color enum == 2                              PASS
  field 8 explicit_zero is present and 0               PASS
  field 9 blob hex 038e029ea705                        PASS
  field 10 crc fixed32 hex efbeadde                    PASS  efbeadde

== round trip against the official bytes ==
  re-encode is byte-identical to SerializeToString()    PASS  10/10 fields identical
  no field was rewritten                                PASS  []

official-runtime cross-check: 21/21 PASS                               exit = 0
```

Field 5 is the useful false-friend: the decoder offers `as_double_repr` for those 8 bytes, and the
official value is a `fixed64` integer. Nothing on the wire distinguishes them, which is why the
candidate list exists instead of a single typed value.

### 3.1 The four-way tie, measured on real bytes

A really-encoded nested message — `Inner{id:1, tag:"x"}` inside field 3, inner payload `0801120178`
— is reported as:

```
  nested message payload 0801120178 -> {'nested_message': 0.5, 'packed_varint': 0.5,
                                        'utf8_string': 0.35, 'bytes': 0.2}
```

`0801120178` is simultaneously a valid two-field message **and** a valid five-element packed varint
array. The decoder refuses to choose; the `tie:` line states that the displayed `view` is a display
default. A real packed field (`2206038e029ea705`) yields `packed_varint 0.55` with
`nested_message` **rejected** — the rejection is printed with its reason instead of being omitted.

### 3.2 proto3 zero — the reference sentence, corrected by measurement

The reference previously stated that `28 00` is byte-identical to an absent field. The runtime shows
that the sentence needs splitting into two halves:

```
  implicit int64 count = 0      : 120178 (3 B)
  count never touched           : 120178 (3 B)
  implicit (no presence) zero is byte-identical to absent         PASS
  that byte string contains no tag for field 1                    PASS
  optional int32 explicit_zero=0: 1201784000 (5 B)
  a presence-carrying field DOES put tag+0x00 on the wire         PASS  1201784000
  the optional zero costs 2 bytes the implicit zero never costs   PASS  5 B vs 3 B
  the decoder sees that 0 and flags the ambiguity                 PASS  ["proto3_explicit_zero"]
```

Read it as two separate facts:

1. For a field **without** presence, `value = 0` and "never set" are the same bytes (no bytes at
   all), so a field **missing** from a decode is not evidence that the value in use was 0.
2. A `0` that **is** on the wire was emitted on purpose — a presence-carrying field (`40 00` here,
   field 8) or a hand-rolled writer. The decoder cannot tell which, so it flags the case.

`references/protocol-reverse.md` §1 consequence 3 now carries that correction.

---

## 4. A real AndroidX DataStore file

`scripts/datastore_inject.py` writes the real AndroidX Preferences protobuf container
(`map<string, Value>`); the decoder has never seen that schema.

```
$ python skills/apk-reverse/scripts/datastore_inject.py --file tools\_work\t5-proto\ds.preferences_pb \
      --key example_expiry_epoch_ms --type long --value 4102444800000 \
      --extra example_flag=true:bool --extra example_name=hello:string
[ok] wrote tools\_work\t5-proto\ds.preferences_pb (81 bytes)

$ python skills/apk-reverse/scripts/protobuf_decode_raw.py tools\_work\t5-proto\ds.preferences_pb
input: tools\_work\t5-proto\ds.preferences_pb, 81 byte(s)
frame 0  bytes 0..81  (81 B)  status=end_of_buffer
  f1  len-delimited(34)  view=nested_message
      ...
      f1  len-delimited(23)  view=utf8_string
          string: 'example_expiry_epoch_ms'
      f2  len-delimited(7)  view=nested_message
          ...
          f4  varint  4102444800000
  f1  len-delimited(18)  view=nested_message      <- the second map entry
      ...
```

The map-entry structure, the key strings and the `long` value all come out correctly with no schema;
every length-delimited field still shows its ties (`nested_message` vs `packed_varint` vs
`utf8_string`) because those ties are real.

### 4.1 Round trip, and an edit confirmed by the other tool

```
$ python skills/apk-reverse/scripts/protobuf_decode_raw.py tools\_work\t5-proto\ds.preferences_pb --json > tools\_work\t5-proto\ds.tree.json
$ python skills/apk-reverse/scripts/protobuf_decode_raw.py --reencode tools\_work\t5-proto\ds.tree.json \
      --out tools\_work\t5-proto\ds.reenc.bin --check tools\_work\t5-proto\ds.preferences_pb
re-encoded 81 byte(s) from 3 field(s)
  fields re-encoded byte-identically: 3/3
  written to tools\_work\t5-proto\ds.reenc.bin
  check against tools\_work\t5-proto\ds.preferences_pb (81 B, the whole file): MATCH    exit = 0
```

Then one value is edited in the JSON tree and re-encoded:

```
editing field 4 from 4102444800000
re-encoded 80 byte(s) from 3 field(s)
  fields re-encoded byte-identically: 2/3
  CHANGED field 1: expected 0a22...80b08fe6b277, got 0a21...20ffc7afa025 (the tree was edited)

$ python skills/apk-reverse/scripts/datastore_inject.py --in tools\_work\t5-proto\ds.edited.bin --list
[in] tools\_work\t5-proto\ds.edited.bin (80 bytes)
   example_expiry_epoch_ms          long=9999999999   (value=6 bytes)
   example_flag                     bool=True   (value=2 bytes)
   example_name                     string='hello'   (value=7 bytes)
```

Two independent facts in one run: the file shrank 81 -> 80 B because a 6-byte varint became a
5-byte one **and the enclosing length prefix was recomputed** (the re-encode rebuilds lengths, it
does not copy them), and a different tool of this repository read the edited bytes back as the new
value. A round trip that only agrees with itself would not have caught either.

---

## 5. Framing: `writeDelimitedTo` is not a gRPC frame

`tools/_work/t5-proto/framing_check.py`:

```
message (20 B): 089601120774657374696e672206038e029ea705
writeDelimitedTo form (21 B): 14089601120774657374696e672206038e029ea705
  varint-length framing: exactly one frame                           PASS  got 1
  a second message makes two frames                                  PASS
  gRPC frame (25 B): 0000000014089601120774657374696e672206038e029ea705
  decoded with --split varint-length: 5 frame(s): [(1, 1, 'end_of_buffer'), (2, 2, ...),
                                                   (3, 3, ...), (4, 4, ...), (5, 25, ...)]
  gRPC frames are NOT varint-length framed (the split misfires)      PASS  got 5 frame(s)
  stripping the 5-byte gRPC prefix decodes the message correctly      PASS  field 1=150, field 4=[3, 270, 86942]
  '|' separates two independently framed messages                     PASS  frames=2

framing check: 8/8 PASS                                                exit = 0
```

| Framing | Bytes in front of the message | `--split varint-length` |
|---|---|---|
| protobuf `writeDelimitedTo` | varint length | correct — 1 frame per message |
| gRPC | 1 compression-flag byte + **4-byte big-endian** length | **wrong, and it does not fail**: the 4 zero bytes become four empty frames |

The same gRPC bytes decoded with **no** splitting reported `stray_end_group` (exit 1), and a
`writeDelimitedTo` file decoded with no splitting reported the same error — that error is a *refusal*,
whereas the wrongful split is a *silent reinterpretation*. Strip the 5-byte gRPC prefix yourself
(`references/protocol-reverse.md` §3), and check the frame count either way.

A `--split varint-length` round trip compares **frame bodies only**, and says so:

```
  check against tools\_work\t5-proto\two_frames.bin (26 B, frame bodies only: 2 of 26 byte(s) are
  length prefixes (framing, not message data)): MATCH
```

---

## 6. Defects these checks found (in the code, not in the target)

Four defects, three of them in the delivered script, all found by the checks above rather than by
reading the code.

| # | Defect (observed) | How it surfaced | Fix |
|---|---|---|---|
| 1 | When two candidate readings tied, both were lowered to the same confidence as the `bytes` fallback, and the tie was then broken by **alphabetical order** — `bytes` sorts before `nested_message`, so a real nested message was never expanded and `--reencode` copied it as an opaque blob | `--selftest`: `nested two levels / field 3 nested child count` returned `0` instead of `2` | `bytes` now scores 0.2 and ties are broken by an explicit `VIEW_PRIORITY`, structural candidates first |
| 2 | In the `\xNN` path, whitespace and commas were kept as data bytes, so `"08 96 01 | \x12\x07testing"` decoded the space after the bar as `field 4 varint 18` and then hit `invalid_wire_type` | the input-form check in §1 | whitespace and commas are stripped before unescaping, in that branch too |
| 3 | Two fixtures were mis-designed, not the code: a bare packed stream and a length-prefixed frame were round-tripped as if each were one top-level message, which reported `FAIL` for correct behaviour | `--selftest` round-trip section | the packed fixture is now a field *value*; the framing fixture compares frame bodies |
| 4 | The cross-check's own assertion expected `0800` for the explicit zero, but the field under test is number 8, whose tag is `0x40` — the official bytes were `...4000`, and the assertion, not the decoder, was wrong | `official_ref.py` | assertion compares `4000` and the 2-byte cost |
| 5 | `--no-expand` did nothing: the expansion branch never consulted the flag, so a 7-level payload was still walked to the bottom | the deep-payload check below | the branch honours `--no-expand` and records `expansion: suppressed by --no-expand` on the field |
| 6 | Hitting `--max-depth` was invisible: the depth cut-off only appeared as a `rejected` note inside one candidate, so the report showed a shallow tree with no statement that anything had been left unexamined | the same check | a `depth_limit` ambiguity is emitted, naming the path and the limit |

Defect 1 is worth its own line in any future reader's mind: a *heuristic* tie-break silently changed
which bytes the tool re-emitted, and it was caught only because a fixture asserted a child count.
Defects 5 and 6 are the other direction — the tool silently *did more* than asked, and silently
*stopped* without saying so; both are ways a report can be read as complete when it is not.

### 6.1 The deep-payload check

A 7-level nesting (`08 01` wrapped six times in field 1, 14 bytes) is the fixture:

```
$ python skills/apk-reverse/scripts/protobuf_decode_raw.py tools\_work\t5-proto\deep.bin
frame 0  bytes 0..14  (14 B)  status=end_of_buffer
  [depth_limit] frame0.1.1.1.1.1.1 @2: a nested reading of this field was not attempted:
  --max-depth 5 reached. The bytes here may well be a message; re-run with a larger --max-depth
  before concluding that they are not

$ python ... tools\_work\t5-proto\deep.bin --max-depth 2
  [depth_limit] frame0.1.1.1 @2: ... --max-depth 2 reached. ...

$ python ... tools\_work\t5-proto\deep.bin --no-expand
      expansion: suppressed by --no-expand
```

The truncation is reported as an ambiguity with the path of the field it stopped at, so "no nested
message here" can never be read off a truncated tree.

---

## 7. What was **not** done

* **No device was used.** The pass intended to pull a real app's `.preferences_pb` from
  `<DEVICE>`: `python tools\_work\devlock.py acquire proto --timeout 1800` waited 120 s and timed out
  with the lock held by another agent (`held by bench for 297s`, note "L1 repack control+patched
  install & screen; L3 frida"). Per the two-strike rule the device source was dropped rather than
  contended for, and the real-file evidence comes from the DataStore file this repository's own tool
  writes (§4). Reading a **device-side** protobuf file with this decoder is therefore **unverified**.
  Device facts used elsewhere in this repository (attach-by-name, the broken `logd` channel) were
  not re-tested here.
* **No protobuf payload was recovered from the benchmark APKs.** Scanning the available sample
  (`<PKG>`-style de-identified, 4,293,620 B, 435 zip entries) for `.pb` / `.proto` / `protobuf`
  resources found none; the MASTG crackmes carry no protobuf at all. So no wild-captured payload was
  decoded in this pass — `inferred` for any claim that a real traffic body looks like these fixtures,
  though §3's bytes come from the reference implementation and §4's from a real AndroidX container.
* **No live traffic.** Nothing was proxied, so the gRPC section of the reference is exercised only
  as *framing* (§5), not as captured HTTP/2.
* `blackboxprotobuf` / `protobuf-inspector` were not installed or compared; the reference still
  labels them unverified.
* `--max-depth` is measured up to a 7-level fixture (§6.1); no real payload deeper than that was
  decoded, and no payload was decoded whose *only* reading is a deep message.

## 8. Artifacts produced by this pass

`tools/_work/t5-proto/` (not committed): `official_ref.py` (official-runtime cross-check, 21 checks),
`framing_check.py` (8 checks), `ds.preferences_pb` (81 B, real DataStore container),
`ds.tree.json` / `ds.edited.json` (decoded trees), `ds.reenc.bin` (byte-identical round trip),
`ds.edited.bin` (80 B, edited value read back by `datastore_inject.py`), `two_frames.bin`,
`frames.tree.json`, `frames.reenc.bin`.

Files changed in the repository by this pass: `skills/apk-reverse/scripts/protobuf_decode_raw.py`
(new), and `skills/apk-reverse/references/protocol-reverse.md` (a new measured subsection under §1,
the corrected proto3-zero wording in §1 consequence 3, and a new framing failure mode in §6).
`SKILL.md` and `README.md` were deliberately not touched; the index rows for the new script are
handed to the lead to register.
