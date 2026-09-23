#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Minimal HTTP/HTTPS forward proxy for giving an offline Android device network access.

Situation: the device has no working network interface (DHCP failure, no default route), so
every request the app makes fails.

Why this works: it does not need a network interface on the device at all. `adb reverse`
opens a listener on the **device's own loopback**, which exists regardless:

    1) run this proxy on the host        (0.0.0.0:8080)
    2) adb -s <serial> reverse tcp:8080 tcp:8080
    3) on the device: settings put global http_proxy 127.0.0.1:8080
    4) the app's HTTP/HTTPS traffic travels over USB and is sent by the host

Supports:
  - CONNECT tunnelling (what HTTPS uses)
  - absolute-URI plain HTTP forwarding

Forwards only: it does not MITM, does not decrypt TLS and does not modify traffic, so
certificate validation is unaffected. See references/environment.md.

Usage: python usb_net_proxy.py [listen_port] [logfile]
"""
import socket
import sys
import threading
import time

if len(sys.argv) > 1 and sys.argv[1] in ('-h', '--help'):
    print(__doc__)
    sys.exit(0)

try:
    PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
except ValueError:
    print('error: listen_port must be a number, got %r\n' % sys.argv[1])
    print(__doc__)
    sys.exit(2)
LOGF = sys.argv[2] if len(sys.argv) > 2 else None
_lock = threading.Lock()
_logf = open(LOGF, 'a', encoding='utf-8') if LOGF else None


def log(msg):
    line = '[%s] %s' % (time.strftime('%H:%M:%S'), msg)
    print(line, flush=True)
    if _logf:
        with _lock:
            _logf.write(line + '\n')
            _logf.flush()


def pump(a, b):
    """Copy a -> b in one direction until either end closes."""
    try:
        while True:
            r, _, _ = select_select([a], [], [], 30)
            if not r:
                break
            data = a.recv(65536)
            if not data:
                break
            b.sendall(data)
    except Exception:
        pass
    finally:
        for s in (a, b):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                s.close()
            except Exception:
                pass


def select_select(rlist, wlist, xlist, timeout):
    import select
    return select.select(rlist, wlist, xlist, timeout)


def read_head(sock, limit=65536):
    data = b''
    while b'\r\n\r\n' not in data and len(data) < limit:
        chunk = sock.recv(4096)
        if not chunk:
            return data
        data += chunk
    return data


def handle(client, addr):
    client.settimeout(30)
    try:
        head = read_head(client)
        if not head:
            client.close()
            return
        first = head.split(b'\r\n', 1)[0].decode('latin-1')
        parts = first.split(' ')
        if len(parts) < 3:
            client.close()
            return
        method, target = parts[0].upper(), parts[1]
        rest = head.split(b'\r\n\r\n', 1)[1] if b'\r\n\r\n' in head else b''

        if method == 'CONNECT':
            host, _, port = target.rpartition(':')
            port = int(port or 443)
            log('CONNECT %s:%d' % (host, port))
            remote = socket.create_connection((host, port), timeout=20)
            client.sendall(b'HTTP/1.1 200 Connection Established\r\n\r\n')
            client.settimeout(None)
            remote.settimeout(None)
            t = threading.Thread(target=pump, args=(client, remote), daemon=True)
            t.start()
            pump(remote, client)
        else:
            # Plain HTTP: target is normally an absolute URI
            if target.startswith('http://'):
                without = target[len('http://'):]
                hostport = without.split('/', 1)[0]
                path = '/' + without.split('/', 1)[1] if '/' in without else '/'
            else:
                hostport = None
                for ln in head.split(b'\r\n'):
                    if ln.lower().startswith(b'host:'):
                        hostport = ln.split(b':', 1)[1].strip().decode()
                path = target
            if not hostport:
                client.close()
                return
            host, _, port = hostport.rpartition(':')
            port = int(port or 80)
            log('HTTP %s%s' % (hostport, path))
            remote = socket.create_connection((host, port), timeout=20)
            req = ('%s %s HTTP/1.1\r\n' % (method, path)).encode()
            hdrs = head.split(b'\r\n')[1:]
            for h in hdrs:
                if h.lower().startswith(b'proxy-connection'):
                    continue
                req += h + b'\r\n'
            req += b'\r\n' + rest
            remote.sendall(req)
            client.settimeout(None)
            remote.settimeout(None)
            t = threading.Thread(target=pump, args=(client, remote), daemon=True)
            t.start()
            pump(remote, client)
    except Exception as e:
        log('ERR %s %s' % (addr, e))
        try:
            client.close()
        except Exception:
            pass


def main():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(('0.0.0.0', PORT))
    srv.listen(128)
    log('proxy listening on 0.0.0.0:%d' % PORT)
    while True:
        c, a = srv.accept()
        threading.Thread(target=handle, args=(c, a), daemon=True).start()


if __name__ == '__main__':
    main()
