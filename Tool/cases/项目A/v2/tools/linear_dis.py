#!/usr/bin/env python
"""Delphi x64 线性反汇编辅助 (capstone) — 用于在没有 IDA 函数库的情况下阅读指定 RVA 的代码。

用法:
  python linear_dis.py <pe> <rva_start> <length> [--back N]
      --back N: 从 rva_start 往前最多 N 字节寻找函数序言作为起点
"""
import sys, struct
import capstone

SECTIONS = None


def load(path):
    import pefile
    pe = pefile.PE(path, fast_load=True)
    secs = []
    for s in pe.sections:
        secs.append((s.Name.decode().rstrip('\x00'), s.VirtualAddress, s.Misc_VirtualSize,
                     s.PointerToRawData, s.SizeOfRawData))
    base = pe.OPTIONAL_HEADER.ImageBase
    data = open(path, 'rb').read()
    return data, secs, base


def rva2off(secs, rva):
    for nm, va, vsz, raw, rawsz in secs:
        if va <= rva < va + max(vsz, rawsz):
            return raw + (rva - va)
    return None


PROLOGUES = [
    bytes.fromhex('48894c2408'),      # mov [rsp+8], rcx
    bytes.fromhex('4c89442418'),      # mov [rsp+18h], r8
    bytes.fromhex('4c894c2420'),      # mov [rsp+20h], r9
    bytes.fromhex('4883ec28'),        # sub rsp, 28h
    bytes.fromhex('4881ec'),          # sub rsp, imm32
    bytes.fromhex('55488bec'),        # push rbp; mov rbp, rsp
    bytes.fromhex('535657'),          # push rbx/rsi/rdi
    bytes.fromhex('40535657'),
]


def find_start(data, secs, rva, back=0x2000):
    off = rva2off(secs, rva)
    lo = max(0, off - back)
    best = None
    for i in range(off, lo, -1):
        for p in PROLOGUES:
            if data[i:i + len(p)] == p:
                # 前一条指令应当是 ret/int3/jmp 结尾 或 空白
                prev = data[i - 1]
                if prev in (0xC3, 0xCC, 0xC2, 0x90, 0xCB) or data[i - 3:i] == b'\xc3\xcc\xcc':
                    return rva - (off - i)
                if best is None:
                    best = rva - (off - i)
    return best if best else rva


def main():
    path = sys.argv[1]
    rva = int(sys.argv[2], 0)
    length = int(sys.argv[3], 0)
    back = 0x2000
    if '--back' in sys.argv:
        back = int(sys.argv[sys.argv.index('--back') + 1], 0)
    data, secs, base = load(path)
    start = rva
    if '--exact' not in sys.argv:
        start = find_start(data, secs, rva, back)
    off = rva2off(secs, start)
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    md.detail = False
    print('# function-ish start RVA 0x%x (requested 0x%x), length 0x%x' % (start, rva, length))
    for i in md.disasm(data[off:off + length], base + start):
        mark = '  <<<' if i.address - base == rva else ''
        print('%08x  %-24s %s %s%s' % (i.address - base, i.bytes.hex(), i.mnemonic, i.op_str, mark))


if __name__ == '__main__':
    main()
