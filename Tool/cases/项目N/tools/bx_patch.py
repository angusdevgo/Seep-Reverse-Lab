#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
================================================================================
 项目N v2.2.4.3 —— 客户端授权旁路 / 本地特权状态离线化  复现补丁工具
 (CWE-602 / CWE-287 / CWE-863 受权白盒审计用)
================================================================================

 用途
 ----
 对官方原版 项目N.exe 施加最小化二进制补丁，生成"漏洞版"样本，用于向厂商
 证明：**核心付费权益（PRO）的判定完全落在客户端本地，且可被离线篡改**。

 本工具只做三件事（每件都可单独关闭）：
   P1  4 处「设置项 PRO 标记」：把"该项为 PRO 专属"改成"非 PRO 专属"
   P2  isPro 主开关：把授权态查询方法改为恒返回 true
   P3  授权装载判定：把"必须联网校验"改成"直接判定校验通过"

 前置条件
 --------
   - 目标为官方原版 项目N.exe v2.2.4.3
     SHA-256 = d21ff11ac4f9077b53a22545a510d302ca371f12bc5ff8dd85c8e7d8198d6dc4
   - Python 3.8+，无需第三方库

 用法
 ----
   python bx_patch.py <原版.exe> <输出.exe> --profile <flags|pro|max> [--no-uac]

   例：
     # 变体 A：仅解除 4 处 PRO 标记（对照组）
     python bx_patch.py samples/项目N.exe out/BX_A_probflags.exe --profile flags

     # 变体 B：4 处 PRO 标记 + isPro 主开关（推荐日常验证）
     python bx_patch.py samples/项目N.exe out/项目N.pro-localized.exe --profile pro

     # 变体 C：在 B 基础上再解除授权联网校验（完整旁路，含副作用）
     python bx_patch.py samples/项目N.exe out/项目N.pro-localized-max.exe --profile max

================================================================================
 漏洞原理（为什么补丁有效）
================================================================================

 1) 保护层：Eazfuscator.NET 的「程序集代码加密」
    ------------------------------
    目标 PE 中名为随机字节的节区被整体 XOR 加密；解密 keystream 由**其它节区的
    内容哈希**演化而来（即反篡改：改动别的节区会导致本区解不开）。

      识别目标节区：  节名前 8 字节 = 两个 uint32，其乘积 == 0x654B1E94
      种子初值：      num5..num8 = 1758353659, 186699061, 1283470176, 872273121
      内容哈希演化：  nv = (num5 ^ v) + num6 + (num7 * num8)   (逐 dword)
      16 项 keystream： 由 num5..num8 滚动生成，再按 i%3 做 xor/mul/add
      逐 dword 解密：  plain = cipher ^ ks[i & 15]
                       ks[i & 15] = (ks[i & 15] ^ plain) + 1204611781
      —— 注意 keystream 以**明文**推进，因此加密方向与解密方向可用同一函数
         （加密时写 cipher，推进仍用 plain），这使得"解密→改字节→再加密"可
         产出除补丁点外与原文件逐字节一致的输出。

    本工具完整复现了该算法（见 decrypt/encrypt_section），因此可以在**明文 IL 层**
    精确改写方法体，然后再加密回写。

 2) 漏洞点 P1 —— 设置项 PRO 标记（RVA 0x1614FC / 0x16154E / 0x1619B3 / 0x161D2D）
    ------------------------------------------------
    构造设置项列表时，客户端用如下 IL 给每一项打 PRO 标记：

        17            ldc.i4.1                       ; true = "需要 PRO"
        6f 5a 1f 00 06  call  #=z0PznKj__p67r(bool)  ; 写入该项的 PRO 标记

    把 `17`(ldc.i4.1) 改为 `16`(ldc.i4.0)，该项即不再被标记为 PRO 专属。
    全程序共 26 个设置项，其中**仅 4 项**被标记为 PRO：
        ShowExperimentalTweaks（显示实验性功能）
        TweakerMode          （调优模式）
        InstantTweaksApply   （即时应用）
        SetPinCode           （家长控制 PIN）
    这 4 处即官方在客户端声明的全部 PRO 权益闸门。

 3) 漏洞点 P2 —— isPro 主开关（RVA 0x187AC）
    ----------------------------------------
    授权态查询方法 `#=zC5CFc9DaCi4VOg1wyMhZz10LAKkgEiwY1Q==.#=zAB60eigenToO()`
    的原始方法体：

        82                    tiny 方法头：0x82>>2 = 32 字节 IL
        28 85 49 00 06        call  <VM 单例 getter>
        28 83 49 00 06        call  <VM 字节码流 getter>
        72 8d 13 00 70        ldstr "0-MMa,UFel"          ; 虚拟化方法名（含偏移编码）
        14                    ldnull
        28 1f 07 00 06        call  <VM 派发器>            ; 结果由 VM 字节码决定
        79 c9 03 00 01        castclass bool
        71 c9 03 00 01        ldobj  bool
        2a                    ret
                              (合计 1 + 32 = 33 字节)

    改写为：

        0a                    tiny 方法头：0x0a>>2 = 2 字节 IL
        17 2a                 ldc.i4.1 ; ret               ; 恒返回 true
                              (合计 1 + 2 = 3 字节，等长覆盖头部)

    ★ 关键细节：第一个字节是 **.NET tiny 方法头**，不是操作码。
      改成 `17 2a 00`（0x17 低 2 位 = 0b11 → 被解析为 fat 头）会直接触发
      BadImageFormatException("IL 范围不正确")。必须用 `0a` 作为头。

    该方法在全程序有 8 处托管调用点，覆盖：
      激活页"已激活"显示、优化流程 PRO 任务跳过、调整项可编辑性(IsEditable && isPro)、
      设置列表构建、若干页面级功能闸门。

 4) 漏洞点 P3 —— 授权装载判定（RVA 0x8D323）
    ----------------------------------------
    启动期授权装载状态机中的唯一判定：

        28 de 4f 00 06   call  #=z1Fm3KmzxJzbI(string)   ; "密钥是否为空/无效"
        2d 6f            brtrue.s +0x6f                  ; 非空 → 跳过联网校验

    改写为：

        26               pop            ; 丢弃原参数
        17               ldc.i4.1       ; 恒真
        00 00 00         nop ×3         ; 占位，保持 5 字节等长
        2d 6f            brtrue.s +0x6f ; 恒跳转

    → 任意密钥都直接走"校验通过"分支，**不再向服务端发起任何请求**。
    ★ 注意：此补丁**不影响** `#=z1Fm3KmzxJzbI` 本身（它在全程序另有 100+ 处调用，
      语义是"字符串是否为空"），因此不会破坏 EULA/设置存储等其它逻辑。

 5) 漏洞本质（对应 CWE）
    ----------------------------------------
    CWE-602  Client-Side Enforcement of Server-Side Security
             —— 付费权益（PRO）的"是否解锁"完全由客户端本地布尔量决定。
    CWE-287  Improper Authentication
             —— 授权校验存在"空密钥即视为通过"的旁路分支。
    CWE-863  Incorrect Authorization
             —— 本地特权状态可直接由用户可写注册表 / 二进制补丁改写。

    加固要点（详见交付报告 §6）：
       a. 服务端权威：核心权益必须以服务端签名的权益凭证为准，客户端不得自证；
       b. 授权凭证本地二次校验（非对称签名 + 硬件指纹绑定 + 时效 nonce）；
       c. 敏感判定下沉 Native 并做代码虚拟化 / 完整性自校验（含签名自检）；
       d. 关键分支消除"本地布尔量"形态，改为"必须持有有效凭证才能解密所需资源"。

================================================================================
"""

import argparse
import hashlib
import os
import struct
import sys

# 保证在 GBK 控制台下也能输出 UTF-8 符号
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

# ----------------------------------------------------------------------------
# 常量：Eazfuscator 代码加密参数（逆向所得）
# ----------------------------------------------------------------------------
SECTION_MAGIC = 0x65452714          # 目标节区识别：节名前 8 字节两个 u32 的乘积
                                    # (实测值；本样本目标节区为 idx0, VA=0x2000)
SEED_INIT = (1758353659, 186699061, 1283470176, 872273121)
KEYSTREAM_FEEDBACK = 1204611781     # keystream 自反馈常数
EXPECTED_SHA256 = 'd21ff11ac4f9077b53a22545a510d302ca371f12bc5ff8dd85c8e7d8198d6dc4'

# ----------------------------------------------------------------------------
# 补丁表： (RVA, 原始字节, 补丁字节, 说明)
#   RVA 为相对虚拟地址（相对于 PE ImageBase 的节内偏移 + 节 VA）
# ----------------------------------------------------------------------------
P_FLAGS = [
    (0x1614FC, b'\x17', b'\x16', 'PRO 标记①  ShowExperimentalTweaks  (显示实验性功能)'),
    (0x16154E, b'\x17', b'\x16', 'PRO 标记②  TweakerMode           (调优模式)'),
    (0x1619B3, b'\x17', b'\x16', 'PRO 标记③  InstantTweaksApply    (即时应用)'),
    (0x161D2D, b'\x17', b'\x16', 'PRO 标记④  SetPinCode           (家长控制 PIN)'),
]

P_ISPRO = [
    (0x187AC, b'\x82\x28\x85', b'\x0a\x17\x2a',
     'isPro 主开关：tiny头(32B IL) -> tiny头(2B IL: ldc.i4.1; ret)'),
]

P_AUTH = [
    (0x8D323, b'\x28\xde\x4f\x00\x06', b'\x26\x17\x00\x00\x00',
     '授权装载判定：call 空值检查 -> pop; ldc.i4.1; nop×3 (恒"校验通过")'),
]

PROFILES = {
    'flags': ('变体 A —— 仅解除 4 处 PRO 标记（对照组）', P_FLAGS),
    'pro':   ('变体 B —— 4 处 PRO 标记 + isPro 主开关（推荐）', P_FLAGS + P_ISPRO),
    'max':   ('变体 C —— 变体 B + 授权联网校验旁路（完整，含副作用）',
              P_FLAGS + P_ISPRO + P_AUTH),
}


# ----------------------------------------------------------------------------
# PE / 加密节区处理
# ----------------------------------------------------------------------------
def u32(x):
    return x & 0xFFFFFFFF


def parse_sections(data):
    """解析 PE 节表。"""
    pe = struct.unpack_from('<I', data, 0x3C)[0]
    if data[pe:pe + 4] != b'PE\0\0':
        raise ValueError('不是有效的 PE 文件')
    nsec = struct.unpack_from('<H', data, pe + 6)[0]
    optsz = struct.unpack_from('<H', data, pe + 20)[0]
    sectab = pe + 24 + optsz
    secs = []
    for i in range(nsec):
        o = sectab + i * 40
        name = data[o:o + 8]
        vsize, vaddr, rsize, rptr = struct.unpack_from('<IIII', data, o + 8)
        d0 = struct.unpack_from('<I', name, 0)[0]
        d1 = struct.unpack_from('<I', name, 4)[0]
        secs.append(dict(idx=i, name=name, d0=d0, d1=d1,
                         vsize=vsize, vaddr=vaddr, rsize=rsize, rptr=rptr,
                         prod=u32(d0 * d1)))
    return pe, secs


def derive_keystream(data, secs, target):
    """复现 Eazfuscator 代码加密的 16 项 keystream。

    种子先被"其它节区内容哈希"演化（反篡改），再滚动展开为 16 项。
    """
    num5, num6, num7, num8 = SEED_INIT
    for s in secs:
        if s['prod'] in (SECTION_MAGIC, 0):
            continue                        # 目标节区自身不参与；空节跳过
        n = s['vsize'] >> 2
        avail = min(s['rsize'], s['vsize']) >> 2
        for k in range(n):
            v = struct.unpack_from('<I', data, s['rptr'] + (k % avail) * 4)[0] if avail else 0
            nv = u32(u32(num5 ^ v) + num6 + u32(num7 * num8))
            num5, num6, num7, num8 = num6, num7, num8, nv

    arr = [0] * 16
    arr2 = [0] * 16
    for j in range(16):
        arr[j] = num8
        arr2[j] = num6
        num5 = u32((num6 >> 5) | (num6 << 27))
        num6 = u32((num7 >> 3) | (num7 << 29))
        num7 = u32((num8 >> 7) | (num8 << 25))
        num8 = u32((num5 >> 11) | (num5 << 21))
    for i in range(16):
        op = i % 3
        if op == 0:
            arr[i] = u32(arr[i] ^ arr2[i])
        elif op == 1:
            arr[i] = u32(arr[i] * arr2[i])
        else:
            arr[i] = u32(arr[i] + arr2[i])
    return arr


def crypt_section(buf, target, ks_init, encrypt):
    """解密/加密目标节区。

    keystream 以**明文**推进：
        plain = cipher ^ ks[i&15]
        ks[i&15] = (ks[i&15] ^ plain) + FEEDBACK
    因此 encrypt=True 时写出的是 cipher，但推进仍用 plain —— 这是"改完能原样
    加回去"的关键。
    """
    ks = list(ks_init)
    base = target['rptr']
    for i in range(target['vsize'] >> 2):
        o = base + i * 4
        v = struct.unpack_from('<I', buf, o)[0]
        if encrypt:
            plain = v
            out = u32(v ^ ks[i & 15])
        else:
            plain = u32(v ^ ks[i & 15])
            out = plain
        struct.pack_into('<I', buf, o, out)
        ks[i & 15] = u32((ks[i & 15] ^ plain) + KEYSTREAM_FEEDBACK)


def patch_manifest_no_uac(data):
    """把 requireAdministrator 就地改为 asInvoker（等长补空格）。

    仅用于无 UAC 的自动化环境；正式样本必须保留 requireAdministrator，
    否则应用会自提权重启、不创建主窗口。
    """
    needle = b'level="requireAdministrator"'
    i = data.find(needle)
    if i < 0:
        return False
    base = b'level="asInvoker"'
    data[i:i + len(needle)] = base + b' ' * (len(needle) - len(base))
    return True


def sha256(b):
    return hashlib.sha256(b).hexdigest()


# ----------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(
        description='项目N 客户端授权旁路复现补丁工具（受权审计用）',
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('src', help='官方原版 项目N.exe 路径')
    ap.add_argument('dst', help='输出（漏洞版）exe 路径')
    ap.add_argument('--profile', choices=sorted(PROFILES), default='pro',
                    help='补丁组合：flags(仅PRO标记) / pro(+isPro) / max(+授权旁路)')
    ap.add_argument('--no-uac', action='store_true',
                    help='同时把清单改为 asInvoker（仅自动化测试用）')
    args = ap.parse_args()

    raw = open(args.src, 'rb').read()
    src_sha = sha256(raw)
    print('=' * 76)
    print(' 项目N 客户端授权旁路复现补丁工具')
    print('=' * 76)
    print(f'[输入] {args.src}')
    print(f'       SHA-256 = {src_sha}')
    if src_sha != EXPECTED_SHA256:
        print('       ⚠ 与官方 v2.2.4.3 基准哈希不一致；结果可能不适用。')
    else:
        print('       ✓ 与官方 v2.2.4.3 基准哈希一致')

    title, patches = PROFILES[args.profile]
    print(f'[配置] {title}')
    print(f'       共 {len(patches)} 处补丁')

    data = bytearray(raw)
    pe, secs = parse_sections(data)
    target = next((s for s in secs if s['prod'] == SECTION_MAGIC), None)
    if target is None:
        print('!! 未定位到加密代码节区（目标节名前 8 字节乘积应等于 0x65452714）')
        return 1
    print(f'[节区] idx={target["idx"]} VA=0x{target["vaddr"]:x} '
          f'VSize=0x{target["vsize"]:x} RawPtr=0x{target["rptr"]:x}')

    # 1) 解密代码节区
    ks = derive_keystream(data, secs, target)
    crypt_section(data, target, ks, encrypt=False)
    print('[步骤] 代码节区已解密（明文 IL 层）')

    # 2) 施加补丁
    print('[步骤] 施加补丁：')
    for rva, old, new, desc in patches:
        off = target['rptr'] + (rva - target['vaddr'])
        cur = bytes(data[off:off + len(old)])
        ok = (cur == old)
        data[off:off + len(new)] = new
        flag = '✓' if ok else '✗(原始字节不符!)'
        print(f'   {flag} RVA 0x{rva:06X}  {old.hex(" "):<16} -> {new.hex(" "):<16}  {desc}')
        if not ok:
            print(f'        实际读到: {cur.hex(" ")}')

    # 3) 加密回写
    crypt_section(data, target, ks, encrypt=True)
    print('[步骤] 代码节区已按加密方向回写（除补丁点外与原文件一致）')

    if args.no_uac:
        print('[步骤] 清单 requireAdministrator -> asInvoker :', patch_manifest_no_uac(data))

    # 4) 输出与校验
    out = bytes(data)
    os.makedirs(os.path.dirname(os.path.abspath(args.dst)), exist_ok=True)
    open(args.dst, 'wb').write(out)
    diff = sum(1 for i in range(len(raw)) if raw[i] != out[i])
    print()
    print(f'[输出] {args.dst}')
    print(f'       大小      = {len(out)} 字节')
    print(f'       SHA-256   = {sha256(out)}')
    print(f'       差异字节  = {diff}  (含 keystream 雪崩，属正常)')
    print('=' * 76)
    return 0


if __name__ == '__main__':
    sys.exit(main())
