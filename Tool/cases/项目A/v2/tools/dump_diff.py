# -*- coding: utf-8 -*-
"""Dump <项目A> 静态数据区 (.data/.bdata) 并差分, 用于定位授权状态变量。"""
import ctypes, ctypes.wintypes as wt, subprocess, sys, os, time, struct

k32 = ctypes.WinDLL('kernel32', use_last_error=True)
k32.OpenProcess.restype = wt.HANDLE
VM = 0x0410 | 0x0020 | 0x0008

def rpm(h, a, n):
    b = ctypes.create_string_buffer(n); got = ctypes.c_size_t(0)
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(a), b, n, ctypes.byref(got)):
        return None
    return b.raw[:got.value]

def dump(exe, out, rng):
    pr = subprocess.Popen([exe], cwd=os.path.dirname(exe))
    time.sleep(15)
    if pr.poll() is not None:
        print('exited early'); return False
    h = k32.OpenProcess(VM, False, pr.pid)
    base = None
    psapi = ctypes.WinDLL('psapi')
    arr = (ctypes.c_void_p * 1024)(); need = wt.DWORD(0)
    psapi.EnumProcessModules(h, arr, ctypes.sizeof(arr), ctypes.byref(need))
    n = need.value // 8
    info = (ctypes.c_ulonglong * 10)()
    for i in range(n):
        psapi.GetModuleInformation(h, ctypes.c_void_p(arr[i]), info, ctypes.sizeof(info))
        buf = ctypes.create_unicode_buffer(512)
        psapi.GetModuleBaseNameW(h, ctypes.c_void_p(arr[i]), buf, 512)
        if buf.value.lower() == os.path.basename(exe).lower():
            base = info[0]; break
    if base is None:
        print('no base'); return False
    with open(out, 'wb') as f:
        for s, e in rng:
            data = rpm(h, base + s, e - s)
            f.write(data if data and len(data) == e - s else b'\x00' * (e - s))
    pr.terminate()
    print('dumped', out, 'base=0x%X' % base)
    return True

if __name__ == '__main__':
    mode = sys.argv[1]
    exe = sys.argv[2]
    out = sys.argv[3]
    if '2830' in exe or '2830' in out:
        rng = [(0x2017000, 0x2335000), (0x2389000, 0x2660000)]
        off0 = 0x2017000
    else:
        rng = [(0x2030000, 0x2337000), (0x23a1000, 0x2674000)]
        off0 = 0x2030000
    if mode == 'dump':
        dump(exe, out, rng)
    else:
        a = open(sys.argv[2], 'rb').read(); b = open(sys.argv[3], 'rb').read()
        n = min(len(a), len(b))
        i = 0; diffs = []
        while i < n:
            if a[i] != b[i]:
                j = i
                while j < n and a[j] != b[j]: j += 1
                if j - i <= 16:
                    diffs.append((i, a[i:j], b[i:j]))
                else:
                    diffs.append((i, a[i:i+8], b[i:i+8]))
                i = j
            else:
                i += 1
        print('diff runs: %d' % len(diffs))
        for off, x, y in diffs[:60]:
            # 映射回 RVA
            if off < 0x308000:
                rva = 0x2017000 + off if '2830' in sys.argv[2] else 0x2030000 + off
            else:
                rva = 0x2389000 + (off - 0x308000) if '2830' in sys.argv[2] else 0x23a1000 + (off - 0x308000)
            print('  RVA 0x%-9X A=%-24s B=%s' % (rva, x.hex(), y.hex()))
