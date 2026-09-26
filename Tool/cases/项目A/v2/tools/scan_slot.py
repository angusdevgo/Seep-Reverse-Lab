import ctypes, ctypes.wintypes as wt, struct, subprocess, sys, time, os
k32=ctypes.WinDLL('kernel32', use_last_error=True)
k32.OpenProcess.restype=wt.HANDLE
VM=0x0410|0x0020|0x0008
def rpm(h,a,n):
    b=ctypes.create_string_buffer(n); got=ctypes.c_size_t(0)
    if not k32.ReadProcessMemory(h,ctypes.c_void_p(a),b,n,ctypes.byref(got)): return None
    return b.raw[:got.value]
exe=os.path.abspath(sys.argv[1])
pr=subprocess.Popen([exe],cwd=os.path.dirname(exe)); time.sleep(14)
h=k32.OpenProcess(VM,False,pr.pid)
psapi=ctypes.WinDLL('psapi')
arr=(ctypes.c_void_p*1024)(); need=wt.DWORD(0)
psapi.EnumProcessModules(h,arr,ctypes.sizeof(arr),ctypes.byref(need))
n=need.value//8
info=(ctypes.c_ulonglong*10)()
mods=[]
for i in range(n):
    psapi.GetModuleInformation(h,ctypes.c_void_p(arr[i]),info,ctypes.sizeof(info))
    buf=ctypes.create_unicode_buffer(512); psapi.GetModuleBaseNameW(h,ctypes.c_void_p(arr[i]),buf,512)
    mods.append((buf.value,info[0]))
base=[m[0] for m in mods].index(os.path.basename(exe))
exe_base=mods[base][1]
ole=[m[1] for m in mods if m[0].lower()=='oleaut32.dll']
print('exe_base=0x%X oleaut32=%s'%(exe_base,[hex(x) for x in ole]))
if ole:
    target=ole[0]+0x10CF0
    print('SysAllocString=0x%X'%target)
    pat=struct.pack('<Q',target)
    # scan data sections (0x2030000..0x2674000) of the EXE
    for rva_start,rva_end,name in [(0x1000,0x2850000,'ALL')]:
        chunk=0x40000
        r=rva_start
        while r<rva_end:
            sz=min(chunk,rva_end-r)
            data=rpm(h,exe_base+r,sz)
            if data:
                i=data.find(pat)
                while i>=0:
                    print('  HIT %s RVA 0x%X'%(name,r+i))
                    i=data.find(pat,i+1)
            r+=sz
pr.terminate()
