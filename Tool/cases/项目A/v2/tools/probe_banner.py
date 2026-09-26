# -*- coding: utf-8 -*-
"""测试 28.40 试用横幅的驱动变量: 写入候选标志后强制刷新标题并观察"""
import ctypes, ctypes.wintypes as wt, subprocess, sys, os, time, struct
k32=ctypes.WinDLL('kernel32',use_last_error=True); k32.OpenProcess.restype=wt.HANDLE
u32=ctypes.WinDLL('user32')
u32.EnumWindows.argtypes=[ctypes.WINFUNCTYPE(ctypes.c_bool,wt.HWND,wt.LPARAM),wt.LPARAM]
VM=0x0410|0x0020|0x0008
def rpm(h,a,n):
    b=ctypes.create_string_buffer(n); g=ctypes.c_size_t(0)
    return b.raw[:g.value] if k32.ReadProcessMemory(h,ctypes.c_void_p(a),b,n,ctypes.byref(g)) else None
def wpm(h,a,d):
    o=wt.DWORD(0); k32.VirtualProtectEx(h,ctypes.c_void_p(a),len(d),0x40,ctypes.byref(o))
    g=ctypes.c_size_t(0); r=k32.WriteProcessMemory(h,ctypes.c_void_p(a),d,len(d),ctypes.byref(g))
    k32.VirtualProtectEx(h,ctypes.c_void_p(a),len(d),o.value,ctypes.byref(o)); return bool(r)
exe=os.path.abspath(sys.argv[1]); d=os.path.dirname(exe)
pr=subprocess.Popen([exe],cwd=d); time.sleep(15)
h=k32.OpenProcess(VM,False,pr.pid)
psapi=ctypes.WinDLL('psapi'); arr=(ctypes.c_void_p*1024)(); need=wt.DWORD(0)
psapi.EnumProcessModules(h,arr,ctypes.sizeof(arr),ctypes.byref(need))
info=(ctypes.c_ulonglong*10)(); base=None
for i in range(need.value//8):
    psapi.GetModuleInformation(h,ctypes.c_void_p(arr[i]),info,ctypes.sizeof(info))
    buf=ctypes.create_unicode_buffer(512); psapi.GetModuleBaseNameW(h,ctypes.c_void_p(arr[i]),buf,512)
    if buf.value.lower()==os.path.basename(exe).lower(): base=info[0]; break
def title():
    res=[]
    def cb(hwnd,l):
        pid=wt.DWORD(0); u32.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
        if pid.value==pr.pid and u32.IsWindowVisible(hwnd):
            n=u32.GetWindowTextLengthW(hwnd); b=ctypes.create_unicode_buffer(n+2)
            u32.GetWindowTextW(hwnd,b,n+2); res.append(b.value)
        return True
    u32.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool,wt.HWND,wt.LPARAM)(cb),0)
    return [t for t in res if '<项目A>' in t]
print('TITLE before :', title())
for rva,val,size in [(0x23ACDEA,0,2),(0x22FD724,5,4),(0x230170C,1,4)]:
    cur=rpm(h,base+rva,size)
    if cur is not None:
        print('  write RVA 0x%X: %s -> %s'%(rva,cur.hex(),wpm(h,base+rva,val.to_bytes(size,'little'))))
time.sleep(1)
subprocess.Popen([exe,'C:\Windows'],cwd=d); time.sleep(6)
print('TITLE after  :', title())
pr.terminate()
