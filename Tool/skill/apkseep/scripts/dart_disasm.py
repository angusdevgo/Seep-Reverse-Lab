#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Annotated, windowed disassembly of a Dart AOT snapshot, plus a caller index.

WHY THIS EXISTS
---------------
Two things make Dart AOT code readable at all:

  1. **Pool annotations.** A raw `ldr x2, [x27, #0x9d0]` is meaningless; annotated with the
     pool entry it becomes `"vipflag"` and the surrounding code explains itself. This tool
     resolves those loads and prints what they point at, including how many other sites
     reference the same entry.
  2. **Windowed disassembly.** Decoding an entire multi-MB `.text` in one pass is how a host
     gets pinned at 1-2 GB and the run looks like a hang. Disassemble only the ranges you
     care about -- that is what this tool does, and it is not a limitation but the method.

Booleans are annotated too: Dart materialises `true`/`false` as small offsets from the null
register, so `add x0, x22, #0x20` is marked TRUE and `#0x30` is marked FALSE. Those are the
cheapest patch sites in the whole snapshot.

The caller index answers the other half of every question -- "what calls this function".
It is built from B/BL target arithmetic on the raw words, so it needs no disassembler at all
and finishes in seconds.

USAGE
-----
    # a window around one address (default: 0x180 before, 0x220 after)
    python dart_disasm.py libapp.so --pp pp.txt --refs pp_refs.json 0x26e390

    # an explicit range
    python dart_disasm.py libapp.so --pp pp.txt --refs pp_refs.json --range 0x64f310 0x64f3e0

    # widen / narrow the window
    python dart_disasm.py libapp.so --refs pp_refs.json 0x64f1bc --before 0x80 --after 0x40

    # caller index
    python dart_disasm.py libapp.so --build-index callers.json
    python dart_disasm.py libapp.so --index callers.json 0x26e230 0x64f0f0

INPUTS
------
  * `--pp` is the decompiler's pool listing (blutter `pp.txt`): lines shaped
    `[pp+0x9d0] String: "vipflag"`. Without it, loads are annotated with the raw offset only.
  * `--refs` is the pool-offset -> code-site index built by `dart_pprefs.py`.

Requires `capstone` for disassembly; the caller index works without it.
"""
import argparse
import json
import os
import re
import struct
import sys

POOL_REG = 27
BOOL_TRUE, BOOL_FALSE = 0x20, 0x30
PP_LINE = re.compile(r'^\[(pp\+0x[0-9a-f]+)\](.*)$')


def text_section(path):
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
        name, _t, _f, addr, off, size = sh(i)
        end = strs.find(b'\x00', name)
        if strs[name:end].decode('ascii', 'replace') == '.text':
            return addr, blob[off:off + size]
    raise SystemExit('.text not found')


def load_pp(path):
    pool = {}
    if not path or not os.path.exists(path):
        return pool
    for line in open(path, encoding='utf-8', errors='replace'):
        m = PP_LINE.match(line.rstrip('\n'))
        if m:
            pool[int(m.group(1)[5:], 16)] = m.group(2).strip()[:120]
    return pool


def load_refs(path):
    if not path or not os.path.exists(path):
        return {}
    return {int(k, 16): v for k, v in json.load(open(path, encoding='utf-8')).items()}


def disasm_window(sample, addr, before, after, pp, refs):
    from capstone import Cs, CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN

    text_addr, blob = text_section(sample)
    end_of_text = text_addr + len(blob)
    start = max(text_addr, addr - before)
    stop = min(end_of_text, addr + after)

    md = Cs(CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN)
    md.skipdata = True      # without this, one undecodable byte silently ends the range
    md.detail = True        # without this, operands are unavailable

    print('range 0x%x..0x%x   focus=0x%x' % (start, stop, addr))
    pending = {}
    for ins in md.disasm(blob[start - text_addr:stop - text_addr], start):
        if ins.id == 0:                      # SKIPDATA pseudo-instruction: no operands
            print('%x: %s' % (ins.address, ins.mnemonic))
            continue
        note = ''
        ops = ins.operands
        rn = ins.reg_name
        if (ins.mnemonic == 'add' and len(ops) == 3 and ops[1].type == 1
                and rn(ops[1].reg) == 'x27' and ops[2].type == 2
                and ops[2].shift.value == 12):
            pending[rn(ops[0].reg)] = ops[2].imm << 12
        elif (ins.mnemonic == 'add' and len(ops) == 3 and ops[1].type == 1
                and rn(ops[1].reg) == 'x22' and ops[2].type == 2):
            note = {BOOL_TRUE: '   ; TRUE', BOOL_FALSE: '   ; FALSE'}.get(ops[2].imm, '')
        elif ins.mnemonic in ('ldr', 'ldur') and len(ops) == 2 and ops[1].type == 3:
            base = rn(ops[1].mem.base) if ops[1].mem.base else ''
            off = None
            if base == 'x27':
                off = ops[1].mem.disp
            elif base in pending:
                off = pending.pop(base) + ops[1].mem.disp
            if off is not None:
                text = pp.get(off, '')
                sites = refs.get(off, [])
                note = '   ; pp+0x%x %s  [%d refs]' % (off, text, len(sites))
        mark = '   <<<' if abs(ins.address - addr) < 4 else ''
        print('%x: %-8s %s%s%s' % (ins.address, ins.mnemonic, ins.op_str, note, mark))


def build_index(sample, out):
    """B/BL target -> call sites, decoded arithmetically (no disassembler needed)."""
    text_addr, blob = text_section(sample)
    index = {}
    words = struct.unpack_from('<%dI' % (len(blob) // 4), blob, 0)
    for i, w in enumerate(words):
        if w & 0xFC000000 in (0x14000000, 0x94000000):
            imm = w & 0x03FFFFFF
            if imm & 0x02000000:
                imm -= 0x04000000
            site = text_addr + i * 4
            index.setdefault(site + (imm << 2), []).append(site)
    with open(out, 'w', encoding='utf-8') as fh:
        json.dump({hex(k): v for k, v in index.items()}, fh)
    print('distinct targets : %d' % len(index))
    print('call sites       : %d' % sum(len(v) for v in index.values()))
    print('written %s' % out)


def lookup_index(sample, path, addrs):
    index = {int(k, 16): v for k, v in json.load(open(path, encoding='utf-8')).items()}
    for spec in addrs:
        target = int(spec, 16)
        sites = sorted(index.get(target, []))
        print('0x%x: %d caller(s)' % (target, len(sites)))
        for s in sites[:80]:
            print('   0x%x' % s)
        if len(sites) > 80:
            print('   ... %d more' % (len(sites) - 80))


def main():
    ap = argparse.ArgumentParser(
        description=__doc__.split('\n')[0],
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument('sample', help='libapp.so')
    ap.add_argument('addr', nargs='*', help='hex address(es) to disassemble around')
    ap.add_argument('--pp', metavar='PP_TXT', help="decompiler pool listing (blutter pp.txt)")
    ap.add_argument('--refs', metavar='REFS_JSON', help='index from dart_pprefs.py')
    ap.add_argument('--range', nargs=2, metavar=('START', 'END'))
    ap.add_argument('--before', default='0x180')
    ap.add_argument('--after', default='0x220')
    ap.add_argument('--build-index', metavar='OUT_JSON')
    ap.add_argument('--index', metavar='CALLERS_JSON')
    a = ap.parse_args()

    if a.build_index:
        return build_index(a.sample, a.build_index)
    if a.index:
        if not a.addr:
            raise SystemExit('give at least one hex address to look up')
        return lookup_index(a.sample, a.index, a.addr)

    pp = load_pp(a.pp)
    refs = load_refs(a.refs)
    if a.range:
        start, stop = int(a.range[0], 16), int(a.range[1], 16)
        disasm_window(a.sample, start, 0, stop - start, pp, refs)
        return 0
    if not a.addr:
        raise SystemExit('give an address, --range, --build-index, or --index')
    for spec in a.addr:
        disasm_window(a.sample, int(spec, 16),
                      int(a.before, 0), int(a.after, 0), pp, refs)
    return 0


if __name__ == '__main__':
    sys.exit(main())
