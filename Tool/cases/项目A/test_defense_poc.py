import ctypes
from ctypes import wintypes
import sys

kernel32 = ctypes.windll.kernel32

print("=" * 60)
print("[+] 软件安全防御与加固机制 PoC 验证测试")
print("=" * 60)

# -------------------------------------------------------------
# 测试 1: 验证 SetDefaultDllDirectories (防御 DLL 目录劫持)
# -------------------------------------------------------------
LOAD_LIBRARY_SEARCH_SYSTEM32 = 0x00000800
LOAD_LIBRARY_SEARCH_USER_DIRS = 0x00000400

try:
    res = kernel32.SetDefaultDllDirectories(LOAD_LIBRARY_SEARCH_SYSTEM32 | LOAD_LIBRARY_SEARCH_USER_DIRS)
    if res != 0:
        print("[V-01 通过] 成功启用 SetDefaultDllDirectories，成功移除当前目录与未受信任目录的默认加载优先权。")
    else:
        print(f"[V-01 失败] SetDefaultDllDirectories 返回错误代码: {kernel32.GetLastError()}")
except Exception as e:
    print(f"[V-01 异常] {e}")

# -------------------------------------------------------------
# 测试 2: 验证 ProcessDynamicCodePolicy (禁止动态修改代码页属性)
# -------------------------------------------------------------
class PROCESS_MITIGATION_DYNAMIC_CODE_POLICY(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD)
    ]

# ProhibitDynamicCode = 1 (bit 0)
policy = PROCESS_MITIGATION_DYNAMIC_CODE_POLICY()
policy.Flags = 1

ProcessDynamicCodePolicy = 2

res_policy = kernel32.SetProcessMitigationPolicy(
    ProcessDynamicCodePolicy,
    ctypes.byref(policy),
    ctypes.sizeof(policy)
)

if res_policy != 0:
    print("[V-02 通过] 成功激活 Windows 内核缓解策略 ProcessDynamicCodePolicy (ProhibitDynamicCode = 1)。")
    
    # 模拟攻击者行为：尝试将已分配的只读内存修改为可执行可写 (PAGE_EXECUTE_READWRITE)
    test_page = kernel32.VirtualAlloc(None, 4096, 0x1000, 0x02) # MEM_COMMIT, PAGE_READONLY
    if test_page:
        old_prot = wintypes.DWORD()
        PAGE_EXECUTE_READWRITE = 0x40
        protect_res = kernel32.VirtualProtect(
            ctypes.c_void_p(test_page),
            4096,
            PAGE_EXECUTE_READWRITE,
            ctypes.byref(old_prot)
        )
        if protect_res == 0:
            err = kernel32.GetLastError()
            print(f"[V-02 验证通过] 内核成功拦截 VirtualProtect 修改代码页权限！返回错误码: {err} (动态代码策略生效)")
        else:
            print("[V-02 告警] VirtualProtect 仍旧成功修改权限，系统策略未拦截。")
        kernel32.VirtualFree(ctypes.c_void_p(test_page), 0, 0x8000)
else:
    err = kernel32.GetLastError()
    print(f"[V-02 提示] SetProcessMitigationPolicy 返回: {err} (可能当前进程未在独立容器或权限约束下运行)")

# -------------------------------------------------------------
# 测试 3: 验证 CheckFunctionIntegrity (Inline Hook / JMP 跳板识别)
# -------------------------------------------------------------
def check_function_integrity(code_bytes, expected_bytes=None):
    if not code_bytes:
        return "DEFENSE_OK"
    # 特征 1: 0xE9 JMP
    if code_bytes[0] == 0xE9:
        return "DEFENSE_ERR_HOOK_DETECTED (JMP rel32)"
    # 特征 2: 0xFF 0x25 JMP [rip+disp] (x64 绝对跳转)
    if len(code_bytes) >= 2 and code_bytes[0] == 0xFF and code_bytes[1] == 0x25:
        return "DEFENSE_ERR_HOOK_DETECTED (JMP [rip+disp32] Trampoline)"
    # 特征 3: 0xCC INT3
    if code_bytes[0] == 0xCC:
        return "DEFENSE_ERR_HOOK_DETECTED (INT 3 断点)"
    
    if expected_bytes and code_bytes[:len(expected_bytes)] != expected_bytes:
        return "DEFENSE_ERR_INTEGRITY_MISMATCH"
        
    return "DEFENSE_OK"

# 构造测试样本
normal_func_prologue = bytes.fromhex("48895C24084889742410574883EC20") # mov [rsp+8], rbx ...
hooked_jmp_prologue   = bytes.fromhex("E9A01200004889742410574883EC20") # jmp ...
hooked_abs_prologue   = bytes.fromhex("FF2500000000A01234567890ABCD00") # jmp [rip+0] ...

print("-" * 60)
print("函数完整性与 Inline Hook 巡检验证：")
print("  正常函数入口检测结果   :", check_function_integrity(normal_func_prologue))
print("  相对跳转 Hook 检测结果 :", check_function_integrity(hooked_jmp_prologue))
print("  绝对跳板 Hook 检测结果 :", check_function_integrity(hooked_abs_prologue))
print("-" * 60)
print("[+] 全量防御功能与验证流程执行完毕。")
