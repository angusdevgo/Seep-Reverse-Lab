#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the four tiny APKs that pin the APK-rebuild contract of `so_constpatch.py`.

WHY THIS EXISTS
---------------
`so_constpatch.py` rebuilt an APK through `zipfile.ZipInfo(filename, date_time)`, which
drops `extra`, `external_attr`, `create_system` and re-deflates every entry. An entry
that must stay STORED or 4-byte aligned (`resources.arsc`, an uncompressed `lib/*.so`)
can therefore come back compressed or unaligned, and the result is refused by the
installer with `[-124]` -- or simply not loadable when the manifest asks for
`extractNativeLibs="false"`. A regression test for that fix needs inputs that actually
carry the metadata which was being dropped, at a size worth keeping in the repository:

  plain.apk         DEFLATED entries, no `resources.arsc` -> an unsafe rebuild is not
                    in play, so this is the "rebuild is allowed" control
  arsc_aligned.apk  `resources.arsc` STORED and 4-byte aligned, plus a STORED and a
                    DEFLATED `lib/*.so` -> the storage/alignment contract must survive
  noextract.apk     the manifest declares `android:extractNativeLibs="false"` and both
                    `resources.arsc` and `lib/*.so` are STORED+aligned -> a rebuild must
                    be REFUSED unless `--unsafe-rebuild` is passed
  services.apk      `META-INF/services/**` entries, a UTF-8 entry name and a non-empty
                    archive comment -> untouched entries must come back byte-identical

Nothing here is target data: every fixture is synthesised from the constants below. Two
details exist so the fixtures are not weaker than real input:

* `AndroidManifest.xml` is a real binary AXML document (string pool + start element), so
  the manifest check reads the same bytes a compiler-produced manifest would give it.
* `resources.arsc` is a valid `RES_TABLE_TYPE` header plus filler: enough to pin the
  storage/alignment contract, not a renderable resource table.
* the `lib/*.so` payload is a real (tiny) aarch64 shared object with `.rodata` and
  `.shstrtab` section headers, so `--section-aware` exercises the section map instead of
  falling back to "no sections".

USAGE
-----
    python make_fixture_apk.py --out tests/fixtures/apk

The generated files are committed. Regenerate only when the contract itself changes;
the output is deterministic (fixed timestamps, fixed compression level, no randomness).
"""
from __future__ import annotations

import argparse
import hashlib
import os
import struct
import zlib

ALIGN = 4
STAMP_UNIX = 1577836800                     # 2020-01-01T00:00:00Z
FORCE_UTF8 = 0x800                          # general purpose bit 11


# ------------------------------------------------------------------ small builders

def _dos(dt):
    """(time, date) MS-DOS words, the way a zip local header stores them."""
    y, mo, d, h, mi, s = dt
    return (h << 11) | (mi << 5) | (s // 2), ((y - 1980) << 9) | (mo << 5) | d


def _deflate(data):
    """Raw deflate (no zlib wrapper) -- what a method-8 zip entry holds."""
    c = zlib.compressobj(9, zlib.DEFLATED, -15)
    return c.compress(data) + c.flush()


def ext_stamp(unix=STAMP_UNIX):
    """An extended-timestamp extra field (id 0x5455), so `extra` is never empty.

    Real APKs carry this on entries written by a toolchain that stamps mtimes, and it is
    exactly the field a rebuilt archive used to lose.
    """
    return b'\x55\x54' + struct.pack('<H', 5) + b'\x01' + struct.pack('<I', unix)


def align_record(pad):
    """A private extra record of `4 + pad` bytes, i.e. `pad` bytes of alignment.

    A zip extra area is a sequence of (id, 2-byte size, payload) records, so the smallest
    record is 4 bytes and a 1-3 byte pad cannot be expressed on its own. Appending a
    record of length `4 + pad` shifts the data offset by `pad` (mod 4), which is exactly
    what is needed, without inserting a filler entry.
    """
    if pad <= 0:
        return b''
    return b'\xca\xca' + struct.pack('<H', pad) + b'\x00' * pad


def make_elf(const=b'apkhuan', decoy=b'libapkhuanx.so'):
    """A minimal aarch64 ET_DYN object: ELF header, `.rodata`, `.shstrtab`, shdrs.

    `const` sits alone between NULs (an isolated constant, safe to rewrite in place);
    `decoy` contains the same bytes as a substring, which is the case `--find` must
    report as NOT isolated.
    """
    rodata = b'\x00' + const + b'\x00' + decoy + b'\x00'
    shstr = b'\x00.rodata\x00.shstrtab\x00'

    ehsize, shentsize, shnum, shstrndx = 64, 64, 3, 2
    ro_off = ehsize
    shstr_off = ro_off + len(rodata)
    sh_off = (shstr_off + len(shstr) + 7) & ~7

    ident = b'\x7fELF' + bytes([2, 1, 1, 0]) + b'\x00' * 8
    ehdr = ident + struct.pack('<HHIQQQIHHHHHH',
                               3,            # e_type   = ET_DYN
                               183,          # e_machine= EM_AARCH64
                               1,            # e_version
                               0, 0,         # e_entry, e_phoff
                               sh_off,       # e_shoff
                               0,            # e_flags
                               ehsize, 0, 0, shentsize, shnum, shstrndx)

    def shdr(name, typ, flags, addr, off, size, align=1):
        return struct.pack('<IIQQQQIIQQ', name, typ, flags, addr, off, size,
                           0, 0, align, 0)

    shdrs = (shdr(0, 0, 0, 0, 0, 0)
             + shdr(1, 1, 0x2, 0x1000, ro_off, len(rodata))        # .rodata PROGBITS
             + shdr(9, 3, 0, 0, shstr_off, len(shstr)))            # .shstrtab STRTAB
    pad = b'\x00' * (sh_off - (shstr_off + len(shstr)))
    return ehdr + rodata + shstr + pad + shdrs


def _string_pool(strings):
    """A UTF-8 (flag 0x100) RES_STRING_POOL chunk."""
    offsets, blob = [], b''
    for s in strings:
        raw = s.encode('utf-8')
        assert len(raw) < 0x80 and len(s) < 0x80, 'fixture pool is ASCII/short on purpose'
        offsets.append(len(blob))
        blob += bytes([len(raw), len(s)]) + raw + b'\x00'
    strings_start = 28 + 4 * len(strings)
    header = struct.pack('<HHI', 0x0001, 28, strings_start + len(blob))
    header += struct.pack('<IIIII', len(strings), 0, 0x100, strings_start, 0)
    return header + b''.join(struct.pack('<I', o) for o in offsets) + blob


def make_axml(package='com.example.fixture', extract_native_libs=None):
    """A minimal but structurally valid binary AndroidManifest.xml.

    Layout: file header, one string pool, one START_ELEMENT chunk for <manifest>. The
    attribute shape matches what aapt2 emits: `extractNativeLibs` is a boolean
    (dataType 0x12) with no raw string, namespaced to the android URI.
    """
    android_uri = 'http://schemas.android.com/apk/res/android'
    strings = ['android', android_uri, 'manifest', 'package', 'extractNativeLibs', package]
    s = {v: i for i, v in enumerate(strings)}

    attrs = [(0xFFFFFFFF, s['package'], 0xFFFFFFFF, 0x03, s[package])]
    if extract_native_libs is not None:
        attrs.append((s[android_uri], s['extractNativeLibs'], 0xFFFFFFFF, 0x12,
                      1 if extract_native_libs else 0))

    pool = _string_pool(strings)

    def chunk(ctype, node, tail):
        # chunk size covers the 8-byte chunk header as well as `node` and `tail`.
        body = node + tail
        return struct.pack('<HHI', ctype, 16, 8 + len(body)) + body

    node = struct.pack('<II', 1, 0xFFFFFFFF)                    # lineNumber, comment
    body = struct.pack('<II', 0xFFFFFFFF, s['manifest'])        # ns, name
    body += struct.pack('<HHHHHH', 20, 20, len(attrs), 0, 0, 0)
    for ns, name, raw, dtype, data in attrs:
        body += struct.pack('<III', ns, name, raw)
        body += struct.pack('<HBBI', 8, 0, dtype, data)
    element = chunk(0x0102, node, body)
    end = chunk(0x0103, node, struct.pack('<II', 0xFFFFFFFF, s['manifest']))

    total = 8 + len(pool) + len(element) + len(end)
    return struct.pack('<HHI', 0x0003, 8, total) + pool + element + end


def make_arsc(filler=60):
    """A `RES_TABLE_TYPE` header with zero packages, plus filler bytes."""
    body = struct.pack('<I', 0) + b'\x00' * filler
    return struct.pack('<HHI', 0x0002, 12, 12 + len(body)) + body


def make_dex(classes=2):
    """A dex header whose file_size matches, so a reader does not reject it outright.

    Only the header is written: the fixtures exist to pin zip behaviour, not dex
    semantics, and a full dex would be the largest file in the repository's test tree.
    """
    header_size, endian = 0x70, 0x12345678
    size = header_size + 4 * classes
    h = bytearray(header_size)
    h[0:8] = b'dex\n035\x00'
    h[32:36] = struct.pack('<I', size)
    h[36:40] = struct.pack('<I', header_size)
    h[40:44] = struct.pack('<I', endian)
    h[104:108] = struct.pack('<I', 0)          # data_size
    h[108:112] = struct.pack('<I', header_size)
    return bytes(h) + b'\x00' * (size - header_size)


# ------------------------------------------------------------------ zip writer

class Entry(object):
    """One fixture entry, with the metadata the rebuild must carry over."""

    def __init__(self, name, data, method=8, date_time=(2020, 1, 1, 0, 0, 0),
                 extra=None, external_attr=0o100644 << 16, internal_attr=0,
                 create_system=3, comment=b'', align=False, utf8=False):
        self.name = name
        self.data = data
        self.method = method
        self.date_time = date_time
        self.extra = ext_stamp() if extra is None else extra
        self.external_attr = external_attr
        self.internal_attr = internal_attr
        self.create_system = create_system
        self.comment = comment
        self.align = align
        self.utf8 = utf8

    @property
    def flags(self):
        return FORCE_UTF8 if self.utf8 else 0


def write_apk(path, entries, archive_comment=b''):
    """Write a zip the way zipalign does: STORED stays STORED, aligned stays aligned.

    Written by hand rather than through `zipfile` because alignment is a property of the
    local header length, which `zipfile` cannot express -- the same reason `repack.py`
    hand-rolls its writer.
    """
    out = bytearray()
    cd = []
    for e in entries:
        name_b = e.name.encode('utf-8')
        payload = e.data if e.method == 0 else _deflate(e.data)
        crc = zlib.crc32(e.data) & 0xFFFFFFFF
        extra = e.extra
        if e.align:
            head = len(out) + 30 + len(name_b) + len(extra)
            extra += align_record((ALIGN - head % ALIGN) % ALIGN)
        t, d = _dos(e.date_time)
        local_off = len(out)
        out += struct.pack('<IHHHHHIIIHH', 0x04034B50, 20, e.flags, e.method, t, d,
                           crc, len(payload), len(e.data), len(name_b), len(extra))
        out += name_b + extra + payload
        data_off = local_off + 30 + len(name_b) + len(extra)
        if e.align and data_off % ALIGN:
            raise RuntimeError('%s is not %d-byte aligned' % (e.name, ALIGN))
        cd.append((e, name_b, crc, len(payload), len(extra), local_off))

    cd_off = len(out)
    for e, name_b, crc, csize, elen, local_off in cd:
        t, d = _dos(e.date_time)
        out += struct.pack('<IHHHHHHIIIHHHHHII', 0x02014B50,
                           (e.create_system << 8) | 20, 20, e.flags, e.method, t, d,
                           crc, csize, len(e.data), len(name_b), len(e.extra),
                           len(e.comment), 0, e.internal_attr, e.external_attr,
                           local_off)
        out += name_b + e.extra + e.comment
    cd_size = len(out) - cd_off
    out += struct.pack('<IHHHHIIH', 0x06054B50, 0, 0, len(cd), len(cd), cd_size,
                       cd_off, len(archive_comment))
    out += archive_comment

    folder = os.path.dirname(os.path.abspath(path))
    if folder:
        os.makedirs(folder, exist_ok=True)
    with open(path, 'wb') as fh:
        fh.write(bytes(out))
    return bytes(out)


# ------------------------------------------------------------------ the fixtures

def definitions():
    """name -> (entries, archive comment). Deterministic; no timestamps from the clock.

    Every STORED entry is 4-byte aligned, the way `zipalign` lays a real APK out: that is
    what makes "the rebuild did not break alignment" a checkable claim, and what keeps a
    rebuilt fixture acceptable to `zipalign -c`.
    """
    elf = make_elf()
    dex = make_dex()
    strings_xml = b'<?xml version="1.0" encoding="utf-8"?>\n<resources/>\n'
    plain_manifest = make_axml('com.example.plain')
    noextract_manifest = make_axml('com.example.noextract', extract_native_libs=False)

    st = dict(method=0, align=True, date_time=(2021, 6, 15, 12, 34, 56))
    plain = [
        Entry('AndroidManifest.xml', plain_manifest, **st),
        Entry('classes.dex', dex, external_attr=0o100600 << 16),
        Entry('res/values/strings.xml', strings_xml),
        Entry('lib/arm64-v8a/libfoo.so', elf),
        Entry('META-INF/MANIFEST.MF', b'Manifest-Version: 1.0\r\n\r\n'),
    ]

    arsc_aligned = [
        Entry('AndroidManifest.xml', plain_manifest, **st),
        Entry('classes.dex', dex),
        # DEFLATED and patched: its compressed size moves, so resources.arsc has to be
        # re-aligned on output. This is the case the old writer silently broke.
        Entry('lib/arm64-v8a/libfoo.so', elf),
        # STORED: must stay STORED, must not be re-compressed, must stay aligned.
        Entry('lib/arm64-v8a/libbar.so', elf, method=0, align=True,
              external_attr=0o100755 << 16),
        Entry('resources.arsc', make_arsc(), method=0, align=True),
        Entry('res/values/strings.xml', strings_xml),
        Entry('META-INF/services/com.example.Provider',
              b'com.example.ProviderImpl\n'),
    ]

    noextract = [
        Entry('AndroidManifest.xml', noextract_manifest, **st),
        Entry('classes.dex', dex),
        Entry('lib/arm64-v8a/libfoo.so', elf, method=0, align=True),
        Entry('resources.arsc', make_arsc(), method=0, align=True),
    ]

    services = [
        Entry('AndroidManifest.xml', plain_manifest, **st),
        Entry('META-INF/services/com.example.Provider', b'com.example.ProviderImpl\n'),
        Entry('META-INF/services/kotlinx.coroutines.internal.MainDispatcherFactory',
              b'kotlinx.coroutines.internal.MainDispatcherFactoryImpl\n', method=0,
              align=True),
        Entry('lib/x86_64/libfoo.so', elf, external_attr=0),
        # A non-ASCII name with the UTF-8 flag (bit 11) set: the raw name bytes and the
        # flag must both survive a rebuild, and this entry must not be touched at all.
        Entry('res/raw/\u6d4b\u8bd5.bin', b'fixture-payload\x00', utf8=True,
              create_system=0, external_attr=0, internal_attr=1,
              comment=b'fixture comment'),
    ]

    return {
        'plain.apk': (plain, b''),
        'arsc_aligned.apk': (arsc_aligned, b''),
        'noextract.apk': (noextract, b''),
        'services.apk': (services, b'fixture-archive-comment'),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--out', default=os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                  'apk'),
                    help='directory to write the fixtures into')
    ap.add_argument('--list', action='store_true', help='print names and exit')
    a = ap.parse_args()

    defs = definitions()
    if a.list:
        for name in sorted(defs):
            print(name)
        return 0

    for name in sorted(defs):
        entries, comment = defs[name]
        path = os.path.join(a.out, name)
        blob = write_apk(path, entries, comment)
        print('%-18s %6d bytes  %2d entries  sha256=%s'
              % (name, len(blob), len(entries), hashlib.sha256(blob).hexdigest()[:16]))
    print('wrote %d fixture(s) to %s' % (len(defs), os.path.abspath(a.out)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
