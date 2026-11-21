#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""agy 钩子的契约测试（纯标准库，不需要装 Antigravity）。

跑法：
    python setup/test_agy_hooks.py
    python setup/test_agy_hooks.py -v

测什么：
  1. 三个钩子都能被「stdin 进 JSON、stdout 出 JSON」的方式调用，且输出合法
  2. lab 开关：lab： 打开、退出实验 关闭、会话之间互不影响
  3. lab 关闭时不注入；打开时注入纪律 + 术语表 + 授权范围
  4. PostToolUse 写审计流水，大字段只存摘要
  5. 所有钩子对畸形输入都不崩（agy 传什么都要能活下来）
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOKS = REPO / ".agents" / "hooks"
PY = sys.executable


class HookTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not HOOKS.is_dir():
            raise unittest.SkipTest("仓库里没有 .agents/hooks，跳过")
        # 状态目录隔离，别污染真实的 ~/.seep
        cls._tmp = tempfile.TemporaryDirectory()
        cls.env = dict(os.environ)
        cls.env["SEEP_AGENT_STATE"] = cls._tmp.name
        cls.env["PYTHONIOENCODING"] = "utf-8"
        cls.state_dir = Path(cls._tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    # -- 工具 ---------------------------------------------------------------
    def run_hook(self, name: str, payload: dict) -> tuple[int, dict, str]:
        p = subprocess.run(
            [PY, str(HOOKS / name)],
            input=json.dumps(payload, ensure_ascii=False),
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", env=self.env, timeout=60,
        )
        try:
            out = json.loads(p.stdout) if p.stdout.strip() else {}
        except json.JSONDecodeError as exc:
            self.fail(f"{name} 输出的不是 JSON：{exc}\nstdout={p.stdout[:300]}")
        return p.returncode, out, p.stderr

    @staticmethod
    def injected(out: dict) -> str:
        steps = out.get("injectSteps") or []
        return "\n".join(
            (s.get("systemMessage") or {}).get("systemMessage", "")
            for s in steps if isinstance(s, dict)
        )

    # -- 1. 契约 ------------------------------------------------------------
    def test_session_start_emits_system_message(self):
        code, out, _ = self.run_hook("session_start.py",
                                     {"conversationId": "c1", "hookEventName": "SessionStart"})
        self.assertEqual(code, 0)
        self.assertIn("injectSteps", out)
        msg = self.injected(out)
        self.assertIn("Seep", msg)
        self.assertIn("seep_auto_triage", msg)

    def test_pre_invocation_silent_when_lab_off(self):
        code, out, _ = self.run_hook("pre_invocation.py",
                                     {"conversationId": "c-off", "lastUserInput": "看看这个 apk"})
        self.assertEqual(code, 0)
        self.assertEqual(self.injected(out), "")

    def test_post_tool_use_returns_empty_object(self):
        code, out, _ = self.run_hook("post_tool_use.py",
                                     {"conversationId": "c1", "toolCall": {"name": "run_command",
                                                                           "args": {"CommandLine": "ls"}}})
        self.assertEqual(code, 0)
        self.assertEqual(out, {})

    # -- 2. lab 状态机 ------------------------------------------------------
    def test_lab_toggle(self):
        conv = {"conversationId": "c-lab", "lastUserInput": "lab：分析这个 apk"}
        _, out, _ = self.run_hook("pre_invocation.py", conv)
        self.assertIn("授权审计协作", self.injected(out))

        # 同一会话下一轮：不再带触发词，仍然是开的
        _, out, _ = self.run_hook("pre_invocation.py",
                                  {"conversationId": "c-lab", "lastUserInput": "继续"})
        self.assertIn("授权审计协作", self.injected(out))

        # 关掉
        _, out, _ = self.run_hook("pre_invocation.py",
                                  {"conversationId": "c-lab", "lastUserInput": "退出实验"})
        self.assertEqual(self.injected(out), "")

        # 关掉之后依然关着
        _, out, _ = self.run_hook("pre_invocation.py",
                                  {"conversationId": "c-lab", "lastUserInput": "继续"})
        self.assertEqual(self.injected(out), "")

    def test_lab_is_per_conversation(self):
        self.run_hook("pre_invocation.py",
                      {"conversationId": "conv-A", "lastUserInput": "lab："})
        _, out, _ = self.run_hook("pre_invocation.py",
                                  {"conversationId": "conv-B", "lastUserInput": "随便聊聊"})
        self.assertEqual(self.injected(out), "", "A 开了 lab 不应该影响 B")

    def test_lab_on_variants(self):
        for i, trig in enumerate(["lab:", "实验：", "进入实验："]):
            cid = f"variant-{i}"
            _, out, _ = self.run_hook("pre_invocation.py",
                                      {"conversationId": cid, "lastUserInput": trig + "看这个"})
            self.assertIn("授权审计协作", self.injected(out), f"{trig} 应该能开")

    # -- 3. 注入内容 --------------------------------------------------------
    def test_lab_injects_glossary_and_scope(self):
        _, out, _ = self.run_hook("pre_invocation.py",
                                  {"conversationId": "c-gloss", "lastUserInput": "lab："})
        msg = self.injected(out)
        self.assertIn("术语对照", msg)
        # 词表来自 sensitive-rules.json 单一真值
        self.assertIn("白盒鉴权脆弱性测试", msg)
        self.assertIn("授权范围", msg)

    # -- 4. 审计流水 --------------------------------------------------------
    def test_audit_log_written(self):
        self.run_hook("post_tool_use.py",
                      {"conversationId": "c-audit", "stepIdx": 3,
                       "toolCall": {"name": "run_command", "args": {"CommandLine": "whoami"}}})
        log_file = self.state_dir / "agy-audit.jsonl"
        self.assertTrue(log_file.is_file(), "审计日志没写出来")
        rec = json.loads(log_file.read_text(encoding="utf-8").strip().splitlines()[-1])
        self.assertEqual(rec["tool"], "run_command")
        self.assertEqual(rec["conversationId"], "c-audit")
        self.assertTrue(rec["ok"])

    def test_audit_truncates_heavy_payload(self):
        big = "A" * 5000
        self.run_hook("post_tool_use.py",
                      {"conversationId": "c-big",
                       "toolCall": {"name": "write_file", "args": {"content": big}}})
        rec = json.loads((self.state_dir / "agy-audit.jsonl").read_text(encoding="utf-8")
                         .strip().splitlines()[-1])
        stored = json.dumps(rec["args"], ensure_ascii=False)
        self.assertLess(len(stored), 600, "大字段没有被压成摘要")
        self.assertIn("sha256", stored)

    def test_audit_marks_failure(self):
        self.run_hook("post_tool_use.py",
                      {"conversationId": "c-err", "error": "exit status 1",
                       "toolCall": {"name": "run_command", "args": {}}})
        rec = json.loads((self.state_dir / "agy-audit.jsonl").read_text(encoding="utf-8")
                         .strip().splitlines()[-1])
        self.assertFalse(rec["ok"])
        self.assertIn("exit status 1", rec.get("error", ""))

    # -- 5. 健壮性 ----------------------------------------------------------
    def test_survives_garbage_input(self):
        for name in ("session_start.py", "pre_invocation.py", "post_tool_use.py"):
            for bad in ("", "not json", "[]", "null", '{"conversationId": null}'):
                p = subprocess.run([PY, str(HOOKS / name)], input=bad,
                                   capture_output=True, text=True, encoding="utf-8",
                                   errors="replace", env=self.env, timeout=30)
                self.assertEqual(p.returncode, 0,
                                 f"{name} 吃到 {bad!r} 时崩了：{p.stderr[:200]}")
                if p.stdout.strip():
                    json.loads(p.stdout)  # 有输出就必须是 JSON

    def test_no_absolute_machine_path_in_hook_scripts(self):
        """钩子脚本本身不能写死本机路径 —— 它是入库的。"""
        for f in HOOKS.glob("*.py"):
            text = f.read_text(encoding="utf-8")
            self.assertNotIn("C:/Users/", text, f"{f.name} 里写死了本机路径")
            self.assertNotIn("C:\\\\Users\\\\", text, f"{f.name} 里写死了本机路径")


if __name__ == "__main__":
    unittest.main(verbosity=2)