#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PS 版与 Python 版工具解析器的判定一致性测试

背景
    「工具在哪」的规则只有一份（setup/tool-registry.json），但求值器有两个：
      · setup/resolve-tools.ps1      —— Windows 原生，Python 坏掉时也能跑
      · Tool/mcp/tool_resolver.py    —— 纯标准库，Unix / MCP 侧使用

    两份实现必然有分叉风险，所以用一个测试把它们钉在一起：对同一个注册表，
    两边必须给出完全一致的 (id, state) 集合。不一致就说明其中一份的解析链被改漏了。

    本机没有 pwsh 时跳过（SKIP），不算失败。

用法:
    python setup/test_tool_resolver_parity.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "Tool", "mcp"))

FAILS = []


def check(cond, msg):
    if cond:
        print("  [PASS] %s" % msg)
    else:
        print("  [FAIL] %s" % msg)
        FAILS.append(msg)


def find_pwsh():
    for name in ("pwsh", "powershell"):
        p = shutil.which(name)
        if p:
            return p
    return None


def ps_report(pwsh):
    script = os.path.join(HERE, "resolve-tools.ps1")
    cmd = [pwsh, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script, "-Json", "-NoCache"]
    proc = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace", timeout=180,
                          stdin=subprocess.DEVNULL)
    text = proc.stdout.strip()
    if not text:
        raise RuntimeError("PS 版无输出: %s" % (proc.stderr or "")[:200])
    start = text.find("{")
    if start < 0:
        raise RuntimeError("PS 版输出不含 JSON: %s" % text[:200])
    return json.loads(text[start:])


def py_report():
    import tool_resolver
    return tool_resolver.external_tool_report(ROOT, verify=False)


def main():
    print("=== PS / Python 工具解析器判定一致性 ===")

    pwsh = find_pwsh()
    if not pwsh:
        print("  [SKIP] 未找到 pwsh / powershell，无法比对")
        print("\nPARITY SKIP")
        return 0

    try:
        ps = ps_report(pwsh)
    except Exception as exc:  # noqa: BLE001
        print("  [SKIP] PS 版执行失败（%s）" % str(exc)[:120])
        print("\nPARITY SKIP")
        return 0

    py = py_report()

    ps_tools = ps.get("tools", {})
    py_tools = py.get("tools", {})

    # PS 版把 tools 写成数组（@() 包过），Python 版是 {id: {...}}。统一成字典再比。
    if isinstance(ps_tools, list):
        ps_tools = {t.get("id"): t for t in ps_tools if isinstance(t, dict)}
    if isinstance(py_tools, list):
        py_tools = {t.get("id"): t for t in py_tools if isinstance(t, dict)}

    check(bool(ps_tools) and bool(py_tools), "两边都解析出了工具列表")
    check(set(ps_tools) == set(py_tools),
          "工具 id 集合一致（PS %d / PY %d）" % (len(ps_tools), len(py_tools)))

    common = sorted(set(ps_tools) & set(py_tools))
    mismatch = [k for k in common if ps_tools[k]["state"] != py_tools[k]["state"]]
    check(not mismatch, "四态判定一致%s" % ("" if not mismatch else "（不一致: %s）" % ", ".join(
        "%s PS=%s PY=%s" % (k, ps_tools[k]["state"], py_tools[k]["state"]) for k in mismatch)))

    # 路径可以不同（缓存/大小写），但「找到与否」不能不同
    found_diff = [k for k in common if bool(ps_tools[k].get("path")) != bool(py_tools[k].get("path"))]
    check(not found_diff, "命中/未命中一致%s" % ("" if not found_diff else "（%s）" % ", ".join(found_diff)))

    for k in common:
        print("      %-16s PS=%-9s PY=%-9s" % (k, ps_tools[k]["state"], py_tools[k]["state"]))

    print()
    if FAILS:
        print("PARITY FAILED (%d)" % len(FAILS))
        return 1
    print("PARITY OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
