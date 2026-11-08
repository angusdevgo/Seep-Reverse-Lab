#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""`setup/mcp-merge.py` 契约测试（纯标准库，跨平台可跑）

守住五条合并语义 —— 它们直接决定「更新会不会毁掉用户配置」：
  1. 用户自加的 MCP 条目一律保留
  2. playwright 已存在时保留（不覆盖用户的 token）
  3. seep 总是被 upsert（路径与解释器必须指向当前工作台）
  4. 写盘前生成备份
  5. 输入带 UTF-8 BOM 也能正确解析

用法:
    python setup/test_mcp_merge.py
退出码: 0 通过 / 1 失败
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
MERGE = os.path.join(HERE, "mcp-merge.py")
TEMPLATE = os.path.join(os.path.dirname(HERE), "Tool", "mcp", "mcp.json.template")

FAILS = []


def check(cond, name, detail=""):
    if cond:
        print("  [PASS] %s" % name)
    else:
        print("  [FAIL] %s%s" % (name, ("  -> " + detail) if detail else ""))
        FAILS.append(name)


REPO_ROOT = os.path.dirname(HERE)


def run_merge(root, python, target, extra=None, dry=False):
    cmd = [sys.executable, MERGE, "--root", REPO_ROOT, "--python", python,
           "--template", TEMPLATE, "--target", target, "--json"]
    if extra:
        cmd += extra
    if dry:
        cmd.append("--dry-run")
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    return proc


def load(path):
    with io.open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def main() -> int:
    if not os.path.isfile(MERGE):
        print("[SKIP] 找不到 setup/mcp-merge.py")
        return 0
    if not os.path.isfile(TEMPLATE):
        print("[SKIP] 找不到 Tool/mcp/mcp.json.template")
        return 0

    print("=== mcp-merge 契约测试 ===")
    tmp = tempfile.mkdtemp(prefix="seep-merge-")
    target = os.path.join(tmp, "agent", "mcp.json")
    os.makedirs(os.path.dirname(target), exist_ok=True)

    # 预置用户资产：自定义条目 + 已存在的 playwright（带真 token）
    seed = {
        "mcpServers": {
            "x64dbg": {"command": "x64dbg-mcp"},
            "playwright": {
                "command": "npx",
                "args": ["-y", "@playwright/mcp@latest", "--extension"],
                "env": {"PLAYWRIGHT_MCP_EXTENSION_TOKEN": "user-real-token"},
            },
        }
    }
    with io.open(target, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(seed, indent=2, ensure_ascii=False))

    # ---- 1. dry-run 不改盘
    before = io.open(target, encoding="utf-8").read()
    run_merge(tmp, "C:\\Py\\python.exe", target, dry=True)
    after = io.open(target, encoding="utf-8").read()
    check(before == after, "dry-run 不修改目标文件")

    # ---- 2/3/4. 真实合并
    proc = run_merge(tmp, "C:\\Py\\python.exe", target)
    check(proc.returncode == 0, "合并退出码为 0", proc.stderr[:200])
    try:
        result = json.loads(proc.stdout)
    except ValueError:
        check(False, "输出为合法 JSON", proc.stdout[:200])
        return 1

    merged = load(target)
    servers = merged.get("mcpServers", {})

    check("x64dbg" in servers, "语义1: 用户自定义条目被保留",
          str(sorted(servers)))
    check(servers.get("playwright", {}).get("env", {}).get(
              "PLAYWRIGHT_MCP_EXTENSION_TOKEN") == "user-real-token",
          "语义2: playwright 已存在时保留用户 token",
          str(servers.get("playwright")))
    check(servers.get("seep", {}).get("command") == "C:/Py/python.exe",
          "语义3: seep 被 upsert 为新解释器",
          str(servers.get("seep", {}).get("command")))
    check("ida" not in servers, "未给 --ida-root 时不注入坏的 ida 条目")

    backup = result.get("backup")
    check(bool(backup) and os.path.isfile(backup), "语义4: 写盘前生成备份",
          str(backup))

    # ---- 5. BOM 输入可读
    bom_target = os.path.join(tmp, "agent2", "mcp.json")
    os.makedirs(os.path.dirname(bom_target), exist_ok=True)
    with io.open(bom_target, "w", encoding="utf-8-sig", newline="\n") as f:
        f.write(json.dumps({"mcpServers": {"keepme": {"command": "x"}}},
                           indent=2, ensure_ascii=False))
    proc2 = run_merge(tmp, "C:\\Py\\python.exe", bom_target)
    check(proc2.returncode == 0, "语义5: 带 BOM 的 mcp.json 可解析",
          proc2.stderr[:200])
    if proc2.returncode == 0:
        check("keepme" in load(bom_target).get("mcpServers", {}),
              "语义5b: BOM 文件里的用户条目未丢失")

    # ---- 6. 幂等：再跑一次应报 unchanged
    proc3 = run_merge(tmp, "C:\\Py\\python.exe", bom_target)
    try:
        r3 = json.loads(proc3.stdout)
    except ValueError:
        r3 = {}
    check(r3.get("unchanged") is True, "幂等: 内容一致时不重复写盘",
          str(r3.get("unchanged")))

    # ---- 7. 损坏 JSON 未加 --force 时应拒绝
    bad = os.path.join(tmp, "agent3", "mcp.json")
    os.makedirs(os.path.dirname(bad), exist_ok=True)
    with io.open(bad, "w", encoding="utf-8", newline="\n") as f:
        f.write("{ this is not json")
    proc4 = run_merge(tmp, "C:\\Py\\python.exe", bad)
    check(proc4.returncode == 1, "损坏 JSON 默认拒绝写盘（不静默清空用户配置）",
          "rc=%d" % proc4.returncode)

    print("")
    if FAILS:
        print("MERGE TESTS FAILED (%d)" % len(FAILS))
        return 1
    print("MERGE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
