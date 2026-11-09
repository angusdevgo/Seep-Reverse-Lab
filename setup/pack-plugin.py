#!/usr/bin/env python3
"""把插件打成一个可以直接安装的 .tgz。

用法
----
    python setup/pack-plugin.py                 # 打包，输出到 dist/
    python setup/pack-plugin.py --check         # 只检查版本一致性，不打包
    python setup/pack-plugin.py --out D:/tmp    # 指定输出目录

**这个脚本不发布**，只产出文件并打印校验和。发布动作永远由人来做：

    npm publish packages/dsh-workbench
    # 或者把 tgz 传到 GitHub Release 当备用通道

为什么不用 `npm pack`
--------------------
`npm pack` 会带上 registry 的元数据行为，也依赖 npm 版本。这里只做一件事：
按 `files` 字段列出的内容打一个标准 npm 包（顶层 `package/` 目录 + gzip）。
标准库就够，任何机器都能跑。
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import sys
import tarfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
PKG_DIR = os.path.join(REPO, "packages", "dsh-workbench")

# 和 package.json 的 files 保持一致：只有这些进包
DEFAULT_FILES = ["package.json", "cordis.patch.yml", "README.md", "lib"]

# 绝不能进包的东西（本机路径、凭据、体积巨大的东西）
FORBIDDEN_NAMES = {".git", "node_modules", ".env", "auth.json", "models.json", ".credentials.yaml"}
FORBIDDEN_SUFFIXES = (".log", ".tgz", ".pyc")


def read_json(path: str) -> dict:
    with io.open(path, encoding="utf-8") as fh:
        return json.load(fh)


def check_versions() -> tuple[bool, list[str]]:
    """三处版本号必须一致：VERSION / 包 package.json / CHANGELOG 最新标题。"""
    problems: list[str] = []

    version_file = os.path.join(REPO, "VERSION")
    repo_version = ""
    if os.path.isfile(version_file):
        repo_version = io.open(version_file, encoding="utf-8").read().strip()

    pkg = read_json(os.path.join(PKG_DIR, "package.json"))
    pkg_version = str(pkg.get("version", "")).strip()

    if repo_version and pkg_version and repo_version != pkg_version:
        problems.append(
            "版本不一致：VERSION=%s，插件 package.json=%s（两处要一样）" % (repo_version, pkg_version)
        )
    if not pkg_version:
        problems.append("插件 package.json 没有 version")
    if pkg.get("private") is True:
        problems.append("package.json 里还是 private: true，npm 会拒绝发布")

    changelog = os.path.join(REPO, "CHANGELOG.md")
    if os.path.isfile(changelog):
        head = io.open(changelog, encoding="utf-8").read()[:4000]
        if pkg_version and pkg_version not in head:
            problems.append(
                "CHANGELOG 里没有 %s 这个版本号（发布记录要跟上）" % pkg_version
            )

    return (not problems), problems


def collect(base: str, entries: list[str]) -> list[tuple[str, str]]:
    """把 files 字段展开成 (磁盘绝对路径, 包内相对路径) 列表。"""
    out: list[tuple[str, str]] = []
    for entry in entries:
        full = os.path.join(base, entry.replace("/", os.sep))
        if os.path.isfile(full):
            out.append((full, entry))
        elif os.path.isdir(full):
            for root, dirs, files in os.walk(full):
                dirs[:] = [d for d in dirs if d not in FORBIDDEN_NAMES]
                for name in files:
                    if name in FORBIDDEN_NAMES or name.endswith(FORBIDDEN_SUFFIXES):
                        continue
                    path = os.path.join(root, name)
                    rel = os.path.relpath(path, base).replace(os.sep, "/")
                    out.append((path, rel))
        else:
            raise FileNotFoundError("package.json 的 files 里写了不存在的东西：%s" % entry)
    return out


def build(out_dir: str) -> str:
    pkg = read_json(os.path.join(PKG_DIR, "package.json"))
    version = str(pkg["version"])
    name = str(pkg["name"])
    # package.json 一定要进包（npm publish 会自带，我们自己打包就得手动加），
    # 否则装上会提示 "declares no dsh.bundle" —— DSH 读不到它的声明。
    files = ["package.json"]
    for entry in pkg.get("files") or DEFAULT_FILES:
        if entry not in files:
            files.append(entry)

    pairs = collect(PKG_DIR, files)
    os.makedirs(out_dir, exist_ok=True)
    target = os.path.join(out_dir, "%s-%s.tgz" % (name, version))

    # npm 包格式：tar.gz，内部所有路径都在 package/ 下面
    with tarfile.open(target, "w:gz", format=tarfile.GNU_FORMAT) as tar:
        for disk_path, rel in pairs:
            info = tar.gettarinfo(disk_path, arcname="package/" + rel)
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.mtime = int(time.time())
            with io.open(disk_path, "rb") as fh:
                tar.addfile(info, fh)

    size = os.path.getsize(target)
    digest = hashlib.sha256(io.open(target, "rb").read()).hexdigest()

    print("  包名   : %s@%s" % (name, version))
    print("  文件数 : %d" % len(pairs))
    for _, rel in sorted(pairs, key=lambda x: x[1]):
        print("           %s" % rel)
    print("  体积   : %.1f KB" % (size / 1024.0))
    print("  sha256 : %s" % digest)
    print("  输出   : %s" % target)
    print()
    print("  安装：dsh plugin add --profile web \"file:%s\"" % target)
    print("  发布：npm publish packages/dsh-workbench")
    return target


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="打插件包（不发布）")
    ap.add_argument("--check", action="store_true", help="只检查版本一致性")
    ap.add_argument("--out", default=os.path.join(REPO, "dist"), help="输出目录")
    args = ap.parse_args(argv)

    print("  Seep 工作台 · DSH 插件打包")
    print("  " + "-" * 60)

    ok, problems = check_versions()
    if problems:
        for p in problems:
            print("  [FAIL] %s" % p)
        if args.check:
            return 1
        print()
        print("  版本对不上先改好再打包（--check 可单独跑）。")
        return 1
    print("  [ok] 版本与 CHANGELOG 一致")

    if args.check:
        return 0

    try:
        build(args.out)
    except (OSError, ValueError, KeyError) as exc:
        print("  [FAIL] 打包失败：%s" % exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
