#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dart AOT object-pool reference index: pool offset -> the instructions that load it.

WHY THIS EXISTS
---------------
blutter's `pp.txt` tells you what is *in* the object pool (strings, types, closures,
field metadata) but not which code reads it. "Who uses this string" is the most frequent
question in Dart AOT work, and it needs an index you build once and query constantly.

Building that index with a general-purpose disassembler is the trap here: decoding every
instruction of a multi-MB `.text` with detail enabled and asking for per-instruction
register writes costs minutes of CPU and 1-2 GB of peak memory, and on a 16 GB host it is
indistinguishable from a hang -- no output, no progress, nothing to interrupt. Only three
encodings can reach the pool, so this decodes them from the raw 32-bit words instead:
seconds, and a flat memory profile.

Recognised forms (AArch64, little endian), with x27 = pool base:

    add  xD, x27, #imm12, lsl #12   ->   xD = x27 + (imm12 << 12)
    ldr  XD, [xN, #imm12 * size]    ->   GP register file, size from bits 31-30
    ldr  DD, [xN, #imm12 * size]    ->   SIMD&FP register file (bit 26 set)
    ldur XD/DD, [xN, #simm9]        ->   unscaled variant, both files

Both register files must be covered. Restricting the LDR form to the GP words
(0xF94/0xB94) silently drops `ldr dN, [x27, #imm]` (0xFD400000), which is how every
*double* constant in the pool is read -- an entire class of references disappears from
the index. On a real Dart 3.6.0 libapp.so that was 302 pool offsets and 1,802 sites lost
(measured, see the verification record); one of them had 150 reference sites that would
all have been reported as zero.

A reference is either a direct load whose base is x27, or a load consuming the register an
ADD just derived from x27. The compiler emits that pair back to back, so a small window
keeps it exact without full liveness analysis.

USAGE
-----
    python dart_pprefs.py libapp.so pp_refs.json              # build the index
    python dart_pprefs.py --lookup pp_refs.json 0x1d1a8 0xc9d0
    python dart_pprefs.py libapp.so out.json --window 5       # widen the ADD->LDR window

NOTES
-----
* Offsets are **pool** offsets -- the `pp+0x...` space used by pp.txt -- not file offsets.
  Keep the two spaces apart in your notes; conflating them costs hours.
* One offset commonly has many reference sites. Count them before editing the entry:
  a shared constant will change behaviour everywhere at once (see references/dart-aot.md).
"""
import argparse
import json
import struct
import sys

POOL_REG = 27          # x27: object-pool base in Dart AOT on arm64
DEFAULT_WINDOW = 3     # instructions an ADD-derived address may survive


def text_section(path):
    """Return (vaddr, bytes) of .text, parsing ELF64 section headers directly."""
    blob = open(path, 'rb').read()
    if blob[:4] != b'\x7fELF':
        raise SystemExit('not an ELF file: %s' % path)
    if blob[4] != 2:
        raise SystemExit('not ELF64: %s' % path)
    e_shoff = struct.unpack_from('<Q', blob, 0x28)[0]
    e_shentsize = struct.unpack_from('<H', blob, 0x3A)[0]
    e_shnum = struct.unpack_from('<H', blob, 0x3C)[0]
    e_shstrndx = struct.unpack_from('<H', blob, 0x3E)[0]

    def sh(i):
        return struct.unpack_from('<IIQQQQ', blob, e_shoff + i * e_shentsize)

    _, _, _, _, shstr_off, shstr_size = sh(e_shstrndx)
    strs = blob[shstr_off:shstr_off + shstr_size]
    for i in range(e_shnum):
        name, _typ, _flags, addr, off, size = sh(i)
        end = strs.find(b'\x00', name)
        if strs[name:end].decode('ascii', 'replace') == '.text':
            return addr, blob[off:off + size]
    raise SystemExit('.text not found; pass --text with its virtual address')


def sx(value, bits):
    m = 1 << (bits - 1)
    return (value ^ m) - m


def scan(text_addr, blob, window):
    refs = {}
    pending = {}
    words = struct.unpack_from('<%dI' % (len(blob) // 4), blob, 0)

    for i, w in enumerate(words):
        addr = text_addr + i * 4

        # add xD, x27, #hi, lsl #12
        if w & 0xFFC00000 == 0x91400000 and (w >> 5) & 0x1F == POOL_REG:
            # Keep the shift out of the mask expression: `a & m << n` binds as
            # `a & (m << n)` in Python, which silently produces a wrong base.
            imm = (w >> 10) & 0xFFF
            pending[w & 0x1F] = [imm << 12, i]
            continue

        # LDR (immediate) / LDUR across BOTH register files. Bits 31-30 give the access
        # size and therefore the immediate scale; bit 26 selects the SIMD&FP file.
        # Matching only the GP words (0xF94/0xB94) drops `ldr dN, [x27, #imm]`
        # (0xFD400000) and with it every double constant read from the pool.
        ldr_scale = {0xF9400000: 3, 0xB9400000: 2, 0x79400000: 1, 0x39400000: 0,
                     0xFD400000: 3, 0xBD400000: 2, 0x7D400000: 1, 0x3DC00000: 4,
                     }.get(w & 0xFFC00000)
        ldur = (w & 0xFFE00C00) in (0xF8400000, 0xB8400000, 0x78400000, 0x38400000,
                                    0xFC400000, 0xBC400000, 0x7C400000, 0x3C400000)

        if ldr_scale is not None or ldur:
            rn = (w >> 5) & 0x1F
            rd = w & 0x1F
            if ldr_scale is not None:
                disp = ((w >> 10) & 0xFFF) << ldr_scale
            else:
                disp = sx((w >> 12) & 0x1FF, 9)
            if rn == POOL_REG:
                refs.setdefault(disp, []).append(addr)
            elif rn in pending:
                base, seq = pending.pop(rn)
                if i - seq <= window:
                    refs.setdefault(base + disp, []).append(addr)
            pending.pop(rd, None)   # this load overwrote rd
            continue

        if w & 0xFFC00000 in (0x91000000, 0x91400000):
            pending.pop(w & 0x1F, None)
        for r in [r for r, (_o, s) in pending.items() if i - s > window]:
            del pending[r]

    return refs


def build(so, out, window):
    text_addr, blob = text_section(so)
    refs = scan(text_addr, blob, window)
    with open(out, 'w', encoding='utf-8') as fh:
        json.dump({hex(k): v for k, v in refs.items()}, fh)
    total = sum(len(v) for v in refs.values())
    print('.text vaddr=0x%x  bytes=%d' % (text_addr, len(blob)))
    print('distinct pool offsets : %d' % len(refs))
    print('reference sites       : %d' % total)
    for off in sorted(refs, key=lambda k: -len(refs[k]))[:8]:
        print('   pp+0x%-8x %4d sites' % (off, len(refs[off])))
    print('written %s' % out)


def lookup(path, offsets):
    refs = {int(k, 16): v for k, v in json.load(open(path, encoding='utf-8')).items()}
    for spec in offsets:
        off = int(spec, 16)
        sites = sorted(refs.get(off, []))
        print('pp+0x%x: %d ref site(s)' % (off, len(sites)))
        for s in sites:
            print('   0x%x' % s)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('sample', nargs='?', help='libapp.so (build mode)')
    ap.add_argument('out', nargs='?', help='output json (build mode)')
    ap.add_argument('--lookup', metavar='REFS_JSON', help='query an existing index')
    ap.add_argument('--window', type=int, default=DEFAULT_WINDOW,
                    help='instructions an ADD-derived address may survive (default %d)'
                         % DEFAULT_WINDOW)
    a = ap.parse_args()

    if a.lookup:
        rest = sys.argv[sys.argv.index('--lookup') + 2:]
        if not rest:
            raise SystemExit('give at least one hex pool offset')
        lookup(a.lookup, rest)
        return 0
    if not (a.sample and a.out):
        raise SystemExit('usage: dart_pprefs.py <libapp.so> <out.json>')
    build(a.sample, a.out, a.window)
    return 0


if __name__ == '__main__':
    sys.exit(main())
