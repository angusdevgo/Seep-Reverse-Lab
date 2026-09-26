"""b11 位点语义验证：反汇编比对 + 扩展窗口一致性"""
import numpy as np
from capstone import Cs, CS_ARCH_X86, CS_MODE_32, CS_OPT_SYNTAX_INTEL
import os
# --- 路径解析（相对本脚本，便于案例库移植）---
_HERE   = os.path.dirname(os.path.abspath(__file__))
BASE    = os.path.dirname(_HERE)                  # 案例根目录
SAMPLES = os.path.join(BASE, "samples")

B10 = r"C:\Program Files (x86)\项目D\项目D.exe.BAK"
B11 = os.path.join(SAMPLES, "项目D_643b11_original.exe")
b10 = open(B10, 'rb').read()
b11 = open(B11, 'rb').read()
A11 = np.frombuffer(b11, dtype=np.uint8)

# 节区表
def sections(d):
    import struct
    lf = struct.unpack_from('<I', d, 0x3C)[0]
    n = struct.unpack_from('<H', d, lf + 6)[0]
    opt = lf + 24; osz = struct.unpack_from('<H', d, lf + 20)[0]
    st = opt + osz
    out = []
    for i in range(n):
        o = st + i * 40
        nm = d[o:o + 8].rstrip(b'\x00').decode('latin1')
        vs, va, rs, rp = struct.unpack_from('<IIII', d, o + 8)
        out.append((nm, va, vs, rp, rs))
    return out

S10 = sections(b10); S11 = sections(b11)

def va_of(secs, foff):
    for nm, va, vs, rp, rs in secs:
        if rp <= foff < rp + rs:
            return va + (foff - rp)
    return None

md = Cs(CS_ARCH_X86, CS_MODE_32)
md.syntax = CS_OPT_SYNTAX_INTEL
md.detail = False

MAPPING = [
    ("授权分支检测", 0x2D7BD, 0x2D45D, "85", "33"),
    ("试用期最大值", 0x4C100, 0x4BF60, "83E00F83C00F", "B8FFFFFF7F90"),
    ("假序列号弹窗A", 0x53F78, 0x53DF8, "74", "EB"),
    ("守护线程A", 0x74920, 0x745A0, "6A", "C3"),
    ("守护线程B", 0x753C0, 0x75040, "6A", "C3"),
    ("守护线程C", 0x7BC00, 0x7B890, "6A", "C3"),
    ("守护线程D", 0x7CA50, 0x7C6E0, "6A", "C3"),
    ("看门狗关联", 0x834E0, 0x83170, "6A", "C3"),
    ("守护线程E", 0x842E0, 0x83F70, "55", "C3"),
    ("守护线程F", 0x131C60, 0x131A60, "6A", "C3"),
    ("过期强退", 0x91ABC, 0x9173C, "0F85", "90E9"),
    ("联网验证标志", 0x99A6D, 0x996ED, "01", "00"),
    ("假序列号弹窗B", 0xF710E, 0xF6EDE, "74", "EB"),
    ("试用状态标志", 0x378CDC, 0x378EDC, "01", "00"),
    ("试用天数常量", 0x378CE0, 0x378EE0, "1E000000", "FFFFFF7F"),
]


def hamming_at(win, pos):
    w = np.frombuffer(win, dtype=np.uint8)
    seg = A11[pos:pos + len(win)]
    return int((seg != w).sum())


def disasm(d, secs, foff, before=12, after=20):
    va = va_of(secs, foff)
    if va is None:
        return "  <非节区内>"
    start_va = va - before
    start_f = foff - before
    code = d[start_f:start_f + before + after]
    lines = []
    for ins in md.disasm(code, start_va):
        mark = " <<<< 补丁点" if ins.address == va else ""
        lines.append("      VA 0x%08X  %-22s %s %s%s"
                     % (ins.address, ins.bytes.hex().upper(), ins.mnemonic, ins.op_str, mark))
    return '\n'.join(lines)


print("=" * 120)
for name, o10, o11, exp_hex, pat_hex in MAPPING:
    exp = bytes.fromhex(exp_hex)
    got = b11[o11:o11 + len(exp)]
    # 扩展窗口一致性：64 / 128 / 256 字节
    res = []
    for w in (64, 128, 256):
        lo = o10 - w // 2
        if lo < 0 or lo + w > len(b10):
            res.append("-"); continue
        win = b10[lo:lo + w]
        pos = o11 - w // 2
        if pos < 0 or pos + w > len(b11):
            res.append("-"); continue
        res.append(str(hamming_at(win, pos)))
    print("【%s】  b10 0x%X -> b11 0x%X   字节 %s (期望 %s) %s"
          % (name, o10, o11, got.hex().upper(), exp_hex, "✓" if got == exp else "✗"))
    print("   扩展窗口汉明距离 (64/128/256 字节): %s" % ' / '.join(res))
    print("   b10 反汇编:")
    print(disasm(b10, S10, o10))
    print("   b11 反汇编:")
    print(disasm(b11, S11, o11))
    print("-" * 120)
