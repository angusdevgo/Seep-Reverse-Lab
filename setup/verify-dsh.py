#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DeepSeek Harness 部署完整度校验

回答一个问题：**工作台在 DSH 上到底部署全了没有，缺什么。**

分母不是「pi 上有什么」，而是「DSH 上本来应该有什么」——
DSH 只有 AGENTS.md 指令层，没有 skill 加载器，所以 skill 数量按 N/A 处理，
不计入分母。这一点搞错的话，任何 DSH 部署都会被算成「缺了 10 个 skill」。

用法:
    python setup/verify-dsh.py                  # 默认 profile=web
    python setup/verify-dsh.py --profile tui
    python setup/verify-dsh.py --json           # 机器可读
    python setup/verify-dsh.py --skip-spawn     # 只查配置，不真启动 MCP（快）

退出码: 0 = 核心项全部通过；1 = 有核心项缺失；2 = 环境不可用（找不到 dsh）
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "Tool", "mcp"))

EXPECT_SEEP_TOOLS = 38      # seep MCP 的对外工具数（tools/list 实测）
EXPECT_JS_TOOLS = 24        # js-reverse 的工具数
EXPECT_KB = 294             # 知识库篇数下限
EXPECT_CASES = 14           # 脱敏案例数下限
EXPECT_MANUALS = 7          # MANUAL/ 战术手册数下限
EXPECT_SKILLS = 10          # 技能源目录的唯一名数量
MIN_TIMEOUT_MS = 300000     # 长任务所需的最低超时（DSH 默认 60s 会杀任务）

OPTIONAL_TOOLS = ["ida", "playwright", "ffmpeg", "frida", "apkid", "aotopsy"]


# ---------------------------------------------------------------- 基础工具

def dsh_home() -> str:
    env = os.environ.get("DSH_HOME")
    if env and env.strip():
        return env
    return os.path.join(os.path.expanduser("~"), ".dsh")


def find_dsh():
    for name in ("dsh", "dsh.cmd", "dsh.ps1"):
        p = shutil.which(name)
        if p:
            return p
    return None


def run(cmd, timeout=60, env_extra=None, stdin_text=None, shell=False):
    env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    if env_extra:
        env.update(env_extra)
    try:
        p = subprocess.run(cmd, input=stdin_text, capture_output=True, encoding="utf-8",
                           errors="replace", timeout=timeout, env=env, shell=shell)
        return p.returncode, (p.stdout or ""), (p.stderr or "")
    except subprocess.TimeoutExpired:
        return None, "", "超时 %ds" % timeout
    except Exception as exc:  # noqa: BLE001
        return None, "", str(exc)


INIT_MSGS = "\n".join(json.dumps(x, ensure_ascii=False) for x in (
    {"jsonrpc": "2.0", "id": 1, "method": "initialize",
     "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                "clientInfo": {"name": "verify-dsh", "version": "1.0"}}},
    {"jsonrpc": "2.0", "method": "notifications/initialized"},
    {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
)) + "\n"


def spawn_tools(command, args, timeout=180):
    """真启动一个 stdio MCP，返回 (工具名列表 | None, 说明)。"""
    argv = [command] + list(args or [])
    use_shell = os.name == "nt" and os.path.basename(command).lower() in ("npx", "npx.cmd", "dsh.cmd")
    rc, out, err = run(argv, timeout=timeout, stdin_text=INIT_MSGS, shell=use_shell)
    if rc is None:
        return None, err or "启动超时"
    for line in out.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        res = msg.get("result")
        if isinstance(res, dict) and isinstance(res.get("tools"), list):
            return [t.get("name") for t in res["tools"]], ""
    tail = (err or out or "").strip().splitlines()
    return None, (tail[0][:130] if tail else "无 tools/list 响应 rc=%s" % rc)


# ---------------------------------------------------------------- 计分

class Report:
    def __init__(self):
        self.items = []
        self.optional = []

    def add(self, group, key, label, weight, ok, detail="", fix=""):
        self.items.append({
            "group": group, "key": key, "label": label, "weight": weight,
            "ok": bool(ok), "detail": detail, "fix": fix,
        })
        return ok

    def add_optional(self, label, state, detail="", fix=""):
        self.optional.append({"label": label, "state": state, "detail": detail, "fix": fix})

    @property
    def total(self):
        return sum(i["weight"] for i in self.items)

    @property
    def earned(self):
        return sum(i["weight"] for i in self.items if i["ok"])

    @property
    def rate(self):
        return 100.0 * self.earned / self.total if self.total else 0.0


# ---------------------------------------------------------------- 检查项

def check_config(rep, profile, composed):
    """第 1 组：DSH 配置层（25 分）"""
    G = "配置层"
    home = dsh_home()
    patch = os.path.join(home, "profiles", profile, "cordis.patch.yml")
    if not os.path.isfile(patch):
        patch = os.path.join(home, "cordis.patch.yml")

    # A1 标记块
    body = ""
    if os.path.isfile(patch):
        body = io.open(patch, encoding="utf-8", errors="replace").read()
    has_block = ">>> seep-workbench" in body
    rep.add(G, "A1", "cordis.patch.yml 含 seep-workbench 标记块", 6, has_block,
            patch if os.path.isfile(patch) else "文件不存在: %s" % patch,
            "python setup/dsh-merge.py --profile %s" % profile)

    # A2 / A3 composed 里有 serverName
    rep.add(G, "A2", "合成配置里有 serverName: seep", 6, "serverName: seep" in composed,
            "见 dsh --dump-config", "重跑 dsh-merge.py 或检查 profile 名")
    rep.add(G, "A3", "合成配置里有 serverName: js-reverse", 5, "serverName: js-reverse" in composed,
            "见 dsh --dump-config", "重跑 dsh-merge.py")

    # A4 超时
    seep_block = ""
    m = re.search(r"serverName: seep(.{0,1200})", composed, re.S)
    if m:
        seep_block = m.group(1)
    tmo = re.search(r"toolCallTimeoutMs:\s*(\d+)", seep_block)
    tmo_val = int(tmo.group(1)) if tmo else 0
    rep.add(G, "A4", "seep 的 toolCallTimeoutMs ≥ %d" % MIN_TIMEOUT_MS, 4,
            tmo_val >= MIN_TIMEOUT_MS,
            "实测 %s（DSH 默认 60000，会杀掉 jadx/HLS/AOT 长任务）" % (tmo_val or "未设置"),
            "重跑 dsh-merge.py，或手动加 toolCallTimeoutMs: 900000")

    # A5 cwd 钉住
    repo_posix = ROOT.replace("\\", "/")
    has_cwd = "cwd:" in seep_block and (repo_posix in seep_block or ROOT in seep_block)
    rep.add(G, "A5", "seep 的 cwd 指向仓库根", 2, has_cwd,
            "seep_mcp_server.py 用相对路径找内置工具，cwd 错了就找不到",
            "重跑 dsh-merge.py（会写入 --root 解析出的绝对路径）")

    # A6 failOnStartupError
    rep.add(G, "A6", "failOnStartupError: false（单服务故障不拖垮整栈）", 2,
            "failOnStartupError: false" in composed, "", "重跑 dsh-merge.py")


def check_mcp(rep, composed, skip_spawn):
    """第 2 组：MCP 可用性（30 分）"""
    G = "MCP 可用性"

    if skip_spawn:
        for key, label, w in (("B1", "seep 能 initialize", 8), ("B2", "seep tools/list 工具数", 10),
                              ("B3", "js-reverse 能 initialize", 6), ("B4", "js-reverse tools/list 工具数", 6)):
            rep.add(G, key, label, w, False, "已跳过（--skip-spawn）", "去掉 --skip-spawn 重跑")
        return

    # 从 composed 中抠出每个 server 的 command/args
    def extract(server):
        m = re.search(r"serverName: %s(.*?)(?=\n- id:|\n    - id:|\Z)" % re.escape(server), composed, re.S)
        if not m:
            return None, None
        blk = m.group(1)
        cmd = re.search(r"command:\s*(.+)", blk)
        args = re.findall(r"^\s*-\s+>-\s*\n\s*(.+)$|^\s*-\s+'?([^'\n]+)'?\s*$", blk, re.M)
        argv = [a or b for a, b in args]
        argv = [x.strip().strip("'\"") for x in argv if x and not x.startswith("serverName")]
        return (cmd.group(1).strip() if cmd else None), argv

    for server, key_init, key_tools, expect, w_init, w_tools in (
        ("seep", "B1", "B2", EXPECT_SEEP_TOOLS, 8, 10),
        ("js-reverse", "B3", "B4", EXPECT_JS_TOOLS, 6, 6),
    ):
        cmd, argv = extract(server)
        if not cmd:
            rep.add(G, key_init, "%s 能 initialize" % server, w_init, False,
                    "合成配置里找不到 %s" % server, "python setup/dsh-merge.py --profile web")
            rep.add(G, key_tools, "%s 工具数" % server, w_tools, False, "同上", "同上")
            continue

        tools, err = spawn_tools(cmd, argv)
        ok_init = tools is not None
        rep.add(G, key_init, "%s 能 initialize" % server, w_init, ok_init,
                "OK" if ok_init else err, "检查 %s 是否可执行/依赖是否齐全" % cmd)
        n = len(tools) if tools else 0
        rep.add(G, key_tools, "%s tools/list = %d 个工具" % (server, expect), w_tools, n >= expect,
                "实测 %d" % n, "工具数偏少通常意味着仓库不完整或启动的是旧副本")


def check_assets(rep):
    """第 3 组：仓库资产（20 分）"""
    G = "仓库资产"
    safe = os.path.join(ROOT, "Tool", "mcp", "Tool", "safe")
    need = ["jadx", "apktool", "radare2", "playwright-mcp", "js-reverse-mcp"]
    missing = [d for d in need if not os.path.isdir(os.path.join(safe, d))]
    rep.add(G, "C1", "内置二进制工具箱 5 件齐（jadx/apktool/radare2/playwright/js-reverse）", 6,
            not missing, "缺: %s" % ", ".join(missing) if missing else "全部在位",
            "重新克隆仓库；node_modules 由 install 解压")

    kb_root = os.path.join(ROOT, "Tool", "mcp", "Tool", "reverselab", "kb")
    kb = sum(1 for _, _, fs in os.walk(kb_root) for f in fs if f.endswith(".md")) if os.path.isdir(kb_root) else 0
    rep.add(G, "C2", "知识库 ≥ %d 篇" % EXPECT_KB, 5, kb >= EXPECT_KB, "实测 %d 篇" % kb,
            "重新克隆仓库")

    cases_dir = os.path.join(ROOT, "Tool", "cases")
    cases = len([d for d in os.listdir(cases_dir) if os.path.isdir(os.path.join(cases_dir, d))]) \
        if os.path.isdir(cases_dir) else 0
    rep.add(G, "C3", "脱敏案例 ≥ %d 个" % EXPECT_CASES, 3, cases >= EXPECT_CASES, "实测 %d 个" % cases,
            "重新克隆仓库")

    manuals_dir = os.path.join(ROOT, "MANUAL")
    manuals = len([f for f in os.listdir(manuals_dir) if f.endswith(".md")]) \
        if os.path.isdir(manuals_dir) else 0
    rep.add(G, "C4", "MANUAL/ 手册 ≥ %d 份" % EXPECT_MANUALS, 3, manuals >= EXPECT_MANUALS,
            "实测 %d 份" % manuals, "重新克隆仓库")

    skill_dir = os.path.join(ROOT, "Tool", "skill")
    names = set()
    if os.path.isdir(skill_dir):
        for d in os.listdir(skill_dir):
            p = os.path.join(skill_dir, d)
            if not os.path.isdir(p):
                continue
            if d == "safe-skills":
                names.update(x for x in os.listdir(p) if os.path.isdir(os.path.join(p, x)))
            elif d != "update":
                names.add(d)
    rep.add(G, "C5", "技能源目录 %d 个（DSH 不加载，但内容是纪律/知识的来源）" % EXPECT_SKILLS, 3,
            len(names) >= EXPECT_SKILLS, "实测 %d 个" % len(names), "重新克隆仓库")


def check_instructions(rep):
    """第 4 组：指令层（15 分）"""
    G = "指令层"
    root_agents = os.path.join(ROOT, "AGENTS.md")
    src_agents = os.path.join(ROOT, "Tool", "prompts", "AGENTS.md")
    has_root = os.path.isfile(root_agents)
    rep.add(G, "D1", "仓库根 AGENTS.md 存在（DSH 自动读取）", 5, has_root,
            root_agents, "python setup/generate-configs.py --root .")

    same = False
    if has_root and os.path.isfile(src_agents):
        same = io.open(root_agents, encoding="utf-8", errors="replace").read() == \
               io.open(src_agents, encoding="utf-8", errors="replace").read()
    rep.add(G, "D2", "根 AGENTS.md 与 Tool/prompts/AGENTS.md 一致（无漂移）", 5, same,
            "", "python setup/generate-configs.py --root .")

    system = os.path.join(ROOT, "Tool", "prompts", "SYSTEM.md")
    rep.add(G, "D3", "纪律文件 Tool/prompts/SYSTEM.md 存在（lab: 时要读的那份）", 5,
            os.path.isfile(system), system, "重新克隆仓库")


def check_runtime(rep):
    """第 5 组：运行时（10 分）"""
    G = "运行时"
    try:
        import tool_resolver as tr
        rep_tools = tr.external_tool_report(ROOT, verify=True)
        tools = rep_tools.get("tools", {})
    except Exception as exc:  # noqa: BLE001
        rep.add(G, "E1", "Python 能 import mcp", 6, False, "解析器不可用: %s" % exc, "")
        rep.add(G, "E2", "Node 可用", 4, False, "", "")
        return

    py = tools.get("python") or {}
    rep.add(G, "E1", "Python 能 import mcp（seep MCP 的运行时）", 6,
            py.get("state") == "READY", (py.get("detail") or "")[:80],
            py.get("fix") or "powershell -File setup\\install-python.ps1")

    node = tools.get("node") or {}
    rep.add(G, "E2", "Node 可用（js-reverse / playwright 的运行时）", 4,
            node.get("state") == "READY", (node.get("detail") or "")[:80],
            node.get("fix") or "安装 Node.js LTS")

    for tid in OPTIONAL_TOOLS:
        t = tools.get(tid)
        if t:
            rep.add_optional(tid, t.get("state"), (t.get("detail") or "")[:60], t.get("fix") or "")


# ---------------------------------------------------------------- 输出

def emit_text(rep, profile, composed_ok):
    print()
    print("=" * 78)
    print("  DeepSeek Harness 部署完整度校验  (profile=%s)" % profile)
    print("=" * 78)
    print("  仓库根 : %s" % ROOT)
    print("  DSH_HOME: %s" % dsh_home())
    if not composed_ok:
        print("  \033[33m[!] 无法读取合成配置，配置层相关项将计为失败\033[0m")
    print()

    group = None
    for it in rep.items:
        if it["group"] != group:
            group = it["group"]
            print("  【%s】" % group)
        mark = "\033[32m[PASS]\033[0m" if it["ok"] else "\033[31m[FAIL]\033[0m"
        print("   %s %-4s %-52s %2d 分" % (mark, it["key"], it["label"][:52], it["weight"]))
        if it["detail"]:
            print("           └─ %s" % it["detail"][:88])
        if not it["ok"] and it["fix"]:
            print("           └─ 修复: %s" % it["fix"][:88])
    print()

    if rep.optional:
        print("  【可选能力（不计入分母）】")
        for o in rep.optional:
            color = {"READY": "32", "DEGRADED": "33", "OPTIONAL": "90", "MISSING": "31"}.get(o["state"], "0")
            print("   \033[%sm%-9s\033[0m %-16s %s" % (color, o["state"], o["label"], o["detail"]))
        print()

    rate = rep.rate
    bar_len = 40
    filled = int(round(rate / 100.0 * bar_len))
    bar = "█" * filled + "░" * (bar_len - filled)
    color = "32" if rate >= 100 else ("33" if rate >= 85 else "31")
    print("-" * 78)
    print("  完整率  \033[%sm%s\033[0m  %5.1f%%   (%d / %d 分)" % (color, bar, rate, rep.earned, rep.total))
    print("-" * 78)

    failed = [i for i in rep.items if not i["ok"]]
    if failed:
        print("  缺失清单（%d 项）:" % len(failed))
        for it in failed:
            print("    · [%s] %s" % (it["key"], it["label"]))
        print()
        print("  \033[33m注意：本表的分母是「DSH 上应该有什么」，不含 skill。\033[0m")
        print("  DSH 没有 skill 加载器，10 个 skill 不参与计分；它们的价值通过")
        print("  AGENTS.md + Tool/prompts/SYSTEM.md 的指令层体现（见第 4 组）。")
    else:
        print("  \033[32m全部通过。但这个分数只说明「配置与资产就位」，\033[0m")
        print("  \033[32m不代表模型会遵守 lab: 闸门 —— 那是指令层的事，需人工抽验。\033[0m")
    print()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="DSH 部署完整度校验")
    ap.add_argument("--profile", default="web")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--skip-spawn", action="store_true", help="不真启动 MCP（快，但 B 组计为失败）")
    args = ap.parse_args(argv)

    dsh = find_dsh()
    if not dsh and not args.json:
        print("[WARN] PATH 里找不到 dsh，合成配置无法读取（配置层会全部计失败）")

    composed = ""
    composed_ok = False
    if dsh:
        rc, out, err = run([dsh, "--profile", args.profile, "--dump-config"], timeout=120)
        if rc == 0 and out.strip():
            composed = out
            composed_ok = True

    rep = Report()
    check_config(rep, args.profile, composed)
    check_mcp(rep, composed, args.skip_spawn or not composed_ok)
    check_assets(rep)
    check_instructions(rep)
    check_runtime(rep)

    if args.json:
        payload = {
            "profile": args.profile,
            "repo_root": ROOT,
            "dsh_home": dsh_home(),
            "composed_ok": composed_ok,
            "score": {"earned": rep.earned, "total": rep.total, "rate": round(rep.rate, 1)},
            "items": rep.items,
            "missing": [i["key"] for i in rep.items if not i["ok"]],
            "optional": rep.optional,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        emit_text(rep, args.profile, composed_ok)

    if not dsh:
        return 2
    return 1 if any(not i["ok"] for i in rep.items) else 0


if __name__ == "__main__":
    sys.exit(main())
