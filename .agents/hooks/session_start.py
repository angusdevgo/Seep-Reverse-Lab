#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SessionStart：新会话开始时注入一次「这台机器上这个仓库是干什么的」。

不注入纪律正文（太长，而且 lab 还没开），只注入三件事：
  1. 这个仓库是 Seep 工作台，工具在哪
  2. lab 怎么开、开了会发生什么
  3. 如果用户写了授权范围（Tool/prompts/agy/scope.md），贴进来

agy 的规则层本来就会自动加载 AGENTS.md，所以这里只补规则层没说清的操作提示。
"""

from __future__ import annotations

import sys

from lib import REPO, emit, lab_is_on, load_scope, log, read_payload


def build_message(scope: str) -> str:
    parts = [
        "## Seep 工作台已就绪（Antigravity 接线）",
        "",
        "这个仓库是客户端鉴权审计工作台：MCP 服务端 + 10 个技能 + 294 篇战术笔记 + 工具本体。",
        "",
        "**工具怎么用**：38 个 `seep_*` 工具已经通过 MCP 挂好，直接调，不要让用户手敲命令。",
        "常用入口：`seep_auto_triage`（先判型）→ `seep_apk_decompile` / `seep_r2_info`（看结构）"
        "→ `seep_kb_search`（查笔记）→ `seep_gen_security_report`（出报告）。",
        "",
        "**lab 模式**：在输入框里单独发一句 `lab：` 打开，`退出实验` 关闭。",
        "打开后每一轮会追加审计协作约定与术语对照；关闭后一切照常。",
        "只影响当前会话，不写进你的任何配置。",
        "",
        "**纪律**：只在有授权的目标上动。没授权就直说做不到。",
    ]
    if scope:
        parts += [
            "",
            "---",
            "",
            "## 本工单的授权范围（用户填写）",
            "",
            scope,
        ]
    return "\n".join(parts)


def main() -> int:
    payload = read_payload()
    conv = str(payload.get("conversationId") or "")
    log(f"SessionStart conv={conv} lab={lab_is_on(conv)}")

    msg = build_message(load_scope())
    emit({"injectSteps": [{"systemMessage": {"systemMessage": msg}}]})
    return 0


if __name__ == "__main__":
    sys.exit(main())