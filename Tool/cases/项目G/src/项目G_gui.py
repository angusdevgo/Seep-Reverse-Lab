#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""项目GActivate GUI — 项目G <目标版本> 一键激活工具（窗口版）。

复用 项目G_activate（core）的 apply/revert/check/guard 逻辑，提供单窗口流程：
  目录列表 -> 一键激活 -> 防回退守卫 -> 还原正版。

命令行参数模式（守卫用，不弹窗）:
  项目GActivate.exe --silent --fix    登录时静默检查/修复
  项目GActivate.exe --guard           注册守卫（静默）
  项目GActivate.exe --unguard         移除守卫（静默）
  项目GActivate.exe --smoke           GUI 冒烟自检（构造窗口后立即退出，exit 0）
"""
import contextlib
import io
import queue
import sys
import threading
import webbrowser
import tkinter as tk
from tkinter import ttk, scrolledtext

try:
    import 项目G_activate as core
except ImportError:
    sys.path.insert(0, __file__.rsplit('\\', 1)[0] if '\\' in __file__ else '.')
    import 项目G_activate as core

STATE_CN = {'patched': '已激活 (patched)', 'original': '原版 (original)', 'unknown': '未知 (unknown)'}


def detect_state(path):
    """读文件前 5 字节判断状态（与 core 一致）。"""
    try:
        with open(path, 'rb') as f:
            data = f.read()
        cur5 = data[core.PATCH_OFFSET:core.PATCH_OFFSET + 5]
        if cur5 == core.PATCH_BYTES:
            return 'patched'
        if cur5 == core.ORIG_BYTES:
            return 'original'
    except OSError:
        pass
    return 'unknown'


class 项目GActivateApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('项目GActivate — 项目G <目标版本> 一键激活工具')
        self.geometry('720x560')
        self.minsize(640, 480)
        self._busy = False
        self._result = None
        self._done = False
        self._build_widgets()
        self.refresh_dirs()
        self.after(200, self.refresh_dirs)

    # ---------- UI ----------
    def _build_widgets(self):
        # 标题 + 购买链接
        head = ttk.Frame(self, padding=(12, 8))
        head.pack(fill='x')
        ttk.Label(head, text='项目G <目标版本> 一键激活工具', font=('Segoe UI', 13, 'bold')).pack(anchor='w')
        ttk.Label(head, text='keygen 不可行：激活数据由官方服务器签发（详见 docs/）', foreground='#666').pack(anchor='w')
        links = ttk.Frame(head)
        links.pack(anchor='w', pady=(4, 0))
        ttk.Label(links, text='支持正版：', foreground='#b00').pack(side='left')
        for text, url in (
                ('官方站点 https://1218.io', core.OFFICIAL_SITE),
                ('购买·中文', core.BUY_URL_CN),
                ('购买·EN', core.BUY_URL_EN)):
            b = ttk.Button(links, text=text, command=lambda u=url: webbrowser.open(u))
            b.pack(side='left', padx=(0, 6))

        # 目录列表
        mid = ttk.Frame(self, padding=(12, 4))
        mid.pack(fill='both', expand=True)
        bar = ttk.Frame(mid)
        bar.pack(fill='x')
        ttk.Label(bar, text='项目G 目录（自动定位）：').pack(side='left')
        ttk.Button(bar, text='刷新', command=self.refresh_dirs).pack(side='right')
        self.dirbox = tk.Listbox(mid, height=6, selectmode='extended')
        self.dirbox.pack(fill='x', pady=(4, 0))
        self.dirbox.bind('<Double-Button-1>', lambda e: self.check_selected())

        # 日志
        ttk.Label(mid, text='日志：').pack(anchor='w', pady=(8, 0))
        self.log = scrolledtext.ScrolledText(mid, height=12, state='disabled', font=('Consolas', 9))
        self.log.pack(fill='both', expand=True)

        # 按钮
        btns = ttk.Frame(self, padding=(12, 8))
        btns.pack(fill='x')
        self.btn_activate = ttk.Button(btns, text='一键激活', command=self.activate_selected)
        self.btn_activate.pack(side='left', padx=(0, 6))
        self.btn_guard = ttk.Button(btns, text='启用防回退守卫', command=self.toggle_guard)
        self.btn_guard.pack(side='left', padx=(0, 6))
        self.btn_check = ttk.Button(btns, text='检查状态', command=self.check_selected)
        self.btn_check.pack(side='left', padx=(0, 6))
        self.btn_revert = ttk.Button(btns, text='还原正版', command=self.revert_selected)
        self.btn_revert.pack(side='left', padx=(0, 6))
        ttk.Button(btns, text='打开购买页', command=lambda: webbrowser.open(core.BUY_URL_CN)).pack(side='right')

    # ---------- 目录/状态 ----------
    def refresh_dirs(self):
        dirs = core.try_locate_项目G_dirs()
        self.dirbox.delete(0, 'end')
        for d in dirs:
            exe = d + '\\项目G.exe'
            st = detect_state(exe)
            self.dirbox.insert('end', '[%s] %s' % (STATE_CN.get(st, st), d))
        self._update_guard_button()

    def _update_guard_button(self):
        st = core.guard_status()
        self.btn_guard.config(text='关闭防回退守卫' if st else '启用防回退守卫')

    def selected_dirs(self):
        out = []
        for i in self.dirbox.curselection():
            line = self.dirbox.get(i)
            d = line.split('] ', 1)[-1]
            out.append(d)
        if not out:
            # 默认全部
            for j in range(self.dirbox.size()):
                out.append(self.dirbox.get(j).split('] ', 1)[-1])
        return out

    # ---------- 操作（子线程防卡 UI） ----------
    def _run(self, fn, args=(), label=''):
        if self._busy:
            return
        self._busy = True
        self._done = False
        self._set_btns('disabled')
        self._log('\n>>> %s ...\n' % (label or fn.__name__))
        threading.Thread(target=self._worker, args=(fn, args), daemon=True).start()
        self.after(100, self._poll)

    def _worker(self, fn, args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            try:
                fn(*args) if args else fn()
            except Exception as e:
                buf.write('\n[ERROR] %s' % e)
        self._result = buf.getvalue()
        self._done = True

    def _poll(self):
        if self._done:
            self._busy = False
            self._set_btns('normal')
            self._log(self._result)
            self.refresh_dirs_quiet()
        else:
            self.after(100, self._poll)

    def refresh_dirs_quiet(self):
        dirs = core.try_locate_项目G_dirs()
        self.dirbox.delete(0, 'end')
        for d in dirs:
            st = detect_state(d + '\\项目G.exe')
            self.dirbox.insert('end', '[%s] %s' % (STATE_CN.get(st, st), d))
        self._update_guard_button()

    def _set_btns(self, st):
        for b in (self.btn_activate, self.btn_guard, self.btn_check, self.btn_revert):
            b.config(state=st)

    def _log(self, text):
        self.log.config(state='normal')
        self.log.insert('end', text)
        self.log.see('end')
        self.log.config(state='disabled')

    # ---------- 动作 ----------
    def activate_selected(self):
        dirs = self.selected_dirs()
        self._run(self._act_all, (dirs,), '一键激活')

    def _act_all(self, dirs):
        for d in dirs:
            core.apply(d)

    def check_selected(self):
        dirs = self.selected_dirs()
        self._run(self._chk_all, (dirs,), '检查状态')

    def _chk_all(self, dirs):
        for d in dirs:
            core.check(d)

    def revert_selected(self):
        dirs = self.selected_dirs()
        self._run(self._rev_all, (dirs,), '还原正版')

    def _rev_all(self, dirs):
        for d in dirs:
            core.revert(d)

    def toggle_guard(self):
        if core.guard_status():
            self._run(core.remove_guard, (), '移除防回退守卫')
        else:
            self._run(core.add_guard, (), '启用防回退守卫')

    # ---------- 冒烟 -------------
    def smoke(self):
        self.update_idletasks()
        self._log('[smoke] GUI constructed OK; dirs=%d\n' % self.dirbox.size())
        self.destroy()


def run_smoke():
    app = 项目GActivateApp()
    app.after(600, app.smoke)
    app.mainloop()
    return 0


def main():
    args = [a.lower() for a in sys.argv[1:]]
    if '--smoke' in args:
        return run_smoke()
    if len(args) > 0 and not (len(args) == 1 and args[0] in ('--silent', '--fix')):
        # 命令行模式（守卫/还原等）：复用 core，windowed 下无控制台输出
        old = sys.stdout
        sys.stdout = io.StringIO()
        try:
            core.main()
        finally:
            sys.stdout = old
        return 0
    app = 项目GActivateApp()
    app.mainloop()
    return 0


if __name__ == '__main__':
    sys.exit(main())