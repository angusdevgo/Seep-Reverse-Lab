# -*- coding: utf-8 -*-
"""在运行进程的 EXE 静态区里找"指向试用标签字符串"的全局变量"""
import ctypes, ctypes.wintypes as wt, subprocess, sys, os, time, struct
k32=ctypes.WinDLL('kernel32',use_last_error=True); k32.OpenProcess.restype=wt.HANDLE
VM=0x0410|0x0020|0x0008
def rpm(h,a,n):
    b=ctypes.create_string_buffer(n); g=ctypes.c_size_t(0)
    return b.raw[:g.value] if k32.ReadProcessMemory(h,ctypes.c_void_p(a),b,n,ctypes.byref(g)) else None
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
print('base=0x%X'%base)
needle='Trial Version'.encode('utf-16-le')
found=[]
CH=0x80000
for r0,r1,nm in [(0x2030000,0x2337000,'.data'),(0x23a1000,0x2674000,'.bdata')]:
    r=r0
    while r<r1:
        sz=min(CH,r1-r); data=rpm(h,base+r,sz)
        if data:
            # 找字符串本身
            k=data.find(needle)
            while k>=0:
                saddr=base+r+k
                # 反向查找指向该地址的指针
                for sec0,sec1,snm in [(0x2030000,0x2337000,'.data'),(0x23a1000,0x2674000,'.bdata')]:
                    rr=sec0
                    while rr<sec1:
                        s2=min(CH,sec1-rr); dd=rpm(h,base+rr,s2)
                        if dd:
                            p=struct.pack('<Q',saddr)
                            j=dd.find(p)
                            while j>=0:
                                found.append((snm,rr+j,saddr))
                                j=dd.find(p,j+1)
                        rr+=s2
                k=data.find(needle,k+1)
        r+=sz
print('pointers to trial-tag strings: %d'%len(found))
for nm,rva,tgt in found[:20]:
    s=rpm(h,tgt,120)
    print('  %s RVA 0x%X -> 0x%X : %r'%(nm,rva,tgt,s.decode('utf-16-le',errors='replace') if s else None))
pr.terminate()
