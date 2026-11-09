#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Seep 工作台 — DSH 配置文件生成器

本工作台只支持两个 Agent：**Pi Agent** 与 **DeepSeek Harness (DSH)**。
Pi 的接线由 setup/install-pi.ps1 负责（写 mcp.json + 拷技能），与这个脚本无关。

这个脚本只生成 DSH 需要的东西：

  1. `setup/cordis.generated.yml`   DeepSeek Harness 官方 - insert: 补丁（旧挂载路线用）
  2. `AGENTS.md`                    项目根指令入口（DSH 从项目根自动读取）

与 PowerShell 版（generate-configs.ps1）输出逐字节一致。

用法
----
    python setup/generate-configs.py                 # 生成
    python setup/generate-configs.py --print-only    # 只打印，不写盘
    python setup/generate-configs.py --dsh-skills none   # 不挂技能图层
"""

from __future__ import annotations

import argparse
import io
import os
import sys

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

CORDIS_SKILLS = """

# ------------------------------------------------------------------------------
# Skill 图层：开启 DSH 自带的 skill 发现与加载（默认关闭，这里显式打开）
# 代价：10 个技能的 name + description 会进入每个会话的上下文。
# 不想付这个成本，重新生成时关掉该图层即可（详见 MANUAL/DSH-VERIFICATION.md）。
# ------------------------------------------------------------------------------
- id: skill-filesystem
  name: '@deepseek-ai/dsh-skill-filesystem'
  disabled: false
  config:
    customSkillDirs:
      - '{root}/Tool/skill'
      - '{root}/Tool/skill/safe-skills'

- id: tool-skill
  name: '@deepseek-ai/dsh-tool-skill'
  disabled: false"""

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


def generate(root: str, print_only: bool = False, dsh_skills: str = "all") -> dict:
    """生成 DSH 需要的两份产物。返回 {产物名: 路径}。"""
    root = normalize_root(os.path.abspath(root))
    server_py = root + "/Tool/mcp/seep_mcp_server.py"

    print("=" * 80)
    print("          Seep Reverse Lab — DSH 配置文件生成器（Pi 走 install-pi）")
    print("=" * 80)
    print("  检测到工作台物理根目录: %s" % root)
    print("  标准化 POSIX 路径表示: %s" % root)

    print()
    print("[1/2] 正在生成 DeepSeek Harness (DSH) 官方补丁 (cordis.generated.yml)...")
    cordis_dest = os.path.join(root, "setup", "cordis.generated.yml")
    cordis_body = CORDIS_YAML + (CORDIS_SKILLS if dsh_skills == "all" else "")
    cordis_content = cordis_body.replace("{root}", root).replace("{server_py}", server_py)
    if print_only or write_if_changed(cordis_dest, cordis_content, print_only):
        if not print_only:
            print("  [√] 已生成: %s (顶层采用官方 - insert: 语法)" % cordis_dest)

    print()
    print("[2/2] 在项目根生成 AGENTS.md（DSH 自动读取的指令入口）...")
    agents_src = os.path.join(root, "Tool", "prompts", "AGENTS.md")
    agents_dest = os.path.join(root, "AGENTS.md")
    if os.path.isfile(agents_src):
        with io.open(agents_src, "r", encoding="utf-8-sig", newline="") as f:
            agents_body = f.read()
        if print_only or write_if_changed(agents_dest, agents_body, print_only):
            if not print_only:
                print("  [√] 已生成: %s" % agents_dest)
    else:
        print("  [!!] 缺少 Tool/prompts/AGENTS.md，跳过")

    if not print_only:
        print()
        print("" + "=" * 80)
        print("  DSH 配置文件生成完毕！")
        print("  - 推荐装法：python setup/dsh-plugin-setup.py（装插件包，运行时自动挂 MCP）")
        print("  - 旧路线  ：python setup/dsh-merge.py --profile web")
        print("=" * 80)

    return {
        "cordis": cordis_dest,
        "agents": agents_dest,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="生成 DSH 配置与指令入口")
    ap.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    help="工作台根目录（默认：脚本所在仓库）")
    ap.add_argument("--print-only", action="store_true")
    ap.add_argument("--dsh-skills", choices=("all", "none"), default="all")
    args = ap.parse_args(argv)

    if not os.path.isdir(os.path.join(args.root, "Tool")):
        print("[ERROR] 目标不像工作台根目录（缺 Tool/）: %s" % args.root, file=sys.stderr)
        return 2
    generate(args.root, print_only=args.print_only, dsh_skills=args.dsh_skills)
    return 0


if __name__ == "__main__":
    sys.exit(main())
