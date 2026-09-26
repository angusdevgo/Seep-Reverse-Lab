"""把 samples/aob_table.cs 的 POINTS 数组替换进 src/Program.cs（换行与编码鲁棒）"""
import io
import os
# --- 路径解析（相对本脚本，便于案例库移植）---
_HERE   = os.path.dirname(os.path.abspath(__file__))
BASE    = os.path.dirname(_HERE)                  # 案例根目录
SAMPLES = os.path.join(BASE, "samples")

PROG = BASE + r"\项目D_Pro_Tool\src\Program.cs"
TABLE = os.path.join(SAMPLES, "aob_table.cs")

raw = open(PROG, 'rb').read()
bom = b''
if raw[:3] == b'\xef\xbb\xbf':
    bom = raw[:3]
    raw = raw[3:]

text = raw.decode('utf-8')
lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
print("原文件行数: %d" % len(lines))

anchor = None
for i, ln in enumerate(lines):
    if 'public static readonly AobPoint[] POINTS' in ln:
        anchor = i
        break
assert anchor is not None, "POINTS 锚点未找到"

start = anchor
while start - 1 >= 0 and lines[start - 1].strip().startswith('//'):
    start -= 1

end = None
for j in range(anchor, len(lines)):
    if lines[j].strip() == '};':
        end = j
        break
assert end is not None, "POINTS 结尾未找到"

new = open(TABLE, encoding='utf-8').read()
new_lines = new.replace('\r\n', '\n').replace('\r', '\n').rstrip('\n').split('\n')

print("替换行 %d..%d (共 %d 行) -> %d 行" % (start + 1, end + 1, end - start + 1, len(new_lines)))
out = lines[:start] + new_lines + lines[end + 1:]

# 统一以 CRLF 写回（与原仓库约定一致）
open(PROG, 'wb').write(bom + '\r\n'.join(out).encode('utf-8'))
print("写入完成，总行数 %d" % len(out))
