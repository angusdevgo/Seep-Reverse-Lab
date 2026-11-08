#!/usr/bin/env python3
"""符合影视站防盗链行为的本地测试服务器。

规则（模拟真实站点）：
  - /enc.key  ：必须带 Referer: https://site.example/ 否则 403
  - /out.m3u8 ：必须带 Referer，否则 403
  - /seg*.ts  ：必须带 Referer 且带 UA，否则 403

用法：python serve_gated.py <dir> <port>
"""
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.abspath(sys.argv[1])
PORT = int(sys.argv[2])
REQUIRED_REFERER = "https://site.example/"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _gate(self):
        path = self.path.split("?")[0]
        referer = self.headers.get("Referer", "")
        ua = self.headers.get("User-Agent", "")

        def deny(msg):
            body = f"403 {msg}".encode()
            self.send_response(403)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return True

        if not referer.startswith(REQUIRED_REFERER.rstrip("/")):
            if path.endswith(".m3u8") or path.endswith(".key"):
                return deny("missing/incorrect Referer")
        if path.endswith(".ts") and (not ua or "Mozilla" not in ua):
            return deny("missing User-Agent for segment")
        return False

    def do_GET(self):
        if self._gate():
            return
        path = self.path.split("?")[0].lstrip("/")
        target = os.path.join(ROOT, path)
        if not os.path.isfile(target):
            body = b"404"
            self.send_response(404)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        with open(target, "rb") as f:
            data = f.read()
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    print(f"serving {ROOT} on :{PORT}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
