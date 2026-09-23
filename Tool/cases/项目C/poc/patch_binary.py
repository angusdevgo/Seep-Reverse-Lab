#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
项目C 客户端离线鉴权脆弱性走查 —— 静态修补工具 (CWE-602)
支持直接给任意路径下的 项目C.x64.exe 或 项目C.exe 打补丁。
"""

import argparse
import os
import shutil
import struct
import sys

# 补丁点定义: (RVA, 期望原始字节, 补丁字节, 描述)
PATCH_SITES = [
    # 1. 未注册默认回退分支 (STD -> ENT) - 核心!
    (0x1317F5,
     bytes.fromhex("c7 86 20 01 00 00 98 00 00 00"),
     bytes.fromhex("c7 86 20 01 00 00 20 1b 00 00"),
     "sub_1401316C0 STD回退分支: 98h (152/STD) -> 1B20h (6944/Enterprise)"),

    # 2. PRO 分支 -> ENT
    (0x13176D,
     bytes.fromhex("c7 86 20 01 00 00 d4 03 00 00"),
     bytes.fromhex("c7 86 20 01 00 00 20 1b 00 00"),
     "sub_1401316C0 PRO分支: 3D4h (980/PRO) -> 1B20h (6944/Enterprise)"),

    # 3. 黑名单核验直通
    (0x1347E0,
     bytes.fromhex("4c 8b dc"),
     bytes.fromhex("31 c0 c3"),
     "sub_1401347E0 服务端黑名单直通 (xor eax, eax; ret)"),
]

def rva_to_offset(data, rva):
    e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
    num_sections = struct.unpack_from("<H", data, e_lfanew + 6)[0]
    opt_hdr_size = struct.unpack_from("<H", data, e_lfanew + 20)[0]
    sec_table = e_lfanew + 24 + opt_hdr_size
    for i in range(num_sections):
        sec_off = sec_table + i * 40
        name = data[sec_off:sec_off + 8].rstrip(b"\0").decode("latin-1")
        vsize, vaddr, raw_size, raw_ptr = struct.unpack_from("<IIII", data, sec_off + 8)
        if vaddr <= rva < vaddr + max(vsize, raw_size):
            return raw_ptr + (rva - vaddr), name
    return None, None

def apply_patch(exe_path, restore=False, check_only=False):
    if not os.path.exists(exe_path):
        print(f"[-] 目标文件不存在: {exe_path}")
        return 1

    bak_path = exe_path + ".bak"
    if restore:
        if not os.path.exists(bak_path):
            print(f"[-] 备份文件不存在: {bak_path}")
            return 1
        shutil.copy2(bak_path, exe_path)
        print(f"[+] 已恢复原版: {exe_path}")
        return 0

    with open(exe_path, "rb") as f:
        data = bytearray(f.read())

    print(f"[*] 正在分析: {exe_path}")
    plan = []
    for rva, expect, repl, desc in PATCH_SITES:
        off, sec = rva_to_offset(data, rva)
        if off is None:
            print(f"[-] RVA 0x{rva:X} 无法映射!")
            return 1
        cur = bytes(data[off:off + len(expect)])
        if cur == repl:
            print(f"    [=] 0x{rva:X} ({sec}) 已处于修补后状态")
        elif cur == expect:
            print(f"    [+] 0x{rva:X} ({sec}) 特征码匹配: {desc}")
            plan.append((off, repl))
        else:
            print(f"[-] 0x{rva:X} ({sec}) 特征码不匹配! 期望 {expect.hex(' ')}, 实际 {cur.hex(' ')}")
            return 1

    if check_only:
        print("[+] 预检完成，特征码 100% 匹配。")
        return 0

    if not plan:
        print("[*] 目标已完全修补，无需再次写入。")
        return 0

    if not os.path.exists(bak_path):
        shutil.copy2(exe_path, bak_path)
        print(f"[+] 已自动创建备份: {bak_path}")

    for off, repl in plan:
        data[off:off + len(repl)] = repl

    with open(exe_path, "wb") as f:
        f.write(data)

    print(f"[+] 修补完成! 共写入 {len(plan)} 处指令补丁。")
    return 0

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target", nargs="?", default=r"..\runtime\项目C.x64.exe",
                    help="目标可执行文件路径 (默认 ..\\runtime\\项目C.x64.exe)")
    ap.add_argument("--restore", action="store_true", help="恢复原版")
    ap.add_argument("--check", action="store_true", help="仅校验特征码")
    args = ap.parse_args()
    return apply_patch(args.target, restore=args.restore, check_only=args.check)

if __name__ == "__main__":
    sys.exit(main())
