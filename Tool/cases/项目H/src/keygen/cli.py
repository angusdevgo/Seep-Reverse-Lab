# -*- coding: utf-8 -*-
"""项目H <目标版本> Keygen —— 命令行入口

用法:
  python -m keygen.cli gen            [--name N] [--email E] [--plan Personal] [--days 366] [--guid G]
  python -m keygen.cli patch          <项目H.exe> <out.exe> [--persist]
  python -m keygen.cli persist        <项目H.exe> <out.exe>   (等同 patch --persist)
  python -m keygen.cli verify         <code>                      (模拟客户端判定链)
  python -m keygen.cli selftest

说明:
  gen    : 生成激活码（默认读取本机 MachineGuid；--guid 可指定其它机器）
  patch  : 替换内嵌官方公钥为自己的密钥对并另存；--persist 同时把 FUN_245880
           失败出口改 0（启动即 Pro）。patch 后需配合 gen 生成的激活码激活。
  verify : 对激活码做模拟客户端校验（同一算法链）。
"""
import argparse
import base64
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from keygen.algo import (  # noqa: E402
    HAVE_CRYPTOGRAPHY,
    build_activation_code,
    decrypt_pubkey,
    encrypt_pubkey,
    expected_machineid,
    generate_keypair_no_nul,
    patch_public_key,
    patch_persist,
    read_machine_guid,
    simulate_client,
    selftest,
    OFFICIAL_PUBKEY,
)
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402


def default_keypair_path():
    """0 门槛：打包后 keypair 固定放在 exe 同目录；源码模式放当前目录"""
    if getattr(sys, "frozen", False):  # PyInstaller 打包
        return os.path.join(os.path.dirname(sys.executable), "keypair.bin")
    return os.path.join(os.getcwd(), "keypair.bin")


def load_or_create_keypair(path):
    """载入/生成 64 字节密钥对（私钥32 + 公钥32），公钥不含 NUL"""
    if os.path.exists(path):
        data = open(path, "rb").read()
        if len(data) == 64:
            return data[:32], data[32:]
    priv, priv_raw, pub = generate_keypair_no_nul()
    open(path, "wb").write(priv_raw + pub)
    return priv_raw, pub


def cmd_gen(args):
    if not HAVE_CRYPTOGRAPHY:
        sys.exit("[!] 需要 cryptography 库")
    args.keypair = args.keypair or default_keypair_path()
    guid = args.guid or read_machine_guid()
    priv_raw, pub = load_or_create_keypair(args.keypair)
    print(f"MachineGuid : {guid}")
    print(f"期望设备码 : {expected_machineid(guid)}")
    priv = Ed25519PrivateKey.from_private_bytes(priv_raw)
    code = build_activation_code(
        priv, name=args.name, email=args.email, plan=args.plan,
        days=args.days, machine_guid=guid)
    print(f"激活码      : {code}")
    if args.out:
        open(args.out, "w").write(code)
        print(f"[OK] 已写入 {args.out}")
    if args.gui:
        # 写入文件供 GUI 读取，避免跨进程传参
        open(os.path.join(os.path.dirname(args.keypair), "last_code.txt"), "w").write(code)
    return code


def cmd_patch(args):
    args.keypair = args.keypair or default_keypair_path()
    src = open(args.exe, "rb").read()
    priv_raw, pub = load_or_create_keypair(args.keypair)
    out = patch_public_key(src, pub)
    if args.persist:
        out = patch_persist(out, enable=True)
        print("[i] 已启用 --persist（启动即 Pro）")
    open(args.out, "wb").write(out)
    print(f"[OK] 已写入 {args.out}")
    print(f"    新公钥: {pub.hex()}")
    print(f"    校验   : 密文恢复 = {decrypt_pubkey(encrypt_pubkey(pub)).hex()}")


def cmd_verify(args):
    if args.pub:
        pub = bytes.fromhex(args.pub)
    else:
        pub = OFFICIAL_PUBKEY
    res = simulate_client(args.code, pub)
    if res is None:
        print("[X] 校验失败（格式 / 签名 / 解压任一环节）")
        sys.exit(1)
    print("[OK] 校验通过")
    print(json.dumps(res, indent=2, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description="项目H <目标版本> Keygen")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("gen", help="生成激活码")
    p.add_argument("--name", default="keygen")
    p.add_argument("--email", default="keygen@keygen.local")
    p.add_argument("--plan", default="Personal")
    p.add_argument("--days", type=int, default=366)
    p.add_argument("--guid", default=None)
    p.add_argument("--keypair", default=None)
    p.add_argument("--out", default=None)
    p.add_argument("--gui", action="store_true", help=argparse.SUPPRESS)
    p.set_defaults(fn=cmd_gen)

    p = sub.add_parser("patch", help="替换公钥（可选 --persist）")
    p.add_argument("exe")
    p.add_argument("out")
    p.add_argument("--persist", action="store_true", help="同时启用启动即 Pro")
    p.add_argument("--keypair", default=None)
    p.set_defaults(fn=cmd_patch)

    p = sub.add_parser("persist", help="仅启用启动即 Pro（等价 patch --persist 的持久化部分）")
    p.add_argument("exe")
    p.add_argument("out")
    p.add_argument("--keypair", default=None)
    p.set_defaults(fn=lambda a: cmd_patch(argparse.Namespace(
        exe=a.exe, out=a.out, persist=True, keypair=a.keypair)))

    p = sub.add_parser("verify", help="模拟客户端校验激活码")
    p.add_argument("code")
    p.add_argument("--pub", default=None, help="ed25519 公钥 hex；缺省用官方公钥")
    p.set_defaults(fn=cmd_verify)

    p = sub.add_parser("selftest")
    p.set_defaults(fn=lambda a: selftest())

    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()