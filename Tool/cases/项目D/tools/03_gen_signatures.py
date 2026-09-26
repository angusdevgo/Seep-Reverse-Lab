"""AOB 特征码生成器 (N 版本共同稳定区)
- 特征码只保留在所有已采集版本中「完全一致」的字节 → 天然排除重定位指针
- 双态唯一性校验：原始态 / 已补丁态 在全部版本中均须唯一命中
"""
import json
import os
# --- 路径解析（相对本脚本，便于案例库移植）---
_HERE   = os.path.dirname(os.path.abspath(__file__))
BASE    = os.path.dirname(_HERE)                  # 案例根目录
SAMPLES = os.path.join(BASE, "samples")

SAMPLES = os.path.join(BASE, "samples")

# 参与生成的全部版本样本
VERSIONS = [
    ("b10",   os.path.join(SAMPLES, "项目D_643b10_original.exe")),
    ("b11.2", os.path.join(SAMPLES, "项目D_643b11_original.exe")),
    ("b11.3", os.path.join(SAMPLES, "项目D_643b11b3_original.exe")),
]

# (名称, 各版本位点偏移..., 期望字节, 补丁字节)
POINTS = [
    ("授权分支检测 (test eax->xor eax)",          [0x2D7BD, 0x2D45D, 0x2D3FD], "85", "33"),
    ("试用期最大值 (->mov eax,7FFFFFFF+nop)",     [0x4C100, 0x4BF60, 0x4BF10], "83E00F83C00F", "B8FFFFFF7F90"),
    ("假序列号弹窗 A (jz->jmp)",                  [0x53F78, 0x53DF8, 0x53DA8], "74", "EB"),
    ("守护线程 A",                                [0x74920, 0x745A0, 0x74550], "6A", "C3"),
    ("守护线程 B",                                [0x753C0, 0x75040, 0x74FF0], "6A", "C3"),
    ("守护线程 C",                                [0x7BC00, 0x7B890, 0x7B830], "6A", "C3"),
    ("守护线程 D",                                [0x7CA50, 0x7C6E0, 0x7C680], "6A", "C3"),
    ("看门狗关联函数",                             [0x834E0, 0x83170, 0x83120], "6A", "C3"),
    ("守护线程 E (push ebp->ret)",                [0x842E0, 0x83F70, 0x83F20], "55", "C3"),
    ("守护线程 F",                                [0x131C60, 0x131A60, 0x131A30], "6A", "C3"),
    ("过期强退逻辑 (0F85->90E9)",                 [0x91ABC, 0x9173C, 0x9170C], "0F85", "90E9"),
    ("联网验证标志位",                             [0x99A6D, 0x996ED, 0x996BD], "01", "00"),
    ("假序列号弹窗 B (jz->jmp)",                  [0xF710E, 0xF6EDE, 0xF6E8E], "74", "EB"),
    ("试用状态标志 + 天数限制常量",                  [0x378CDC, 0x378EDC, 0x378EDC], "010000001E000000", "00000000FFFFFF7F"),
]

MAXLEN = 96
data = [open(p, 'rb').read() for _, p in VERSIONS]


def apply_patches(base, idx):
    buf = bytearray(base)
    for name, offs, eh, ph in POINTS:
        o = offs[idx]
        buf[o:o + len(bytes.fromhex(ph))] = bytes.fromhex(ph)
    return bytes(buf)


patched = [apply_patches(d, i) for i, d in enumerate(data)]


def grow(offs, plen):
    """向左右扩展，要求所有版本对应位置字节一致"""
    left = 0
    while left < MAXLEN:
        vals = []
        for i, d in enumerate(data):
            a = offs[i] - left - 1
            if a < 0:
                vals = None; break
            vals.append(d[a])
        if not vals or len(set(vals)) != 1:
            break
        left += 1
    right = 0
    while right < MAXLEN:
        vals = []
        for i, d in enumerate(data):
            a = offs[i] + plen + right
            if a >= len(d):
                vals = None; break
            vals.append(d[a])
        if not vals or len(set(vals)) != 1:
            break
        right += 1
    return left, right


def occ(hay, needle):
    n = 0; p = 0
    while True:
        i = hay.find(needle, p)
        if i < 0:
            break
        n += 1
        p = i + 1
        if n > 20:
            break
    return n


print("=" * 126)
print("%-38s %-6s %-4s %-4s  %s" % ("补丁点", "长度", "左", "右", "双态唯一性 " + " ".join("%-7s" % v[0] for v in VERSIONS)))
print("=" * 126)

table = []
allok = True
for name, offs, eh, ph in POINTS:
    exp = bytes.fromhex(eh); pat = bytes.fromhex(ph); plen = len(exp)
    left, right = grow(offs, plen)
    # 以第一个版本的字节为准构造特征码
    sig = data[0][offs[0] - left: offs[0] + plen + right]
    sigp = sig[:left] + pat + sig[left + plen:]

    counts = []
    ok = True
    for i, d in enumerate(data):
        c1 = occ(d, sig)
        c2 = occ(patched[i], sigp)
        counts.append("%d/%d" % (c1, c2))
        if c1 != 1 or c2 != 1:
            ok = False
    # 校验各版本位点字节
    for i, d in enumerate(data):
        if d[offs[i]:offs[i] + plen] != exp:
            ok = False
    if not ok:
        allok = False

    print("%-38s %-6d %-4d %-4d  %s  %s"
          % (name, len(sig), left, right, '  '.join("%-7s" % c for c in counts), "OK" if ok else "!! 失败"))
    table.append({"name": name, "sig": sig.hex().upper(), "sigPatched": sigp.hex().upper(),
                  "patchOffsetInSig": left, "expected": eh, "patch": ph,
                  "offsets": {v[0]: offs[i] for i, v in enumerate(VERSIONS)}, "unique": ok})

print("=" * 126)
print("全部通过: %s   (%d/%d)" % (allok, sum(1 for t in table if t["unique"]), len(table)))
print("特征码总字节 %d，平均 %.1f 字节/位点"
      % (sum(len(t["sig"]) // 2 for t in table), sum(len(t["sig"]) // 2 for t in table) / len(table)))
json.dump(table, open(os.path.join(SAMPLES, "final_table.json"), 'w', encoding='utf-8'),
          ensure_ascii=False, indent=2)
