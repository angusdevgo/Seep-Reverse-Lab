#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Seep 工作台 — 各 Agent 配置文件生成器（跨平台，纯标准库）

与 `setup/generate-configs.ps1` 输出**逐字节一致**（由 `setup/test_config_parity.py` 守住）。

生成三份产物：
  1. `.mcp.json`                    Claude Code 项目级配置（相对路径，可移植、可入库）
  2. `opencode.jsonc`               OpenCode 官方 mcp 顶层 + 数组 command 格式
  3. `setup/cordis.generated.yml`   DeepSeek Harness 官方 `- insert:` Overlay 补丁

工程约定：
  · 一律 LF、UTF-8 无 BOM；**不写结尾换行**（与 PowerShell here-string 行为一致）
  · 内容未变化则不写盘 —— 重写同一份字节会让 mtime 变化，git 的 stat 缓存失效，
    `git status` 会把「内容完全相同」的文件报成已修改，update 脚本于是每次都
    弹一次「本地改动已 stash」的警告。见 commit eade7b1。

用法:
    python setup/generate-configs.py             # 生成到工作台根目录
    python setup/generate-configs.py --print-only  # 只打印，不写盘
    python setup/generate-configs.py --root <dir>  # 指定工作台根（测试用）
"""

from __future__ import annotations

import argparse
import io
import os
import sys

# ---------------------------------------------------------------------------
# 模板（与 generate-configs.ps1 严格对应，改动必须两边同步）
# ---------------------------------------------------------------------------

CLAUDE_MCP_JSON = """{
  "mcpServers": {
    "seep": {
      "command": "python",
      "args": [
        "Tool/mcp/seep_mcp_server.py"
      ],
      "env": {
        "PYTHONIOENCODING": "utf-8"
      },
      "transport": "stdio"
    },
    "js-reverse": {
      "command": "npx",
      "args": [
        "-y",
        "js-reverse-mcp"
      ],
      "transport": "stdio"
    }
  }
}"""

OPENCODE_JSONC = """{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "seep": {
      "type": "local",
      "command": [
        "python",
        "{server_py}"
      ],
      "enabled": true,
      "environment": {
        "PYTHONIOENCODING": "utf-8"
      }
    }
  }
}"""

CORDIS_YAML = """# ==============================================================================
# DeepSeek Harness (Cordis) Overlay 补丁 — 遵循 DSH 官方 - insert: 规范
# 生成基准目录: {root}
#
# 挂载方式（二选一）:
#   1. 临时挂载: dsh web --patch "{root}/setup/cordis.generated.yml"
#   2. 持久挂载: python setup/dsh-merge.py --profile web
#      幂等写入 $DSH_HOME/profiles/<profile>/cordis.patch.yml，
#      只替换标注块，你自己的模型/插件配置原样保留。
#
# 关于 toolCallTimeoutMs：必须显式设置。DSH 的默认值是 60000（60 秒），
# 而工作台的长任务远超这个量级 —— HLS 取证（ffmpeg 解密分片）、Flutter AOT
# 分析、jadx 全量反编译都可能跑几分钟。不设就必然被 DSH 按超时中断。
# ==============================================================================
- insert:
    - id: seep-mcp
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: seep
        transport: stdio
        command: python
        args:
          - '{server_py}'
        env:
          PYTHONIOENCODING: utf-8
        cwd: '{root}'
        toolCallTimeoutMs: 900000
        failOnStartupError: false

    - id: seep-js-reverse-mcp
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: js-reverse
        transport: stdio
        command: npx
        args:
          - '-y'
          - 'js-reverse-mcp'
        cwd: '{root}'
        toolCallTimeoutMs: 600000
        failOnStartupError: false"""


def normalize_root(path: str) -> str:
    """统一成 POSIX 正斜杠表示，与 PowerShell 版 `$Root.Replace('\\', '/')` 对齐。"""
    return path.replace("\\", "/").rstrip("/")


def write_if_changed(path: str, content: str, print_only: bool = False) -> bool:
    """内容不变就不写盘。返回是否真的写了。"""
    normalized = content.replace("\r\n", "\n")
    if print_only:
        print(normalized)
        return False
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8-sig", newline="") as f:
                existing = f.read()
            if existing.replace("\r\n", "\n") == normalized:
                print("  [=] \u5185\u5bb9\u672a\u53d8\u5316\uff0c\u8df3\u8fc7\u5199\u5165: %s" % path)
                return False
        except OSError:
            pass
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(normalized)
    return True


def generate(root: str, print_only: bool = False) -> dict:
    """生成三份配置。返回 {产物名: 路径}。"""
    root = normalize_root(os.path.abspath(root))
    server_py = root + "/Tool/mcp/seep_mcp_server.py"

    print("=" * 80)
    print("          Seep Reverse Lab \u2014 \u591a Agent \u914d\u7f6e\u6587\u4ef6\u751f\u6210\u4e0e\u81ea\u6108\u5668")
    print("=" * 80)
    print("  \u68c0\u6d4b\u5230\u5de5\u4f5c\u53f0\u7269\u7406\u6839\u76ee\u5f55: %s" % root)
    print("  \u6807\u51c6\u5316 POSIX \u8def\u5f84\u8868\u793a: %s" % root)

    print("\n[1/4] \u6b63\u5728\u751f\u6210 Claude Code \u9879\u76ee\u7ea7\u914d\u7f6e (.mcp.json)...")
    claude_dest = os.path.join(root, ".mcp.json")
    if print_only or write_if_changed(claude_dest, CLAUDE_MCP_JSON, print_only):
        if not print_only:
            print("  [\u221a] \u5df2\u66f4\u65b0: %s" % claude_dest)

    print("\n[2/4] \u6b63\u5728\u751f\u6210 OpenCode \u5b98\u65b9\u6807\u51c6\u914d\u7f6e (opencode.jsonc)...")
    opencode_dest = os.path.join(root, "opencode.jsonc")
    opencode_content = OPENCODE_JSONC.replace("{server_py}", server_py)
    if print_only or write_if_changed(opencode_dest, opencode_content, print_only):
        if not print_only:
            print("  [\u221a] \u5df2\u66f4\u65b0: %s (\u7b26\u5408 OpenCode \u5b98\u65b9 mcp \u9876\u5c42\u4e0e\u6570\u7ec4 command \u6807\u51c6)" % opencode_dest)

    print("\n[3/4] \u6b63\u5728\u751f\u6210 DeepSeek Harness (DSH) \u5b98\u65b9\u8865\u4e01 (cordis.generated.yml)...")
    cordis_dest = os.path.join(root, "setup", "cordis.generated.yml")
    cordis_content = CORDIS_YAML.replace("{root}", root).replace("{server_py}", server_py)
    if print_only or write_if_changed(cordis_dest, cordis_content, print_only):
        if not print_only:
            print("  [\u221a] \u5df2\u751f\u6210: %s (\u9876\u5c42\u91c7\u7528\u5b98\u65b9 - insert: \u8bed\u6cd5)" % cordis_dest)

    print("\n[4/4] \u5728\u9879\u76ee\u6839\u751f\u6210 AGENTS.md\uff08\u4f9b DSH / Codex \u81ea\u52a8\u8bfb\u53d6\uff09...")
    agents_src = os.path.join(root, "Tool", "prompts", "AGENTS.md")
    agents_dest = os.path.join(root, "AGENTS.md")
    if os.path.isfile(agents_src):
        with io.open(agents_src, "r", encoding="utf-8-sig", newline="") as f:
            agents_body = f.read()
        if print_only or write_if_changed(agents_dest, agents_body, print_only):
            if not print_only:
                print("  [\u221a] \u5df2\u751f\u6210: %s" % agents_dest)
    else:
        print("  [!!] \u7f3a\u5c11 Tool/prompts/AGENTS.md\uff0c\u8df3\u8fc7")

    if not print_only:
        print("\n" + "=" * 80)
        print("  \U0001f389 \u6240\u6709 Agent \u914d\u7f6e\u6587\u4ef6\u751f\u6210\u5b8c\u6bd5\uff01")
        print("  - OpenCode: \u76f4\u63a5\u542f\u52a8 opencode\uff0c\u81ea\u52a8\u8bc6\u522b\u6839\u76ee\u5f55 opencode.jsonc")
        print("  - DSH: \u53ef\u6267\u884c dsh web --patch \"%s/setup/cordis.generated.yml\"" % root)
        print("=" * 80)

    return {
        "claude": claude_dest,
        "opencode": opencode_dest,
        "cordis": cordis_dest,
        "agents": agents_dest,
    }


def main(argv=None) -> int:
    default_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ap = argparse.ArgumentParser(description="Seep \u591a Agent \u914d\u7f6e\u751f\u6210\u5668\uff08\u8de8\u5e73\u53f0\uff09")
    ap.add_argument("--root", default=default_root, help="\u5de5\u4f5c\u53f0\u6839\u76ee\u5f55\uff08\u9ed8\u8ba4\u811a\u672c\u4e0a\u4e00\u5c42\uff09")
    ap.add_argument("--print-only", action="store_true", help="\u53ea\u6253\u5370\uff0c\u4e0d\u5199\u76d8")
    args = ap.parse_args(argv)

    if not os.path.isdir(os.path.join(args.root, "Tool")):
        print("[ERROR] \u76ee\u6807\u4e0d\u50cf\u5de5\u4f5c\u53f0\u6839\u76ee\u5f55\uff08\u7f3a Tool/\uff09: %s" % args.root,
              file=sys.stderr)
        return 2
    generate(args.root, print_only=args.print_only)
    return 0


if __name__ == "__main__":
    sys.exit(main())
