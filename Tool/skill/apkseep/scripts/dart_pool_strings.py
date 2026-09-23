#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Recover string literals from a Dart AOT snapshot, and locate them by file offset.

WHY THIS EXISTS
---------------
Strings are the cheapest anchor for locating logic in a stripped AOT snapshot: field
names, endpoint paths and labels survive compilation even when every symbol name is gone.
Two things this gives you that a decompiler's own listing does not:

  * **file offsets**, where the constant physically sits in the binary (what you need to
    patch bytes, as opposed to a pool offset);
  * **identifiers the decompiler's listing omits** -- measured on a real sample, most of
    what this recovers was absent from the pool listing entirely. Treat the two as
    complementary, not competitive.

THE FRAMING
-----------
    [ tag ][ payload ]        tag = 0x80 | (len << 1) | <two-byte flag>

  * tag bit 7 set          -> a string entry
  * (tag >> 1) & 0x3F      -> payload length in characters (this framing tops out at 63)
  * the low bit            -> nominally "payload is UTF-16LE"

ENCODING, AND WHY ONE-BYTE IS THE DEFAULT
-----------------------------------------
The two payload kinds are searched differently, and this is where most people lose time:

  * **one-byte** payloads are ASCII / Latin-1 -> a **UTF-8 byte search finds them**
  * **two-byte** payloads are **UTF-16LE**    -> a UTF-8 search returns *zero hits*

So search ASCII as UTF-8 and CJK/non-Latin as UTF-16LE; forcing one encoding on both is
the classic false negative (`pitfalls.md` P25).

**But automatic two-byte detection does not work reliably.** The low tag bit is not a
dependable discriminator against ordinary data, and UTF-16LE decoding essentially never
fails -- *any* byte pair is a legal code unit -- so decoding success filters nothing. On a
real sample, two-byte output was ~10k entries of near-pure garbage that happened to form
long runs, while one-byte output was almost entirely genuine. Hence:

  * default: one-byte only (reliable; verified against a decompiler listing on a real sample)
  * `--two-byte`: opt in, and **verify every hit yourself**
  * to find a *known* non-Latin literal, use `--find` -- a direct search is far more
    reliable than enumerating candidates

WHY THE RUN LENGTH IS REPORTED
------------------------------
A per-byte scan for tag-like bytes hits constantly inside ordinary data; a multi-MB
snapshot yields hundreds of thousands of candidates. Most real string tables are laid out
consecutively, so a genuine entry usually begins a run of back-to-back entries (each
entry's tag+payload ends exactly where the next begins). `--min-chain` uses that to shed
the scattered tail.

Note what the measurement showed: raising this threshold barely changes one-byte
precision while steadily destroying recall. It is a **noise filter, not a confidence
score** -- do not tune it expecting accuracy to improve.

USAGE
-----
    python dart_pool_strings.py libapp.so strings.tsv
    python dart_pool_strings.py libapp.so strings.tsv --pp pp.txt     # annotate cross-hits
    python dart_pool_strings.py libapp.so strings.tsv --min-chain 2 --two-byte
    python dart_pool_strings.py libapp.so --find /activateVipCode --find vipflag
    python dart_pool_strings.py libapp.so --stats

OUTPUT
------
    offset_hex <TAB> text <TAB> run <TAB> form [<TAB> in_pp]

`in_pp` is present with `--pp`: `1` means the decompiler's own pool listing contains this
exact string. Absence is **not** evidence of a false positive -- the decompiler's listing
is incomplete by design.

NOTES
-----
* `--max` is capped at 63 by the framing; longer literals are serialized differently and
  will not appear here (a few hundred per sample at most).
* Never edit a string without counting its references first: a shared entry changes every
  consumer at once (`references/dart-aot.md` section 10).
"""
import argparse
import collections
import re
import sys

TAG_STR = 0x80
BAD = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')


def decode_payload(raw, two_byte):
    if two_byte:
        if len(raw) % 2:
            return None
        try:
            text = raw.decode('utf-16-le')
        except UnicodeDecodeError:
            return None
    else:
        try:
            text = raw.decode('utf-8')
        except UnicodeDecodeError:
            return None
    if BAD.search(text):
        return None
    return text


def extract(blob, min_len, max_len, want_two_byte):
    """Return {start: (end, text, form)} for every framed candidate of the wanted kind."""
    n = len(blob)
    cands = {}
    for i in range(n - 2):
        tag = blob[i]
        if not (tag & TAG_STR):
            continue
        ln = (tag >> 1) & 0x3F
        if not (min_len <= ln <= max_len):
            continue
        two = tag & 1
        if two and not want_two_byte:
            continue
        end = i + 1 + (ln * 2 if two else ln)
        if end > n:
            continue
        text = decode_payload(blob[i + 1:end], two)
        if text is None or len(text.strip()) < min_len:
            continue
        cands[i] = (end, text, 'utf16le' if two else 'one-byte')
    return cands


def run_lengths(cands):
    """For each candidate, how many back-to-back entries follow it (inclusive)."""
    nxt = {s: cands[s][0] for s in cands}
    lengths = {}
    closed = set()
    for start in sorted(cands):
        if start in closed:
            continue
        seq = []
        cur = start
        guard = 0
        while cur in nxt and cur not in closed:
            seq.append(cur)
            closed.add(cur)
            cur = nxt[cur]
            guard += 1
            if guard > 1_000_000:
                break
        for i, item in enumerate(seq):
            lengths[item] = len(seq) - i
    return lengths


def load_pp(path):
    """Strings present in a decompiler pool listing, for cross-annotation."""
    if not path:
        return set()
    out = set()
    pat = re.compile(r'^\[pp\+0x[0-9a-f]+\] String: (.*)$')
    for line in open(path, encoding='utf-8', errors='replace'):
        m = pat.match(line.strip())
        if not m:
            continue
        s = m.group(1).strip()
        if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
            s = s[1:-1]
        if s:
            out.add(s)
    return out


def histogram(lengths):
    counts = collections.Counter(lengths.values())
    for run in sorted(counts)[:10]:
        print('   run=%-4d %d' % (run, counts[run]))
    tail = sum(v for k, v in counts.items() if k > 10)
    if tail:
        print('   run>%-3d %d' % (10, tail))


def search(blob, needles):
    total = 0
    for needle in needles:
        for label, enc in (('utf-8', needle.encode('utf-8')),
                           ('utf-16le', needle.encode('utf-16-le'))):
            offsets = []
            start = blob.find(enc)
            while start != -1 and len(offsets) < 8:
                offsets.append(start)
                start = blob.find(enc, start + 1)
            if offsets:
                total += len(offsets)
                print('%-26s %-9s file offset %s' % (
                    needle, label, ' '.join(hex(o) for o in offsets)))
    if not total:
        print('no hits in either encoding. Try the shortest distinctive fragment -- text is\n'
              'often assembled from parts, and a literal may only exist as fragments\n'
              '(pitfalls.md P25).')
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('sample', help='libapp.so or any artifact holding the snapshot')
    ap.add_argument('out', nargs='?', help='output tsv')
    ap.add_argument('--min', type=int, default=4, help='minimum payload length (default 4)')
    ap.add_argument('--max', type=int, default=63,
                    help="maximum payload length; 63 is this framing's ceiling (default 63)")
    ap.add_argument('--min-chain', type=int, default=3,
                    help='noise filter: minimum run of consecutive entries (default 3). '
                         'This does not improve accuracy -- see the module docstring.')
    ap.add_argument('--two-byte', action='store_true',
                    help='ALSO emit UTF-16 candidates. Detection is unreliable; verify each.')
    ap.add_argument('--pp', metavar='PP_TXT',
                    help='decompiler pool listing, to mark which strings it also contains')
    ap.add_argument('--stats', action='store_true',
                    help='print the run-length histogram and exit')
    ap.add_argument('--keep-isolated', action='store_true',
                    help='also write entries below --min-chain (noisy; triage only)')
    ap.add_argument('--find', action='append', default=[], metavar='TEXT',
                    help='search a literal in BOTH encodings and print file offsets '
                         '(repeatable; the reliable way to locate a known literal)')
    a = ap.parse_args()

    blob = open(a.sample, 'rb').read()

    if a.find:
        return search(blob, a.find)
    if not a.out and not a.stats:
        raise SystemExit('give an output path, or --find / --stats')

    cands = extract(blob, a.min, a.max, a.two_byte)
    lengths = run_lengths(cands)

    if a.stats:
        print('candidates (two-byte included: %s): %d' % (a.two_byte, len(cands)))
        print('run-length histogram:')
        histogram(lengths)
        return 0

    pp = load_pp(a.pp)
    kept = [s for s in cands if lengths[s] >= a.min_chain]
    rows = kept + (sorted(s for s in cands if lengths[s] < a.min_chain)
                   if a.keep_isolated else [])
    with open(a.out, 'w', encoding='utf-8') as fh:
        fh.write('# offset_hex\ttext\trun\tform%s\n' % ('\tin_pp' if pp else ''))
        for s in sorted(rows):
            _end, text, form = cands[s]
            flat = text.replace('\n', '\\n').replace('\t', ' ')
            extra = ('\t%d' % (1 if text in pp else 0)) if pp else ''
            fh.write('0x%06x\t%s\t%d\t%s%s\n' % (s, flat, lengths[s], form, extra))

    one = sum(1 for s in kept if cands[s][2] == 'one-byte')
    print('candidates           : %d' % len(cands))
    print('kept (run >= %d)      : %d  (one-byte %d / utf16le %d)'
          % (a.min_chain, len(kept), one, len(kept) - one))
    print('below threshold      : %d%s' % (
        len(cands) - len(kept), '' if a.keep_isolated else '  [--keep-isolated to keep them]'))
    if pp:
        hits = sum(1 for s in kept if cands[s][1] in pp)
        print('also in --pp listing : %d / %d  (absence is NOT a false positive: the'
              % (hits, len(kept)))
        print('                       decompiler listing is incomplete by design)')
    if a.two_byte:
        print('WARNING: --two-byte detection is unreliable (see module docstring);')
        print('         verify each UTF-16 hit before trusting it.')
    print('written %s' % a.out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
