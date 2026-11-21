#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PostToolUse：工具跑完记一条审计流水。只记不管，绝不改任何决策。

为什么不用 PreToolUse：PreToolUse 必须返回 decision（allow/deny/ask），
返回 allow 就等于替用户点了「永远允许」，那是越权。这条线只观察、不干预。

日志：~/.seep/agy-audit.jsonl（一行一条，可 tail、可 jq）
禁用：删掉 .agents/hooks.json 里对应那一段，或设 SEEP_AGENT_STATE 换目录
"""

from __future__ import annotations

import hashlib
import json
import sys
import time

from lib import (AUDIT_LOG, STATE_DIR, emit, in_repo, lab_is_on, log,
                 primary_workspace, read_payload)

# 参数里这些键的值可能是大段文件内容，记摘要就够，别把整个 APK 写进日志
HEAVY_KEYS = {"content", "fileContent", "data", "file_content", "text", "body"}


def summarize(args) -> dict:
    if not isinstance(args, dict):
        return {"_raw": str(args)[:200]}
    out = {}
    for k, v in args.items():
        if k in HEAVY_KEYS and isinstance(v, str) and len(v) > 120:
            digest = hashlib.sha256(v.encode("utf-8", "ignore")).hexdigest()[:12]
            out[k] = f"<{len(v)} bytes sha256:{digest}>"
        elif isinstance(v, str) and len(v) > 300:
            out[k] = v[:300] + "…"
        else:
            out[k] = v
    return out


def main() -> int:
    payload = read_payload()
    call = payload.get("toolCall") or {}
    name = str(call.get("name") or "")
    if not name:
        emit({})
        return 0

    # 全局装的时候，人在别的项目里也会调工具。
    # 只记「仓库内」或「lab 开着」的调用，别把无关项目的流水也写进来。
    conv = str(payload.get("conversationId") or "")
    if not in_repo(payload) and not lab_is_on(conv):
        emit({})
        return 0

    rec = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "conversationId": payload.get("conversationId"),
        "workspace": primary_workspace(payload),
        "inRepo": in_repo(payload),
        "stepIdx": payload.get("stepIdx"),
        "tool": name,
        "args": summarize(call.get("args")),
        "ok": not bool(payload.get("error")),
    }
    if payload.get("error"):
        rec["error"] = str(payload["error"])[:300]

    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with AUDIT_LOG.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception as exc:
        log(f"审计日志写不进去：{exc}")

    # PostToolUse 契约：输出空对象
    emit({})
    return 0


if __name__ == "__main__":
    sys.exit(main())