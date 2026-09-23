/**
 * defense_hardening.c
 * 软件安全防护与加固核心防御实现
 */

#include "defense_hardening.h"
#include <stdio.h>

bool EnableSecureDllSearchOrder(void) {
    // 强制限定依赖库搜索仅限系统目录 (System32) 和安全用户目录，排除当前程序根目录
    BOOL res = SetDefaultDllDirectories(LOAD_LIBRARY_SEARCH_SYSTEM32 | LOAD_LIBRARY_SEARCH_USER_DIRS);
    return (res != FALSE);
}

bool EnableDynamicCodeMitigation(void) {
    // 调用 Windows 原生进程缓解策略，禁止在进程内生成/修改动态代码
    PROCESS_MITIGATION_DYNAMIC_CODE_POLICY policy;
    ZeroMemory(&policy, sizeof(policy));
    policy.ProhibitDynamicCode = 1;

    BOOL res = SetProcessMitigationPolicy(ProcessDynamicCodePolicy, &policy, sizeof(policy));
    return (res != FALSE);
}

DefenseStatus CheckFunctionIntegrity(const void* target_func, const uint8_t* expected_bytes, size_t check_len) {
    if (!target_func || check_len == 0) {
        return DEFENSE_OK;
    }

    // 1. 检查函数所在内存页的保护属性
    MEMORY_BASIC_INFORMATION mbi;
    if (VirtualQuery(target_func, &mbi, sizeof(mbi))) {
        // 合法的可执行代码页应严格为 PAGE_EXECUTE_READ (0x20)
        // 若为 PAGE_EXECUTE_READWRITE (0x40) 或 PAGE_READWRITE (0x04)，则高度可疑已被热补丁打桩
        if ((mbi.Protect & PAGE_EXECUTE_READWRITE) || (mbi.Protect & PAGE_READWRITE)) {
            return DEFENSE_ERR_PAGE_PROTECT_TAMPERED;
        }
    }

    const uint8_t* code = (const uint8_t*)target_func;

    // 2. 特征检测：常见的 Inline Hook 跳板
    // 0xE9: JMP rel32 (常见 5 字节跳转)
    if (code[0] == 0xE9) {
        return DEFENSE_ERR_HOOK_DETECTED;
    }

    // 0xFF 0x25: JMP [rip + disp32] (x64 常见 6 字节或 14 字节绝对跳转)
    if (check_len >= 2 && code[0] == 0xFF && code[1] == 0x25) {
        return DEFENSE_ERR_HOOK_DETECTED;
    }

    // 0xCC: INT 3 软件断点
    if (code[0] == 0xCC) {
        return DEFENSE_ERR_HOOK_DETECTED;
    }

    // 3. 预期字节精确哈希/序列比对
    if (expected_bytes != NULL) {
        for (size_t i = 0; i < check_len; ++i) {
            if (code[i] != expected_bytes[i]) {
                return DEFENSE_ERR_INTEGRITY_MISMATCH;
            }
        }
    }

    return DEFENSE_OK;
}
