import struct
import shutil
import os

# 1. Read clean system version.dll
CLEAN_SRC = r"C:\Windows\System32\version.dll"
with open(CLEAN_SRC, "rb") as f:
    dll = bytearray(f.read())

print(f"[+] Loaded clean system version.dll ({len(dll)} bytes)")

# Ensure fothk[0x10:0x15] is untouched
assert dll[0x4010:0x4015] == b'\xe9\x2b\xf6\xff\xff', "fothk[0x10:0x15] must be original jump!"

BASE_RVA = 0x4000
RAW_BASE = 0x4000

OFF_HOOK_MAIN   = 0x100  # RVA 0x4100
OFF_HOOK_SCOPE  = 0x300  # RVA 0x4300

OFF_STR_KERNEL32 = 0x500
OFF_STR_VP       = 0x530
OFF_STR_INTERNAL = 0x550
OFF_STR_USER     = 0x570
OFF_STR_KEY      = 0x590
OFF_PATCH1_DATA  = 0x600
OFF_PATCH2_DATA  = 0x630
OFF_PATCH3_DATA  = 0x640

# Prepare strings & patch data
STR_KERNEL32 = "kernel32.dll\0".encode("utf-16le")
STR_VP = b"VirtualProtect\0"
STR_INTERNAL = "内部授权\0".encode("utf-16le")
STR_USER = "VIPUesr\0".encode("utf-16le")
STR_KEY = "xy01-Lifetime-License-Pro-vipuser\0".encode("utf-16le")

PATCH1_BYTES = bytes.fromhex("66C705AC46C8010000C7059C90C70100000000C705AA50C70105000000E9F0000000") # 34 bytes
PATCH2_BYTES = bytes.fromhex("66B8FFFF90") # 5 bytes
PATCH3_BYTES = bytes.fromhex("FF25156ED701") # 6 bytes: jmp qword ptr [rip + 0x1D76E15] -> SysAllocString

# -------------------------------------------------------------
# Construct Hook_InternalScope at RVA 0x4300 (Fully Autonomous!)
# -------------------------------------------------------------
scope_code = bytearray()
def emit_sc(b): scope_code.extend(b)

# push rbx; push rsi; push rdi; sub rsp, 0x20
emit_sc(b'\x53')                 # push rbx
emit_sc(b'\x56')                 # push rsi
emit_sc(b'\x57')                 # push rdi
emit_sc(b'\x48\x83\xec\x20')     # sub rsp, 0x20

# mov rax, gs:[0x60]
emit_sc(b'\x65\x48\x8b\x04\x25\x60\x00\x00\x00')
# mov rbx, [rax + 0x10] (项目ABase)
emit_sc(b'\x48\x8b\x58\x10')
# mov rsi, [rbx + 0x265e408] (SysAllocString)
emit_sc(b'\x48\x8b\xb3\x08\xe4\x65\x02')

# 1. Allocate STR_USER and store in [rbx + 0x221CEF8]
cur_ip = (BASE_RVA + OFF_HOOK_SCOPE) + len(scope_code)
disp = (BASE_RVA + OFF_STR_USER) - (cur_ip + 7)
emit_sc(b'\x48\x8d\x0d' + struct.pack("<i", disp)) # lea rcx, [rip + OFF_STR_USER]
emit_sc(b'\xff\xd6')                               # call rsi
emit_sc(b'\x48\x89\x83\xf8\xce\x21\x02')         # mov [rbx + 0x221CEF8], rax

# 2. Allocate STR_KEY and store in [rbx + 0x22694A0] and [rbx + 0x21E52F0]
cur_ip = (BASE_RVA + OFF_HOOK_SCOPE) + len(scope_code)
disp = (BASE_RVA + OFF_STR_KEY) - (cur_ip + 7)
emit_sc(b'\x48\x8d\x0d' + struct.pack("<i", disp)) # lea rcx, [rip + OFF_STR_KEY]
emit_sc(b'\xff\xd6')                               # call rsi
emit_sc(b'\x48\x89\x83\xa0\x94\x26\x02')         # mov [rbx + 0x22694A0], rax
emit_sc(b'\x48\x89\x83\xf0\x52\x1e\x02')         # mov [rbx + 0x21E52F0], rax

# 3. Allocate STR_INTERNAL and keep in rax as function return value
cur_ip = (BASE_RVA + OFF_HOOK_SCOPE) + len(scope_code)
disp = (BASE_RVA + OFF_STR_INTERNAL) - (cur_ip + 7)
emit_sc(b'\x48\x8d\x0d' + struct.pack("<i", disp)) # lea rcx, [rip + OFF_STR_INTERNAL]
emit_sc(b'\xff\xd6')                               # call rsi

# Epilogue
emit_sc(b'\x48\x83\xc4\x20')     # add rsp, 0x20
emit_sc(b'\x5f')                 # pop rdi
emit_sc(b'\x5e')                 # pop rsi
emit_sc(b'\x5b')                 # pop rbx
emit_sc(b'\xc3')                 # ret

print(f"[+] Autonomous Hook_InternalScope length: {len(scope_code)} bytes at RVA 0x{BASE_RVA + OFF_HOOK_SCOPE:X}")

# -------------------------------------------------------------
# Construct Main Hook at RVA 0x4100
# -------------------------------------------------------------
main_code = bytearray()
def emit(b): main_code.extend(b)

# push non-volatile registers
emit(b'\x53')             # push rbx
emit(b'\x56')             # push rsi
emit(b'\x57')             # push rdi
emit(b'\x41\x54')         # push r12
emit(b'\x41\x55')         # push r13
emit(b'\x41\x56')         # push r14
emit(b'\x41\x57')         # push r15
emit(b'\x48\x83\xec\x50') # sub rsp, 0x50

# 1. Call original 0x1794 (__security_init_cookie)
cur_ip = (BASE_RVA + OFF_HOOK_MAIN) + len(main_code)
disp = 0x1794 - (cur_ip + 5)
emit(b'\xe8' + struct.pack("<i", disp))

# 2. Get 项目A.exe ImageBase into rbx
# mov rax, gs:[0x60]
emit(b'\x65\x48\x8b\x04\x25\x60\x00\x00\x00')
# mov rbx, [rax + 0x10]
emit(b'\x48\x8b\x58\x10')

# 3. Call LoadLibraryW(L"kernel32.dll") via version.dll IAT 0x5288
cur_ip = (BASE_RVA + OFF_HOOK_MAIN) + len(main_code)
disp_k32 = (BASE_RVA + OFF_STR_KERNEL32) - (cur_ip + 7)
emit(b'\x48\x8d\x0d' + struct.pack("<i", disp_k32)) # lea rcx, [rip + OFF_STR_KERNEL32]
cur_ip = (BASE_RVA + OFF_HOOK_MAIN) + len(main_code)
disp_loadlib = 0x5288 - (cur_ip + 6)
emit(b'\xff\x15' + struct.pack("<i", disp_loadlib)) # call [rip + disp_loadlib]
emit(b'\x49\x89\xc4')                               # mov r12, rax (r12 = hKernel32)

# 4. Call GetProcAddress(r12, "VirtualProtect") via version.dll IAT 0x5278
emit(b'\x4c\x89\xe1')                               # mov rcx, r12
cur_ip = (BASE_RVA + OFF_HOOK_MAIN) + len(main_code)
disp_vp = (BASE_RVA + OFF_STR_VP) - (cur_ip + 7)
emit(b'\x48\x8d\x15' + struct.pack("<i", disp_vp))  # lea rdx, [rip + OFF_STR_VP]
cur_ip = (BASE_RVA + OFF_HOOK_MAIN) + len(main_code)
disp_getproc = 0x5278 - (cur_ip + 6)
emit(b'\xff\x15' + struct.pack("<i", disp_getproc)) # call [rip + disp_getproc]
emit(b'\x49\x89\xc5')                               # mov r13, rax (r13 = VirtualProtect)

# Helper function to generate patch application block
def emit_apply_patch(target_rva, patch_off, patch_len):
    emit(b'\x48\x8d\x8b' + struct.pack("<i", target_rva)) # lea rcx, [rbx + target_rva]
    emit(b'\xba' + struct.pack("<i", patch_len))          # mov edx, patch_len
    emit(b'\x41\xb8\x40\x00\x00\x00')                     # mov r8d, 0x40
    emit(b'\x4c\x8d\x4c\x24\x20')                         # lea r9, [rsp + 0x20]
    emit(b'\x41\xff\xd5')                                 # call r13 (VirtualProtect)

    cur_ip = (BASE_RVA + OFF_HOOK_MAIN) + len(main_code)
    disp = (BASE_RVA + patch_off) - (cur_ip + 7)
    emit(b'\x48\x8d\x35' + struct.pack("<i", disp))       # lea rsi, [rip + patch_off]
    emit(b'\x48\x8d\xbb' + struct.pack("<i", target_rva)) # lea rdi, [rbx + target_rva]
    emit(b'\xb9' + struct.pack("<i", patch_len))          # mov ecx, patch_len
    emit(b'\xf3\xa4')                                     # rep movsb

# 5. Apply Patch 1 (0x66FC95, 34 bytes)
emit_apply_patch(0x66FC95, OFF_PATCH1_DATA, len(PATCH1_BYTES))

# 6. Apply Patch 2 (0x66DB7B, 5 bytes)
emit_apply_patch(0x66DB7B, OFF_PATCH2_DATA, len(PATCH2_BYTES))

# 7. Apply Patch 3 (0x8E75ED, 6 bytes)
emit_apply_patch(0x8E75ED, OFF_PATCH3_DATA, len(PATCH3_BYTES))

# 8. Apply Patch 4 (0x8E6D83, 14 bytes trampoline to Hook_InternalScope)
cur_ip = (BASE_RVA + OFF_HOOK_MAIN) + len(main_code)
disp_scope = (BASE_RVA + OFF_HOOK_SCOPE) - (cur_ip + 7)
emit(b'\x48\x8d\x15' + struct.pack("<i", disp_scope)) # lea rdx, [rip + OFF_HOOK_SCOPE]
emit(b'\xc7\x44\x24\x28\xff\x25\x00\x00')             # mov dword ptr [rsp + 0x28], 0x0025ff
emit(b'\x66\xc7\x44\x24\x2c\x00\x00')                 # mov word ptr [rsp + 0x2c], 0x0000
emit(b'\x48\x89\x54\x24\x2e')                         # mov qword ptr [rsp + 0x2e], rdx

emit(b'\x48\x8d\x8b\x83\x6d\x8e\x00')                 # lea rcx, [rbx + 0x8e6d83]
emit(b'\xba\x0e\x00\x00\x00')                         # mov edx, 14
emit(b'\x41\xb8\x40\x00\x00\x00')                     # mov r8d, 0x40
emit(b'\x4c\x8d\x4c\x24\x20')                         # lea r9, [rsp + 0x20]
emit(b'\x41\xff\xd5')                                 # call r13 (VirtualProtect)

emit(b'\x48\x8d\x74\x24\x28')                         # lea rsi, [rsp + 0x28]
emit(b'\x48\x8d\xbb\x83\x6d\x8e\x00')                 # lea rdi, [rbx + 0x8e6d83]
emit(b'\xb9\x0e\x00\x00\x00')                         # mov ecx, 14
emit(b'\xf3\xa4')                                     # rep movsb

# 9. Clean up stack and restore registers
emit(b'\x48\x83\xc4\x50')                             # add rsp, 0x50
emit(b'\x41\x5f')                                     # pop r15
emit(b'\x41\x5e')                                     # pop r14
emit(b'\x41\x5d')                                     # pop r13
emit(b'\x41\x5c')                                     # pop r12
emit(b'\x5f')                                         # pop rdi
emit(b'\x5e')                                         # pop rsi
emit(b'\x5b')                                         # pop rbx
emit(b'\xc3')                                         # ret

print(f"[+] MainHook length: {len(main_code)} bytes at RVA 0x{BASE_RVA + OFF_HOOK_MAIN:X}")

# -------------------------------------------------------------
# Write payloads into section fothk buffer without touching 0x4010..0x4015
# -------------------------------------------------------------
dll[RAW_BASE + OFF_HOOK_MAIN : RAW_BASE + OFF_HOOK_MAIN + len(main_code)] = main_code
dll[RAW_BASE + OFF_HOOK_SCOPE : RAW_BASE + OFF_HOOK_SCOPE + len(scope_code)] = scope_code

def write_at(off, data):
    dll[RAW_BASE + off : RAW_BASE + off + len(data)] = data

write_at(OFF_STR_KERNEL32, STR_KERNEL32)
write_at(OFF_STR_VP, STR_VP)
write_at(OFF_STR_INTERNAL, STR_INTERNAL)
write_at(OFF_STR_USER, STR_USER)
write_at(OFF_STR_KEY, STR_KEY)
write_at(OFF_PATCH1_DATA, PATCH1_BYTES)
write_at(OFF_PATCH2_DATA, PATCH2_BYTES)
write_at(OFF_PATCH3_DATA, PATCH3_BYTES)

# Patch DllMain entry point at 0x144C to call MainHook (0x4100)
hook_call = b'\xe8' + struct.pack("<i", (BASE_RVA + OFF_HOOK_MAIN) - (0x144C + 5))
dll[0x144C : 0x144C + 5] = hook_call

assert dll[0x4010:0x4015] == b'\xe9\x2b\xf6\xff\xff', "0x4010 MUST REMAIN UNTOUCHED!"

with open(r"<本地路径>", "wb") as f:
    f.write(dll)

# Also copy directly to <本地路径>
with open(r"<本地路径>", "wb") as f:
    f.write(dll)

print(f"[+] Successfully generated truly autonomous version.dll ({len(dll)} bytes)")