#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Find every reference to a method/field/class, so you can judge blast radius
BEFORE patching it.

This is the check that prevents the classic mistake: patching something that looked
ad-specific but is actually a general utility with dozens of callers.

Usage
-----
  # a smali tree, a single .dex, a directory holding either, or an .apk
  python find_refs.py <smali_tree|dex|dir|apk> 'Lcom/pkg/Helper;->showAd(Landroid/app/Activity;)V'

  # a whole class (all of its members)
  python find_refs.py <smali_tree|dex|dir|apk> 'Lcom/pkg/Helper;'

  # a field
  python find_refs.py <smali_tree|dex|dir|apk> 'Lcom/pkg/Helper;->count:I'

  # just the counts, no listing
  python find_refs.py <smali_tree|dex|dir|apk> 'Lcom/pkg/Helper;->showAd' --count-only

Reading the result
------------------
  few callers, all inside one feature area   -> safe to patch
  many callers, or callers in unrelated pkgs -> general utility. DO NOT patch it.
                                                Go one level up and patch the
                                                specific caller instead.

The first line is part of the answer, not decoration. `[scanned] 0 file(s)` means
the input was never read -- an unsupported path, a typo, a directory with nothing
this script can open -- and it is a different result from "read N files and found
nothing". The two used to print identically, which put a false zero on exactly the
decision this script exists to protect. Input that cannot be read now exits 2 and
says why.

Input forms, precisely:
  .smali file     text scan (no decoder needed)
  .dex file       decoded with dexutil (no baksmali/jadx required)
  directory       every .smali and .dex found under it, recursively
  .apk/.zip/...   every classes*.dex inside the archive
  anything else   refused with an error, rather than reported as "no references"

Also inspect the signature. If it mentions Modifier / ContentScale / Shape / View /
ColorScheme or a content-generic model type, it is shared UI, not your target.
"""
import argparse
import os
import re
import sys
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from dexutil import (  # noqa: E402
    IFIELD_OPS, INVOKE_OPS, PFIELD_OPS, SFIELD_OPS, insn_units, load_dex, u16,
)

TEXT_EXT = ('.smali',)
DEX_EXT = ('.dex',)
ARCHIVE_EXT = ('.apk', '.zip', '.jar', '.xapk', '.apks', '.apkm')
REF_RE_TMPL = r'invoke[^\n]*%s|sget[^\n]*%s|sput[^\n]*%s|new-instance[^\n]*%s|check-cast[^\n]*%s'

FIELD_OPS = tuple(IFIELD_OPS) + tuple(PFIELD_OPS) + tuple(SFIELD_OPS)
# new-instance (0x22) and check-cast (0x1F) both carry a type index at byte 2,
# which is where the 21c format puts it.
TYPE_OPS = (0x1F, 0x22)
# classes.dex, classes2.dex, ... in an archive.
ARCHIVE_DEX_RE = re.compile(r'(?:^|/)classes\d*\.dex$')

EXIT_FOUND = 0
EXIT_NO_MATCH = 1
EXIT_BAD_INPUT = 2


def gather(root):
    """Return (smali_paths, dex_paths, archive_paths).

    Raises ValueError for input this script cannot read, so that "nothing was
    scanned" can never be mistaken for "nothing references it".
    """
    if os.path.isdir(root):
        smali, dexs = [], []
        for dp, _dirs, files in os.walk(root):
            for fn in sorted(files):
                path = os.path.join(dp, fn)
                if fn.endswith(TEXT_EXT):
                    smali.append(path)
                elif fn.endswith(DEX_EXT):
                    dexs.append(path)
        if not smali and not dexs:
            raise ValueError(
                'no .smali and no .dex files under %s.\n'
                '        A directory of .apk archives is not scanned; pass the '
                '.apk itself, or disassemble first (%s).'
                % (root, 'smtool.py'))
        return smali, dexs, []

    if not os.path.exists(root):
        raise ValueError('no such file or directory: %s' % root)

    low = root.lower()
    if low.endswith(TEXT_EXT):
        return [root], [], []
    if low.endswith(DEX_EXT):
        return [], [root], []
    if low.endswith(ARCHIVE_EXT):
        return [], [], [root]
    raise ValueError(
        '%s is not a .smali file, a .dex, a directory, or an archive.\n'
        '        Accepted: .smali, .dex, a directory holding either, '
        '%s' % (root, '/'.join(ARCHIVE_EXT)))


def method_owner(text, idx):
    """Map a character offset to the enclosing .method declaration."""
    head = text.rfind('.method ', 0, idx)
    if head < 0:
        return '?'
    end = text.find('\n', head)
    return text[head:end].strip()


def scan_smali(path, pat):
    """Return [(offset, owner, matched_text)] for one smali file."""
    try:
        with open(path, encoding='utf-8', errors='replace') as fh:
            text = fh.read()
    except OSError:
        return []
    return [(m.start(), method_owner(text, m.start()), m.group(0).strip())
            for m in pat.finditer(text)]


def walk_insns(dex, code_off):
    """Yield (offset, opcode) for one method body.

    Deliberately not dex.decode(): this walks every instruction of every method
    in the dex, and the per-instruction dict decode() builds is not needed to
    read an operand index out of the raw bytes.
    """
    info = dex.code_info(code_off)
    pos = info['insns_off']
    end = pos + info['insns_size'] * 2
    while pos < end:
        op = dex.d[pos]
        units = insn_units(op, dex.d, pos, end)
        if units < 1 or pos + units * 2 > end:
            return
        yield pos, op
        pos += units * 2


def scan_dex(dex, needle):
    """Return [(insn_off, owner, rendered)] for references inside one dex.

    The rendered form is the same string the smali side matches textually
    (`Lcom/pkg/Helper;->showAd(Landroid/app/Activity;)V`), so both input forms
    answer the same question the same way.
    """
    out = []
    for i in range(dex.header['class_defs_size']):
        cd_off = dex.header['class_defs_off'] + i * 32
        for _section, _midx, cls, name, desc, code_off in dex.methods_at(cd_off):
            if not code_off:
                continue
            owner = '%s->%s%s' % (cls, name, desc)
            for pos, op in walk_insns(dex, code_off):
                if op in INVOKE_OPS:
                    cls2, nm, ds = dex.method(u16(dex.d, pos + 2))
                    rendered = '%s->%s%s' % (cls2, nm, ds)
                elif op in FIELD_OPS:
                    cls2, nm, ty = dex.field(u16(dex.d, pos + 2))
                    rendered = '%s->%s:%s' % (cls2, nm, ty)
                elif op in TYPE_OPS:
                    rendered = dex.type_(u16(dex.d, pos + 2))
                else:
                    continue
                if needle in rendered:
                    out.append((pos, owner, rendered))
    return out


def dex_sources(path):
    """Return [(label, Dex)] for a .dex file or every classes*.dex in an archive."""
    if path.lower().endswith(DEX_EXT):
        dex, _entry = load_dex(path)
        return [(path, dex)]
    with zipfile.ZipFile(path) as z:
        names = sorted(n for n in z.namelist() if ARCHIVE_DEX_RE.search(n))
    if not names:
        raise ValueError('no classes*.dex inside %s' % path)
    out = []
    for name in names:
        dex, _entry = load_dex(path, entry=name)
        out.append(('%s!%s' % (path, name), dex))
    return out


def main():
    ap = argparse.ArgumentParser(
        description='Count and list references to a method/field/class, in a smali '
                    'tree, a .dex, a directory of either, or an .apk.')
    ap.add_argument('root', help='.smali file, .dex file, directory, or archive')
    ap.add_argument('needle', help='e.g. Lcom/pkg/Helper;->showAd(...)V, '
                                   'Lcom/pkg/Helper;, or Lcom/pkg/Helper;->count:I')
    ap.add_argument('--count-only', action='store_true')
    ap.add_argument('--max-print', type=int, default=60)
    a = ap.parse_args()

    esc = re.escape(a.needle)
    # match the needle plus one more char so we do not match a longer prefix
    pat = re.compile(REF_RE_TMPL % (esc, esc, esc, esc, esc))

    try:
        smali_paths, dex_paths, archives = gather(a.root)
    except ValueError as exc:
        print('[error] %s' % exc)
        return EXIT_BAD_INPUT

    per_file = []          # (count, label, hits)
    scanned = 0
    unreadable = []

    for path in smali_paths:
        hits = scan_smali(path, pat)
        scanned += 1
        if hits:
            per_file.append((len(hits), path, hits))

    for path in dex_paths + archives:
        try:
            sources = dex_sources(path)
        except (ValueError, OSError, zipfile.BadZipFile) as exc:
            unreadable.append('%s (%s)' % (path, exc))
            continue
        for label, dex in sources:
            problems = dex.check()
            if problems:
                unreadable.append('%s (%s)' % (label, problems[0]))
                continue
            hits = scan_dex(dex, a.needle)
            scanned += 1
            if hits:
                per_file.append((len(hits), label, hits))

    if scanned == 0:
        print('[error] nothing readable was scanned under %s' % a.root)
        for u in unreadable:
            print('  unreadable: %s' % u)
        print('        Input was refused rather than reported as zero references, '
              'because the two are not the same answer.')
        return EXIT_BAD_INPUT

    total = sum(c for c, _l, _h in per_file)
    per_file.sort(key=lambda row: row[0], reverse=True)
    print('[scanned] %d file(s) (%d smali, %d dex)'
          % (scanned, len(smali_paths), scanned - len(smali_paths)))
    print('[total refs] %d across %d files' % (total, len(per_file)))
    for u in unreadable:
        print('[unreadable] %s' % u)
    print()

    printed = 0
    for cnt, label, hits in per_file:
        print('%-70s %d' % (label, cnt))
        if a.count_only:
            continue
        for off, owner, rendered in hits:
            if printed >= a.max_print:
                print('  ... (truncated)')
                return EXIT_FOUND
            print('    in %s' % owner)
            print('      %s' % rendered)
            printed += 1

    if total == 0:
        print('[note] scanned %d file(s) and found no reference to %r. Check the '
              'descriptor prefix "L...;", the exact obfuscated name, and whether the '
              'behaviour lives in another dex or in native code.'
              % (scanned, a.needle))
        return EXIT_NO_MATCH
    return EXIT_FOUND


if __name__ == '__main__':
    sys.exit(main())
