#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Seep 工作台 —— 合规转译中继 (compliance-relay)

把「敏感口语 → 合规术语」的转译从「Agent 插件能力」下沉为「网络传输能力」，
从而一次性覆盖任意支持自定义 baseUrl 的 Agent（Pi Agent / Claude Code / Codex 等）。

设计原则
--------
1. 零新增依赖：纯 Python 标准库实现（http.server + http.client + json + re）。
2. 单趟最长优先：单次正则扫描，替换产物不回扫，杜绝 A→B、B→C 级联失控。
3. 上下文守卫：Agent 自注入的上下文（环境、AGENTS.md、技能清单）绝不被改写。
4. 零落盘：绝不记录请求体 / 响应体 / 鉴权头，日志只输出命中条数。
5. Lab Mode 联动：~/.pi/agent/lab-mode.flag 存在才改写，mtime 热加载。

用法
----
    python relay.py                     # 启动中继（默认 127.0.0.1:17890）
    python relay.py --scan-pi           # 从 ~/.pi/agent/models.json 生成 upstream 映射
    python relay.py --force-on          # 强制启用改写（排障用）
    python relay.py --force-off         # 强制关闭改写（A/B 对比用）
    python relay.py --port 17891        # 覆盖端口
"""

from __future__ import annotations

import argparse
import json
import os
import re
import secrets
import sys
import threading
from http.client import HTTPConnection, HTTPSConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

HERE = os.path.dirname(os.path.abspath(__file__))
RULES_FILE = os.path.join(HERE, "sensitive-rules.json")
GUARDS_FILE = os.path.join(HERE, "guard-prefixes.json")
CONFIG_FILE = os.path.join(HERE, "relay-config.json")

DEFAULT_PORT = 17890
DEFAULT_LAB_FLAG = os.path.join(
    os.path.expanduser("~"), ".pi", "agent", "lab-mode.flag"
)
DEFAULT_PI_MODELS = os.path.join(
    os.path.expanduser("~"), ".pi", "agent", "models.json"
)

# 逐跳头：不可透传
HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}

# 请求头中需要重写的项
REQUEST_HEADER_DROP = {"host", "content-length", "accept-encoding"}

CHUNK_SIZE = 8192


# =============================================================================
# 1. 规则匹配引擎
# =============================================================================
class Matcher:
    """单趟最长优先的字面替换引擎。

    - 单次正则扫描 → 替换产物不会被再次匹配（不回扫）
    - alternation 按长度降序排列 → 同一位置取最长规则（LeftmostLongest 语义）
    """

    def __init__(self, rules: list[dict]):
        mapping: dict[str, str] = {}
        for rule in rules:
            src = rule.get("from")
            dst = rule.get("to")
            if not isinstance(src, str) or not src:
                continue
            if not isinstance(dst, str):
                continue
            mapping.setdefault(src, dst)
        self.mapping = mapping
        if not mapping:
            self._pattern = None
            return
        ordered = sorted(mapping.keys(), key=len, reverse=True)
        self._pattern = re.compile("|".join(re.escape(k) for k in ordered))

    @property
    def is_empty(self) -> bool:
        return self._pattern is None

    def rewrite(self, text: str) -> tuple[str, int]:
        """返回 (改写后文本, 命中条数)。无命中时原样返回。"""
        if self._pattern is None or not text:
            return text, 0
        if is_slash_command(text):
            return text, 0
        counter = {"n": 0}

        def _repl(match: re.Match) -> str:
            counter["n"] += 1
            return self.mapping[match.group(0)]

        out = self._pattern.sub(_repl, text)
        return (out, counter["n"]) if counter["n"] else (text, 0)


def is_slash_command(text: str) -> bool:
    """以 / 开头（去前导空白后）视为斜杠命令，整条跳过。"""
    return text.lstrip().startswith("/")


def rewrite_with_guard(
    text: str, matcher: Matcher, guard: dict
) -> tuple[str, int]:
    """带上下文守卫的改写。返回 (文本, 命中条数)。"""
    if not isinstance(text, str) or not text:
        return text, 0

    head = text.lstrip()

    # 守卫 1：Agent 自注入的上下文整条跳过
    for prefix in guard.get("skipPrefixes", []):
        if prefix and head.startswith(prefix):
            return text, 0

    # 守卫 2：包裹型上下文，只改写请求标题之后的用户原话
    heading = guard.get("requestHeading", "")
    for prefix in guard.get("wrappedPrefixes", []):
        if prefix and head.startswith(prefix) and heading:
            idx = text.rfind(heading)
            if idx == -1:
                return text, 0
            newline = text.find("\n", idx)
            cut = len(text) if newline == -1 else newline + 1
            prefix_part, tail = text[:cut], text[cut:]
            new_tail, count = matcher.rewrite(tail)
            if count:
                return prefix_part + new_tail, count
            return text, 0

    new_text, count = matcher.rewrite(text)
    return (new_text, count) if count else (text, 0)


# =============================================================================
# 2. 三协议适配器
# =============================================================================
def rewrite_openai_completions(
    body: dict, matcher: Matcher, guard: dict
) -> int:
    """OpenAI Chat Completions：messages[] 中 role=user 的 text 内容。

    这是 Pi Agent 全部 provider 使用的协议（models.json 中 api=openai-completions）。
    """
    messages = body.get("messages")
    if not isinstance(messages, list):
        return 0
    changed = 0
    for msg in messages:
        if not isinstance(msg, dict) or msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            new_text, count = rewrite_with_guard(content, matcher, guard)
            if count:
                msg["content"] = new_text
                changed += count
        elif isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") not in ("text", "input_text"):
                    continue
                text = part.get("text")
                new_text, count = rewrite_with_guard(text, matcher, guard)
                if count:
                    part["text"] = new_text
                    changed += count
    return changed


def rewrite_anthropic_messages(
    body: dict, matcher: Matcher, guard: dict
) -> int:
    """Anthropic Messages：messages[] 中 role=user 的 text block。

    system（字符串或 block 数组）、tools、assistant 内容、tool_result 一律不动。
    """
    messages = body.get("messages")
    if not isinstance(messages, list):
        return 0
    changed = 0
    for msg in messages:
        if not isinstance(msg, dict) or msg.get("role") != "user":
            continue
        content = msg.get("content")
        if isinstance(content, str):
            new_text, count = rewrite_with_guard(content, matcher, guard)
            if count:
                msg["content"] = new_text
                changed += count
        elif isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") != "text":
                    continue
                text = block.get("text")
                new_text, count = rewrite_with_guard(text, matcher, guard)
                if count:
                    block["text"] = new_text
                    changed += count
    return changed


def rewrite_openai_responses(
    body: dict, matcher: Matcher, guard: dict
) -> int:
    """OpenAI Responses：input[] 中 role=user 的 input_text 分片。

    instructions、tools、developer / assistant / reasoning / tool 项一律不动。
    """
    items = body.get("input")
    if not isinstance(items, list):
        return 0
    changed = 0
    for item in items:
        if not isinstance(item, dict) or item.get("role") != "user":
            continue
        kind = item.get("type")
        if kind is not None and kind != "message":
            continue
        content = item.get("content")
        if isinstance(content, str):
            new_text, count = rewrite_with_guard(content, matcher, guard)
            if count:
                item["content"] = new_text
                changed += count
        elif isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") != "input_text":
                    continue
                text = part.get("text")
                new_text, count = rewrite_with_guard(text, matcher, guard)
                if count:
                    part["text"] = new_text
                    changed += count
    return changed


PROTOCOL_REWRITERS = {
    "openai-completions": rewrite_openai_completions,
    "anthropic-messages": rewrite_anthropic_messages,
    "openai-responses": rewrite_openai_responses,
}


def detect_protocol(path: str) -> str | None:
    """按请求路径自动识别协议。"""
    lowered = path.lower().split("?", 1)[0]
    if lowered.endswith("/messages"):
        return "anthropic-messages"
    if lowered.endswith("/chat/completions"):
        return "openai-completions"
    if lowered.endswith("/responses"):
        return "openai-responses"
    return None


# =============================================================================
# 3. Lab Mode 状态门（mtime 热加载）
# =============================================================================
class LabModeGate:
    """检查 lab-mode.flag 是否启用改写；按 mtime 热加载，无需重启进程。"""

    def __init__(self, flag_path: str, force: bool | None = None):
        self.flag_path = flag_path
        self.force = force
        self._stamp: tuple[int, int] | None = None
        self._active = False
        self._lock = threading.Lock()

    def is_active(self) -> bool:
        if self.force is not None:
            return self.force
        with self._lock:
            try:
                st = os.stat(self.flag_path)
                stamp = (st.st_mtime_ns, st.st_size)
            except OSError:
                stamp = None
            if stamp != self._stamp:
                self._stamp = stamp
                self._active = stamp is not None
            return self._active


# =============================================================================
# 4. 配置加载
# =============================================================================
def _load_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def load_matcher() -> Matcher:
    if not os.path.isfile(RULES_FILE):
        raise FileNotFoundError(
            f"未找到规则表 {RULES_FILE}，请先运行: python extract-rules.py"
        )
    payload = _load_json(RULES_FILE)
    rules = payload.get("rules")
    if not isinstance(rules, list):
        raise ValueError(f"{RULES_FILE} 缺少 rules 数组")
    return Matcher(rules)


def load_guards() -> dict:
    if not os.path.isfile(GUARDS_FILE):
        return {}
    payload = _load_json(GUARDS_FILE)
    guards = payload.get("guards")
    return guards if isinstance(guards, dict) else {}


def load_or_init_config(port: int | None) -> dict:
    """读取 relay-config.json；不存在则生成（含随机 token）。"""
    if os.path.isfile(CONFIG_FILE):
        cfg = _load_json(CONFIG_FILE)
    else:
        cfg = {"schema": 1, "port": DEFAULT_PORT, "token": "", "upstreams": {}}

    if not cfg.get("token"):
        cfg["token"] = secrets.token_urlsafe(24)
    if port is not None:
        cfg["port"] = port
    cfg.setdefault("schema", 1)
    cfg.setdefault("port", DEFAULT_PORT)
    cfg.setdefault("upstreams", {})

    with open(CONFIG_FILE, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(cfg, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    return cfg


def scan_pi_providers(pi_models_path: str) -> dict[str, str]:
    """从 Pi 的 models.json 生成 upstream 映射（只读 provider 名与 baseUrl，不碰 apiKey）。"""
    if not os.path.isfile(pi_models_path):
        return {}
    data = _load_json(pi_models_path)
    providers = data.get("providers")
    if not isinstance(providers, dict):
        return {}
    upstreams: dict[str, str] = {}
    for name, cfg in providers.items():
        if not isinstance(cfg, dict):
            continue
        base_url = cfg.get("baseUrl")
        if isinstance(base_url, str) and base_url.startswith(("http://", "https://")):
            upstreams[f"pi-{name}"] = base_url.rstrip("/")
    return upstreams


# =============================================================================
# 5. 中继 HTTP 处理器
# =============================================================================
class RelayState:
    """进程级共享状态。"""

    def __init__(self, config: dict, matcher: Matcher, guards: dict, gate: LabModeGate):
        self.config = config
        self.matcher = matcher
        self.guards = guards
        self.gate = gate
        self.token = config["token"]
        self.upstreams = config.get("upstreams", {})
        self.verbose = False


def _parse_route(raw_path: str) -> tuple[str, str, str] | None:
    """解析 /r/<token>/<key>/<rest...>，返回 (token, key, rest_path)。"""
    path = raw_path.split("?", 1)[0]
    query = raw_path[len(path) :]
    parts = path.split("/")
    # ['', 'r', token, key, ...rest]
    if len(parts) < 4 or parts[1] != "r":
        return None
    token = parts[2]
    key = parts[3]
    rest = "/" + "/".join(parts[4:]) if len(parts) > 4 else "/"
    return token, key, rest + query


def _split_upstream(base_url: str) -> tuple[str, str, int | None, str]:
    """拆分上游 baseUrl → (scheme, host, port, base_path)。"""
    parts = urlsplit(base_url)
    scheme = parts.scheme or "https"
    host = parts.hostname or ""
    port = parts.port
    base_path = parts.path.rstrip("/")
    return scheme, host, port, base_path


def _read_request_body(handler: BaseHTTPRequestHandler) -> bytes | None:
    """读取请求体，支持 Content-Length 与 chunked。"""
    te = (handler.headers.get("Transfer-Encoding") or "").lower()
    if "chunked" in te:
        chunks: list[bytes] = []
        while True:
            line = handler.rfile.readline(65536).strip()
            if not line:
                break
            try:
                size = int(line.split(b";", 1)[0], 16)
            except ValueError:
                return None
            if size == 0:
                handler.rfile.readline(65536)
                break
            chunks.append(handler.rfile.read(size))
            handler.rfile.readline(65536)
        return b"".join(chunks)

    length_raw = handler.headers.get("Content-Length")
    if not length_raw:
        return b""
    try:
        length = int(length_raw)
    except ValueError:
        return None
    return handler.rfile.read(length)


def _apply_rewrite(
    state: RelayState, protocol: str | None, raw_body: bytes
) -> tuple[bytes, int]:
    """按协议改写请求体。返回 (新请求体, 命中条数)。"""
    if protocol is None or not raw_body:
        return raw_body, 0
    if state.matcher.is_empty:
        return raw_body, 0
    if not state.gate.is_active():
        return raw_body, 0

    rewriter = PROTOCOL_REWRITERS.get(protocol)
    if rewriter is None:
        return raw_body, 0

    try:
        body = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        # 非 JSON 请求体（例如文件上传）：原样透传
        return raw_body, 0

    if not isinstance(body, dict):
        return raw_body, 0

    guard = state.guards.get(protocol, {})
    try:
        changed = rewriter(body, state.matcher, guard)
    except Exception:  # 改写失败绝不阻断主链路
        return raw_body, 0

    if not changed:
        return raw_body, 0

    return json.dumps(body, ensure_ascii=False).encode("utf-8"), changed


class RelayHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "SeepComplianceRelay/1.0"

    # 由 create_server 注入
    state: RelayState = None  # type: ignore[assignment]

    def log_message(self, fmt: str, *args) -> None:  # noqa: A003
        """静默默认访问日志，避免任何请求内容落盘/落屏。"""
        return

    # ------------------------------------------------------------------ 路由
    def _resolve(self) -> tuple[str, str, str] | None:
        route = _parse_route(self.path)
        if route is None:
            self._send_plain(404, "not found")
            return None
        token, key, rest = route
        if token != self.state.token:
            self._send_plain(403, "forbidden")
            return None
        upstream = self.state.upstreams.get(key)
        if not upstream:
            self._send_plain(502, f"unknown upstream key: {key}")
            return None
        return key, upstream, rest

    def _send_plain(self, code: int, message: str) -> None:
        payload = message.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    # ------------------------------------------------------------- 请求转发
    def _forward(self, method: str) -> None:
        resolved = self._resolve()
        if resolved is None:
            return
        key, upstream, rest = resolved

        raw_body = _read_request_body(self)
        if raw_body is None:
            self._send_plain(400, "bad request body")
            return

        protocol = detect_protocol(rest)
        new_body, changed = _apply_rewrite(self.state, protocol, raw_body)

        scheme, host, port, base_path = _split_upstream(upstream)
        if not host:
            self._send_plain(502, "invalid upstream")
            return

        target = f"{base_path}{rest}" if base_path else rest
        if not target.startswith("/"):
            target = "/" + target

        headers = {}
        for name, value in self.headers.items():
            lowered = name.lower()
            if lowered in HOP_BY_HOP or lowered in REQUEST_HEADER_DROP:
                continue
            headers[name] = value
        headers["Host"] = host
        headers["Content-Length"] = str(len(new_body))

        if changed:
            print(
                f"[REWRITE] key={key} protocol={protocol} path={target} changed={changed}",
                flush=True,
            )
        elif self.state.verbose and protocol:
            print(
                f"[PASS   ] key={key} protocol={protocol} path={target} changed=0",
                flush=True,
            )

        conn_cls = HTTPSConnection if scheme == "https" else HTTPConnection
        conn = None
        try:
            conn = conn_cls(host, port, timeout=600)
            conn.request(method, target, body=new_body, headers=headers)
            resp = conn.getresponse()
        except Exception as exc:  # 上游不可达
            if conn is not None:
                try:
                    conn.close()
                except Exception:
                    pass
            print(f"[ERROR  ] upstream unreachable: {type(exc).__name__}", flush=True)
            self._send_plain(502, f"upstream error: {type(exc).__name__}")
            return

        try:
            self.send_response(resp.status)
            upstream_headers = resp.getheaders()
            has_length = False
            for name, value in upstream_headers:
                lowered = name.lower()
                if lowered in HOP_BY_HOP:
                    continue
                if lowered == "content-length":
                    has_length = True
                self.send_header(name, value)

            chunked_out = False
            if not has_length:
                # 上游为流式（SSE）响应：自行使用 chunked 编码保持 HTTP/1.1 语义
                self.send_header("Transfer-Encoding", "chunked")
                chunked_out = True
            self.end_headers()

            while True:
                chunk = resp.read(CHUNK_SIZE)
                if not chunk:
                    break
                if chunked_out:
                    self.wfile.write(f"{len(chunk):X}\r\n".encode("ascii"))
                    self.wfile.write(chunk)
                    self.wfile.write(b"\r\n")
                else:
                    self.wfile.write(chunk)
                try:
                    self.wfile.flush()
                except Exception:
                    break
            if chunked_out:
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

    # ---------------------------------------------------------------- 方法
    def do_POST(self) -> None:  # noqa: N802
        self._forward("POST")

    def do_GET(self) -> None:  # noqa: N802
        self._forward("GET")

    def do_PUT(self) -> None:  # noqa: N802
        self._forward("PUT")

    def do_DELETE(self) -> None:  # noqa: N802
        self._forward("DELETE")

    def do_PATCH(self) -> None:  # noqa: N802
        self._forward("PATCH")


class RelayHTTPServer(ThreadingHTTPServer):
    """静默错误处理的 HTTP 服务。

    SSE 流式场景下客户端会主动提前断开，socketserver 默认会把
    ConnectionAbortedError 的完整堆栈打到 stderr，属于无意义噪声。
    """

    daemon_threads = True
    allow_reuse_address = True

    def handle_error(self, request, client_address) -> None:
        exc = sys.exc_info()[1]
        if isinstance(exc, (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)):
            return
        print(
            f"[ERROR  ] relay handler failure: {type(exc).__name__}: {exc}",
            file=sys.stderr,
            flush=True,
        )


def create_server(state: RelayState, host: str, port: int) -> RelayHTTPServer:
    handler_cls = type("BoundRelayHandler", (RelayHandler,), {"state": state})
    server = RelayHTTPServer((host, port), handler_cls)
    return server


# =============================================================================
# 6. 入口
# =============================================================================
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Seep 合规转译中继（本地回环，零落盘）"
    )
    parser.add_argument("--port", type=int, default=None, help="监听端口")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址")
    parser.add_argument(
        "--force-on", action="store_true", help="强制启用改写（忽略 lab-mode.flag）"
    )
    parser.add_argument(
        "--force-off", action="store_true", help="强制关闭改写（纯透传）"
    )
    parser.add_argument(
        "--scan-pi",
        action="store_true",
        help="从 ~/.pi/agent/models.json 生成 upstream 映射后退出",
    )
    parser.add_argument(
        "--lab-flag", default=DEFAULT_LAB_FLAG, help="lab-mode 标志文件路径"
    )
    parser.add_argument("--verbose", action="store_true", help="输出透传日志")
    args = parser.parse_args()

    if args.force_on and args.force_off:
        print("[FAIL] --force-on 与 --force-off 不能同时使用", file=sys.stderr)
        return 2

    force: bool | None = None
    if args.force_on:
        force = True
    elif args.force_off:
        force = False

    # --scan-pi：生成 Pi provider 的 upstream 映射
    if args.scan_pi:
        config = load_or_init_config(args.port)
        scanned = scan_pi_providers(DEFAULT_PI_MODELS)
        if not scanned:
            print(f"[WARN] 未从 {DEFAULT_PI_MODELS} 读取到 provider", file=sys.stderr)
        config.setdefault("upstreams", {}).update(scanned)
        config["upstreams"].setdefault("anthropic", "https://api.anthropic.com")
        config["upstreams"].setdefault("openai", "https://api.openai.com")
        with open(CONFIG_FILE, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(config, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        print(f"[OK] 已写入 {CONFIG_FILE}")
        for key, url in sorted(scanned.items()):
            print(f"     {key} -> {url}")
        print(f"     token = {config['token']}")
        print("     提示：token 属于本机凭据，请勿外传或提交到公开仓库。")
        return 0

    try:
        matcher = load_matcher()
    except (FileNotFoundError, ValueError) as exc:
        print(f"[FAIL] {exc}", file=sys.stderr)
        return 1

    guards = load_guards()
    config = load_or_init_config(args.port)
    gate = LabModeGate(args.lab_flag, force=force)

    state = RelayState(config, matcher, guards, gate)
    state.verbose = args.verbose

    port = config["port"]
    try:
        server = create_server(state, args.host, port)
    except OSError as exc:
        print(f"[FAIL] 无法监听 {args.host}:{port} -> {exc}", file=sys.stderr)
        return 1

    mode = "FORCED-ON" if force is True else ("FORCED-OFF" if force is False else "LAB-GATED")
    print("=" * 78)
    print("  Seep Compliance Relay (合规转译中继)")
    print("=" * 78)
    print(f"  监听地址 : http://{args.host}:{port}")
    print(f"  规则条数 : {len(matcher.mapping)}")
    print(f"  改写模式 : {mode}  (lab flag: {args.lab_flag})")
    print(f"  上游映射 : {len(state.upstreams)} 个")
    print(f"  访问令牌 : {config['token'][:8]}...（完整值见 relay-config.json，请勿外传）")
    print("-" * 78)
    print("  接入示例：")
    print(f"    Pi Agent     : models.json 中 provider 的 baseUrl 改为")
    print(f"                   http://127.0.0.1:{port}/r/<token>/pi-<ProviderName>")
    print(f"    Claude Code  : ANTHROPIC_BASE_URL=http://127.0.0.1:{port}/r/<token>/anthropic")
    print(f"    Codex        : base_url = http://127.0.0.1:{port}/r/<token>/openai/v1")
    print("-" * 78)
    print("  零落盘纪律：仅记录命中条数，绝不记录请求体 / 响应体 / 鉴权头")
    print("  Ctrl+C 退出")
    print("=" * 78, flush=True)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[INFO] 正在关闭中继...", flush=True)
    finally:
        server.shutdown()
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
