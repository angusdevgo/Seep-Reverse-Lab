"""从 final_table.json 生成 C# 特征码表源码片段"""
import json
import textwrap
import os
# --- 路径解析（相对本脚本，便于案例库移植）---
_HERE   = os.path.dirname(os.path.abspath(__file__))
BASE    = os.path.dirname(_HERE)                  # 案例根目录
SAMPLES = os.path.join(BASE, "samples")

TABLE = json.load(open(os.path.join(SAMPLES, "final_table.json"), encoding='utf-8'))

def wrap_hex(h, indent):
    """把长 hex 串折成多行 C# 字符串拼接"""
    parts = textwrap.wrap(h, 96)
    if len(parts) == 1:
        return '"%s"' % parts[0]
    out = []
    for i, p in enumerate(parts):
        if i == 0:
            out.append('"%s" +' % p)
        elif i == len(parts) - 1:
            out.append(indent + '"%s"' % p)
        else:
            out.append(indent + '"%s" +' % p)
    return '\n'.join(out)

lines = []
lines.append("        // ===== AOB 特征码表 =====")
lines.append("        // 经 项目D 6.43 build 10 / build 11 (6.43.11.2) / build 11 (6.43.11.3) 三版本交叉验证：")
lines.append("        // 全部 14 个位点在三个版本的「原始态 / 已补丁态」中均为唯一命中。")
lines.append("        public static readonly AobPoint[] POINTS = new AobPoint[]")
lines.append("        {")
for t in TABLE:
    lines.append('            new AobPoint(')
    lines.append('                "%s",' % t["name"])
    lines.append('                %s,' % wrap_hex(t["sig"], ' ' * 16))
    lines.append('                %s,' % wrap_hex(t["sigPatched"], ' ' * 16))
    lines.append('                %d, "%s", "%s"),' % (t["patchOffsetInSig"], t["expected"], t["patch"]))
lines.append("        };")

open(os.path.join(SAMPLES, "aob_table.cs"), 'w', encoding='utf-8').write('\n'.join(lines))
print("生成 %d 条特征码" % len(TABLE))
print("总行数 %d" % len(lines))
print()
print('\n'.join(lines[:12]))
print("...")
print('\n'.join(lines[-4:]))
