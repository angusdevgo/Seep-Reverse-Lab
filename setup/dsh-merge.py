#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DeepSeek Harness (DSH) 持久化挂载器 —— 把 seep MCP 写进 cordis.patch.yml

为什么需要它
------------
`setup/cordis.generated.yml` 只适合 `dsh web --patch ...` 临时挂载。
要在 DSH 里**长期生效**，必须把补丁条目写进：

    $DSH_HOME/profiles/<profile>/cordis.patch.yml   （单个 profile）
    $DSH_HOME/cordis.patch.yml                      （本机所有 profile）

而 `cordis.patch.yml` 里通常已经有用户自己的模型 / provider / 插件配置
（本机就有 `llm-pi-ai` 的 apiKeyEnv、`agent-default-model` 等），
**整文件覆盖会毁掉它们** —— 这正是 setup/mcp-merge.py 解决过的同一类问题。

实现方式
--------
`cordis.patch.yml` 的顶层是「loader patch 条目数组」，而 `cordis.generated.yml`
本身也是一个数组（内含一条 `- insert:`）。所以把生成块原样追加进去就是合法的
合并，不需要 YAML 解析器（Python 标准库没有 YAML）。

为了可重复执行，块用注释标记包裹：

    # >>> seep-workbench (managed block ...)
    ...
    # <<< seep-workbench

已存在则**整块替换**，不存在则追加。你自己的条目一个都不动。

用法
----
    python setup/dsh-merge.py                    # 写入 ~/.dsh/profiles/web/cordis.patch.yml
    python setup/dsh-merge.py --profile main
    python setup/dsh-merge.py --global            # 写 ~/.dsh/cordis.patch.yml
    python setup/dsh-merge.py --check             # 只检查是否已挂载（verify 用）
    python setup/dsh-merge.py --dry-run
    python setup/dsh-merge.py --remove            # 移除标注块，其余配置不动

退出码：0 成功 / `--check` 且已挂载；1 `--check` 且未挂载，或参数/IO 错误。
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import shutil
import subprocess
import sys
import time

BEGIN = "# >>> seep-workbench (managed block — 由 setup/dsh-merge.py 生成，请勿手改)"
END = "# <<< seep-workbench"
BLOCK_RE = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n?", re.S)


def default_dsh_home() -> str:
    env = os.environ.get("DSH_HOME")
    if env:
        return env
    return os.path.join(os.path.expanduser("~"), ".dsh")


def resolve_python(explicit: str | None) -> str:
    """挑一个真的能 `import mcp` 的解释器；都不行就退回显式值或 sys.executable。"""
    if explicit:
        return explicit.replace("\\", "/")
    cands = []
    if os.environ.get("SEEP_PYTHON"):
        cands.append(os.environ["SEEP_PYTHON"])
    home = os.path.expanduser("~")
    cands += [
        os.path.join(home, ".pi", "agent", "seep-venv", "Scripts", "python.exe"),
        os.path.join(home, ".pi", "agent", "seep-venv", "bin", "python"),
    ]
    cands.append(sys.executable)
    for c in cands:
        if not c or not os.path.isfile(c):
            continue
        try:
            r = subprocess.run([c, "-c", "import mcp"], capture_output=True, timeout=20)
            if r.returncode == 0:
                return c.replace("\\", "/")
        except (OSError, subprocess.SubprocessError):
            continue
    return (sys.executable or "python").replace("\\", "/")


def build_block(gen_path: str, python_exe: str, root: str) -> str:
    with io.open(gen_path, "r", encoding="utf-8-sig", newline="") as f:
        body = f.read().replace("\r\n", "\n").rstrip("\n")
    # 生成器写的是 `command: python`（可移植）；落到用户本地配置时换成解析出的绝对路径。
    body = body.replace("        command: python\n",
                        "        command: %s\n" % python_exe)
    return BEGIN + "\n" + body + "\n" + END


def ensure_parent(path: str) -> None:
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d, exist_ok=True)


def backup(path: str) -> str | None:
    if not os.path.isfile(path):
        return None
    d = os.path.join(os.path.dirname(path), "backup-" + time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(d, exist_ok=True)
    dest = os.path.join(d, os.path.basename(path))
    shutil.copy2(path, dest)
    return dest


def write_if_changed(path: str, content: str) -> bool:
    if os.path.isfile(path):
        with io.open(path, "r", encoding="utf-8-sig", newline="") as f:
            cur = f.read()
        if cur.replace("\r\n", "\n") == content:
            return False
    ensure_parent(path)
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)
    return True


def main(argv=None) -> int:
    here = os.path.dirname(os.path.abspath(__file__))
    default_root = os.path.dirname(here)

    ap = argparse.ArgumentParser(description="\u628a seep MCP \u6302\u8f7d\u5230 DSH cordis.patch.yml")
    ap.add_argument("--root", default=default_root, help="\u5de5\u4f5c\u53f0\u6839\u76ee\u5f55")
    ap.add_argument("--dsh-home", default=None, help="\u9ed8\u8ba4 $DSH_HOME \u6216 ~/.dsh")
    ap.add_argument("--profile", default="web", help="\u9ed8\u8ba4 web\uff08\u5bf9\u5e94 ~/.dsh/profiles/web/）")
    ap.add_argument("--global", dest="use_global", action="store_true",
                    help="\u5199 $DSH_HOME/cordis.patch.yml\uff08\u672c\u673a\u6240\u6709 profile\uff09")
    ap.add_argument("--patch-file", default=None, help="\u76f4\u63a5\u6307\u5b9a\u76ee\u6807\u6587\u4ef6\uff08\u6d4b\u8bd5\u7528\uff09")
    ap.add_argument("--python", default=None, help="seep MCP \u4f7f\u7528\u7684\u89e3\u91ca\u5668\u7edd\u5bf9\u8def\u5f84")
    ap.add_argument("--check", action="store_true", help="\u53ea\u68c0\u67e5\u662f\u5426\u5df2\u6302\u8f7d")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--remove", action="store_true", help="\u79fb\u9664\u6807\u6ce8\u5757\uff0c\u5176\u4f59\u914d\u7f6e\u4e0d\u52a8")
    ap.add_argument("--no-backup", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    root = os.path.abspath(args.root).replace("\\", "/").rstrip("/")
    gen = os.path.join(root, "setup", "cordis.generated.yml")
    dsh_home = args.dsh_home or default_dsh_home()

    if args.patch_file:
        target = args.patch_file
    elif args.use_global:
        target = os.path.join(dsh_home, "cordis.patch.yml")
    else:
        target = os.path.join(dsh_home, "profiles", args.profile, "cordis.patch.yml")

    if not os.path.isfile(gen) and not args.remove:
        print("[ERROR] \u751f\u6210\u7269\u4e0d\u5b58\u5728: %s\uff08\u5148\u8fd0\u884c setup/generate-configs.py\uff09" % gen,
              file=sys.stderr)
        return 1

    existing = ""
    if os.path.isfile(target):
        with io.open(target, "r", encoding="utf-8-sig", newline="") as f:
            existing = f.read().replace("\r\n", "\n")

    has_block = bool(BLOCK_RE.search(existing))

    # ---------------- --check ----------------
    if args.check:
        ok = has_block and "serverName: seep" in existing
        info = {
            "target": target,
            "dsh_home_exists": os.path.isdir(dsh_home),
            "patch_exists": os.path.isfile(target),
            "mounted": has_block,
            "has_seep_entry": "serverName: seep" in existing,
        }
        if args.json:
            print(json.dumps(info, ensure_ascii=False))
        else:
            print("  target      : %s" % target)
            print("  DSH_HOME    : %s%s" % (dsh_home, "" if os.path.isdir(dsh_home) else "  (\u4e0d\u5b58\u5728)"))
            print("  patch file  : %s" % ("\u5b58\u5728" if os.path.isfile(target) else "\u4e0d\u5b58\u5728"))
            print("  mounted     : %s" % ("\u662f" if has_block else "\u5426"))
        return 0 if ok else 1

    # ---------------- --remove ----------------
    if args.remove:
        if not has_block:
            print("  result   : \u672a\u627e\u5230\u6807\u6ce8\u5757\uff0c\u65e0\u9700\u79fb\u9664")
            return 0
        new = BLOCK_RE.sub("", existing).rstrip("\n") + "\n"
        if args.dry_run:
            print("  result   : DRY-RUN \u5c06\u79fb\u9664\u6807\u6ce8\u5757")
            return 0
        if not args.no_backup:
            b = backup(target)
            if b:
                print("  backup   : %s" % b)
        write_if_changed(target, new)
        print("  result   : \u5df2\u79fb\u9664\u6807\u6ce8\u5757")
        return 0

    # ---------------- \u6302\u8f7d ----------------
    python_exe = resolve_python(args.python)
    block = build_block(gen, python_exe, root)

    if has_block:
        new = BLOCK_RE.sub(block + "\n", existing)
    else:
        base = existing.rstrip("\n")
        new = (base + "\n\n" if base else "") + block + "\n"

    changed = new != existing
    written = False
    bk = None
    if not args.dry_run and changed:
        if not args.no_backup:
            bk = backup(target)
        written = write_if_changed(target, new)

    if args.json:
        print(json.dumps({
            "target": target, "python": python_exe, "changed": changed,
            "written": written, "backup": bk, "replaced": has_block,
        }, ensure_ascii=False))
        return 0

    print("  target   : %s" % target)
    print("  python   : %s" % python_exe)
    print("  mode     : %s" % ("\u6574\u5757\u66ff\u6362\uff08\u5df2\u5b58\u5728\u6807\u6ce8\u5757\uff09" if has_block else "\u8ffd\u52a0\uff08\u9996\u6b21\u6302\u8f7d\uff09"))
    if bk:
        print("  backup   : %s" % bk)
    if args.dry_run:
        print("  result   : DRY-RUN \u9884\u89c8")
    elif not changed:
        print("  result   : \u672a\u53d8\u5316\uff08\u5185\u5bb9\u4e00\u81f4\uff0c\u672a\u5199\u76d8\uff09")
    else:
        print("  result   : \u5df2\u5199\u5165")
    return 0


if __name__ == "__main__":
    sys.exit(main())
