#include <windows.h>

#define TARGET_PATCH1_RVA 0x66FC95
#define TARGET_PATCH2_RVA 0x66DB7B

// Patch 1 bytes (34 bytes)
static const unsigned char g_patch1[] = {
    0x66, 0xC7, 0x05, 0xAC, 0x46, 0xC8, 0x01, 0x00, 0x00,
    0xC7, 0x05, 0x9C, 0x90, 0xC7, 0x01, 0x00, 0x00, 0x00, 0x00,
    0xC7, 0x05, 0xAA, 0x50, 0xC7, 0x01, 0x05, 0x00, 0x00, 0x00,
    0xE9, 0xF0, 0x00, 0x00, 0x00
};

// Patch 2 bytes (5 bytes)
static const unsigned char g_patch2[] = {
    0x66, 0xB8, 0xFF, 0xFF, 0x90
};

static void ApplyMemoryPatch(void)
{
    HMODULE hModule = GetModuleHandleA(NULL);
    if (!hModule) return;

    uintptr_t base = (uintptr_t)hModule;
    void *patch1_addr = (void *)(base + TARGET_PATCH1_RVA);
    void *patch2_addr = (void *)(base + TARGET_PATCH2_RVA);

    DWORD oldProtect;

    // Apply Patch 1
    if (VirtualProtect(patch1_addr, sizeof(g_patch1), PAGE_EXECUTE_READWRITE, &oldProtect)) {
        memcpy(patch1_addr, g_patch1, sizeof(g_patch1));
        VirtualProtect(patch1_addr, sizeof(g_patch1), oldProtect, &oldProtect);
    }

    // Apply Patch 2
    if (VirtualProtect(patch2_addr, sizeof(g_patch2), PAGE_EXECUTE_READWRITE, &oldProtect)) {
        memcpy(patch2_addr, g_patch2, sizeof(g_patch2));
        VirtualProtect(patch2_addr, sizeof(g_patch2), oldProtect, &oldProtect);
    }
}

BOOL WINAPI DllMain(HINSTANCE hinstDLL, DWORD fdwReason, LPVOID lpReserved)
{
    if (fdwReason == DLL_PROCESS_ATTACH) {
        DisableThreadLibraryCalls(hinstDLL);
        ApplyMemoryPatch();
    }
    return TRUE;
}
