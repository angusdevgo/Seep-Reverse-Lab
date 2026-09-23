#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Probe an app's HTTP API the way the app does.

Purpose-built for the common frustration: your request gets 403 while the app
works fine. Almost always the app sends a header you are not sending (frequently
one custom header), or your egress IP differs from the device's.

Usage
-----
  python probe_api.py --base https://api.example.com --path /health
  python probe_api.py --base https://api.example.com --path /adverts \
      --param position=banner --header 'X-App-Name: myapp'
  python probe_api.py --base https://api.example.com \
      --path "/items?page=1" --raw

Options
-------
  --base        Base URL (required)
  --path        Path, may already contain a query string (required)
  --param k=v   Repeatable; appended as query parameters
  --header k=v  Repeatable; sent as-is. Always send the app's real headers.
  --token T     Convenience: adds 'Authorization: Bearer T'
  --ua UA       User-Agent (default: okhttp/4.12.0)
  --no-proxy    Ignore environment proxy settings (recommended)
  --show        Print the first N bytes of the body (default 800)

Interpreting results
--------------------
  200 + data        -> alive; read the envelope shape
  200 + empty list  -> valid input, nothing to return. Do NOT assume "ad removed":
                       it may simply be that no item is configured.
  400 + message     -> input is validated; the message often lists valid values
  401/403, no creds -> auth-gated (server-side ownership)
  401/403, forged   -> token is verified server-side; client patching cannot mint one
  403 + HTML body    -> a WAF/CDN refused your *request shape* or egress, not the endpoint
  404               -> exact path mismatch
"""
import argparse
import json
import urllib.error
import urllib.parse
import urllib.request


def build_opener(no_proxy):
    if no_proxy:
        return urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return urllib.request.build_opener()


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument('--base', required=True)
    ap.add_argument('--path', required=True)
    ap.add_argument('--param', action='append', default=[])
    ap.add_argument('--header', action='append', default=[])
    ap.add_argument('--token')
    ap.add_argument('--ua', default='okhttp/4.12.0')
    ap.add_argument('--no-proxy', action='store_true')
    ap.add_argument('--show', type=int, default=800)
    a = ap.parse_args()

    url = a.base.rstrip('/') + a.path
    if a.param:
        params = []
        for p in a.param:
            if '=' not in p:
                print('[FAIL] --param expects k=v, got %r' % p)
                return 2
            k, v = p.split('=', 1)
            params.append((k, v))
        sep = '&' if '?' in url else '?'
        url += sep + urllib.parse.urlencode(params)

    headers = {
        'User-Agent': a.ua,
        'Accept': 'application/json',
    }
    for h in a.header:
        if ':' not in h:
            print('[FAIL] --header expects "Name: value", got %r' % h)
            return 2
        k, v = h.split(':', 1)
        headers[k.strip()] = v.strip()
    if a.token:
        headers['Authorization'] = 'Bearer %s' % a.token

    print('[req] GET %s' % url)
    for k, v in headers.items():
        shown = v if k.lower() != 'authorization' else v[:24] + '...'
        print('      %s: %s' % (k, shown))

    req = urllib.request.Request(url, headers=headers)
    op = build_opener(a.no_proxy)
    try:
        with op.open(req, timeout=30) as r:
            body = r.read().decode('utf-8', 'replace')
            print('[res] %s  %s' % (r.status, r.headers.get('Content-Type', '')))
            print(body[:a.show])
            if body.strip().startswith(('{', '[')):
                try:
                    parsed = json.loads(body)
                    if isinstance(parsed, dict) and 'data' in parsed:
                        d = parsed['data']
                        if isinstance(d, dict) and 'list' in d:
                            print('[shape] data.list length=%s' % len(d['list'] or []))
                except Exception:
                    pass
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', 'replace')
        print('[res] HTTP %s' % e.code)
        print(body[:a.show])
    except Exception as e:
        print('[ERR] %s' % e)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
