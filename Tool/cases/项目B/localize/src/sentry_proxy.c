#include <windows.h>
#include <stdio.h>
#include <stdbool.h>

// ==============================================================================
// 项目B Player Local Guard & Pure Patch Proxy DLL (sentry.dll)
// ==============================================================================

typedef struct {
    const char* name;
    DWORD rva;
    BYTE patch[16];
    BYTE orig[16];
    size_t len;
} PatchPoint;

// 基于当前版本 项目B.exe (SHA256: <实测哈希>)
// 经过点位校准的内存热补丁表
static PatchPoint g_Patches[] = {
    // 1. 账号序列化 A: 到期时间固定为 2099-12-31 (0xF485E67F)
    { "serialize_a_expiry",        0x01073B8E, { 0xb8, 0x7f, 0xe6, 0x85, 0xf4, 0x90, 0x90 }, { 0x48, 0x8b, 0x85, 0xc8, 0x02, 0x00, 0x00 }, 7 },
    // 2. 账号序列化 A: 会员状态强制为 1 (VIP)
    { "serialize_a_member_status", 0x01073C8F, { 0xb8, 0x01, 0x00, 0x00, 0x00, 0x90 },       { 0x8b, 0x85, 0xd4, 0x02, 0x00, 0x00 },       6 },
    // 3. 账号序列化 A: 会员类型强制为 VIP (1)
    { "serialize_a_member_type",   0x01073D80, { 0xb8, 0x01, 0x00, 0x00, 0x00, 0x90 },       { 0x8b, 0x85, 0xd8, 0x02, 0x00, 0x00 },       6 },
    // 4. 账号序列化 A: 当前设备权益强制启用 (1)
    { "serialize_a_device_member", 0x01073F70, { 0xb8, 0x01, 0x00, 0x00, 0x00, 0x90 },       { 0x8b, 0x85, 0x08, 0x03, 0x00, 0x00 },       6 },
    // 5. 账号序列化 A: 试用状态设为已使用/非活动 (2)
    { "serialize_a_trial",         0x01074042, { 0xb8, 0x02, 0x00, 0x00, 0x00, 0x90 },       { 0x8b, 0x85, 0x00, 0x03, 0x00, 0x00 },       6 },

    // 6. 账号序列化 B: 到期时间固定为 2099-12-31 (0xF485E67F)
    { "serialize_b_expiry",        0x0107EE70, { 0xb9, 0x7f, 0xe6, 0x85, 0xf4, 0x90, 0x90 }, { 0x48, 0x8b, 0x8d, 0x78, 0x03, 0x00, 0x00 }, 7 },
    // 7. 账号序列化 B: 会员状态强制为 1 (VIP)
    { "serialize_b_member_status", 0x0107EF72, { 0xb9, 0x01, 0x00, 0x00, 0x00, 0x90 },       { 0x8b, 0x8d, 0x84, 0x03, 0x00, 0x00 },       6 },
    // 8. 账号序列化 B: 当前设备权益强制启用 (1)
    { "serialize_b_device_member", 0x0107F13D, { 0xb9, 0x01, 0x00, 0x00, 0x00, 0x90 },       { 0x8b, 0x8d, 0x88, 0x03, 0x00, 0x00 },       6 },
    // 9. 账号序列化 B: 会员类型强制为 VIP (1)
    { "serialize_b_member_type",   0x0107F2EE, { 0xb9, 0x01, 0x00, 0x00, 0x00, 0x90 },       { 0x8b, 0x8d, 0xb0, 0x03, 0x00, 0x00 },       6 },
    // 10. 账号序列化 B: 试用状态设为已使用/非活动 (2)
    { "serialize_b_trial",         0x0107F3CD, { 0xb9, 0x02, 0x00, 0x00, 0x00, 0x90 },       { 0x8b, 0x8d, 0xb4, 0x03, 0x00, 0x00 },       6 },

    // 11. 跳过试用广告与推广 Banner 分支 (je/jle -> jmp)
    { "skip_trial_banner_flow",    0x00CE541F, { 0xe9, 0xee, 0x00, 0x00, 0x00, 0x90 },       { 0x0f, 0x8e, 0xed, 0x00, 0x00, 0x00 },       6 },

    // 12. 广告移除触发函数入口: sub_14012A640
    // 直接返回 1 (mov eax, 1; ret)
    { "member_remove_ad_ok_gate",  0x0012A640, { 0xb8, 0x01, 0x00, 0x00, 0x00, 0xc3 },       { 0x48, 0x89, 0x5c, 0x24, 0x08, 0x48 },       6 }
};

static const size_t g_NumPatches = sizeof(g_Patches) / sizeof(g_Patches[0]);

static void LogMessage(const char* format, ...) {
    char buf[1024];
    va_list args;
    va_start(args, format);
    vsnprintf(buf, sizeof(buf), format, args);
    va_end(args);

    OutputDebugStringA(buf);

    FILE* fp = fopen("C:\\Users\\Angus\\Desktop\\pi\\seep\\项目B\\localize\\logs\\项目B_local_guard.log", "a");
    if (fp) {
        SYSTEMTIME st;
        GetLocalTime(&st);
        fprintf(fp, "[%04d-%02d-%02d %02d:%02d:%02d.%03d] %s\n",
            st.wYear, st.wMonth, st.wDay, st.wHour, st.wMinute, st.wSecond, st.wMilliseconds, buf);
        fclose(fp);
    }
}

static DWORD WINAPI GuardWorkerThread(LPVOID lpParam) {
    LogMessage("[+] 项目B Local Guard Thread Started");

    // 预留足够时间等待主程序初始化和 PE 映射完成
    Sleep(1500);

    HMODULE hMain = GetModuleHandleA(NULL);
    if (!hMain) {
        LogMessage("[-] Failed to get main module handle");
        return 1;
    }

    uintptr_t base = (uintptr_t)hMain;
    LogMessage("[+] Main module base address: 0x%p", (void*)base);

    size_t applied = 0;
    for (size_t i = 0; i < g_NumPatches; i++) {
        PatchPoint* p = &g_Patches[i];
        void* targetAddr = (void*)(base + p->rva);

        // 验证内存保护属性并设置为可写
        DWORD oldProtect = 0;
        if (VirtualProtect(targetAddr, p->len, PAGE_EXECUTE_READWRITE, &oldProtect)) {
            // 核对原始字节匹配度（可选）
            if (memcmp(targetAddr, p->patch, p->len) == 0) {
                LogMessage("[*] Patch '%s' already applied at 0x%p", p->name, targetAddr);
                applied++;
            } else {
                memcpy(targetAddr, p->patch, p->len);
                FlushInstructionCache(GetCurrentProcess(), targetAddr, p->len);
                LogMessage("[+] Successfully applied patch '%s' at 0x%p", p->name, targetAddr);
                applied++;
            }
            VirtualProtect(targetAddr, p->len, oldProtect, &oldProtect);
        } else {
            LogMessage("[-] VirtualProtect failed for patch '%s' at 0x%p, Error=%lu",
                p->name, targetAddr, GetLastError());
        }
    }

    LogMessage("[SUCCESS] Total applied patches: %zu / %zu", applied, g_NumPatches);
    return 0;
}

BOOL WINAPI DllMain(HINSTANCE hinstDLL, DWORD fdwReason, LPVOID lpvReserved) {
    switch (fdwReason) {
        case DLL_PROCESS_ATTACH:
            DisableThreadLibraryCalls(hinstDLL);
            CreateThread(NULL, 0, GuardWorkerThread, NULL, 0, NULL);
            break;
        case DLL_PROCESS_DETACH:
            break;
    }
    return TRUE;
}
