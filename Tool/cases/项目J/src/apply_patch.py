#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
项目J —— 在线卡密授权客户端旁路补丁器 (CWE-602)
=================================================================
目标：某加密壳保护的在线卡密授权客户端（易语言 + miniblink 混合运行时）
段  ：.ev3n（运行期解密为 RWX） · 镜像基址 0x00400000（无 ASLR，地址固定）

补丁 3 处 / 22 字节
-------------------
  P1  0x00401290  83 7D FC 00 0F 84 4D 02 00 00  ->  C7 45 FC 01 00 00 00 90 90 90
      登录卡密裁决点：cmp [ebp-4],0 / je fail  ->  mov dword [ebp-4],1
  P2  0x0041AC81  0F 8D 34 01 00 00              ->  E9 35 01 00 00 90
      授权心跳复检 #1：jge 0x41ADBB  ->  jmp 0x41ADBB
  P3  0x0041AE05  0F 8D 34 01 00 00              ->  E9 35 01 00 00 90
      授权心跳复检 #2：jge 0x41AF3F  ->  jmp 0x41AF3F

对照实验结论（务必三处齐打）
---------------------------
  仅 P1                  -> 主窗口建不出来，进程 5 秒内自杀（心跳复检失败）
  P1 + 心跳函数整体 ret   -> 主窗口打开，约 17 秒后访问违例崩溃（跳过必要初始化）
  P1 + 0x41AFA6 改返回值  -> 5 秒退出（该函数返回字节集，类型转换失败）
  P1 + P2 + P3 ✅        -> 稳定运行 ≥ 320 秒

用法
----
  python apply_patch.py [目标exe路径]
  （目标带 requireAdministrator 清单时，本脚本需以管理员身份运行）
"""

import ctypes
from ctypes import wintypes as wt
import sys, time, os

k32 = ctypes.WinDLL('kernel32', use_last_error=True)

k32.CreateProcessW.argtypes = [
    wt.LPCWSTR, wt.LPWSTR, ctypes.c_void_p, ctypes.c_void_p, wt.BOOL,
    wt.DWORD, ctypes.c_void_p, wt.LPCWSTR, ctypes.c_void_p, ctypes.c_void_p]
k32.CreateProcessW.restype = wt.BOOL

k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
k32.OpenProcess.restype = wt.HANDLE

k32.ReadProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                  ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k32.ReadProcessMemory.restype = wt.BOOL

k32.WriteProcessMemory.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                   ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
k32.WriteProcessMemory.restype = wt.BOOL

k32.VirtualProtectEx.argtypes = [wt.HANDLE, ctypes.c_void_p, ctypes.c_size_t,
                                 wt.DWORD, ctypes.POINTER(wt.DWORD)]
k32.VirtualProtectEx.restype = wt.BOOL

PROCESS_ALL_ACCESS      = 0x1F0FFF
PAGE_EXECUTE_READWRITE  = 0x40
# 让目标脱离调用方控制台：否则 .bat 跑完、控制台关闭时会触发 CTRL_CLOSE_EVENT 把目标一起杀掉
CREATE_DETACHED_PROCESS = 0x00000008

# 外壳解密完成判据：心跳函数入口的序言 push ebp; mov ebp,esp
HEARTBEAT_ENTRY = 0x0041AB86
DECRYPTED_MAGIC = bytes.fromhex('558BEC')

# (地址, 原始字节, 补丁字节, 说明)
PATCH_SET = [
    (0x00401290,
     bytes.fromhex('837DFC000F844D020000'),
     bytes.fromhex('C745FC01000000909090'),
     'P1 登录卡密裁决点：cmp [ebp-4],0 / je fail  ->  mov dword [ebp-4],1'),
    (0x0041AC81,
     bytes.fromhex('0F8D34010000'),
     bytes.fromhex('E93501000090'),
     'P2 授权心跳复检 #1：jge 0x41ADBB  ->  jmp 0x41ADBB'),
    (0x0041AE05,
     bytes.fromhex('0F8D34010000'),
     bytes.fromhex('E93501000090'),
     'P3 授权心跳复检 #2：jge 0x41AF3F  ->  jmp 0x41AF3F'),
]

HERE = os.path.dirname(os.path.abspath(__file__))
_CANDIDATE_NAMES = ('target_patched.exe', '实验副本.exe', 'target.exe')


def _resolve_default_target():
    """自动定位目标：同目录 -> 上层 03_原始样本 / 06_免UAC实验环境 -> 向上回溯搜索 .exe"""
    def _first_in(d):
        for n in _CANDIDATE_NAMES:
            p = os.path.join(d, n)
            if os.path.isfile(p):
                return p
        return None

    hit = _first_in(HERE)
    if hit:
        return hit

    root = os.path.dirname(HERE)
    for sub in ('06_免UAC实验环境', '03_原始样本', '03_原始样本_未改动', 'samples'):
        hit = _first_in(os.path.join(root, sub))
        if hit:
            return hit

    for dirpath, dirnames, filenames in os.walk(root):
        if dirpath.count(os.sep) - root.count(os.sep) > 2:
            dirnames[:] = []
            continue
        for n in _CANDIDATE_NAMES:
            if n in filenames:
                return os.path.join(dirpath, n)
    return None


DEFAULT_TARGET = _resolve_default_target()


class STARTUPINFOW(ctypes.Structure):
    _fields_ = [('cb', wt.DWORD), ('lpReserved', wt.LPWSTR), ('lpDesktop', wt.LPWSTR),
                ('lpTitle', wt.LPWSTR), ('dwX', wt.DWORD), ('dwY', wt.DWORD),
                ('dwXSize', wt.DWORD), ('dwYSize', wt.DWORD),
                ('dwXCountChars', wt.DWORD), ('dwYCountChars', wt.DWORD),
                ('dwFillAttribute', wt.DWORD), ('dwFlags', wt.DWORD),
                ('wShowWindow', wt.WORD), ('cbReserved2', wt.WORD),
                ('lpReserved2', ctypes.c_void_p), ('hStdInput', wt.HANDLE),
                ('hStdOutput', wt.HANDLE), ('hStdError', wt.HANDLE)]


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [('hProcess', wt.HANDLE), ('hThread', wt.HANDLE),
                ('dwProcessId', wt.DWORD), ('dwThreadId', wt.DWORD)]


def rpm(h, addr, size):
    buf = ctypes.create_string_buffer(size)
    n = ctypes.c_size_t(0)
    if not k32.ReadProcessMemory(h, ctypes.c_void_p(addr), buf, size, ctypes.byref(n)):
        return None
    return buf.raw[:n.value]


def wpm(h, addr, data):
    old = wt.DWORD(0)
    k32.VirtualProtectEx(h, ctypes.c_void_p(addr), len(data),
                         PAGE_EXECUTE_READWRITE, ctypes.byref(old))
    n = ctypes.c_size_t(0)
    ok = k32.WriteProcessMemory(h, ctypes.c_void_p(addr), data, len(data), ctypes.byref(n))
    k32.VirtualProtectEx(h, ctypes.c_void_p(addr), len(data), old.value, ctypes.byref(old))
    return bool(ok) and n.value == len(data)


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_TARGET
    if not target or not os.path.isfile(target):
        print('[!] 未找到目标。请显式指定：python apply_patch.py <目标exe路径>')
        return 1
    print('[*] target = %s' % target)

    si = STARTUPINFOW(); si.cb = ctypes.sizeof(si)
    pi = PROCESS_INFORMATION()
    if not k32.CreateProcessW(target, None, None, None, False,
                              CREATE_DETACHED_PROCESS, None,
                              os.path.dirname(os.path.abspath(target)),
                              ctypes.byref(si), ctypes.byref(pi)):
        err = ctypes.get_last_error()
        if err == 740:
            print('[!] CreateProcess 需要提权(ERROR_ELEVATION_REQUIRED) —— 请以管理员身份运行本脚本')
        else:
            print('[!] CreateProcess failed err=%d' % err)
        return 1

    pid = pi.dwProcessId
    print('[*] target launched, PID=%d ; waiting for unpacker to decrypt .ev3n ...' % pid)

    h = k32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)
    if not h:
        print('[!] OpenProcess failed err=%d (run as Administrator)' % ctypes.get_last_error())
        return 1

    deadline = time.time() + 30
    ready = False
    while time.time() < deadline:
        if rpm(h, HEARTBEAT_ENTRY, 3) == DECRYPTED_MAGIC:
            ready = True
            break
        time.sleep(0.02)
    if not ready:
        print('[!] timeout: .ev3n section still not decrypted')
        return 1
    print('[+] .ev3n decrypted')

    ok_all = True
    for addr, orig, patch, desc in PATCH_SET:
        cur = rpm(h, addr, len(orig))
        if cur is None:
            print('[!] read failed @0x%08X' % addr); ok_all = False; continue
        if cur == patch:
            print('[=] already patched @0x%08X  (%s)' % (addr, desc)); continue
        if cur != orig:
            print('[!] unexpected bytes @0x%08X: %s (expect %s)'
                  % (addr, cur.hex(' '), orig.hex(' ')))
            ok_all = False
            continue
        if wpm(h, addr, patch):
            back = rpm(h, addr, len(patch))
            print('[+] patched @0x%08X  %s' % (addr, desc))
            print('      %s  ->  %s   [readback %s]'
                  % (orig.hex(' '), patch.hex(' '), back.hex(' ') if back else 'ERR'))
        else:
            print('[!] WriteProcessMemory failed @0x%08X err=%d'
                  % (addr, ctypes.get_last_error()))
            ok_all = False

    if not ok_all:
        print('[!] 部分补丁未生效')
        return 1

    print('[+] DONE —— 在登录框输入任意卡密(例如 123456)点击「登陆」即可进入主界面')
    return 0


if __name__ == '__main__':
    sys.exit(main())
