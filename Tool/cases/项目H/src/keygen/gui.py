# -*- coding: utf-8 -*-
"""项目H <目标版本> Keygen —— 一键激活 GUI（tkinter，零第三方依赖）

功能：
  - 自动定位 项目H.exe（exe 同目录 / 常见安装目录 / 注册表 / 常见盘符）
  - ⚡ 一键激活：自动 patch（公钥替换 + 可选持久化），就地替换并备份原文件
  - 生成激活码（keypair.bin 自动生成/复用，存放在 exe 同目录）
  - 复制激活码到剪贴板 / 手动 Patch

运行：python -m keygen.gui
"""
import glob
import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from keygen.cli import load_or_create_keypair  # noqa: E402
from keygen.algo import (  # noqa: E402
    HAVE_CRYPTOGRAPHY,
    build_activation_code,
    expected_machineid,
    patch_public_key,
    patch_persist,
    read_machine_guid,
)
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

BACKUP_SUFFIX = ".official.bak"


def find_项目H():
    """自动搜索 项目H.exe：exe 同目录 → 常见安装目录 → 注册表卸载项 → 常见盘符"""
    exe_dir = os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.getcwd()
    cands = [
        os.path.join(exe_dir, "项目H.exe"),
        r"<本地路径>",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\项目H\项目H.exe"),
        os.path.expandvars(r"%ProgramFiles%\项目H\项目H.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\项目H\项目H.exe"),
        os.path.expandvars(r"%LOCALAPPDATA%\项目H\项目H.exe"),
    ]
    for p in cands:
        if p and os.path.isfile(p):
            return p
    # 注册表卸载信息 → InstallLocation
    try:
        import winreg
        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            sub = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
            try:
                k = winreg.OpenKey(root, sub)
            except OSError:
                continue
            n = 0
            while True:
                try:
                    name = winreg.EnumKey(k, n)
                except OSError:
                    break
                try:
                    kk = winreg.OpenKey(k, name)
                    disp, _ = winreg.QueryValueEx(kk, "DisplayName")
                    if "项目H" in str(disp).lower():
                        loc, _ = winreg.QueryValueEx(kk, "InstallLocation")
                        if loc:
                            p = os.path.join(loc, "项目H.exe")
                            if os.path.isfile(p):
                                winreg.CloseKey(kk)
                                winreg.CloseKey(k)
                                return p
                    winreg.CloseKey(kk)
                except OSError:
                    pass
                n += 1
            winreg.CloseKey(k)
    except Exception:
        pass
    # 常见盘根目录 glob（如 <本地路径>
    for drive in ("<本地路径>", "C:\\", "D:\\", "E:\\"):
        try:
            for m in glob.glob(os.path.join(drive, "*[Ss]nipaste*", "项目H.exe")):
                if os.path.isfile(m):
                    return m
        except OSError:
            continue
    return None


class KeygenApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("项目H <目标版本> 一键激活")
        root.geometry("660x520")
        self.keypair = os.path.join(
            os.path.dirname(sys.executable) if getattr(sys, "frozen", False) else os.getcwd(),
            "keypair.bin")
        self.guid = None
        self.var_src = tk.StringVar()
        self._build_widgets()
        threading.Thread(target=self._load_machine, daemon=True).start()
        threading.Thread(target=self._find_in_thread, daemon=True).start()

    def _build_widgets(self):
        pad = {"padx": 8, "pady": 4}
        frm = tk.Frame(self.root)
        frm.pack(fill="x", **pad)

        tk.Label(frm, text="MachineGuid:").grid(row=0, column=0, sticky="w")
        self.lbl_guid = tk.Label(frm, text="(读取中…)", anchor="w", fg="#444")
        self.lbl_guid.grid(row=0, column=1, sticky="we")
        tk.Label(frm, text="期望设备码:").grid(row=1, column=0, sticky="w")
        self.lbl_mid = tk.Label(frm, text="-", anchor="w", fg="#444")
        self.lbl_mid.grid(row=1, column=1, sticky="we")
        frm.columnconfigure(1, weight=1)

        # 项目H.exe 定位行
        row = tk.Frame(self.root)
        row.pack(fill="x", **pad)
        tk.Label(row, text="项目H.exe:").pack(side="left")
        en = tk.Entry(row, textvariable=self.var_src)
        en.pack(side="left", fill="x", expand=True, padx=4)
        tk.Button(row, text="浏览…", command=self.on_browse).pack(side="left")
        self.lbl_auto = tk.Label(self.root, text="🔍 正在自动检测…", anchor="w", fg="#666")
        self.lbl_auto.pack(fill="x", padx=12)

        # 一键激活行
        btns = tk.Frame(self.root)
        btns.pack(fill="x", **pad)
        tk.Button(btns, text="⚡ 一键激活",
                  command=self.on_oneclick, bg="#4caf50", fg="white",
                  font=("", 11, "bold"), padx=18, pady=6).pack(side="left", padx=4)
        self.btn_persist = tk.BooleanVar(value=True)
        tk.Checkbutton(btns, text="启用持久化(重启仍Pro)", variable=self.btn_persist).pack(side="left", padx=8)

        # 可选：生成激活码 / 手动 patch
        frm2 = tk.Frame(self.root)
        frm2.pack(fill="x", **pad)
        tk.Label(frm2, text="名称:").grid(row=0, column=0, sticky="w")
        self.ent_name = tk.Entry(frm2, width=20)
        self.ent_name.insert(0, "keygen")
        self.ent_name.grid(row=0, column=1, sticky="we")
        tk.Label(frm2, text="邮箱:").grid(row=1, column=0, sticky="w")
        self.ent_email = tk.Entry(frm2, width=20)
        self.ent_email.insert(0, "keygen@keygen.local")
        self.ent_email.grid(row=1, column=1, sticky="we")
        frm2.columnconfigure(1, weight=1)

        btns2 = tk.Frame(self.root)
        btns2.pack(fill="x", **pad)
        tk.Button(btns2, text="生成激活码", command=self.on_gen).pack(side="left", padx=4)
        tk.Button(btns2, text="复制", command=self.on_copy).pack(side="left", padx=4)
        tk.Button(btns2, text="手动 Patch（另存为）…", command=self.on_patch).pack(side="left", padx=4)

        self.txt = scrolledtext.ScrolledText(self.root, height=10, state="disabled", font=("Consolas", 9))
        self.txt.pack(fill="both", expand=True, padx=8, pady=4)

    def _log(self, s: str):
        self.txt.configure(state="normal")
        self.txt.insert("end", s + "\n")
        self.txt.see("end")
        self.txt.configure(state="disabled")

    def _load_machine(self):
        try:
            self.guid = read_machine_guid()
            mid = expected_machineid(self.guid)
            self.root.after(0, lambda: (
                self.lbl_guid.configure(text=self.guid),
                self.lbl_mid.configure(text=mid),
            ))
        except Exception as e:  # pragma: no cover
            self.root.after(0, lambda: self.lbl_guid.configure(text=f"读取失败: {e}"))

    def _find_in_thread(self):
        p = find_项目H()
        if p:
            self.root.after(0, lambda: (
                self.var_src.set(p),
                self.lbl_auto.configure(text=f"✓ 自动检测到: {p}", fg="#2a7d2a"),
            ))
        else:
            self.root.after(0, lambda: self.lbl_auto.configure(
                text="未自动检测到，请点「浏览…」选择 项目H.exe", fg="#a00"))

    def on_browse(self):
        p = filedialog.askopenfilename(
            title="选择 项目H.exe", filetypes=[("项目H", "项目H.exe")])
        if p:
            self.var_src.set(p)
            self.lbl_auto.configure(text=f"✓ 已选择: {p}", fg="#2a7d2a")

    def on_oneclick(self):
        src = self.var_src.get().strip()
        if not src or not os.path.isfile(src):
            messagebox.showwarning("未定位", "请先选择 项目H.exe（可点「浏览…」）")
            return
        if not messagebox.askyesno(
                "一键激活",
                f"将对以下程序执行激活：\n{src}\n\n"
                "· 自动备份原文件为 项目H.exe.official.bak\n"
                "· 完成即专业版（重启 项目H 生效）\n\n继续？"):
            return
        try:
            priv_raw, pub = load_or_create_keypair(self.keypair)
            data = open(src, "rb").read()
            out = patch_public_key(data, pub)
            if self.btn_persist.get():
                out = patch_persist(out, enable=True)
                self._log("→ 已启用持久化(重启仍Pro)")
            bak = src + BACKUP_SUFFIX
            if not os.path.exists(bak):
                open(bak, "wb").write(data)
                self._log(f"→ 已备份原版: {bak}")
            tmp = src + ".tmp"
            open(tmp, "wb").write(out)
            os.replace(tmp, src)
            self._log(f"✓ 一键激活完成: {src}")
            self._log(f"  公钥: {pub.hex()}")
            messagebox.showinfo("完成",
                                "✓ 项目H 已是专业版！\n\n"
                                f"现在可直接运行:\n{src}\n\n"
                                "还原方法：用 项目H.exe.official.bak 覆盖 项目H.exe。")
        except Exception as e:
            messagebox.showerror("激活失败", str(e))

    def on_gen(self):
        if not HAVE_CRYPTOGRAPHY:
            messagebox.showerror("缺少依赖", "需要 cryptography 库")
            return
        if self.guid is None:
            self.guid = read_machine_guid()
        try:
            priv_raw, pub = load_or_create_keypair(self.keypair)
            priv = Ed25519PrivateKey.from_private_bytes(priv_raw)
            code = build_activation_code(
                priv, name=self.ent_name.get() or "keygen",
                email=self.ent_email.get() or "keygen@keygen.local",
                machine_guid=self.guid)
            self._code = code
            self._log(f"→ 公钥: {pub.hex()}")
            self._log(f"→ 激活码: {code}")
        except Exception as e:
            messagebox.showerror("生成失败", str(e))

    def on_copy(self):
        code = getattr(self, "_code", None)
        if not code:
            messagebox.showwarning("无激活码", "请先生成激活码")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(code)
        self._log("→ 已复制到剪贴板")

    def on_patch(self):
        src = filedialog.askopenfilename(
            title="选择 项目H.exe", filetypes=[("项目H", "项目H.exe")])
        if not src:
            return
        dst = filedialog.asksaveasfilename(
            title="保存 patched 副本（默认即源目录，直接保存即可）",
            defaultextension=".exe", initialfile="项目H_pro.exe",
            initialdir=os.path.dirname(src))
        if not dst:
            return
        try:
            priv_raw, pub = load_or_create_keypair(self.keypair)
            data = open(src, "rb").read()
            out = patch_public_key(data, pub)
            if self.btn_persist.get():
                out = patch_persist(out, enable=True)
                self._log("→ 已启用持久化(启动即Pro)")
            open(dst, "wb").write(out)
            self._log(f"→ patched 已保存: {dst}")
            self._log(f"→ 新公钥: {pub.hex()}")
        except Exception as e:
            messagebox.showerror("Patch 失败", str(e))


def main():
    if not HAVE_CRYPTOGRAPHY:  # pragma: no cover
        print("[!] 需要 cryptography 库：pip install cryptography")
        sys.exit(1)
    root = tk.Tk()
    KeygenApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()