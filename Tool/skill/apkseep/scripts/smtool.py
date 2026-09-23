#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""baksmali / smali wrapper.

Assembling and disassembling dex requires smali + baksmali + several runtime jars on
the classpath. Getting the set wrong produces a bare `ClassNotFoundException` that
looks like a broken tool rather than a missing jar, so this wrapper centralizes it.

Two ways to configure the classpath, in priority order:
  1. --cp "jar1;jar2"          (explicit, per invocation)
  2. APK_REVERSE_SMALI_CP env var
  3. a `smali_cp.txt` next to this script (one jar path per line, '#' comments ok)

Required jars: smali, baksmali, dexlib2, util, antlr-runtime, stringtemplate,
jcommander, guava.

Usage
-----
  python smtool.py d <in.dex> <out_dir>      # disassemble to a smali tree
  python smtool.py a <in_tree> <out.dex>     # assemble a smali tree back to dex
  python smtool.py check                     # print the resolved classpath and exit

Notes
-----
* Always pass the tree directory as its own argument; do not rely on the shell.
* Call java from Python rather than from a shell: PowerShell in particular mangles
  arguments containing ';' or '$', which silently drops jars from the classpath.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CP_FILE = os.path.join(HERE, 'smali_cp.txt')

JAR_NAMES = [
    'smali-2.5.2.jar',
    'antlr-runtime-3.5.2.jar',
    'stringtemplate-3.2.1.jar',
    'baksmali-2.5.2.jar',
    'util-2.5.2.jar',
    'jcommander-1.64.jar',
    'guava-27.1-android.jar',
    'dexlib2-2.5.2.jar',
]


def resolve_cp(explicit=None):
    if explicit:
        return explicit
    env = os.environ.get('APK_REVERSE_SMALI_CP')
    if env:
        return env
    if os.path.isfile(CP_FILE):
        parts = []
        for line in open(CP_FILE, encoding='utf-8'):
            line = line.strip()
            if line and not line.startswith('#'):
                parts.append(line)
        if parts:
            return os.pathsep.join(parts)
    # last resort: look for the jars in a 'tools' dir next to this script
    cand = [os.path.join(HERE, 'tools', n) for n in JAR_NAMES]
    if all(os.path.isfile(c) for c in cand):
        return os.pathsep.join(cand)
    return None


def run(cp, main_class, args):
    cmd = ['java', '-cp', cp, main_class] + args
    r = subprocess.run(cmd, capture_output=True, text=True, errors='replace')
    out = (r.stdout or '') + (('\n[stderr]\n' + r.stderr) if (r.stderr or '').strip() else '')
    return r.returncode, out


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    explicit = None
    argv = sys.argv[1:]
    if '--cp' in argv:
        i = argv.index('--cp')
        explicit = argv[i + 1]
        del argv[i:i + 2]

    cp = resolve_cp(explicit)
    if not cp:
        print('[FAIL] no classpath. Provide --cp, set APK_REVERSE_SMALI_CP, '
              'or create smali_cp.txt next to this script.')
        return 1

    cmd = argv[0]
    if cmd == 'check':
        print('classpath: %s' % cp)
        for j in cp.split(os.pathsep):
            print('  %s  %s' % ('OK ' if os.path.isfile(j) else 'MISSING', j))
        return 0

    if cmd in ('d', 'dis', 'disassemble'):
        if len(argv) < 3:
            print('usage: smtool.py d <in.dex> <out_dir>')
            return 2
        rc, out = run(cp, 'org.jf.baksmali.Main', ['d', argv[1], '-o', argv[2]])
    elif cmd in ('a', 'asm', 'assemble'):
        if len(argv) < 3:
            print('usage: smtool.py a <in_tree> <out.dex>')
            return 2
        rc, out = run(cp, 'org.jf.smali.Main', ['a', argv[1], '-o', argv[2]])
    else:
        print(__doc__)
        return 2

    print(out.strip()[-4000:])
    print('rc=%d' % rc)
    return 0 if rc == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
