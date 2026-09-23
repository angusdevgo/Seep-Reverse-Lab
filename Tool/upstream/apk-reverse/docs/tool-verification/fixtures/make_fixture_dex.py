#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build a minimal, structurally valid dex whose reference counts are known.

WHY THIS EXISTS
---------------
Verifying a dex reader against a real APK only shows that two readers agree.
Verifying it against a program whose call graph was written down in advance shows
that the *number* is right. This fixture encodes exactly two method bodies:

    Lcom/example/Caller;->go()V    invoke-static   Lcom/example/Target;->run()V   x2
    Lcom/example/Target;->run()V   invoke-virtual  Ljava/lang/String;->length()I  x3

so the answers a blast-radius check must return are 3, 2 and 2. The same call
graph is also written out as a smali tree, because the point of the fix this
fixture verifies is that a `.dex` and a smali tree answer a needle identically.

USAGE
-----
    python make_fixture_dex.py out.dex [--smali DIR]

    # then, from the skill's scripts directory:
    python find_refs.py out.dex 'Ljava/lang/String;->length'   # expect 3
    python find_refs.py out.dex 'Lcom/example/Target;->run'    # expect 2
    python find_refs.py out.dex 'Lcom/example/Target;'         # expect 2
    python find_refs.py DIR  'Ljava/lang/String;->length'      # expect 3

Dependency-free (stdlib only) on purpose: the fixture must be reproducible on a
machine with no Android toolchain, which is where the defect it verifies was found.

Nothing here is target data. The dex is synthesised from the constants below.
"""
import argparse
import hashlib
import os
import struct
import zlib

CALLER = 'Lcom/example/Caller;'
TARGET = 'Lcom/example/Target;'
OBJECT = 'Ljava/lang/Object;'
STRING = 'Ljava/lang/String;'

SMALI_CALLER = """.class public Lcom/example/Caller;
.super Ljava/lang/Object;

.method public static go()V
    .registers 0
    invoke-static {}, Lcom/example/Target;->run()V
    invoke-static {}, Lcom/example/Target;->run()V
    return-void
.end method
"""

SMALI_TARGET = """.class public Lcom/example/Target;
.super Ljava/lang/Object;

.method public static run()V
    .registers 1
    invoke-virtual {v0}, Ljava/lang/String;->length()I
    invoke-virtual {v0}, Ljava/lang/String;->length()I
    invoke-virtual {v0}, Ljava/lang/String;->length()I
    return-void
.end method
"""

EXPECTED = (('Ljava/lang/String;->length', 3),
            ('Lcom/example/Target;->run', 2),
            ('Lcom/example/Target;', 2))


def uleb(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def p16(v):
    return struct.pack('<H', v)


def p32(v):
    return struct.pack('<I', v)


def string_data(s):
    raw = s.encode('utf-8')
    return uleb(len(raw)) + raw + b'\x00'


def code_item(registers, outs, insns):
    body = b''.join(p16(u) for u in insns)
    return (p16(registers) + p16(0) + p16(outs) + p16(0)
            + p32(0) + p32(len(insns)) + body)


def invoke(op, method_idx, count=0, c=0, g=0):
    """35c layout: op(G<<8)(count<<12), index, then the register nibbles."""
    return [op | (g << 8) | (count << 12), method_idx, c & 0xF]


def class_data(entries):
    """entries: [(method_idx, access_flags, code_off)], ascending by method_idx."""
    out = uleb(0) + uleb(0) + uleb(len(entries)) + uleb(0)
    prev = 0
    for mi, acc, co in entries:
        out += uleb(mi - prev) + uleb(acc) + uleb(co)
        prev = mi
    return out


def build():
    strings = sorted({CALLER, TARGET, OBJECT, STRING, 'I', 'V', 'go', 'run', 'length'})
    sidx = {s: i for i, s in enumerate(strings)}
    types = sorted({CALLER, TARGET, OBJECT, STRING, 'I', 'V'}, key=lambda t: sidx[t])
    tidx = {t: i for i, t in enumerate(types)}

    protos = [('I', 'I'), ('V', 'V')]                    # (shorty, return type)
    protos.sort(key=lambda p: tidx[p[1]])
    pidx = {shorty: i for i, (shorty, _r) in enumerate(protos)}

    methods = [(CALLER, 'go', 'V'), (TARGET, 'run', 'V'), (STRING, 'length', 'I')]
    methods.sort(key=lambda m: (tidx[m[0]], sidx[m[1]], pidx[m[2]]))
    midx = {(c, n): i for i, (c, n, _r) in enumerate(methods)}

    insns_go = invoke(0x71, midx[(TARGET, 'run')]) * 2 + [0x000E]
    insns_run = invoke(0x6E, midx[(STRING, 'length')], count=1) * 3 + [0x000E]

    off = 0x70
    string_ids_off = off
    off += 4 * len(strings)
    type_ids_off = off
    off += 4 * len(types)
    proto_ids_off = off
    off += 12 * len(protos)
    method_ids_off = off
    off += 8 * len(methods)
    class_defs_off = off
    off += 32 * 2
    data_off = off

    data = bytearray()

    def align(n):
        while len(data) % n:
            data.append(0)

    str_offs = []
    for s in strings:
        str_offs.append(data_off + len(data))
        data += string_data(s)

    align(4)
    code_go_off = data_off + len(data)
    data += code_item(0, 0, insns_go)
    align(4)
    code_run_off = data_off + len(data)
    data += code_item(1, 1, insns_run)
    align(4)

    cd_go_off = data_off + len(data)
    data += class_data([(midx[(CALLER, 'go')], 0x0009, code_go_off)])
    cd_run_off = data_off + len(data)
    data += class_data([(midx[(TARGET, 'run')], 0x0009, code_run_off)])
    align(4)

    map_off = data_off + len(data)

    def map_item(kind, size, offset):
        return p16(kind) + p16(0) + p32(size) + p32(offset)

    items = [
        (0x0000, 1, 0),                       # header_item
        (0x0001, len(strings), string_ids_off),
        (0x0002, len(types), type_ids_off),
        (0x0003, len(protos), proto_ids_off),
        (0x0005, len(methods), method_ids_off),
        (0x0006, 2, class_defs_off),
        (0x2002, len(strings), str_offs[0]),  # string_data_item
        (0x2001, 2, code_go_off),             # code_item
        (0x2000, 2, cd_go_off),               # class_data_item
        (0x1000, 1, map_off),                 # map_list
    ]
    items.sort(key=lambda it: it[2])
    data += p32(len(items)) + b''.join(map_item(*it) for it in items)

    string_ids = b''.join(p32(str_offs[i]) for i in range(len(strings)))
    type_ids = b''.join(p32(sidx[t]) for t in types)
    proto_ids = b''.join(p32(sidx[shorty]) + p32(tidx[ret]) + p32(0)
                         for shorty, ret in protos)
    method_ids = b''.join(p16(tidx[c]) + p16(pidx[r]) + p32(sidx[n])
                          for c, n, r in methods)

    def class_def(class_idx, super_idx, class_data_off):
        return (p32(class_idx) + p32(0x0001) + p32(super_idx) + p32(0)
                + p32(0xFFFFFFFF) + p32(0) + p32(class_data_off) + p32(0))

    classes = sorted([(CALLER, cd_go_off), (TARGET, cd_run_off)], key=lambda c: tidx[c[0]])
    class_defs = b''.join(class_def(tidx[c], tidx[OBJECT], cdo) for c, cdo in classes)

    h = bytearray(0x70)
    h[0:8] = b'dex\n035\x00'
    h[32:36] = p32(data_off + len(data))     # file_size
    h[36:40] = p32(0x70)                     # header_size
    h[40:44] = p32(0x12345678)               # endian_tag
    h[52:56] = p32(map_off)
    h[56:60] = p32(len(strings))
    h[60:64] = p32(string_ids_off)
    h[64:68] = p32(len(types))
    h[68:72] = p32(type_ids_off)
    h[72:76] = p32(len(protos))
    h[76:80] = p32(proto_ids_off)
    h[80:84] = p32(0)                        # field_ids_size
    # There are no fields. Size 0 is correct; the offset points at the next
    # section rather than 0 only because a zero offset reads as "out of range"
    # to a structural check that treats every offset as present.
    h[84:88] = p32(method_ids_off)
    h[88:92] = p32(len(methods))
    h[92:96] = p32(method_ids_off)
    h[96:100] = p32(2)                       # class_defs_size
    h[100:104] = p32(class_defs_off)
    h[104:108] = p32(len(data))
    h[108:112] = p32(data_off)

    blob = bytearray(bytes(h) + string_ids + type_ids + proto_ids + method_ids
                     + class_defs + bytes(data))
    blob[12:32] = hashlib.sha1(bytes(blob[32:])).digest()      # signature first
    blob[8:12] = (zlib.adler32(bytes(blob[12:])) & 0xFFFFFFFF).to_bytes(4, 'little')
    return bytes(blob), len(strings), len(types), len(methods)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('out', nargs='?', default='fixture.dex')
    ap.add_argument('--smali', metavar='DIR',
                    help='also write the same call graph as a smali tree')
    a = ap.parse_args()

    blob, n_str, n_ty, n_m = build()
    with open(a.out, 'wb') as fh:
        fh.write(blob)
    print('wrote %s (%d bytes, %d strings, %d types, %d methods, 2 classes)'
          % (a.out, len(blob), n_str, n_ty, n_m))

    if a.smali:
        d = os.path.join(a.smali, 'com', 'example')
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, 'Caller.smali'), 'w', newline='\n') as fh:
            fh.write(SMALI_CALLER)
        with open(os.path.join(d, 'Target.smali'), 'w', newline='\n') as fh:
            fh.write(SMALI_TARGET)
        print('wrote smali tree under %s' % a.smali)

    print('expected: ' + '  '.join('%s=%d' % kv for kv in EXPECTED))


if __name__ == '__main__':
    main()
