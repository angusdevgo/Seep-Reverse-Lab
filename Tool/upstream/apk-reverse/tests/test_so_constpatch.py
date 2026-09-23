#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Regression tests for `skills/apk-reverse/scripts/so_constpatch.py`.

What is being locked down
-------------------------
The script rewrites one zip entry inside an APK. The first implementation rebuilt the
whole archive through `zipfile.ZipInfo(filename, date_time)` and re-deflated everything,
which dropped `extra`, `external_attr` and `create_system`, and could push
`resources.arsc` off its STORED/4-byte-aligned layout -- an APK the installer refuses
with `[-124]`, and one that may not load at all when the manifest asks for
`extractNativeLibs="false"`.

These tests run the CLI the way a caller does (subprocess, exit code, RESULT token, JSON)
and re-read the written archive to check the contract, so they cannot pass by trusting
the writer's own bookkeeping. No device, no Android toolchain, no network.

The fixtures in `tests/fixtures/apk/` are committed; `tests/fixtures/make_fixture_apk.py`
regenerates them and is exercised too, so a fixture that stops carrying the metadata
under test fails here rather than silently weakening the suite.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import struct
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SCRIPT = REPO / 'skills' / 'apk-reverse' / 'scripts' / 'so_constpatch.py'
SCRIPTS_DIR = SCRIPT.parent
FIXTURES = HERE / 'fixtures' / 'apk'
MAKE_FIXTURES = HERE / 'fixtures' / 'make_fixture_apk.py'

APKHUNAN = b'apkhuan'
ANDROID = b'android'
SO_ENTRY = 'lib/arm64-v8a/libfoo.so'
STORE_ENTRY = 'lib/arm64-v8a/libbar.so'
X64_SO_ENTRY = 'lib/x86_64/libfoo.so'
SERVICES_ENTRIES = (
    'META-INF/services/com.example.Provider',
    'META-INF/services/kotlinx.coroutines.internal.MainDispatcherFactory',
)
UTF8_ENTRY = 'res/raw/\u6d4b\u8bd5.bin'


# ------------------------------------------------------------------ helpers

def run_cli(*args, cwd=None):
    return subprocess.run([sys.executable, str(SCRIPT)] + [str(a) for a in args],
                          capture_output=True, text=True, encoding='utf-8',
                          errors='replace', cwd=cwd)


def token_of(proc):
    for line in reversed(proc.stdout.splitlines()):
        if line.startswith('RESULT='):
            return line.split('=', 1)[1].strip()
    return None


def json_of(proc):
    lines = proc.stdout.strip().splitlines()
    assert lines and lines[-1].startswith('RESULT='), proc.stdout
    return json.loads('\n'.join(lines[:-1]))


def load_named(name, path):
    """Import a module by path, so the tests do not depend on sys.path state."""
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_module():
    return load_named('so_constpatch_under_test', SCRIPT)


def local_extra(path, name):
    """The local-header extra field, which is what alignment lives in."""
    with zipfile.ZipFile(path) as z, open(path, 'rb') as fh:
        info = z.getinfo(name)
        fh.seek(info.header_offset)
        head = fh.read(30)
        nlen, elen = struct.unpack_from('<HH', head, 26)
        return fh.read(nlen + elen)[nlen:]


def data_offset(path, name):
    with zipfile.ZipFile(path) as z, open(path, 'rb') as fh:
        info = z.getinfo(name)
        fh.seek(info.header_offset)
        head = fh.read(30)
        nlen, elen = struct.unpack_from('<HH', head, 26)
        return info.header_offset + 30 + nlen + elen


def zip_dump(path):
    """Everything a rebuild must preserve, keyed by entry name."""
    out = {}
    with zipfile.ZipFile(path) as z, open(path, 'rb') as fh:
        for info in z.infolist():
            fh.seek(info.header_offset)
            head = fh.read(30)
            nlen, elen = struct.unpack_from('<HH', head, 26)
            raw_name = fh.read(nlen)
            local_extra_bytes = fh.read(elen)
            out[info.filename] = {
                'info': info,
                'raw_name': raw_name,
                'local_extra': local_extra_bytes,
                'method': info.compress_type,
                'extra': info.extra,
                'external_attr': info.external_attr,
                'internal_attr': info.internal_attr,
                'create_system': info.create_system,
                'comment': info.comment,
                'flags': info.flag_bits,
                'date_time': info.date_time,
                'crc': info.CRC,
                'compress_size': info.compress_size,
                'file_size': info.file_size,
                'data_offset': info.header_offset + 30 + nlen + elen,
                'sha256': hashlib.sha256(z.read(info.filename)).hexdigest(),
            }
    return out


def fixture(name):
    p = FIXTURES / name
    assert p.is_file(), 'missing fixture %s; run tests/fixtures/make_fixture_apk.py' % p
    return p


def so_bytes(apk, entry=SO_ENTRY):
    with zipfile.ZipFile(apk) as z:
        return z.read(entry)


# ------------------------------------------------------------------ fixtures themselves

def test_fixtures_carry_the_metadata_under_test():
    """A fixture that lost its `extra`/`external_attr` would make the suite vacuous."""
    for name in ('plain.apk', 'arsc_aligned.apk', 'noextract.apk', 'services.apk'):
        dump = zip_dump(fixture(name))
        assert dump, name
        for entry, row in dump.items():
            assert row['extra'], '%s!%s has no extra field to preserve' % (name, entry)
        assert any(row['external_attr'] for row in dump.values()), \
            '%s has no non-zero external_attr to preserve' % name
    # And one entry that must keep a zero external_attr / create_system=0 too.
    zeroed = zip_dump(fixture('services.apk'))[UTF8_ENTRY]
    assert zeroed['external_attr'] == 0 and zeroed['create_system'] == 0

    arsc = zip_dump(fixture('arsc_aligned.apk'))['resources.arsc']
    assert arsc['method'] == 0
    assert arsc['data_offset'] % 4 == 0

    noextract = zip_dump(fixture('noextract.apk'))
    assert noextract[SO_ENTRY]['method'] == 0
    assert noextract[SO_ENTRY]['data_offset'] % 4 == 0


def test_fixture_manifest_is_binary_axml_with_the_declaration():
    """The manifest is real AXML, and the script's reader agrees with repack.py's.

    Two independent readers on the same bytes: if either drifts, this fails instead of
    one tool quietly disagreeing with the other about `extractNativeLibs`.
    """
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        import repack
    finally:
        sys.path.pop(0)

    with zipfile.ZipFile(fixture('noextract.apk')) as z:
        blob = z.read('AndroidManifest.xml')
    assert blob[:2] == b'\x03\x00', 'not a binary AXML document'

    attrs = repack.axml_root_attrs(blob)
    assert attrs['extractNativeLibs'] == 'false'
    assert attrs['package'] == 'com.example.noextract'

    mod = load_module()
    assert mod.axml_root_attributes(blob)['extractNativeLibs'] == 'false'
    assert mod.manifest_extract_native_libs(blob) == 'false'

    with zipfile.ZipFile(fixture('plain.apk')) as z:
        assert mod.manifest_extract_native_libs(z.read('AndroidManifest.xml')) is None
    assert mod.manifest_extract_native_libs(
        b'<manifest xmlns:android="x" android:extractNativeLibs="false">') == 'false'
    assert mod.manifest_extract_native_libs(b'</bad>') == 'unreadable'


def test_alignment_predicate_matches_a_real_abi_directory():
    """`lib/<abi>/x.so` has two slashes; a `[^/]+` pattern would match nothing."""
    mod = load_module()
    for name in ('lib/arm64-v8a/libfoo.so', 'lib/x86/libfoo.so', 'lib/x86_64/a.so'):
        assert mod.needs_alignment(name, 0, 8) is True, name
    # `resources.arsc` is mandatory whatever its input offset is.
    assert mod.needs_alignment('resources.arsc', 0, 10) is True
    assert mod.needs_alignment('resources.arsc', 8, 10) is True
    # An uncompressed .so is mandatory too (extractNativeLibs=false maps it in place).
    assert mod.needs_alignment('lib/arm64-v8a/libfoo.so', 0, 10) is True
    # Any other STORED entry keeps the alignment it arrived with, and is not re-laid out.
    assert mod.needs_alignment('assets/blob.bin', 0, 8) is True
    assert mod.needs_alignment('assets/blob.bin', 0, 10) is False
    # Deflated entries have no alignment requirement.
    assert mod.needs_alignment('classes.dex', 8, 8) is False
    assert mod.needs_alignment('lib/arm64-v8a/libfoo.so', 8, 8) is False


def test_fixture_generator_reproduces_the_committed_archives(tmp_path):
    proc = subprocess.run([sys.executable, str(MAKE_FIXTURES), '--out', str(tmp_path)],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    for name in ('plain.apk', 'arsc_aligned.apk', 'noextract.apk', 'services.apk'):
        regenerated = tmp_path / name
        assert regenerated.is_file()
        assert list(zip_dump(regenerated)) == list(zip_dump(fixture(name))), name
        # Structure must match even if a different zlib produced different bytes.
        assert os.path.getsize(regenerated) < 8192, 'fixtures must stay tiny'


# ------------------------------------------------------------------ the bare-.so path

def test_bare_so_rewrite_is_byte_exact(tmp_path):
    """The `.so` path predates the container work and must not move a single byte.

    The expected output is constructed here from the input, so this is not a
    self-consistency check: patching `apkhuan` at its reported offset is the whole
    contract. The sha256 of this same output was measured identical under the
    pre-change script (see tools/_work/zip-safety-EVIDENCE.md).
    """
    src = so_bytes(fixture('plain.apk'))
    so_path = tmp_path / 'libfoo.so'
    so_path.write_bytes(src)
    out = tmp_path / 'libfoo.patched.so'

    proc = run_cli(so_path, '--replace', 'apkhuan=android', '-o', out)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert token_of(proc) == 'patched'

    got = out.read_bytes()
    expected = bytearray(src)
    expected[0x41:0x41 + len(APKHUNAN)] = ANDROID
    assert got == bytes(expected)
    assert len(got) == len(src)
    assert hashlib.sha256(got).hexdigest() == \
        hashlib.sha256(bytes(expected)).hexdigest()


def test_bare_so_reports_the_bytes_actually_changed(tmp_path):
    """`N byte(s) actually changed`: the window is 7, the changed bytes are 6."""
    so_path = tmp_path / 'libfoo.so'
    so_path.write_bytes(so_bytes(fixture('plain.apk')))
    proc = run_cli(so_path, '--replace', 'apkhuan=android', '-o', tmp_path / 'o.so')
    assert '6 byte(s) actually changed' in proc.stdout, proc.stdout


# ------------------------------------------------------------------ APK rebuild: metadata

def test_deflated_entry_rebuild_preserves_every_other_entry(tmp_path):
    src = fixture('plain.apk')
    out = tmp_path / 'plain.patched.apk'
    before = zip_dump(src)

    proc = run_cli(src, '--entry', SO_ENTRY, '--replace', 'apkhuan=android', '-o', out,
                   '--verbose')
    assert proc.returncode == 0, proc.stdout + proc.stderr
    after = zip_dump(out)

    assert list(after) == list(before), 'entry order changed'
    assert len(after) == len(before)

    changed = after[SO_ENTRY]
    assert changed['sha256'] != before[SO_ENTRY]['sha256'], 'the patched entry did not change'
    assert changed['method'] == 8

    for name, row in before.items():
        if name == SO_ENTRY:
            continue
        got = after[name]
        assert got['sha256'] == row['sha256'], '%s payload changed' % name
        assert got['crc'] == row['crc'], '%s CRC changed' % name
        assert got['compress_size'] == row['compress_size'], '%s compress_size changed' % name
        assert got['extra'] == row['extra'], '%s central-directory extra changed' % name
        assert got['local_extra'] == row['local_extra'], '%s local extra changed' % name
        assert got['external_attr'] == row['external_attr'], '%s external_attr changed' % name
        assert got['internal_attr'] == row['internal_attr']
        assert got['create_system'] == row['create_system']
        assert got['comment'] == row['comment']
        assert got['date_time'] == row['date_time']
        assert got['flags'] == row['flags']


def test_store_stays_store_and_is_not_recompressed(tmp_path):
    """A STORED entry must come back STORED with the same layout, not re-deflated."""
    src = fixture('arsc_aligned.apk')
    out = tmp_path / 'arsc_store.patched.apk'
    before = zip_dump(src)

    proc = run_cli(src, '--entry', STORE_ENTRY, '--replace', 'apkhuan=android', '-o', out)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    after = zip_dump(out)

    got, want = after[STORE_ENTRY], before[STORE_ENTRY]
    assert want['method'] == 0
    assert got['method'] == 0, 'a STORED entry was re-compressed'
    assert got['compress_size'] == want['compress_size'] == want['file_size']
    assert got['file_size'] == want['file_size']
    assert got['sha256'] != want['sha256']

    # Nothing moved, so alignment needed no new padding and every extra field is
    # byte-identical -- the strongest form of "metadata preserved".
    assert got['data_offset'] == want['data_offset']
    assert got['extra'] == want['extra']
    assert got['local_extra'] == want['local_extra']
    for name, row in before.items():
        assert after[name]['data_offset'] == row['data_offset'], name
        assert after[name]['local_extra'] == row['local_extra'], name


def test_deflated_change_keeps_arsc_and_stored_so_aligned(tmp_path):
    """The case the old writer broke: a size change before `resources.arsc`."""
    src = fixture('arsc_aligned.apk')
    out = tmp_path / 'arsc_deflate.patched.apk'
    before = zip_dump(src)

    proc = run_cli(src, '--entry', SO_ENTRY, '--replace', 'apkhuan=android', '-o', out)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    after = zip_dump(out)

    assert after[SO_ENTRY]['compress_size'] != before[SO_ENTRY]['compress_size'], \
        'this fixture must make the patched entry change size, or padding is not exercised'

    for name, row in before.items():
        got = after[name]
        if row['method'] != 0:
            continue
        # Every uncompressed entry that was aligned stays aligned (zipalign semantics),
        # and `resources.arsc` is aligned even if it had not been.
        assert got['data_offset'] % 4 == 0, '%s lost 4-byte alignment' % name
        assert got['method'] == 0, '%s is no longer STORED' % name
        if name != SO_ENTRY:
            # The entry itself is untouched...
            assert got['sha256'] == row['sha256'], name
            assert got['crc'] == row['crc'], name
            assert got['extra'] == row['extra'], name
            assert got['external_attr'] == row['external_attr'], name
            # ...and its original local extra survives as a prefix of the new one:
            # padding is appended, never substituted.
            assert got['local_extra'].startswith(row['local_extra']), name

    # `libbar.so` is STORED and sits before `resources.arsc`, so the size change shifts
    # it by an unaligned amount: the writer must restore its alignment with a pad record.
    bar_pad = len(after[STORE_ENTRY]['local_extra']) \
        - len(before[STORE_ENTRY]['local_extra'])
    assert bar_pad > 0, 'a shifted STORED .so was left unaligned without a pad record'
    pad = bar_pad - 4
    assert 1 <= pad <= 3, 'the appended record claims a pad of %d bytes' % pad
    assert bar_pad % 4 == pad, 'the appended record does not land on the boundary'
    appended = after[STORE_ENTRY]['local_extra'][
        len(before[STORE_ENTRY]['local_extra']):]
    assert struct.unpack_from('<H', appended, 2)[0] == pad, 'malformed extra record'
    assert 'alignment padding' in proc.stdout
    assert 'resources.arsc' in proc.stdout
    assert '4-byte aligned' in proc.stdout


def test_an_unaligned_stored_entry_is_not_silently_relaid(tmp_path):
    """This tool preserves alignment; it does not re-lay-out an archive it was not asked
    to fix. A STORED entry that arrived unaligned stays that way, with its extra and
    offsets untouched -- silently rewriting it would be the same class of change the
    STORED/alignment work exists to prevent."""
    fx = load_named('make_fixture_apk_under_test', MAKE_FIXTURES)
    src = tmp_path / 'handmade.apk'
    entries = [
        fx.Entry('classes.dex', fx.make_dex(), method=8),
        fx.Entry('lib/arm64-v8a/libfoo.so', fx.make_elf(), method=8),
        # STORED, deliberately NOT aligned (the generator aligns only when asked).
        fx.Entry('AndroidManifest.xml', fx.make_axml('com.example.unaligned'), method=0),
    ]
    fx.write_apk(str(src), entries)
    before = zip_dump(src)
    assert before['AndroidManifest.xml']['data_offset'] % 4 != 0, \
        'the handmade archive is supposed to be unaligned here'

    out = tmp_path / 'handmade.patched.apk'
    proc = run_cli(src, '--entry', SO_ENTRY, '--replace', 'apkhuan=android', '-o', out)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    after = zip_dump(out)

    assert after[SO_ENTRY]['compress_size'] != before[SO_ENTRY]['compress_size']
    got = after['AndroidManifest.xml']
    assert got['data_offset'] % 4 != 0, 'an unaligned STORED entry was silently moved'
    assert got['local_extra'] == before['AndroidManifest.xml']['local_extra']
    assert got['sha256'] == before['AndroidManifest.xml']['sha256']
    assert got['extra'] == before['AndroidManifest.xml']['extra']
    assert 'NOT 4-byte aligned in the input' in proc.stdout


def test_self_check_is_printed_and_reads_back_the_written_file(tmp_path):
    src = fixture('arsc_aligned.apk')
    out = tmp_path / 'selfcheck.apk'
    proc = run_cli(src, '--entry', STORE_ENTRY, '--replace', 'apkhuan=android', '-o', out)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    text = proc.stdout
    assert 'rebuild self-check' in text
    assert 'entry count' in text and 'identical' in text
    assert 'CRC+size identical' in text
    assert 'sha256 identical' in text
    assert 'header_offset' in text


def test_services_and_utf8_entries_are_untouched(tmp_path):
    src = fixture('services.apk')
    out = tmp_path / 'services.patched.apk'
    before = zip_dump(src)

    proc = run_cli(src, '--entry', X64_SO_ENTRY, '--replace', 'apkhuan=android', '-o', out,
                   '--verbose')
    assert proc.returncode == 0, proc.stdout + proc.stderr
    after = zip_dump(out)

    for name in SERVICES_ENTRIES + (UTF8_ENTRY, 'AndroidManifest.xml'):
        assert after[name]['sha256'] == before[name]['sha256'], '%s changed' % name
        assert after[name]['extra'] == before[name]['extra'], '%s extra changed' % name
        assert after[name]['external_attr'] == before[name]['external_attr']
        assert after[name]['create_system'] == before[name]['create_system']
        assert after[name]['comment'] == before[name]['comment']

    utf8 = after[UTF8_ENTRY]
    assert utf8['info'].filename == UTF8_ENTRY
    assert utf8['flags'] & 0x800, 'the UTF-8 name flag was dropped'
    assert utf8['create_system'] == 0
    assert utf8['internal_attr'] == 1
    assert utf8['comment'] == b'fixture comment'

    with zipfile.ZipFile(src) as a, zipfile.ZipFile(out) as b:
        assert a.comment == b.comment == b'fixture-archive-comment'


# ------------------------------------------------------------------ the refusal gate

def test_extract_native_libs_false_is_refused_by_default(tmp_path):
    src = fixture('noextract.apk')
    out = tmp_path / 'noextract.patched.apk'
    proc = run_cli(src, '--entry', SO_ENTRY, '--replace', 'apkhuan=android', '-o', out)

    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert token_of(proc) == 'refused_unsafe_rebuild'
    assert not out.exists(), 'a refused rebuild must write nothing'
    assert 'REFUSED' in proc.stdout
    assert 'extractNativeLibs' in proc.stdout
    assert 'scripts/repack.py' in proc.stdout, 'the refusal must name the right tool'
    assert '--unsafe-rebuild' in proc.stdout


def test_unsafe_rebuild_is_explicit_and_reported(tmp_path):
    src = fixture('noextract.apk')
    out = tmp_path / 'noextract.unsafe.apk'
    proc = run_cli(src, '--entry', SO_ENTRY, '--replace', 'apkhuan=android', '-o', out,
                   '--unsafe-rebuild')
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert token_of(proc) == 'patched'
    assert 'WARNING: --unsafe-rebuild accepted' in proc.stdout

    after = zip_dump(out)
    assert after[SO_ENTRY]['method'] == 0
    assert after[SO_ENTRY]['data_offset'] % 4 == 0
    assert after['resources.arsc']['method'] == 0
    assert after['resources.arsc']['data_offset'] % 4 == 0


def test_a_compressed_arsc_is_refused(tmp_path):
    """An arsc that is not STORED+aligned cannot be made compliant by this writer."""
    mod = load_module()
    broken = tmp_path / 'compressed_arsc.apk'
    with zipfile.ZipFile(fixture('arsc_aligned.apk')) as src_z:
        plan = [(i.filename, src_z.read(i.filename), i.compress_type, i.extra,
                 i.external_attr, i.create_system, i.date_time)
                for i in src_z.infolist()]
    with zipfile.ZipFile(broken, 'w') as dst:
        for name, blob, method, extra, eattr, csys, dt in plan:
            zi = zipfile.ZipInfo(name, date_time=dt)
            zi.compress_type = zipfile.ZIP_DEFLATED if name == 'resources.arsc' else method
            zi.extra = extra
            zi.external_attr = eattr
            zi.create_system = csys
            dst.writestr(zi, blob)

    out = tmp_path / 'x.apk'
    proc = run_cli(broken, '--entry', STORE_ENTRY, '--replace', 'apkhuan=android',
                   '-o', out)
    assert proc.returncode == 1, proc.stdout + proc.stderr
    assert token_of(proc) == 'refused_unsafe_rebuild'
    assert 'resources.arsc' in proc.stdout
    assert not out.exists()

    # The audit reads the storage state without needing a rebuild at all.
    facts = mod.audit_apk_for_rebuild(str(broken), mod.Reporter(as_json=True))
    assert facts['arsc']['stored'] is False
    assert facts['unsafe']


# ------------------------------------------------------------------ find / usage errors

def test_find_reports_isolated_and_non_isolated(tmp_path):
    src = fixture('plain.apk')
    proc = run_cli(src, '--entry', SO_ENTRY, '--find', 'apkhuan')
    assert proc.returncode == 0
    assert token_of(proc) == 'found'
    assert 'isolated=True' in proc.stdout and 'isolated=False' in proc.stdout
    assert 'isolated (safe to rewrite in place): 1 / 2' in proc.stdout


def test_find_without_hits_is_a_negative_finding():
    proc = run_cli(fixture('plain.apk'), '--entry', SO_ENTRY, '--find', 'nosuchthing')
    assert proc.returncode == 1
    assert token_of(proc) == 'not_found'


def test_equal_length_is_mandatory():
    proc = run_cli(fixture('plain.apk'), '--entry', SO_ENTRY, '--replace', 'apkhuan=and',
                   '-o', 'out.apk')
    assert proc.returncode == 2
    assert 'Equal length is mandatory' in proc.stdout


def test_non_isolated_and_multi_hits_need_an_explicit_flag():
    # The decoy `libapkhuanx.so` makes a second, non-isolated hit.
    proc = run_cli(fixture('plain.apk'), '--entry', SO_ENTRY, '--replace', 'apkhuan=android',
                   '-o', 'out.apk', '--allow-nonisolated')
    assert proc.returncode == 2
    assert '--force' in proc.stdout
    assert token_of(proc) == 'usage_error'


def test_missing_entry_and_missing_out_are_usage_errors(tmp_path):
    p = run_cli(fixture('plain.apk'), '--entry', 'lib/arm64-v8a/nope.so',
                '--replace', 'apkhuan=android', '-o', tmp_path / 'x.apk')
    assert p.returncode == 2
    assert 'available .so entries' in p.stdout

    p = run_cli(fixture('plain.apk'), '--replace', 'apkhuan=android')
    assert p.returncode == 2

    p = run_cli(fixture('plain.apk'), '--entry', SO_ENTRY, '--replace', 'apkhuan=android')
    assert p.returncode == 2, 'patching an APK without -o must be rejected'

    p = run_cli(fixture('plain.apk'), '--entry', SO_ENTRY, '--replace', 'apkhuan=android',
                '-o', fixture('plain.apk'))
    assert p.returncode == 2, 'overwriting the input in place must be rejected'


# ------------------------------------------------------------------ json contract

def test_json_contract_on_success(tmp_path):
    out = tmp_path / 'j.apk'
    proc = run_cli(fixture('arsc_aligned.apk'), '--entry', STORE_ENTRY, '--replace',
                   'apkhuan=android', '-o', out, '--json')
    assert proc.returncode == 0, proc.stdout + proc.stderr
    payload = json_of(proc)
    assert payload['status'] == 'ok'
    assert payload['exit_code'] == 0
    assert payload['capability'] == 'native_const_patch'
    assert payload['result'] == 'patched'
    for key in ('evidence', 'warnings', 'next_action'):
        assert key in payload
    assert isinstance(payload['evidence'], list) and payload['evidence']
    assert payload['verify']['entries'] == payload['verify']['untouched'] + 1
    assert payload['verify']['sha256_identical'] == payload['verify']['untouched']
    assert payload['audit']['arsc']['stored'] is True
    assert payload['audit']['unsafe'] == []


def test_json_contract_on_refusal(tmp_path):
    proc = run_cli(fixture('noextract.apk'), '--entry', SO_ENTRY, '--replace',
                   'apkhuan=android', '-o', tmp_path / 'r.apk', '--json')
    assert proc.returncode == 1
    payload = json_of(proc)
    assert payload['status'] == 'refused'
    assert payload['exit_code'] == 1
    assert payload['result'] == 'refused_unsafe_rebuild'
    assert payload['audit']['extract_native_libs'] == 'false'
    assert payload['audit']['unsafe']
    assert 'repack.py' in payload['next_action']


def test_json_contract_on_negative_find():
    proc = run_cli(fixture('plain.apk'), '--entry', SO_ENTRY, '--find', 'nope', '--json')
    assert proc.returncode == 1
    payload = json_of(proc)
    assert payload['status'] == 'negative'
    assert payload['result'] == 'not_found'
    assert payload['exit_code'] == 1


# ------------------------------------------------------------------ streaming archives

def test_data_descriptors_are_resolved_into_the_local_header(tmp_path):
    """An entry written while streaming carries flag bit 3 and no CRC in its local
    header. The rebuild resolves it from the central directory, so the output is
    readable by tools that never look at the central directory."""
    class _Sink(object):
        """A file object without seek/tell, which is what makes zipfile stream."""

        def __init__(self, fh):
            self._fh = fh

        def write(self, data):
            return self._fh.write(data)

        def flush(self):
            self._fh.flush()

        def close(self):
            self._fh.close()

    streaming = tmp_path / 'streaming.apk'
    with zipfile.ZipFile(fixture('plain.apk')) as zin:
        with open(streaming, 'wb') as raw:
            with zipfile.ZipFile(_Sink(raw), 'w', zipfile.ZIP_DEFLATED) as zout:
                for info in zin.infolist():
                    zi = zipfile.ZipInfo(info.filename, date_time=info.date_time)
                    zi.compress_type = info.compress_type
                    with zout.open(zi, 'w') as fh:
                        fh.write(zin.read(info.filename))

    before = zip_dump(streaming)
    assert all(row['flags'] & 0x08 for row in before.values()), \
        'this fixture must carry data descriptors, or the branch is not covered'
    assert all(row['local_extra'] == b'' or True for row in before.values())

    out = tmp_path / 'streaming.patched.apk'
    proc = run_cli(streaming, '--entry', SO_ENTRY, '--replace', 'apkhuan=android',
                   '-o', out)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    after = zip_dump(out)

    assert 'data descriptors' in proc.stdout
    for name, row in before.items():
        got = after[name]
        assert not (got['flags'] & 0x08), '%s still declares a data descriptor' % name
        if name != SO_ENTRY:
            assert got['sha256'] == row['sha256']
            assert got['crc'] == row['crc']
    with zipfile.ZipFile(out) as z:
        assert z.testzip() is None


# ------------------------------------------------------------------ internal invariants

def test_padding_record_is_four_byte_expressible():
    """A zip extra record is (id, size, payload) and its minimum length is 4 bytes."""
    mod = load_module()
    assert mod._pad_extra(0) == b''
    for pad in (1, 2, 3):
        rec = mod._pad_extra(pad)
        assert len(rec) == 4 + pad
        assert len(rec) % 4 == pad
        assert struct.unpack_from('<H', rec, 2)[0] == pad


def test_eocd_and_unsupported_containers_are_reported(tmp_path):
    mod = load_module()
    junk = tmp_path / 'not-a-zip.apk'
    junk.write_bytes(b'not a zip at all')
    with pytest.raises(mod.Refused) as exc:
        mod.audit_apk_for_rebuild(str(junk), mod.Reporter(as_json=True))
    assert exc.value.exit_code == 3
    assert exc.value.token == 'unsupported_container'

    proc = run_cli(junk, '--entry', 'anything', '--replace', 'a=b', '-o', tmp_path / 'o.apk')
    assert proc.returncode == 3
    assert token_of(proc) == 'unsupported_container'
