#!/usr/bin/env python3
"""模拟一个苹果CMS(maccms10) 风格影视站，用于 cms-fingerprint.ps1 的离线回归。

刻意还原真实特征：
  /                       首页：Powered by Maccms + MacPlayer + 直出 m3u8
  /api.php/provide/vod/   采集接口：ac=list 返回标准 JSON
  /tvbox/config.json      TVBox 源配置（sites 数组）
  /admin.php              后台登录页
  /.env                   配置泄露（高危）
  /backup.zip             备份文件（高危）

用法：python serve_cms.py <port>
"""
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 18081

INDEX = """<!DOCTYPE html>
<html><head><title>某某影院 - 高清影视在线观看</title>
<meta name="generator" content="Maccms">
</head><body>
<div class="foot">Powered by <a href="https://www.maccms.com/">Maccms</a></div>
<script src="/static/js/mac_common.js"></script>
<script src="/static/player/MacPlayer.js"></script>
<script>var player_aaaa={"flag":"play","encrypt":0,"url":"https://cdn.example.com/hls/index.m3u8"};</script>
</body></html>
"""

VOD_LIST = json.dumps({
    "code": 1,
    "msg": "数据列表",
    "page": 1,
    "pagecount": 12,
    "limit": "20",
    "total": 236,
    "list": [
        {"vod_id": 1001, "vod_name": "示例影片 A", "type_name": "动作片",
         "vod_play_url": "第01集$https://cdn.example.com/hls/1/index.m3u8"},
        {"vod_id": 1002, "vod_name": "示例影片 B", "type_name": "动漫",
         "vod_play_url": "第01集$https://cdn.example.com/hls/2/index.m3u8"},
    ],
}, ensure_ascii=False)

TVBOX = json.dumps({"sites": [
    {"key": "csp_Demo", "name": "示例源", "type": 3, "api": "csp_Demo", "searchable": 1},
    {"key": "csp_Maccms", "name": "苹果源", "type": 1, "api": "https://api.example-vod.com/api.php/provide/vod/"},
], "lives": []}, ensure_ascii=False)

ADMIN = """<html><head><title>管理登录</title></head>
<body><form method="post" action="/admin.php"><input name="username">
<input type="password" name="password"><button>登录</button></form></body></html>"""

ENVFILE = "APP_NAME=Example\nAPP_KEY=base64:ZmFrZWtleWZha2VrZXk=\nDB_PASSWORD=s3cr3t\n"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        path = self.path.split("?")[0]

        if path == "/":
            self._send(200, INDEX)
        elif path.startswith("/api.php/provide/vod"):
            self._send(200, VOD_LIST, "application/json; charset=utf-8")
        elif path == "/tvbox/config.json":
            self._send(200, TVBOX, "application/json; charset=utf-8")
        elif path == "/admin.php":
            self._send(200, ADMIN)
        elif path == "/.env":
            self._send(200, ENVFILE, "text/plain; charset=utf-8")
        elif path == "/backup.zip":
            self._send(200, b"PK\x03\x04" + b"\x00" * 100, "application/zip")
        elif path == "/static/player/MacPlayer.js":
            self._send(200, "/* MacPlayer */", "application/javascript")
        else:
            self._send(404, "Not Found", "text/plain")

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    print(f"cms fixture on :{PORT}", flush=True)
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
