#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pi agent 关键配置面的指纹快照 / 漂移比对

用途：在跑部署或更新之前拍一张快照，跑完再拍一张，比对是否动过 pi agent 的
skill / MCP / 提示词 / 扩展。回答的是「这次操作有没有污染我自己的环境」，
而不是「部署成功了没有」。

只覆盖会被部署流程触碰的部分（~/.pi/agent 下的配置文件 + skills/ + extensions/），
**不扫** project/、logs/ 之类的作业目录。

用法:
    python setup/pi-agent-snapshot.py snapshot before.json
    python setup/pi-agent-snapshot.py snapshot after.json
    python setup/pi-agent-snapshot.py diff before.json after.json     # 有漂移则 rc=1

可用 SEEP_AGENT_DIR 指定其它 agent 目录（隔离部署时用）。
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys

TARGETS = ["mcp.json", "settings.json", "AGENTS.md", "seep-system.md", "SYSTEM.md"]
DIRS = ["skills", "extensions"]
SKIP_DIRS = {"node_modules", "__pycache__", ".git", "seep-venv", "py312-venv"}


def agent_root() -> str:
    env = os.environ.get("SEEP_AGENT_DIR")
    if env:
        return env
    return os.path.join(os.path.expanduser("~"), ".pi", "agent")


def sha(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def collect(root: str) -> dict:
    rows = {}
    for name in TARGETS:
        p = os.path.join(root, name)
        if os.path.isfile(p):
            rows[name] = {"sha": sha(p), "size": os.path.getsize(p)}
    for d in DIRS:
        base = os.path.join(root, d)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [x for x in dirnames if x not in SKIP_DIRS]
            for fn in filenames:
                p = os.path.join(dirpath, fn)
                rel = os.path.relpath(p, root).replace(os.sep, "/")
                try:
                    rows[rel] = {"sha": sha(p), "size": os.path.getsize(p)}
                except OSError:
                    rows[rel] = {"sha": "ERR", "size": 0}
    return rows


def cmd_snapshot(out: str) -> int:
    root = agent_root()
    if not os.path.isdir(root):
        print("[SKIP] agent 目录不存在: %s" % root)
        return 0
    rows = collect(root)
    with io.open(out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1, sort_keys=True)
    skills = sorted({k.split("/")[1] for k in rows if k.startswith("skills/")})
    print("  目录  : %s" % root)
    print("  条目  : %d" % len(rows))
    print("  skills: %d 个" % len(skills))
    print("  已写出: %s" % out)
    return 0


def cmd_diff(before: str, after: str) -> int:
    a = json.load(io.open(before, encoding="utf-8"))
    b = json.load(io.open(after, encoding="utf-8"))
    added = sorted(set(b) - set(a))
    removed = sorted(set(a) - set(b))
    changed = sorted(k for k in set(a) & set(b) if a[k] != b[k])

    def show(label, items, limit=12):
        if not items:
            return
        print("  %s: %d" % (label, len(items)))
        for it in items[:limit]:
            print("      %s" % it)
        if len(items) > limit:
            print("      … 另 %d 项" % (len(items) - limit))

    show("新增", added)
    show("删除", removed)
    show("变更", changed)

    if added or removed or changed:
        print("  结论: 有漂移（共 %d 处）" % (len(added) + len(removed) + len(changed)))
        return 1
    print("  结论: 无漂移 —— pi agent 的 skill / MCP / 提示词 / 扩展完全未被改动")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="pi agent 配置面指纹快照 / 漂移比对")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s1 = sub.add_parser("snapshot", help="拍快照")
    s1.add_argument("out")
    s2 = sub.add_parser("diff", help="比对两份快照")
    s2.add_argument("before")
    s2.add_argument("after")
    args = ap.parse_args(argv)

    if args.cmd == "snapshot":
        return cmd_snapshot(args.out)
    return cmd_diff(args.before, args.after)


if __name__ == "__main__":
    sys.exit(main())
