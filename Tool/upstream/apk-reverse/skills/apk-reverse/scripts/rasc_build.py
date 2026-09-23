#!/usr/bin/env python3
"""Build and verify `rasc`, the Rust re-implementation of ASC.

Why this script exists: `rasc` has no prebuilt artifact anywhere -- no GitHub release asset, no
crate, and `cargo install rasc` fetches an unrelated maths parser. Adopting it therefore means
building it, and a build that only one machine has ever performed is a build nobody else can
reproduce. This wraps the whole path: toolchain check, clone, build, and the smoke tests that decide
whether the binary is usable rather than merely present.

What it is for, and where it stops: `rasc` answers the same *location* questions as the Python
`droidasc` -- which classes exist, where a string/type/method/field is referenced, what the manifest
says, and the decompiled source of one class -- several times faster, with a Rust DEX decompiler
(droidsaw) behind `getclass`. It is not a replacement for a full decompiler on every class shape;
see `skills/apk-reverse/references/rasc-and-droidsaw.md` for the measured boundary.

Usage:
    python rasc_build.py --check                 # is a usable rasc present? (fast)
    python rasc_build.py --build                 # clone + build into a local tools/ tree
    python rasc_build.py --verify <apk>          # compare against droidasc on a real APK
    python rasc_build.py --json

Requires, to build: git, and a Rust toolchain (rustup). On Windows the GNU host toolchain needs a
64-bit MinGW-w64 gcc on PATH -- the 32-bit MinGW that ships with some setups cannot link a 64-bit
binary and fails with "64-bit mode not compiled in".
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def _repo_root():
    """Walk up from this script to the repository root, or None when there is not one.

    The script lives at `<repo>/skills/apk-reverse/scripts/`, so `tools/_work` is three levels up --
    but a skill installed by `npx skills add` has no repository around it at all. Resolving
    `tools/_work` relative to the *script* directory (the first version of this did) looks for
    `skills/apk-reverse/scripts/tools/_work`, which never exists, and then reports a working binary
    as missing.
    """
    cur = HERE
    for _ in range(6):
        if os.path.isdir(os.path.join(cur, 'tools', '_work')) or \
                os.path.isdir(os.path.join(cur, '.git')):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    return None


ROOT = _repo_root()
# Falls back to a user-level directory when the skill runs outside a checkout, so the tool is not
# pinned to a layout the caller may not have.
DEFAULT_WORK = (os.path.join(ROOT, 'tools', '_work') if ROOT
                else os.path.join(os.path.expanduser('~'), '.apk-reverse', 'work'))

# A cargo/rustc installed to a non-default CARGO_HOME is invisible to a non-interactive PATH, which
# is how this was first run: the toolchain was at <work>/rust/cargo/bin and the check said "missing".
TOOLCHAIN_HINTS = (
    os.path.join(DEFAULT_WORK, 'rust', 'cargo', 'bin'),
    os.path.expanduser('~/.cargo/bin'),
)
for _hint in TOOLCHAIN_HINTS:
    if os.path.isdir(_hint) and _hint not in os.environ.get('PATH', ''):
        os.environ['PATH'] = _hint + os.pathsep + os.environ.get('PATH', '')

REPO = 'https://github.com/MG1937/ASC.git'
BRANCH = 'rust'
RASC_HINTS = (
    os.environ.get('RASC', ''),
    os.path.join(DEFAULT_WORK, 'rust', 'target', 'release', 'rasc'),
    os.path.join(DEFAULT_WORK, 'rust', 'target', 'release', 'rasc.exe'),
    'rasc',
)

EXIT_OK, EXIT_FAILED, EXIT_USAGE, EXIT_CAPABILITY, EXIT_INTERNAL = 0, 1, 2, 3, 4


def find_rasc():
    for hint in RASC_HINTS:
        if not hint:
            continue
        if os.path.isabs(hint):
            if os.path.isfile(hint):
                return hint
            continue
        found = shutil.which(hint)
        if found:
            return found
    return None


def rasc_version(path):
    try:
        out = subprocess.run([path, '--version'], capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        return None, str(exc)
    if out.returncode != 0:
        return None, (out.stderr or out.stdout).strip()[:200]
    return (out.stdout or '').strip(), ''


def toolchain():
    """What this machine has that a build needs, reported rather than assumed."""
    report = {}
    for name in ('git', 'cargo', 'rustc', 'cc', 'gcc'):
        report[name] = shutil.which(name)
    if report['gcc']:
        try:
            out = subprocess.run([report['gcc'], '-dumpmachine'], capture_output=True, text=True,
                                 timeout=60)
            report['gcc_target'] = (out.stdout or '').strip()
        except (OSError, subprocess.SubprocessError):
            report['gcc_target'] = 'unknown'
    return report


def build(workdir, jobs=None):
    repo = os.path.join(workdir, 'rasc')
    if not os.path.isdir(os.path.join(repo, '.git')):
        os.makedirs(workdir, exist_ok=True)
        cmd = ['git', 'clone', '--branch', BRANCH, '--depth', '1', REPO, repo]
        print('+ %s' % ' '.join(cmd))
        rc = subprocess.run(cmd).returncode
        if rc != 0:
            print('clone failed (rc=%d)' % rc, file=sys.stderr)
            return None
    env = dict(os.environ)
    env.setdefault('CARGO_TARGET_DIR', os.path.join(workdir, 'rust', 'target'))
    cmd = ['cargo', 'build', '--release'] + (['--jobs', str(jobs)] if jobs else [])
    print('+ %s   (in %s)' % (' '.join(cmd), repo))
    t0 = time.perf_counter()
    rc = subprocess.run(cmd, cwd=repo, env=env).returncode
    print('build finished in %.1f s (rc=%d)' % (time.perf_counter() - t0, rc))
    if rc != 0:
        return None
    for name in ('rasc', 'rasc.exe'):
        candidate = os.path.join(env['CARGO_TARGET_DIR'], 'release', name)
        if os.path.isfile(candidate):
            return candidate
    return None


def smoke(binary, apk):
    """Ask the same question of rasc and of the Python `droidasc`, and compare the answers.

    Presence is not capability: the check that matters is whether the class-definition set agrees on
    a real archive. A build that runs but answers differently is a build that must not be adopted,
    which is why this lives next to the build rather than in a note.
    """
    if not os.path.isfile(apk):
        return {'result': 'usage', 'detail': 'apk not found: %s' % apk}
    ours = subprocess.run([binary, 'classes', apk], capture_output=True, timeout=1800)
    if ours.returncode != 0:
        return {'result': 'failed', 'detail': 'rasc classes rc=%d %s'
                % (ours.returncode, ours.stderr.decode('utf-8', 'replace')[:200])}
    py = shutil.which('droidasc')
    if not py:
        n = len(re.findall(rb'L[^;|\s]+;', ours.stdout))
        return {'result': 'partial', 'rasc_classes': n,
                'detail': 'droidasc not on PATH, so only the rasc side was run'}
    env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUTF8='1')
    theirs = subprocess.run([py, 'listclass', apk], capture_output=True, timeout=1800, env=env)
    if theirs.returncode != 0:
        return {'result': 'partial', 'detail': 'droidasc rc=%d (its output is not UTF-8 safe on a '
                                               'non-UTF-8 console without PYTHONUTF8=1)'
                % theirs.returncode}

    def descriptors(blob):
        out = set()
        for line in blob.decode('utf-8', 'replace').splitlines():
            for tok in re.split(r'[\s|]+', line.strip()):
                if re.fullmatch(r'L[^;]+;', tok):
                    out.add(tok)
                    break
        return out

    a, b = descriptors(ours.stdout), descriptors(theirs.stdout)
    return {'result': 'ok' if a == b else 'failed',
            'rasc_classes': len(a), 'droidasc_classes': len(b),
            'only_rasc': len(a - b), 'only_droidasc': len(b - a)}


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog='rasc_build.py',
        description='Build and verify rasc, the Rust ASC re-implementation.',
        epilog='exit codes: 0 ok, 1 verification failed, 2 usage, 3 a required capability is '
               'missing, 4 internal error\n'
               'examples:\n'
               '  rasc_build.py --check\n'
               '  rasc_build.py --build --work tools/_work\n'
               '  rasc_build.py --verify tools/_work/apks/sample.apk\n')
    ap.add_argument('--check', action='store_true', help='report whether a usable rasc is present')
    ap.add_argument('--build', action='store_true', help='clone and build rasc')
    ap.add_argument('--verify', metavar='APK', help='compare rasc against droidasc on this APK')
    ap.add_argument('--work', default=DEFAULT_WORK, help='where to clone and build (default: %s)'
                    % DEFAULT_WORK)
    ap.add_argument('--jobs', type=int, default=None, help='parallel build jobs')
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args(argv)

    if not (args.check or args.build or args.verify):
        ap.print_help()
        print('RESULT=usage')
        return EXIT_USAGE

    payload = {'toolchain': {k: v for k, v in toolchain().items()}, 'work': args.work}
    binary = find_rasc()
    if binary:
        version, err = rasc_version(binary)
        payload['rasc'] = {'path': binary, 'version': version, 'error': err or None}
    else:
        payload['rasc'] = None

    if args.build:
        missing = [k for k in ('git', 'cargo', 'rustc') if not payload['toolchain'][k]]
        if missing:
            payload['result'] = 'capability_missing'
            payload['next_action'] = ('install Rust (rustup) and git; missing: %s' % ', '.join(missing))
            if args.json:
                print(json.dumps(payload, indent=2))
            print('cannot build: missing %s' % ', '.join(missing), file=sys.stderr)
            print('RESULT=capability_missing')
            return EXIT_CAPABILITY
        gcc_target = payload['toolchain'].get('gcc_target') or ''
        built = build(args.work, args.jobs)
        if not built:
            payload['result'] = 'build_failed'
            # The hint is only useful when the linker target is the 32-bit one, which is the
            # failure this actually hit: name the target rather than printing a generic list.
            payload['next_action'] = (
                'read the cargo output above; the GNU host toolchain needs a 64-bit MinGW-w64 '
                'gcc and this machine reports %r' % (gcc_target or 'no gcc on PATH') if
                'mingw32' in gcc_target or not gcc_target else
                'read the cargo output above')
            if args.json:
                print(json.dumps(payload, indent=2))
            print('RESULT=build_failed')
            return EXIT_FAILED
        binary = built
        version, _ = rasc_version(binary)
        payload['rasc'] = {'path': built, 'version': version, 'error': None}

    if args.verify:
        if not binary:
            payload['result'] = 'capability_missing'
            payload['next_action'] = 'run --build first, or set RASC to an existing binary'
            if args.json:
                print(json.dumps(payload, indent=2))
            print('RESULT=capability_missing')
            return EXIT_CAPABILITY
        payload['verify'] = smoke(binary, args.verify)
        payload['result'] = payload['verify']['result']

    if args.check and 'result' not in payload:
        payload['result'] = 'ok' if binary else 'capability_missing'
        if not binary:
            payload['next_action'] = 'run --build (needs git + rustup), or set RASC=<path>'

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        tc = payload['toolchain']
        print('toolchain : git=%s cargo=%s rustc=%s gcc=%s%s'
              % (tc.get('git') or '-', tc.get('cargo') or '-', tc.get('rustc') or '-',
                 tc.get('gcc') or '-',
                 ('(%s)' % tc['gcc_target']) if tc.get('gcc_target') else ''))
        print('rasc      : %s' % (('%s  %s' % (payload['rasc']['path'], payload['rasc']['version']))
                                  if payload['rasc'] else 'not found'))
        if 'verify' in payload:
            print('verify    : %s' % payload['verify'])
        print('result    : %s' % payload['result'])
        if payload.get('next_action'):
            print('next      : %s' % payload['next_action'])

    print('RESULT=%s' % payload['result'])
    return {'ok': EXIT_OK, 'build_failed': EXIT_FAILED, 'failed': EXIT_FAILED,
            'usage': EXIT_USAGE, 'capability_missing': EXIT_CAPABILITY,
            'partial': EXIT_OK}.get(payload['result'], EXIT_INTERNAL)


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except (ValueError, OSError):
            pass
    sys.exit(main())
