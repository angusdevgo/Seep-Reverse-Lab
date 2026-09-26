// ============================================================================
//  XYplorer 授权状态本地伪造 PoC —— version.dll (DLL 搜索顺序劫持载体)
//  ---------------------------------------------------------------------------
//  用途：白盒审计复现件。放入 XYplorer.exe 同目录后，进程启动即加载本 DLL，
//        在后台线程把授权状态全局变量改写为 Lifetime License(5)，
//        并用宿主自身的 SysAllocString 写入伪造许可证名/码。
//
//  依据：XYplorer 授权判定完全依赖进程内可写全局变量（CWE-602），
//        无服务端校验、无签名回执、无一致性自校验。
//
//  构建： rustc --edition 2021 --crate-type cdylib -O -C strip=symbols \
//                -C panic=abort -o version.dll lib.rs
// ============================================================================
#![allow(non_snake_case, non_camel_case_types, non_upper_case_globals)]

use core::ffi::c_void;
use std::fs::OpenOptions;
use std::io::Write;
use std::thread;
use std::time::Duration;

type Hmod = *mut c_void;

extern "system" {
    fn GetModuleHandleW(name: *const u16) -> Hmod;
    fn LoadLibraryExW(name: *const u16, file: *mut c_void, flags: u32) -> Hmod;
    fn GetProcAddress(h: Hmod, name: *const u8) -> *mut c_void;
    fn GetModuleFileNameW(h: Hmod, buf: *mut u16, size: u32) -> u32;
    fn CreateThread(attr: *mut c_void, size: usize,
                    start: unsafe extern "system" fn(*mut c_void) -> u32,
                    param: *mut c_void, flags: u32, tid: *mut u32) -> *mut c_void;
}

const LOAD_LIBRARY_SEARCH_SYSTEM32: u32 = 0x0000_0800;

// ---------------------------------------------------------------------------
// 版本映射表：SizeOfImage 用于识别版本，其余为目标全局变量的 RVA
// ---------------------------------------------------------------------------
struct Map {
    size_of_image: u32,
    lic: usize,   // license_type        0=未注册 / 1..5 = xy01..xy05 代次 (5=Lifetime)
    flag: usize,  // 版本覆盖标志         1=覆盖本版本
    name: usize,  // 许可证名 WideString 全局
    code1: usize, // 许可证码 WideString 全局 #1
    code2: usize, // 许可证码 WideString 全局 #2
    sysalloc: usize, // OLEAUT32!SysAllocString 的 IAT 槽位
}

static MAPS: [Map; 2] = [
    // XYplorer 28.40.0100
    Map { size_of_image: 0x0285_0000, lic: 0x22FD724, flag: 0x230170C,
          name: 0x2235A88, code1: 0x2281C70, code2: 0x21FDDE0,
          sysalloc: 0x2675408 },
    // XYplorer 28.30.2600
    Map { size_of_image: 0x0283_B000, lic: 0x22E4D5C, flag: 0x22E8D44,
          name: 0x221CEF8, code1: 0x22694A0, code2: 0x21E52F0,
          sysalloc: 0x265E408 },
];

const FAKE_NAME: &str = "seep";
const FAKE_CODE: &str = "xy05-Lifetime-License-Pro-seep-poc";

// ---------------------------------------------------------------------------
// 工具
// ---------------------------------------------------------------------------
unsafe fn read_u32(p: usize) -> u32 { core::ptr::read_unaligned(p as *const u32) }
unsafe fn write_u32(p: usize, v: u32) { core::ptr::write_unaligned(p as *mut u32, v) }
unsafe fn read_u64(p: usize) -> u64 { core::ptr::read_unaligned(p as *const u64) }

fn wide(s: &str) -> Vec<u16> {
    s.encode_utf16().chain(core::iter::once(0)).collect()
}

fn log_path() -> Option<std::path::PathBuf> {
    unsafe {
        let mut buf = vec![0u16; 1024];
        let n = GetModuleFileNameW(core::ptr::null_mut(), buf.as_mut_ptr(), 1024);
        if n == 0 { return None; }
        let s = String::from_utf16_lossy(&buf[..n as usize]);
        let mut p = std::path::PathBuf::from(s);
        p.set_file_name("version_poc.log");
        Some(p)
    }
}

fn log(msg: &str) {
    if let Some(p) = log_path() {
        if let Ok(mut f) = OpenOptions::new().create(true).append(true).open(p) {
            let _ = writeln!(f, "{}", msg);
        }
    }
}

// ---------------------------------------------------------------------------
// 核心：定位并改写授权状态
// ---------------------------------------------------------------------------
unsafe fn pick_map(base: usize) -> Option<&'static Map> {
    let e_lfanew = read_u32(base + 0x3C) as usize;
    if e_lfanew < 0x40 || e_lfanew > 0x1000 { return None; }
    let size_of_image = read_u32(base + e_lfanew + 0x50);
    for m in MAPS.iter() {
        if m.size_of_image == size_of_image {
            return Some(m);
        }
    }
    // 兜底：用 license_type 取值合理性判定
    for m in MAPS.iter() {
        let v = read_u32(base + m.lic);
        if v <= 5 { return Some(m); }
    }
    None
}

unsafe fn patch() -> bool {
    let base = GetModuleHandleW(core::ptr::null()) as usize;   // 宿主主模块 = XYplorer.exe
    if base == 0 { return false; }
    let m = match pick_map(base) { Some(m) => m, None => return false };

    let mut changed = false;

    // 1) license_type -> 5 (Lifetime License)
    if read_u32(base + m.lic) != 5 {
        write_u32(base + m.lic, 5);
        changed = true;
    }
    // 2) 版本覆盖标志 -> 1 (许可证覆盖当前版本)
    if read_u32(base + m.flag) != 1 {
        write_u32(base + m.flag, 1);
        changed = true;
    }

    // 3) [可选] 借用宿主自带的 SysAllocString 写入伪造许可证名/码
    //    默认关闭: 宿主按自有字符串管理器释放该 BSTR 会导致堆损坏 (0xC0000374)
    //    启用方式: 在 DLL 同目录创建空文件 version_poc_strings.enable
    let enable_strings = std::path::Path::new("version_poc_strings.enable").exists()
        || log_path().map(|p| p.with_file_name("version_poc_strings.enable").exists()).unwrap_or(false);
    if !enable_strings {
        return changed;
    }
    let sysalloc = read_u64(base + m.sysalloc) as usize;
    if sysalloc > 0x10000 && sysalloc < 0x0000_7FFF_FFFF_FFFF {
        let f: unsafe extern "system" fn(*const u16) -> *mut c_void =
            core::mem::transmute(sysalloc);
        let name = wide(FAKE_NAME);
        let code = wide(FAKE_CODE);
        let n = f(name.as_ptr()) as usize;
        let c = f(code.as_ptr()) as usize;
        if n > 0x10000 {
            if read_u64(base + m.name) != n as u64 { core::ptr::write_unaligned((base + m.name) as *mut u64, n as u64); changed = true; }
        }
        if c > 0x10000 {
            if read_u64(base + m.code1) != c as u64 { core::ptr::write_unaligned((base + m.code1) as *mut u64, c as u64); changed = true; }
            if read_u64(base + m.code2) != c as u64 { core::ptr::write_unaligned((base + m.code2) as *mut u64, c as u64); changed = true; }
        }
    }
    changed
}

// ---------------------------------------------------------------------------
// 后台线程：等待宿主初始化后持续维持授权状态（仅在值不一致时写入）
// ---------------------------------------------------------------------------
unsafe extern "system" fn worker(_param: *mut c_void) -> u32 {
    let mut reported = false;
    for i in 0..2400 {                      // ~20 分钟
        if patch() && !reported {
            reported = true;
            let base = GetModuleHandleW(core::ptr::null()) as usize;
            let lic = pick_map(base).map(|m| read_u32(base + m.lic)).unwrap_or(0);
            log(&format!("[+] license state forged: license_type={} name='{}' code='{}'",
                         lic, FAKE_NAME, FAKE_CODE));
        }
        // 启动前 8 秒高频抢占 (每 50ms), 赶在宿主计算标题/授权标签之前落地
        let d = if i < 160 { 50 } else { 500 };
        thread::sleep(Duration::from_millis(d));
    }
    0
}

// ---------------------------------------------------------------------------
// 入口
// ---------------------------------------------------------------------------
#[no_mangle]
pub unsafe extern "system" fn DllMain(_hinst: Hmod, reason: u32, _res: *mut c_void) -> i32 {
    if reason == 1 {                        // DLL_PROCESS_ATTACH
        let mut tid: u32 = 0;
        CreateThread(core::ptr::null_mut(), 0, worker, core::ptr::null_mut(), 0, &mut tid);
    }
    1
}

// ---------------------------------------------------------------------------
// version.dll 导出转发（保证宿主原有功能不受影响）
// ---------------------------------------------------------------------------
static mut REAL: Hmod = core::ptr::null_mut();

unsafe fn real() -> Hmod {
    if REAL.is_null() {
        let sys: Vec<u16> = "C:\\Windows\\System32\\version.dll\0".encode_utf16().collect();
        REAL = LoadLibraryExW(sys.as_ptr(), core::ptr::null_mut(), LOAD_LIBRARY_SEARCH_SYSTEM32);
    }
    REAL
}

macro_rules! fwd {
    ($name:ident, $($arg:ident : $ty:ty),*) => {
        #[no_mangle]
        pub unsafe extern "system" fn $name($($arg: $ty),*) -> isize {
            let h = real();
            let f = GetProcAddress(h, concat!(stringify!($name), "\0").as_ptr());
            if f.is_null() { return 0; }
            let fp: unsafe extern "system" fn($($ty),*) -> isize = core::mem::transmute(f);
            fp($($arg),*)
        }
    };
}

fwd!(GetFileVersionInfoA, a: *const u8, b: u32, c: u32, d: *mut c_void);
fwd!(GetFileVersionInfoW, a: *const u16, b: u32, c: u32, d: *mut c_void);
fwd!(GetFileVersionInfoByHandle, a: u32, b: *mut c_void, c: u32, d: *mut c_void);
fwd!(GetFileVersionInfoExA, a: u32, b: *const u8, c: u32, d: u32, e: *mut c_void);
fwd!(GetFileVersionInfoExW, a: u32, b: *const u16, c: u32, d: u32, e: *mut c_void);
fwd!(GetFileVersionInfoSizeA, a: *const u8, b: *mut u32);
fwd!(GetFileVersionInfoSizeW, a: *const u16, b: *mut u32);
fwd!(GetFileVersionInfoSizeExA, a: u32, b: *const u8, c: *mut u32);
fwd!(GetFileVersionInfoSizeExW, a: u32, b: *const u16, c: *mut u32);
fwd!(VerFindFileA, a: u32, b: *const u8, c: *const u8, d: *const u8, e: *mut u8, f: *mut u32, g: *mut u8, h: *mut u32);
fwd!(VerFindFileW, a: u32, b: *const u16, c: *const u16, d: *const u16, e: *mut u16, f: *mut u32, g: *mut u16, h: *mut u32);
fwd!(VerInstallFileA, a: u32, b: *const u8, c: *const u8, d: *const u8, e: *const u8, f: *mut u8, g: *mut u32);
fwd!(VerInstallFileW, a: u32, b: *const u16, c: *const u16, d: *const u16, e: *const u16, f: *mut u16, g: *mut u32);
fwd!(VerLanguageNameA, a: u32, b: *mut u8, c: u32);
fwd!(VerLanguageNameW, a: u32, b: *mut u16, c: u32);
fwd!(VerQueryValueA, a: *const c_void, b: *const u8, c: *mut *mut c_void, d: *mut u32);
fwd!(VerQueryValueW, a: *const c_void, b: *const u16, c: *mut *mut c_void, d: *mut u32);
