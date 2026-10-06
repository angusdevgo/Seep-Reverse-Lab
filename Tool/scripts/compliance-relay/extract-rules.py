#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Seep 工作台 —— 合规规则表提取器 (extract-rules.py)

单一真值源策略：以 Tool/prompts/extensions/security-audit-interceptor.ts 中的
SENSITIVE_WORD_MAP 为唯一权威来源，单向提取生成 sensitive-rules.json 供
compliance-relay 中继读取。TS 侧保持内嵌自包含，零改动。

用法:
    python extract-rules.py            # 提取并写入 sensitive-rules.json
    python extract-rules.py --check    # 仅校验现有 JSON 是否与 TS 源一致（CI 用）
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
TS_SOURCE = os.path.join(
    REPO_ROOT, "Tool", "prompts", "extensions", "security-audit-interceptor.ts"
)
OUTPUT = os.path.join(HERE, "sensitive-rules.json")

MIN_RULES = 30

# 匹配形如:  [/破解/g, "白盒鉴权脆弱性测试"],
RULE_LINE = re.compile(
    r"""\[\s*/(?P<pattern>(?:\\.|[^/\\])*)/[a-z]*\s*,\s*"(?P<replacement>(?:\\.|[^"\\])*)"\s*\]""",
    re.VERBOSE,
)

TS_STRING_ESCAPES = {
    "\\n": "\n",
    "\\t": "\t",
    "\\r": "\r",
    '\\"': '"',
    "\\'": "'",
    "\\\\": "\\",
}


def _unescape_ts_string(value: str) -> str:
    """还原 TS 字符串字面量中的转义序列。"""
    out = []
    i = 0
    while i < len(value):
        ch = value[i]
        if ch == "\\" and i + 1 < len(value):
            pair = value[i : i + 2]
            if pair in TS_STRING_ESCAPES:
                out.append(TS_STRING_ESCAPES[pair])
                i += 2
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def _unescape_regex_pattern(pattern: str) -> str:
    """还原正则字面量中的转义：\\/ -> /，\\\\ -> \\，其余保持字面。"""
    out = []
    i = 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "\\" and i + 1 < len(pattern):
            nxt = pattern[i + 1]
            if nxt == "/":
                out.append("/")
                i += 2
                continue
            if nxt == "\\":
                out.append("\\")
                i += 2
                continue
            # 保留其他转义（虽然当前规则表未使用元字符，稳妥起见不丢信息）
            out.append(ch)
            out.append(nxt)
            i += 2
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def extract_rules(ts_path: str = TS_SOURCE) -> list[dict]:
    """从 TS 源文件中提取 SENSITIVE_WORD_MAP 规则表。"""
    if not os.path.isfile(ts_path):
        raise FileNotFoundError(f"未找到 TS 规则源文件: {ts_path}")

    with open(ts_path, "r", encoding="utf-8") as fh:
        source = fh.read()

    start = source.find("SENSITIVE_WORD_MAP")
    if start == -1:
        raise ValueError("TS 源文件中未找到 SENSITIVE_WORD_MAP 声明")

    end = source.find("];", start)
    if end == -1:
        raise ValueError("TS 源文件中 SENSITIVE_WORD_MAP 数组未正常闭合")

    block = source[start:end]

    rules: list[dict] = []
    seen: set[str] = set()
    for match in RULE_LINE.finditer(block):
        pattern = _unescape_regex_pattern(match.group("pattern"))
        replacement = _unescape_ts_string(match.group("replacement"))
        if not pattern:
            continue
        if pattern in seen:
            continue
        seen.add(pattern)
        rules.append({"from": pattern, "to": replacement})

    return rules


def validate(rules: list[dict]) -> list[str]:
    """返回错误列表，空列表表示校验通过。"""
    errors: list[str] = []
    if len(rules) < MIN_RULES:
        errors.append(
            f"规则数量不足: 提取到 {len(rules)} 条，至少需要 {MIN_RULES} 条"
        )
    seen: set[str] = set()
    for idx, rule in enumerate(rules):
        src = rule.get("from", "")
        dst = rule.get("to", "")
        if not src:
            errors.append(f"第 {idx} 条规则的 from 为空")
        if not dst:
            errors.append(f"第 {idx} 条规则的 to 为空 (from={src!r})")
        if src in seen:
            errors.append(f"规则 from 重复: {src!r}")
        seen.add(src)
    return errors


def build_payload(rules: list[dict]) -> dict:
    """构造输出载荷（不含时间戳，避免无意义 diff）。"""
    rel_source = os.path.relpath(TS_SOURCE, REPO_ROOT).replace("\\", "/")
    return {
        "schema": 1,
        "generatedFrom": rel_source,
        "_comment": "本文件由 extract-rules.py 自动生成，请勿手工编辑；请修改 TS 源文件后重新提取。",
        "ruleCount": len(rules),
        "rules": rules,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="从 TS 扩展提取合规规则表")
    parser.add_argument(
        "--check",
        action="store_true",
        help="仅校验现有 sensitive-rules.json 是否与 TS 源一致",
    )
    args = parser.parse_args()

    try:
        rules = extract_rules()
    except (FileNotFoundError, ValueError) as exc:
        print(f"[FAIL] 规则提取失败: {exc}", file=sys.stderr)
        return 1

    errors = validate(rules)
    if errors:
        print("[FAIL] 规则校验未通过:", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    payload = build_payload(rules)
    serialized = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"

    if args.check:
        if not os.path.isfile(OUTPUT):
            print(f"[FAIL] 未找到 {OUTPUT}，请先运行 extract-rules.py", file=sys.stderr)
            return 1
        with open(OUTPUT, "r", encoding="utf-8") as fh:
            current = fh.read()
        if current != serialized:
            print(
                "[FAIL] sensitive-rules.json 与 TS 源不一致，请重新运行 extract-rules.py",
                file=sys.stderr,
            )
            return 1
        print(f"[OK] 规则表已同步，共 {len(rules)} 条")
        return 0

    with open(OUTPUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(serialized)
    print(f"[OK] 已生成 {OUTPUT}")
    print(f"     规则条数: {len(rules)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
