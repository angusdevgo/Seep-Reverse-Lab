#!/usr/bin/env python3
# capability: native_const_patch
# requires: python3 stdlib only (argparse, hashlib, json, struct, sys, zipfile, zlib)
# exits: 0 success / 1 negative finding or refused rebuild / 2 usage+input error
#        / 3 this tool cannot (safely) do it / 4 internal error, output discarded
"""Redirect a native library load by rewriting an isolated string constant in place.

Why this exists
---------------
Protected targets frequently name a *checker* library at a single call site
(``System.loadLibrary("X")`` reached from a JNI constant pool) rather than through
``DT_NEEDED``. When that checker does the integrity validation, deleting the loader
deadlocks you: keep it and validation kills the process, delete it and the load
throws.

Rewriting the *name* is the way out. Point that call at a library that is guaranteed
already mapped (on Android, ``android`` / ``libandroid.so``): the load succeeds, the
checker is never mapped, and **no byte offsets move** because the replacement is
exactly the same length. Nothing for an integrity check to notice about layout, and
no death path to neutralize.

Usage
-----
    # inspect: where does this name occur, and is it an isolated constant?
    python so_constpatch.py libfoo.so --find apkhuan

    # patch a bare .so
    python so_constpatch.py libfoo.so --replace apkhuan=android -o libfoo.patched.so

    # patch inside an APK (rebuilds the zip, entry order preserved)
    python so_constpatch.py app.apk --entry lib/arm64-v8a/libfoo.so \
        --replace apkhuan=android -o app.patched.apk

    # only patch occurrences that sit in an ELF constant-pool section
    python so_constpatch.py libfoo.so --replace apkhuan=android --section-aware

    # machine-readable, for a long task that decides from tokens
    python so_constpatch.py app.apk --entry lib/arm64-v8a/libfoo.so \
        --replace apkhuan=android -o out.apk --json

Design notes
------------
* Equal length is mandatory and enforced; there is no padding mode that can be safe
  when the next constant lives immediately after the NUL.
* ``--find`` reports whether each hit is isolated (NUL on both sides). Patching a
  substring of a longer identifier corrupts that identifier, so non-isolated hits are
  refused unless ``--allow-nonisolated`` is given explicitly.
* The ELF section map is only used for *reporting* which constant pool a hit lives in.
  It never gates a patch on section validity, because hardened libraries ship forged
  section headers (see references/native-tamper-and-suicide.md) while the bytes you
  need are still exactly where the loader reads them.

Rebuilding an APK is the dangerous half
---------------------------------------
Rewriting one zip entry means writing a new archive, and a zip is an install contract,
not a bag of files. The first version of this script wrote every entry through
``zipfile.ZipInfo(filename, date_time)`` and re-deflated the whole archive. That drops
the ``extra`` field, ``external_attr``, ``create_system`` and permissions, and it can
turn ``resources.arsc`` from STORED into DEFLATED. Android R+ then refuses the install::

    Failure [-124: Failed parse during installPackageLI: Targeting R+ (version 30 and
    above) requires the resources.arsc of installed APKs to be stored uncompressed and
    aligned on a 4-byte boundary]

and a package built with ``extractNativeLibs="false"`` can fail to load at all, because
its ``lib/*.so`` are mapped straight out of the archive.

This script now rebuilds the container the way a packager does:

  1. **Every entry keeps its own metadata byte-for-byte**: raw local name bytes, the
     local ``extra`` field, the central-directory ``extra``, ``external_attr``,
     ``internal_attr``, ``create_system``, ``create_version``, the entry comment, the
     DOS time/date words and the original ``version needed``.
  2. **STORED stays STORED.** An untouched entry's compressed stream is copied verbatim,
     so its CRC and ``compress_size`` are identical by construction. Only the entry you
     asked to rewrite is re-compressed, and then only if it was DEFLATED to begin with.
  3. **Alignment is recomputed deliberately.** ``resources.arsc`` and uncompressed
     ``lib/*.so`` are padded to a 4-byte data offset with a private extra record. The
     original local extra stays a byte-for-byte prefix; the pad is appended, never
     substituted.
  4. **An unsafe rebuild is refused by default.** If the manifest declares
     ``android:extractNativeLibs="false"``, or ``resources.arsc`` is present and is not
     STORED + 4-byte aligned, the script prints why and writes nothing. Pass
     ``--unsafe-rebuild`` to proceed anyway. If what you actually want is a resource-
     safe pack, use ``scripts/repack.py``: it owns the STORED+aligned writer and the
     signing pipeline.
  5. **The result is verified before it is reported.** Entry count, per-entry CRC,
     payload sha256, metadata equality and the arsc storage/alignment gate are all
     re-read from the file that was just written.

Exit codes (see references/long-task-discipline.md and the kit-wide convention)::

    0  success                     RESULT=patched | found
    1  negative finding            RESULT=not_found | refused_unsafe_rebuild
    2  usage or input error        RESULT=usage_error
    3  this tool cannot do it      RESULT=unsupported_container
    4  internal error, no output   RESULT=internal_error

``--json`` prints one JSON object (with ``status``, ``exit_code``, ``capability``,
``evidence``, ``warnings``, ``next_action``) followed by the same final
``RESULT=<token>`` line every other script in this kit ends with.
"""

import argparse
import hashlib
import json
import os
import re
import struct
import sys
import zipfile
import zlib

CAPABILITY = 'native_const_patch'
TOOL = 'so_constpatch.py'

ALIGN = 4
# Entries Android R+ requires to be STORED, and (for the ones it names) 4-byte aligned.
ALIGNED_STORED = ('resources.arsc',)
# `lib/<abi>/<name>.so` -- the ABI directory is part of the path, so `[^/]+` would match
# nothing on a real APK and silently skip the alignment of every native library.
ALIGNED_SO_RE = re.compile(r'^lib/.+\.so$')
# Private extra-field id used only for alignment padding. It never replaces an existing
# record; it is appended, so the entry's original extra field stays a prefix.
PAD_EXTRA_ID = 0xCA
MAX_ENTRIES = 0xFFFF
MAX_U32 = 0xFFFFFFFF


# ---------------------------------------------------------------- reporting

class Reporter(object):
    """Collects the log, prints it unless --json, and holds the machine answer.

    In --json mode stdout must stay parseable, so human lines are collected into
    ``evidence``/``warnings`` and only the JSON object plus the final RESULT line are
    printed.
    """

    def __init__(self, as_json=False, verbose=False):
        self.as_json = as_json
        self.verbose = verbose
        self.lines = []
        self.warnings = []
        self.notes = []

    def log(self, msg=''):
        self.lines.append(msg)
        if not self.as_json:
            print(msg, flush=True)

    def warn(self, msg):
        self.warnings.append(msg)
        self.log('WARNING: %s' % msg)

    def note(self, msg):
        self.notes.append(msg)

    @property
    def evidence(self):
        # A long package produces a long log; the tail is what matters, so keep the
        # first lines (what was requested) and the last ones (what happened).
        if len(self.lines) <= 60:
            return list(self.lines)
        return self.lines[:20] + ['... %d line(s) omitted ...' % (len(self.lines) - 40)] \
            + self.lines[-20:]


class Refused(Exception):
    """The requested work is not something this tool should do. Carries its exit code.

    ``data`` carries the measurement that justified the refusal into the JSON payload,
    so a caller does not have to scrape the log to find out *why* nothing was written.
    """

    def __init__(self, message, exit_code=2, token='usage_error', data=None):
        Exception.__init__(self, message)
        self.exit_code = exit_code
        self.token = token
        self.data = data or {}


# ---------------------------------------------------------------- ELF helpers

def elf_sections(data: bytes):
    """Return [(name, sh_type, addr, offset, size)] or [] if unusable.

    Deliberately tolerant: forged/truncated section headers are common in this
    domain, and a failed parse must not stop the string scan.
    """
    try:
        if data[:4] != b'\x7fELF':
            return []
        e_shoff = struct.unpack_from('<Q', data, 0x28)[0]
        e_shentsize = struct.unpack_from('<H', data, 0x3a)[0]
        e_shnum = struct.unpack_from('<H', data, 0x3c)[0]
        e_shstrndx = struct.unpack_from('<H', data, 0x3e)[0]
        if e_shoff == 0 or e_shnum == 0 or e_shoff >= len(data):
            return []
        raw = []
        for i in range(e_shnum):
            o = e_shoff + i * e_shentsize
            if o + 0x40 > len(data):
                break
            name, stype, _flags, addr, offset, size = struct.unpack_from('<IIQQQQ', data, o)
            raw.append([name, stype, addr, offset, size])
        if e_shstrndx >= len(raw):
            return []
        base = raw[e_shstrndx][3]
        out = []
        for name, stype, addr, offset, size in raw:
            try:
                end = data.index(b'\x00', base + name)
                nm = data[base + name:end].decode('ascii', 'replace')
            except Exception:
                nm = '?'
            out.append((nm, stype, addr, offset, size))
        return out
    except Exception:
        return []


def section_of(sections, off: int):
    for nm, stype, _addr, soff, ssize in sections:
        if stype != 8 and soff <= off < soff + ssize:
            return nm
    return None


POOLS = ('.rodata', '.data', '.data.rel.ro', '.rodata.str1.1', '.dynstr', '.strtab')


def occurrences(data: bytes, needle: bytes):
    """Yield (offset, isolated, section_name, context)."""
    sections = elf_sections(data)
    start = 0
    while True:
        i = data.find(needle, start)
        if i < 0:
            return
        prev = data[i - 1:i]
        nxt = data[i + len(needle):i + len(needle) + 1]
        isolated = (prev == b'\x00' or i == 0) and (nxt == b'\x00')
        yield i, isolated, section_of(sections, i), data[max(0, i - 24):i + len(needle) + 24]
        start = i + 1


def describe(ctx: bytes) -> str:
    return ''.join(chr(b) if 32 <= b < 127 else ('\\0' if b == 0 else '.') for b in ctx)


# ---------------------------------------------------------------- operations

def do_find(rep, data: bytes, needle: bytes) -> str:
    hits = list(occurrences(data, needle))
    if not hits:
        rep.log('no occurrence of %r' % needle.decode('utf-8', 'replace'))
        return 'not_found'
    rep.log('%d occurrence(s) of %r:' % (len(hits), needle.decode('utf-8', 'replace')))
    for off, iso, sec, ctx in hits:
        rep.log('  0x%-8x isolated=%-5s section=%-12s | %s' % (off, iso, sec or '-', describe(ctx)))
    n_iso = sum(1 for _, iso, _, _ in hits if iso)
    rep.log('\nisolated (safe to rewrite in place): %d / %d' % (n_iso, len(hits)))
    return 'found'


def do_replace(rep, data: bytes, old: bytes, new: bytes, section_aware: bool,
               allow_nonisolated: bool, force: bool) -> tuple[bytes, list]:
    if len(old) != len(new):
        raise Refused(
            'REFUSING: %r (%d bytes) -> %r (%d bytes).\n'
            'Equal length is mandatory - a different length shifts every byte after it '
            'and invalidates the ELF.\nPass a same-length name (e.g. pad with a shorter '
            'already-loaded library name).' % (
                old.decode('utf-8', 'replace'), len(old),
                new.decode('utf-8', 'replace'), len(new)), 2)

    hits = list(occurrences(data, old))
    if not hits:
        raise Refused('REFUSING: %r not present' % old.decode('utf-8', 'replace'),
                      1, 'not_found')

    selected = []
    for off, iso, sec, ctx in hits:
        if not iso and not allow_nonisolated:
            rep.log('  skip 0x%-8x not an isolated constant (would corrupt a neighbour)' % off)
            continue
        if section_aware and (sec not in POOLS):
            rep.log('  skip 0x%-8x section=%s (not a constant pool; --section-aware)' % (off, sec))
            continue
        selected.append(off)

    if not selected:
        raise Refused('REFUSING: no eligible occurrence (see remarks above)', 2)

    if len(selected) > 1 and not force:
        rep.log('\n%d eligible occurrence(s). Re-run with --force to patch all of them, '
                'or narrow the search.' % len(selected))
        for off in selected:
            rep.log('  0x%x' % off)
        raise Refused('more than one eligible occurrence; --force not given', 2)

    out = bytearray(data)
    applied = []
    for off in selected:
        before = bytes(out[off:off + len(old)])
        out[off:off + len(old)] = new
        applied.append((off, before, bytes(new)))
        rep.log('  patched 0x%-8x %r -> %r' % (off, before.decode('utf-8', 'replace'),
                                               new.decode('utf-8', 'replace')))

    changed = sum(1 for _off, before, after in applied
                  for a, b in zip(before, after) if a != b)
    rep.log('\n%d byte(s) actually changed inside %d same-length overwrite(s), '
            'file length unchanged (%d).' % (changed, len(applied), len(data)))
    return bytes(out), applied


# ---------------------------------------------------------------- AXML helpers

def axml_root_attributes(blob: bytes):
    """{name: value} for the root element of a binary AndroidManifest.xml.

    An independent implementation of the same walk ``scripts/repack.py`` performs (that
    script must stay usable on its own, and so must this one). Both are exercised on the
    same committed fixture, so a disagreement shows up as a test failure rather than as
    two tools quietly disagreeing about `extractNativeLibs`.
    """
    if len(blob) < 36 or struct.unpack_from('<H', blob, 0)[0] != 0x0003:
        return None                                  # not binary XML
    if struct.unpack_from('<H', blob, 8)[0] != 0x0001:
        return None                                  # no string pool where one must be
    hdr_size = struct.unpack_from('<H', blob, 10)[0]
    try:
        count, _styles, flags, strings_start, _styles_start = struct.unpack_from(
            '<IIIII', blob, 16)
    except struct.error:
        return None
    if not 0 < count <= 1000000:
        return None
    try:
        offsets = struct.unpack_from('<%dI' % count, blob, 8 + hdr_size)
    except struct.error:
        return None
    utf8 = bool(flags & (1 << 8))
    base = 8 + strings_start
    strings = []
    for off in offsets:
        p = base + off
        if p >= len(blob):
            return None
        try:
            if utf8:
                n = blob[p]
                p += 1
                if n & 0x80:
                    n = ((n & 0x7F) << 8) | blob[p]
                    p += 1
                m = blob[p]
                p += 1
                if m & 0x80:
                    m = ((m & 0x7F) << 8) | blob[p]
                    p += 1
                strings.append(blob[p:p + m].decode('utf-8', 'replace'))
            else:
                n = struct.unpack_from('<H', blob, p)[0]
                p += 2
                if n & 0x8000:
                    n = ((n & 0x7FFF) << 16) | struct.unpack_from('<H', blob, p)[0]
                    p += 2
                strings.append(blob[p:p + n * 2].decode('utf-16-le', 'replace'))
        except (IndexError, struct.error):
            return None

    total = struct.unpack_from('<I', blob, 4)[0] or len(blob)
    end = min(len(blob), total)
    off = 8
    while off + 8 <= end:
        ctype, _hsize, csize = struct.unpack_from('<HHI', blob, off)
        if csize < 8 or off + csize > end:
            return None
        if ctype == 0x0102:                          # RES_XML_START_ELEMENT
            try:
                attr_start, attr_size, attr_count = struct.unpack_from('<HHH', blob, off + 24)
            except struct.error:
                return None
            attrs = {}
            first = off + 16 + attr_start
            for i in range(attr_count):
                p = first + i * attr_size
                if attr_size < 20 or p + 20 > off + csize:
                    return None
                name_i, raw_i = struct.unpack_from('<II', blob, p + 4)
                _size, _res0, dtype = struct.unpack_from('<HBB', blob, p + 12)
                data = struct.unpack_from('<I', blob, p + 16)[0]
                name = strings[name_i] if name_i < len(strings) else '?'
                if dtype == 0x03:
                    val = strings[data] if data < len(strings) else ''
                elif raw_i != 0xFFFFFFFF and raw_i < len(strings):
                    val = strings[raw_i]
                elif dtype == 0x10:
                    val = str(data - (1 << 32) if data >= (1 << 31) else data)
                elif dtype == 0x12:
                    val = 'true' if data else 'false'
                else:
                    val = '@0x%x' % data
                attrs[name] = val
            return attrs
        off += csize
    return None


def manifest_extract_native_libs(blob: bytes):
    """'true' / 'false' when declared, None when absent, 'unreadable' when undecidable.

    A plain-text placeholder manifest is accepted: a fixture or a hand-built archive may
    not carry binary XML, and refusing to look would turn "no declaration" into a false
    alarm.
    """
    attrs = axml_root_attributes(blob)
    if attrs is not None:
        for key, val in attrs.items():
            if key == 'extractNativeLibs' or key.endswith(':extractNativeLibs'):
                return str(val).strip().lower()
        return None
    text = blob.decode('utf-8', 'replace')
    m = re.search(r'extractNativeLibs\s*=\s*"([^"]*)"', text)
    if m:
        return m.group(1).strip().lower()
    if '<manifest' in text:
        return None
    return 'unreadable'


FALSE_VALUES = ('false', '0')
TRUE_VALUES = ('true', '1')


# ---------------------------------------------------------------- container audit

def _local_layout(fh, header_offset):
    """(version_needed, flags, method, time_word, date_word, nlen, elen) of a local header."""
    fh.seek(header_offset)
    head = fh.read(30)
    if len(head) != 30 or head[:4] != b'PK\x03\x04':
        raise Refused('entry at 0x%x has no zip local header' % header_offset, 3,
                      'unsupported_container')
    ver_need, flags, method = struct.unpack_from('<HHH', head, 4)
    time_w, date_w = struct.unpack_from('<HH', head, 10)
    nlen, elen = struct.unpack_from('<HH', head, 26)
    return ver_need, flags, method, time_w, date_w, nlen, elen


def entry_data_offset(path, item, fh=None):
    """File offset of an entry's data, read from its own local header."""
    close = False
    if fh is None:
        fh = open(path, 'rb')
        close = True
    try:
        _v, _f, _m, _tw, _dw, nlen, elen = _local_layout(fh, item.header_offset)
        return item.header_offset + 30 + nlen + elen
    finally:
        if close:
            fh.close()


def needs_alignment(name, method, src_offset):
    """Should this entry land on a 4-byte data offset in the rebuilt archive?

    Three cases, in order of force:

    * `resources.arsc` -- Android R+ refuses the install outright, and uncompressed
      `lib/**/*.so` -- the platform maps those straight out of the archive, so the
      layout is part of the load contract. Always aligned.
    * any other STORED entry that was **already** aligned in the input -- `zipalign`
      aligns every uncompressed entry, so a rebuild that shifts one of them is a
      regression even though the installer tolerates it. Preserved, not introduced.
    * everything else -- untouched. A STORED entry that arrived unaligned is left
      unaligned: this tool does not silently re-lay-out an archive it was not asked to
      fix, and a DEFLATED entry has no alignment requirement at all.
    """
    if name in ALIGNED_STORED:
        return True
    if ALIGNED_SO_RE.match(name) and method == 0:
        return True
    return method == 0 and src_offset % ALIGN == 0


def _read_eocd(path):
    """(comment, entry_count, disk numbers). Raises when the EOCD is missing/zip64."""
    size = os.path.getsize(path)
    with open(path, 'rb') as fh:
        tail_len = min(size, 66000)
        fh.seek(size - tail_len)
        tail = fh.read(tail_len)
    idx = tail.rfind(b'PK\x05\x06')
    if idx < 0 or idx + 22 > len(tail):
        raise Refused('no end-of-central-directory record: not a zip archive', 3,
                      'unsupported_container')
    disk, cd_disk, n_disk, n_total = struct.unpack_from('<HHHH', tail, idx + 4)
    comment_len = struct.unpack_from('<H', tail, idx + 20)[0]
    if 0xFFFF in (n_disk, n_total) or disk or cd_disk:
        raise Refused('zip64 or multi-disk archive: this writer does not reproduce '
                      'zip64 structures safely. Use scripts/repack.py, or 7z to '
                      'rewrite the container first.', 3, 'unsupported_container')
    return tail[idx + 22:idx + 22 + comment_len], n_total, (disk, cd_disk)


def audit_apk_for_rebuild(path, rep):
    """What Android would say about this archive, plus the rebuild-refusal reasons.

    Returns a dict with the measured facts and an ``unsafe`` list. The audit is a
    *measurement*, not a guess: everything printed here is read from the file.
    """
    facts = {'path': os.path.abspath(path), 'entries': 0, 'zip64': False,
             'extract_native_libs': None, 'arsc': None, 'stored_so': [],
             'aligned_entries': [], 'data_descriptors': 0, 'unaligned_stored': []}
    unsafe = []
    comment, n_total, _disks = _read_eocd(path)
    facts['archive_comment_bytes'] = len(comment)
    facts['entries_in_eocd'] = n_total

    with zipfile.ZipFile(path, 'r') as z, open(path, 'rb') as fh:
        infos = z.infolist()
        facts['entries'] = len(infos)
        if len(infos) > MAX_ENTRIES:
            raise Refused('%d entries exceeds the classic zip limit (%d)'
                          % (len(infos), MAX_ENTRIES), 3, 'unsupported_container')
        names = [i.filename for i in infos]
        for item in infos:
            if (item.compress_size > MAX_U32 or item.file_size > MAX_U32
                    or item.header_offset > MAX_U32):
                facts['zip64'] = True
                raise Refused('entry %r needs zip64 fields; this writer does not '
                              'reproduce zip64 structures. Use scripts/repack.py.'
                              % item.filename, 3, 'unsupported_container')
            if item.flag_bits & 0x08:
                facts['data_descriptors'] += 1
            if item.is_dir():
                continue
            if item.compress_type == 0:
                off = entry_data_offset(path, item, fh)
                aligned = off % ALIGN == 0
                if needs_alignment(item.filename, 0, off):
                    facts['aligned_entries'].append(
                        {'name': item.filename, 'offset': off, 'aligned': aligned})
                if ALIGNED_SO_RE.match(item.filename):
                    facts['stored_so'].append(item.filename)
                if not aligned:
                    facts['unaligned_stored'].append(item.filename)
            if item.filename == 'resources.arsc':
                off = entry_data_offset(path, item, fh)
                facts['arsc'] = {'method': item.compress_type, 'offset': off,
                                 'stored': item.compress_type == 0,
                                 'aligned': off % ALIGN == 0, 'size': item.file_size}
            if item.filename == 'AndroidManifest.xml':
                try:
                    manifest = z.read(item.filename)
                except (zipfile.BadZipFile, RuntimeError, NotImplementedError) as exc:
                    rep.warn('AndroidManifest.xml could not be read (%s); the '
                             'extractNativeLibs state is unknown.' % exc)
                    manifest = b''
                facts['extract_native_libs'] = manifest_extract_native_libs(manifest)
        if 'AndroidManifest.xml' not in names:
            facts['extract_native_libs'] = 'absent'

    enl = facts['extract_native_libs']
    if enl in FALSE_VALUES:
        unsafe.append(
            'AndroidManifest.xml declares android:extractNativeLibs="false": the platform '
            'maps lib/*.so straight out of the archive, so the archive layout is part of '
            'the load contract (STORED bytes at the recorded offset).')
    if enl == 'unreadable':
        rep.warn('AndroidManifest.xml is present but its attributes could not be read; '
                 'the extractNativeLibs state is unknown and the rebuild is treated as '
                 'safe only because nothing said otherwise.')
    arsc = facts['arsc']
    if arsc is not None and not (arsc['stored'] and arsc['aligned']):
        unsafe.append(
            'resources.arsc is present and is not STORED + 4-byte aligned '
            '(method=%d, data offset 0x%x): Android R+ refuses to install that, and a '
            'container rebuild cannot make it compliant without re-compressing it.'
            % (arsc['method'], arsc['offset']))
    facts['unsafe'] = unsafe
    return facts


def describe_audit(facts, rep):
    rep.log('== container audit: %s' % facts['path'])
    rep.log('   entries=%d  archive comment=%d bytes  data descriptors=%d'
            % (facts['entries'], facts.get('archive_comment_bytes', 0),
               facts['data_descriptors']))
    enl = facts['extract_native_libs']
    label = {None: 'not declared', 'absent': 'AndroidManifest.xml absent'}.get(enl, enl)
    suffix = '' if enl in (None, 'true', 'false', 'absent') \
        else ' (unreadable manifest: treated as undeclared)'
    rep.log('   extractNativeLibs=%s%s' % (label, suffix))
    arsc = facts['arsc']
    if arsc is None:
        rep.log('   resources.arsc: absent')
    else:
        rep.log('   resources.arsc: %s, data offset 0x%x (%s), %d bytes'
                % ('STORED' if arsc['stored'] else 'COMPRESSED(method=%d)' % arsc['method'],
                   arsc['offset'], '4-byte aligned' if arsc['aligned'] else 'NOT aligned',
                   arsc['size']))
    for row in facts['aligned_entries']:
        if row['name'] in ALIGNED_STORED:
            continue                      # already reported on its own line above
        rep.log('   %s: data offset 0x%x (%s)'
                % (row['name'], row['offset'],
                   '4-byte aligned' if row['aligned'] else 'NOT aligned'))
    if facts['stored_so']:
        rep.log('   STORED lib/*.so: %s' % ', '.join(facts['stored_so']))
    if facts['unaligned_stored']:
        rep.log('   STORED entries that are NOT 4-byte aligned in the input: %s'
                % ', '.join(facts['unaligned_stored'][:8]) +
                ('' if len(facts['unaligned_stored']) <= 8
                 else ' (+%d more)' % (len(facts['unaligned_stored']) - 8)))
    for reason in facts['unsafe']:
        rep.log('   UNSAFE: %s' % reason)


# ---------------------------------------------------------------- bundle readers

class Item(object):
    """One source entry with everything needed to reproduce it byte-for-byte.

    The compressed stream of an untouched entry is *not* loaded into memory: its
    ``src_data_offset`` and ``csize`` are enough to copy it across, which keeps a rebuild
    of a few-hundred-megabyte APK at constant memory.
    """

    __slots__ = ('name', 'raw_name', 'local_extra', 'cd_extra', 'comment', 'method',
                 'flags', 'ver_need', 'time_word', 'date_word', 'crc', 'csize', 'usize',
                 'create_system', 'create_version', 'extract_version', 'internal_attr',
                 'external_attr', 'header_offset', 'src_data_offset', 'payload',
                 'is_dir', 'is_target')

    def __repr__(self):
        return '<Item %r method=%d>' % (self.name, self.method)


def _deflate_raw(data):
    """Raw deflate (no zlib wrapper), which is what a zip method-8 entry holds.

    zlib.compress() prepends a 2-byte zlib header. Some readers tolerate it, some do
    not, and the failure reads as a corrupt entry rather than as a bad compressor call.
    """
    c = zlib.compressobj(9, zlib.DEFLATED, -15)
    return c.compress(data) + c.flush()


def read_raw_entries(path, entry):
    """Every entry of `path` as an Item, with its original compressed stream in place."""
    items = []
    try:
        with zipfile.ZipFile(path, 'r') as z, open(path, 'rb') as fh:
            for info in z.infolist():
                ver_need, flags, method, time_w, date_w, nlen, elen = _local_layout(
                    fh, info.header_offset)
                fh.seek(info.header_offset + 30)
                raw_name = fh.read(nlen)
                local_extra = fh.read(elen)
                src_data_offset = fh.tell()
                if info.header_offset + 30 + nlen + elen + info.compress_size \
                        > os.path.getsize(path):
                    raise Refused('entry %r: data runs past the end of the file'
                                  % info.filename, 3, 'unsupported_container')
                it = Item()
                it.name = info.filename
                it.raw_name = raw_name
                it.local_extra = local_extra
                it.cd_extra = info.extra
                it.comment = info.comment
                it.method = info.compress_type
                it.flags = flags
                it.ver_need = ver_need
                it.time_word = time_w
                it.date_word = date_w
                it.crc = info.CRC
                it.csize = info.compress_size
                it.usize = info.file_size
                it.create_system = info.create_system
                it.create_version = info.create_version
                it.extract_version = info.extract_version
                it.internal_attr = info.internal_attr
                it.external_attr = info.external_attr
                it.header_offset = info.header_offset
                it.src_data_offset = src_data_offset
                it.payload = None
                it.is_dir = info.is_dir()
                it.is_target = (info.filename == entry)
                items.append(it)
    except zipfile.BadZipFile as exc:
        raise Refused('not a readable zip archive: %s' % exc, 3, 'unsupported_container')
    except OSError as exc:
        raise Refused('cannot read %s: %s' % (path, exc), 2, 'usage_error')
    if entry is not None and not any(i.is_target for i in items):
        so_names = [i.name for i in items if i.name.endswith('.so')]
        raise Refused('entry %r not in %s\navailable .so entries:\n  %s'
                      % (entry, path, '\n  '.join(so_names[:40]) or '  (none)'),
                      2, 'usage_error')
    return items


# ---------------------------------------------------------------- the writer

def _pad_extra(pad):
    """An appended private extra record contributing exactly `pad` bytes (mod 4).

    A zip extra area is a sequence of (id, 2-byte size, payload) records, so its
    smallest record is 4 bytes and a 1-3 byte pad cannot be expressed on its own. A
    record of length `4 + pad` shifts the data offset by `pad` (mod 4), which is exactly
    what is needed -- and it is *appended*, so the entry keeps its original extra bytes.
    """
    if pad <= 0:
        return b''
    return struct.pack('<HH', PAD_EXTRA_ID, pad) + b'\x00' * pad


def _copy_range(src_fh, dst, offset, size, chunk=1 << 20):
    """Copy `size` raw bytes from `offset` without loading them all at once."""
    src_fh.seek(offset)
    remaining = size
    while remaining > 0:
        block = src_fh.read(min(chunk, remaining))
        if not block:
            raise Refused('internal: short read while copying %d byte(s) at 0x%x'
                          % (size, offset), 4, 'internal_error')
        dst.write(block)
        remaining -= len(block)


def _sha_range(path, offset, size, chunk=1 << 20):
    """sha256 of a byte range, streamed."""
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        fh.seek(offset)
        remaining = size
        while remaining > 0:
            block = fh.read(min(chunk, remaining))
            if not block:
                break
            h.update(block)
            remaining -= len(block)
    return h.hexdigest()


def rebuild_apk(src_path, out_path, entry, new_data, rep):
    """Rewrite the archive keeping every entry's own metadata. Returns a report.

    Only `entry` may change. Every other entry's compressed stream is copied across
    verbatim, so its CRC and compress_size are identical by construction rather than by
    hope.
    """
    items = read_raw_entries(src_path, entry)
    comment, n_total, _disks = _read_eocd(src_path)
    if n_total != len(items):
        rep.warn('EOCD reports %d entries, the central directory lists %d'
                 % (n_total, len(items)))

    order = []
    tmp = out_path + '.tmp'
    with open(src_path, 'rb') as src_fh, open(tmp, 'wb') as out:
        for it in items:
            method = it.method
            crc, csize, usize = it.crc, it.csize, it.usize
            payload = None
            if it.is_target:
                if method == 0:
                    payload = new_data                     # STORE stays STORE
                elif method == 8:
                    payload = _deflate_raw(new_data)
                else:
                    raise Refused(
                        'entry %r uses compression method %d; this tool rewrites STORED '
                        '(0) and DEFLATED (8) entries only. Use scripts/repack.py.'
                        % (it.name, method), 3, 'unsupported_container')
                crc = zlib.crc32(new_data) & 0xFFFFFFFF
                csize = len(payload)
                usize = len(new_data)

            extra = it.local_extra
            pad = 0
            if needs_alignment(it.name, method, it.src_data_offset):
                head = out.tell() + 30 + len(it.raw_name) + len(extra)
                pad = (ALIGN - head % ALIGN) % ALIGN
                extra = extra + _pad_extra(pad)

            flags = it.flags & ~0x08                        # data descriptor is resolved
            local_offset = out.tell()
            out.write(struct.pack('<IHHHHHIIIHH', 0x04034B50, it.ver_need, flags, method,
                                  it.time_word, it.date_word, crc, csize, usize,
                                  len(it.raw_name), len(extra)))
            out.write(it.raw_name)
            out.write(extra)
            data_off = out.tell()
            if needs_alignment(it.name, method, it.src_data_offset) and data_off % ALIGN:
                raise Refused('internal: %s landed at 0x%x, not %d-byte aligned'
                              % (it.name, data_off, ALIGN), 4, 'internal_error')
            if out.tell() != local_offset + 30 + len(it.raw_name) + len(extra):
                raise Refused('internal: offset bookkeeping drift for %s' % it.name,
                              4, 'internal_error')
            if payload is None:
                _copy_range(src_fh, out, it.src_data_offset, it.csize)
            else:
                out.write(payload)
            order.append({'item': it, 'method': method, 'flags': flags, 'crc': crc,
                          'csize': csize, 'usize': usize, 'extra': extra,
                          'local_offset': local_offset, 'data_offset': data_off,
                          'pad': pad})

        cd_start = out.tell()
        for row in order:
            it = row['item']
            vm = (it.create_system << 8) | it.create_version
            out.write(struct.pack('<IHHHHHHIIIHHHHHII', 0x02014B50, vm,
                                  it.extract_version, row['flags'], row['method'],
                                  it.time_word, it.date_word, row['crc'], row['csize'],
                                  row['usize'], len(it.raw_name), len(it.cd_extra),
                                  len(it.comment), 0, it.internal_attr,
                                  it.external_attr, row['local_offset']))
            out.write(it.raw_name)
            out.write(it.cd_extra)
            out.write(it.comment)
        cd_size = out.tell() - cd_start
        out.write(struct.pack('<IHHHHIIH', 0x06054B50, 0, 0, len(order), len(order),
                              cd_size, cd_start, len(comment)))
        out.write(comment)

    os.replace(tmp, out_path)
    report = {'entries': len(order), 'order': order,
              'padded': [(r['item'].name, r['pad']) for r in order if r['pad']],
              'descripped': [r['item'].name for r in order
                             if r['item'].flags & 0x08]}
    return report


def verify_apk_rebuild(src_path, out_path, entry, report, rep):
    """Re-read the written file and check the contract it was supposed to keep.

    Nothing here is inferred from the writing loop: entry count, per-entry CRC and
    payload sha256, the metadata fields and the arsc storage/alignment gate are all read
    back from disk. A structural failure (unreadable output, entry count, untouched
    entry content) is an internal error; a storage/alignment failure is reported as a
    warning under --unsafe-rebuild and never silently accepted.
    """
    problems = []
    warnings = []
    untouched = [i for i in report['order'] if not i['item'].is_target]
    detailed = rep.verbose or len(report['order']) <= 32

    try:
        out_items = read_raw_entries(out_path, None)
    except Refused as exc:
        raise Refused('the written archive is not readable: %s' % exc, 4, 'internal_error')

    if len(out_items) != report['entries']:
        problems.append('entry count changed: %d -> %d'
                        % (report['entries'], len(out_items)))

    src_by_name = {i.name: i for i in (r['item'] for r in report['order'])}
    crc_ok = sha_ok = meta_ok = 0
    for got in out_items:
        want = src_by_name.get(got.name)
        if want is None:
            problems.append('unexpected entry %r in the output' % got.name)
            continue
        same_fields = (got.method == want.method
                       and got.external_attr == want.external_attr
                       and got.internal_attr == want.internal_attr
                       and got.create_system == want.create_system
                       and got.create_version == want.create_version
                       and got.extract_version == want.extract_version
                       and got.comment == want.comment
                       and got.cd_extra == want.cd_extra
                       and got.raw_name == want.raw_name
                       and (got.flags & ~0x08) == (want.flags & ~0x08)
                       and got.time_word == want.time_word
                       and got.date_word == want.date_word)
        out_sha = _sha_range(out_path, got.src_data_offset, got.csize)
        src_sha = _sha_range(src_path, want.src_data_offset, want.csize)
        if want.is_target:
            if out_sha == src_sha:
                warnings.append('%s: the rewritten entry came back byte-identical to the '
                                'input (the replacement may be the same string as the old '
                                'one)' % got.name)
            if detailed:
                rep.log('   CHANGED %-52s crc=%08x -> %08x  %d -> %d bytes  sha256=%s'
                        % (got.name, want.crc, got.crc, want.csize, got.csize, out_sha[:16]))
            if not same_fields:
                problems.append('rewritten entry %r: metadata changed' % got.name)
            continue
        crc_same = got.crc == want.crc and got.csize == want.csize \
            and got.usize == want.usize
        sha_same = out_sha == src_sha
        crc_ok += 1 if crc_same else 0
        sha_ok += 1 if sha_same else 0
        meta_ok += 1 if same_fields else 0
        if not crc_same:
            problems.append('untouched entry %r: CRC/size changed '
                            '(%08x/%d -> %08x/%d)'
                            % (got.name, want.crc, want.csize, got.crc, got.csize))
        if not sha_same:
            problems.append('untouched entry %r: payload sha256 changed' % got.name)
        if not same_fields:
            problems.append('untouched entry %r: metadata changed' % got.name)
        if detailed:
            rep.log('   OK      %-52s crc=%08x  sha256=%s%s'
                    % (got.name, got.crc, out_sha[:16],
                       '' if same_fields else '  METADATA-DIFF'))

    n_untouched = len(untouched)
    rep.log('== rebuild self-check')
    rep.log('   entry count          : %d -> %d   %s'
            % (report['entries'], len(out_items),
               'identical' if report['entries'] == len(out_items) else 'DIFFERENT'))
    rep.log('   untouched entries    : %d/%d CRC+size identical, %d/%d payload sha256 '
            'identical, %d/%d metadata identical'
            % (crc_ok, n_untouched, sha_ok, n_untouched, meta_ok, n_untouched))
    if report['descripped']:
        rep.log('   data descriptors      : resolved into the local header for %s'
                % ', '.join(report['descripped']))
    for name, pad in report['padded']:
        rep.log('   alignment padding     : %s += %d byte(s) in a private local extra '
                'record' % (name, pad))

    with zipfile.ZipFile(out_path, 'r') as z, open(out_path, 'rb') as fh:
        in_align = []
        for info in z.infolist():
            want = src_by_name.get(info.filename)
            src_off = want.src_data_offset if want is not None else 0
            if not needs_alignment(info.filename, info.compress_type, src_off):
                continue
            off = entry_data_offset(out_path, info, fh)
            if info.compress_type != 0:
                warnings.append('%s is COMPRESSED (method=%d) in the output, but an '
                                'uncompressed entry is what the layout requires'
                                % (info.filename, info.compress_type))
                rep.log('   %-20s : COMPRESSED (method=%d) FAIL'
                        % (info.filename, info.compress_type))
                continue
            in_align.append((info.filename, off, info.header_offset))
            if off % ALIGN:
                warnings.append('%s data offset 0x%x is not 4-byte aligned'
                                % (info.filename, off))
                rep.log('   %-20s : STORED but data offset 0x%x is NOT aligned FAIL'
                        % (info.filename, off))
        for name, off, hdr in in_align:
            rep.log('   %-20s : STORED, data offset 0x%x (4-byte aligned), '
                    'header_offset 0x%x OK' % (name, off, hdr))
        if in_align:
            rep.log('   alignment gate       : the field that must be 4-byte aligned is '
                    'the ENTRY DATA offset (what zipalign -c and apksigner check); the '
                    'local header offset is not part of that gate')
        else:
            rep.log('   (no entry requires 4-byte alignment in this archive)')

    for w in warnings:
        rep.warn(w)
    if problems:
        for p in problems:
            rep.log('   FAIL %s' % p)
        raise Refused('the rebuilt archive failed its own self-check (%d problem(s)); the '
                      'output was removed rather than reported as good' % len(problems),
                      4, 'internal_error')
    return {'entries': report['entries'], 'untouched': n_untouched,
            'crc_identical': crc_ok, 'sha256_identical': sha_ok,
            'metadata_identical': meta_ok, 'padded': report['padded'],
            'data_descriptors_resolved': report['descripped'], 'failures': [],
            'warnings': warnings}


# ---------------------------------------------------------------- containers

def load_target(path: str, entry):
    """The bytes to patch: a bare file, or one entry read out of an APK."""
    if path.lower().endswith('.apk') or path.lower().endswith('.zip'):
        if not entry:
            raise Refused('--entry is required when patching an APK '
                          '(e.g. --entry lib/arm64-v8a/libfoo.so)', 2)
        try:
            with zipfile.ZipFile(path, 'r') as z:
                names = z.namelist()
                if entry not in names:
                    cands = [n for n in names if n.endswith('.so')]
                    raise Refused('entry %r not in %s\navailable .so entries:\n  %s'
                                  % (entry, path, '\n  '.join(cands[:40]) or '  (none)'),
                                  2)
                if entry.endswith('/'):
                    raise Refused('entry %r is a directory' % entry, 2)
                return z.read(entry), 'apk'
        except zipfile.BadZipFile as exc:
            raise Refused('not a readable zip archive: %s' % exc, 3,
                          'unsupported_container')
        except OSError as exc:
            raise Refused('cannot read %s: %s' % (path, exc), 2)
    try:
        with open(path, 'rb') as f:
            return f.read(), 'file'
    except OSError as exc:
        raise Refused('cannot read %s: %s' % (path, exc), 2)


def write_target(rep, out_path: str, kind: str, src_path: str, entry,
                 new_data: bytes, unsafe):
    """Write the patched artifact. A bare file is copied; an APK is rebuilt."""
    if kind == 'file':
        with open(out_path, 'wb') as f:
            f.write(new_data)
        rep.log('  wrote %d bytes (bare file, container untouched)' % len(new_data))
        return None

    audit = audit_apk_for_rebuild(src_path, rep)
    describe_audit(audit, rep)
    if audit['unsafe'] and not unsafe:
        rep.log('')
        rep.log('REFUSED: this package cannot be rebuilt safely by this tool (see the '
                'UNSAFE line(s) above). Nothing was written.')
        rep.log('  * If you want a resource-safe repack, use scripts/repack.py: it owns '
                'the STORED+aligned writer and the signing pipeline.')
        rep.log('  * If you have already confirmed the package is safe to rewrite, '
                're-run with --unsafe-rebuild to proceed anyway.')
        raise Refused('unsafe APK rebuild refused by default', 1,
                      'refused_unsafe_rebuild', {'audit': audit})
    if audit['unsafe'] and unsafe:
        for reason in audit['unsafe']:
            rep.warn('--unsafe-rebuild accepted: %s' % reason)

    report = rebuild_apk(src_path, out_path, entry, new_data, rep)
    verified = verify_apk_rebuild(src_path, out_path, entry, report, rep)
    rep.log('  rebuilt %s (%d entries, order and metadata preserved)'
            % (out_path, report['entries']))
    return {'audit': audit, 'verify': verified}


# ---------------------------------------------------------------- main

EXIT_CODES = {'patched': 0, 'found': 0, 'not_found': 1,
              'refused_unsafe_rebuild': 1, 'usage_error': 2,
              'unsupported_container': 3, 'internal_error': 4}


def _status_for(token):
    if token in ('patched', 'found'):
        return 'ok'
    if token == 'not_found':
        return 'negative'
    if token == 'refused_unsafe_rebuild':
        return 'refused'
    if token == 'usage_error':
        return 'usage_error'
    if token == 'unsupported_container':
        return 'capability_missing'
    return 'internal_error'


def main():
    ap = argparse.ArgumentParser(
        description='In-place same-length rewrite of a string constant (library-load '
                    'redirection), including APK rebuilds that preserve zip metadata.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='examples:\n'
               '  so_constpatch.py libfoo.so --find checkername\n'
               '  so_constpatch.py libfoo.so --replace checkername=android -o libfoo.patched.so\n'
               '  so_constpatch.py app.apk --entry lib/arm64-v8a/libfoo.so '
               '--replace checkername=android -o app.patched.apk\n'
               '\n'
               'an APK rebuild is refused by default when the manifest declares\n'
               'android:extractNativeLibs="false", or when resources.arsc is not\n'
               'STORED + 4-byte aligned. Use scripts/repack.py for a resource-safe\n'
               'repack, or pass --unsafe-rebuild to override after checking the audit.\n'
               '\n'
               'exit codes: 0 ok / 1 negative finding or refused rebuild / 2 usage or\n'
               'input error / 3 this tool cannot do it / 4 internal error (no output)\n')
    ap.add_argument('target', help='.so file or .apk')
    ap.add_argument('--entry', default=None, help='zip entry path when target is an APK')
    ap.add_argument('--find', default=None, metavar='STR', help='report occurrences and exit')
    ap.add_argument('--replace', default=None, metavar='OLD=NEW',
                    help='same-length rewrite of OLD with NEW')
    ap.add_argument('-o', '--out', default=None, help='output path (required for --replace)')
    ap.add_argument('--section-aware', action='store_true',
                    help='only patch hits inside known constant-pool sections')
    ap.add_argument('--allow-nonisolated', action='store_true',
                    help='permit patching a substring of a longer identifier (dangerous)')
    ap.add_argument('--force', action='store_true', help='patch every eligible occurrence')
    ap.add_argument('--unsafe-rebuild', action='store_true',
                    help='proceed with an APK rebuild even when the audit says the '
                         'package cannot survive it (see the UNSAFE lines)')
    ap.add_argument('--json', action='store_true',
                    help='print one JSON object plus the final RESULT line')
    ap.add_argument('--verbose', action='store_true',
                    help='print a per-entry self-check line instead of a summary')
    args = ap.parse_args()

    rep = Reporter(args.json, args.verbose)
    token = 'internal_error'
    exit_code = 4
    extra = {}
    next_action = None
    try:
        data, kind = load_target(args.target, args.entry)
        rep.log('loaded %s (%s, %d bytes)\n' % (args.target, kind, len(data)))

        if args.find:
            token = do_find(rep, data, args.find.encode())
            exit_code = EXIT_CODES[token]
            if token == 'not_found':
                next_action = ('check the name: --find matches raw bytes, so try a shorter '
                               'substring of the constant.')
            return finish(rep, args, token, exit_code, extra, next_action)

        if not args.replace:
            ap.error('one of --find or --replace is required')

        if '=' not in args.replace:
            ap.error('--replace expects OLD=NEW')
        old_s, new_s = args.replace.split('=', 1)
        old, new = old_s.encode(), new_s.encode()

        if not args.out and kind == 'file':
            args.out = args.target + '.patched'
        if not args.out:
            ap.error('-o/--out is required when patching an APK')
        if os.path.abspath(args.out) == os.path.abspath(args.target):
            ap.error('refusing to overwrite the input in place; choose a different -o')
        if args.unsafe_rebuild and kind == 'file':
            rep.warn('--unsafe-rebuild only affects an APK rebuild; a bare .so is copied '
                     'as-is.')

        patched, applied = do_replace(rep, data, old, new, args.section_aware,
                                      args.allow_nonisolated, args.force)
        extra['patch'] = {'occurrences': len(applied),
                          'offsets': ['0x%x' % off for off, _b, _a in applied]}
        result = write_target(rep, args.out, kind, args.target, args.entry, patched,
                              args.unsafe_rebuild)
        if result:
            extra.update(result)
        rep.log('\nwrote %s' % args.out)
        token = 'patched'
        exit_code = 0
        next_action = ('re-sign, then verify the loader\'s log tag count is 0 on a cold '
                       'start (see references/code-virtualization-and-custom-linkers.md).')
        if kind == 'apk':
            next_action = ('sign the rebuilt APK (scripts/repack.py --no-sign writes the '
                           'same container; apksigner/zipalign applies the signature), '
                           'then verify on a cold start.')
    except Refused as exc:
        token = exc.token
        exit_code = exc.exit_code
        extra.update(exc.data)
        if token == 'refused_unsafe_rebuild':
            next_action = ('use scripts/repack.py for a resource-safe repack, or re-run '
                           'with --unsafe-rebuild.')
        elif token == 'usage_error':
            next_action = 'fix the invocation (see --help).'
        elif token == 'unsupported_container':
            next_action = ('use scripts/repack.py, or rewrite the container with a tool '
                           'that handles zip64 and non-deflate entries.')
        rep.log('\n%s' % exc)
        if exit_code == 4:
            out = args.out or ''
            for candidate in (out, out + '.tmp'):
                if candidate and os.path.exists(candidate):
                    try:
                        os.remove(candidate)
                        rep.log('removed %s' % candidate)
                    except OSError:
                        pass
    except SystemExit:
        raise
    return finish(rep, args, token, exit_code, extra, next_action)


def finish(rep, args, token, exit_code, extra, next_action):
    """Emit the machine-readable answer: JSON (when asked) plus the RESULT token."""
    if args.json:
        payload = {'status': _status_for(token), 'exit_code': exit_code,
                   'capability': CAPABILITY, 'tool': TOOL, 'result': token,
                   'target': args.target, 'entry': args.entry, 'out': args.out,
                   'evidence': rep.evidence, 'warnings': rep.warnings}
        for key, val in extra.items():
            payload[key] = val
        if next_action:
            payload['next_action'] = next_action
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        if next_action:
            print('next: %s' % next_action)
    print('RESULT=%s' % token)
    return exit_code


if __name__ == '__main__':
    sys.exit(main())
