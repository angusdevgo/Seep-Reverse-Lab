#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 Seep 工作台插件装进 DSH，并把工作台路径写进配置。

为什么需要这个脚本：

    DSH 0.2.2 的插件页对「第三方插件包」不显示自动生成的配置表单
    （只有内置插件才有那种卡片），所以路径没法在网页上直接填。
    用户能改的入口是 设置 → 打开配置文件，但那是手工编辑 YAML。

    这个脚本把「装包 + 写路径」两步一次做完，用户不用碰 YAML。

它做的事情：
    1. 卸掉旧的同名包（file: 安装是硬链接，加了新文件必须重装才生效）
    2. dsh plugin --profile <p> add file:<仓库>/packages/dsh-workbench
    3. 在 profile 的 cordis.patch.yml 里写入/更新：
           - id: seep-workbench-boot
             config:
               repoRoot: '<仓库绝对路径>'
    4. 打印下一步该干什么

用法:
    python setup/dsh-plugin-setup.py                        # 默认 profile=web，仓库=脚本上级
    python setup/dsh-plugin-setup.py --profile tui
    python setup/dsh-plugin-setup.py --root /path/to/Seep-Reverse-Lab
    python setup/dsh-plugin-setup.py --no-skills            # 不在 DSH 里列技能
    python setup/dsh-plugin-setup.py --no-lab-gate          # 关掉 lab 开关
    python setup/dsh-plugin-setup.py --dry-run              # 只看会改什么

退出码: 0 = 装好并写好了；1 = 失败；2 = 找不到 dsh
"""

from __future__ import annotations

import argparse
import io
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
BUNDLE_REL = os.path.join("packages", "dsh-workbench")
PKG_NAME = "seep-dsh-workbench"
ENTRY_ID = "seep-workbench-boot"

# 插件条目在 profile patch 里的起始行
ENTRY_RE = re.compile(r"^- id:\s*" + re.escape(ENTRY_ID) + r"\s*$", re.M)


def dsh_home() -> str:
    env = os.environ.get("DSH_HOME")
    if env and env.strip():
        return env.strip()
    return os.path.join(os.path.expanduser("~"), ".dsh")


def find_dsh():
    for name in ("dsh", "dsh.cmd", "dsh.ps1", "dsh.bat"):
        p = shutil.which(name)
        if p:
            return p
    return None


def run(cmd, timeout=300):
    env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        p = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace",
                           timeout=timeout, env=env, shell=False)
        return p.returncode, (p.stdout or ""), (p.stderr or "")
    except subprocess.TimeoutExpired:
        return None, "", "超时 %ds" % timeout
    except Exception as exc:  # noqa: BLE001
        return None, "", str(exc)


def quote_yaml(value: str) -> str:
    """单引号包住，内部的单引号双写。单引号里的反斜杠是字面量，正合 Windows 路径。"""
    return "'" + str(value).replace("'", "''") + "'"


def build_entry(root: str, skills: bool, lab_gate: bool) -> str:
    lines = [
        "- id: %s" % ENTRY_ID,
        "  config:",
        "    repoRoot: %s" % quote_yaml(root),
    ]
    if not skills:
        lines.append("    enableSkills: false")
    if not lab_gate:
        lines.append("    labGate: false")
    return "\n".join(lines) + "\n"


def splice(text: str, entry: str) -> tuple[str, str]:
    """把条目写进 patch 文本。返回 (新文本, 动作说明)。"""
    m = ENTRY_RE.search(text)
    if m is None:
        # 没有就追加。profile patch 顶层是 YAML 数组，追加一个列表项是合法的。
        body = text.rstrip("\n")
        # 只看非注释、非空行：模板可能写的是“注释 + []”
        meaningful = [ln for ln in body.splitlines()
                      if ln.strip() and not ln.lstrip().startswith("#")]
        if meaningful in ([], ["[]"]):
            # 模板里的空数组要换掉，否则会得到 "[]\n- id: ..."（YAML 非法）
            header = [ln for ln in text.splitlines() if ln.lstrip().startswith("#")]
            head = "\n".join(header)
            new = (head + "\n\n" if head else "") + entry
            return new, "新建条目（原文件是空数组）"
        return body + "\n\n" + entry, "追加条目"

    # 已有条目：从它开始，替换到下一个顶层列表项之前
    start = m.start()
    tail = text[m.end():]
    stop = len(text)
    for mm in re.finditer(r"^- \S", tail, re.M):
        stop = m.end() + mm.start()
        break
    return text[:start] + entry + text[stop:], "更新已有条目"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="把 Seep 工作台插件装进 DSH 并写好路径")
    ap.add_argument("--profile", default="web")
    ap.add_argument("--root", default=REPO, help="工作台仓库绝对路径（默认：本脚本的上级目录）")
    ap.add_argument("--no-skills", action="store_true", help="不在 DSH 里列出技能")
    ap.add_argument("--no-lab-gate", action="store_true", help="关掉 lab 开关")
    ap.add_argument("--dry-run", action="store_true", help="只打印，不实际改动")
    args = ap.parse_args(argv)

    root = os.path.abspath(args.root)
    bundle = os.path.join(root, BUNDLE_REL)

    print()
    print("=" * 70)
    print("  Seep 工作台 → DeepSeek Harness 插件安装")
    print("=" * 70)
    print("  仓库    : %s" % root)
    print("  插件包  : %s" % bundle)
    print("  DSH_HOME: %s" % dsh_home())
    print("  profile : %s" % args.profile)
    print()

    if not os.path.isfile(os.path.join(bundle, "package.json")):
        print("  [FAIL] 找不到插件包：%s" % bundle)
        print("         这个脚本必须在仓库里跑（packages/dsh-workbench 要存在）。")
        return 1
    if not os.path.isfile(os.path.join(root, "Tool", "mcp", "seep_mcp_server.py")):
        print("  [FAIL] %s 不像工作台（缺 Tool/mcp/seep_mcp_server.py）" % root)
        return 1

    dsh = find_dsh()
    if dsh is None:
        print("  [FAIL] PATH 里找不到 dsh。先装 DeepSeek Harness 再来。")
        return 2

    # 1) 装包。file: 是硬链接，升级时必须 remove 再 add，否则新加的文件不会出现。
    if args.dry_run:
        print("  [dry-run] 会执行：dsh plugin --profile %s remove %s" % (args.profile, PKG_NAME))
        print("  [dry-run] 会执行：dsh plugin --profile %s add file:%s" % (args.profile, bundle))
    else:
        rc, _, err = run([dsh, "plugin", "--profile", args.profile, "remove", PKG_NAME])
        # 没装过时 remove 会失败，属于正常情况，不当错误
        if rc != 0 and "not" not in (err or "").lower():
            print("  [warn] 卸载旧包没成功（通常说明本来就没装）：%s" % (err or "").strip()[:120])

        print("  正在装包 …")
        rc, out, err = run([dsh, "plugin", "--profile", args.profile, "add", "file:" + bundle])
        if rc != 0:
            print("  [FAIL] 装包失败：")
            for line in ((err or out or "").strip().splitlines()[:8]):
                print("         %s" % line)
            return 1
        print("  [ok] 插件包装好了")

    # 2) 写路径
    patch_dir = os.path.join(dsh_home(), "profiles", args.profile)
    patch = os.path.join(patch_dir, "cordis.patch.yml")
    entry = build_entry(root, skills=not args.no_skills, lab_gate=not args.no_lab_gate)

    if not os.path.isdir(patch_dir):
        print("  [FAIL] profile 目录不存在：%s" % patch_dir)
        print("         先跑一次 dsh --profile %s，让它把 profile 建出来。" % args.profile)
        return 1

    old = ""
    if os.path.isfile(patch):
        old = io.open(patch, encoding="utf-8", errors="replace").read()
    new, action = splice(old, entry)

    print()
    print("  将要写入 %s：" % patch)
    for line in entry.rstrip("\n").splitlines():
        print("    | %s" % line)
    print("  动作：%s" % action)

    if args.dry_run:
        print("\n  [dry-run] 到此为止，没有改任何文件。")
        return 0

    if new != old:
        if old:
            backup = patch + ".bak"
            io.open(backup, "w", encoding="utf-8", newline="\n").write(old)
            print("  [ok] 旧配置备份到 %s" % backup)
        io.open(patch, "w", encoding="utf-8", newline="\n").write(new)
        print("  [ok] 路径已写入")
    else:
        print("  [ok] 配置内容没变，无需改写")

    print()
    print("-" * 70)
    print("  下一步：")
    print("    1. 重启 DSH（关掉再开），插件会在启动时挂上 MCP 和技能")
    print("    2. 检查是否接上：python setup/verify-dsh.py")
    print("    3. 想改路径：重跑本脚本并加 --root <新路径>，或改 %s" % patch)
    print()
    print("  注意：这个 DSH 版本的插件页不给第三方包显示配置表单，")
    print("        所以路径只能这样写进去 —— 不是在网页上填。")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
