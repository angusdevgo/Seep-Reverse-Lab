#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""seep MCP stdio 冒烟回归测试（对应 issue #13）。

背景
----
`seep_mcp_server._run_cmd()` 用 `subprocess.run()` 派生子进程时，若没有重定向
`stdin`，在 stdio 传输下子进程会继承 MCP 服务端自己的 stdin —— 那是一条由客户端
（Pi / DSH 等宿主程序）持有、会话结束前不会关闭的管道。子进程卡在
启动阶段，脚本业务代码一行都没执行，工具表现为「永久挂起」直到客户端超时。

受影响的工具都经由 `_run_pe_script()` → `_run_cmd()`：
`seep_pe_triage` / `seep_pe_aob_scan` / `seep_pe_diff` / `seep_pe_patch`。

为什么现有检查发现不了
----------------------
`setup/verify.ps1` 对这个文件只做 `ast.parse` 语法自洽检查，而这样写语法完全合法；
手动在普通 shell 里跑脚本也一切正常（0.09s）。只有真的以 stdio 服务方式运行才暴露。

两层校验
--------
  [1] 静态不变量（--quick 只跑这层，零依赖、毫秒级）
      每一个 `subprocess.run/Popen/call/check_*` 调用点都必须显式给出 `stdin=`。
      删掉修复立刻失败（报出具体行号），适合放进 `check.ps1`。

  [2] 端到端（默认跑）
      真的把服务端作为 stdio MCP 服务拉起，走 initialize → tools/list →
      tools/call（含一次 `seep_pe_triage`）。这是唯一能复现原始故障的层级：
      去掉修复时这条 `tools/call` 会一直挂到超时。

用法
----
    python Tool/mcp/test_stdio_smoke.py          # 全量
    python Tool/mcp/test_stdio_smoke.py --quick  # 只跑静态层

退出码：0 = 通过（依赖缺失导致的 SKIP 也算通过），1 = 失败。

来源
----
本脚本由 @MrUncleXiang 在 PR #14 中贡献，随 issue #13 的修复一并合入 main。
合入时按 v1.9.0 现状做了适配：工具数断言由 27 改为下限判定（当前 38 个），
并接入 setup/verify.ps1 作为常驻检查项。
"""

import ast
import importlib.util
import json
import os
import queue
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.join(HERE, "seep_mcp_server.py")

RPC_TIMEOUT = 60       # 单次 JSON-RPC 往返上限
STARTUP_TIMEOUT = 60   # 服务端启动 + initialize 上限

# 接受 stdin= 参数、且会继承父进程 stdin 的 subprocess 入口。
# getoutput / getstatusoutput 走 shell 且不接受 stdin=，不在此列。
SUBPROCESS_ENTRIES = {"run", "Popen", "call", "check_call", "check_output"}

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


class SmokeFailure(Exception):
    pass


def _say(ok, name, detail=""):
    print("  [{0}] {1}{2}".format("PASS" if ok else "FAIL", name, ("  -> " + detail) if detail else ""))
    return ok


def _skip(name, detail):
    print("  [SKIP] {0}{1}".format(name, ("  -> " + detail) if detail else ""))
    return True


# ---------------------------------------------------------------------------
# [1] 静态不变量
# ---------------------------------------------------------------------------
def check_subprocess_calls_redirect_stdin():
    if not os.path.isfile(SERVER):
        return _skip("subprocess 调用都重定向了 stdin", "找不到 seep_mcp_server.py")

    with open(SERVER, "r", encoding="utf-8", errors="replace") as f:
        source = f.read()
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return _say(False, "subprocess 调用都重定向了 stdin", "文件语法错误：{0}".format(e))

    offenders = []
    total = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr not in SUBPROCESS_ENTRIES:
            continue
        owner = node.func.value
        if (getattr(owner, "id", None) or getattr(owner, "attr", None)) != "subprocess":
            continue
        total += 1
        if not any(kw.arg == "stdin" for kw in node.keywords):
            offenders.append(node.lineno)

    if offenders:
        return _say(False, "subprocess 调用都重定向了 stdin",
                    "第 {0} 行缺少 stdin=（子进程会继承 MCP 的 stdin 并挂起）".format(
                        ", ".join(str(n) for n in sorted(offenders))))
    return _say(True, "subprocess 调用都重定向了 stdin", "{0} 处调用点".format(total))


# ---------------------------------------------------------------------------
# [2] 端到端 stdio 会话
# ---------------------------------------------------------------------------
class StdioClient(object):
    """够用的 JSON-RPC over stdio 客户端，只依赖标准库。"""

    def __init__(self, argv, cwd):
        self.proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        self._lines = queue.Queue()
        self._stderr = []
        self._id = 0
        threading.Thread(target=self._pump_stdout, daemon=True).start()
        threading.Thread(target=self._pump_stderr, daemon=True).start()

    def _pump_stdout(self):
        try:
            for line in self.proc.stdout:
                self._lines.put(line)
        except Exception:
            pass

    def _pump_stderr(self):
        try:
            for line in self.proc.stderr:
                self._stderr.append(line.rstrip())
        except Exception:
            pass

    def _send(self, obj):
        self.proc.stdin.write(json.dumps(obj) + "\n")
        self.proc.stdin.flush()

    def notify(self, method, params=None):
        msg = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            msg["params"] = params
        self._send(msg)

    def request(self, method, params=None, timeout=RPC_TIMEOUT):
        self._id += 1
        rid = self._id
        msg = {"jsonrpc": "2.0", "id": rid, "method": method}
        if params is not None:
            msg["params"] = params
        self._send(msg)

        deadline = time.time() + timeout
        while True:
            remain = deadline - time.time()
            if remain <= 0:
                raise SmokeFailure("{0} 在 {1}s 内没有响应（挂起）。stderr 尾部：\n{2}".format(
                    method, timeout, "\n".join(self._stderr[-6:]) or "<empty>"))
            try:
                line = self._lines.get(timeout=remain)
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
                raise SmokeFailure("{0} 返回错误：{1}".format(method, obj["error"]))
            return obj.get("result")

    def close(self):
        try:
            if self.proc.stdin:
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


def _text_of(result):
    parts = []
    for item in (result or {}).get("content") or []:
        if isinstance(item, dict) and item.get("type") == "text":
            parts.append(item.get("text") or "")
    return "\n".join(parts)


def check_stdio_session():
    # 服务端用 sys.executable 拉起，解释器里没有 mcp 就直接跳过，不要白等超时
    if importlib.util.find_spec("mcp") is None:
        return _skip("stdio 会话", "当前解释器未安装 mcp（先跑 setup/install-python.ps1）")

    client = StdioClient([sys.executable, SERVER], HERE)
    try:
        started = time.time()
        init = client.request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "seep-stdio-smoke", "version": "1.0"},
            },
            timeout=STARTUP_TIMEOUT,
        )
        info = (init or {}).get("serverInfo") or {}
        if not info.get("name"):
            return _say(False, "initialize", "没有返回 serverInfo：{0}".format(init))
        client.notify("notifications/initialized")
        _say(True, "initialize", "{0} {1}（{2:.2f}s）".format(
            info.get("name"), info.get("version", ""), time.time() - started))

        tools = client.request("tools/list")
        names = [t.get("name") for t in (tools or {}).get("tools") or []]
        if len(names) < 20:
            return _say(False, "tools/list", "工具数异常：{0}".format(len(names)))
        if "seep_pe_triage" not in names:
            return _say(False, "tools/list", "缺少 seep_pe_triage")
        _say(True, "tools/list", "{0} 个工具".format(len(names)))

        status = client.request("tools/call", {"name": "seep_status", "arguments": {}})
        if not _text_of(status).strip():
            return _say(False, "tools/call seep_status", "返回空文本")
        _say(True, "tools/call seep_status")

        target = r"C:\Windows\System32\notepad.exe"
        if sys.platform != "win32" or not os.path.isfile(target):
            return _skip("tools/call seep_pe_triage", "非 Windows 或样本缺失")

        began = time.time()
        triage = client.request(
            "tools/call",
            {"name": "seep_pe_triage", "arguments": {"pe_path": target, "no_strings": True}},
            timeout=RPC_TIMEOUT,
        )
        elapsed = time.time() - began
        text = _text_of(triage)
        if "command timed out" in text.lower():
            return _say(False, "tools/call seep_pe_triage",
                        "子进程被 stdin 阻塞，{0:.1f}s 后超时".format(elapsed))
        if not text.strip() or text.lstrip().startswith("[ERROR]"):
            return _say(False, "tools/call seep_pe_triage", text[:160])
        return _say(True, "tools/call seep_pe_triage", "{0:.2f}s".format(elapsed))
    finally:
        client.close()


def main(argv):
    quick = "--quick" in argv

    if not os.path.isfile(SERVER):
        print("[SKIP] 找不到 seep_mcp_server.py：{0}".format(SERVER))
        return 0

    print("=== seep MCP stdio 冒烟（issue #13 回归） ===")
    ok = check_subprocess_calls_redirect_stdin()
    if ok and not quick:
        try:
            ok = check_stdio_session()
        except SmokeFailure as e:
            ok = _say(False, "stdio 会话", str(e))
        except Exception as e:  # noqa: BLE001
            ok = _say(False, "stdio 会话", "{0}: {1}".format(type(e).__name__, e))

    print("")
    print("SMOKE OK" if ok else "SMOKE FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        sys.exit(1)
