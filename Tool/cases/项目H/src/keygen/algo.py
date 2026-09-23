# -*- coding: utf-8 -*-
"""
项目H <目标版本> 授权算法核心（独立逆向还原）

覆盖：
  1. 设备绑定哈希：期望设备码 = blake2s(("项目H 2", "1", MachineGuid))[-6:] 的 hex 大写
     按 4-8 分段 + 校验字符(相邻 ASCII 差和 % len) + '1'（15 字符，自洽 len=6）
  2. JSON license 载荷：字段 nam/eml/lic/dev/pln/dom/api/iat/exp/exx/ref/hwi{...}
  3. hwi.machineid 编码：encode_field（随机 key XOR + 循环旋转），客户端 decode_field 还原
  4. 激活码结构：code[0]=版本字符，code[1]=校验字符(对 base64 段的相邻差和)，code[2]='-'，
     code[3:]=base64( sig(64B) + gzip(JSON) XOR sig )
  5. Ed25519 签名/验签（使用 keypair.bin 配套私钥；公钥已内嵌于 patched 项目H.exe）
  6. 官方公钥存储密文替换：keystream 派生自官方密文 XOR 官方明文，可把任意新公钥加密回去

所有接口均带自检断言（见文件末尾 if __name__ == "__main__"）。
"""

import base64
import datetime
import gzip
import hashlib
import json
import struct
import zlib

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey,
        Ed25519PublicKey,
    )
    from cryptography.hazmat.primitives import serialization
    from cryptography.exceptions import InvalidSignature
    HAVE_CRYPTOGRAPHY = True
except ImportError:  # pragma: no cover
    Ed25519PrivateKey = None
    Ed25519PublicKey = None
    HAVE_CRYPTOGRAPHY = False


# ---------------------------------------------------------------------------
# 常量（来自逆向，frida 动态提取验证）
# ---------------------------------------------------------------------------

# 官方 Ed25519 公钥（32 字节，原始格式）
OFFICIAL_PUBKEY = bytes.fromhex(
    "86a6313855512c692b7f44a7041a86d02890544923714acaeeb29e52883c9060"
)

# 官方公钥密文（58 字节，来自 FUN_140249fa0 的 15 个立即数，栈序）
CIPHER = bytes.fromhex(
    "02d60506aca99a6d902f58a6bf0c0a4dace06077da89fcce55e28253332a1cfd"
    "bb01b4eb32f98a2e2bac2ec37a0b013dd675d375071fb22a05f6"
)
assert len(CIPHER) == 58

# 密文主体（前 33 字节 = 公钥 32 字节 + NUL 终止字节）
CIPHER_BODY = CIPHER[:33]

# 明文主体：官方公钥 + b'\x00'（QByteArray(char*, -1) 以 NUL 结尾的字符串语义）
PLAIN = OFFICIAL_PUBKEY + b"\x00"
assert len(PLAIN) == 33

# keystream：密文主体 XOR 明文主体（16 字节周期，实测）
KEYSTREAM = bytes(c ^ p for c, p in zip(CIPHER_BODY, PLAIN))
assert KEYSTREAM[:16] == KEYSTREAM[16:32], "keystream 应为 16 字节周期"

# patch 文件偏移（RVA - 0xC00，见 docs/reverse-engineering.md）
PATCH_OFFSETS = [
    0x2493C8, 0x2493CF, 0x2493D6, 0x2493DD, 0x2493E4, 0x2493EB, 0x2493F2, 0x2493F9,
    0x249400,  # block[32..35]: 密文第 33 字节 + 标志 + IV 前 2 字节
]

# FUN_245880 持久化 patch：把 license 状态检查的失败出口立即数改为 0
# （使 项目H 启动即视为已激活；详见 docs/algorithm.md）
PERSIST_PATCHES = {
    0x245a14: b"\x0c\x00\x00\x00",
    0x245ada: b"\x08\x00\x00\x00",
    0x245b12: b"\x1f\x00\x00\x00",
    0x245b22: b"\x0c\x00\x00\x00",
}


# ---------------------------------------------------------------------------
# 设备码与哈希
# ---------------------------------------------------------------------------

def blake2s_short(data: bytes, r: int) -> bytes:
    """客户端 sub_140245b50 的哈希：blake2s('项目H 2' + '1' + data) 取尾部 r 字节"""
    h = hashlib.blake2s(digest_size=16)
    h.update(b"项目H 2")
    h.update(b"1")
    h.update(data)
    return h.digest()[-r:]


def adjacent_char_diff_sum(s: str) -> str:
    """相邻 ASCII 码差绝对值之和 mod len，取该下标字符（编制 FUN_288c00）"""
    if not s:
        return "0"
    n = len(s)
    if n == 1:
        return s[0]
    total = sum(abs(ord(s[i]) - ord(s[i - 1])) for i in range(1, n))
    return s[total % n]


def expected_machineid(machine_guid: str) -> str:
    """客户端现算的期望设备码（15 字符，自洽 len=6）
    示意：62D7-B676622561 = '62D7B6766225' 4-8 分段 + 校验 + '1'
    """
    h = blake2s_short(machine_guid.encode("utf-8"), 6).hex().upper()
    assert len(h) == 12
    s = h[:4] + "-" + h[4:]
    return s + adjacent_char_diff_sum(h) + "1"


def read_machine_guid() -> str:
    """读 HKLM\\SOFTWARE\\Microsoft\\Cryptography\\MachineGuid"""
    import winreg
    try:
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography")
        try:
            guid, _ = winreg.QueryValueEx(key, "MachineGuid")
            return guid
        finally:
            winreg.CloseKey(key)
    except OSError:
        raise RuntimeError("无法读取 MachineGuid（需要 Windows + 注册表权限）")


# ---------------------------------------------------------------------------
# hwi.machineid 字段编解码（FUN_26db40 / FUN_26dc80）
# ---------------------------------------------------------------------------

def _key_sign(b: int) -> int:
    """int8 有符号"""
    return b - 256 if b > 127 else b


def encode_field(plain: bytes, key: int = None) -> bytes:
    """encode：rotate right |key^L|%L 再 XOR(key^i)，前插 key 字节。
    key=None 时自动选可打印 ASCII key（保证 JSON / UTF-8 传输无损）。"""
    n = len(plain)
    if key is None:
        for k in range(0x20, 0x7F):
            enc = encode_field(plain, k)
            if all(0x20 <= b < 0x7F for b in enc):
                return enc
        key = (plain[0] + 1) & 0xFF
    key_se = _key_sign(key)
    rot = abs(n ^ key_se) % n
    body = bytearray(plain)
    if rot:
        body = body[-rot:] + body[:-rot]
    for i in range(n):
        body[i] ^= (key ^ i) & 0xFF
    return bytes([key]) + bytes(body)


def decode_field(data: bytes) -> bytes:
    """decode：XOR(key^i) 再 rotate left |key^(L-1)|%(L-1)"""
    n = len(data) - 1
    if n <= 0:
        return b""
    key = data[0]
    key_se = _key_sign(key)
    rot = abs(n ^ key_se) % n
    body = bytearray(data[1:1 + n])
    for i in range(n):
        body[i] ^= (key ^ i) & 0xFF
    if rot:
        body = body[rot:] + body[:rot]
    return bytes(body)


# ---------------------------------------------------------------------------
# 签名 / 验签 / 载荷
# ---------------------------------------------------------------------------

def xorcrypt(data: bytes, key: bytes) -> bytes:
    """逐字节周期异或（周期 = len(key)）"""
    if not key:
        return data
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


def generate_keypair_no_nul():
    """生成 Ed25519 密钥对，公钥 32 字节且不含 0x00（QByteArray 内嵌字符串必需）"""
    if not HAVE_CRYPTOGRAPHY:
        raise RuntimeError("需要 cryptography 库")
    while True:
        priv = Ed25519PrivateKey.generate()
        pub = priv.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw)
        if 0 not in pub:
            return priv, priv.private_bytes(
                encoding=serialization.Encoding.Raw,
                format=serialization.PrivateFormat.Raw,
                encryption_algorithm=serialization.NoEncryption()), pub


def sign_json(priv, json_bytes: bytes) -> bytes:
    """Ed25519 签名，返回 64 字节"""
    return priv.sign(json_bytes)


def ed25519_verify(pub: bytes, msg: bytes, sig: bytes) -> bool:
    if not HAVE_CRYPTOGRAPHY:
        raise RuntimeError("需要 cryptography 库")
    try:
        Ed25519PublicKey.from_public_bytes(pub).verify(sig, msg)
        return True
    except InvalidSignature:
        return False


def make_license_json(name, email, dom, machineid, plan="Personal", days=366):
    """构造 license JSON（与服务端签发同构）"""
    now = datetime.datetime.now()
    exp = now + datetime.timedelta(days=days)
    info = {
        "nam": name,
        "eml": email,
        "lic": "KEYGEN",
        "dev": 1,
        "pln": plan,   # Personal / Business / Trial
        "dom": dom,    # 匹配工作组（"" 则跳过检查）
        "api": 0,
        "iat": now.strftime("%Y-%m-%d %H:%M:%S"),
        "exp": exp.strftime("%Y-%m-%d %H:%M:%S"),
        "exx": exp.strftime("%Y-%m-%d %H:%M:%S"),
        "ref": now.strftime("%Y-%m-%d %H:%M:%S"),
        "hwi": {"machineid": machineid, "platform": 1, "domain": ""},
    }
    return json.dumps(info, separators=(",", ":")).encode("utf-8")


def build_activation_code(priv, name="keygen", email="keygen@keygen.local",
                          plan="Personal", days=366, machine_guid=None,
                          dom="") -> str:
    """生成离线激活码（0<checksum>-<base64>）"""
    guid = machine_guid or read_machine_guid()
    mid = expected_machineid(guid)
    js = make_license_json(name, email, dom, mid, plan, days)
    sig = sign_json(priv, js)
    body = xorcrypt(gzip.compress(js, 9), sig)
    b64 = base64.b64encode(sig + body).decode()
    check = adjacent_char_diff_sum(b64)
    return "0" + check + "-" + b64


def simulate_client(code: str, pub: bytes) -> dict:
    """模拟客户端判定链，返回解析出的 JSON；失败返回 None（描述在注释/异常）"""
    if not (len(code) > 3 and code[2] == "-"):
        return None
    if code[1] != adjacent_char_diff_sum(code[3:]):
        return None
    raw = base64.b64decode(code[3:])
    if len(raw) < 65:
        return None
    sig = raw[:64]
    body = bytearray(raw[64:])
    body = bytearray(xorcrypt(bytes(body), sig))       # A
    try:
        body = bytearray(gzip.decompress(bytes(body)))   # B
    except zlib.error:
        return None
    body = bytearray(xorcrypt(bytes(body), sig))       # C（B 与验签前抵消）
    msg = xorcrypt(bytes(body), sig)                    # 验签前再 XOR = JSON 明文
    if not ed25519_verify(pub, msg, sig):
        return None
    return json.loads(msg)


# ---------------------------------------------------------------------------
# 官方公钥密文替换（patch 项目H.exe 换成自己的密钥对）
# ---------------------------------------------------------------------------

def encrypt_pubkey(new_pub: bytes) -> bytes:
    """把 32 字节新公钥加密成 33 字节密文主体（= 新明文 XOR keystream）"""
    assert len(new_pub) == 32 and 0 not in new_pub, "公钥必须 32 字节且不含 NUL"
    return bytes(p ^ k for p, k in zip(new_pub, KEYSTREAM)) + bytes([KEYSTREAM[32]])


def decrypt_pubkey(body: bytes) -> bytes:
    """从密文主体恢复公钥（用于验证）"""
    return bytes(c ^ k for c, k in zip(body, KEYSTREAM))


def patch_public_key(src_exe: bytes, new_pub: bytes) -> bytes:
    """替换 项目H.exe 内嵌官方公钥为 new_pub（9 处文件偏移）"""
    assert len(new_pub) == 32 and 0 not in new_pub
    data = bytearray(src_exe)
    body = encrypt_pubkey(new_pub)
    for i, off in enumerate(PATCH_OFFSETS):
        if i == len(PATCH_OFFSETS) - 1:
            # 第 9 个 dword：只改首字节（body[32]），其余保持
            data[off:off + 4] = bytes([body[32]]) + bytes(data[off + 1:off + 4])
        else:
            data[off:off + 4] = body[i * 4:(i + 1) * 4]
    return bytes(data)


def patch_persist(src_exe: bytes, enable: bool = True) -> bytes:
    """（可选）把 FUN_245880 的失败出口改为 0 → 启动即 Pro。
    注：某些环境实测对话框打开偶发退出，推荐默认关闭；核心 keygen 用 --persist 显式开启。"""
    data = bytearray(src_exe)
    for rva_off, orig in PERSIST_PATCHES.items():
        off = rva_off - 0xC00 + 2  # +2 跳过 C7 07 指令头
        if enable:
            assert bytes(data[off:off + 4]) == orig, f"persist patch 位置校验失败 {rva_off:#x}"
            data[off:off + 4] = b"\x00" * 4
        else:
            if bytes(data[off:off + 4]) == b"\x00" * 4:
                data[off:off + 4] = orig
    return bytes(data)


# ---------------------------------------------------------------------------
# 自检
# ---------------------------------------------------------------------------

def selftest():
    assert adjacent_char_diff_sum("62D7B6766225") == "6", "校验字符公式"
    assert expected_machineid("c342b9e3-b9d0-40a0-8d38-542a2339d02e") == \
        "62D7-B676622561", "期望设备码"
    mid = "62D7-B676622561"
    enc = encode_field(mid.encode())
    assert decode_field(enc) == mid.encode(), "encode/decode 回路"
    # keystream 周期
    assert KEYSTREAM[:16] == KEYSTREAM[16:32]
    # 密文还原官方公钥
    assert decrypt_pubkey(CIPHER_BODY).rstrip(b"\x00") == OFFICIAL_PUBKEY
    # patch 往返
    exe = open(r"<本地路径>", "rb").read()
    out = patch_public_key(exe, OFFICIAL_PUBKEY)
    assert out == exe, "官方公钥 patch 应恒等"
    print("[selftest] OK")


if __name__ == "__main__":
    selftest()