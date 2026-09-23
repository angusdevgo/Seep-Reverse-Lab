/**
 * defense_hardening.h
 * 软件安全防护与加固核心防御头文件
 */

#ifndef DEFENSE_HARDENING_H
#define DEFENSE_HARDENING_H

#include <windows.h>
#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

// 自检结果枚举
typedef enum {
    DEFENSE_OK = 0,
    DEFENSE_ERR_HOOK_DETECTED = 1,
    DEFENSE_ERR_PAGE_PROTECT_TAMPERED = 2,
    DEFENSE_ERR_INTEGRITY_MISMATCH = 3
} DefenseStatus;

/**
 * 阶段 1：加固加载器目录，防范当前工作目录/同级目录的 DLL 劫持
 * @return true 成功启用，false 失败
 */
bool EnableSecureDllSearchOrder(void);

/**
 * 阶段 2：启用 Windows 内核缓解策略，禁止运行时对可执行代码段调用 VirtualProtect 赋予写权限
 * @return true 成功启用，false 失败
 */
bool EnableDynamicCodeMitigation(void);

/**
 * 阶段 3：自检目标敏感函数是否被挂钩（检测 E9、FF 25 等跳转跳板或内存保护属性篡改）
 * @param target_func 目标函数指针
 * @param expected_bytes 预期的初始机器码（前 8 字节），如为 NULL 则仅做跳板与属性特征通用检测
 * @param check_len 校验长度（通常为 8 到 16 字节）
 * @return DefenseStatus
 */
DefenseStatus CheckFunctionIntegrity(const void* target_func, const uint8_t* expected_bytes, size_t check_len);

#ifdef __cplusplus
}
#endif

#endif // DEFENSE_HARDENING_H
