"""离线校验：按 points_v4.json 逐点比对目标二进制磁盘字节（无需启动模拟器）。

用法：
    python verify_all_points.py
    python verify_all_points.py "D:\\Data\\项目B\\nx_main"
"""
import hashlib
import json
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DIR = r'D:\Data\项目B\nx_main'


def parse_pe(data):
    e = struct.unpack_from('<I', data, 0x3C)[0]
    n = struct.unpack_from('<H', data, e + 6)[0]
    optsz = struct.unpack_from('<H', data, e + 20)[0]
    sh = e + 24 + optsz
    secs = []
    for k in range(n):
        o = sh + k * 40
        nm = data[o:o + 8].rstrip(b'\0').decode('latin1')
        vsz, va, rsz, rp = struct.unpack_from('<IIII', data, o + 8)
        secs.append((nm, va, vsz, rp, rsz))
    return secs


def rva2off(secs, rva):
    for nm, va, vsz, rp, rs in secs:
        if va <= rva < va + max(vsz, rs):
            d = rva - va
            if d < rs:
                return rp + d
    return None


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for b in iter(lambda: f.read(1 << 20), b''):
            h.update(b)
    return h.hexdigest()


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DIR
    rows = json.load(open(os.path.join(HERE, 'points_v4.json'), encoding='utf-8'))

    print('=' * 78)
    print('  项目B 6.8.10.0 点位离线校验（磁盘字节级，目标构建 2026-10-28）')
    print('  目标目录: %s' % target)
    print('=' * 78)

    hosts = {}
    for r in rows:
        hosts.setdefault(r['host'], []).append(r)

    total_ok = total_bad = 0
    for host, pts in hosts.items():
        path = os.path.join(target, host)
        if not os.path.exists(path):
            print('\n[!] 缺少文件: %s' % path)
            continue
        data = open(path, 'rb').read()
        secs = parse_pe(data)
        print('\n%s  sha256=%s  %s bytes' % (host, sha256(path), format(len(data), ',')))
        ok = bad = 0
        for r in pts:
            off = rva2off(secs, r['rva'])
            plen = len(bytes.fromhex(r['patch']))
            cur = data[off:off + plen] if off is not None else b''
            want = bytes.fromhex(r['orig'])[:plen]
            already = bytes.fromhex(r['patch'])
            if cur == want:
                ok += 1
            elif cur == already:
                ok += 1
            else:
                bad += 1
                print('  [FAIL] %-52s rva=0x%08X got=%s exp=%s' % (
                    r['id'], r['rva'], cur.hex() or '-', want.hex()))
        total_ok += ok
        total_bad += bad
        print('  -> %d 通过 / %d 不符 / 共 %d 点' % (ok, bad, len(pts)))

    print('\n' + '-' * 78)
    print('  合计: %d 通过, %d 不符' % (total_ok, total_bad))
    print('  RESULT:', 'ALL VERIFIED' if total_bad == 0 and total_ok > 0 else 'HAS FAILURES')
    print('=' * 78)
    return 0 if total_bad == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
