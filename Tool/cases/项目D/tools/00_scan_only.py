"""只读 AOB 扫描：验证特征码表对目标 项目D.exe 的命中情况"""
import json
import sys
import os
# --- 路径解析（相对本脚本，便于案例库移植）---
_HERE   = os.path.dirname(os.path.abspath(__file__))
BASE    = os.path.dirname(_HERE)                  # 案例根目录
SAMPLES = os.path.join(BASE, "samples")

TARGET = sys.argv[1] if len(sys.argv) > 1 else r"C:\Program Files (x86)\项目D\项目D.exe"
TABLE = os.path.join(SAMPLES, "final_table.json")

data = open(TARGET, 'rb').read()
table = json.load(open(TABLE, encoding='utf-8'))

print("目标: %s" % TARGET)
print("体积: %d 字节" % len(data))
print("=" * 104)
print("%-38s %-10s %-8s %-8s %s" % ("补丁点", "命中偏移", "状态", "唯一", "位点字节校验"))
print("=" * 104)

ok_all = True
for t in table:
    sig = bytes.fromhex(t["sig"])
    sigp = bytes.fromhex(t["sigPatched"])
    exp = bytes.fromhex(t["expected"])

    op = data.find(sigp)
    oo = data.find(sig)

    if op >= 0 and oo < 0:
        site = op + t["patchOffsetInSig"]
        print("%-38s 0x%-8X %-8s %-8s %s" % (t["name"], site, "已补丁", "-", "-"))
        continue

    if oo < 0:
        print("%-38s %-10s %-8s %-8s %s" % (t["name"], "-", "缺失", "-", "✗ 未命中"))
        ok_all = False
        continue

    uniq = data.find(sig, oo + 1) < 0
    site = oo + t["patchOffsetInSig"]
    got = data[site:site + len(exp)]
    good = (got == exp)
    if not uniq or not good:
        ok_all = False
    print("%-38s 0x%-8X %-8s %-8s %s"
          % (t["name"], site, "原始态", "是" if uniq else "否 ✗",
             ("%s == %s ✓" % (got.hex().upper(), t["expected"])) if good else
             ("%s != %s ✗" % (got.hex().upper(), t["expected"]))))

print("=" * 104)
print()
print("结论: %s" % ("✓ 全部命中，可安全打补丁" if ok_all else "✗ 存在未命中/不唯一，禁止打补丁"))
