#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""外部工具解析 / 实跑验证 —— 纯标准库实现（PowerShell 版的内存等价物）

为什么单独一个模块
    「这个工具在哪、能不能启动」这件事，Windows 的 setup/resolve-tools.ps1、
    Unix 的 setup/verify.sh、以及 MCP 的 seep_status 本来各写一套，路径判断就有
    三份真相，换个用户路径不同就会互相打架。

    现在规则只有一处：<repo>/setup/tool-registry.json。
    解析逻辑也只有一处：就是这个文件。三方都调用它。

    刻意不依赖 mcp 库 —— 否则 setup 各处的自检脚本都要先能 import mcp 才能跑，
    而 Python 环境本身正是它们要检查的东西之一。

四态
    READY     找到且实跑成功（verified=True）；未实跑时 verified=False
    DEGRADED  找到但跑不起来（缺依赖 / 版本不符 / 许可失效）
    OPTIONAL  没找到，属于可选能力
    MISSING   没找到，属于核心能力

解析链（逐层下降，命中即停，记录来源层）
    env → cache → bundled → path → candidates
    可在注册表里用 tools[].chain 覆盖顺序（python 就靠这个优先找 venv 而不是 PATH 垫片）
"""

from __future__ import annotations

import io
import json
import os
import re
import shutil
import subprocess
import sys
from typing import Any, Dict, List, Optional

DEFAULT_CHAIN = ["env", "cache", "bundled", "path", "candidates"]


# ---------------------------------------------------------------- 路径工具

def expand_pattern(pattern: str, root: str = "") -> str:
    """展开 {root} / %VAR% / {env:VAR} / ~，并归一化成本机路径。"""
    if not pattern:
        return pattern
    p = pattern.replace("{root}", root) if root else pattern

    def _env_repl(m):
        val = os.environ.get(m.group(1))
        return val if val else m.group(0)

    p = re.sub(r"\{env:([A-Za-z0-9_]+)\}", _env_repl, p)
    p = re.sub(r"%([A-Za-z0-9_() ]+)%", _env_repl, p)
    if p.startswith("~"):
        p = os.path.join(os.path.expanduser("~"), p[1:].lstrip("/\\"))
    return os.path.normpath(p)


def tool_layout(tool: dict) -> List[str]:
    """从「根目录」推出候选可执行文件（{root} 占位）。"""
    if tool.get("toolbox_layout"):
        return list(tool["toolbox_layout"])
    if tool.get("id") == "ida":
        return ["{root}/ida.exe", "{root}/ida64.exe", "{root}/App/IDA Pro/ida.exe"]
    out: List[str] = []
    for n in tool.get("path_names") or []:
        out += ["{root}/%s.exe" % n, "{root}/%s" % n,
                "{root}/bin/%s.exe" % n, "{root}/bin/%s" % n,
                "{root}/Scripts/%s.exe" % n]
    return out


def find_in_root(tool: dict, root: str) -> Optional[str]:
    for pat in tool_layout(tool):
        cand = expand_pattern(pat, root)
        if cand and os.path.isfile(cand):
            return cand
    return None


# ---------------------------------------------------------------- 注册表 / 缓存

def registry_path(repo_root: str) -> str:
    return os.path.join(repo_root, "setup", "tool-registry.json")


def cache_path() -> str:
    return os.path.join(os.path.expanduser("~"), ".seep", "tools.json")


def load_registry(repo_root: str) -> List[dict]:
    try:
        with io.open(registry_path(repo_root), encoding="utf-8") as f:
            return list(json.load(f).get("tools", []))
    except (OSError, ValueError):
        return []


def load_cache() -> Dict[str, Any]:
    try:
        with io.open(cache_path(), encoding="utf-8") as f:
            return dict(json.load(f).get("resolved", {}))
    except (OSError, ValueError):
        return {}


def save_cache(report: Dict[str, Any]) -> None:
    """只记解析到且 READY 的位置，避免把坏路径固化下来。"""
    entries = {}
    for tid, t in report.get("tools", {}).items():
        if t.get("path") and t.get("state") == "READY":
            entries[tid] = {"path": t["path"], "source": t.get("source")}
    data = {"version": 1, "resolved": entries}
    try:
        d = os.path.dirname(cache_path())
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
        with io.open(cache_path(), "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(data, ensure_ascii=False, indent=2))
    except OSError:
        pass


# ---------------------------------------------------------------- 解析

def resolve_one(tool: dict, cache: Dict[str, Any], repo_root: str) -> Dict[str, Any]:
    tid = tool.get("id")
    chain = tool.get("chain") or DEFAULT_CHAIN
    path = None
    source = None
    warn: List[str] = []

    for layer in chain:
        if path:
            break

        if layer == "env":
            env_name = tool.get("env")
            if not env_name:
                continue
            raw = os.environ.get(env_name)
            if not raw:
                continue
            exp = expand_pattern(raw)
            if not os.path.exists(exp):
                # 环境变量写错了不该直接判死：记下警告，继续沿链往下降
                warn.append("%s 指向的路径不存在: %s" % (env_name, exp))
                continue
            if os.path.isdir(exp):
                hit = find_in_root(tool, exp)
                if hit:
                    path, source = hit, "env:%s" % env_name
            else:
                path, source = exp, "env:%s" % env_name

        elif layer == "cache":
            entry = cache.get(tid) or {}
            cached = entry.get("path")
            if cached and os.path.exists(cached):
                path, source = cached, "cache"

        elif layer == "bundled":
            for b in tool.get("bundled") or []:
                full = os.path.join(repo_root, b.replace("/", os.sep))
                if os.path.exists(full):
                    path, source = full, "bundled"
                    break

        elif layer == "path":
            for n in tool.get("path_names") or []:
                hit = shutil.which(n)
                if hit:
                    path, source = hit, "path"
                    break

        elif layer == "candidates":
            for c in tool.get("candidates") or []:
                exp = expand_pattern(c)
                if not exp or not os.path.exists(exp):
                    continue
                if os.path.isdir(exp):
                    hit = find_in_root(tool, exp)
                    if hit:
                        path, source = hit, "candidates"
                        break
                else:
                    path, source = exp, "candidates"
                    break

    if path:
        state = "READY"
    elif tool.get("kind") == "optional":
        state = "OPTIONAL"
    else:
        state = "MISSING"

    return {
        "id": tid,
        "kind": tool.get("kind", "core"),
        "state": state,
        "path": path,
        "source": source,
        "verified": False,
        "detail": "；".join(warn),
        "purpose": tool.get("purpose", ""),
        "fix": tool.get("fix", ""),
        "expect": tool.get("expect", ""),
    }


# ---------------------------------------------------------------- 实跑验证

def _strip_ansi(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def _first_lines(text: str, n: int = 2) -> str:
    out = [l for l in text.splitlines()
           if l.strip() and not re.fullmatch(r"[-=*_#~]+", l.strip())][:n]
    return " / ".join(out)[:120]


def verify_one(tool: dict, resolved: Dict[str, Any], find_java=None) -> Dict[str, Any]:
    """实跑。只有这一步通过，READY 才算「真的能启动」。"""
    spec = tool.get("verify") or {}
    kind = spec.get("kind", "version")
    p = resolved.get("path")
    if not p:
        return resolved

    if kind == "exists":
        pkg = os.path.join(p, "package.json")
        if os.path.isfile(pkg):
            resolved["verified"] = True
            resolved["detail"] = "包目录完整（package.json 在位）"
        else:
            resolved["state"] = "DEGRADED"
            resolved["detail"] = "包目录缺少 package.json（可能 node_modules 未解压）"
        return resolved

    if kind == "ida":
        root = os.path.dirname(p)
        found = False
        for dirpath, _dirnames, filenames in os.walk(root):
            if "server.py" in filenames and "ida_pro_mcp" in dirpath:
                found = True
                break
        if found:
            resolved["verified"] = True
            resolved["detail"] = "ida.exe + ida_pro_mcp 就绪"
        else:
            resolved["state"] = "DEGRADED"
            resolved["detail"] = "ida.exe 在位，但未装 ida_pro_mcp（跑 install-ida.ps1）"
        return resolved

    exe = p
    args: List[str] = []

    if kind == "python-import":
        args = ["-c", "import %s" % spec.get("arg", "mcp")]
    elif kind == "jar":
        java = find_java() if find_java else (shutil.which("java"))
        if not java:
            resolved["state"] = "DEGRADED"
            resolved["detail"] = "缺少 java，无法执行 jar"
            return resolved
        exe, args = java, ["-jar", p] + list(spec.get("args") or [])
    else:
        args = list(spec.get("args") or [])

    # .bat / .cmd 必须经 cmd.exe，且要传「单个字符串」：
    #   · 引号整体再包一层（/s /c ""path" "args""），否则带空格的路径会被当成一个 token
    #   · 传 list 的话 Python 会再套一层 list2cmdline 转义，把引号彻底搅乱
    if os.name == "nt" and exe.lower().endswith((".bat", ".cmd")):
        argstr = " ".join('"%s"' % a.replace('"', '""') for a in args)
        comspec = os.environ.get("ComSpec", "cmd.exe")
        cmd: Any = '%s /s /c ""%s" %s"' % (comspec, exe.replace('"', '""'), argstr)
    else:
        cmd = [exe] + args

    try:
        # encoding/errors 必须显式指定：Windows 默认 GBK 解码，遇到 UTF-8 输出会在
        # reader 线程里抛 UnicodeDecodeError，整个调用变成空结果。
        proc = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace",
                              timeout=int(spec.get("timeout", 15)), stdin=subprocess.DEVNULL)
        text = _strip_ansi(((proc.stdout or "") + "\n" + (proc.stderr or "")).strip())
        resolved["verified"] = proc.returncode == 0
        resolved["detail"] = _first_lines(text)
        if proc.returncode != 0:
            resolved["state"] = "DEGRADED"
    except Exception as exc:  # noqa: BLE001
        resolved["state"] = "DEGRADED"
        resolved["detail"] = str(exc)[:120]
    return resolved


# ---------------------------------------------------------------- 总报告

def external_tool_report(repo_root: str, verify: bool = False,
                         only: Optional[List[str]] = None) -> Dict[str, Any]:
    tools = load_registry(repo_root)
    if not tools:
        return {"registry": registry_path(repo_root), "available": False, "tools": {}}

    if only:
        want = {x.lower() for x in only}
        tools = [t for t in tools if t.get("id", "").lower() in want]

    cache = load_cache()
    out: Dict[str, Any] = {}
    for t in tools:
        r = resolve_one(t, cache, repo_root)
        if verify and r.get("path"):
            r = verify_one(t, r)
        out[r["id"]] = r

    # requires 依赖（apktool 需要 java）
    by_id = {t.get("id"): t for t in tools}
    for tid, r in out.items():
        for dep in (by_id.get(tid) or {}).get("requires") or []:
            d = out.get(dep)
            if d and d["state"] != "READY":
                r["state"] = "DEGRADED"
                r["detail"] = "依赖 %s 未就绪" % dep

    summary = {
        "ready": sum(1 for v in out.values() if v["state"] == "READY"),
        "degraded": sum(1 for v in out.values() if v["state"] == "DEGRADED"),
        "optional": sum(1 for v in out.values() if v["state"] == "OPTIONAL"),
        "missing": sum(1 for v in out.values() if v["state"] == "MISSING"),
    }
    return {
        "registry": registry_path(repo_root),
        "available": True,
        "verify_run": bool(verify),
        "summary": summary,
        "hint": ("路径判断规则在 setup/tool-registry.json。要验证「是否真的能启动」，"
                 "跑 resolve-tools -Verify（Windows 用 .ps1，其它平台用 .py）。"),
        "tools": out,
    }


def find_repo_root(start: str = None) -> str:
    """从给定位置往上找含 setup/tool-registry.json 的目录。"""
    p = os.path.abspath(start or os.path.dirname(os.path.abspath(__file__)))
    for _ in range(6):
        if os.path.isfile(registry_path(p)):
            return p
        parent = os.path.dirname(p)
        if parent == p:
            break
        p = parent
    return os.path.abspath(start or os.getcwd())


def main(argv=None) -> int:
    """简易 CLI：python Tool/mcp/tool_resolver.py [--verify] [--json] [--tool id ...]"""
    argv = list(sys.argv[1:] if argv is None else argv)
    verify = "--verify" in argv
    as_json = "--json" in argv
    only: List[str] = []
    if "--tool" in argv:
        i = argv.index("--tool")
        only = [a for a in argv[i + 1:] if not a.startswith("--")]
    root = find_repo_root(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    rep = external_tool_report(root, verify=verify, only=only or None)

    # --state <id>：给 shell 脚本用，只打印一个四态词，省掉在 verify.sh 里内联 Python
    if "--state" in argv:
        i = argv.index("--state")
        target = argv[i + 1] if i + 1 < len(argv) else ""
        t = rep["tools"].get(target) or {}
        print(t.get("state", "UNKNOWN"))
        return 0

    if as_json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        print("\n  repo: %s" % root)
        print("  registry: %s\n" % rep["registry"])
        print("  %-16s %-10s %-12s %s" % ("ID", "STATE", "SOURCE", "PATH"))
        print("  " + "-" * 96)
        for tid, t in rep["tools"].items():
            print("  %-16s %-10s %-12s %s" % (tid, t["state"], t["source"] or "-", t["path"] or "-"))
            if t.get("detail"):
                print("  %-16s %-10s %-12s   └─ %s" % ("", "", "", t["detail"][:90]))
        s = rep["summary"]
        print("  " + "-" * 96)
        print("  READY %d | DEGRADED %d | OPTIONAL %d | MISSING %d" %
              (s["ready"], s["degraded"], s["optional"], s["missing"]))
        print()

    return 1 if rep["summary"]["missing"] > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
