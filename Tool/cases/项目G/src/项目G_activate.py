#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""项目G <目标版本> 一键激活工具（patch 路线，服务端签名模型下 keygen 不可行的替代方案）。

原理（逆向证据见 cases/2026-09-项目G-keygen/findings.md F8/F10）:
  - 项目G 激活数据由服务器签发（V1 property_key 网络激活; V2 设备 payload + sha384(key_hash)
    自引用校验），纯离线 keygen 不可行。
  - 启动授权判定点: 项目G::isLicensed(void) @0x140b83910 (文件偏移 0xB82D10)，
    checkLicense 每次启动调用两次；原版返回 false -> "checkLicense free trial"。
  - Patch: 入口 5 字节 48 89 4c 24 08 -> B0 01 C3 90 90 (mov al,1; ret; nop; nop)，
    isLicensed(void) 恒 true -> 启动走 "checkLicense pass"（frida 分支 hook 双向实测）。

支持正版: 项目G 是商业软件，请通过官方渠道购买授权。
  官方站点: https://1218.io/
  购买页(中): https://1218.io/项目G/fwd_cn/order.html
  购买页(EN): https://1218.io/项目G/fwd/order.html

用法:
  一键激活项目G.exe                       # 自动定位 项目G 目录并激活
  一键激活项目G.exe --check               # 查看状态
  一键激活项目G.exe --revert              # 还原原版（.bak）
  一键激活项目G.exe --install-dir DIR     # 指定 项目G 目录
  一键激活项目G.exe --buy                 # 打开官方购买页
"""
import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import webbrowser

try:
    import winreg
except ImportError:  # 非 Windows（如 CI lint）
    winreg = None

GUARD_RUN_KEY = r'Software\Microsoft\Windows\CurrentVersion\Run'
GUARD_VALUE = '项目GActivateGuard'

OFFICIAL_SITE = 'https://1218.io/'
BUY_URL_CN = 'https://1218.io/项目G/fwd_cn/order.html'
BUY_URL_EN = 'https://1218.io/项目G/fwd/order.html'

# 已知版本哈希（强校验）；未知构建走字节级检查兜底
ORIG_SHA256 = '<实测哈希>'
PATCHED_SHA256 = '<实测哈希>'

PATCH_OFFSET = 0xB82D10
PATCH_BYTES = bytes.fromhex('b0 01 c3 90 90')   # mov al,1; ret; nop; nop
ORIG_BYTES = bytes.fromhex('48 89 4c 24 08')   # mov [rsp+8], rcx


def sha256(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def banner(silent=False):
    if silent:
        return
    print('=' * 60)
    print('  项目G <目标版本> 一键激活工具 (patch 路线)')
    print('  keygen 不可行: 激活数据由服务器签发 (payload 自引用校验)')
    print('  --- 支持正版 ---')
    print('  官方站点: %s' % OFFICIAL_SITE)
    print('  购买页(中): %s' % BUY_URL_CN)
    print('  购买页(EN): %s' % BUY_URL_EN)
    print('=' * 60)
    print()


def guard_command():
    """--guard 写入的启动命令：登录时静默检查并自动修复。"""
    if getattr(sys, 'frozen', False):
        return '"%s" --silent --fix' % sys.executable
    py = sys.executable or 'python'
    script = os.path.abspath(__file__)
    return '"%s" "%s" --silent --fix' % (py, script)


def add_guard():
    if winreg is None:
        print('[-] winreg 不可用（非 Windows）')
        return False
    cmd = guard_command()
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, GUARD_RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            winreg.SetValueEx(k, GUARD_VALUE, 0, winreg.REG_SZ, cmd)
        print('[+] 防回退守卫已注册（登录自动检查/修复）:')
        print('    HKCU\\%s\\%s = %s' % (GUARD_RUN_KEY, GUARD_VALUE, cmd))
        return True
    except OSError as e:
        print('[-] 注册守卫失败: %s' % e)
        return False


def remove_guard():
    if winreg is None:
        print('[-] winreg 不可用')
        return False
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, GUARD_RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
            try:
                winreg.DeleteValue(k, GUARD_VALUE)
                print('[+] 防回退守卫已移除')
            except OSError:
                print('[=] 守卫本就不存在')
        return True
    except OSError as e:
        print('[-] 移除守卫失败: %s' % e)
        return False


def guard_status():
    if winreg is None:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, GUARD_RUN_KEY, 0, winreg.KEY_READ) as k:
            try:
                v, _ = winreg.QueryValueEx(k, GUARD_VALUE)
                return v
            except OSError:
                return None
    except OSError:
        return None


def try_locate_项目G_dirs():
    """定位 项目G.exe 所在目录：便携目录 -> 常见安装路径 -> 注册表 Uninstall。"""
    candidates = []
    script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    # ReverseLab 便携解包目录（相对本脚本）
    for rel in ('samples/unpacked/项目G',):
        p = os.path.normpath(os.path.join(script_dir, '..', rel))
        if os.path.isfile(os.path.join(p, '项目G.exe')):
            candidates.append(p)
    # 常见安装路径
    for base in (os.environ.get('LOCALAPPDATA', ''), os.environ.get('ProgramFiles', ''),
                 os.environ.get('ProgramFiles(x86)', ''), r'C:\Program Files', r'C:\Program Files (x86)',
                 '<本地路径>', 'B:\\'):
        if base:
            for sub in ('项目G', '项目G'):
                p = os.path.join(base, sub)
                if os.path.isfile(os.path.join(p, '项目G.exe')):
                    candidates.append(p)
    # 注册表 Uninstall 定位
    try:
        import winreg
        for hive, kroot in ((winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall'),
                            (winreg.HKEY_CURRENT_USER, r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall'),
                            (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall')):
            try:
                with winreg.OpenKey(hive, kroot) as k:
                    i = 0
                    while True:
                        try:
                            sub = winreg.EnumKey(k, i)
                            i += 1
                        except OSError:
                            break
                        try:
                            with winreg.OpenKey(hive, kroot + '\\' + sub) as sk:
                                name, _ = winreg.QueryValueEx(sk, 'DisplayName')
                                if name and '项目G' in name.lower():
                                    loc, _ = winreg.QueryValueEx(sk, 'InstallLocation')
                                    if loc and os.path.isfile(os.path.join(loc, '项目G.exe')):
                                        candidates.append(loc)
                        except OSError:
                            continue
            except OSError:
                continue
    except Exception:
        pass
    seen, out = set(), []
    for c in candidates:
        c = os.path.normpath(c)
        if c not in seen:
            seen.add(c)
            out.append(c)
    return out


def apply(install_dir):
    target = os.path.join(install_dir, '项目G.exe')
    if not os.path.isfile(target):
        print('[-] 项目G.exe not found in %s' % install_dir)
        return False
    with open(target, 'rb') as f:
        data = f.read()
    cur5 = data[PATCH_OFFSET:PATCH_OFFSET + 5]
    cur_sha = hashlib.sha256(data).hexdigest()
    if cur5 == PATCH_BYTES:
        print('[=] %s: already patched (offset 0x%X = %s)' % (target, PATCH_OFFSET, cur5.hex(' ')))
        return True
    if cur5 != ORIG_BYTES:
        print('[!] %s: unexpected bytes at 0x%X: %s' % (target, PATCH_OFFSET, cur5.hex(' ')))
        print('    known original  : %s' % ORIG_SHA256)
        print('    known patched   : %s' % PATCHED_SHA256)
        print('    current sha256  : %s' % cur_sha)
        print('    （版本不匹配或已非标准构建，未改动）')
        return False
    if cur_sha != ORIG_SHA256:
        print('[!] %s: offset bytes match original but sha256 differs: %s' % (target, cur_sha))
        print('    （可能是不同小版本；字节级补丁继续执行）')
    bak = target + '.bak'
    if not os.path.isfile(bak):
        shutil.copy2(target, bak)
        print('[+] backup -> %s' % bak)
    out = bytearray(data)
    out[PATCH_OFFSET:PATCH_OFFSET + 5] = PATCH_BYTES
    with open(target, 'wb') as f:
        f.write(bytes(out))
    print('[+] patched %s' % target)
    print('[+] offset 0x%X: %s -> %s' % (PATCH_OFFSET, ORIG_BYTES.hex(' '), PATCH_BYTES.hex(' ')))
    print('[+] new sha256: %s' % sha256(target))
    print('[+] 完成。重启 项目G 后启动判定走 "checkLicense pass"。')
    return True


def revert(install_dir):
    target = os.path.join(install_dir, '项目G.exe')
    bak = target + '.bak'
    if not os.path.isfile(bak):
        print('[-] no backup file %s' % bak)
        return False
    shutil.copy2(bak, target)
    print('[+] restored original from %s' % bak)
    print('[+] sha256: %s' % sha256(target))
    return True


def check(install_dir):
    target = os.path.join(install_dir, '项目G.exe')
    if not os.path.isfile(target):
        print('[-] 项目G.exe not found')
        return
    with open(target, 'rb') as f:
        data = f.read(0xB82D10 + 5)
    cur5 = data[PATCH_OFFSET:PATCH_OFFSET + 5]
    if cur5 == PATCH_BYTES:
        state = 'patched (已激活)'
    elif cur5 == ORIG_BYTES:
        state = 'original (原版)'
    else:
        state = 'unknown'
    print('[i] %s: %s' % (target, state))
    if os.path.isfile(target + '.bak'):
        print('[i] backup: %s' % (target + '.bak'))


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument('--install-dir', help='项目G 目录（含 项目G.exe）')
    ap.add_argument('--revert', action='store_true', help='还原原版')
    ap.add_argument('--check', action='store_true', help='检查状态')
    ap.add_argument('--buy', action='store_true', help='打开官方购买页')
    ap.add_argument('--guard', action='store_true', help='注册防回退守卫（登录自动检查/修复）')
    ap.add_argument('--unguard', action='store_true', help='移除防回退守卫')
    ap.add_argument('--fix', action='store_true', help='静默修复模式：自动定位并对所有目录补丁（守卫用）')
    ap.add_argument('--silent', action='store_true', help='不输出（守卫用）')
    args = ap.parse_args()

    if args.buy:
        webbrowser.open(BUY_URL_CN)
        print('[+] 已在浏览器打开官方购买页: %s' % BUY_URL_CN)
        return

    if args.guard:
        banner(args.silent)
        if add_guard():
            print('[+] 完成。之后若 项目G 被升级覆盖，登录时守卫会自动恢复激活。')
        return
    if args.unguard:
        banner(args.silent)
        remove_guard()
        return

    banner(args.silent)
    dirs = [args.install_dir] if args.install_dir else try_locate_项目G_dirs()
    if not dirs:
        print('[-] 项目G 目录未找到，请用 --install-dir 指定')
        sys.exit(1)

    if args.fix:
        # 静默修复：只对「已补丁过或可识别的原版」目录自动重打；未知版本跳过
        for d in dirs:
            target = os.path.join(d, '项目G.exe')
            if not os.path.isfile(target):
                continue
            with open(target, 'rb') as f:
                data = f.read()
            cur5 = data[PATCH_OFFSET:PATCH_OFFSET + 5]
            if cur5 == PATCH_BYTES:
                continue
            apply(d)
        return

    print('[i] 定位到 %d 个 项目G 目录' % len(dirs))
    for d in dirs:
        if args.check:
            check(d)
        elif args.revert:
            revert(d)
        else:
            apply(d)
    g = guard_status()
    if g:
        print('[i] 防回退守卫: 已启用 (%s ...)' % g[:60])
    else:
        print('[i] 防回退守卫: 未启用（建议运行本工具 --guard 注册）')
    if not args.check and not args.revert:
        print()
        print('[+] 如需还原正版: 运行本工具 --revert')
        print('[+] 支持正版: 官方购买页 %s' % BUY_URL_CN)


if __name__ == '__main__':
    main()