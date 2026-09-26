"""端到端验证：用 AOB 特征码表给 b11 打补丁"""
import json
import struct
import hashlib
import os
# --- 路径解析（相对本脚本，便于案例库移植）---
_HERE   = os.path.dirname(os.path.abspath(__file__))
BASE    = os.path.dirname(_HERE)                  # 案例根目录
SAMPLES = os.path.join(BASE, "samples")

B11 = os.path.join(SAMPLES, "项目D_643b11_original.exe")
TABLE = json.load(open(os.path.join(SAMPLES, "final_table.json"), encoding='utf-8'))

orig = open(B11, 'rb').read()
buf = bytearray(orig)

print("=" * 100)
print("AOB 扫描并打补丁")
print("=" * 100)

results = []
for t in TABLE:
    sig = bytes.fromhex(t["sig"])
    sigp = bytes.fromhex(t["sigPatched"])
    exp = bytes.fromhex(t["expected"])
    pat = bytes.fromhex(t["patch"])
    off_in_sig = t["patchOffsetInSig"]

    # 1) 先看是否已是补丁状态
    idxp = buf.find(sigp)
    idx = buf.find(sig)
    if idxp >= 0 and idx < 0:
        results.append((t["name"], idxp + off_in_sig, "已补丁", exp, pat))
        print("  %-38s 已是补丁状态 @0x%-8X" % (t["name"], idxp + off_in_sig))
        continue
    if idx < 0:
        print("  %-38s ✗ 未找到特征码" % t["name"])
        results.append((t["name"], None, "未找到", exp, pat))
        continue
    if buf.find(sig, idx + 1) >= 0:
        print("  %-38s ✗ 特征码不唯一" % t["name"])
        results.append((t["name"], None, "不唯一", exp, pat))
        continue

    site = idx + off_in_sig
    got = bytes(buf[site:site + len(exp)])
    if got != exp:
        print("  %-38s ✗ 位点字节不符: %s (期望 %s)" % (t["name"], got.hex().upper(), t["expected"]))
        results.append((t["name"], None, "字节不符", exp, pat))
        continue

    buf[site:site + len(pat)] = pat
    results.append((t["name"], site, "已打补丁", exp, pat))
    print("  %-38s ✓ 0x%-8X  %s -> %s" % (t["name"], site, exp.hex().upper(), pat.hex().upper()))

applied = sum(1 for r in results if r[2] == "已打补丁")
print()
print("应用成功: %d / %d" % (applied, len(TABLE)))

# ---- PE 头修正 ----
def pe_info(d):
    lf = struct.unpack_from('<I', d, 0x3C)[0]
    n = struct.unpack_from('<H', d, lf + 6)[0]
    opt = lf + 24
    osz = struct.unpack_from('<H', d, lf + 20)[0]
    magic = struct.unpack_from('<H', d, opt)[0]
    plus = (magic == 0x20B)
    chk = opt + 0x40
    dd = opt + (0x70 if plus else 0x60)
    sec = dd + 4 * 8
    st = opt + osz
    imgend = 0
    for i in range(n):
        o = st + i * 40
        rs, rp = struct.unpack_from('<II', d, o + 16)
        imgend = max(imgend, rp + rs)
    return dict(checksum=chk, secdir=sec, imgend=imgend, ndd=struct.unpack_from('<I', d, opt + (0x6C if plus else 0x5C))[0])

pi = pe_info(buf)
print()
print("=== PE 头修正 ===")
srv, ssz = struct.unpack_from('<II', buf, pi["secdir"])
print("  数字签名目录 RVA=0x%X Size=0x%X @0x%X" % (srv, ssz, pi["secdir"]))
struct.pack_into('<II', buf, pi["secdir"], 0, 0)
print("  -> 已清零")

overlay = len(buf) - pi["imgend"]
print("  映像末尾=0x%X  尾部(签名)=%d 字节" % (pi["imgend"], overlay))
if overlay > 0 and overlay == ssz:
    del buf[pi["imgend"]:]
    print("  -> 已剥离签名尾部")
elif overlay > 0:
    del buf[pi["imgend"]:]
    print("  -> 已剥离尾部 %d 字节" % overlay)


def pe_checksum(data, off):
    t = 0
    n = len(data)
    for i in range(0, n - 1, 2):
        w = 0 if (off <= i < off + 4) else (data[i] | (data[i + 1] << 8))
        t += w
        t = (t & 0xFFFF) + (t >> 16)
    if n & 1:
        t += data[n - 1]
        t = (t & 0xFFFF) + (t >> 16)
    while t > 0xFFFF:
        t = (t & 0xFFFF) + (t >> 16)
    return (t + n) & 0xFFFFFFFF


old = struct.unpack_from('<I', buf, pi["checksum"])[0]
new = pe_checksum(buf, pi["checksum"])
struct.pack_into('<I', buf, pi["checksum"], new)
print("  PE 校验和: 0x%08X -> 0x%08X" % (old, new))

# ---- 输出与校验 ----
out = os.path.join(SAMPLES, "项目D_643b11_patched.exe")
open(out, 'wb').write(bytes(buf))
print()
print("=== 产物 ===")
print("  路径: %s" % out)
print("  大小: %d 字节 (原 %d, 差 %+d)" % (len(buf), len(orig), len(buf) - len(orig)))
print("  SHA256: %s" % hashlib.sha256(bytes(buf)).hexdigest().upper())

# 复验 PE 合法性
pi2 = pe_info(buf)
ok_pe = True
lf = struct.unpack_from('<I', buf, 0x3C)[0]
n = struct.unpack_from('<H', buf, lf + 6)[0]
opt = lf + 24; osz = struct.unpack_from('<H', buf, lf + 20)[0]
st = opt + osz
for i in range(n):
    o = st + i * 40
    rs, rp = struct.unpack_from('<II', buf, o + 16)
    if rp + rs > len(buf):
        ok_pe = False
print("  PE 结构合法: %s" % ok_pe)

# 差异统计
diffs = [i for i in range(min(len(orig), len(buf))) if orig[i] != buf[i]]
print("  相对原版的字节差异: %d 处" % len(diffs))
