"""三代 项目D 版本授权校验链对比分析"""
import struct
import hashlib
import os
from capstone import Cs, CS_ARCH_X86, CS_MODE_32, CS_OPT_SYNTAX_INTEL
# --- 路径解析（相对本脚本，便于案例库移植）---
_HERE   = os.path.dirname(os.path.abspath(__file__))
BASE    = os.path.dirname(_HERE)                  # 案例根目录
SAMPLES = os.path.join(BASE, "samples")

SAMPLES = os.path.join(BASE, "samples")

VERS = [
    ("b10  (6.43.10.2)", os.path.join(SAMPLES, "项目D_643b10_original.exe")),
    ("b11.2(6.43.11.2)", os.path.join(SAMPLES, "项目D_643b11_original.exe")),
    ("b11.3(6.43.11.3)", os.path.join(SAMPLES, "项目D_643b11b3_original.exe")),
]
data = [open(p, 'rb').read() for _, p in VERS]

# (名称, b10, b11.2, b11.3, 期望, 补丁)
POINTS = [
    ("授权分支检测",          0x2D7BD, 0x2D45D, 0x2D3FD, "85", "33"),
    ("试用期最大值",          0x4C100, 0x4BF60, 0x4BF10, "83E00F83C00F", "B8FFFFFF7F90"),
    ("假序列号弹窗 A",        0x53F78, 0x53DF8, 0x53DA8, "74", "EB"),
    ("守护线程 A",            0x74920, 0x745A0, 0x74550, "6A", "C3"),
    ("守护线程 B",            0x753C0, 0x75040, 0x74FF0, "6A", "C3"),
    ("守护线程 C",            0x7BC00, 0x7B890, 0x7B830, "6A", "C3"),
    ("守护线程 D",            0x7CA50, 0x7C6E0, 0x7C680, "6A", "C3"),
    ("看门狗关联函数",         0x834E0, 0x83170, 0x83120, "6A", "C3"),
    ("守护线程 E",            0x842E0, 0x83F70, 0x83F20, "55", "C3"),
    ("守护线程 F",            0x131C60, 0x131A60, 0x131A30, "6A", "C3"),
    ("过期强退逻辑",           0x91ABC, 0x9173C, 0x9170C, "0F85", "90E9"),
    ("联网验证标志位",         0x99A6D, 0x996ED, 0x996BD, "01", "00"),
    ("假序列号弹窗 B",        0xF710E, 0xF6EDE, 0xF6E8E, "74", "EB"),
    ("试用标志+天数常量",      0x378CDC, 0x378EDC, 0x378EDC, "010000001E000000", "00000000FFFFFF7F"),
]


def pe(d):
    lf = struct.unpack_from('<I', d, 0x3C)[0]
    n = struct.unpack_from('<H', d, lf + 6)[0]
    opt = lf + 24
    osz = struct.unpack_from('<H', d, lf + 20)[0]
    magic = struct.unpack_from('<H', d, opt)[0]
    plus = magic == 0x20B
    chk = opt + 0x40
    dd = opt + (0x70 if plus else 0x60)
    sec = dd + 4 * 8
    st = opt + osz
    end = 0
    secs = []
    for i in range(n):
        o = st + i * 40
        nm = d[o:o + 8].rstrip(b'\x00').decode('latin1')
        vs, va, rs, rp = struct.unpack_from('<IIII', d, o + 8)
        secs.append((nm, va, vs, rp, rs))
        end = max(end, rp + rs)
    return dict(chk=chk, sec=sec, end=end, secs=secs, n=n)


def pe_checksum(d, off):
    t = 0; n = len(d)
    for i in range(0, n - 1, 2):
        w = 0 if (off <= i < off + 4) else (d[i] | (d[i + 1] << 8))
        t += w; t = (t & 0xFFFF) + (t >> 16)
    if n & 1: t += d[n - 1]; t = (t & 0xFFFF) + (t >> 16)
    while t > 0xFFFF: t = (t & 0xFFFF) + (t >> 16)
    return (t + n) & 0xFFFFFFFF


print("=" * 108)
print("【一】版本指纹对比")
print("=" * 108)
print("%-18s %-11s %-12s %-14s %-14s" % ("版本", "体积", "PE校验和", "映像末尾", "签名目录"))
for i, (name, p) in enumerate(VERS):
    d = data[i]; P = pe(d)
    srv, ssz = struct.unpack_from('<II', d, P['sec'])
    print("%-18s %-11d 0x%08X     0x%-12X RVA=0x%X Size=%d"
          % (name, len(d), pe_checksum(d, P['chk']), P['end'], srv, ssz))
print()
print("%-18s %-11s %-20s %s" % ("版本", "节区数", "节区 RawPtr", "SHA256"))
for i, (name, p) in enumerate(VERS):
    d = data[i]; P = pe(d)
    rps = ','.join('0x%X' % s[3] for s in P['secs'])
    print("%-18s %-11d %-20s %s" % (name, P['n'], rps, hashlib.sha256(d).hexdigest()[:32]))

print()
print("=" * 108)
print("【二】14 个授权校验位点偏移对比")
print("=" * 108)
print("%-18s %-10s %-10s %-10s %-11s %-11s %s" % ("补丁点", "b10", "b11.2", "b11.3", "b10→11.2", "11.2→11.3", "字节一致"))
print("-" * 108)
for name, o10, o112, o113, eh, ph in POINTS:
    exp = bytes.fromhex(eh)
    ok = (data[0][o10:o10 + len(exp)] == exp and
          data[1][o112:o112 + len(exp)] == exp and
          data[2][o113:o113 + len(exp)] == exp)
    print("%-18s 0x%-8X 0x%-8X 0x%-8X %+10d %+11d  %s"
          % (name, o10, o112, o113, o112 - o10, o113 - o112, "✓" if ok else "✗"))

print()
print("=" * 108)
print("【三】指令级语义对比（每点取位点前 6 字节反汇编上下文）")
print("=" * 108)
md = Cs(CS_ARCH_X86, CS_MODE_32); md.syntax = CS_OPT_SYNTAX_INTEL


def va_of(P, foff):
    for nm, va, vs, rp, rs in P['secs']:
        if rp <= foff < rp + rs:
            return va + (foff - rp)
    return None


def insn_at(d, P, foff):
    """从位点精确解码，取 3 条指令"""
    va = va_of(P, foff)
    if va is None: return "?"
    code = d[foff:foff + 24]
    out = []
    for ins in md.disasm(code, va):
        out.append(ins.mnemonic + (" " + ins.op_str if ins.op_str else ""))
        if len(out) >= 3:
            break
    return ' | '.join(out)


for name, o10, o112, o113, eh, ph in POINTS:
    P0, P1, P2 = pe(data[0]), pe(data[1]), pe(data[2])
    a = insn_at(data[0], P0, o10)
    b = insn_at(data[1], P1, o112)
    c = insn_at(data[2], P2, o113)
    # 归一化：去掉跳转目标与立即数地址，只看助记符
    def norm(s):
        import re
        s = re.sub(r'0x[0-9a-f]+', 'ADDR', s)
        return s
    same = (norm(a) == norm(b) == norm(c))
    print("\n【%s】" % name)
    print("  b10  : %s" % a)
    print("  b11.2: %s" % b)
    print("  b11.3: %s" % c)
    print("  语义一致: %s" % ("✓ 是（仅地址/目标重定位）" if same else "✗ 否"))

print()
print("=" * 108)
print("【四】补丁集演进：Gen2 (旧) vs Gen4 (新)")
print("=" * 108)
print("""
Gen2 旧补丁集（18 点 / 31 字节，硬编码偏移）
  代码段 15 点 / 24 字节:
    + 0x150    PE Checksum 校正      (3 字节，硬编码值 EA 0B 5F)
    + 0x191    Security 目录 RVA     (2 字节)
    + 0x194    Security 目录 Size    (2 字节)
    ... 其余 15 点同上表
  数据段拆分:
    - 0x378CDC  试用状态标志   (1 字节)
    - 0x378CE0  试用天数常量   (4 字节)

Gen4 新补丁集（14 点 / 24 字节 + PE 头动态处理）
  移除 3 个硬编码 PE 头位点 → 改为 PeImageUtil 动态求解
    · CheckSum 偏移 = OptionalHeader + 0x40
    · Security 目录 = DataDirectory[4]
    · 校验和值 = 微软标准算法重算（非硬编码）
  合并 2 个相邻数据段位点 → 单条 8 字节条目
    · 0x378CDC..0x378CE3: 01 00 00 00 1E 00 00 00 -> 00 00 00 00 FF FF FF 7F
""")
