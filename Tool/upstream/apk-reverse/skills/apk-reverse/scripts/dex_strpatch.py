#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Byte-level, in-place patch of a string constant inside a dex — no smali round-trip.

Why not a smali round-trip: a disassemble -> reassemble of a whole tree can damage
R8-optimized output in ways the class table does not show. Observed symptom: a synthetic
access bridge lost its interface/class relationship, producing
IncompatibleClassChangeError ("Found interface X, but class was expected") at runtime even
though class_defs and access_flags looked untouched. See references/pitfalls.md P3.

What this script does instead (zero structural change to the dex):
  1. Replaces the target string with another of **exactly equal byte length**. Equal length
     keeps the string_data_item uleb128 length prefix unchanged, so offsets, indices and
     every table stay exactly where they were.
  2. Recomputes the dex header signature (SHA-1, from offset 32) and checksum (adler32,
     from offset 12).

Use only when the replacement can be equal-length. Otherwise use a method-level dex API
rewrite (references/dex-patching.md, technique 1).

Usage: python dex_strpatch.py <in.dex> <out.dex> <old_str> <new_str>
Requires len(new) == len(old) in UTF-8 bytes, and exactly one occurrence of old in the dex.
"""
import hashlib
import struct
import sys
import zlib


def _uleb128(data, off):
    result = 0
    shift = 0
    while True:
        b = data[off]
        off += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            break
        shift += 7
    return result, off


def _read_strings(data):
    off = struct.unpack('<I', data[0x3C:0x40])[0]
    size = struct.unpack('<I', data[0x38:0x3C])[0]
    out = []
    for i in range(size):
        sdata_off = struct.unpack('<I', data[off + i * 4: off + i * 4 + 4])[0]
        n, p = _uleb128(data, sdata_off)
        out.append((sdata_off, bytes(data[p:p + n])))
    return out


def _order_ok(data, off, ob, nb):
    """Check whether replacing `ob` with `nb` still satisfies the string_ids ordering rule.

    Note: string_ids stores the offset of each string_data_item — i.e. the position of the
    **length prefix** (a few bytes ahead of the UTF-8 payload), not of the text itself — so
    matching by string-data offset directly is not possible; this matches the entry by
    content instead.
    """
    entries = _read_strings(data)
    idx = None
    for i, (_sdata_off, raw) in enumerate(entries):
        if raw == ob:
            idx = i
            break
    if idx is None:
        print('[order] target string not found in string_ids, skip check')
        return True
    prev = entries[idx - 1][1] if idx > 0 else None
    nxt = entries[idx + 1][1] if idx + 1 < len(entries) else None
    if prev is not None and nb <= prev:
        print('[order] FAIL: new %r <= prev %r' % (nb, prev))
        return False
    if nxt is not None and nb >= nxt:
        print('[order] FAIL: new %r >= next %r' % (nb, nxt))
        return False
    print('[order] OK: %r < %r < %r' % (prev, nb, nxt))
    return True


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ('-h', '--help'):
        print(__doc__)
        return 0
    if len(sys.argv) < 5:
        print('error: needs 4 arguments, got %d\n' % (len(sys.argv) - 1))
        print(__doc__)
        return 2
    src, dst, old, new = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
    ob, nb = old.encode('utf-8'), new.encode('utf-8')
    if len(ob) != len(nb):
        print('[FAIL] length mismatch: %d vs %d (must be equal)' % (len(ob), len(nb)))
        return 1
    data = bytearray(open(src, 'rb').read())
    if data[:8] != b'dex\n035\x00' and data[:4] != b'dex\n':
        print('[warn] unexpected magic: %r' % bytes(data[:8]))
    n = data.count(ob)
    print('[info] occurrences of %r = %d' % (old, n))
    if n != 1:
        print('[FAIL] expected exactly 1 occurrence')
        return 1
    off = data.find(ob)

    # The dex spec requires string_ids to be ordered by string content. An equal-length
    # replacement moves no offset, but it does change where this entry sits in that ordering
    # — and once it lands out of order the whole dex is rejected by the ClassLoader
    # (symptom: ClassNotFoundException naming the Application class). So validate the
    # interval before writing.
    if not _order_ok(data, off, ob, nb):
        print('[FAIL] replacement would break string_ids ordering. '
              'Pick a string that stays between its two neighbours.')
        return 1

    data[off:off + len(ob)] = nb
    print('[ok] patched at offset 0x%x: %r -> %r' % (off, old, new))

    # signature = SHA-1 over data[32:], stored at 12..32
    sig = hashlib.sha1(bytes(data[32:])).digest()
    data[12:32] = sig
    # checksum = adler32 over data[12:], stored at 8..12 (little endian)
    chk = zlib.adler32(bytes(data[12:])) & 0xFFFFFFFF
    data[8:12] = struct.pack('<I', chk)
    print('[ok] signature=%s checksum=0x%08x' % (sig.hex(), chk))

    open(dst, 'wb').write(bytes(data))
    print('[ok] wrote %s (%d bytes)' % (dst, len(data)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
