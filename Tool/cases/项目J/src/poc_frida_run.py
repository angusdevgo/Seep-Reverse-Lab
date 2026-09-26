#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
PoC (方案B) 启动器 —— Frida 注入版卡密授权旁路
用法: python poc_frida_run.py [目标exe路径]
"""
import frida, sys, os, time

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = sys.argv[1] if len(sys.argv) > 1 else (os.path.join(HERE, 'target_patched.exe')
                                                if os.path.isfile(os.path.join(HERE, 'target_patched.exe'))
                                                else os.path.join(HERE, 'target.exe'))


def main():
    if not os.path.isfile(TARGET):
        print('[!] target not found:', TARGET)
        return 1
    print('[*] spawning', TARGET)
    pid = frida.spawn([TARGET], cwd=os.path.dirname(os.path.abspath(TARGET)))
    sess = frida.attach(pid)
    frida.resume(pid)

    src = open(os.path.join(HERE, 'poc_frida_bypass.js'), encoding='utf-8').read()
    sc = sess.create_script(src)
    sc.on('message', lambda m, d: print(m.get('payload', m), flush=True))
    sc.load()
    print('[*] PID =', pid, '—— 请在登录框输入任意卡密并点击「登陆」')
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == '__main__':
    sys.exit(main())
