#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""agy 钩子活体探针：边开着它，边在 Antigravity 里操作，看有没有反应。

它盯三样东西：

  1. ~/.seep/agy-lab.json    —— lab 开关状态（发 `lab：` 会立刻变）
  2. ~/.seep/agy-audit.jsonl —— 工具调用流水（模型一调工具就多一行）
  3. 进程还在不在            —— 没在跑就什么都看不到

用法：
    python setup/agy-watch.py              # 一直盯，Ctrl+C 退出
    python setup/agy-watch.py --once       # 只看当前快照，然后退出

看到 "✅ 钩子在跑" 就说明接线生效了。什么都看不到 = 钩子没被调用，看下面的排查。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

STATE_DIR = Path(os.path.expanduser(os.environ.get("SEEP_AGENT_STATE", "~/.seep")))
LAB = STATE_DIR / "agy-lab.json"
AUDIT = STATE_DIR / "agy-audit.jsonl"
REPO = Path(__file__).resolve().parent.parent
HOOKS_JSON = REPO / ".agents" / "hooks.json"


def _fmt_lab(data: dict) -> list[str]:
    if not isinstance(data, dict) or not data:
        return []
    out = []
    for cid, rec in data.items():
        if not isinstance(rec, dict):
            continue
        on = "🟢 lab 开" if rec.get("on") else "⚪ lab 关"
        ts = rec.get("ts") or 0
        try:
            when = time.strftime("%H:%M:%S", time.localtime(float(ts)))
        except (TypeError, ValueError):
            when = "  ?  "
        out.append(f"      {on}  {when}  会话 {cid[:16]}")
    return out


def snapshot() -> str:
    lines = []
    lines.append(f"  状态目录 : {STATE_DIR}")
    lines.append(f"  钩子配置 : {HOOKS_JSON} {'✓ 在' if HOOKS_JSON.is_file() else '✗ 没有（跑 agy-setup.py --with-hooks）'}")
    lines.append("")

    if LAB.is_file():
        try:
            data = json.loads(LAB.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = {}
        rows = _fmt_lab(data)
        lines.append(f"  lab 状态 : {'有记录' if rows else '文件在但没内容'}")
        lines.extend(rows)
    else:
        lines.append("  lab 状态 : ✗ 还没有（说明 PreInvocation 从没被调用过）")

    lines.append("")
    if AUDIT.is_file():
        n = 0
        tail = []
        with AUDIT.open(encoding="utf-8", errors="replace") as f:
            for line in f:
                n += 1
                if line.strip():
                    tail.append(line.rstrip())
        lines.append(f"  审计流水 : {n} 条")
        for row in tail[-3:]:
            try:
                rec = json.loads(row)
                lines.append(f"      {rec.get('ts','')}  {rec.get('tool','?'):<18} "
                             f"{'ok' if rec.get('ok') else 'FAIL'}")
            except json.JSONDecodeError:
                lines.append(f"      {row[:100]}")
    else:
        lines.append("  审计流水 : ✗ 还没有（说明 PostToolUse 从没被调用过）")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="看 agy 钩子到底有没有被调用")
    ap.add_argument("--once", action="store_true", help="只打一次快照")
    ap.add_argument("--interval", type=float, default=1.0, help="刷新间隔秒数")
    args = ap.parse_args()

    if args.once:
        print(snapshot())
        return 0

    print("盯着钩子输出，在 Antigravity 里发一句 `lab：` 试试。Ctrl+C 退出。\n")
    last = None
    try:
        while True:
            snap = snapshot()
            if snap != last:
                print("=" * 68)
                print(time.strftime("%H:%M:%S"))
                print(snap)
                if LAB.is_file() or AUDIT.is_file():
                    print("\n  ✅ 钩子在跑")
                last = snap
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\n退出。")
    return 0


if __name__ == "__main__":
    sys.exit(main())