#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DeepSeek Harness 部署完整度校验

回答一个问题：**工作台在 DSH 上到底部署全了没有，缺什么。**

分母不是「pi 上有什么」，而是「DSH 上本来应该有什么」：
DSH 自带技能机制（dsh-skill + dsh-skill-filesystem + dsh-tool-skill），
格式与 pi 一致（<name>/SKILL.md + frontmatter），所以 10 个技能计入分母。

1.14.0 起接线改由插件包完成：DSH 里的「设置 → 插件」填路径，
插件在运行时挂 MCP 与技能，并把结果写到 $DSH_HOME/seep-workbench.status.json。
本脚本读那份状态文件，而不是去猜合成配置。

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

OPTIONAL_TOOLS = ["ida", "playwright", "ffmpeg", "frida", "apkid", "aotopsy"]

PLUGIN_PKG = "seep-dsh-workbench"   # 插件包名
STATUS_FILE = "seep-workbench.status.json"


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


def profile_dir(profile):
    return os.path.join(dsh_home(), "profiles", profile)


def plugin_installed(profile):
    """插件包是否已装进这个 profile（新路线的唯一判据）。"""
    pj = os.path.join(profile_dir(profile), "package.json")
    if not os.path.isfile(pj):
        return False
    try:
        data = json.loads(io.open(pj, encoding="utf-8", errors="replace").read())
    except (ValueError, OSError):
        return False
    bundles = (((data.get("dsh") or {}).get("profile") or {}).get("bundles")) or []
    return PLUGIN_PKG in bundles


def read_status():
    """读插件写出的状态文件。插件没跑过就没这个文件。"""
    p = os.path.join(dsh_home(), STATUS_FILE)
    if not os.path.isfile(p):
        return None
    try:
        st = json.loads(io.open(p, encoding="utf-8", errors="replace").read())
    except (ValueError, OSError):
        return None
    if not isinstance(st, dict):
        return None
    st["_path"] = p
    return st


def same_path(a, b):
    if not a or not b:
        return False
    na = os.path.normcase(os.path.normpath(str(a)))
    nb = os.path.normcase(os.path.normpath(str(b)))
    return na == nb


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

def check_config(rep, profile, status):
    """第 1 组：DSH 配置层（20 分）

    1.14.0 起接线不走「往 profile patch 里塞条目」，而是装一个插件包：
    包本身 declare 接线方式，路径在设置面板里填。所以这一组查的是：
    包装了没、跑过没、指向对不对、lab 开关开没开。
    """
    G = "配置层"
    installed = plugin_installed(profile)

    # A1 插件包已装进 profile
    rep.add(G, "A1", "插件包 %s 已装进 profile" % PLUGIN_PKG, 7, installed,
            "dsh.profile.bundles 含 %s" % PLUGIN_PKG if installed
            else "未装；旧路线的 marker 块不算数（两种路线同时用会挂两份 MCP）",
            "dsh plugin --profile %s add file:<仓库>/packages/dsh-workbench" % profile)

    # A2 插件跑过（有状态文件）
    rep.add(G, "A2", "插件已启动并写出状态文件", 4, bool(status),
            status["_path"] if status else "没找到 %s" % os.path.join(dsh_home(), STATUS_FILE),
            "启动一次 dsh --profile %s，再重新跑本脚本" % profile)

    # A3 状态 ok 且指向当前仓库
    repo_root = (status or {}).get("repoRoot") or ""
    ok3 = bool(status) and status.get("ok") is True and same_path(repo_root, ROOT)
    rep.add(G, "A3", "状态 ok 且路径指向当前仓库", 3, ok3,
            "repoRoot=%s, ok=%s" % (repo_root or "空", (status or {}).get("ok")),
            "在 DSH 设置 → 插件 → seep-workbench-boot 里把路径改成：%s" % ROOT)

    # A4 lab 开关
    lab = (status or {}).get("labGate")
    rep.add(G, "A4", "lab 开关已启用（只在 lab： 之后注入纪律）", 3, lab is True,
            "labGate=%s" % lab,
            "设置 → 插件 → seep-workbench-boot → lab 开关 打开")

    # A5 面板：包声明了 dsh.client 且 client 入口存在
    pkg_dir = os.path.join(ROOT, "packages", "dsh-workbench")
    client_entry = os.path.join(pkg_dir, "lib", "client.js")
    declared = False
    pj = os.path.join(pkg_dir, "package.json")
    if os.path.isfile(pj):
        try:
            manifest = json.loads(io.open(pj, encoding="utf-8", errors="replace").read())
            declared = bool((manifest.get("dsh") or {}).get("client"))
        except (ValueError, OSError):
            declared = False
    rep.add(G, "A5", "设置面板已声明（dsh.client + lib/client.js）", 3,
            declared and os.path.isfile(client_entry),
            "声明=%s, client.js=%s" % (declared, os.path.isfile(client_entry)),
            "重新 clone 仓库；面板文件在 packages/dsh-workbench/lib/client.js")

    # A8 装进 profile 的那份 client.js 必须和仓库一致。
    #
    # 为什么需要这条：pnpm 的 file: 安装本来靠硬链接，改仓库即生效。
    # 但只要有人用 `git checkout -- <文件>` 还原过一次，硬链接就被切断，
    # profile 里变成一份**不会再更新的副本** —— 于是"我改了代码却没反应"，
    # 排查半天。这条把它变成一眼可见的红灯。
    installed = os.path.join(profile_dir(profile), "node_modules", "seep-dsh-workbench")
    installed_client = os.path.join(installed, "lib", "client.js")
    drift = ""
    if not os.path.isfile(installed_client):
        drift = "profile 里没有 client.js（插件没装进 profile）"
    elif not os.path.isfile(client_entry):
        drift = "仓库里没有 client.js"
    else:
        try:
            a = io.open(installed_client, "rb").read()
            b = io.open(client_entry, "rb").read()
            if a != b:
                drift = "profile 里的插件与仓库代码不一致（本地装法多是硬链接断了）"
        except OSError as exc:
            drift = "读不到文件：%s" % exc
    rep.add(G, "A8", "装进 profile 的插件与仓库代码一致（没被旧副本卡住）", 2, not drift,
            drift or "一致",
            "python setup/dsh-plugin-setup.py --root . 重装插件，恢复硬链接")

    # 旧路线残留：不扣分，但会重复挂载
    patch = os.path.join(profile_dir(profile), "cordis.patch.yml")
    body = ""
    if os.path.isfile(patch):
        body = io.open(patch, encoding="utf-8", errors="replace").read()
    legacy = ">>> seep-workbench" in body
    rep.add(G, "A6", "没有旧路线残留（两条路线同时用会挂两份 MCP）", 3, not legacy,
            "profile patch 里还有 dsh-merge.py 的 marker 块" if legacy else "干净",
            "重跑 python setup/dsh-plugin-setup.py（会自动清掉旧块）")


def check_lab_gate(rep):
    """第 1 组附加：lab 开关的单测。

    lab 是「会话级、默认关、只认指令」三件事，光看状态文件里的 labGate=true
    说明不了它真的这么工作。这里直接跑仓库里的单测（纯 JS 逻辑，不需要 DSH）。
    """
    G = "配置层"
    test = os.path.join(ROOT, "packages", "dsh-workbench", "test", "lab-gate.test.mjs")
    if not os.path.isfile(test):
        rep.add(G, "A7", "lab 开关单测通过（会话级 / 默认关 / 只认指令）", 4, False,
                "缺 %s" % test, "重新 clone 仓库")
        return
    node = shutil.which("node") or shutil.which("node.exe")
    if not node:
        rep.add(G, "A7", "lab 开关单测通过（会话级 / 默认关 / 只认指令）", 4, False,
                "PATH 里找不到 node", "安装 Node.js LTS")
        return
    rc, out, err = run([node, test], timeout=120)
    passed = rc == 0
    tail = [ln.strip() for ln in (out or "").splitlines() if ln.strip()]
    summary = tail[-1] if tail else (err or "").strip()[:100]
    rep.add(G, "A7", "lab 开关单测通过（会话级 / 默认关 / 只认指令）", 4, passed,
            summary[:90], "node packages/dsh-workbench/test/lab-gate.test.mjs 看具体哪条挂了")


def check_mcp(rep, status, skip_spawn):
    """第 2 组：MCP 可用性（25 分）

    命令和参数从插件写出的状态文件里取 —— 校验的就是插件真正会启动的东西，
    而不是从 YAML 里猜。
    """
    G = "MCP 可用性"

    if not status or not status.get("repoRoot"):
        for key, label, w in (("B1", "seep 能 initialize", 6), ("B2", "seep 工具数", 7),
                              ("B3", "js-reverse 能 initialize", 5), ("B4", "js-reverse 工具数", 4)):
            rep.add(G, key, label, w, False, "插件还没跑过 / 没填路径",
                    "先跑 setup/verify-dsh.py 的 A2、A3 两项")
        return

    if skip_spawn:
        for key, label, w in (("B1", "seep 能 initialize", 6), ("B2", "seep 工具数", 7),
                              ("B3", "js-reverse 能 initialize", 5), ("B4", "js-reverse 工具数", 4)):
            rep.add(G, key, label, w, False, "已跳过（--skip-spawn）", "去掉 --skip-spawn 重跑")
        return

    root = status["repoRoot"]
    py = status.get("python") or "python"
    entry = os.path.join(root, "Tool", "mcp", "seep_mcp_server.py")

    for server, cmd, argv, key_init, key_tools, expect, w_init, w_tools in (
        ("seep", py, [entry], "B1", "B2", EXPECT_SEEP_TOOLS, 6, 7),
        ("js-reverse", "npx", ["-y", "js-reverse-mcp"], "B3", "B4", EXPECT_JS_TOOLS, 5, 4),
    ):
        tools, err = spawn_tools(cmd, argv)
        ok_init = tools is not None
        rep.add(G, key_init, "%s 能 initialize" % server, w_init, ok_init,
                "OK" if ok_init else err, "检查 %s 是否可执行/依赖是否齐全" % cmd)
        n = len(tools) if tools else 0
        rep.add(G, key_tools, "%s tools/list = %d 个工具" % (server, expect), w_tools, n >= expect,
                "实测 %d" % n, "工具数偏少通常意味着仓库不完整或启动的是旧副本")


def check_skills(rep, status):
    """第 3 组：技能层（15 分）

    DSH 自带 skill 机制（dsh-skill / dsh-skill-filesystem / dsh-tool-skill），
    bundle 格式与 pi 一致，所以 10 个技能是能真的被 DSH 看到的。
    web profile 默认把后面两个关掉，插件负责在运行时打开并指到两个技能根。
    """
    G = "技能层"

    enabled = (status or {}).get("skillsEnabled") is True
    mounted = bool(((status or {}).get("mounted") or {}).get("skills"))

    # 光看 mounted.skills 只说明「调了 ctx.plugin」，不等于技能真的注册上了。
    # 插件会在运行时问一次技能注册表，把结果写进 status.skills。
    # 注册表里除我们的 10 个，还会有 DSH 自带的（沙箱诊断等），所以只要求我们的都在。
    runtime = ((status or {}).get("skills") or {})
    seen = set(runtime.get("names") or [])

    # 配了外置内容目录时，技能是从那边挂的，仓库自带的根本没装 ——
    # 这时候拿仓库的技能名去比，会冤枉成「没注册」。
    content_root = ((status or {}).get("content") or {}).get("root") or ""
    expected = set()
    roots = (
        [os.path.join(content_root, "skill"), os.path.join(content_root, "safe-skills")]
        if content_root
        else [os.path.join(ROOT, *rel.split("/")) for rel in ("Tool/skill", "Tool/skill/safe-skills")]
    )
    for d in roots:
        if not os.path.isdir(d):
            continue
        for child in os.listdir(d):
            md = os.path.join(d, child, "SKILL.md")
            if not os.path.isfile(md):
                continue
            name = child
            try:
                body = io.open(md, encoding="utf-8", errors="replace").read(2000)
                m = re.search(r"^name:\s*(.+)$", body, re.M)
                if m:
                    name = m.group(1).strip()
            except OSError:
                pass
            expected.add(name)

    missing = sorted(expected - seen)
    registered = enabled and mounted and bool(seen) and not missing

    if not seen:
        detail = "状态文件里没有 skills 字段（插件没探测成功）"
    elif missing:
        detail = "注册表 %d 个，缺：%s" % (len(seen), ", ".join(missing[:4]))
    else:
        where = "内容目录" if content_root else "仓库"
        detail = "注册表 %d 个（%s %d 个全在）" % (len(seen), where, len(expected))

    rep.add(G, "F1", "技能真的注册进 DSH 注册表（不只是挂了个插件）", 5, registered, detail,
            "重启 DSH；仍有缺失看 dsh 启动日志里的 [seep-workbench] 技能行")

    found = 0
    for rel in ("Tool/skill", "Tool/skill/safe-skills"):
        d = os.path.join(ROOT, *rel.split("/"))
        if os.path.isdir(d):
            for child in os.listdir(d):
                if os.path.isfile(os.path.join(d, child, "SKILL.md")):
                    found += 1
    rep.add(G, "F2", "仓库里可发现 ≥ %d 个技能" % EXPECT_SKILLS, 6, found >= EXPECT_SKILLS,
            "实测 %d 个" % found, "重新克隆仓库；技能包格式：<名称>/SKILL.md + frontmatter")

    roots = all(os.path.isdir(os.path.join(ROOT, *rel.split("/")))
                for rel in ("Tool/skill", "Tool/skill/safe-skills"))
    rep.add(G, "F3", "两个技能根都在仓库里", 4, roots,
            "Tool/skill 与 Tool/skill/safe-skills", "重新克隆仓库")


def check_optional_mcp(rep, status):
    """可选的第二个 MCP（ida / playwright）：挂了就报 READY，没开就说清楚。

    不计分：这两个是「有更好」，缺了不影响 seep 本身。
    """
    status = status or {}
    mounted = status.get("mounted") or {}
    wanted = status.get("optionalMcp") or {}

    plugin = status.get("plugin") or {}
    if plugin:
        rep.add_optional("插件来源", "READY" if plugin.get("updatable") else "OPTIONAL",
                         "安装方式", "%s（%s）" % (plugin.get("mode", "-"), plugin.get("spec", "")))

    lab = status.get("lab") or {}
    if lab:
        rep.add_optional("lab 运行状态", "READY" if lab.get("enabled") else "OPTIONAL", "lab 总闸",
                         "开（%s）" % ("当前已进入" if lab.get("injecting") else "当前未进入")
                         if lab.get("enabled") else "关（连 lab： 口令也不认）")

    for key, label, hint in (
        ("playwright", "playwright", "python setup/dsh-plugin-setup.py --with-playwright"),
        ("ida", "ida", "python setup/dsh-plugin-setup.py --with-ida"),
    ):
        if mounted.get(key):
            rep.add_optional("可选 MCP", "READY", label, "已在 DSH 里挂上")
        elif wanted.get(key):
            rep.add_optional("可选 MCP", "DEGRADED", label,
                             "配置里开了但没挂上（看 dsh 启动日志的 [seep-workbench] 提示）")
        else:
            rep.add_optional("可选 MCP", "OPTIONAL", label, "没开；要挂：%s" % hint)


def check_assets(rep):
    """第 3 组：仓库资产（20 分）"""
    G = "仓库资产"
    safe = os.path.join(ROOT, "Tool", "mcp", "Tool", "safe")
    need = ["jadx", "apktool", "radare2", "playwright-mcp", "js-reverse-mcp"]
    missing = [d for d in need if not os.path.isdir(os.path.join(safe, d))]
    rep.add(G, "C1", "内置二进制工具箱 5 件齐（jadx/apktool/radare2/playwright/js-reverse）", 5,
            not missing, "缺: %s" % ", ".join(missing) if missing else "全部在位",
            "重新克隆仓库；node_modules 由 install 解压")

    kb_root = os.path.join(ROOT, "Tool", "mcp", "Tool", "reverselab", "kb")
    kb = sum(1 for _, _, fs in os.walk(kb_root) for f in fs if f.endswith(".md")) if os.path.isdir(kb_root) else 0
    rep.add(G, "C2", "知识库 ≥ %d 篇" % EXPECT_KB, 3, kb >= EXPECT_KB, "实测 %d 篇" % kb,
            "重新克隆仓库")

    cases_dir = os.path.join(ROOT, "Tool", "cases")
    cases = len([d for d in os.listdir(cases_dir) if os.path.isdir(os.path.join(cases_dir, d))]) \
        if os.path.isdir(cases_dir) else 0
    rep.add(G, "C3", "脱敏案例 ≥ %d 个" % EXPECT_CASES, 2, cases >= EXPECT_CASES, "实测 %d 个" % cases,
            "重新克隆仓库")

    manuals_dir = os.path.join(ROOT, "MANUAL")
    manuals = len([f for f in os.listdir(manuals_dir) if f.endswith(".md")]) \
        if os.path.isdir(manuals_dir) else 0
    rep.add(G, "C4", "MANUAL/ 手册 ≥ %d 份" % EXPECT_MANUALS, 2, manuals >= EXPECT_MANUALS,
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
    rep.add(G, "C5", "技能源目录 %d 个（内容质量的基础）" % EXPECT_SKILLS, 1,
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
    rep.add(G, "D3", "纪律文件 Tool/prompts/SYSTEM.md 存在（lab: 时要读的那份）", 3,
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
        print("  \033[33m注意：本表的分母是「DSH 上应该有什么」，不是「pi 上有什么」。\033[0m")
        print("  长任务超时、cwd、failOnStartupError 这些接线细节现在由插件负责，")
        print("  不再体现在合成配置里 —— 所以本表不查它们，改查状态文件的 mounted 标记。")
    else:
        print("  \033[32m全部通过。但这个分数只说明「接线与资产就位」，\033[0m")
        print("  \033[32m不代表模型会遵守 lab： 闸门 —— 那要靠实际发一条消息抽验。\033[0m")
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
    status = read_status()
    check_config(rep, args.profile, status)
    check_mcp(rep, status, args.skip_spawn)
    check_lab_gate(rep)
    check_skills(rep, status)
    check_optional_mcp(rep, status)
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
