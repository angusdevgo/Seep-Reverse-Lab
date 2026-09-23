#include <windows.h>
#include <stdio.h>
#include <stdbool.h>

#define LOG_FILE "C:\\Users\\Angus\\Desktop\\pi\\seep\\项目B\\localize\\logs\\项目B_version_guard.log"

static void WriteLog(const char* fmt, ...) {
    FILE* fp = fopen(LOG_FILE, "a+");
    if (!fp) return;
    
    SYSTEMTIME st;
    GetLocalTime(&st);
    fprintf(fp, "[%04d-%02d-%02d %02d:%02d:%02d.%03d] ",
            st.wYear, st.wMonth, st.wDay, st.wHour, st.wMinute, st.wSecond, st.wMilliseconds);
            
    va_list args;
    va_start(args, fmt);
    vfprintf(fp, fmt, args);
    va_end(args);
    
    fprintf(fp, "\n");
    fclose(fp);
}

typedef struct {
    const char* id;
    DWORD rva;
    unsigned char patch[8];
    size_t len;
    const char* desc;
} PatchPoint;

// 项目B.exe 精简高纯度、零堆栈破坏点位（包含 UI 决策与网络层，共 28 处）
static const PatchPoint g_mainPatches[] = {
    // 0. 前台 UI 会员决策核心 (纯寄存器返回值，零栈干扰)
    { "ui_member_check_direct",       0x00B47850, {0xb0, 0x01, 0xc3},                         3, "前台 UI 会员判定直接返回 1 (VIP)" },

    // 1. 网络登录回包反序列化 (用户在线登录/刷新时直接改写服务端下发的值)
    { "resp_expiry_2099",             0x00D0EEBA, {0xb8, 0x7f, 0xe6, 0x85, 0xf4},             5, "网络响应 到期时间 2099-12-31" },
    { "resp_member_status",           0x00D0EF4E, {0xb8, 0x01, 0x00, 0x00, 0x00},             5, "网络响应 会员状态置为 1" },
    { "resp_member_type",             0x00D0EFDA, {0xb8, 0x01, 0x00, 0x00, 0x00},             5, "网络响应 会员类型置为 VIP (1)" },
    { "resp_device_count",            0x00D0F065, {0xb8, 0x05, 0x00, 0x00, 0x00},             5, "网络响应 可用设备数置为 5" },
    { "resp_trial_status",            0x00D0F214, {0xb8, 0x02, 0x00, 0x00, 0x00},             5, "网络响应 试用状态置为 2" },
    { "resp_privilege_enable",        0x00D0F506, {0xb8, 0x01, 0x00, 0x00, 0x00},             5, "网络响应 特权使能置为 1" },

    // 2. 业务流程与弹窗阻断 (无损控制流)
    { "skip_trial_banner_flow",       0x00CE541F, {0xe9, 0xee, 0x00, 0x00, 0x00, 0x90},       6, "跳过试用与营销 Banner 流程" },
    { "member_remove_ad_ok_gate",     0x0012A640, {0xb8, 0x01, 0x00, 0x00, 0x00, 0xc3},       6, "广告剥离网关直接放行" },

    // 3. 账号缓存解析 A (从本地/云端 JSON 读入时注入，保证数据源 100% 纯正)
    { "parse_a_device_member",        0x01079CBE, {0xb8, 0x01, 0x00, 0x00, 0x00},             5, "缓存解析 A 设备会员置为 1" },
    { "parse_a_expiry_2099",          0x01079E18, {0xb8, 0x7f, 0xe6, 0x85, 0xf4},             5, "缓存解析 A 到期时间 2099-12-31" },
    { "parse_a_member_status",        0x01079E7B, {0xb8, 0x01, 0x00, 0x00, 0x00},             5, "缓存解析 A 会员状态置为 1" },
    { "parse_a_trial_status",         0x01079F3D, {0xb8, 0x02, 0x00, 0x00, 0x00},             5, "缓存解析 A 试用状态置为 2" },
    { "parse_a_member_type",          0x01079FB4, {0xb8, 0x01, 0x00, 0x00, 0x00},             5, "缓存解析 A 会员类型置为 VIP (1)" },

    // 4. 账号缓存解析 B (第二解析通道)
    { "parse_b_expiry_2099",          0x0107D165, {0xb8, 0x7f, 0xe6, 0x85, 0xf4},             5, "缓存解析 B 到期时间 2099-12-31" },
    { "parse_b_member_status",        0x0107D1ED, {0xb8, 0x01, 0x00, 0x00, 0x00},             5, "缓存解析 B 会员状态置为 1" },
    { "parse_b_device_member",        0x0107D240, {0xb8, 0x01, 0x00, 0x00, 0x00},             5, "缓存解析 B 设备权益置为 1" },
    { "parse_b_trial_status",         0x0107D3E1, {0xb8, 0x02, 0x00, 0x00, 0x00},             5, "缓存解析 B 试用状态置为 2" },
    { "parse_b_member_type",          0x0107D4C8, {0xb8, 0x01, 0x00, 0x00, 0x00},             5, "缓存解析 B 会员类型置为 VIP (1)" },

    // 5. 账号缓存序列化 A (写出到磁盘/内存缓存)
    { "serialize_a_expiry",           0x01073B8E, {0xb8, 0x7f, 0xe6, 0x85, 0xf4, 0x90, 0x90}, 7, "序列化 A 到期时间 2099-12-31" },
    { "serialize_a_member_status",    0x01073C8F, {0xb8, 0x01, 0x00, 0x00, 0x00, 0x90},       6, "序列化 A 会员状态 1" },
    { "serialize_a_member_type",      0x01073D80, {0xb8, 0x01, 0x00, 0x00, 0x00, 0x90},       6, "序列化 A 会员类型 1" },
    { "serialize_a_device_member",    0x01073F70, {0xb8, 0x01, 0x00, 0x00, 0x00, 0x90},       6, "序列化 A 设备权益 1" },
    { "serialize_a_trial",            0x01074042, {0xb8, 0x02, 0x00, 0x00, 0x00, 0x90},       6, "序列化 A 试用状态 2" },

    // 6. 账号缓存序列化 B (第二写出通道)
    { "serialize_b_expiry",           0x0107EE70, {0xb9, 0x7f, 0xe6, 0x85, 0xf4, 0x90, 0x90}, 7, "序列化 B 到期时间 2099-12-31" },
    { "serialize_b_member_status",    0x0107EF72, {0xb9, 0x01, 0x00, 0x00, 0x00, 0x90},       6, "序列化 B 会员状态 1" },
    { "serialize_b_device_member",    0x0107F13D, {0xb9, 0x01, 0x00, 0x00, 0x00, 0x90},       6, "序列化 B 设备权益 1" },
    { "serialize_b_member_type",      0x0107F2EE, {0xb9, 0x01, 0x00, 0x00, 0x00, 0x90},       6, "序列化 B 会员类型 1" },
    { "serialize_b_trial",            0x0107F3CD, {0xb9, 0x02, 0x00, 0x00, 0x00, 0x90},       6, "序列化 B 试用状态 2" }
};

// 项目B.exe 全量服务点位（共 10 处）
static const PatchPoint g_servicePatches[] = {
    { "svc_parse_a_device_member",    0x009F097E, {0xb8, 0x01, 0x00, 0x00, 0x00},             5, "Service 解析设备会员 1" },
    { "svc_parse_a_expiry",          0x009F0AD8, {0xb8, 0x7f, 0xe6, 0x85, 0xf4},             5, "Service 解析到期时间 2099" },
    { "svc_parse_a_member_status",   0x009F0B3B, {0xb8, 0x01, 0x00, 0x00, 0x00},             5, "Service 解析会员状态 1" },
    { "svc_parse_a_trial_status",    0x009F0BFD, {0xb8, 0x02, 0x00, 0x00, 0x00},             5, "Service 解析试用状态 2" },
    { "svc_parse_a_member_type",     0x009F0C74, {0xb8, 0x01, 0x00, 0x00, 0x00},             5, "Service 解析会员类型 1" },

    { "svc_serialize_a_expiry",      0x009EA84E, {0xb8, 0x7f, 0xe6, 0x85, 0xf4, 0x90, 0x90}, 7, "Service 序列化到期时间 2099" },
    { "svc_serialize_a_status",      0x009EA94F, {0xb8, 0x01, 0x00, 0x00, 0x00, 0x90},       6, "Service 序列化会员状态 1" },
    { "svc_serialize_a_type",        0x009EAA40, {0xb8, 0x01, 0x00, 0x00, 0x00, 0x90},       6, "Service 序列化会员类型 1" },
    { "svc_serialize_a_device",      0x009EAC30, {0xb8, 0x01, 0x00, 0x00, 0x00, 0x90},       6, "Service 序列化设备会员 1" },
    { "svc_serialize_a_trial",       0x009EAD02, {0xb8, 0x02, 0x00, 0x00, 0x00, 0x90},       6, "Service 序列化试用状态 2" }
};

static bool ApplyPatchPoint(uintptr_t baseAddr, const PatchPoint* p) {
    void* target = (void*)(baseAddr + p->rva);
    DWORD oldProtect = 0;
    if (!VirtualProtect(target, p->len, PAGE_EXECUTE_READWRITE, &oldProtect)) {
        return false;
    }
    memcpy(target, p->patch, p->len);
    VirtualProtect(target, p->len, oldProtect, &oldProtect);
    FlushInstructionCache(GetCurrentProcess(), target, p->len);
    return true;
}

// 单次初始化注入线程 (One-shot Execution - 彻底杜绝循环争用与闪退)
static DWORD WINAPI InitOneShotGuard(LPVOID lpParam) {
    char modPath[MAX_PATH] = {0};
    GetModuleFileNameA(NULL, modPath, MAX_PATH);
    
    bool isMain = (strstr(modPath, "项目B.exe") != NULL);
    bool isService = (strstr(modPath, "项目B.exe") != NULL);
    
    if (!isMain && !isService) {
        return 0;
    }
    
    uintptr_t baseAddr = (uintptr_t)GetModuleHandleA(NULL);
    const PatchPoint* patchList = isMain ? g_mainPatches : g_servicePatches;
    size_t patchCount = isMain ? (sizeof(g_mainPatches)/sizeof(g_mainPatches[0])) : (sizeof(g_servicePatches)/sizeof(g_servicePatches[0]));
    const char* procType = isMain ? "项目B" : "项目B";
    
    WriteLog("[OneShotGuard] Initializing for %s (PID: %lu, Base: 0x%p, Total: %zu)...",
             procType, GetCurrentProcessId(), (void*)baseAddr, patchCount);
             
    // 稍微等待主模块完成基础 PE 重定位
    Sleep(100);
    
    size_t okCount = 0;
    for (size_t i = 0; i < patchCount; i++) {
        if (ApplyPatchPoint(baseAddr, &patchList[i])) {
            okCount++;
        }
    }
    
    WriteLog("[OneShotGuard] Success: Applied %zu / %zu patches to %s. Thread completed cleanly.",
             okCount, patchCount, procType);
             
    return 0;
}

BOOL WINAPI DllMain(HINSTANCE hinstDLL, DWORD fdwReason, LPVOID lpvReserved) {
    if (fdwReason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(hinstDLL);
        // 单次创建工作线程进行安全注入，完成后线程自然结束
        HANDLE hThread = CreateThread(NULL, 0, InitOneShotGuard, NULL, 0, NULL);
        if (hThread) {
            CloseHandle(hThread);
        }
    }
    return TRUE;
}
