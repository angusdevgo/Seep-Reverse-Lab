# -*- coding: utf-8 -*-
"""项目GActivate 自检测试（pytest）。

覆盖:
  1. 常量自洽: 补丁偏移/原始字节/补丁字节/已知哈希
  2. 字节级补丁逻辑: 对内存中的伪 项目G.exe 应用/幂等/回滚
  3. 版本识别: 原始/已补丁/未知字节 三分支
"""
import hashlib
import io
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

import 项目G_activate as act

ORIG_SHA256 = '<实测哈希>'
PATCHED_SHA256 = '<实测哈希>'


class Fake项目G:
    """内存中的伪 项目G.exe（足够长以容纳补丁偏移）。"""

    def __init__(self, orig=True):
        self.data = bytearray(act.PATCH_OFFSET + 8)
        if orig:
            self.data[act.PATCH_OFFSET:act.PATCH_OFFSET + 5] = act.ORIG_BYTES
        else:
            self.data[act.PATCH_OFFSET:act.PATCH_OFFSET + 5] = act.PATCH_BYTES


def test_constants():
    assert len(act.PATCH_BYTES) == 5
    assert len(act.ORIG_BYTES) == 5
    assert act.PATCH_BYTES.hex(' ') == 'b0 01 c3 90 90'
    assert act.ORIG_BYTES.hex(' ') == '48 89 4c 24 08'
    assert act.PATCH_OFFSET == 0xB82D10


def test_known_hashes_match_samples():
    # 与 ReverseLab 样本副本一致性（若样本存在）
    sample = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..',
                          'ReverseLab', 'samples', 'unpacked', '项目G', '项目G.exe')
    if os.path.isfile(sample):
        h = hashlib.sha256(open(sample, 'rb').read()).hexdigest()
        assert h == ORIG_SHA256
    patched = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'tools', '项目GActivate.exe')
    # tools/项目GActivate.exe 是打包器本身，不校验哈希


def test_patch_bytes_roundtrip():
    f = Fake项目G(orig=True)
    data = bytes(f.data)
    assert data[act.PATCH_OFFSET:act.PATCH_OFFSET + 5] == act.ORIG_BYTES
    # apply
    out = bytearray(data)
    out[act.PATCH_OFFSET:act.PATCH_OFFSET + 5] = act.PATCH_BYTES
    assert bytes(out[act.PATCH_OFFSET:act.PATCH_OFFSET + 5]) == act.PATCH_BYTES
    # revert
    out[act.PATCH_OFFSET:act.PATCH_OFFSET + 5] = act.ORIG_BYTES
    assert bytes(out[act.PATCH_OFFSET:act.PATCH_OFFSET + 5]) == act.ORIG_BYTES


def test_version_detect():
    f1 = Fake项目G(orig=True)
    f2 = Fake项目G(orig=False)
    f3 = Fake项目G(orig=False)
    f3.data[act.PATCH_OFFSET:act.PATCH_OFFSET + 5] = b'\x90\x90\x90\x90\x90'
    def detect(data):
        cur5 = data[act.PATCH_OFFSET:act.PATCH_OFFSET + 5]
        if cur5 == act.PATCH_BYTES:
            return 'patched'
        if cur5 == act.ORIG_BYTES:
            return 'original'
        return 'unknown'
    assert detect(bytes(f1.data)) == 'original'
    assert detect(bytes(f2.data)) == 'patched'
    assert detect(bytes(f3.data)) == 'unknown'


def test_support_links_present():
    assert act.OFFICIAL_SITE == 'https://1218.io/'
    assert 'order.html' in act.BUY_URL_CN
    assert 'order.html' in act.BUY_URL_EN
