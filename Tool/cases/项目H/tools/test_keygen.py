# -*- coding: utf-8 -*-
"""项目H Keygen 自检（pytest 兼容，也可直接 python tests/test_keygen.py 运行）

覆盖：
  - 算法常量与 keystream 周期
  - 官方公钥密文解密（CIPHER→OFFICIAL_PUBKEY）
  - 期望设备码（与 frida 实测值对照）
  - 校验字符（adjacent_char_diff_sum）
  - encode/decode 回路
  - 激活码生成→模拟客户端验签（含官方公钥必失败）
  - patch 公钥（官方公钥恒等；新公钥成对）
  - persist patch 往返
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from keygen.algo import (  # noqa: E402
    CIPHER,
    CIPHER_BODY,
    KEYSTREAM,
    OFFICIAL_PUBKEY,
    adjacent_char_diff_sum,
    build_activation_code,
    decode_field,
    decrypt_pubkey,
    ed25519_verify,
    encode_field,
    expected_machineid,
    patch_persist,
    patch_public_key,
    simulate_client,
)
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

GUID = "c342b9e3-b9d0-40a0-8d38-542a2339d02e"


def test_constants():
    assert len(CIPHER) == 58
    assert len(CIPHER_BODY) == 33
    assert len(KEYSTREAM) == 33
    assert KEYSTREAM[:16] == KEYSTREAM[16:32], "keystream 16 字节周期"


def test_official_pubkey_restore():
    assert decrypt_pubkey(CIPHER_BODY).rstrip(b"\x00") == OFFICIAL_PUBKEY


def test_expected_machineid():
    assert expected_machineid(GUID) == "62D7-B676622561"  # frida 实测值


def test_adjacent_char_diff_sum():
    assert adjacent_char_diff_sum("62D7B6766225") == "6"
    assert adjacent_char_diff_sum("") == "0"
    assert adjacent_char_diff_sum("A") == "A"


def test_encode_decode_roundtrip():
    for k in (0, 1, 98, 250):
        plain = b"62D7-B676622561"
        enc = encode_field(plain, k)
        assert decode_field(enc) == plain


def test_gen_and_simulate():
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key().public_bytes_raw()
    code = build_activation_code(priv, name="t", email="t@t", machine_guid=GUID)
    res = simulate_client(code, pub)
    assert res and res["nam"] == "t"
    assert res["hwi"]["machineid"] == expected_machineid(GUID)
    # 官方公钥必须验签失败
    assert simulate_client(code, OFFICIAL_PUBKEY) is None


def test_patch_pubkey_identity():
    exe = open(r"<本地路径>", "rb").read()
    out = patch_public_key(exe, OFFICIAL_PUBKEY)
    assert out == exe


def test_patch_pubkey_roundtrip():
    exe = open(r"<本地路径>", "rb").read()
    priv = Ed25519PrivateKey.generate()
    pub = priv.public_key().public_bytes_raw()
    while b"\x00" in pub:
        priv = Ed25519PrivateKey.generate()
        pub = priv.public_key().public_bytes_raw()
    out = patch_public_key(exe, pub)
    assert len(out) == len(exe)
    assert out != exe


def test_patch_persist_roundtrip():
    exe = open(r"<本地路径>", "rb").read()
    enabled = patch_persist(exe, True)
    assert enabled != exe
    restored = patch_persist(enabled, False)
    assert restored == exe


if __name__ == "__main__":
    import traceback

    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"[PASS] {name}")
            except Exception:
                failures += 1
                print(f"[FAIL] {name}")
                traceback.print_exc()
    print(f"\n{sum(1 for n in globals() if n.startswith('test_')) - failures}/{sum(1 for n in globals() if n.startswith('test_'))} passed")
    sys.exit(1 if failures else 0)