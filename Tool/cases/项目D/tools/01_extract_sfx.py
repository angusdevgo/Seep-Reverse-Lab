"""项目D 6.43b11 安装包完整提取器
条目结构: [0x20 头][zlib 数据]
  头: +0x00 DWORD 原始大小, +0x04 DWORD 压缩大小, +0x08/0x10/0x18 FILETIME
"""
import zlib
import struct
import re
import os
# --- 路径解析（相对本脚本，便于案例库移植）---
_HERE   = os.path.dirname(os.path.abspath(__file__))
BASE    = os.path.dirname(_HERE)                  # 案例根目录
SAMPLES = os.path.join(BASE, "samples")

SRC = os.path.join(BASE, "idman643build11.exe")
OUT = os.path.join(SAMPLES, "extracted")
OV = 0x17400

os.makedirs(OUT, exist_ok=True)
d = open(SRC, 'rb').read()
ov = d[OV:]


def inflate_at(buf, off):
    o = zlib.decompressobj()
    out = o.decompress(buf[off:])
    out += o.flush()
    return out


# ---- 遍历全部条目 ----
entries = []
pos = 0
while pos + 0x20 <= len(ov):
    d0, d1 = struct.unpack_from('<II', ov, pos)
    if d1 <= 0 or pos + 0x20 + d1 > len(ov):
        break
    try:
        data = inflate_at(ov, pos + 0x20)
    except Exception as e:
        print("  [停止] @0x%X 解压失败: %s" % (pos, e))
        break
    entries.append((pos, d0, d1, data))
    pos = pos + 0x20 + d1

print("共解析出 %d 个条目，overlay 覆盖到 0x%X / 0x%X" % (len(entries), pos, len(ov)))
print()

# ---- 从安装脚本解析文件清单 ----
script = entries[0][3].decode('latin1')
names = {}
for m in re.finditer(r'<P(\d+)="([^"]+)"', script):
    names[int(m.group(1))] = m.group(2)
print("脚本清单条目数: %d" % len(names))
print()

# ---- 落盘 ----
manifest_lines = []
for i, (off, d0, d1, data) in enumerate(entries):
    if i == 0:
        fn = "_install_script.txt"
    else:
        fn = names.get(i, "entry_%03d.bin" % i)
    fn = fn.replace('/', os.sep).replace('\\', os.sep)
    target = os.path.join(OUT, fn)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    open(target, 'wb').write(data)
    manifest_lines.append("%-4d %-8s %-42s raw=%9d comp=%8d" % (i, "0x%X" % off, fn, d0, d1))

open(os.path.join(OUT, "_manifest.txt"), 'w', encoding='utf-8').write('\n'.join(manifest_lines))

print("=== 提取清单 ===")
for line in manifest_lines:
    print("  " + line)

# ---- 定位并核验 项目D.exe ----
print()
cand = os.path.join(OUT, "项目D.exe")
if os.path.exists(cand):
    b = open(cand, 'rb').read()
    lf = struct.unpack_from('<I', b, 0x3C)[0]
    nsec = struct.unpack_from('<H', b, lf + 6)[0]
    print("=== 项目D.exe 核验 ===")
    print("  路径: %s" % cand)
    print("  大小: %d 字节" % len(b))
    print("  MZ/PE: %s" % (b[:2] == b'MZ' and b[lf:lf + 4] == b'PE\x00\x00'))
    print("  节区数: %d" % nsec)
    import hashlib
    print("  MD5:    %s" % hashlib.md5(b).hexdigest().upper())
    print("  SHA256: %s" % hashlib.sha256(b).hexdigest().upper())
