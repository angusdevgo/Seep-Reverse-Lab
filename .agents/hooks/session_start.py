#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SessionStart：新会话开始时注入一次说明。

**按工作区分两种说法** —— 因为钩子可能装在全局（任何项目都会跑）：

  · 工作区是本仓库   → 说清工具、技能、lab 用法、以及你填的授权范围
  · 工作区是别的项目 → 只说一句「Seep 工具可用，要开工发 lab：」，不啰嗦

不注入纪律正文（太长，而且 lab 还没开）。纪律在 PreInvocation 里按需注入。
"""

from __future__ import annotations

import sys

from lib import (emit, in_repo, load_scope, log, primary_workspace,
                 read_payload)


def repo_message(scope: str) -> str:
    parts = [
        "## Seep 工作台已就绪",
        "",
        "当前工作区就是这个工作台仓库：MCP 服务端 + 10 个技能 + 294 篇战术笔记 + 工具本体。",
        "",
        "**工具怎么用**：38 个 `seep_*` 工具已通过 MCP 挂好，直接调，不要让用户手敲命令。",
        "常用入口：`seep_auto_triage`（先判型）→ `seep_apk_decompile` / `seep_r2_info`（看结构）"
        "→ `seep_kb_search`（查笔记）→ `seep_gen_security_report`（出报告）。",
        "",
        "**lab 模式**：输入框发一句 `lab：` 打开，`退出实验` 关闭。"
        "打开后每轮追加审计协作约定与术语对照；关闭后一切照常。只影响当前会话。",
        "",
        "**纪律**：只在有授权的目标上动。没授权就直说做不到。",
    ]
    if scope:
        parts += ["", "---", "", "## 本工单的授权范围（用户填写）", "", scope]
    return "\n".join(parts)


def generic_message() -> str:
    return "\n".join([
        "## Seep 工作台可用",
        "",
        "`seep_*`（38 个）、`js-reverse`（24 个）等 MCP 工具已挂好，技能也已注册。",
        "要做客户端鉴权审计 / 逆向分析，在输入框发一句 `lab：` 即进入协作模式，`退出实验` 退出。",
        "做别的活儿不用管这一条。",
    ])


def main() -> int:
    payload = read_payload()
    conv = str(payload.get("conversationId") or "")
    here = in_repo(payload)
    log(f"SessionStart conv={conv} in_repo={here} ws={primary_workspace(payload)}")

    msg = repo_message(load_scope()) if here else generic_message()
    emit({"injectSteps": [{"systemMessage": {"systemMessage": msg}}]})
    return 0


if __name__ == "__main__":
    sys.exit(main())