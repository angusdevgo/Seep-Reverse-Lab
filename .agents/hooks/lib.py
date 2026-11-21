#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""agy 钩子共用件：读 stdin、写 stdout、记 lab 状态、加载术语表与授权范围。

三个钩子（session_start / pre_invocation / post_tool_use）都从这里拿工具函数。

为什么要有这一层：agy 的钩子契约是「stdin 进 JSON、stdout 出 JSON」，
每个钩子只活几秒，所有状态都放磁盘。放这里统一处理，省得三份重复。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# -----------------------------------------------------------------------------
# 仓库与状态文件
# -----------------------------------------------------------------------------

# .agents/hooks/lib.py → 仓库根
REPO = Path(__file__).resolve().parent.parent.parent

STATE_DIR = Path(os.path.expanduser(os.environ.get("SEEP_AGENT_STATE", "~/.seep")))
LAB_STATE = STATE_DIR / "agy-lab.json"
AUDIT_LOG = STATE_DIR / "agy-audit.jsonl"
SCOPE_FILE = REPO / "Tool" / "prompts" / "agy" / "scope.md"
RULES_FILE = REPO / "Tool" / "scripts" / "compliance-relay" / "sensitive-rules.json"

MAX_STATE = 200  # 状态文件里最多留多少个会话，防止无限增长

# -----------------------------------------------------------------------------
# 输入输出
# -----------------------------------------------------------------------------


def read_payload() -> dict:
    """读钩子 stdin。读不到就返回空字典，绝不抛。"""
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return {}
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def emit(obj: dict) -> None:
    """把结果写到 stdout。钩子只认 stdout 的 JSON。"""
    sys.stdout.write(json.dumps(obj, ensure_ascii=False))
    sys.stdout.flush()


def log(msg: str) -> None:
    """调试输出走 stderr，不污染 stdout 的协议数据。"""
    try:
        sys.stderr.write(f"[seep-hook] {msg}\n")
        sys.stderr.flush()
    except Exception:
        pass


# -----------------------------------------------------------------------------
# lab 状态（按 conversationId 记，天然是「会话级」）
# -----------------------------------------------------------------------------


def _load_state() -> dict:
    try:
        data = json.loads(LAB_STATE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    try:
        if len(state) > MAX_STATE:
            # 只保留最近写入的一批：值是 {"on": bool, "ts": float}
            keep = sorted(state.items(), key=lambda kv: kv[1].get("ts", 0) if isinstance(kv[1], dict) else 0)
            state = dict(keep[-MAX_STATE:])
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        LAB_STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n",
                             encoding="utf-8", newline="\n")
    except Exception as exc:
        log(f"状态写不进去：{exc}")


def lab_is_on(conversation_id: str) -> bool:
    if not conversation_id:
        return False
    rec = _load_state().get(conversation_id)
    return bool(isinstance(rec, dict) and rec.get("on"))


def set_lab(conversation_id: str, on: bool) -> None:
    if not conversation_id:
        return
    import time
    state = _load_state()
    state[conversation_id] = {"on": bool(on), "ts": time.time()}
    _save_state(state)


def clear_lab(conversation_id: str) -> None:
    state = _load_state()
    if state.pop(conversation_id, None) is not None:
        _save_state(state)


# -----------------------------------------------------------------------------
# 工作区感知
#
# 钩子可能装在两个位置：
#   1. <仓库>/.agents/hooks.json  —— 只在本仓库生效
#   2. ~/.gemini/config/hooks.json —— 全局，任何工作区都会跑
#
# 全局装的时候，用户可能正在做跟逆向无关的活。所以每个钩子都要先问一句
# 「当前工作区是不是这个仓库」，再决定注入长内容还是短提示。
# -----------------------------------------------------------------------------


def _norm_path(p: str) -> str:
    try:
        s = os.path.normpath(os.path.expanduser(str(p))).replace("\\", "/")
        return s.rstrip("/").lower() if os.name == "nt" else s.rstrip("/")
    except Exception:
        return ""


def workspace_paths(payload: dict) -> list[str]:
    """agy 传过来的 work区列表，cwd 也算一个（有的界面只给 cwd）。"""
    out = []
    for key in ("workspacePaths", "cwd"):
        v = payload.get(key)
        if isinstance(v, str) and v:
            out.append(v)
        elif isinstance(v, list):
            out.extend([x for x in v if isinstance(x, str) and x])
    seen, uniq = set(), []
    for p in out:
        n = _norm_path(p)
        if n and n not in seen:
            seen.add(n)
            uniq.append(p)
    return uniq


def in_repo(payload: dict) -> bool:
    """当前工作区是不是落在本仓库里（相等或在其子目录）。"""
    repo = _norm_path(str(REPO))
    for p in workspace_paths(payload):
        n = _norm_path(p)
        if n == repo or n.startswith(repo + "/"):
            return True
    return False


def primary_workspace(payload: dict) -> str:
    ws = workspace_paths(payload)
    return ws[0] if ws else ""


# -----------------------------------------------------------------------------
# 触发词（与 pi / DSH 保持同一套）
# -----------------------------------------------------------------------------

LAB_ON = ("lab：", "lab:", "实验：", "实验:", "进入实验：", "进入实验:")
LAB_OFF = ("退出实验", "退出工作环境", "exit lab", "exit-lab")


def trigger_of(text: str) -> str:
    """判断这句用户输入是不是开关指令。返回 'on' / 'off' / ''。"""
    if not isinstance(text, str):
        return ""
    head = text.strip()[:24].lower()
    for t in LAB_OFF:
        if head.startswith(t.lower()):
            return "off"
    for t in LAB_ON:
        if head.startswith(t.lower()):
            return "on"
    return ""


# -----------------------------------------------------------------------------
# 术语表与授权范围
# -----------------------------------------------------------------------------


def load_rules() -> list[tuple[str, str]]:
    """读单一真值表：sensitive-rules.json（由 TS 扩展 extract 出来）。"""
    try:
        data = json.loads(RULES_FILE.read_text(encoding="utf-8"))
        out = []
        for r in data.get("rules", []):
            f, t = r.get("from"), r.get("to")
            if isinstance(f, str) and isinstance(t, str) and f:
                out.append((f, t))
        return out
    except Exception as exc:
        log(f"术语表读不到：{exc}")
        return []


def load_scope() -> str:
    """授权范围。用户自己写的，没有就返回空。"""
    try:
        if SCOPE_FILE.is_file():
            return SCOPE_FILE.read_text(encoding="utf-8").strip()
    except Exception as exc:
        log(f"授权范围读不到：{exc}")
    return ""