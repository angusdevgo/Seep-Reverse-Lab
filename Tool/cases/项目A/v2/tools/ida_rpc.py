#!/usr/bin/env python
"""Minimal JSON-RPC client for the IDA Pro MCP plugin (127.0.0.1:13337)."""
import json, sys, urllib.request

URL = 'http://127.0.0.1:13337/mcp'


def call(method, params=None, timeout=600):
    payload = {'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or []}
    req = urllib.request.Request(URL, data=json.dumps(payload).encode(),
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def main():
    method = sys.argv[1]
    params = json.loads(sys.argv[2]) if len(sys.argv) > 2 else []
    res = call(method, params)
    if 'error' in res:
        print('ERROR:', json.dumps(res['error'], ensure_ascii=False))
        return 1
    out = res.get('result')
    print(json.dumps(out, ensure_ascii=False, indent=1) if not isinstance(out, str) else out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
