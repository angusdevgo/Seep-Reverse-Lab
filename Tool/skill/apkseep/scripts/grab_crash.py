#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Capture a crash stack when the app's crash-reporter SDK is hiding it.

Problem this solves
-------------------
Many apps install a global uncaught-exception handler (友盟/UCrash, Bugly, Firebase
Crashlytics in some configs). The Java stack then never reaches `logcat` -- you only
see something like:

    W/UCrash.Java: uncaughtException time: <ts>

...and the process dies. Without a stack you are guessing.

Three ways to get it, in order of reliability:
  1. Frida: hook Thread.setDefaultUncaughtExceptionHandler (use references/dynamic-frida.md)
  2. Race the reporter's own log file (this script): it writes a file under the app's
     data dir, then zips, uploads, and deletes it. Poll fast and copy on sight.
  3. Use a build with the reporter disabled.

Usage
-----
  python grab_crash.py --pkg com.example.app --activity .MainActivity
  python grab_crash.py --pkg com.example.app --activity .MainActivity \
      --scan-dir /data/data/com.example.app --wait 25

Notes
-----
* `--scan-dir` defaults to /data/data/<pkg>; the script searches a few levels deep for
  newly appeared *.log / *.txt / *.stacktrace files, so you do not have to know which
  SDK is installed.
* The watcher loop self-terminates after ~80 s, so nothing is left running on device.
* Requires root (the app's data dir is private).
"""
import argparse
import subprocess
import sys
import time

CAPTURE = '/data/local/tmp/_skill_crash_capture.log'


def adb(args, serial=None, timeout=180):
    cmd = ['adb']
    if serial:
        cmd += ['-s', serial]
    cmd += args
    r = subprocess.run(cmd, capture_output=True, text=True, errors='replace', timeout=timeout)
    return (r.stdout or '') + (('\n[stderr]\n' + r.stderr) if (r.stderr or '').strip() else '')


def su(cmd, serial=None):
    return adb(['shell', 'su -c "%s"' % cmd.replace('"', '\\"')], serial)


def main():
    ap = argparse.ArgumentParser(add_help=True)
    ap.add_argument('--pkg', required=True)
    ap.add_argument('--activity', required=True)
    ap.add_argument('--serial')
    ap.add_argument('--scan-dir')
    ap.add_argument('--wait', type=int, default=25)
    a = ap.parse_args()

    scan = a.scan_dir or ('/data/data/%s' % a.pkg)
    s = a.serial

    # On-device watcher: copy any *.log/*.txt that appears under the app dir.
    watch = (
        "i=0; while [ $i -lt 400 ]; do "
        "  find {d} -maxdepth 5 -type f \\( -name '*.log' -o -name '*.txt' -o -name '*.stacktrace' "
        "     -o -name '*.crash' \\) -newermt '-3 minutes' -exec cp -f {{}} {c} \\; 2>/dev/null; "
        "  i=$((i+1)); sleep 0.2; "
        "done"
    ).format(d=scan, c=CAPTURE)

    su('am force-stop %s' % a.pkg, s)
    su('rm -f %s' % CAPTURE, s)
    print('[grab] arming on-device watcher over %s' % scan)
    subprocess.Popen(['adb'] + (['-s', s] if s else []) +
                     ['shell', "su -c '%s'" % watch],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)

    print('[grab] starting app')
    print(adb(['shell', 'am start -n %s/%s' % (a.pkg, a.activity)], s))
    time.sleep(a.wait)

    pid = adb(['shell', 'pidof %s' % a.pkg], s).strip()
    print('[grab] pid: %s' % (pid or '(dead -> likely crashed)'))

    print('[grab] ==== captured file ====')
    out = su('head -c 6000 %s' % CAPTURE, s)
    if 'No such file' in out or not out.strip():
        print('(nothing captured)')
        print('[hint] the reporter may have deleted it faster than 0.2 s, or it writes '
              'outside --scan-dir. Use the Frida approach instead.')
    else:
        print(out)
    return 0


if __name__ == '__main__':
    sys.exit(main())
