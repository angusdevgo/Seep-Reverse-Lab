// ===========================================================================
//  项目B 本地化守护 —— 代理 DLL 运行时（Rust 模板，由 work/gen_proxy.py 展开）
//
//  行为：
//    ① DllMain 启动看门狗线程，按「宿主主模块基址 + RVA」写入点位
//    ② 写入前逐字节核对「原始字节」；不匹配 -> 跳过并记 MISMATCH（禁止盲写）
//    ③ 日志四态：APPLIED / ALREADY / MISMATCH / SKIPPED
//    ④ 宿主不在覆盖范围内 -> 不做任何修改
// ===========================================================================
#![allow(non_snake_case, non_upper_case_globals, static_mut_refs)]
use std::io::Write;

type HMODULE = *mut u8;

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
}

struct PatchPoint {
    id: &'static str,
    rva: u32,
    orig: &'static [u8],
    patch: &'static [u8],
    optional: bool,
}

// ------------------------------ 点位表 ------------------------------
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
    ("项目BRemoteService.exe", POINTS_REMOTE),

];

// ------------------------------ 日志 ------------------------------
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
        // 截断到最后一个反斜杠之后
        let mut cut = n;
        let mut i = 0;
        while i < n {
            if buf[i] == b'\\' || buf[i] == b'/' {
                cut = i + 1;
            }
            i += 1;
        }
        let fname = b"项目B_guard_version.log";
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

// ------------------------------ 打补丁 ------------------------------
/// 校验 RVA 是否落在宿主模块的某个节区虚拟范围内。
/// 这一步至关重要：宿主与点位表不匹配时（例如被错误地注入到其它进程），
/// 直接读取越界地址会触发访问违例并杀死目标进程。
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

/// 返回：1=APPLIED 2=ALREADY 3=MISMATCH/FAILED 0=SKIPPED
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

    log("=== 项目B Local Guard (version.dll) start, real=version_orig.dll ===");

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
            // 主模块名已可读但不在覆盖表内 —— 判定已终局，无需继续重试
            break;
        }
        unsafe { Sleep(250) };
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
        init_log_path(hinst);
        log("---- DllMain attach (version.dll) ----");
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
