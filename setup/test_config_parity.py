#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`generate-configs.py` 与 `generate-configs.ps1` 输出一致性测试

两份生成器各服务一个平台（Unix 走 .py，Windows 走 .ps1）。它们必须产出**逐字节相同**
的三份配置，否则同一个仓库在不同平台生成的 `.mcp.json` / `opencode.jsonc` /
`cordis.generated.yml` 会出现差异，进而引发「我这台好用、他那台不好用」。

做法：把两份生成器分别跑进两个临时根目录，比较三份产物。
`opencode.jsonc` 与 `cordis.generated.yml` 内嵌了工作台绝对路径，
比较前先把各自的根目录替换成占位符。

无 PowerShell（非 Windows 且无 pwsh）时 SKIP，不判失败。

用法:
    python setup/test_config_parity.py
退出码: 0 通过或 SKIP / 1 失败
"""

from __future__ import annotations

import io
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
GEN_PY = os.path.join(HERE, "generate-configs.py")
GEN_PS1 = os.path.join(HERE, "generate-configs.ps1")

PRODUCTS = (".mcp.json", "opencode.jsonc", os.path.join("setup", "cordis.generated.yml"))
FAILS = []


def find_powershell():
    for cand in ("pwsh", "powershell"):
        p = shutil.which(cand)
        if p:
            return p
    return None


def read_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def normalize(data: bytes, root: str) -> bytes:
    """把临时根目录替换成占位符，消除路径差异。"""
    posix = root.replace("\\", "/").rstrip("/")
    out = data
    for variant in (posix, posix.replace("/", "\\"), root, root.replace("/", "\\")):
        out = out.replace(variant.encode("utf-8"), b"<ROOT>")
    return out


def check(cond, name, detail=""):
    if cond:
        print("  [PASS] %s" % name)
    else:
        print("  [FAIL] %s%s" % (name, ("  -> " + detail) if detail else ""))
        FAILS.append(name)


def main() -> int:
    if not os.path.isfile(GEN_PY):
        print("[SKIP] 找不到 setup/generate-configs.py")
        return 0
    ps = find_powershell()
    if not ps:
        print("[SKIP] 未找到 PowerShell（非 Windows 且无 pwsh），跳过双生成器比对")
        return 0

    print("=== generate-configs 双平台一致性 ===")
    base = tempfile.mkdtemp(prefix="seep-gen-")
    root_a = os.path.join(base, "a")
    root_b = os.path.join(base, "b")
    for r in (root_a, root_b):
        os.makedirs(os.path.join(r, "Tool", "mcp"), exist_ok=True)
        os.makedirs(os.path.join(r, "setup"), exist_ok=True)

    # 1) Python 生成器
    proc = subprocess.run([sys.executable, GEN_PY, "--root", root_a],
                          capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    check(proc.returncode == 0, "generate-configs.py 执行成功",
          (proc.stderr or proc.stdout)[-300:])

    # 2) PowerShell 生成器
    proc2 = subprocess.run([ps, "-NoProfile", "-ExecutionPolicy", "Bypass",
                            "-File", GEN_PS1, "-Root", root_b],
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
    check(proc2.returncode == 0, "generate-configs.ps1 执行成功",
          (proc2.stderr or proc2.stdout)[-300:])

    # 3) 逐字节比对
    for rel in PRODUCTS:
        pa = os.path.join(root_a, rel)
        pb = os.path.join(root_b, rel)
        if not (os.path.isfile(pa) and os.path.isfile(pb)):
            check(False, "产物存在: %s" % rel,
                  "py=%s ps1=%s" % (os.path.isfile(pa), os.path.isfile(pb)))
            continue
        a = normalize(read_bytes(pa), root_a)
        b = normalize(read_bytes(pb), root_b)
        if a == b:
            check(True, "字节一致: %s" % rel)
        else:
            # 给出第一处差异，便于定位
            i = next((k for k in range(min(len(a), len(b))) if a[k] != b[k]), -1)
            ctx = ""
            if i >= 0:
                ctx = "首个差异 @%d: py=%r ps1=%r" % (
                    i, a[max(0, i - 20):i + 30], b[max(0, i - 20):i + 30])
            check(False, "字节一致: %s" % rel, ctx or "长度不同: %d vs %d" % (len(a), len(b)))

    shutil.rmtree(base, ignore_errors=True)

    print("")
    if FAILS:
        print("PARITY FAILED (%d)" % len(FAILS))
        return 1
    print("PARITY OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
