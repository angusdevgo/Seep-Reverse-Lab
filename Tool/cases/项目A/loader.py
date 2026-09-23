import subprocess
import time
import os
import sys

项目A_PATH = r"<本地路径>"
INJECTOR_SCRIPT = os.path.abspath("injector.py")
DLL_PATH = os.path.abspath("项目APatch.dll")

def launch_and_patch():
    print("[*] Launching 项目A.exe...")
    proc = subprocess.Popen([项目A_PATH])
    print(f"[*] Process started with PID: {proc.pid}")
    
    # Wait briefly for main module to load
    time.sleep(1.0)
    
    print("[*] Performing direct memory patch...")
    # Direct memory patching implementation
    import ctypes
    from ctypes import wintypes
    
    PROCESS_ALL_ACCESS = 0x1F0FFF
    PAGE_EXECUTE_READWRITE = 0x40
    
    kernel32 = ctypes.windll.kernel32
    psapi = ctypes.windll.psapi
    
    h_proc = kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, proc.pid)
    if not h_proc:
        print("[-] Failed to open process")
        return
        
    # Get base address
    h_mods = (wintypes.HMODULE * 1024)()
    cb_needed = wintypes.DWORD()
    psapi.EnumProcessModules(h_proc, h_mods, ctypes.sizeof(h_mods), ctypes.byref(cb_needed))
    base = h_mods[0]
    
    # Patch 1: VA 0x14066fc95 -> RVA 0x66fc95
    p1 = bytes.fromhex("66c705ac46c8010000c7059c90c70100000000c705aa50c70105000000e9f0000000")
    addr1 = ctypes.c_void_p(base + 0x66FC95)
    old1 = wintypes.DWORD()
    kernel32.VirtualProtectEx(h_proc, addr1, len(p1), PAGE_EXECUTE_READWRITE, ctypes.byref(old1))
    written = ctypes.c_size_t()
    kernel32.WriteProcessMemory(h_proc, addr1, p1, len(p1), ctypes.byref(written))
    kernel32.VirtualProtectEx(h_proc, addr1, len(p1), old1.value, ctypes.byref(old1))
    
    # Patch 2: VA 0x14066db7b -> RVA 0x66db7b
    p2 = bytes.fromhex("66b8ffff90")
    addr2 = ctypes.c_void_p(base + 0x66DB7B)
    old2 = wintypes.DWORD()
    kernel32.VirtualProtectEx(h_proc, addr2, len(p2), PAGE_EXECUTE_READWRITE, ctypes.byref(old2))
    kernel32.WriteProcessMemory(h_proc, addr2, p2, len(p2), ctypes.byref(written))
    kernel32.VirtualProtectEx(h_proc, addr2, len(p2), old2.value, ctypes.byref(old2))
    
    kernel32.CloseHandle(h_proc)
    print("[+] Patches applied successfully to running process!")

if __name__ == "__main__":
    launch_and_patch()
