// Single-DLL Proxy: winhttp.dll (loaded by Main, Service, and RemoteService)
// Directly put into <安装目录>\nx_main\winhttp.dll to activate all 52 points!
#![allow(non_snake_case, non_upper_case_globals, static_mut_refs)]
use std::arch::naked_asm;
use std::ffi::c_void;
use std::io::Write;

type HMODULE = *mut u8;
type FARPROC = *const c_void;

const PAGE_EXECUTE_READWRITE: u32 = 0x40;

#[repr(C)]
struct SystemTime {
    wYear: u16,
    wMonth: u16,
    wDayOfWeek: u16,
    wDay: u16,
    wHour: u16,
    wMinute: u16,
    wSecond: u16,
    wMilliseconds: u16,
}

#[link(name = "kernel32")]
extern "system" {
    fn LoadLibraryW(lpLibFileName: *const u16) -> HMODULE;
    fn GetProcAddress(hModule: HMODULE, lpProcName: *const u8) -> FARPROC;
    fn GetModuleHandleA(name: *const u8) -> HMODULE;
    fn GetModuleFileNameA(h: HMODULE, buf: *mut u8, n: u32) -> u32;
    fn VirtualProtect(a: *mut u8, s: usize, np: u32, op: *mut u32) -> i32;
    fn FlushInstructionCache(h: *mut u8, a: *const u8, s: usize) -> i32;
    fn GetCurrentProcess() -> *mut u8;
    fn Sleep(ms: u32);
    fn CreateThread(
        a: *mut u8,
        s: usize,
        f: Option<extern "system" fn(*mut u8) -> u32>,
        p: *mut u8,
        fl: u32,
        id: *mut u32,
    ) -> *mut u8;
    fn GetEnvironmentVariableA(n: *const u8, b: *mut u8, s: u32) -> u32;
    fn GetLocalTime(t: *mut SystemTime);
    fn GetLastError() -> u32;
    fn ExitProcess(uExitCode: u32) -> !;
}

static mut REAL_WINHTTP: HMODULE = std::ptr::null_mut();

static mut P_DllCanUnloadNow: usize = 0;
static mut P_DllGetClassObject: usize = 0;
static mut P_Private1: usize = 0;
static mut P_SvchostPushServiceGlobals: usize = 0;
static mut P_WinHttpAddRequestHeaders: usize = 0;
static mut P_WinHttpAddRequestHeadersEx: usize = 0;
static mut P_WinHttpAutoProxySvcMain: usize = 0;
static mut P_WinHttpCheckPlatform: usize = 0;
static mut P_WinHttpCloseHandle: usize = 0;
static mut P_WinHttpConnect: usize = 0;
static mut P_WinHttpConnectionDeletePolicyEntries: usize = 0;
static mut P_WinHttpConnectionDeletePolicyEntriesByAppSid: usize = 0;
static mut P_WinHttpConnectionDeleteProxyInfo: usize = 0;
static mut P_WinHttpConnectionFreeNameList: usize = 0;
static mut P_WinHttpConnectionFreeProxyInfo: usize = 0;
static mut P_WinHttpConnectionFreeProxyList: usize = 0;
static mut P_WinHttpConnectionGetNameList: usize = 0;
static mut P_WinHttpConnectionGetProxyInfo: usize = 0;
static mut P_WinHttpConnectionGetProxyList: usize = 0;
static mut P_WinHttpConnectionOnlyConvert: usize = 0;
static mut P_WinHttpConnectionOnlyReceive: usize = 0;
static mut P_WinHttpConnectionOnlySend: usize = 0;
static mut P_WinHttpConnectionSetPolicyEntries: usize = 0;
static mut P_WinHttpConnectionSetProxyInfo: usize = 0;
static mut P_WinHttpConnectionUpdateIfIndexTable: usize = 0;
static mut P_WinHttpCrackUrl: usize = 0;
static mut P_WinHttpCreateProxyList: usize = 0;
static mut P_WinHttpCreateProxyManager: usize = 0;
static mut P_WinHttpCreateProxyResolver: usize = 0;
static mut P_WinHttpCreateProxyResult: usize = 0;
static mut P_WinHttpCreateUiCompatibleProxyString: usize = 0;
static mut P_WinHttpCreateUrl: usize = 0;
static mut P_WinHttpDetectAutoProxyConfigUrl: usize = 0;
static mut P_WinHttpFreeProxyResult: usize = 0;
static mut P_WinHttpFreeProxyResultEx: usize = 0;
static mut P_WinHttpFreeProxySettings: usize = 0;
static mut P_WinHttpFreeProxySettingsEx: usize = 0;
static mut P_WinHttpFreeQueryConnectionGroupResult: usize = 0;
static mut P_WinHttpGetDefaultProxyConfiguration: usize = 0;
static mut P_WinHttpGetIEProxyConfigForCurrentUser: usize = 0;
static mut P_WinHttpGetProxyForUrl: usize = 0;
static mut P_WinHttpGetProxyForUrlEx: usize = 0;
static mut P_WinHttpGetProxyForUrlEx2: usize = 0;
static mut P_WinHttpGetProxyForUrlHvsi: usize = 0;
static mut P_WinHttpGetProxyResult: usize = 0;
static mut P_WinHttpGetProxyResultEx: usize = 0;
static mut P_WinHttpGetProxySettingsEx: usize = 0;
static mut P_WinHttpGetProxySettingsResultEx: usize = 0;
static mut P_WinHttpGetProxySettingsVersion: usize = 0;
static mut P_WinHttpGetTunnelSocket: usize = 0;
static mut P_WinHttpOpen: usize = 0;
static mut P_WinHttpOpenRequest: usize = 0;
static mut P_WinHttpPacJsWorkerMain: usize = 0;
static mut P_WinHttpProbeConnectivity: usize = 0;
static mut P_WinHttpProtocolCompleteUpgrade: usize = 0;
static mut P_WinHttpProtocolReceive: usize = 0;
static mut P_WinHttpProtocolSend: usize = 0;
static mut P_WinHttpQueryAuthSchemes: usize = 0;
static mut P_WinHttpQueryConnectionGroup: usize = 0;
static mut P_WinHttpQueryDataAvailable: usize = 0;
static mut P_WinHttpQueryHeaders: usize = 0;
static mut P_WinHttpQueryHeadersEx: usize = 0;
static mut P_WinHttpQueryOption: usize = 0;
static mut P_WinHttpReadData: usize = 0;
static mut P_WinHttpReadDataEx: usize = 0;
static mut P_WinHttpReadProxySettings: usize = 0;
static mut P_WinHttpReadProxySettingsHvsi: usize = 0;
static mut P_WinHttpReceiveResponse: usize = 0;
static mut P_WinHttpRefreshProxySettings: usize = 0;
static mut P_WinHttpRegisterProxyChangeNotification: usize = 0;
static mut P_WinHttpResetAutoProxy: usize = 0;
static mut P_WinHttpResolverGetProxyForUrl: usize = 0;
static mut P_WinHttpSaveProxyCredentials: usize = 0;
static mut P_WinHttpSendRequest: usize = 0;
static mut P_WinHttpSetCredentials: usize = 0;
static mut P_WinHttpSetDefaultProxyConfiguration: usize = 0;
static mut P_WinHttpSetOption: usize = 0;
static mut P_WinHttpSetProxySettingsPerUser: usize = 0;
static mut P_WinHttpSetSecureLegacyServersAppCompat: usize = 0;
static mut P_WinHttpSetStatusCallback: usize = 0;
static mut P_WinHttpSetTimeouts: usize = 0;
static mut P_WinHttpTimeFromSystemTime: usize = 0;
static mut P_WinHttpTimeToSystemTime: usize = 0;
static mut P_WinHttpUnregisterProxyChangeNotification: usize = 0;
static mut P_WinHttpWebSocketClose: usize = 0;
static mut P_WinHttpWebSocketCompleteUpgrade: usize = 0;
static mut P_WinHttpWebSocketQueryCloseStatus: usize = 0;
static mut P_WinHttpWebSocketReceive: usize = 0;
static mut P_WinHttpWebSocketSend: usize = 0;
static mut P_WinHttpWebSocketShutdown: usize = 0;
static mut P_WinHttpWriteData: usize = 0;
static mut P_WinHttpWriteProxySettings: usize = 0;

unsafe fn init_real_winhttp() {
    let mut path = [0u16; 260];
    let sys_str = r"C:\Windows\System32\winhttp.dll";
    for (i, c) in sys_str.encode_utf16().chain(std::iter::once(0)).enumerate() {
        path[i] = c;
    }
    REAL_WINHTTP = LoadLibraryW(path.as_ptr());
    if !REAL_WINHTTP.is_null() {

        P_DllCanUnloadNow = GetProcAddress(REAL_WINHTTP, b"DllCanUnloadNow\0".as_ptr()) as usize;
        P_DllGetClassObject = GetProcAddress(REAL_WINHTTP, b"DllGetClassObject\0".as_ptr()) as usize;
        P_Private1 = GetProcAddress(REAL_WINHTTP, b"Private1\0".as_ptr()) as usize;
        P_SvchostPushServiceGlobals = GetProcAddress(REAL_WINHTTP, b"SvchostPushServiceGlobals\0".as_ptr()) as usize;
        P_WinHttpAddRequestHeaders = GetProcAddress(REAL_WINHTTP, b"WinHttpAddRequestHeaders\0".as_ptr()) as usize;
        P_WinHttpAddRequestHeadersEx = GetProcAddress(REAL_WINHTTP, b"WinHttpAddRequestHeadersEx\0".as_ptr()) as usize;
        P_WinHttpAutoProxySvcMain = GetProcAddress(REAL_WINHTTP, b"WinHttpAutoProxySvcMain\0".as_ptr()) as usize;
        P_WinHttpCheckPlatform = GetProcAddress(REAL_WINHTTP, b"WinHttpCheckPlatform\0".as_ptr()) as usize;
        P_WinHttpCloseHandle = GetProcAddress(REAL_WINHTTP, b"WinHttpCloseHandle\0".as_ptr()) as usize;
        P_WinHttpConnect = GetProcAddress(REAL_WINHTTP, b"WinHttpConnect\0".as_ptr()) as usize;
        P_WinHttpConnectionDeletePolicyEntries = GetProcAddress(REAL_WINHTTP, b"WinHttpConnectionDeletePolicyEntries\0".as_ptr()) as usize;
        P_WinHttpConnectionDeletePolicyEntriesByAppSid = GetProcAddress(REAL_WINHTTP, b"WinHttpConnectionDeletePolicyEntriesByAppSid\0".as_ptr()) as usize;
        P_WinHttpConnectionDeleteProxyInfo = GetProcAddress(REAL_WINHTTP, b"WinHttpConnectionDeleteProxyInfo\0".as_ptr()) as usize;
        P_WinHttpConnectionFreeNameList = GetProcAddress(REAL_WINHTTP, b"WinHttpConnectionFreeNameList\0".as_ptr()) as usize;
        P_WinHttpConnectionFreeProxyInfo = GetProcAddress(REAL_WINHTTP, b"WinHttpConnectionFreeProxyInfo\0".as_ptr()) as usize;
        P_WinHttpConnectionFreeProxyList = GetProcAddress(REAL_WINHTTP, b"WinHttpConnectionFreeProxyList\0".as_ptr()) as usize;
        P_WinHttpConnectionGetNameList = GetProcAddress(REAL_WINHTTP, b"WinHttpConnectionGetNameList\0".as_ptr()) as usize;
        P_WinHttpConnectionGetProxyInfo = GetProcAddress(REAL_WINHTTP, b"WinHttpConnectionGetProxyInfo\0".as_ptr()) as usize;
        P_WinHttpConnectionGetProxyList = GetProcAddress(REAL_WINHTTP, b"WinHttpConnectionGetProxyList\0".as_ptr()) as usize;
        P_WinHttpConnectionOnlyConvert = GetProcAddress(REAL_WINHTTP, b"WinHttpConnectionOnlyConvert\0".as_ptr()) as usize;
        P_WinHttpConnectionOnlyReceive = GetProcAddress(REAL_WINHTTP, b"WinHttpConnectionOnlyReceive\0".as_ptr()) as usize;
        P_WinHttpConnectionOnlySend = GetProcAddress(REAL_WINHTTP, b"WinHttpConnectionOnlySend\0".as_ptr()) as usize;
        P_WinHttpConnectionSetPolicyEntries = GetProcAddress(REAL_WINHTTP, b"WinHttpConnectionSetPolicyEntries\0".as_ptr()) as usize;
        P_WinHttpConnectionSetProxyInfo = GetProcAddress(REAL_WINHTTP, b"WinHttpConnectionSetProxyInfo\0".as_ptr()) as usize;
        P_WinHttpConnectionUpdateIfIndexTable = GetProcAddress(REAL_WINHTTP, b"WinHttpConnectionUpdateIfIndexTable\0".as_ptr()) as usize;
        P_WinHttpCrackUrl = GetProcAddress(REAL_WINHTTP, b"WinHttpCrackUrl\0".as_ptr()) as usize;
        P_WinHttpCreateProxyList = GetProcAddress(REAL_WINHTTP, b"WinHttpCreateProxyList\0".as_ptr()) as usize;
        P_WinHttpCreateProxyManager = GetProcAddress(REAL_WINHTTP, b"WinHttpCreateProxyManager\0".as_ptr()) as usize;
        P_WinHttpCreateProxyResolver = GetProcAddress(REAL_WINHTTP, b"WinHttpCreateProxyResolver\0".as_ptr()) as usize;
        P_WinHttpCreateProxyResult = GetProcAddress(REAL_WINHTTP, b"WinHttpCreateProxyResult\0".as_ptr()) as usize;
        P_WinHttpCreateUiCompatibleProxyString = GetProcAddress(REAL_WINHTTP, b"WinHttpCreateUiCompatibleProxyString\0".as_ptr()) as usize;
        P_WinHttpCreateUrl = GetProcAddress(REAL_WINHTTP, b"WinHttpCreateUrl\0".as_ptr()) as usize;
        P_WinHttpDetectAutoProxyConfigUrl = GetProcAddress(REAL_WINHTTP, b"WinHttpDetectAutoProxyConfigUrl\0".as_ptr()) as usize;
        P_WinHttpFreeProxyResult = GetProcAddress(REAL_WINHTTP, b"WinHttpFreeProxyResult\0".as_ptr()) as usize;
        P_WinHttpFreeProxyResultEx = GetProcAddress(REAL_WINHTTP, b"WinHttpFreeProxyResultEx\0".as_ptr()) as usize;
        P_WinHttpFreeProxySettings = GetProcAddress(REAL_WINHTTP, b"WinHttpFreeProxySettings\0".as_ptr()) as usize;
        P_WinHttpFreeProxySettingsEx = GetProcAddress(REAL_WINHTTP, b"WinHttpFreeProxySettingsEx\0".as_ptr()) as usize;
        P_WinHttpFreeQueryConnectionGroupResult = GetProcAddress(REAL_WINHTTP, b"WinHttpFreeQueryConnectionGroupResult\0".as_ptr()) as usize;
        P_WinHttpGetDefaultProxyConfiguration = GetProcAddress(REAL_WINHTTP, b"WinHttpGetDefaultProxyConfiguration\0".as_ptr()) as usize;
        P_WinHttpGetIEProxyConfigForCurrentUser = GetProcAddress(REAL_WINHTTP, b"WinHttpGetIEProxyConfigForCurrentUser\0".as_ptr()) as usize;
        P_WinHttpGetProxyForUrl = GetProcAddress(REAL_WINHTTP, b"WinHttpGetProxyForUrl\0".as_ptr()) as usize;
        P_WinHttpGetProxyForUrlEx = GetProcAddress(REAL_WINHTTP, b"WinHttpGetProxyForUrlEx\0".as_ptr()) as usize;
        P_WinHttpGetProxyForUrlEx2 = GetProcAddress(REAL_WINHTTP, b"WinHttpGetProxyForUrlEx2\0".as_ptr()) as usize;
        P_WinHttpGetProxyForUrlHvsi = GetProcAddress(REAL_WINHTTP, b"WinHttpGetProxyForUrlHvsi\0".as_ptr()) as usize;
        P_WinHttpGetProxyResult = GetProcAddress(REAL_WINHTTP, b"WinHttpGetProxyResult\0".as_ptr()) as usize;
        P_WinHttpGetProxyResultEx = GetProcAddress(REAL_WINHTTP, b"WinHttpGetProxyResultEx\0".as_ptr()) as usize;
        P_WinHttpGetProxySettingsEx = GetProcAddress(REAL_WINHTTP, b"WinHttpGetProxySettingsEx\0".as_ptr()) as usize;
        P_WinHttpGetProxySettingsResultEx = GetProcAddress(REAL_WINHTTP, b"WinHttpGetProxySettingsResultEx\0".as_ptr()) as usize;
        P_WinHttpGetProxySettingsVersion = GetProcAddress(REAL_WINHTTP, b"WinHttpGetProxySettingsVersion\0".as_ptr()) as usize;
        P_WinHttpGetTunnelSocket = GetProcAddress(REAL_WINHTTP, b"WinHttpGetTunnelSocket\0".as_ptr()) as usize;
        P_WinHttpOpen = GetProcAddress(REAL_WINHTTP, b"WinHttpOpen\0".as_ptr()) as usize;
        P_WinHttpOpenRequest = GetProcAddress(REAL_WINHTTP, b"WinHttpOpenRequest\0".as_ptr()) as usize;
        P_WinHttpPacJsWorkerMain = GetProcAddress(REAL_WINHTTP, b"WinHttpPacJsWorkerMain\0".as_ptr()) as usize;
        P_WinHttpProbeConnectivity = GetProcAddress(REAL_WINHTTP, b"WinHttpProbeConnectivity\0".as_ptr()) as usize;
        P_WinHttpProtocolCompleteUpgrade = GetProcAddress(REAL_WINHTTP, b"WinHttpProtocolCompleteUpgrade\0".as_ptr()) as usize;
        P_WinHttpProtocolReceive = GetProcAddress(REAL_WINHTTP, b"WinHttpProtocolReceive\0".as_ptr()) as usize;
        P_WinHttpProtocolSend = GetProcAddress(REAL_WINHTTP, b"WinHttpProtocolSend\0".as_ptr()) as usize;
        P_WinHttpQueryAuthSchemes = GetProcAddress(REAL_WINHTTP, b"WinHttpQueryAuthSchemes\0".as_ptr()) as usize;
        P_WinHttpQueryConnectionGroup = GetProcAddress(REAL_WINHTTP, b"WinHttpQueryConnectionGroup\0".as_ptr()) as usize;
        P_WinHttpQueryDataAvailable = GetProcAddress(REAL_WINHTTP, b"WinHttpQueryDataAvailable\0".as_ptr()) as usize;
        P_WinHttpQueryHeaders = GetProcAddress(REAL_WINHTTP, b"WinHttpQueryHeaders\0".as_ptr()) as usize;
        P_WinHttpQueryHeadersEx = GetProcAddress(REAL_WINHTTP, b"WinHttpQueryHeadersEx\0".as_ptr()) as usize;
        P_WinHttpQueryOption = GetProcAddress(REAL_WINHTTP, b"WinHttpQueryOption\0".as_ptr()) as usize;
        P_WinHttpReadData = GetProcAddress(REAL_WINHTTP, b"WinHttpReadData\0".as_ptr()) as usize;
        P_WinHttpReadDataEx = GetProcAddress(REAL_WINHTTP, b"WinHttpReadDataEx\0".as_ptr()) as usize;
        P_WinHttpReadProxySettings = GetProcAddress(REAL_WINHTTP, b"WinHttpReadProxySettings\0".as_ptr()) as usize;
        P_WinHttpReadProxySettingsHvsi = GetProcAddress(REAL_WINHTTP, b"WinHttpReadProxySettingsHvsi\0".as_ptr()) as usize;
        P_WinHttpReceiveResponse = GetProcAddress(REAL_WINHTTP, b"WinHttpReceiveResponse\0".as_ptr()) as usize;
        P_WinHttpRefreshProxySettings = GetProcAddress(REAL_WINHTTP, b"WinHttpRefreshProxySettings\0".as_ptr()) as usize;
        P_WinHttpRegisterProxyChangeNotification = GetProcAddress(REAL_WINHTTP, b"WinHttpRegisterProxyChangeNotification\0".as_ptr()) as usize;
        P_WinHttpResetAutoProxy = GetProcAddress(REAL_WINHTTP, b"WinHttpResetAutoProxy\0".as_ptr()) as usize;
        P_WinHttpResolverGetProxyForUrl = GetProcAddress(REAL_WINHTTP, b"WinHttpResolverGetProxyForUrl\0".as_ptr()) as usize;
        P_WinHttpSaveProxyCredentials = GetProcAddress(REAL_WINHTTP, b"WinHttpSaveProxyCredentials\0".as_ptr()) as usize;
        P_WinHttpSendRequest = GetProcAddress(REAL_WINHTTP, b"WinHttpSendRequest\0".as_ptr()) as usize;
        P_WinHttpSetCredentials = GetProcAddress(REAL_WINHTTP, b"WinHttpSetCredentials\0".as_ptr()) as usize;
        P_WinHttpSetDefaultProxyConfiguration = GetProcAddress(REAL_WINHTTP, b"WinHttpSetDefaultProxyConfiguration\0".as_ptr()) as usize;
        P_WinHttpSetOption = GetProcAddress(REAL_WINHTTP, b"WinHttpSetOption\0".as_ptr()) as usize;
        P_WinHttpSetProxySettingsPerUser = GetProcAddress(REAL_WINHTTP, b"WinHttpSetProxySettingsPerUser\0".as_ptr()) as usize;
        P_WinHttpSetSecureLegacyServersAppCompat = GetProcAddress(REAL_WINHTTP, b"WinHttpSetSecureLegacyServersAppCompat\0".as_ptr()) as usize;
        P_WinHttpSetStatusCallback = GetProcAddress(REAL_WINHTTP, b"WinHttpSetStatusCallback\0".as_ptr()) as usize;
        P_WinHttpSetTimeouts = GetProcAddress(REAL_WINHTTP, b"WinHttpSetTimeouts\0".as_ptr()) as usize;
        P_WinHttpTimeFromSystemTime = GetProcAddress(REAL_WINHTTP, b"WinHttpTimeFromSystemTime\0".as_ptr()) as usize;
        P_WinHttpTimeToSystemTime = GetProcAddress(REAL_WINHTTP, b"WinHttpTimeToSystemTime\0".as_ptr()) as usize;
        P_WinHttpUnregisterProxyChangeNotification = GetProcAddress(REAL_WINHTTP, b"WinHttpUnregisterProxyChangeNotification\0".as_ptr()) as usize;
        P_WinHttpWebSocketClose = GetProcAddress(REAL_WINHTTP, b"WinHttpWebSocketClose\0".as_ptr()) as usize;
        P_WinHttpWebSocketCompleteUpgrade = GetProcAddress(REAL_WINHTTP, b"WinHttpWebSocketCompleteUpgrade\0".as_ptr()) as usize;
        P_WinHttpWebSocketQueryCloseStatus = GetProcAddress(REAL_WINHTTP, b"WinHttpWebSocketQueryCloseStatus\0".as_ptr()) as usize;
        P_WinHttpWebSocketReceive = GetProcAddress(REAL_WINHTTP, b"WinHttpWebSocketReceive\0".as_ptr()) as usize;
        P_WinHttpWebSocketSend = GetProcAddress(REAL_WINHTTP, b"WinHttpWebSocketSend\0".as_ptr()) as usize;
        P_WinHttpWebSocketShutdown = GetProcAddress(REAL_WINHTTP, b"WinHttpWebSocketShutdown\0".as_ptr()) as usize;
        P_WinHttpWriteData = GetProcAddress(REAL_WINHTTP, b"WinHttpWriteData\0".as_ptr()) as usize;
        P_WinHttpWriteProxySettings = GetProcAddress(REAL_WINHTTP, b"WinHttpWriteProxySettings\0".as_ptr()) as usize;
    }
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn DllCanUnloadNow() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_DllCanUnloadNow);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn DllGetClassObject() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_DllGetClassObject);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn Private1() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_Private1);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn SvchostPushServiceGlobals() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_SvchostPushServiceGlobals);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpAddRequestHeaders() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpAddRequestHeaders);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpAddRequestHeadersEx() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpAddRequestHeadersEx);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpAutoProxySvcMain() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpAutoProxySvcMain);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpCheckPlatform() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpCheckPlatform);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpCloseHandle() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpCloseHandle);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpConnect() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpConnect);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpConnectionDeletePolicyEntries() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpConnectionDeletePolicyEntries);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpConnectionDeletePolicyEntriesByAppSid() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpConnectionDeletePolicyEntriesByAppSid);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpConnectionDeleteProxyInfo() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpConnectionDeleteProxyInfo);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpConnectionFreeNameList() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpConnectionFreeNameList);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpConnectionFreeProxyInfo() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpConnectionFreeProxyInfo);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpConnectionFreeProxyList() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpConnectionFreeProxyList);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpConnectionGetNameList() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpConnectionGetNameList);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpConnectionGetProxyInfo() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpConnectionGetProxyInfo);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpConnectionGetProxyList() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpConnectionGetProxyList);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpConnectionOnlyConvert() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpConnectionOnlyConvert);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpConnectionOnlyReceive() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpConnectionOnlyReceive);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpConnectionOnlySend() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpConnectionOnlySend);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpConnectionSetPolicyEntries() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpConnectionSetPolicyEntries);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpConnectionSetProxyInfo() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpConnectionSetProxyInfo);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpConnectionUpdateIfIndexTable() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpConnectionUpdateIfIndexTable);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpCrackUrl() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpCrackUrl);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpCreateProxyList() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpCreateProxyList);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpCreateProxyManager() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpCreateProxyManager);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpCreateProxyResolver() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpCreateProxyResolver);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpCreateProxyResult() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpCreateProxyResult);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpCreateUiCompatibleProxyString() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpCreateUiCompatibleProxyString);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpCreateUrl() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpCreateUrl);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpDetectAutoProxyConfigUrl() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpDetectAutoProxyConfigUrl);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpFreeProxyResult() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpFreeProxyResult);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpFreeProxyResultEx() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpFreeProxyResultEx);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpFreeProxySettings() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpFreeProxySettings);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpFreeProxySettingsEx() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpFreeProxySettingsEx);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpFreeQueryConnectionGroupResult() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpFreeQueryConnectionGroupResult);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpGetDefaultProxyConfiguration() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpGetDefaultProxyConfiguration);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpGetIEProxyConfigForCurrentUser() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpGetIEProxyConfigForCurrentUser);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpGetProxyForUrl() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpGetProxyForUrl);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpGetProxyForUrlEx() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpGetProxyForUrlEx);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpGetProxyForUrlEx2() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpGetProxyForUrlEx2);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpGetProxyForUrlHvsi() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpGetProxyForUrlHvsi);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpGetProxyResult() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpGetProxyResult);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpGetProxyResultEx() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpGetProxyResultEx);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpGetProxySettingsEx() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpGetProxySettingsEx);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpGetProxySettingsResultEx() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpGetProxySettingsResultEx);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpGetProxySettingsVersion() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpGetProxySettingsVersion);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpGetTunnelSocket() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpGetTunnelSocket);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpOpen() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpOpen);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpOpenRequest() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpOpenRequest);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpPacJsWorkerMain() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpPacJsWorkerMain);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpProbeConnectivity() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpProbeConnectivity);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpProtocolCompleteUpgrade() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpProtocolCompleteUpgrade);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpProtocolReceive() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpProtocolReceive);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpProtocolSend() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpProtocolSend);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpQueryAuthSchemes() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpQueryAuthSchemes);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpQueryConnectionGroup() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpQueryConnectionGroup);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpQueryDataAvailable() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpQueryDataAvailable);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpQueryHeaders() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpQueryHeaders);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpQueryHeadersEx() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpQueryHeadersEx);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpQueryOption() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpQueryOption);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpReadData() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpReadData);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpReadDataEx() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpReadDataEx);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpReadProxySettings() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpReadProxySettings);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpReadProxySettingsHvsi() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpReadProxySettingsHvsi);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpReceiveResponse() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpReceiveResponse);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpRefreshProxySettings() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpRefreshProxySettings);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpRegisterProxyChangeNotification() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpRegisterProxyChangeNotification);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpResetAutoProxy() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpResetAutoProxy);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpResolverGetProxyForUrl() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpResolverGetProxyForUrl);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpSaveProxyCredentials() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpSaveProxyCredentials);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpSendRequest() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpSendRequest);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpSetCredentials() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpSetCredentials);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpSetDefaultProxyConfiguration() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpSetDefaultProxyConfiguration);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpSetOption() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpSetOption);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpSetProxySettingsPerUser() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpSetProxySettingsPerUser);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpSetSecureLegacyServersAppCompat() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpSetSecureLegacyServersAppCompat);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpSetStatusCallback() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpSetStatusCallback);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpSetTimeouts() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpSetTimeouts);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpTimeFromSystemTime() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpTimeFromSystemTime);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpTimeToSystemTime() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpTimeToSystemTime);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpUnregisterProxyChangeNotification() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpUnregisterProxyChangeNotification);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpWebSocketClose() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpWebSocketClose);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpWebSocketCompleteUpgrade() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpWebSocketCompleteUpgrade);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpWebSocketQueryCloseStatus() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpWebSocketQueryCloseStatus);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpWebSocketReceive() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpWebSocketReceive);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpWebSocketSend() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpWebSocketSend);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpWebSocketShutdown() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpWebSocketShutdown);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpWriteData() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpWriteData);
}

#[unsafe(naked)]
#[no_mangle]
pub unsafe extern "system" fn WinHttpWriteProxySettings() {
    naked_asm!("mov rax, qword ptr [rip + {slot}]", "jmp rax", slot = sym P_WinHttpWriteProxySettings);
}


struct PatchPoint {
    id: &'static str,
    rva: u32,
    orig: &'static [u8],
    patch: &'static [u8],
    optional: bool,
}

static POINTS_MAIN: &[PatchPoint] = &[
    PatchPoint { id: "nxmain_ad_gate_member_remove_ad_ok_bypass", rva: 0x12B9A3, orig: &[0x0f, 0x84, 0xb9, 0x01, 0x00, 0x00], patch: &[0x90, 0x90, 0x90, 0x90, 0x90, 0x90], optional: false },
    PatchPoint { id: "nxmain_skip_trial_banner_flow", rva: 0xCF01DF, orig: &[0x0f, 0x8e, 0xed, 0x00, 0x00, 0x00], patch: &[0xe9, 0xee, 0x00, 0x00, 0x00, 0x90], optional: false },
    PatchPoint { id: "nxmain_resp_expiry_2099_12_31", rva: 0xD19C7A, orig: &[0xe8, 0x28, 0x42, 0x31, 0xff], patch: &[0xb8, 0x7f, 0xe6, 0x85, 0xf4], optional: false },
    PatchPoint { id: "nxmain_resp_member_status_enabled", rva: 0xD19D0E, orig: &[0xe8, 0x8e, 0x9f, 0x2e, 0xff], patch: &[0xb8, 0x01, 0x00, 0x00, 0x00], optional: false },
    PatchPoint { id: "nxmain_resp_member_type_vip", rva: 0xD19D9A, orig: &[0xe8, 0x02, 0x9f, 0x2e, 0xff], patch: &[0xb8, 0x01, 0x00, 0x00, 0x00], optional: false },
    PatchPoint { id: "nxmain_resp_device_count_5", rva: 0xD19E25, orig: &[0xe8, 0x77, 0x9e, 0x2e, 0xff], patch: &[0xb8, 0x05, 0x00, 0x00, 0x00], optional: false },
    PatchPoint { id: "nxmain_resp_trial_status_used", rva: 0xD19FD4, orig: &[0xe8, 0xc8, 0x9c, 0x2e, 0xff], patch: &[0xb8, 0x02, 0x00, 0x00, 0x00], optional: false },
    PatchPoint { id: "nxmain_resp_privilege_enable", rva: 0xD1A2C6, orig: &[0xe8, 0xd6, 0x99, 0x2e, 0xff], patch: &[0xb8, 0x01, 0x00, 0x00, 0x00], optional: false },
    PatchPoint { id: "nxmain_parse_a_device_member_enabled", rva: 0x1086BBE, orig: &[0xe8, 0xde, 0xd0, 0xf7, 0xfe], patch: &[0xb8, 0x01, 0x00, 0x00, 0x00], optional: false },
    PatchPoint { id: "nxmain_parse_a_expiry_2099_12_31", rva: 0x1086D18, orig: &[0xe8, 0x8a, 0x71, 0xfa, 0xfe], patch: &[0xb8, 0x7f, 0xe6, 0x85, 0xf4], optional: false },
    PatchPoint { id: "nxmain_parse_a_member_status_enabled", rva: 0x1086D7B, orig: &[0xe8, 0x21, 0xcf, 0xf7, 0xfe], patch: &[0xb8, 0x01, 0x00, 0x00, 0x00], optional: false },
    PatchPoint { id: "nxmain_parse_a_trial_status_used", rva: 0x1086E3D, orig: &[0xe8, 0x5f, 0xce, 0xf7, 0xfe], patch: &[0xb8, 0x02, 0x00, 0x00, 0x00], optional: false },
    PatchPoint { id: "nxmain_parse_a_member_type_vip", rva: 0x1086EB4, orig: &[0xe8, 0xe8, 0xcd, 0xf7, 0xfe], patch: &[0xb8, 0x01, 0x00, 0x00, 0x00], optional: false },
    PatchPoint { id: "nxmain_parse_b_expiry_2099_12_31", rva: 0x108A065, orig: &[0xe8, 0x3d, 0x3e, 0xfa, 0xfe], patch: &[0xb8, 0x7f, 0xe6, 0x85, 0xf4], optional: false },
    PatchPoint { id: "nxmain_parse_b_member_status_enabled", rva: 0x108A0ED, orig: &[0xe8, 0xaf, 0x9b, 0xf7, 0xfe], patch: &[0xb8, 0x01, 0x00, 0x00, 0x00], optional: false },
    PatchPoint { id: "nxmain_parse_b_device_member_enabled", rva: 0x108A140, orig: &[0xe8, 0x5c, 0x9b, 0xf7, 0xfe], patch: &[0xb8, 0x01, 0x00, 0x00, 0x00], optional: false },
    PatchPoint { id: "nxmain_parse_b_trial_status_used", rva: 0x108A2E1, orig: &[0xe8, 0xbb, 0x99, 0xf7, 0xfe], patch: &[0xb8, 0x02, 0x00, 0x00, 0x00], optional: false },
    PatchPoint { id: "nxmain_parse_b_member_type_vip", rva: 0x108A3C8, orig: &[0xe8, 0xd4, 0x98, 0xf7, 0xfe], patch: &[0xb8, 0x01, 0x00, 0x00, 0x00], optional: false },
    PatchPoint { id: "nxmain_serialize_a_expiry_2099_12_31", rva: 0x1080A8E, orig: &[0x48, 0x8b, 0x85, 0xc8, 0x02, 0x00, 0x00], patch: &[0xb8, 0x7f, 0xe6, 0x85, 0xf4, 0x90, 0x90], optional: false },
    PatchPoint { id: "nxmain_serialize_a_member_status_enabled", rva: 0x1080B8F, orig: &[0x8b, 0x85, 0xd4, 0x02, 0x00, 0x00], patch: &[0xb8, 0x01, 0x00, 0x00, 0x00, 0x90], optional: false },
    PatchPoint { id: "nxmain_serialize_a_member_type_vip", rva: 0x1080C80, orig: &[0x8b, 0x85, 0xd8, 0x02, 0x00, 0x00], patch: &[0xb8, 0x01, 0x00, 0x00, 0x00, 0x90], optional: false },
    PatchPoint { id: "nxmain_serialize_a_device_member_enabled", rva: 0x1080E70, orig: &[0x8b, 0x85, 0x08, 0x03, 0x00, 0x00], patch: &[0xb8, 0x01, 0x00, 0x00, 0x00, 0x90], optional: false },
    PatchPoint { id: "nxmain_serialize_a_trial_status_used", rva: 0x1080F42, orig: &[0x8b, 0x85, 0x00, 0x03, 0x00, 0x00], patch: &[0xb8, 0x02, 0x00, 0x00, 0x00, 0x90], optional: false },
    PatchPoint { id: "nxmain_serialize_b_expiry_2099_12_31", rva: 0x108BD70, orig: &[0x48, 0x8b, 0x8d, 0x78, 0x03, 0x00, 0x00], patch: &[0xb9, 0x7f, 0xe6, 0x85, 0xf4, 0x90, 0x90], optional: false },
    PatchPoint { id: "nxmain_serialize_b_member_status_enabled", rva: 0x108BE72, orig: &[0x8b, 0x8d, 0x84, 0x03, 0x00, 0x00], patch: &[0xb9, 0x01, 0x00, 0x00, 0x00, 0x90], optional: false },
    PatchPoint { id: "nxmain_serialize_b_device_member_enabled", rva: 0x108C03D, orig: &[0x8b, 0x8d, 0x88, 0x03, 0x00, 0x00], patch: &[0xb9, 0x01, 0x00, 0x00, 0x00, 0x90], optional: false },
    PatchPoint { id: "nxmain_serialize_b_member_type_vip", rva: 0x108C1EE, orig: &[0x8b, 0x8d, 0xb0, 0x03, 0x00, 0x00], patch: &[0xb9, 0x01, 0x00, 0x00, 0x00, 0x90], optional: false },
    PatchPoint { id: "nxmain_serialize_b_trial_status_used", rva: 0x108C2CD, orig: &[0x8b, 0x8d, 0xb4, 0x03, 0x00, 0x00], patch: &[0xb9, 0x02, 0x00, 0x00, 0x00, 0x90], optional: false },
    PatchPoint { id: "nxmain_ui_member_check_direct", rva: 0xB50D80, orig: &[0x48, 0x8b, 0x89, 0x48, 0x01, 0x00, 0x00, 0x48, 0x85, 0xc9, 0x74, 0x07, 0x48, 0x8b, 0x01, 0x48, 0xff, 0x60, 0x18, 0x32, 0xc0, 0xc3], patch: &[0xb0, 0x01, 0xc3], optional: false },
    PatchPoint { id: "nxmain_ui_member_check_direct_b", rva: 0xB52810, orig: &[0x48, 0x8b, 0x89, 0xc8, 0x01, 0x00, 0x00, 0x48, 0x85, 0xc9, 0x74, 0x0a, 0x48, 0x8b, 0x01, 0x48, 0xff, 0xa0, 0xb8, 0x00, 0x00, 0x00, 0x32, 0xc0, 0xc3], patch: &[0xb0, 0x01, 0xc3], optional: true },
];

static POINTS_SERVICE: &[PatchPoint] = &[
    PatchPoint { id: "nxservice_parse_a_device_member_enabled", rva: 0xA0104E, orig: &[0xe8, 0xd0, 0x22, 0x60, 0xff], patch: &[0xb8, 0x01, 0x00, 0x00, 0x00], optional: false },
    PatchPoint { id: "nxservice_parse_a_expiry_2099_12_31", rva: 0xA011A8, orig: &[0xe8, 0x8a, 0x2e, 0x62, 0xff], patch: &[0xb8, 0x7f, 0xe6, 0x85, 0xf4], optional: false },
    PatchPoint { id: "nxservice_parse_a_member_status_enabled", rva: 0xA0120B, orig: &[0xe8, 0x13, 0x21, 0x60, 0xff], patch: &[0xb8, 0x01, 0x00, 0x00, 0x00], optional: false },
    PatchPoint { id: "nxservice_parse_a_trial_status_used", rva: 0xA012CD, orig: &[0xe8, 0x51, 0x20, 0x60, 0xff], patch: &[0xb8, 0x02, 0x00, 0x00, 0x00], optional: false },
    PatchPoint { id: "nxservice_parse_a_member_type_vip", rva: 0xA01344, orig: &[0xe8, 0xda, 0x1f, 0x60, 0xff], patch: &[0xb8, 0x01, 0x00, 0x00, 0x00], optional: false },
    PatchPoint { id: "nxservice_parse_a_is_valid_infos_true", rva: 0xA014E4, orig: &[0xe8, 0x00, 0xad, 0x60, 0xff], patch: &[0xb0, 0x01, 0x90, 0x90, 0x90], optional: false },
    PatchPoint { id: "nxservice_parse_b_expiry_2099_12_31", rva: 0xA044F5, orig: &[0xe8, 0x3d, 0xfb, 0x61, 0xff], patch: &[0xb8, 0x7f, 0xe6, 0x85, 0xf4], optional: false },
    PatchPoint { id: "nxservice_parse_b_member_status_enabled", rva: 0xA0457D, orig: &[0xe8, 0xa1, 0xed, 0x5f, 0xff], patch: &[0xb8, 0x01, 0x00, 0x00, 0x00], optional: false },
    PatchPoint { id: "nxservice_parse_b_device_member_enabled", rva: 0xA045D0, orig: &[0xe8, 0x4e, 0xed, 0x5f, 0xff], patch: &[0xb8, 0x01, 0x00, 0x00, 0x00], optional: false },
    PatchPoint { id: "nxservice_parse_b_trial_status_used", rva: 0xA04771, orig: &[0xe8, 0xad, 0xeb, 0x5f, 0xff], patch: &[0xb8, 0x02, 0x00, 0x00, 0x00], optional: false },
    PatchPoint { id: "nxservice_parse_b_member_type_vip", rva: 0xA04858, orig: &[0xe8, 0xc6, 0xea, 0x5f, 0xff], patch: &[0xb8, 0x01, 0x00, 0x00, 0x00], optional: false },
    PatchPoint { id: "nxservice_serialize_expiry_2099_12_31", rva: 0xA06410, orig: &[0x48, 0x8b, 0x8d, 0x78, 0x03, 0x00, 0x00], patch: &[0xb9, 0x7f, 0xe6, 0x85, 0xf4, 0x90, 0x90], optional: false },
    PatchPoint { id: "nxservice_serialize_member_status_enabled", rva: 0xA06512, orig: &[0x8b, 0x8d, 0x84, 0x03, 0x00, 0x00], patch: &[0xb9, 0x01, 0x00, 0x00, 0x00, 0x90], optional: false },
    PatchPoint { id: "nxservice_serialize_device_member_enabled", rva: 0xA066DD, orig: &[0x8b, 0x8d, 0x88, 0x03, 0x00, 0x00], patch: &[0xb9, 0x01, 0x00, 0x00, 0x00, 0x90], optional: false },
    PatchPoint { id: "nxservice_serialize_member_type_vip", rva: 0xA0688E, orig: &[0x8b, 0x8d, 0xb0, 0x03, 0x00, 0x00], patch: &[0xb9, 0x01, 0x00, 0x00, 0x00, 0x90], optional: false },
    PatchPoint { id: "nxservice_serialize_trial_status_used", rva: 0xA0696D, orig: &[0x8b, 0x8d, 0xb4, 0x03, 0x00, 0x00], patch: &[0xb9, 0x02, 0x00, 0x00, 0x00, 0x90], optional: false },
    PatchPoint { id: "nxservice_serialize_is_valid_infos_true", rva: 0xA06E6B, orig: &[0x0f, 0xb6, 0x8d, 0x32, 0x04, 0x00, 0x00], patch: &[0xb1, 0x01, 0x90, 0x90, 0x90, 0x90, 0x90], optional: false },
    PatchPoint { id: "nxservice_disable_cloud_member_trial_endpoint", rva: 0x10B7D38, orig: &[0x76, 0x31, 0x2f, 0x6d, 0x65, 0x6d, 0x62, 0x65, 0x72, 0x2f, 0x74, 0x72, 0x69, 0x61, 0x6c], patch: &[0x76, 0x31, 0x2f, 0x6d, 0x65, 0x6d, 0x62, 0x65, 0x72, 0x2f, 0x6c, 0x6f, 0x63, 0x61, 0x6c], optional: false },
];

static POINTS_REMOTE: &[PatchPoint] = &[
    PatchPoint { id: "nxremote_force_remote_enable_flag_false", rva: 0x1AFD47, orig: &[0x41, 0x0f, 0x95, 0xc7], patch: &[0x45, 0x31, 0xff, 0x90], optional: false },
    PatchPoint { id: "nxremote_is_current_session_remote_session_false", rva: 0x17E5B0, orig: &[0x48, 0x83, 0xec, 0x58], patch: &[0x33, 0xc0, 0xc3, 0x90], optional: true },
    PatchPoint { id: "nxremote_skip_healthd_launch", rva: 0xD26E0, orig: &[0x48, 0x89, 0x5c, 0x24, 0x10], patch: &[0xc3, 0x90, 0x90, 0x90, 0x90], optional: false },
    PatchPoint { id: "nxremote_skip_backend_launch", rva: 0xD3340, orig: &[0x48, 0x89, 0x5c, 0x24, 0x10], patch: &[0xc3, 0x90, 0x90, 0x90, 0x90], optional: false },
];


static HOSTS: &[(&str, &[PatchPoint])] = &[
    ("项目BNxMain.exe", POINTS_MAIN),
    ("项目BNxService.exe", POINTS_SERVICE),
    ("项目BRemoteService.exe", POINTS_REMOTE),
];

static mut LOG_PATH: [u8; 1024] = [0; 1024];

fn log(msg: &str) {
    let (path, plen) = unsafe {
        let p = std::ptr::addr_of!(LOG_PATH) as *const u8;
        let mut end = 0usize;
        while end < 1024 && *p.add(end) != 0 {
            end += 1;
        }
        (p, end)
    };
    if plen == 0 {
        return;
    }
    let path = unsafe { std::str::from_utf8(std::slice::from_raw_parts(path, plen)).unwrap_or("") };
    let mut st = SystemTime {
        wYear: 0,
        wMonth: 0,
        wDayOfWeek: 0,
        wDay: 0,
        wHour: 0,
        wMinute: 0,
        wSecond: 0,
        wMilliseconds: 0,
    };
    unsafe { GetLocalTime(&mut st) };
    if let Ok(mut f) = std::fs::OpenOptions::new().create(true).append(true).open(path) {
        let _ = writeln!(
            f,
            "[{:04}-{:02}-{:02} {:02}:{:02}:{:02}.{:03}] {}",
            st.wYear, st.wMonth, st.wDay, st.wHour, st.wMinute, st.wSecond, st.wMilliseconds, msg
        );
    }
}

fn hexs(b: &[u8]) -> String {
    b.iter().take(32).map(|x| format!("{:02x}", x)).collect::<Vec<_>>().join("")
}

fn init_log_path(selfmod: HMODULE) {
    unsafe {
        let mut buf = [0u8; 1024];
        let n = GetModuleFileNameA(selfmod, buf.as_mut_ptr(), 1024);
        if n == 0 {
            return;
        }
        let n = n as usize;
        let mut cut = n;
        let mut i = 0;
        while i < n {
            if buf[i] == b'\\' || buf[i] == b'/' {
                cut = i + 1;
            }
            i += 1;
        }
        let fname = b"项目B_guard_winhttp.log";
        let p = std::ptr::addr_of_mut!(LOG_PATH) as *mut u8;
        let mut k = 0usize;
        while k < cut && k < 1023 {
            *p.add(k) = buf[k];
            k += 1;
        }
        let mut j = 0usize;
        while j < fname.len() && k < 1023 {
            *p.add(k) = fname[j];
            k += 1;
            j += 1;
        }
        *p.add(k) = 0;
    }
}

unsafe fn rva_in_module(host: HMODULE, rva: u32, len: usize) -> bool {
    let dos = host as *const u8;
    if dos.is_null() || *dos != b'M' || *dos.add(1) != b'Z' {
        return false;
    }
    let e_lfanew = *(dos.add(0x3c) as *const u32) as usize;
    if e_lfanew == 0 || e_lfanew > 0x1000 {
        return false;
    }
    let nt = dos.add(e_lfanew);
    if *(nt as *const u32) != 0x0000_4550 {
        return false;
    }
    let nsec = *(nt.add(6) as *const u16) as usize;
    let optsz = *(nt.add(20) as *const u16) as usize;
    let secs = nt.add(24 + optsz);
    let lo = rva as usize;
    let hi = lo + len;
    for i in 0..nsec {
        let s = secs.add(i * 40);
        let vsize = *(s.add(8) as *const u32) as usize;
        let vaddr = *(s.add(12) as *const u32) as usize;
        let rawsize = *(s.add(16) as *const u32) as usize;
        let vs = if vsize > rawsize { vsize } else { rawsize };
        if lo >= vaddr && hi <= vaddr + vs {
            return true;
        }
    }
    false
}

fn apply(host: HMODULE, p: &PatchPoint) -> u8 {
    unsafe {
        if p.optional {
            let key = b"GUARD_DISABLE_OPTIONAL\0";
            let mut vb = [0u8; 8];
            let n = GetEnvironmentVariableA(key.as_ptr(), vb.as_mut_ptr(), 8);
            if n > 0 && vb[0] == b'1' {
                log(&format!("[SKIPPED ] {:<46} (optional, disabled by env)", p.id));
                return 0;
            }
        }
        if !rva_in_module(host, p.rva, p.orig.len()) {
            log(&format!(
                "[OUTOFRANGE] {:<46} rva=0x{:08X} 不在宿主模块任何节区内 -> SKIP",
                p.id, p.rva
            ));
            return 3;
        }
        let addr: *mut u8 = host.add(p.rva as usize);
        let cur = std::slice::from_raw_parts(addr, p.orig.len());
        if cur == p.patch {
            log(&format!("[ALREADY ] {:<46} rva=0x{:08X}", p.id, p.rva));
            return 2;
        }
        if cur != p.orig {
            log(&format!(
                "[MISMATCH] {:<46} rva=0x{:08X} got={} -> SKIP",
                p.id,
                p.rva,
                hexs(cur)
            ));
            return 3;
        }
        let mut old = 0u32;
        if VirtualProtect(addr, p.orig.len(), PAGE_EXECUTE_READWRITE, &mut old) == 0 {
            log(&format!("[FAILED  ] {:<46} VirtualProtect err={}", p.id, GetLastError()));
            return 3;
        }
        std::ptr::copy_nonoverlapping(p.patch.as_ptr(), addr, p.patch.len());
        FlushInstructionCache(GetCurrentProcess(), addr, p.orig.len());
        VirtualProtect(addr, p.orig.len(), old, &mut old);
        log(&format!(
            "[APPLIED ] {:<46} rva=0x{:08X}  {}/{} bytes",
            p.id,
            p.rva,
            p.patch.len(),
            p.orig.len()
        ));
        1
    }
}

extern "system" fn worker(_param: *mut u8) -> u32 {
    let mut host: HMODULE = std::ptr::null_mut();
    let mut exe = String::new();
    let mut matched: Option<&'static [PatchPoint]> = None;

    log("=== 项目B Universal Guard (winhttp.dll single-DLL) start ===");

    for _ in 0..80 {
        host = unsafe { GetModuleHandleA(std::ptr::null()) };
        if !host.is_null() {
            let mut buf = [0u8; 260];
            let n = unsafe { GetModuleFileNameA(host, buf.as_mut_ptr(), 260) };
            if n > 0 {
                let s = &buf[..n as usize];
                let base = match s.iter().rposition(|&c| c == b'\\' || c == b'/') {
                    Some(i) => &s[i + 1..],
                    None => s,
                };
                exe = String::from_utf8_lossy(base).to_string();
                for h in HOSTS {
                    if h.0.eq_ignore_ascii_case(&exe) {
                        matched = Some(h.1);
                        break;
                    }
                }
            }
        }
        if matched.is_some() {
            break;
        }
        if !exe.is_empty() {
            break;
        }
        unsafe { Sleep(250) };
    }

    if exe.eq_ignore_ascii_case("项目BNxUpdater.exe") {
        log(&format!("[BLOCKED ] host '{}' detected -> auto-aborting update process to prevent overwrite!", exe));
        unsafe { ExitProcess(0); }
    }

    let pts = match matched {
        Some(p) => p,
        None => {
            log(&format!(
                "[SKIPPED ] host '{}' not covered by this proxy -> no modification",
                exe
            ));
            return 0;
        }
    };

    log(&format!("[+] host={} base={:p} points={}", exe, host, pts.len()));
    let (mut applied, mut already, mut mism, mut skipped) = (0u32, 0u32, 0u32, 0u32);
    for p in pts {
        match apply(host, p) {
            1 => applied += 1,
            2 => already += 1,
            3 => mism += 1,
            _ => skipped += 1,
        }
    }
    log(&format!(
        "=== summary: applied={} already={} mismatch={} skipped={} total={} ===",
        applied,
        already,
        mism,
        skipped,
        pts.len()
    ));
    0
}

#[no_mangle]
pub extern "system" fn DllMain(hinst: HMODULE, reason: u32, _reserved: *mut u8) -> i32 {
    if reason == 1 {
        unsafe { init_real_winhttp(); }
        init_log_path(hinst);
        log("---- DllMain attach (winhttp.dll) ----");
        unsafe {
            CreateThread(
                std::ptr::null_mut(),
                0,
                Some(worker),
                std::ptr::null_mut(),
                0,
                std::ptr::null_mut(),
            );
        }
    }
    1
}
