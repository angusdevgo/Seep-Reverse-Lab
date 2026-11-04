"""运行时校验：直接读目标进程内存，逐点核对补丁字节是否已写入。

用法：
    python verify_runtime.py                     # 自动找 项目B 四个宿主
    python verify_runtime.py --pid 1234 --host 项目BNxMain.exe
"""
import ctypes
import ctypes.wintypes as wt
import json
import os
import sys

k32 = ctypes.WinDLL('kernel32', use_last_error=True)
PROCESS_VM_READ = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
TH32CS_SNAPPROCESS = 0x00000002
TH32CS_SNAPMODULE = 0x00000008
TH32CS_SNAPMODULE32 = 0x00000010
MAX_PATH = 260

HOSTS = ('mumunxmain.exe', 'mumunxservice.exe', 'mumuremoteservice.exe', 'mumunxupdater.exe')


class PROCESSENTRY32(ctypes.Structure):
    _fields_ = [('dwSize', wt.DWORD), ('cntUsage', wt.DWORD),
                ('th32ProcessID', wt.DWORD), ('th32DefaultHeapID', ctypes.POINTER(ctypes.c_ulong)),
                ('th32ModuleID', wt.DWORD), ('cntThreads', wt.DWORD),
                ('th32ParentProcessID', wt.DWORD), ('pcPriClassBase', ctypes.c_long),
                ('dwFlags', wt.DWORD), ('szExeFile', ctypes.c_char * MAX_PATH)]


class MODULEENTRY32(ctypes.Structure):
    _fields_ = [('dwSize', wt.DWORD), ('th32ModuleID', wt.DWORD), ('th32ProcessID', wt.DWORD),
                ('GlblcntUsage', wt.DWORD), ('ProccntUsage', wt.DWORD),
                ('modBaseAddr', ctypes.POINTER(ctypes.c_byte)), ('modBaseSize', wt.DWORD),
                ('hModule', wt.HMODULE), ('szModule', ctypes.c_char * 256),
                ('szExePath', ctypes.c_char * MAX_PATH)]


def find_pids():
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    pe = PROCESSENTRY32()
    pe.dwSize = ctypes.sizeof(pe)
    out = {}
    ok = k32.Process32First(snap, ctypes.byref(pe))
    while ok:
        name = pe.szExeFile.decode('latin1')
        if name.lower() in HOSTS:
            out[name] = pe.th32ProcessID
        ok = k32.Process32Next(snap, ctypes.byref(pe))
    k32.CloseHandle(snap)
    return out


def module_base(pid):
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, pid)
    if snap == -1:
        return None
    me = MODULEENTRY32()
    me.dwSize = ctypes.sizeof(me)
    base = None
    if k32.Module32First(snap, ctypes.byref(me)):
        base = ctypes.cast(me.modBaseAddr, ctypes.c_void_p).value
    k32.CloseHandle(snap)
    return base


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    rows = json.load(open(os.path.join(here, 'points_v4.json'), encoding='utf-8'))
    by_host = {}
    for r in rows:
        by_host.setdefault(r['host'], []).append(r)

    arg_pid = None
    arg_host = None
    if '--pid' in sys.argv:
        arg_pid = int(sys.argv[sys.argv.index('--pid') + 1])
    if '--host' in sys.argv:
        arg_host = sys.argv[sys.argv.index('--host') + 1]

    pids = find_pids()
    if arg_pid:
        pids = {arg_host or '项目BNxMain.exe': arg_pid}
    if not pids:
        print('[!] 没有发现正在运行的 项目B 进程。请先启动模拟器。')
        return 2

    total_ok = total_bad = 0
    for name, pid in pids.items():
        pts = by_host.get(name)
        if not pts:
            continue
        base = module_base(pid)
        if not base:
            print('[!] %s (pid=%d) 取模块基址失败（权限不足？）' % (name, pid))
            continue
        h = k32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_INFORMATION, False, pid)
        if not h:
            print('[!] %s (pid=%d) OpenProcess 失败' % (name, pid))
            continue
        print('\n%s  pid=%d  base=0x%X  共 %d 点' % (name, pid, base, len(pts)))
        ok = bad = 0
        for r in pts:
            n = len(bytes.fromhex(r['patch']))
            buf = ctypes.create_string_buffer(n)
            got = ctypes.c_size_t(0)
            if not k32.ReadProcessMemory(h, ctypes.c_void_p(base + r['rva']), buf, n, ctypes.byref(got)):
                bad += 1
                print('  [READFAIL] %-52s rva=0x%08X' % (r['id'], r['rva']))
                continue
            cur = buf.raw.hex()
            if cur == r['patch']:
                ok += 1
            elif cur == r['orig']:
                bad += 1
                print('  [NOTAPPLIED] %-48s rva=0x%08X' % (r['id'], r['rva']))
            else:
                bad += 1
                print('  [DIFF] %-54s rva=0x%08X got=%s' % (r['id'], r['rva'], cur))
        k32.CloseHandle(h)
        total_ok += ok
        total_bad += bad
        print('  -> 已生效 %d / 异常 %d / 共 %d' % (ok, bad, len(pts)))

    print('\n' + '-' * 70)
    print('  合计: 已生效 %d, 异常 %d' % (total_ok, total_bad))
    print('  RESULT:', 'ALL PATCHED' if total_bad == 0 and total_ok else 'CHECK FAILED')
    return 0 if total_bad == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
