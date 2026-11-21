#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 Seep 工作台接进 Antigravity（agy）。

Antigravity 认三样东西，我们对应接三条线：

  1. 规则  —— 仓库根的 AGENTS.md
      agy 会从当前文件往上走到仓库根，自动加载途中所有 AGENTS.md / GEMINI.md。
      这一条零配置：仓库里已经有 AGENTS.md，打开仓库就生效。

  2. 技能  —— ~/.gemini/config/skills.json
      `entries` 里写目录路径，每条只扫一层。我们给两组：
        Tool/skill          → softseep / apkseep / exe-reverse / webseep / license-bypass
        Tool/skill/safe-skills → 5 个独立战术包

  3. MCP   —— ~/.gemini/config/mcp_config.json
      有 agy 命令时走官方 `agy mcp add`（它会自己校验并热加载）；
      没有 agy 命令时直接合并 JSON。

  4. 钩子  —— <仓库>/.agents/hooks.json（可选，--with-hooks）
      agy 的 SessionStart / PreInvocation / PostToolUse 三个事件，
      分别做「开场说明」「lab 闸门 + 术语对照」「审计流水」。
      agy 没有运行时改写钩子，所以这里只注入 systemMessage，不改用户原话。

用法：
  python setup/agy-setup.py                     # 默认：seep + js-reverse + 技能
  python setup/agy-setup.py --dry-run           # 只看会改什么，不落盘
  python setup/agy-setup.py --list              # 只看现状
  python setup/agy-setup.py --with-playwright   # 再把 playwright 挂上
  python setup/agy-setup.py --with-ida          # 再把 IDA 挂上（需本机有 IDA）
  python setup/agy-setup.py --no-skills         # 只接 MCP，不碰技能
  python setup/agy-setup.py --root <仓库路径>    # 仓库不在默认位置时
  python setup/agy-setup.py --ida-root <IDA目录>

装完重启 Antigravity（或新建会话）才生效。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# -----------------------------------------------------------------------------
# 常量
# -----------------------------------------------------------------------------

MCP_NAMES = ("seep", "js-reverse", "playwright", "ida")

# 与 setup/tool-registry.json 里 python 那条的 candidates 保持一致
PY_CANDIDATES = (
    "~/.pi/agent/seep-venv/Scripts/python.exe",
    "~/.pi/agent/seep-venv/bin/python",
    "%LOCALAPPDATA%/Programs/Python/Python312/python.exe",
    "%LOCALAPPDATA%/Programs/Python/Python311/python.exe",
)

IDA_CANDIDATES = (
    "%ProgramFiles%/IDA Pro",
    "%ProgramFiles%/IDA Professional 9.0",
    "%ProgramFiles%/IDA Pro 9.4",
    "%ProgramFiles%/IDA Professional 9.4",
    "%ProgramFiles%/IDA Free",
    "D:/Tool/IDA Pro",       # 与 setup/tool-registry.json 的 candidates 保持同一份
    "C:/IDA Pro",
    "C:/IDA",
    "D:/IDA Pro",
    "D:/IDA",
    "E:/IDA Pro",
    "F:/IDA Pro",
)

WIN = os.name == "nt"
EXE = ".exe" if WIN else ""
SEP = "\\" if WIN else "/"


# -----------------------------------------------------------------------------
# 小工具
# -----------------------------------------------------------------------------

def expand(p: str) -> str:
    """展开 ~ 和 %VAR% / $VAR。"""
    if not p:
        return p
    s = os.path.expandvars(os.path.expanduser(p))
    return s.replace("\\", "/") if WIN else s


def norm(p: str) -> str:
    """比较用的规范形式：绝对路径、正斜杠、小写（Windows 大小写不敏感）。"""
    s = expand(p).replace("\\", "/").rstrip("/")
    return s.lower() if WIN else s


def say(msg: str = "") -> None:
    print(msg)


def step(msg: str) -> None:
    print(f"\n{msg}")


def ok(msg: str) -> None:
    print(f"  [ok] {msg}")


def skip(msg: str) -> None:
    print(f"  [--] {msg}")


def warn(msg: str) -> None:
    print(f"  [!] {msg}")


def fail(msg: str) -> None:
    print(f"  [X] {msg}")


def repo_root(cli_root: str | None) -> Path:
    if cli_root:
        return Path(expand(cli_root)).resolve()
    return Path(__file__).resolve().parent.parent


def agy_home() -> Path:
    """agy 的全局配置目录。官方文档：~/.gemini/config/"""
    override = os.environ.get("SEEP_AGY_CONFIG")
    if override:
        return Path(expand(override))
    return Path(os.path.expanduser("~/.gemini/config"))


def read_json(p: Path) -> dict:
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def write_json(p: Path, data: dict, dry: bool, label: str) -> bool:
    """写 JSON。有变化才写，写前备份。返回是否真的写了。"""
    old = p.read_text(encoding="utf-8") if p.exists() else ""
    new = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    if old == new:
        return False
    if dry:
        print(f"  [dry-run] 会写入 {label}：{p}")
        return False
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        shutil.copy2(p, str(p) + ".bak")
    p.write_text(new, encoding="utf-8", newline="\n")
    ok(f"已写入 {label}（旧文件备份为 {p.name}.bak）")
    return True


def run(cmd: list[str], timeout: int = 120) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True,
                           encoding="utf-8", errors="replace",
                           timeout=timeout, shell=False)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except FileNotFoundError:
        return 127, "command not found"
    except subprocess.TimeoutExpired:
        return 124, "timeout"


# -----------------------------------------------------------------------------
# 找 agy / python / ida
# -----------------------------------------------------------------------------

def find_agy(cli: str | None) -> str | None:
    if cli:
        return expand(cli)
    env = os.environ.get("SEEP_AGY")
    if env:
        return expand(env)
    found = shutil.which("agy")
    if found:
        return found
    cand = expand("%LOCALAPPDATA%/agy/bin/agy" + EXE)
    if os.path.isfile(cand):
        return cand
    return None


def can_import_mcp(python: str) -> bool:
    code, _ = run([python, "-c", "import mcp"], timeout=25)
    return code == 0


def resolve_python() -> str | None:
    env = expand(os.environ.get("SEEP_PYTHON", ""))
    if env and os.path.isfile(env) and can_import_mcp(env):
        return env
    for c in PY_CANDIDATES:
        p = expand(c)
        if os.path.isfile(p) and can_import_mcp(p):
            return p
    for name in ("python3", "python"):
        found = shutil.which(name)
        if found and can_import_mcp(found):
            return found
    return None


def resolve_ida(cli_root: str | None) -> tuple[str, str] | None:
    roots: list[str] = []
    if cli_root:
        roots.append(cli_root)
    env = os.environ.get("SEEP_IDA_ROOT")
    if env:
        roots.append(expand(env))
    roots.extend(expand(c) for c in IDA_CANDIDATES)

    for root in roots:
        py = os.path.join(root, "python311", "python" + EXE)
        server = os.path.join(root, "python311", "Lib", "site-packages",
                              "ida_pro_mcp", "server.py")
        if os.path.isfile(py) and os.path.isfile(server):
            return py.replace("\\", "/"), server.replace("\\", "/")
    return None


# -----------------------------------------------------------------------------
# MCP 接线
# -----------------------------------------------------------------------------

def desired_servers(root: Path, py: str, with_playwright: bool,
                    with_ida: bool, ida_root: str | None) -> dict:
    """要挂的 server 定义。结构同 mcp_config.json。"""
    server_py = (root / "Tool" / "mcp" / "seep_mcp_server.py").as_posix()
    out: dict[str, dict] = {
        "seep": {
            "command": py.replace("\\", "/"),
            "args": [server_py],
            "env": {"PYTHONIOENCODING": "utf-8"},
        },
        "js-reverse": {
            "command": "npx",
            "args": ["-y", "js-reverse-mcp"],
        },
    }
    if with_playwright:
        out["playwright"] = {
            "command": "npx",
            "args": ["-y", "@playwright/mcp@latest"],
        }
    if with_ida:
        ida = resolve_ida(ida_root)
        if ida:
            py_ida, server = ida
            out["ida"] = {
                "command": py_ida,
                "args": [server],
                "env": {"PYTHONIOENCODING": "utf-8"},
            }
    return out


def mcp_via_cli(agy: str, servers: dict, existing: dict, dry: bool,
                force: bool) -> None:
    """走官方 `agy mcp add`。已存在且没 --force 的不动（保住用户自己的参数）。"""
    for name, spec in servers.items():
        if name in existing and not force:
            skip(f"{name} 已经在了，保持原样（要覆盖加 --force）")
            continue
        cmd = [agy, "mcp", "add"]
        for k, v in (spec.get("env") or {}).items():
            cmd += ["--env", f"{k}={v}"]
        cmd += [name, spec["command"], *spec.get("args", [])]
        if dry:
            print(f"  [dry-run] 会执行：agy mcp add {name} {spec['command']}")
            continue
        code, out = run(cmd)
        if code == 0:
            ok(f"{name} 已挂上")
        else:
            fail(f"{name} 挂载失败：{out.strip()[:200]}")


def mcp_via_json(cfg_path: Path, servers: dict, existing: dict, dry: bool,
                 force: bool) -> bool:
    """没有 agy 命令时的退路：直接合并 JSON。"""
    data = read_json(cfg_path) or {"mcpServers": {}}
    data.setdefault("mcpServers", {})
    changed = False
    for name, spec in servers.items():
        if name in data["mcpServers"] and not force:
            skip(f"{name} 已经在了，保持原样（要覆盖加 --force）")
            continue
        entry = {"command": spec["command"], "args": spec.get("args", [])}
        if spec.get("env"):
            entry["env"] = spec["env"]
        entry["disabled"] = False
        data["mcpServers"][name] = entry
        changed = True
        ok(f"{name} 已写入配置")
    if changed:
        write_json(cfg_path, data, dry, "MCP 配置")
    return changed


# -----------------------------------------------------------------------------
# 技能接线
# -----------------------------------------------------------------------------

def skill_entries(root: Path) -> list[dict]:
    """两条：主技能目录 + safe-skills 子目录。每条只扫一层。"""
    return [
        {
            "path": (root / "Tool" / "skill").as_posix(),
            "exclude": ["^safe-skills$"],
        },
        {
            "path": (root / "Tool" / "skill" / "safe-skills").as_posix(),
        },
    ]


def install_skills(root: Path, cfg_dir: Path, dry: bool) -> bool:
    p = cfg_dir / "skills.json"
    data = read_json(p) or {}
    entries = data.get("entries")
    if not isinstance(entries, list):
        entries = []

    wanted = skill_entries(root)
    wanted_paths = {norm(e["path"]) for e in wanted}
    kept = [e for e in entries
            if isinstance(e, dict) and norm(e.get("path", "")) not in wanted_paths]

    # 已经被别的 skills.json 引用过的同名目录不重复写
    data["entries"] = kept + wanted
    return write_json(p, data, dry, "技能清单")


def hooks_config(py: str, root: Path) -> dict:
    """生成 hooks.json。python 用绝对路径 —— cmd/sh 里 PATH 上的 python 不可靠。"""
    q = '"' + py.replace("\\", "/") + '"'
    rel = root / ".agents"  # 钩子命令的工作目录就是 hooks.json 所在目录
    del rel
    return {
        "seep-session-start": {
            "SessionStart": [
                {"type": "command", "command": f"{q} hooks/session_start.py", "timeout": 20}
            ]
        },
        "seep-lab-gate": {
            "PreInvocation": [
                {"type": "command", "command": f"{q} hooks/pre_invocation.py", "timeout": 20}
            ]
        },
        "seep-audit-trail": {
            "PostToolUse": [
                {"matcher": "*",
                 "hooks": [{"type": "command", "command": f"{q} hooks/post_tool_use.py", "timeout": 20}]}
            ]
        },
    }


def install_hooks(root: Path, py: str, dry: bool) -> bool:
    """写 <仓库>/.agents/hooks.json（本仓库 = 工作区，agy 打开它就会读）。"""
    agents = root / ".agents"
    if not (agents / "hooks").is_dir():
        warn(f"缺目录 {agents / 'hooks'}，跳过钩子")
        return False
    return write_json(agents / "hooks.json", hooks_config(py, root), dry, "钩子配置")


def count_skills(root: Path) -> int:
    n = 0
    for d in (root / "Tool" / "skill").iterdir() if (root / "Tool" / "skill").is_dir() else []:
        if d.is_dir() and d.name != "safe-skills" and (d / "SKILL.md").is_file():
            n += 1
    safe = root / "Tool" / "skill" / "safe-skills"
    if safe.is_dir():
        for d in safe.iterdir():
            if d.is_dir() and (d / "SKILL.md").is_file():
                n += 1
    return n


# -----------------------------------------------------------------------------
# 现状
# -----------------------------------------------------------------------------

def show_status(root: Path, agy: str | None, cfg_dir: Path) -> None:
    step("现状")
    print(f"  仓库       : {root}")
    print(f"  agy 命令   : {agy or '没找到（会退化成直接改 JSON）'}")
    print(f"  配置目录   : {cfg_dir}")

    rule = root / "AGENTS.md"
    print(f"  规则入口   : {'AGENTS.md 在' if rule.is_file() else 'AGENTS.md 缺失'}"
          f"（agy 自动加载，无需配置）")

    mcp = read_json(cfg_dir / "mcp_config.json").get("mcpServers") or {}
    if mcp:
        print("  MCP 已挂  :")
        for name, spec in mcp.items():
            if name not in MCP_NAMES and not isinstance(spec, dict):
                continue
            cmd = spec.get("command") or spec.get("url") or "?"
            state = "disabled" if spec.get("disabled") else "enabled"
            print(f"      - {name:<12} {state:<9} {cmd}")
    else:
        print("  MCP 已挂  : （空）")

    skills = read_json(cfg_dir / "skills.json").get("entries") or []
    ours = [e for e in skills if isinstance(e, dict)
            and "seep" in norm(e.get("path", "")).lower()]
    print(f"  技能已挂  : {len(ours)} 条（仓库里有 {count_skills(root)} 个 SKILL.md）")
    for e in ours:
        print(f"      - {e.get('path')}")


# -----------------------------------------------------------------------------
# 主流程
# -----------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description="把 Seep 工作台接进 Antigravity（agy）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="装完重启 Antigravity（或新建会话）才生效。",
    )
    ap.add_argument("--root", help="仓库路径（默认：脚本的上级目录）")
    ap.add_argument("--agy", help="agy 可执行文件路径（默认自动找）")
    ap.add_argument("--dry-run", action="store_true", help="只看会改什么")
    ap.add_argument("--list", action="store_true", help="只看现状后退出")
    ap.add_argument("--no-skills", action="store_true", help="不写技能清单")
    ap.add_argument("--with-playwright", action="store_true", help="额外挂 playwright")
    ap.add_argument("--with-ida", action="store_true", help="额外挂 IDA（需本机有 IDA）")
    ap.add_argument("--ida-root", help="IDA 安装目录")
    ap.add_argument("--force", action="store_true", help="已存在的 server 也覆盖")
    ap.add_argument("--with-hooks", action="store_true",
                    help="生成 .agents/hooks.json（lab 闸门 + 审计流水）")
    ap.add_argument("--no-hooks", action="store_true", help="不生成钩子配置")
    args = ap.parse_args()

    root = repo_root(args.root)
    cfg_dir = agy_home()
    agy = find_agy(args.agy)

    if not (root / "Tool" / "mcp" / "seep_mcp_server.py").is_file():
        fail(f"这个目录不像 Seep 仓库：{root}")
        print("     用 --root <仓库路径> 指一下。")
        return 2

    if args.list:
        show_status(root, agy, cfg_dir)
        return 0

    step("1) 规则层")
    if (root / "AGENTS.md").is_file():
        ok("仓库根有 AGENTS.md —— agy 打开仓库就自动加载，这一层不用配置")
    else:
        warn("仓库根没有 AGENTS.md（先跑 python setup/generate-configs.py）")

    step("2) MCP 层")
    py = resolve_python()
    if not py:
        fail("找不到能 import mcp 的 python")
        print("     fix: powershell -File setup\\install-python.ps1")
        return 2
    ok(f"python: {py}")

    servers = desired_servers(root, py, args.with_playwright, args.with_ida,
                              args.ida_root)
    if args.with_ida and "ida" not in servers:
        warn("没找到 IDA，跳过（用 --ida-root 指定安装目录）")

    existing = (read_json(cfg_dir / "mcp_config.json").get("mcpServers") or {})
    if agy:
        mcp_via_cli(agy, servers, existing, args.dry_run, args.force)
    else:
        mcp_via_json(cfg_dir / "mcp_config.json", servers, existing,
                     args.dry_run, args.force)

    step("3) 技能层")
    if args.no_skills:
        skip("按 --no-skills 跳过")
    else:
        n = count_skills(root)
        if install_skills(root, cfg_dir, args.dry_run):
            ok(f"{n} 个技能已列进 skills.json")
        else:
            skip(f"skills.json 已经是这个样子（{n} 个技能）")

    step("4) 钩子层")
    if args.no_hooks:
        skip("按 --no-hooks 跳过")
    elif args.with_hooks:
        if install_hooks(root, py, args.dry_run):
            ok("钩子已生成：lab 闸门 + 审计流水")
        else:
            skip(".agents/hooks.json 已经是最新")
    else:
        skip("没给 --with-hooks（想开 lab 闸门加这个参数）")

    step("5) 收尾")
    if args.dry_run:
        print("  [dry-run] 到此为止，没有改任何文件。")
    else:
        print("  改了以下几处，重启 Antigravity 后生效：")
        print(f"    {cfg_dir / 'mcp_config.json'}")
        print(f"    {cfg_dir / 'skills.json'}")
        if args.with_hooks:
            print(f"    {root / '.agents' / 'hooks.json'}")
    print()
    if args.with_hooks:
        print("  lab 模式：在 agy 输入框里单独发一句 lab： 打开，退出实验 关闭")
        print("  审计流水：~/.seep/agy-audit.jsonl（一行一条，tail -f 可看）")
        print()
    print("  在 agy 里验证：")
    print("    1. 打开这个仓库，随便点一个文件 —— AGENTS.md 会自动进上下文")
    print("    2. 让它「用 seep_auto_triage 看一眼这个 apk」，能调起来就通了")
    print("    3. 想看挂载列表：python setup/agy-setup.py --list")
    print()
    print("  只支持读、不写：这个脚本不碰你的 Antigravity 用户设置、不碰模型配置。")
    return 0


if __name__ == "__main__":
    sys.exit(main())