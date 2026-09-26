"""基于 numpy 滑动汉明距离的精确位点定位"""
import numpy as np
import json
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

WIN = 64          # 签名窗口
CHUNK = 1_000_000


def best_match(win_bytes):
    """返回 (最佳位置, 最小汉明距离, 距离<=6 的全部位置列表)"""
    w = np.frombuffer(win_bytes, dtype=np.uint8)
    n = len(b11) - WIN + 1
    best_pos, best_d = -1, 10 ** 9
    near = []
    for s in range(0, n, CHUNK):
        e = min(s + CHUNK, n)
        # 分块构建滑窗
        idx = np.arange(s, e)[:, None] + np.arange(WIN)[None, :]
        dist = (A11[idx] != w[None, :]).sum(axis=1)
        mn = int(dist.min())
        if mn < best_d:
            best_d = mn
            best_pos = s + int(dist.argmin())
        if mn <= 6:
            for p in (s + np.nonzero(dist <= 6)[0]).tolist():
                near.append((p, int(dist[p - s])))
    return best_pos, best_d, near


POINTS = [
    ("授权分支检测", 0x2D7BD, "85", "33"),
    ("试用期最大值", 0x4C100, "83E00F83C00F", "B8FFFFFF7F90"),
    ("假序列号弹窗A", 0x53F78, "74", "EB"),
    ("守护线程A", 0x74920, "6A", "C3"),
    ("守护线程B", 0x753C0, "6A", "C3"),
    ("守护线程C", 0x7BC00, "6A", "C3"),
    ("守护线程D", 0x7CA50, "6A", "C3"),
    ("看门狗关联", 0x834E0, "6A", "C3"),
    ("守护线程E", 0x842E0, "55", "C3"),
    ("守护线程F", 0x131C60, "6A", "C3"),
    ("过期强退", 0x91ABC, "0F85", "90E9"),
    ("联网验证标志", 0x99A6D, "01", "00"),
    ("假序列号弹窗B", 0xF710E, "74", "EB"),
    ("试用状态标志", 0x378CDC, "01", "00"),
    ("试用天数常量", 0x378CE0, "1E000000", "FFFFFF7F"),
]

HALF = WIN // 2
print("=" * 116)
print("%-14s %-9s %-9s %-8s %-6s %-8s %s" % ("补丁点", "b10", "b11(最佳)", "位移", "汉明", "该点字节", "判定"))
print("=" * 116)

out = []
for name, o10, exp_hex, pat_hex in POINTS:
    exp = bytes.fromhex(exp_hex)
    lo = max(0, o10 - HALF)
    win = b10[lo:lo + WIN]
    pos, dist, near = best_match(win)
    cand = pos + (o10 - lo) if pos >= 0 else -1
    got = b11[cand:cand + len(exp)] if cand >= 0 else b''
    ok = (got == exp)
    delta = cand - o10 if cand >= 0 else 0
    print("%-14s 0x%-7X 0x%-7X %+7d  %-6d %-8s %s"
          % (name, o10, cand, delta, dist, got.hex().upper(),
             ("✓ 匹配" if ok else "✗ 期望 %s" % exp_hex)))
    if near:
        print("        近邻(<=6): %s" % ', '.join("0x%X(d=%d)" % (p, d) for p, d in near[:6]))
    out.append({"name": name, "b10": o10, "b11": cand, "delta": delta,
                "hamming": dist, "exp": exp_hex, "pat": pat_hex, "ok": ok})

print("=" * 116)
print()
print("字节完全匹配: %d / %d" % (sum(1 for x in out if x["ok"]), len(POINTS)))
json.dump(out, open(os.path.join(SAMPLES, "hamming_result.json"), 'w',
                    encoding='utf-8'), ensure_ascii=False, indent=2)
