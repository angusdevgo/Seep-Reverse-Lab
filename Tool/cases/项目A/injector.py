import sys
import ctypes
from ctypes import wintypes
import subprocess
import time

PROCESS_ALL_ACCESS = 0x1F0FFF
MEM_COMMIT = 0x1000
MEM_RESERVE = 0x2000
PAGE_READWRITE = 0x04

kernel32 = ctypes.windll.kernel32

def inject_dll(pid, dll_path):
    h_process = kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)
    if not h_process:
        print(f"[-] OpenProcess failed: {ctypes.GetLastError()}")
        return False

    dll_bytes = dll_path.encode('utf-8') + b'\x00'
    arg_address = kernel32.VirtualAllocEx(h_process, None, len(dll_bytes), MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE)
    if not arg_address:
        print(f"[-] VirtualAllocEx failed: {ctypes.GetLastError()}")
        kernel32.CloseHandle(h_process)
        return False

    written = ctypes.c_size_t()
    if not kernel32.WriteProcessMemory(h_process, arg_address, dll_bytes, len(dll_bytes), ctypes.byref(written)):
        print(f"[-] WriteProcessMemory failed: {ctypes.GetLastError()}")
        kernel32.VirtualFreeEx(h_process, arg_address, 0, 0x8000)
        kernel32.CloseHandle(h_process)
        return False

    h_kernel32 = kernel32.GetModuleHandleA(b"kernel32.dll")
    load_library_addr = kernel32.GetProcAddress(h_kernel32, b"LoadLibraryA")

    thread_id = wintypes.DWORD()
    h_thread = kernel32.CreateRemoteThread(h_process, None, 0, load_library_addr, arg_address, 0, ctypes.byref(thread_id))
    if not h_thread:
        print(f"[-] CreateRemoteThread failed: {ctypes.GetLastError()}")
        kernel32.VirtualFreeEx(h_process, arg_address, 0, 0x8000)
        kernel32.CloseHandle(h_process)
        return False

    kernel32.WaitForSingleObject(h_thread, 0xFFFFFFFF)
    kernel32.CloseHandle(h_thread)
    kernel32.VirtualFreeEx(h_process, arg_address, 0, 0x8000)
    kernel32.CloseHandle(h_process)
    print(f"[+] DLL successfully injected into PID {pid}")
    return True

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python injector.py <PID> <DLL_PATH>")
        sys.exit(1)
    inject_dll(int(sys.argv[1]), sys.argv[2])
