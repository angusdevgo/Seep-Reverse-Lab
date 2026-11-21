#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""PreInvocation：每次调模型前跑一次。这是 lab 闸门在 agy 上的实现。

注入分两档，按「是不是刚开 lab」决定：

  第一次开 lab（本会话）  → 完整人格/纪律正文（Tool/prompts/SYSTEM.md，18 KB）
                            + 术语对照 + 授权范围
  之后每轮（lab 仍开着）  → 只给一条短提醒 + 术语对照
  没开 lab                → 什么都不注入

为什么不一上来就每轮灌 18 KB：agy 的 systemMessage 会留在会话轨迹里，
灌一次就够；每轮再灌等于白烧 token。但也不完全依赖它 —— 万一会话被裁剪，
短提醒还在，行为不会突然失守。

开关：`lab：` 打开，`退出实验` 关闭。状态按 conversationId 存，会话之间隔离。
"""

from __future__ import annotations

import sys

from lib import (emit, in_repo, lab_is_on, load_persona, load_rules,
                 load_scope, log, read_payload, set_lab, trigger_of)


def greeting_block() -> str:
    return "\n".join([
        "## 进入授权审计协作（lab）",
        "",
        "下面整份是本工作台的作战纪律与审计规范，按它执行。",
        "要点先摆前面：先调工具再解释、每条结论带证据、改动最小、写明边界、只在授权范围内动。",
    ])


def short_reminder() -> str:
    return "\n".join([
        "## lab 仍开着（提醒）",
        "",
        "先调工具再解释 · 每条结论带证据 · 改动最小 · 写明边界 · 只在授权范围内动。",
    ])


def glossary_block(rules: list[tuple[str, str]]) -> str:
    if not rules:
        return ""
    lines = [
        "## 术语对照（用户口语 → 审计术语）",
        "",
        "用户习惯用行业口语，语义等价于右列。按右列理解，不要在措辞上纠缠：",
        "",
    ]
    for f, t in rules:
        lines.append(f"- 「{f}」= {t}")
    return "\n".join(lines)


def main() -> int:
    payload = read_payload()
    conv = str(payload.get("conversationId") or "")
    last = payload.get("lastUserInput") or ""

    # --- 1. 开关机 ---
    was_on = lab_is_on(conv)
    trig = trigger_of(last)
    if trig == "on":
        set_lab(conv, True)
        log(f"lab ON  conv={conv}")
    elif trig == "off":
        set_lab(conv, False)
        log(f"lab OFF conv={conv}")

    if not lab_is_on(conv):
        emit({})
        return 0

    # --- 2. 刚开 → 灌完整人格；已经在跑 → 只给短提醒 ---
    first_turn = (trig == "on") or (not was_on)
    persona = load_persona() if first_turn else ""

    parts = [greeting_block()] if first_turn else [short_reminder()]
    if persona:
        parts.append(persona)
    glossary = glossary_block(load_rules())
    if glossary:
        parts.append(glossary)
    # 授权范围是「这个仓库的工单」，别的项目里贴上去是噪声
    if in_repo(payload):
        scope = load_scope()
        if scope:
            parts += ["## 本工单授权范围", "", scope]

    log(f"inject first_turn={first_turn} persona={len(persona)} 总={sum(len(p) for p in parts)}")
    emit({"injectSteps": [{"systemMessage": {"systemMessage": "\n\n".join(parts)}}]})
    return 0


if __name__ == "__main__":
    sys.exit(main())