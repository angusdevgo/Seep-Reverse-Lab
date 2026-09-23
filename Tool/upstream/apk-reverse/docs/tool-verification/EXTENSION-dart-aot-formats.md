# EXTENSION — Dart AOT string-table formats, measured on a real dual-ABI app

Evidence file for the `dart-aot.md` changes in this pass. Every claim below carries a grade:

- **observed** — a command was run here and its output is quoted in this file.
- **inferred** — follows from an observed fact or from documented mechanism; the step was not executed.
- **unverified** — assumed or reported elsewhere, not reproduced here.

Target identity is replaced with `<PKG>`; the artifact is referred to as "the sample". The technique
(tool, library, function, hardening product) is kept, per
`skills/apk-reverse/references/desensitization-and-leak-scans.md`.

## 1. What was measured

| Claim under test | Grade | Result |
|---|---|---|
| The arm64 Dart AOT string table is `[0x80\|(len<<1)\|two_byte][payload]` and the entries chain | **observed** | confirmed on 4,980 entries |
| The armv7 (32-bit) snapshot uses the *same* format | **refuted** | the same extractor keeps 0 entries; the tag byte is not present before the literal |
| An armv7 string record is `[length u32le][UTF-16LE chars]`, so the length field reads `len*2` | **refuted** | the u32 before the payload reads the **byte** count, and the payload is UTF-8 |
| The engine version banner always yields `x.y.z (stable) (…)` | **refuted** | a real `libflutter.so` carries `0.0.1` with a blank build id and no `(stable)` |
| An equal-length replacement of a data key is legal on both ABIs without recomputing the tag | **observed** (record layout), **unverified** (end-to-end device run) | the record is self-contained on both ABIs |

Two of the five were assumptions that would have been written into the reference as fact. Both were
killed by a single command each, which is the whole argument for measuring before documenting.

## 2. Sample and preparation

The sample is the locally supplied "complex encryption and hardening" APK (360 shell + Flutter).
The two AOT snapshots were extracted from the zip without repacking:

```
$ python -c "import zipfile; z=zipfile.ZipFile(r'存在问题和例子\<sample>.apk'); \
    [print(n, len(z.read(n))) for n in ('lib/arm64-v8a/libapp.so','lib/armeabi-v7a/libapp.so')]"
lib/arm64-v8a/libapp.so  16352152
lib/armeabi-v7a/libapp.so 17629776
```

Work copies live under the ignored workspace `tools/_work/dart/`; nothing from this evidence pass is
committed except the reference text.

## 3. The arm64 packed table — confirmed

```
$ python skills/apk-reverse/scripts/dart_pool_strings.py tools/_work/dart/app_arm64.so s64.tsv --min 6
candidates           : 17352
kept (run >= 3)      : 4980  (one-byte 4980 / utf16le 0)
below threshold      : 12372  [--keep-isolated to keep them]
written s64.tsv
```

The tag arithmetic was checked directly against real literals in the image rather than only through
the script. For each literal, the byte immediately before it must equal `0x80|(len<<1)`:

```
$ python -c "... for m in (b'AdmobBanner', b'showSplashAd', b'AdPgl_Splash'): ..."
### app_arm64.so
  AdmobBanner    @0x4932e len=11 expected_tag=0x96
     tag_byte_at_-1=0x96  matches=True
  showSplashAd   @0x39deb len=12 expected_tag=0x98
     tag_byte_at_-1=0x98  matches=True
  AdPgl_Splash   @0x493ee len=12 expected_tag=0x98
     tag_byte_at_-1=0x98  matches=True
```

**observed**: three independent literals of two different lengths, three matching tag bytes. This is
also the assertion a patch script should perform (`dart-aot.md` §10), and it is what rejects a hit
that landed mid-string.

## 4. The armv7 assumption — refuted, and what is actually there

The starting hypothesis (carried over from an external case) was that the 32-bit snapshot stores a
string as `[tag 0x81][len*2 u32le][UTF-16LE chars]`. Two scanners written against that hypothesis
found nothing, which is itself the evidence:

```
$ python tools/_work/dart/probe3.py app_armv7.so raw        # [8-byte hdr ending 0x81][u32le len][chars]
hits=0  chained_runs=0  entries_in_runs=0

$ python tools/_work/dart/probe3.py app_armv7.so packed     # the arm64 tag scheme
hits=0  chained_runs=0  entries_in_runs=0
```

The same extractor that keeps 4,980 entries on arm64 keeps **zero** on armv7:

```
$ python skills/apk-reverse/scripts/dart_pool_strings.py tools/_work/dart/app_armv7.so s7.tsv --min 6
candidates           : 1355
kept (run >= 3)      : 0  (one-byte 0 / utf16le 0)
```

A zero here is a **format mismatch, not an empty string table**, and that distinction is now stated in
`dart-aot.md` §7: reading it as "the strings were stripped" is exactly the wrong conclusion the same
section warns about for UTF-16.

What the record actually looks like, from bytes around a known literal:

```
$ python -c "... b.find(b'SystemChrome') ..."
0x1ffb3c b'\x00\x00\x00\x008\x06U\x00F\x00\x00\x00\xce-\x8a@SystemChrome.setEnab...'
0x204ce4 b'\x00\x00\x00\x008\x06U\x00H\x00\x00\x00\xa45jVSystemChrome.setSyst...'
0x2185c4 b' ere8\x07U\x00J\x00\x00\x00\x8c]\xb4GSystemChrome.setPref...'
```

Read as `[header u32][length u32le][payload]`: `0x00550638` then `0x00000046` = **70**, which is the
byte length of `SystemChrome.setEnabledSystemUIMode` (36 chars) immediately followed by
`SystemChrome.setSystemUIOverlayStyle` (34 chars) — **70 bytes, UTF-8, not UTF-16**. The second
literal starts at the exact byte where the first ends, and its own length field reads `0x00000048` =
72, matching its own continuation.

**observed**: `length == payload byte count`, payload is UTF-8, and in-place equal-length replacement
therefore keeps the record valid without recomputing anything. **refuted**: the `len*2` / UTF-16 form.

The header word is a tags value with full 4-byte alignment, not a constant to hard-code:

```
$ python -c "... alignment histogram over the image ..."
alignment mod 4: {0: 13397}
```

```
$ python tools/_work/dart/perf.py app_armv7.so
scanned 17629776 B in 0.94s using 4-byte stride + int.from_bytes
aligned-header string records: 582
stride-1 micro scan over 17629776 B took 2.80s (found 2762)
```

The literal search plus a backwards length assertion is the tool-independent method, and it costs
under a second over a 17.6 MB image — so validating every candidate is affordable and the armv7
limitation does not justify a hand-built table parser. **unverified**: whether a *different* armv7
snapshot uses a different header word; the reference tells the reader to read it from the file.

## 5. The engine version banner — a version-shaped lie

```
$ python -c "... rfind NUL before the ' on \"android_arm64\"' suffix ..."
end-of-version offset 0x110821
version string start 0x1107f1 => total 66
b'0.0.1                                            on "android_arm64"'
```

The banner exists, is 66 bytes long, and its numeric field is `0.0.1` with a blank build-id field —
no `(stable)`, no `(Mon …)`. A regex that takes `\d+\.\d+\.\d+` out of this returns a value that would
send a reader to build a Dart VM for `0.0.1`.

**observed** (the byte string above), **inferred** (that this is a build-time population failure rather
than a deliberately rewritten banner). The actionable consequence is in `dart-aot.md` §1: assert the
`(stable) (…)` tail before using the number, and fall back to the snapshot hash otherwise. **The
sample's Dart version was not pinned in this pass** — that is an unverified item, not a finding.

## 6. Cross-validation

Every measurement above is a **raw byte search with an independent arithmetic assertion** (find the
literal in the file; check the byte or word immediately before it against the length of what follows).
It does not depend on `dart_pool_strings.py`, and the script's numbers are reported alongside the raw
probe rather than as the source of truth. The two agree on arm64 (4,980 kept entries, tag byte equal to
`0x80|(len<<1)` at every literal tested) and on armv7 (the packed scheme finds nothing, the byte layer
shows why).

**Not obtained**: a second, independently implemented Dart snapshot parser. `blutter` was not built in
this pass, so the reference's `pp.txt`-side claims were not re-derived here, and the armv7 conclusion
rests on the byte layout rather than on a tool's agreement. That is the boundary of this evidence.

## 7. What this pass changed in the repository

- `skills/apk-reverse/references/dart-aot.md` — §7 gained the armv7 record format and the
  "the armv7 zero is a format mismatch" warning; §1 gained the banner-shape assertion; §10 gained the
  data-key-versus-API-path rule with its measured failure mode, and the longest-first / assert-the-prefix
  rule. No new file, no new index row: the finding belongs in the file that already owns this layer.
- The equal-length-replacement failure (a 404 whose body is not JSON, `jsonDecode` throwing, the app
  frozen on the launch logo) is documented as the concrete instance of the top-level constraint
  "do not make an API fail to suppress a UI element".

## 8. Not done, and known to be outstanding

1. **No end-to-end device run.** The string-table patch was not repacked, signed and installed in this
   pass, so "an equal-length key replacement suppresses the feature while the app still starts" is
   `unverified` end-to-end even though the record layout that makes it legal is `observed`.
2. **No `blutter` build**, so no `pp.txt` comparison and no confirmation of the arm64 pool space from a
   second implementation (§6).
3. **The sample's Dart version is unpinned** (§5); a structural probe or a snapshot hash is the next
   experiment, not a guessed number.
4. **The armv7 header word is not characterised.** It is read from the file and used as a validator;
   which component assigns it was not determined.
