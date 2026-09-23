#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extract strings, URLs and vendor markers from dex files without a decompiler.

Fast recon: dex strings are stored as plain MUTF-8, so ASCII substrings can be found
by scanning the raw bytes. This answers most classification questions in seconds --
which dex holds the app's code, which ad SDKs ship with it, what endpoints it calls.

Usage
-----
  # all URLs across a directory of dex files
  python dex_strings.py <dex_dir> --urls

  # find which dex files contain a marker (ASCII substring)
  python dex_strings.py <dex_dir> --find 'openadsdk|com.qq.e|anythink' --per-file

  # dump a class/package inventory per dex (type descriptors)
  python dex_strings.py <dex_dir> --classes 'Lcom/example/app/'

  # raw string-table dump, length-filtered
  python dex_strings.py <dex_dir> --strings --min 8 --max 60

  # compare two dex files' string tables (what changed after a patch)
  python dex_strings.py --diff a.dex b.dex

Notes
-----
* A marker in the string table means the class/URL is *present*, not that the app
  *uses* that feature. Confirm with runtime behavior before acting.
* `--urls` output is the fastest way to see an app's whole API surface and its
  third-party endpoints at once.
* A dex may be a multi-dex set: run this per directory, not per file, to see which
  split holds a given marker.
"""
import argparse
import glob
import os
import re
import struct
import sys

URL_RE = re.compile(rb'https?://[A-Za-z0-9\.\-_:/%\.\?=&~#]{4,200}')


def uleb128(data, off):
    r = 0
    s = 0
    while True:
        b = data[off]
        off += 1
        r |= (b & 0x7F) << s
        if not (b & 0x80):
            break
        s += 7
    return r, off


def dex_strings(path):
    """Yield the dex string table in table order, as bytes."""
    data = open(path, 'rb').read()
    if data[:4] != b'dex\n':
        return
    n = struct.unpack('<I', data[0x38:0x3C])[0]
    off = struct.unpack('<I', data[0x3C:0x40])[0]
    for i in range(n):
        sdata = struct.unpack('<I', data[off + i * 4: off + i * 4 + 4])[0]
        ln, p = uleb128(data, sdata)
        yield bytes(data[p:p + ln])


def iter_dex(target):
    if os.path.isdir(target):
        return sorted(glob.glob(os.path.join(target, '*.dex')))
    return [target]


def main():
    ap = argparse.ArgumentParser(
        description='Extract strings / URLs / class descriptors / vendor markers from dex files '
                    'without a decompiler.')
    ap.add_argument('target', nargs='?', default=None,
                    help='a .dex file or a directory containing .dex files (omit when using --diff)')
    ap.add_argument('--urls', action='store_true', help='print only http(s) URLs')
    ap.add_argument('--strings', action='store_true', help='dump raw string table entries')
    ap.add_argument('--classes', metavar='PREFIX',
                    help='print only entries starting with this prefix (e.g. Lcom/example/app/)')
    ap.add_argument('--find', metavar='REGEX',
                    help='only keep entries matching this regex (applied to the decoded text)')
    ap.add_argument('--per-file', action='store_true',
                    help='with --find: report one line per dex with a hit count, instead of each string')
    ap.add_argument('--diff', nargs=2, metavar=('A', 'B'),
                    help='compare two dex files string tables')
    ap.add_argument('--min', type=int, default=6, help='minimum string length (default 6)')
    ap.add_argument('--max', type=int, default=200, help='maximum string length (default 200)')
    ap.add_argument('--max-print', type=int, default=5000,
                    help='stop printing after this many lines (default 5000; use 0 for unlimited)')
    a = ap.parse_args()

    # --diff mode needs no target
    if a.diff:
        A = set(dex_strings(a.diff[0]))
        B = set(dex_strings(a.diff[1]))
        only_a = sorted(x for x in A - B if a.min <= len(x) <= a.max)
        only_b = sorted(x for x in B - A if a.min <= len(x) <= a.max)
        print('A strings=%d  B strings=%d' % (len(A), len(B)))
        print('only in A: %d' % len(only_a))
        for x in only_a[:40]:
            print('   -', x.decode('utf-8', 'replace'))
        print('only in B: %d' % len(only_b))
        for x in only_b[:40]:
            print('   +', x.decode('utf-8', 'replace'))
        return 0

    if not a.target:
        ap.error('target is required unless --diff is used')

    # Two patterns: the per-file mode scans raw bytes (fast), the per-string mode
    # matches decoded text. Keeping both avoids the bytes/str mismatch that silently
    # breaks one of the two paths.
    pat_text = re.compile(a.find) if a.find else None
    pat_bytes = re.compile(a.find.encode('utf-8')) if a.find else None
    files = iter_dex(a.target)

    if a.find and a.per_file:
        for fp in files:
            data = open(fp, 'rb').read()
            hits = len(pat_bytes.findall(data))
            if hits:
                print('%-22s hits=%d' % (os.path.basename(fp), hits))
        return 0

    printed = 0
    seen = set()
    for fp in files:
        for raw in dex_strings(fp):
            s = raw.decode('utf-8', 'replace')
            if not (a.min <= len(s) <= a.max):
                continue
            if pat_text and not pat_text.search(s):
                continue
            if a.classes and not s.startswith(a.classes):
                continue
            if a.urls and not raw.startswith((b'http://', b'https://')):
                continue
            if s in seen:
                continue
            seen.add(s)
            if a.max_print and printed >= a.max_print:
                print('[note] output cap reached (%d). Use --max-print 0 to lift.' % a.max_print)
                return 0
            if a.classes:
                print('%-18s %s' % (os.path.basename(fp), s))
            else:
                print(s)
            printed += 1

    if a.urls and not seen:
        # fall back to a raw byte scan: covers URLs stored outside the string table
        print('[note] no URLs in string tables; raw scan:')
        for fp in files:
            for m in sorted(set(URL_RE.findall(open(fp, 'rb').read()))):
                print(os.path.basename(fp), m.decode('utf-8', 'replace'))
    return 0


if __name__ == '__main__':
    sys.exit(main())
