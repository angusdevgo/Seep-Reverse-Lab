#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Seep 工作台 — `~/.pi/agent/mcp.json` 安全增量合并器（跨平台，纯标准库）

为什么需要它
------------
`setup/install.sh` 原先用一行 `sed "s|<SEEP_ROOT>|$ROOT|g" template > mcp.json`：
**整体覆盖**、**零备份**。用户自己加的 MCP 服务（x64dbg / 自建网关）和
playwright token 会被直接抹掉，而 `setup/update.sh` 头部还写着
"覆盖前自动备份到 backup-<时间戳>/" —— 那句承诺此前没有任何代码实现。

本脚本把 `setup/install-pi.ps1` 的合并语义固化成一份跨平台实现：
只 upsert 工作台自己管理的条目，其余一律原样保留，写盘前先备份。

合并契约
--------
| 条目                | 行为                                                   |
|---------------------|--------------------------------------------------------|
| `seep`              | 总是 upsert（路径与解释器必须指向当前工作台）           |
| `js-reverse`        | 总是 upsert（工作台托管，固定 npx 调用）                |
| `playwright`        | **仅当不存在时**新增；已存在则保留（不覆盖用户 token）   |
| `ida`               | 仅在传入 `--ida-root` 时 upsert；否则已存在则保留、不新增 |
| 其它任何用户条目    | **一律原样保留**                                        |

写盘规格：UTF-8 无 BOM、LF、无结尾换行（与 PowerShell 版一致，避免来回抖动）。
内容与磁盘一致时不写盘（避免 mtime 抖动导致 git 误报「已修改」）。

用法
----
    python setup/mcp-merge.py --root <repo> --python <interp>
    python setup/mcp-merge.py --root <repo> --python <interp> --dry-run
    python setup/mcp-merge.py --root <repo> --python <interp> --ida-root /path/to/ida
    python setup/mcp-merge.py ... --json      # 机器可读结果（供 update.sh 校验）

退出码：0 成功（含 unchanged）；1 目标 JSON 损坏且未加 --force；2 参数/环境错误。
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import shutil
import sys
import time

DEFAULT_TARGET = os.path.join(os.path.expanduser("~"), ".pi", "agent", "mcp.json")

# 工作台托管的条目：这两个总是由脚本决定内容，用户不应手改
MANAGED_ALWAYS = ("seep", "js-reverse")
# 仅在缺失时补的条目（存在即视为用户资产）
ADD_IF_ABSENT = ("playwright",)


# ---------------------------------------------------------------------------
# 读写
# ---------------------------------------------------------------------------
def read_json_bom_tolerant(path: str):
    """读 JSON，容忍 UTF-8 BOM。返回 (data, warning)。"""
    if not os.path.isfile(path):
        return {"mcpServers": {}}, None
    with open(path, "r", encoding="utf-8-sig", errors="replace", newline="") as f:
        raw = f.read()
    if not raw.strip():
        return {"mcpServers": {}}, None
    try:
        data = json.loads(raw)
    except ValueError as exc:
        return None, "现有 mcp.json 语法异常：%s" % exc
    if not isinstance(data, dict):
        return None, "现有 mcp.json 顶层不是对象"
    if not isinstance(data.get("mcpServers"), dict):
        data["mcpServers"] = {}
    return data, None


def write_json(path: str, data: dict) -> None:
    """UTF-8 无 BOM、LF、无结尾换行 —— 与 PowerShell ConvertTo-Json 行为对齐。"""
    text = json.dumps(data, indent=2, ensure_ascii=False)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def backup_target(target: str) -> str | None:
    """备份到 <agent>/backup-<stamp>/mcp.json。返回备份路径。"""
    if not os.path.isfile(target):
        return None
    agent_dir = os.path.dirname(target)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest_dir = os.path.join(agent_dir, "backup-" + stamp)
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, os.path.basename(target))
    shutil.copy2(target, dest)
    return dest


# ---------------------------------------------------------------------------
# 模板与合并
# ---------------------------------------------------------------------------
def load_template(path: str, subs: dict) -> dict:
    """读模板并替换占位符。占位符未提供时保持原样（便于人工补）。"""
    with open(path, "r", encoding="utf-8-sig", errors="replace", newline="") as f:
        raw = f.read()
    for key, val in subs.items():
        if val is not None:
            raw = raw.replace(key, val)
    data = json.loads(raw)
    if not isinstance(data.get("mcpServers"), dict):
        raise ValueError("模板缺少 mcpServers 对象: %s" % path)
    return data


def merge(existing: dict, template: dict, ida_root: str | None) -> tuple[dict, dict]:
    """按契约合并。返回 (合并结果, 变更摘要)。"""
    result = copy.deepcopy(existing)
    servers = result.setdefault("mcpServers", {})
    tpl_servers = template.get("mcpServers", {})

    added, updated, preserved = [], [], []

    for name in MANAGED_ALWAYS:
        if name not in tpl_servers:
            continue
        if name in servers:
            if servers[name] != tpl_servers[name]:
                updated.append(name)
        else:
            added.append(name)
        servers[name] = copy.deepcopy(tpl_servers[name])

    for name in ADD_IF_ABSENT:
        if name not in tpl_servers:
            continue
        if name in servers:
            preserved.append(name)
        else:
            servers[name] = copy.deepcopy(tpl_servers[name])
            added.append(name)

    # ida：只有显式给出 --ida-root 才接管；否则已存在就保留，不存在就不新增
    # （模板里未替换的 <IDA_ROOT>/<IDA_PYTHON> 会产出坏条目，宁可不要）
    if ida_root:
        if "ida" in tpl_servers:
            if "ida" in servers:
                if servers["ida"] != tpl_servers["ida"]:
                    updated.append("ida")
            else:
                added.append("ida")
            servers["ida"] = copy.deepcopy(tpl_servers["ida"])
    elif "ida" in servers:
        preserved.append("ida")

    for name in servers:
        if name not in MANAGED_ALWAYS and name not in ADD_IF_ABSENT and name != "ida":
            preserved.append(name)

    summary = {
        "added": sorted(set(added)),
        "updated": sorted(set(updated)),
        "preserved": sorted(set(preserved)),
    }
    return result, summary


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    default_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser(description="Seep mcp.json \u5b89\u5168\u589e\u91cf\u5408\u5e76\u5668")
    ap.add_argument("--root", default=default_root, help="\u5de5\u4f5c\u53f0\u6839\u76ee\u5f55")
    ap.add_argument("--template", default=None, help="\u9ed8\u8ba4 <root>/Tool/mcp/mcp.json.template")
    ap.add_argument("--target", default=DEFAULT_TARGET, help="\u9ed8\u8ba4 ~/.pi/agent/mcp.json")
    ap.add_argument("--python", default=sys.executable, help="seep MCP \u4f7f\u7528\u7684\u89e3\u91ca\u5668\u7edd\u5bf9\u8def\u5f84")
    ap.add_argument("--ida-root", default=None, help="\u663e\u5f0f\u7ed9\u51fa\u65f6\u624d\u63a5\u7ba1 ida \u6761\u76ee")
    ap.add_argument("--ida-python", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-backup", action="store_true")
    ap.add_argument("--force", action="store_true", help="\u76ee\u6807 JSON \u635f\u574f\u65f6\u4ecd\u5199\u76d8\uff08\u4ecd\u4f1a\u5148\u5907\u4efd\uff09")
    ap.add_argument("--json", action="store_true", help="\u8f93\u51fa\u673a\u5668\u53ef\u8bfb\u7ed3\u679c")
    args = ap.parse_args(argv)

    root = os.path.abspath(args.root).replace("\\", "/").rstrip("/")
    template_path = args.template or os.path.join(root, "Tool", "mcp", "mcp.json.template")
    if not os.path.isfile(template_path):
        print("[ERROR] \u6a21\u677f\u4e0d\u5b58\u5728: %s" % template_path, file=sys.stderr)
        return 2

    # 关键：所有路径类占位符都要先归一化为正斜杠。
    # 直接塞 "D:\Tool\...\python.exe" 进 JSON 字符串会产生 \T 这种非法转义，
    # json.loads 直接抛 "Invalid \escape"。Python 在 Windows 上同样接受正斜杠。
    def posix(p):
        return p.replace("\\", "/") if p else p

    subs = {
        "<SEEP_ROOT>": root,
        "<SEEP_PYTHON>": posix(args.python),
    }
    if args.ida_root:
        ida_root = os.path.abspath(args.ida_root).replace("\\", "/").rstrip("/")
        subs["<IDA_ROOT>"] = ida_root
        subs["<IDA_ROOT>"] = ida_root
        ida_py = args.ida_python or os.path.join(ida_root, "python311", "python.exe")
        subs["<IDA_PYTHON>"] = posix(ida_py)

    try:
        template = load_template(template_path, subs)
    except (OSError, ValueError) as exc:
        print("[ERROR] \u6a21\u677f\u89e3\u6790\u5931\u8d25: %s" % exc, file=sys.stderr)
        return 2

    existing, warning = read_json_bom_tolerant(args.target)
    if existing is None:
        if not args.force:
            print("[ERROR] %s" % warning, file=sys.stderr)
            print("        \u5982\u786e\u8ba4\u8981\u91cd\u5efa\uff0c\u52a0 --force\uff08\u4ecd\u4f1a\u5148\u5907\u4efd\u539f\u6587\u4ef6\uff09", file=sys.stderr)
            return 1
        print("[WARN] %s \u2014\u2014 \u5df2\u52a0 --force\uff0c\u5c06\u91cd\u5efa" % warning, file=sys.stderr)
        existing = {"mcpServers": {}}

    merged, summary = merge(existing, template, args.ida_root)

    unchanged = (merged == existing)
    backup_path = None

    if args.dry_run:
        pass
    elif unchanged:
        pass
    else:
        if not args.no_backup:
            backup_path = backup_target(args.target)
        write_json(args.target, merged)

    if args.json:
        print(json.dumps({
            "target": args.target,
            "unchanged": unchanged,
            "backup": backup_path,
            "added": summary["added"],
            "updated": summary["updated"],
            "preserved": summary["preserved"],
            "keys": sorted(merged.get("mcpServers", {}).keys()),
        }, ensure_ascii=False))
        return 0

    print("  target   : %s" % args.target)
    if backup_path:
        print("  backup   : %s" % backup_path)
    if unchanged:
        print("  result   : \u672a\u53d8\u5316\uff08\u5185\u5bb9\u4e00\u81f4\uff0c\u672a\u5199\u76d8\uff09")
    else:
        print("  result   : %s" % ("DRY-RUN \u9884\u89c8" if args.dry_run else "\u5df2\u5199\u5165"))
    print("  added    : %s" % (", ".join(summary["added"]) or "\u2014"))
    print("  updated  : %s" % (", ".join(summary["updated"]) or "\u2014"))
    print("  preserved: %s" % (", ".join(summary["preserved"]) or "\u2014"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
