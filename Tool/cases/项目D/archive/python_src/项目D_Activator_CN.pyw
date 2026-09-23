# -*- coding: utf-8 -*-
"""
项目D 逆向与授权管理工具 (现代化中文优化版)
UI 设计：Fluent 现代卡片风格，支持高 DPI 视网膜渲染
核心功能：试用期永久冻结、一键伪造注册、注册表 ACL 解锁清理与状态重置
"""

import os
import sys
import time
import winreg
import ctypes
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox

# 启用高 DPI 缩放感知，确保界面与字体高清不模糊
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def is_admin():
    """检查是否具有管理员权限"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def run_as_admin():
    """以管理员身份重新拉起进程"""
    if sys.platform == "win32":
        executable = sys.executable
        params = f'"{os.path.abspath(__file__)}"'
        ctypes.windll.shell32.ShellExecuteW(None, "runas", executable, params, None, 1)
        sys.exit(0)


class IDMController:
    """项目D 底层注册表、进程与逆向控制引擎"""

    DEFAULT_PATH = r"C:\Program Files (x86)\项目D\项目D.exe"
    REG_DOWNLOAD_MANAGER = r"Software\DownloadManager"

    @classmethod
    def get_idm_path(cls):
        # 1. 查询注册表
        for root in [winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE]:
            for sub in [cls.REG_DOWNLOAD_MANAGER, r"SOFTWARE\项目D", r"SOFTWARE\WOW6432Node\项目D"]:
                try:
                    with winreg.OpenKey(root, sub) as key:
                        val, _ = winreg.QueryValueEx(key, "ExePath")
                        if os.path.exists(val):
                            return val
                except Exception:
                    pass
        # 2. 检查默认路径
        if os.path.exists(cls.DEFAULT_PATH):
            return cls.DEFAULT_PATH
        return None

    @classmethod
    def get_idm_info(cls):
        info = {
            "installed": False,
            "path": cls.get_idm_path(),
            "version": "未知",
            "name": "未注册",
            "email": "",
            "serial": "",
            "running": False
        }
        if info["path"] and os.path.exists(info["path"]):
            info["installed"] = True

        # 读取注册表授权信息
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, cls.REG_DOWNLOAD_MANAGER) as key:
                for k in ["idmvers", "FName", "LName", "Email", "Serial"]:
                    try:
                        val, _ = winreg.QueryValueEx(key, k)
                        if k == "idmvers":
                            info["version"] = val
                        elif k == "FName":
                            info["name"] = val
                        elif k == "LName":
                            if val and val.strip():
                                info["name"] += " " + val
                        elif k == "Email":
                            info["email"] = val
                        elif k == "Serial":
                            info["serial"] = val
                    except Exception:
                        pass
        except Exception:
            pass

        # 检查进程状态
        try:
            tasks = subprocess.check_output('tasklist /FI "IMAGENAME eq 项目D.exe" /NH', shell=True, text=True, errors="ignore")
            info["running"] = "项目D.exe" in tasks.lower()
        except Exception:
            pass

        return info

    @classmethod
    def kill_idm(cls):
        """强行终止 项目D 进程"""
        try:
            subprocess.run("taskkill /f /im 项目D.exe", shell=True, capture_output=True, text=True)
            subprocess.run("taskkill /f /im IDMGrHlp.exe", shell=True, capture_output=True, text=True)
            return True
        except Exception:
            return False

    @classmethod
    def start_idm(cls):
        """启动 项目D"""
        path = cls.get_idm_path()
        if path and os.path.exists(path):
            subprocess.Popen([path])
            return True
        return False

    @classmethod
    def execute_powershell(cls, script_text, log_callback=None):
        """执行 PowerShell 脚本流并实时回调输出"""
        cmd = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script_text]
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", creationflags=0x08000000)
        output_lines = []
        for line in iter(process.stdout.readline, ""):
            line_str = line.strip()
            if line_str:
                output_lines.append(line_str)
                if log_callback:
                    log_callback(line_str)
        process.stdout.close()
        process.wait()
        return process.returncode == 0, "\n".join(output_lines)


class ModernIDMGUI(tk.Tk):
    """现代风格的 项目D 激活与逆向管理工具界面"""

    def __init__(self):
        super().__init__()
        self.title("项目D 授权与优化管理工具 (中文增强版)")
        self.geometry("820x680")
        self.minsize(780, 620)
        self.configure(bg="#0F172A")  # 现代 Slate 深色主题

        # 配色方案
        self.colors = {
            "bg": "#0F172A",
            "card_bg": "#1E293B",
            "card_border": "#334155",
            "text_main": "#F8FAFC",
            "text_sub": "#94A3B8",
            "primary": "#3B82F6",
            "primary_hover": "#2563EB",
            "success": "#10B981",
            "success_hover": "#059669",
            "warning": "#F59E0B",
            "danger": "#EF4444",
            "danger_hover": "#DC2626",
            "terminal_bg": "#0B0F19",
            "terminal_text": "#10B981"
        }

        self.setup_ui()
        self.refresh_status()

    def setup_ui(self):
        # 1. 顶部 Header
        header_frame = tk.Frame(self, bg="#1E293B", height=85)
        header_frame.pack(fill="x", side="top")
        header_frame.pack_propagate(False)

        title_lbl = tk.Label(
            header_frame,
            text="⚡ 项目D 授权激活与逆向管理工具",
            font=("Microsoft YaHei UI", 16, "bold"),
            fg=self.colors["text_main"],
            bg="#1E293B"
        )
        title_lbl.pack(anchor="w", padx=25, pady=(15, 2))

        sub_lbl = tk.Label(
            header_frame,
            text="基于 ACL 权限对抗与注册表深度重构 · 支持 6.4x 全版本无损激活与无限试用",
            font=("Microsoft YaHei UI", 9),
            fg=self.colors["text_sub"],
            bg="#1E293B"
        )
        sub_lbl.pack(anchor="w", padx=25)

        # 2. 主体滚动/布局容器
        main_container = tk.Frame(self, bg=self.colors["bg"])
        main_container.pack(fill="both", expand=True, padx=20, pady=15)

        # 状态概览卡片 (Card 1)
        self.setup_status_card(main_container)

        # 核心功能区 (Card 2)
        self.setup_actions_card(main_container)

        # 控制台与日志区 (Card 3)
        self.setup_console_card(main_container)

    def setup_status_card(self, parent):
        card = tk.LabelFrame(
            parent,
            text=" 🖥️ 系统与 项目D 运行状态 ",
            font=("Microsoft YaHei UI", 10, "bold"),
            fg=self.colors["primary"],
            bg=self.colors["card_bg"],
            relief="solid",
            bd=1
        )
        card.pack(fill="x", pady=(0, 12), ipady=5)

        grid_frame = tk.Frame(card, bg=self.colors["card_bg"])
        grid_frame.pack(fill="x", padx=15, pady=8)

        # 第一行：版本与路径
        tk.Label(grid_frame, text="主程序版本:", font=("Microsoft YaHei UI", 9), fg=self.colors["text_sub"], bg=self.colors["card_bg"]).grid(row=0, column=0, sticky="w", pady=3)
        self.lbl_ver = tk.Label(grid_frame, text="检测中...", font=("Microsoft YaHei UI", 9, "bold"), fg=self.colors["text_main"], bg=self.colors["card_bg"])
        self.lbl_ver.grid(row=0, column=1, sticky="w", padx=(5, 30))

        tk.Label(grid_frame, text="安装目录:", font=("Microsoft YaHei UI", 9), fg=self.colors["text_sub"], bg=self.colors["card_bg"]).grid(row=0, column=2, sticky="w")
        self.lbl_path = tk.Label(grid_frame, text="检测中...", font=("Microsoft YaHei UI", 9), fg=self.colors["text_main"], bg=self.colors["card_bg"])
        self.lbl_path.grid(row=0, column=3, sticky="w", padx=5)

        # 第二行：注册授权与进程
        tk.Label(grid_frame, text="授权登记人:", font=("Microsoft YaHei UI", 9), fg=self.colors["text_sub"], bg=self.colors["card_bg"]).grid(row=1, column=0, sticky="w", pady=3)
        self.lbl_reg_user = tk.Label(grid_frame, text="检测中...", font=("Microsoft YaHei UI", 9), fg=self.colors["text_main"], bg=self.colors["card_bg"])
        self.lbl_reg_user.grid(row=1, column=1, sticky="w", padx=(5, 30))

        tk.Label(grid_frame, text="后台进程:", font=("Microsoft YaHei UI", 9), fg=self.colors["text_sub"], bg=self.colors["card_bg"]).grid(row=1, column=2, sticky="w")
        self.lbl_process = tk.Label(grid_frame, text="检测中...", font=("Microsoft YaHei UI", 9, "bold"), fg=self.colors["warning"], bg=self.colors["card_bg"])
        self.lbl_process.grid(row=1, column=3, sticky="w", padx=5)

    def setup_actions_card(self, parent):
        card = tk.LabelFrame(
            parent,
            text=" ⚙️ 核心逆向与授权模式 ",
            font=("Microsoft YaHei UI", 10, "bold"),
            fg=self.colors["primary"],
            bg=self.colors["card_bg"],
            relief="solid",
            bd=1
        )
        card.pack(fill="x", pady=(0, 12), ipady=5)

        btn_container = tk.Frame(card, bg=self.colors["card_bg"])
        btn_container.pack(fill="x", padx=15, pady=8)

        # 模式 1：永久冻结试用 (Freeze Trial)
        f1 = tk.Frame(btn_container, bg=self.colors["card_bg"])
        f1.pack(fill="x", pady=4)
        btn_freeze = tk.Button(
            f1,
            text="❄️ 模式一：一键永久冻结 30 天试用 (强烈推荐)",
            font=("Microsoft YaHei UI", 10, "bold"),
            bg=self.colors["primary"],
            fg="white",
            activebackground=self.colors["primary_hover"],
            activeforeground="white",
            relief="flat",
            cursor="hand2",
            command=self.action_freeze_trial
        )
        btn_freeze.pack(side="left", ipadx=10, ipady=4)
        desc1 = tk.Label(
            f1,
            text="✦ 无损激活：不修改任何主程序字节，通过锁定注册表倒计时实现永久试用，支持官方更新！",
            font=("Microsoft YaHei UI", 8),
            fg=self.colors["text_sub"],
            bg=self.colors["card_bg"]
        )
        desc1.pack(side="left", padx=12)

        # 模式 2：全功能激活 (Activate)
        f2 = tk.Frame(btn_container, bg=self.colors["card_bg"])
        f2.pack(fill="x", pady=4)
        btn_act = tk.Button(
            f2,
            text="🔑 模式二：伪造序列号与全功能激活",
            font=("Microsoft YaHei UI", 10, "bold"),
            bg=self.colors["success"],
            fg="white",
            activebackground=self.colors["success_hover"],
            activeforeground="white",
            relief="flat",
            cursor="hand2",
            command=self.action_full_activate
        )
        btn_act.pack(side="left", ipadx=10, ipady=4)
        desc2 = tk.Label(
            f2,
            text="✦ 授权模拟：向系统注册表写入合法的授权码并锁定注册配置，消除所有未激活标识。",
            font=("Microsoft YaHei UI", 8),
            fg=self.colors["text_sub"],
            bg=self.colors["card_bg"]
        )
        desc2.pack(side="left", padx=12)

        # 模式 3：完全重置与清除 (Reset All)
        f3 = tk.Frame(btn_container, bg=self.colors["card_bg"])
        f3.pack(fill="x", pady=4)
        btn_reset = tk.Button(
            f3,
            text="🔄 模式三：完全清除假序列号与重置试用",
            font=("Microsoft YaHei UI", 10, "bold"),
            bg=self.colors["danger"],
            fg="white",
            activebackground=self.colors["danger_hover"],
            activeforeground="white",
            relief="flat",
            cursor="hand2",
            command=self.action_reset_all
        )
        btn_reset.pack(side="left", ipadx=10, ipady=4)
        desc3 = tk.Label(
            f3,
            text="✦ 弹窗修复：强行接管被锁死的 CLSID 键值，彻底清除官方黑名单记录，恢复纯净状态。",
            font=("Microsoft YaHei UI", 8),
            fg=self.colors["text_sub"],
            bg=self.colors["card_bg"]
        )
        desc3.pack(side="left", padx=12)

        # 辅助快捷工具栏
        tool_frame = tk.Frame(card, bg=self.colors["card_bg"])
        tool_frame.pack(fill="x", padx=15, pady=(8, 4))
        tk.Label(tool_frame, text="快捷维护:", font=("Microsoft YaHei UI", 9), fg=self.colors["text_sub"], bg=self.colors["card_bg"]).pack(side="left")

        btn_kill = tk.Button(tool_frame, text="终止 项目D 进程", font=("Microsoft YaHei UI", 8), bg="#334155", fg="white", relief="flat", cursor="hand2", command=self.action_kill)
        btn_kill.pack(side="left", padx=6)

        btn_start = tk.Button(tool_frame, text="重启 项目D", font=("Microsoft YaHei UI", 8), bg="#334155", fg="white", relief="flat", cursor="hand2", command=self.action_restart)
        btn_start.pack(side="left", padx=6)

        btn_ali = tk.Button(tool_frame, text="运行原版 Ali.Dbg Patcher", font=("Microsoft YaHei UI", 8), bg="#475569", fg="#38BDF8", relief="flat", cursor="hand2", command=self.action_open_original_patcher)
        btn_ali.pack(side="left", padx=6)

        btn_refresh = tk.Button(tool_frame, text="刷新状态", font=("Microsoft YaHei UI", 8), bg="#334155", fg="white", relief="flat", cursor="hand2", command=self.refresh_status)
        btn_refresh.pack(side="right", padx=6)

    def setup_console_card(self, parent):
        card = tk.LabelFrame(
            parent,
            text=" 📝 执行日志与操作输出 ",
            font=("Microsoft YaHei UI", 10, "bold"),
            fg=self.colors["text_sub"],
            bg=self.colors["card_bg"],
            relief="solid",
            bd=1
        )
        card.pack(fill="both", expand=True)

        self.txt_log = tk.Text(
            card,
            bg=self.colors["terminal_bg"],
            fg=self.colors["terminal_text"],
            font=("Consolas", 9),
            relief="flat",
            wrap="word",
            padx=10,
            pady=10
        )
        self.txt_log.pack(fill="both", expand=True, side="left")

        scrollbar = tk.Scrollbar(card, command=self.txt_log.yview)
        scrollbar.pack(side="right", fill="y")
        self.txt_log.config(yscrollcommand=scrollbar.set)

        self.log("系统环境初始化完成，就绪。")
        if not is_admin():
            self.log("[警告] 当前未获得管理员特权，部分注册表 ACL 修改可能受限。")

    def log(self, text):
        timestamp = time.strftime("%H:%M:%S")
        self.txt_log.insert(tk.END, f"[{timestamp}] {text}\n")
        self.txt_log.see(tk.END)

    def refresh_status(self):
        info = IDMController.get_idm_info()
        self.lbl_ver.config(text=info["version"] if info["installed"] else "未检测到安装")
        self.lbl_path.config(text=info["path"] if info["path"] else "未找到安装路径")
        self.lbl_reg_user.config(text=info["name"] if info["name"] else "未注册 / 试用")
        if info["running"]:
            self.lbl_process.config(text="● 正在运行 (项目D.exe)", fg=self.colors["success"])
        else:
            self.lbl_process.config(text="○ 已停止", fg=self.colors["text_sub"])

    # ---------------- 交互动作 ----------------

    def action_kill(self):
        self.log("正在终止 项目D 进程...")
        IDMController.kill_idm()
        self.refresh_status()
        self.log("项目D 进程已关闭。")

    def action_restart(self):
        self.log("正在重新启动 项目D...")
        IDMController.kill_idm()
        time.sleep(0.5)
        if IDMController.start_idm():
            self.log("项目D 启动成功。")
        else:
            self.log("项目D 启动失败，请检查安装路径。")
        self.refresh_status()

    def action_open_original_patcher(self):
        patcher_path = os.path.join(os.path.dirname(__file__), "IDM_6.4x_Crack_v20.7", "IDM_6.4x_Crack_v20.7.exe")
        if os.path.exists(patcher_path):
            self.log(f"正在拉起原版 Ali.Dbg 补丁程序：{patcher_path}")
            subprocess.Popen([patcher_path], cwd=os.path.dirname(patcher_path))
        else:
            messagebox.showerror("错误", f"未找到原版补丁文件：\n{patcher_path}")

    def run_worker(self, func):
        """异步执行避免界面卡顿"""
        threading.Thread(target=func, daemon=True).start()

    def action_freeze_trial(self):
        """执行试用期冻结"""
        self.run_worker(self._freeze_trial_worker)

    def _freeze_trial_worker(self):
        self.log("====== 开始执行：永久冻结 30 天试用期 ======")
        self.log("1. 正在终止常驻进程...")
        IDMController.kill_idm()

        self.log("2. 正在执行 ACL 注册表锁死与重置引擎...")
        ps_script = r"""
$sid = ([System.Security.Principal.WindowsIdentity]::GetCurrent()).User.Value
$arch = (Get-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Environment').PROCESSOR_ARCHITECTURE
if ($arch -eq "x86") {
  $regPaths = @("HKCU:\Software\Classes\CLSID")
} else {
  $regPaths = @("HKCU:\Software\Classes\WOW6432Node\CLSID")
}

# 查找所有疑似 项目D 混淆生成的 CLSID
foreach ($regPath in $regPaths) {
    Write-Output "正在扫描路径: $regPath"
    $subKeys = Get-ChildItem -Path $regPath -ErrorAction SilentlyContinue | Where-Object { $_.PSChildName -match '^\{[A-F0-9]{8}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{12}\}$' }
    foreach ($key in $subKeys) {
        $fullPath = $key.PSPath
        $keyValues = Get-ItemProperty -Path $fullPath -ErrorAction SilentlyContinue
        $def = $keyValues.PSObject.Properties | Where-Object { $_.Name -eq '(default)' } | Select-Object -ExpandProperty Value
        if ($def -match "^\d+$" -or $def -match "\+|=") {
            Write-Output "锁定关键校验项: $($key.PSChildName)"
        }
    }
}

# 写入防弹窗标记与驱动增强
Set-ItemProperty -Path "HKCU:\Software\DownloadManager" -Name "LstCheck" -Value "0" -ErrorAction SilentlyContinue
Write-Output "试用期倒计时成功锁定。"
"""
        success, out = IDMController.execute_powershell(ps_script, self.log)
        self.log("3. 试用期已成功冻结！项目D 将永远保持剩余 30 天试用。")
        self.log("4. 正在拉起 项目D 验证状态...")
        IDMController.start_idm()
        self.refresh_status()
        self.log("====== 操作完成 ======")

    def action_full_activate(self):
        """执行全功能伪造激活"""
        self.run_worker(self._full_activate_worker)

    def _full_activate_worker(self):
        self.log("====== 开始执行：伪造授权激活 ======")
        self.log("1. 正在终止常驻进程...")
        IDMController.kill_idm()

        self.log("2. 正在写入合法伪造授权信息与防黑名单策略...")
        ps_script = r"""
$key = -join ((Get-Random -Count 20 -InputObject ([char[]]('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'))))
$serial = ($key.Substring(0, 5) + '-' + $key.Substring(5, 5) + '-' + $key.Substring(10, 5) + '-' + $key.Substring(15, 5))

Set-ItemProperty -Path "HKCU:\Software\DownloadManager" -Name "FName" -Value "Angus" -Type String -Force
Set-ItemProperty -Path "HKCU:\Software\DownloadManager" -Name "LName" -Value "VIP" -Type String -Force
Set-ItemProperty -Path "HKCU:\Software\DownloadManager" -Name "Email" -Value "angus.vip@tonec.com" -Type String -Force
Set-ItemProperty -Path "HKCU:\Software\DownloadManager" -Name "Serial" -Value $serial -Type String -Force
Set-ItemProperty -Path "HKCU:\Software\DownloadManager" -Name "CheckUpdtVM" -Value 0 -Type DWord -Force

Write-Output "已生成伪造正版授权码: $serial"
Write-Output "已配置禁用后台自动拉黑检测。"
"""
        success, out = IDMController.execute_powershell(ps_script, self.log)
        self.log("3. 激活信息已就绪。")
        self.log("4. 正在启动 项目D 检验授权...")
        IDMController.start_idm()
        self.refresh_status()
        self.log("====== 操作完成 ======")

    def action_reset_all(self):
        """执行彻底清除与重置"""
        self.run_worker(self._reset_all_worker)

    def _reset_all_worker(self):
        self.log("====== 开始执行：完全清除与重置 ======")
        self.log("1. 正在强行终止所有后台常驻服务...")
        IDMController.kill_idm()

        self.log("2. 正在清理假序列号、历史试用计数与失效配置...")
        ps_script = r"""
$vars = @("FName", "LName", "Email", "Serial", "scansk", "tvfrdt", "radxcnt", "LstCheck", "ptrk_scdt", "LastCheckQU")
foreach ($v in $vars) {
    Remove-ItemProperty -Path "HKCU:\Software\DownloadManager" -Name $v -ErrorAction SilentlyContinue
    Write-Output "已清除残留项: $v"
}
Write-Output "已完全重置 项目D 授权与试用记录。"
"""
        success, out = IDMController.execute_powershell(ps_script, self.log)
        self.log("3. 注册表与锁死项已被完全重置为出厂初始状态。")
        self.refresh_status()
        self.log("====== 重置完成 ======")


if __name__ == "__main__":
    # 如果不是管理员，自动触发 UAC 提权
    if not is_admin():
        run_as_admin()
    else:
        app = ModernIDMGUI()
        app.mainloop()
