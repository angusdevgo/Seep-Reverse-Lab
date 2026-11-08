#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""MCP 服务逐个实探：配置里写了，和「真的能用」，是两件事

读一个 mcp.json（默认 pi 的 ~/.pi/agent/mcp.json），对里面每个 stdio 服务
做一次真实的 initialize → tools/list 握手，报出工具数量与名字。

用途：
  · 核对 pi / DSH / Claude Code 各自到底挂了哪些服务、各有多少工具；
  · 排查「配置里有但工具列表是空的」这类静默故障。

用法:
    python setup/probe-mcp.py                       # 探 pi 的 mcp.json
    python setup/probe-mcp.py --config <path>       # 探指定文件
    python setup/probe-mcp.py --only seep,ida       # 只探这两个
    python setup/probe-mcp.py --timeout 60
    python setup/probe-mcp.py --json
"""

from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import subprocess
import sys

INIT = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                   "clientInfo": {"name": "probe-mcp", "version": "1.0"}}}
INITED = {"jsonrpc": "2.0", "method": "notifications/initialized"}
LIST = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
PAYLOAD = "\n".join(json.dumps(m, ensure_ascii=False) for m in (INIT, INITED, LIST)) + "\n"


def default_config() -> str:
    return os.path.join(os.path.expanduser("~"), ".pi", "agent", "mcp.json")


def probe(name: str, cfg: dict, timeout: int = 180):
    command = cfg.get("command") or ""
    args = list(cfg.get("args") or [])
    if not command:
        return None, "配置里没有 command", []

    # Windows 上 npx / *.cmd 需要 shell 才能解析
    shell = os.name == "nt" and os.path.basename(command).lower() in ("npx", "npx.cmd", "npm", "npm.cmd")

    # 显式解析一次路径，避免子进程找不到命令时报 WinError 2
    if shutil.which(command):
        command = shutil.which(command)

    env = dict(os.environ)
    env.update(cfg.get("env") or {})
    env.setdefault("PYTHONIOENCODING", "utf-8")

    try:
        p = subprocess.run([command] + args, input=PAYLOAD, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout, env=env, shell=shell)
    except subprocess.TimeoutExpired:
        return None, "超时 %ds 未响应" % timeout, []
    except FileNotFoundError:
        return None, "命令不存在: %s" % command, []
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)[:140], []

    seen_result = False
    for line in (p.stdout or "").splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        if msg.get("id") == 1 and isinstance(msg.get("result"), dict):
            seen_result = True
        res = msg.get("result")
        if isinstance(res, dict) and isinstance(res.get("tools"), list):
            return [t.get("name") for t in res["tools"]], "", []

    tail = (p.stderr or p.stdout or "").strip().splitlines()
    reason = tail[0][:140] if tail else "无 tools/list 响应 (rc=%s)" % p.returncode
    if not seen_result and not tail:
        reason = "initialize 无响应 (rc=%s)" % p.returncode
    return None, reason, []


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="MCP 服务逐个实探")
    ap.add_argument("--config", default=default_config())
    ap.add_argument("--only", default="", help="逗号分隔的服务名")
    ap.add_argument("--timeout", type=int, default=180)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.config):
        print("[FAIL] 找不到配置文件: %s" % args.config, file=sys.stderr)
        return 2
    with io.open(args.config, encoding="utf-8-sig") as f:
        servers = json.load(f).get("mcpServers", {})
    if not servers:
        print("[FAIL] 配置里没有 mcpServers", file=sys.stderr)
        return 2

    names = [n.strip() for n in args.only.split(",") if n.strip()] or list(servers)
    out = {}
    for name in names:
        cfg = servers.get(name)
        if not cfg:
            out[name] = {"ok": False, "count": 0, "tools": [], "reason": "不在该配置里"}
            continue
        tools, reason, _ = probe(name, cfg, args.timeout)
        out[name] = {"ok": tools is not None, "count": len(tools or []),
                     "tools": sorted(tools or []), "reason": reason}

    if args.json:
        print(json.dumps({"config": args.config, "servers": out}, ensure_ascii=False, indent=2))
    else:
        print("\n  配置: %s\n" % args.config)
        total = 0
        for name, r in out.items():
            if r["ok"]:
                total += r["count"]
                print("  %-14s [OK]   %2d 个工具" % (name, r["count"]))
                for i in range(0, len(r["tools"]), 6):
                    print("                        " + ", ".join(r["tools"][i:i + 6]))
            else:
                print("  %-14s [FAIL] %s" % (name, r["reason"]))
        print("\n  合计: %d 个工具 / %d 个服务\n" % (total, len(out)))

    return 0 if all(r["ok"] for r in out.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
