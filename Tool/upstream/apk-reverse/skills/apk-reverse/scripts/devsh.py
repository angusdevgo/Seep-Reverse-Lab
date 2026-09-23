#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Quoting-safe ADB helper.

Why this exists: if you build device commands inside a host shell, the host expands
`$`, `|`, `>`, and quotes *before* adb sees them. Symptoms are host-side errors that
look like device failures -- "Could not find a part of the path", "no closing quote",
"Missing type name after '['", unexpanded variables. Windows PowerShell is the worst
offender (it also eats `$var:`, `[^"...`, `$(...)`).

Calling adb from Python with an argument list avoids all of it.

Configuration (first match wins):
  1. CLI flags: --serial / --adb
  2. env: ADB_SERIAL / ADB_PATH
  3. defaults below

Usage
-----
  python devsh.py sh  "pm list packages | grep myapp"      # as the shell user
  python devsh.py su  "pm grant <pkg> android.permission.X"
  python devsh.py sh  "dumpsys window | grep mCurrentFocus"
  python devsh.py pull /data/local/tmp/x.apk ./x.apk
  python devsh.py push ./x.apk /data/local/tmp/x.apk
  python devsh.py dev                                       # list devices

`su` wraps the command in `su -c "..."`; internal double quotes are escaped.
"""
import argparse
import os
import subprocess
import sys

try:
    import device_shell as _shell          # same directory as this script
except ImportError:                        # run from the repository root instead
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import device_shell as _shell

DEFAULT_ADB = 'adb'
DEFAULT_SERIAL = None


def resolve():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument('--adb')
    ap.add_argument('--serial')
    known, _ = ap.parse_known_args()
    adb = known.adb or os.environ.get('ADB_PATH') or DEFAULT_ADB
    serial = known.serial or os.environ.get('ADB_SERIAL') or DEFAULT_SERIAL
    return adb, serial


def run(adb, serial, args, timeout=300):
    cmd = [adb]
    if serial:
        cmd += ['-s', serial]
    cmd += args
    r = subprocess.run(cmd, capture_output=True, text=True, errors='replace', timeout=timeout)
    out = r.stdout or ''
    if (r.stderr or '').strip():
        out += '\n[stderr]\n' + r.stderr
    return r.returncode, out


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    adb, serial = resolve()
    argv = [a for a in sys.argv[1:] if not a.startswith('--adb=') and not a.startswith('--serial=')]
    # strip flag/value pairs
    cleaned = []
    skip = False
    for a in argv:
        if skip:
            skip = False
            continue
        if a in ('--adb', '--serial'):
            skip = True
            continue
        cleaned.append(a)
    argv = cleaned
    if len(argv) < 2 and argv and argv[0] not in ('dev',):
        print(__doc__)
        return 2

    mode = argv[0]

    try:
        if mode == 'dev':
            rc, out = run(adb, None, ['devices', '-l'])
        elif mode in ('sh', 'shell'):
            rc, out = run(adb, serial, ['shell', argv[1]])
        elif mode == 'su':
            # POSIX single-quote quoting, via the shared module. The previous form escaped only double
            # quotes, so `;`, `$( )` and backticks still reached the device shell as syntax -- and this
            # helper sits directly under an agent's hands. See scripts/device_shell.py.
            rc, out = run(adb, serial, ['shell', _shell.su_wrap([argv[1]])])
        elif mode == 'suf':  # read a device text file
            # `suf` interpolates a path and a byte count into a device command, so both are validated:
            # a path with a space or a metacharacter is refused here rather than mangled on the device.
            path = _shell.validate_device_path(argv[1])
            size = argv[2] if len(argv) > 2 else '6000'
            if not size.isdigit():
                print('suf: size must be a decimal byte count, got %r' % size, file=sys.stderr)
                return 2
            rc, out = run(adb, serial, ['shell', _shell.su_wrap(['head', '-c', size, path])])
        elif mode == 'pull':
            rc, out = run(adb, serial, ['pull', argv[1], argv[2]])
        elif mode == 'push':
            rc, out = run(adb, serial, ['push', argv[1], argv[2]])
        else:
            print(__doc__)
            return 2
    except _shell.Refused as exc:
        # A malformed device value is a usage error (2): distinguishable by a caller from "the device
        # said no" (1) and from a defect in this tool (4). Never a traceback.
        print('refused: %s' % exc, file=sys.stderr)
        print('RESULT=refused')
        return 2

    sys.stdout.write(out)
    return 0 if rc == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
