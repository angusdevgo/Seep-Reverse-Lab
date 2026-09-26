#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
<项目A> 本地授权状态伪造 PoC (CWE-602)
=====================================
原理: <项目A> 的授权判定完全依赖进程内的几个可写全局变量:
    license_type  : 0=未注册, 1..5 = 对应 xy01..xy05 许可证代次
    ver_flag      : 0/1/2 = 当前许可证是否覆盖本版本
 没有任何服务端校验、没有签名回执，因此任意进程内代码 (DLL 注入 / 调试器 /
 内存补丁 / 同权限进程) 只要改写这两个变量即可获得 "Lifetime License" 状态。

用法:
    python poc_license.py --exe <<项目A>.exe> [--mode read|patch] [--wait 14]

作者: 小π (seep 工作台)
"""
import argparse
import ctypes
import ctypes.wintypes as wt
import os
import struct
import subprocess
import sys
import time

# 版本 -> (license_type RVA, ver_flag RVA, 许可证名/码全局 RVA 列表)
TARGETS = {
    '28.30': dict(lic=0x22E4D5C, flag=0x22E8D44, word=0x22F434A,
                  name=0x221CEF8, code1=0x22694A0, code2=0x21E52F0),
    '28.40': dict(lic=0x22FD724, flag=0x230170C, word=0x22FD9C8,
                  name=0x2281C70, code1=0x2281C70, code2=0x2281C70),
}

PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
PROCESS_VM_OPERATION = 0x0008
PROCESS_QUERY_INFORMATION = 0x0400

k32 = ctypes.WinDLL('kernel32', use_last_error=True)
k32.OpenProcess.restype = wt.HANDLE
k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
k32.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                  ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k32.WriteProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                   ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k32.VirtualQueryEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_size_t]
k32.CloseHandle.argtypes = [wt.HANDLE]


class MEMORY_BASIC_INFORMATION64(ctypes.Structure):
    _fields_ = [('BaseAddress', ctypes.c_ulonglong), ('AllocationBase', ctypes.c_ulonglong),
                ('AllocationProtect', wt.DWORD), ('__alignment1', wt.DWORD),
                ('RegionSize', ctypes.c_ulonglong), ('State', wt.DWORD),
                ('Protect', wt.DWORD), ('Type', wt.DWORD), ('__alignment2', wt.DWORD)]


def rpm(h, addr, size):
    buf = ctypes.create_string_buffer(size)
    got = ctypes.c_size_t(0)
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, size, ctypes.byref(got)):
        return None
    return buf.raw[:got.value]


def wpm(h, addr, data):
    old = wt.DWORD(0)
    k32.VirtualProtectEx(h, ctypes.c_void_p(addr), len(data), 0x40, ctypes.byref(old))
    got = ctypes.c_size_t(0)
    ok = k32.WriteProcessMemory(h, ctypes.c_void_p(addr), data, len(data), ctypes.byref(got))
    k32.VirtualProtectEx(h, ctypes.c_void_p(addr), len(data), old.value, ctypes.byref(old))
    return bool(ok) and got.value == len(data)


def peb_image_base(h):
    """通过 PEB 取主模块基址 (EnumProcessModules 失败时的兜底)"""
    ntdll = ctypes.WinDLL('ntdll')
    class PROCESS_BASIC_INFORMATION(ctypes.Structure):
        _fields_ = [('Reserved1', ctypes.c_void_p), ('PebBaseAddress', ctypes.c_void_p),
                    ('Reserved2', ctypes.c_void_p * 2), ('UniqueProcessId', ctypes.c_void_p),
                    ('Reserved3', ctypes.c_void_p)]
    pbi = PROCESS_BASIC_INFORMATION()
    ret = ntdll.NtQueryInformationProcess(ctypes.c_void_p(h), 0, ctypes.byref(pbi),
                                          ctypes.sizeof(pbi), None)
    if ret != 0 or not pbi.PebBaseAddress:
        print('    [debug] NtQueryInformationProcess ret=%d' % ret)
        return None
    raw = rpm(h, ctypes.cast(pbi.PebBaseAddress, ctypes.c_void_p).value + 0x10, 8)
    if not raw:
        return None
    return struct.unpack('<Q', raw)[0]


def module_base(h, want_name):
    """返回主模块 (EnumProcessModules 列表第 0 项即主 EXE) 的 (base, size)"""
    psapi = ctypes.WinDLL('psapi', use_last_error=True)
    arr = (ctypes.c_void_p * 1024)()
    needed = wt.DWORD(0)
    if not psapi.EnumProcessModules(h, arr, ctypes.sizeof(arr), ctypes.byref(needed)):
        print('    [debug] EnumProcessModules failed err=%d' % ctypes.get_last_error())
        return None
    n = needed.value // ctypes.sizeof(ctypes.c_void_p)
    print('    [debug] modules=%d first=0x%X' % (n, arr[0] or 0))
    for i in range(n):
        hmod = arr[i]
        buf = ctypes.create_unicode_buffer(512)
        psapi.GetModuleBaseNameW(h, ctypes.c_void_p(hmod), buf, 512)
        info = (ctypes.c_ulonglong * 10)()
        psapi.GetModuleInformation(h, ctypes.c_void_p(hmod), info, ctypes.sizeof(info))
        if i == 0 or buf.value.lower() == want_name.lower():
            return hmod, info[0]
    return None


def read_widestring(h, ptr, maxlen=256):
    if not ptr:
        return ''
    raw = rpm(h, ptr, maxlen * 2)
    if not raw:
        return '<unreadable>'
    out = []
    for i in range(0, len(raw) - 1, 2):
        ch = raw[i:i + 2]
        if ch == b'\x00\x00':
            break
        out.append(ch.decode('utf-16-le', errors='replace'))
    return ''.join(out)


def detect_version(path):
    """从 README 或文件版本资源推断版本号"""
    d = os.path.dirname(path)
    for fn in ('Readme.txt', '<项目A>.ini'):
        p = os.path.join(d, fn)
        if os.path.exists(p):
            try:
                txt = open(p, 'r', encoding='utf-16', errors='ignore').read()
            except Exception:
                txt = open(p, 'r', errors='ignore').read()
            for tok in txt.split():
                if tok.count('.') == 2 and tok[0].isdigit():
                    return '.'.join(tok.split('.')[:2])
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--exe', required=True)
    ap.add_argument('--mode', choices=['read', 'patch'], default='read')
    ap.add_argument('--wait', type=int, default=14)
    ap.add_argument('--version', default=None, help='28.30 / 28.40 (默认自动探测)')
    ap.add_argument('--keep', action='store_true', help='结束后不关闭进程')
    ap.add_argument('--pid', type=int, default=0, help='附加到已运行进程')
    args = ap.parse_args()

    exe = os.path.abspath(args.exe)
    ver = args.version or detect_version(exe) or '28.40'
    if ver not in TARGETS:
        print('未知版本 %s, 请用 --version 指定' % ver)
        return 2
    t = TARGETS[ver]
    print('[*] target = %s   version = %s' % (exe, ver))

    proc = None
    if args.pid:
        pid = args.pid
    else:
        proc = subprocess.Popen([exe], cwd=os.path.dirname(exe))
        pid = proc.pid
        print('[*] 启动 pid=%d, 等待 %ds 初始化 ...' % (pid, args.wait))
        time.sleep(args.wait)
        if proc.poll() is not None:
            print('[!] 目标进程已退出, code=%s (可能已有实例在运行)' % proc.returncode)
            return 5

    h = k32.OpenProcess(PROCESS_VM_READ | PROCESS_VM_WRITE | PROCESS_VM_OPERATION |
                        PROCESS_QUERY_INFORMATION, False, pid)
    if not h:
        print('[!] OpenProcess 失败 (err=%d), 需要同权限/管理员' % ctypes.get_last_error())
        return 3

    mod = module_base(h, os.path.basename(exe))
    if mod:
        base, size = mod
    else:
        base = peb_image_base(h)
        size = 0
        if not base:
            print('[!] 无法定位主模块基址')
            return 4
        print('    [debug] 使用 PEB 兜底基址 0x%X' % base)
    print('[*] imagebase = 0x%X  size = 0x%X' % (base, size))

    def dump(tag):
        lic = rpm(h, base + t['lic'], 4)
        flag = rpm(h, base + t['flag'], 4)
        word = rpm(h, base + t['word'], 2)
        name_p = struct.unpack('<Q', rpm(h, base + t['name'], 8))[0]
        print('    [%s] license_type=%-3d ver_flag=%-3d word=0x%04X' % (
            tag, struct.unpack('<I', lic)[0] if lic else -1,
            struct.unpack('<I', flag)[0] if flag else -1,
            struct.unpack('<H', word)[0] if word else 0))
        print('    [%s] license_name_ptr=0x%X  -> %r' % (tag, name_p, read_widestring(h, name_p)))
        for key in ('code1', 'code2'):
            if t.get(key):
                cp = struct.unpack('<Q', rpm(h, base + t[key], 8))[0]
                print('    [%s] %s_ptr=0x%X -> %r' % (tag, key, cp, read_widestring(h, cp)))
        return lic, flag

    print('\n=== 1. 基线读取 (未经任何修改) ===')
    dump('before')

    if args.mode == 'patch':
        print('\n=== 2. 注入本地授权状态 (Lifetime License = type 5) ===')
        ok1 = wpm(h, base + t['lic'], struct.pack('<I', 5))
        ok2 = wpm(h, base + t['flag'], struct.pack('<I', 1))
        print('    write license_type=5 : %s' % ok1)
        print('    write ver_flag=1     : %s' % ok2)
        print('\n=== 3. 回读验证 ===')
        dump('after')

    k32.CloseHandle(h)
    if proc and not args.keep:
        time.sleep(1)
        proc.terminate()
        print('\n[*] 已关闭测试进程')
    elif proc:
        print('\n[*] 进程仍在运行 pid=%d' % proc.pid)
    return 0


if __name__ == '__main__':
    sys.exit(main())
