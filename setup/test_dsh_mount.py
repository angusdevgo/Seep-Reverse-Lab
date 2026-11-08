#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DSH 挂载端到端校验：从 DSH 自己的配置树里取出 seep 条目，再真的把它跑起来

为什么需要这个测试
------------------
`setup/dsh-merge.py` 只是把补丁块写进 `cordis.patch.yml`，格式对不对、DSH 认不认、
拼装出来的 command/args 能不能真的拉起 MCP 服务 —— 这些都要端到端验证，
光看 YAML 长得像是不够的（我们已经栽过一次：`toolCallTimeoutMs` 没设，
DSH 默认 60 秒，长任务必然被掐断）。

流程
----
  1. `dsh --profile <p> --dump-config` —— 让 DSH 的 loader 自己合成配置树
  2. 从合成结果里取 `serverName: seep` 那一项的 command / args / cwd / env
  3. 校验 command 与 args[0] 在磁盘上存在
  4. 用这份**合成后的**配置真的 spawn 一次，走 initialize → tools/list
  5. 断言工具数 ≥ 30 且包含 seep_pe_triage

dsh 未安装、profile 不存在、或未挂载时 SKIP（不判失败）。

用法:
    python setup/test_dsh_mount.py
    python setup/test_dsh_mount.py --profile web
退出码: 0 通过或 SKIP / 1 失败
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

FAILS = []


def check(cond, name, detail=""):
    if cond:
        print("  [PASS] %s" % name)
    else:
        print("  [FAIL] %s%s" % (name, ("  -> " + detail) if detail else ""))
        FAILS.append(name)
    return cond


def skip(name, detail=""):
    print("  [SKIP] %s%s" % (name, ("  -> " + detail) if detail else ""))
    return True


# ---------------------------------------------------------------------------
# 1. 取 DSH 合成后的配置树
# ---------------------------------------------------------------------------
def dump_config(profile: str) -> str | None:
    # 注意：Windows 上的 dsh 是 .CMD 垫片，subprocess 不会自己做 PATHEXT 查找，
    # 直接传 "dsh" 会报 WinError 2；必须先用 shutil.which 解析成完整路径。
    dsh_bin = shutil.which("dsh")
    if not dsh_bin:
        print("  [SKIP] dsh 不在 PATH")
        return None
    try:
        proc = subprocess.run(
            [dsh_bin, "--profile", profile, "--dump-config"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        print("  [SKIP] 无法执行 dsh：%s" % exc)
        return None
    if proc.returncode != 0:
        print("  [SKIP] dsh --dump-config 返回 %d：%s"
              % (proc.returncode, (proc.stderr or "")[:300]))
        return None
    return proc.stdout


def find_seep_entry(text: str):
    """在 dump-config 的 YAML 文本里定位 serverName: seep 的条目。

    不引入 YAML 依赖：dump-config 是规整的块状 YAML，按缩进扫描即可。
    """
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip() != "serverName: seep":
            continue
        # 向上找最近的 "- id:" 起点
        start = i
        while start > 0 and not lines[start].lstrip().startswith("- id:"):
            start -= 1
        # 向下收集到下一个同级 "- id:"
        base_indent = len(lines[start]) - len(lines[start].lstrip())
        end = len(lines)
        for j in range(i + 1, len(lines)):
            cur = lines[j]
            if not cur.strip():
                continue
            ind = len(cur) - len(cur.lstrip())
            if ind == base_indent and cur.lstrip().startswith("- id:"):
                end = j
                break
        return lines[start:end]
    return None


def parse_block(block):
    """从条目块里抽出 command / args / cwd / env。"""
    command, args, cwd = None, [], None
    in_args = False
    for raw in block:
        s = raw.strip()
        if s.startswith("command:") and command is None:
            command = s.split(":", 1)[1].strip().strip("'\"")
        elif s.startswith("cwd:"):
            cwd = s.split(":", 1)[1].strip().strip("'\"")
        elif s == "args:":
            in_args = True
        elif in_args:
            if s.startswith("- "):
                val = s[2:].strip()
                if val in (">-", ">", "|", "|-"):
                    continue          # block scalar 标记，值在下一行
                args.append(val.strip("'\""))
            elif s and not s.startswith("-"):
                # 形如 "    C:/...py" 的续行（YAML folded scalar）
                args.append(s.strip("'\""))
                in_args = False
    return command, args, cwd


# ---------------------------------------------------------------------------
# 2. 最小 stdio MCP 客户端
# ---------------------------------------------------------------------------
class StdioClient(object):
    def __init__(self, argv, cwd, env):
        self.proc = subprocess.Popen(
            argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, cwd=cwd, env=env, text=True,
            encoding="utf-8", errors="replace", bufsize=1,
        )
        self.q = queue.Queue()
        self.err = []
        self.rid = 0
        threading.Thread(target=self._pump, daemon=True).start()
        threading.Thread(target=self._pump_err, daemon=True).start()

    def _pump(self):
        try:
            for line in self.proc.stdout:
                self.q.put(line)
        except Exception:
            pass

    def _pump_err(self):
        try:
            for line in self.proc.stderr:
                self.err.append(line.rstrip())
        except Exception:
            pass

    def request(self, method, params=None, timeout=60):
        self.rid += 1
        rid = self.rid
        msg = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            msg["params"] = params
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()
        deadline = time.time() + timeout
        while True:
            remain = deadline - time.time()
            if remain <= 0:
                raise TimeoutError("%s \u8d85\u65f6\uff1bstderr\uff1a%s"
                                   % (method, "\n".join(self.err[-5:])))
            try:
                line = self.q.get(timeout=remain)
            except queue.Empty:
                continue
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if obj.get("id") != rid:
                continue
            if "error" in obj:
                raise RuntimeError("%s \u8fd4\u56de\u9519\u8bef\uff1a%s" % (method, obj["error"]))
            return obj.get("result")

    def close(self):
        try:
            self.proc.stdin.close()
        except Exception:
            pass
        try:
            self.proc.wait(timeout=10)
        except Exception:
            try:
                self.proc.kill()
            except Exception:
                pass


# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="DSH \u6302\u8f7d\u7aef\u5230\u7aef\u6821\u9a8c")
    ap.add_argument("--profile", default="web")
    args = ap.parse_args(argv)

    if not shutil.which("dsh"):
        return skip("DSH \u5df2\u5b89\u88c5", "dsh \u4e0d\u5728 PATH") and 0

    print("=== DSH \u6302\u8f7d\u7aef\u5230\u7aef\u6821\u9a8c (profile=%s) ===" % args.profile)

    text = dump_config(args.profile)
    if text is None:
        return 0

    block = find_seep_entry(text)
    if not block:
        check(False, "DSH \u5408\u6210\u914d\u7f6e\u91cc\u627e\u5230 serverName: seep",
              "\u5c1a\u672a\u6302\u8f7d\uff1b\u8fd0\u884c python setup/dsh-merge.py --profile %s" % args.profile)
        print("\nDSH MOUNT FAILED")
        return 1
    check(True, "DSH \u5408\u6210\u914d\u7f6e\u91cc\u627e\u5230 serverName: seep")

    command, argv_list, cwd = parse_block(block)
    check(bool(command), "command \u5df2\u8bbe\u7f6e", str(command))
    check(bool(argv_list), "args \u5df2\u8bbe\u7f6e", str(argv_list))
    if not (command and argv_list):
        print("\nDSH MOUNT FAILED")
        return 1

    # block scalar 折行时 args 可能只有一项（脚本路径），命令就是 command
    cmd_on_disk = os.path.isfile(command) or shutil.which(command)
    check(bool(cmd_on_disk), "command \u5728\u78c1\u76d8\u4e0a\u5b58\u5728", command)
    script = argv_list[0]
    check(os.path.isfile(script), "\u670d\u52a1\u7aef\u811a\u672c\u5b58\u5728", script)
    if not (cmd_on_disk and os.path.isfile(script)):
        print("\nDSH MOUNT FAILED")
        return 1

    # ---- 用合成后的配置真的把它跑起来
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    client = StdioClient([command] + argv_list, cwd or ROOT, env)
    try:
        init = client.request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "seep-dsh-mount", "version": "1.0"},
        }, timeout=90)
        name = ((init or {}).get("serverInfo") or {}).get("name")
        check(bool(name), "\u6309 DSH \u5408\u6210\u914d\u7f6e\u80fd initialize", str(name))

        tools = client.request("tools/list", timeout=90)
        names = [t.get("name") for t in (tools or {}).get("tools") or []]
        check(len(names) >= 30, "tools/list \u8fd4\u56de \u226530 \u4e2a\u5de5\u5177", str(len(names)))
        check("seep_pe_triage" in names, "tools/list \u5305\u542b seep_pe_triage")
        print("      \u5de5\u5177\u6570\uff1a%d\uff08DSH \u4e2d\u5bf9\u5916\u540d\u4e3a mcp__seep__<tool>\uff09" % len(names))
    except (TimeoutError, RuntimeError, OSError) as exc:
        check(False, "\u6309 DSH \u5408\u6210\u914d\u7f6e\u542f\u52a8 MCP \u670d\u52a1", str(exc)[:300])
    finally:
        client.close()

    print("")
    if FAILS:
        print("DSH MOUNT FAILED (%d)" % len(FAILS))
        return 1
    print("DSH MOUNT OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
