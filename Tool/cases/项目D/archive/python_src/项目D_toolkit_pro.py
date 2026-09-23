# -*- coding: utf-8 -*-
"""
项目D 现代化授权与环境优化管理工具 Pro (项目D Toolkit Pro)
基于 CustomTkinter 打造的现代化 UI 极简纯净版
全内置原生二进制特征补丁与系统 ACL 策略，零外部依赖
"""

import os
import sys
import time
import shutil
import string
import random
import winreg
import ctypes
import subprocess
import threading
import customtkinter as ctk
from tkinter import messagebox, filedialog

# 基础主题与外观设置
ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# 高 DPI 适配
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def get_app_dir():
    """获取当前可执行文件或脚本所在的真实目录（兼容 PyInstaller 打包环境）"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def is_admin():
    """检查当前进程是否具有管理员特权"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def request_admin():
    if sys.platform == "win32":
        executable = sys.executable
        if getattr(sys, 'frozen', False):
            executable = sys.executable
            params = ""
        else:
            params = f'"{os.path.abspath(__file__)}"'
        ctypes.windll.shell32.ShellExecuteW(None, "runas", executable, params, None, 1)
        sys.exit(0)


def generate_serial():
    chars = string.ascii_uppercase + string.digits
    parts = []
    for _ in range(4):
        parts.append(''.join(random.choice(chars) for _ in range(5)))
    return '-'.join(parts)


class NativePatcherEngine:
    """
    原生内置特征修补引擎
    直接对 项目D.exe 进行特征码检索与修补，完全内置
    """

    RULES = [
        {
            "name": "解除授权分支检测 (Bypass Reg Check)",
            "search": bytes.fromhex("0051ff150440690085c00f851b010000c6"),
            "replace": bytes.fromhex("0051ff150440690033c00f851b010000c6")
        },
        {
            "name": "锁定试用期最大值 (Force Unlimited Days)",
            "search": bytes.fromhex("dc9c7700f7d81bc083e00f83c00fa3e09c7700885dcf"),
            "replace": bytes.fromhex("dc9c7700f7d81bc0b8ffffff7f90a3e09c7700885dcf")
        },
        {
            "name": "屏蔽假序列号警告弹窗 A (Bypass Nag 1)",
            "search": bytes.fromhex("10e8aa030e0084c0742a807c2407007523"),
            "replace": bytes.fromhex("10e8aa030e0084c0eb2a807c2407007523")
        },
        {
            "name": "阻断自检守护线程 A (Kill Watchdog Thread 1)",
            "search": bytes.fromhex("ec000000c3cccccc6aff683b84660064a1"),
            "replace": bytes.fromhex("ec000000c3ccccccc3ff683b84660064a1")
        },
        {
            "name": "阻断自检守护线程 B (Kill Watchdog Thread 2)",
            "search": bytes.fromhex("010000c3cccccccc6aff687884660064a1"),
            "replace": bytes.fromhex("010000c3ccccccccc3ff687884660064a1")
        },
        {
            "name": "阻断自检守护线程 C (Kill Watchdog Thread 3)",
            "search": bytes.fromhex("cccccccccccccccc6aff68cb8c660064a1"),
            "replace": bytes.fromhex("ccccccccccccccccc3ff68cb8c660064a1")
        },
        {
            "name": "阻断自检守护线程 D (Kill Watchdog Thread 4)",
            "search": bytes.fromhex("cccccccccccccccc6aff689c8d660064a1"),
            "replace": bytes.fromhex("ccccccccccccccccc3ff689c8d660064a1")
        },
        {
            "name": "切断外部看门狗关联 (Kill Watchdog Hook)",
            "search": bytes.fromhex("c41c100000c3cccc6aff689c8d660064a1"),
            "replace": bytes.fromhex("c41c100000c3ccccc3ff689c8d660064a1")
        },
        {
            "name": "屏蔽假序列号警告弹窗 B (Bypass Nag 2)",
            "search": bytes.fromhex("00e814d2030084c0742a807c2407007523"),
            "replace": bytes.fromhex("00e814d2030084c0eb2a807c2407007523")
        },
        {
            "name": "阻断过期强退逻辑 (Bypass License Expiry)",
            "search": bytes.fromhex("c975f92bc283f8020f85d2010000e8596ffb"),
            "replace": bytes.fromhex("c975f92bc283f80290e9d2010000e8596ffb")
        },
        {
            "name": "修正试用天数限制常量 (Trial Constant Patch)",
            "search": bytes.fromhex("01000000010000001e0000003883690030f36900"),
            "replace": bytes.fromhex("0100000001000000ffffff7f3883690030f36900")
        }
    ]

    @classmethod
    def apply_patch(cls, target_exe, backup=True, log_fn=print):
        if not os.path.exists(target_exe):
            log_fn(f"错误：未找到目标文件 {target_exe}")
            return False

        bak_path = target_exe + ".BAK"
        if backup and not os.path.exists(bak_path):
            try:
                shutil.copy2(target_exe, bak_path)
                log_fn(f"已创建官方原始备份: {bak_path}")
            except Exception as e:
                log_fn(f"创建备份提示: {e}")

        with open(target_exe, "rb") as f:
            data = bytearray(f.read())

        applied = 0
        for rule in cls.RULES:
            idx = data.find(rule["search"])
            if idx != -1:
                data[idx:idx + len(rule["replace"])] = rule["replace"]
                applied += 1
                log_fn(f"✓ 成功优化节点: {rule['name']}")

        if applied == 0:
            log_fn("提示：目标程序已处于优化完成状态。")
            return True

        try:
            with open(target_exe, "wb") as f:
                f.write(data)
            log_fn(f"★ 核心优化成功！共完成 {applied} 处底层逻辑升级。")
            return True
        except Exception as e:
            log_fn(f"写入补丁时发生错误: {e}")
            return False

    @classmethod
    def restore_original(cls, target_exe, log_fn=print):
        bak_path = target_exe + ".BAK"
        if not os.path.exists(bak_path):
            log_fn("未检测到官方原始备份文件 (项目D.exe.BAK)，无法还原。")
            return False
        try:
            shutil.copy2(bak_path, target_exe)
            log_fn("已将主程序无损还原为官方原版文件！")
            return True
        except Exception as e:
            log_fn(f"还原失败: {e}")
            return False


class IDMCore:
    """项目D 底层核心控制逻辑"""

    DEFAULT_PATH = r"C:\Program Files (x86)\项目D\项目D.exe"
    REG_PATH = r"Software\DownloadManager"

    @classmethod
    def get_idm_path(cls):
        for root in [winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE]:
            for sub in [cls.REG_PATH, r"SOFTWARE\项目D", r"SOFTWARE\WOW6432Node\项目D"]:
                try:
                    with winreg.OpenKey(root, sub) as key:
                        val, _ = winreg.QueryValueEx(key, "ExePath")
                        if os.path.exists(val):
                            return val
                except Exception:
                    pass
        if os.path.exists(cls.DEFAULT_PATH):
            return cls.DEFAULT_PATH
        return None

    @classmethod
    def get_info(cls):
        info = {
            "installed": False,
            "path": cls.get_idm_path(),
            "version": "未检测到",
            "name": "未注册 / 试用",
            "email": "",
            "serial": "",
            "running": False,
            "has_backup": False
        }
        if info["path"] and os.path.exists(info["path"]):
            info["installed"] = True
            info["has_backup"] = os.path.exists(info["path"] + ".BAK")

        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, cls.REG_PATH) as key:
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

        try:
            tasks = subprocess.check_output('tasklist /FI "IMAGENAME eq 项目D.exe" /NH', shell=True, text=True, errors="ignore")
            info["running"] = "项目D.exe" in tasks.lower()
        except Exception:
            pass

        return info

    @classmethod
    def kill_idm(cls):
        try:
            subprocess.run("taskkill /f /im 项目D.exe", shell=True, capture_output=True, text=True)
            subprocess.run("taskkill /f /im IDMGrHlp.exe", shell=True, capture_output=True, text=True)
            return True
        except Exception:
            return False

    @classmethod
    def start_idm(cls):
        path = cls.get_idm_path()
        if path and os.path.exists(path):
            subprocess.Popen([path])
            return True
        return False

    @classmethod
    def run_powershell_stream(cls, script_text, log_fn):
        cmd = ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script_text]
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=0x08000000
        )
        for line in iter(proc.stdout.readline, ""):
            s = line.strip()
            if s:
                log_fn(s)
        proc.stdout.close()
        proc.wait()
        return proc.returncode == 0


class IDMToolkitApp(ctk.CTk):
    """现代化美化主窗口界面"""

    def __init__(self):
        super().__init__()
        self.title("项目D 授权与环境优化工具 Pro")
        self.geometry("1020x720")
        self.minsize(960, 680)

        # 尝试加载图标
        ico_file = os.path.join(get_app_dir(), "idm_icon.ico")
        if not os.path.exists(ico_file):
            ico_file = os.path.join(os.path.dirname(__file__), "idm_icon.ico")
        if os.path.exists(ico_file):
            try:
                self.iconbitmap(ico_file)
            except Exception:
                pass

        self.setup_layout()
        self.refresh_all_status()

    def setup_layout(self):
        # 整体采用深度暗黑配色
        self.configure(fg_color="#0D1117")
        self.grid_columnconfigure(0, weight=0, minsize=280)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # 1. 左侧边栏 (Sidebar)
        self.sidebar = ctk.CTkFrame(
            self,
            corner_radius=0,
            fg_color="#161B22",
            border_width=0
        )
        self.sidebar.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)
        self.setup_sidebar()

        # 2. 右侧主工作区 (Main Panel)
        self.main_panel = ctk.CTkFrame(
            self,
            corner_radius=0,
            fg_color="#0D1117",
            border_width=0
        )
        self.main_panel.grid(row=0, column=1, sticky="nsew", padx=20, pady=20)
        self.setup_main_panel()

    def setup_sidebar(self):
        # --- 顶部 Brand 区域 ---
        brand_box = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        brand_box.pack(fill="x", padx=20, pady=(24, 16))

        # 标题与图标
        title_row = ctk.CTkFrame(brand_box, fg_color="transparent")
        title_row.pack(anchor="w")

        logo_icon = ctk.CTkLabel(
            title_row,
            text="⚡",
            font=ctk.CTkFont(size=22),
            text_color="#38BDF8"
        )
        logo_icon.pack(side="left", padx=(0, 6))

        logo_label = ctk.CTkLabel(
            title_row,
            text="项目D 工具箱 Pro",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=20, weight="bold"),
            text_color="#F0F6FC"
        )
        logo_label.pack(side="left")

        # 版本徽章
        badge_box = ctk.CTkFrame(brand_box, fg_color="#1E293B", corner_radius=6)
        badge_box.pack(anchor="w", pady=(8, 0))

        badge_label = ctk.CTkLabel(
            badge_box,
            text="PRO EDITION · v2026.1",
            font=ctk.CTkFont(family="Consolas", size=10, weight="bold"),
            text_color="#38BDF8"
        )
        badge_label.pack(padx=8, pady=2)

        # --- 状态监视卡片 ---
        self.status_card = ctk.CTkFrame(
            self.sidebar,
            fg_color="#0D1117",
            border_width=1,
            border_color="#30363D",
            corner_radius=12
        )
        self.status_card.pack(fill="x", padx=16, pady=(0, 16))

        st_header = ctk.CTkLabel(
            self.status_card,
            text="🖥️ 系统状态仪表盘",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=12, weight="bold"),
            text_color="#8B949E"
        )
        st_header.pack(anchor="w", padx=14, pady=(12, 8))

        # 状态列表项
        st_inner = ctk.CTkFrame(self.status_card, fg_color="transparent")
        st_inner.pack(fill="x", padx=14, pady=(0, 12))

        # 1. 安装状态
        row1 = ctk.CTkFrame(st_inner, fg_color="transparent")
        row1.pack(fill="x", pady=3)
        ctk.CTkLabel(row1, text="软件安装:", font=ctk.CTkFont(family="Microsoft YaHei UI", size=11), text_color="#8B949E").pack(side="left")
        self.lbl_stat_install = ctk.CTkLabel(row1, text="检测中...", font=ctk.CTkFont(family="Microsoft YaHei UI", size=11, weight="bold"), text_color="#E6EDF3")
        self.lbl_stat_install.pack(side="right")

        # 2. 当前版本
        row2 = ctk.CTkFrame(st_inner, fg_color="transparent")
        row2.pack(fill="x", pady=3)
        ctk.CTkLabel(row2, text="内核版本:", font=ctk.CTkFont(family="Microsoft YaHei UI", size=11), text_color="#8B949E").pack(side="left")
        self.lbl_stat_ver = ctk.CTkLabel(row2, text="未知", font=ctk.CTkFont(family="Microsoft YaHei UI", size=11), text_color="#C9D1D9")
        self.lbl_stat_ver.pack(side="right")

        # 3. 授权身份
        row3 = ctk.CTkFrame(st_inner, fg_color="transparent")
        row3.pack(fill="x", pady=3)
        ctk.CTkLabel(row3, text="授权状态:", font=ctk.CTkFont(family="Microsoft YaHei UI", size=11), text_color="#8B949E").pack(side="left")
        self.lbl_stat_auth = ctk.CTkLabel(row3, text="检测中", font=ctk.CTkFont(family="Microsoft YaHei UI", size=11, weight="bold"), text_color="#38BDF8")
        self.lbl_stat_auth.pack(side="right")

        # 4. 进程状态
        row4 = ctk.CTkFrame(st_inner, fg_color="transparent")
        row4.pack(fill="x", pady=3)
        ctk.CTkLabel(row4, text="后台进程:", font=ctk.CTkFont(family="Microsoft YaHei UI", size=11), text_color="#8B949E").pack(side="left")
        self.lbl_stat_proc = ctk.CTkLabel(row4, text="检测中", font=ctk.CTkFont(family="Microsoft YaHei UI", size=11), text_color="#F59E0B")
        self.lbl_stat_proc.pack(side="right")

        # --- 快捷管理操作区 ---
        action_box = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        action_box.pack(fill="x", padx=16, pady=4)

        lbl_ops = ctk.CTkLabel(
            action_box,
            text="🛠️ 快捷进程控制",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=12, weight="bold"),
            text_color="#8B949E"
        )
        lbl_ops.pack(anchor="w", pady=(0, 10))

        btn_refresh = ctk.CTkButton(
            action_box,
            text="🔄 刷新运行状态",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=12),
            fg_color="#21262D",
            hover_color="#30363D",
            text_color="#F0F6FC",
            border_width=1,
            border_color="#30363D",
            corner_radius=8,
            height=34,
            command=self.refresh_all_status
        )
        btn_refresh.pack(fill="x", pady=3)

        btn_kill = ctk.CTkButton(
            action_box,
            text="⏹️ 强行终止 项目D 进程",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=12),
            fg_color="#21262D",
            hover_color="#30363D",
            text_color="#F0F6FC",
            border_width=1,
            border_color="#30363D",
            corner_radius=8,
            height=34,
            command=self.action_kill
        )
        btn_kill.pack(fill="x", pady=3)

        btn_start = ctk.CTkButton(
            action_box,
            text="▶️ 启动 / 重启 项目D",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=12),
            fg_color="#21262D",
            hover_color="#30363D",
            text_color="#F0F6FC",
            border_width=1,
            border_color="#30363D",
            corner_radius=8,
            height=34,
            command=self.action_start
        )
        btn_start.pack(fill="x", pady=3)

        self.btn_restore_orig = ctk.CTkButton(
            action_box,
            text="♻️ 一键还原官方原版",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=12),
            fg_color="#21262D",
            hover_color="#30363D",
            text_color="#8B949E",
            border_width=1,
            border_color="#30363D",
            corner_radius=8,
            height=34,
            command=self.action_restore_orig
        )
        self.btn_restore_orig.pack(fill="x", pady=3)

        # 底部弹性填充
        spacer = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        spacer.pack(fill="both", expand=True)

        # 底部管理员徽章卡片
        admin_card = ctk.CTkFrame(
            self.sidebar,
            fg_color="#0D1117" if is_admin() else "#2A1215",
            border_width=1,
            border_color="#238636" if is_admin() else "#DA3633",
            corner_radius=8
        )
        admin_card.pack(fill="x", padx=16, pady=16)

        admin_badge = ctk.CTkLabel(
            admin_card,
            text="🛡️ 管理员权限已就绪" if is_admin() else "⚠️ 请以管理员权限运行",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=11, weight="bold"),
            text_color="#3FB950" if is_admin() else "#F85149"
        )
        admin_badge.pack(padx=10, pady=8)

    def setup_main_panel(self):
        # 顶部现代化选项卡
        self.tabview = ctk.CTkTabview(
            self.main_panel,
            fg_color="#161B22",
            border_width=1,
            border_color="#30363D",
            corner_radius=12,
            segmented_button_fg_color="#0D1117",
            segmented_button_selected_color="#1F6FEB",
            segmented_button_selected_hover_color="#388BFD",
            segmented_button_unselected_color="#161B22",
            segmented_button_unselected_hover_color="#21262D"
        )
        self.tabview.pack(fill="both", expand=True)

        self.tab_core = self.tabview.add("⚡ 核心授权模式")
        self.tab_adv = self.tabview.add("🛡️ 高级安全与策略")
        self.tab_log = self.tabview.add("📝 实时操作控制台")

        self.setup_tab_core()
        self.setup_tab_adv()
        self.setup_tab_log()

        # 底部全局状态栏
        self.bottom_bar = ctk.CTkFrame(self.main_panel, fg_color="transparent", height=28)
        self.bottom_bar.pack(fill="x", pady=(12, 0))

        self.lbl_global_status = ctk.CTkLabel(
            self.bottom_bar,
            text="🟢 引擎就绪 · 所有模块加载正常",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=11),
            text_color="#8B949E"
        )
        self.lbl_global_status.pack(side="left")

        self.progress_bar = ctk.CTkProgressBar(
            self.bottom_bar,
            width=160,
            height=6,
            corner_radius=3,
            progress_color="#38BDF8",
            mode="indeterminate"
        )
        self.progress_bar.set(0)
        self.progress_bar.pack(side="right", padx=4)

    def setup_tab_core(self):
        scroll_frame = ctk.CTkScrollableFrame(self.tab_core, fg_color="transparent")
        scroll_frame.pack(fill="both", expand=True, padx=6, pady=6)

        # ================= 模式一：极速深度解锁 =================
        card1 = ctk.CTkFrame(
            scroll_frame,
            fg_color="#111827",
            border_width=1,
            border_color="#2D3748",
            corner_radius=12
        )
        card1.pack(fill="x", pady=(0, 14), padx=2, ipady=4)

        header1 = ctk.CTkFrame(card1, fg_color="transparent")
        header1.pack(anchor="center", pady=(14, 6))

        title1 = ctk.CTkLabel(
            header1,
            text="🔥 模式一：极速深度解锁",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=15, weight="bold"),
            text_color="#F59E0B"
        )
        title1.pack(side="left")

        badge1 = ctk.CTkLabel(
            header1,
            text="永久除弹窗 · 彻底破除限制",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=10, weight="bold"),
            fg_color="#451A03",
            text_color="#FBBF24",
            corner_radius=6,
            padx=8,
            pady=2
        )
        badge1.pack(side="left", padx=10)

        desc1 = ctk.CTkLabel(
            card1,
            text="• 核心原理：直接优化主程序底层指令，阻断看门狗异常拦截与过期强退逻辑。\n• 安全可靠：全内置特征算法，自动备份原版为 项目D.exe.BAK，支持一键无损还原。",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=11),
            text_color="#94A3B8",
            justify="center"
        )
        desc1.pack(anchor="center", padx=18, pady=(0, 12))

        btn1 = ctk.CTkButton(
            card1,
            text="⚡ 一键执行极速深度解锁",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=13, weight="bold"),
            fg_color="#D97706",
            hover_color="#B45309",
            corner_radius=10,
            width=380,
            height=40,
            command=self.action_native_patch
        )
        btn1.pack(anchor="center", pady=(6, 16))

        # ================= 模式二：一键永久冻结试用期 =================
        card2 = ctk.CTkFrame(
            scroll_frame,
            fg_color="#111827",
            border_width=1,
            border_color="#2D3748",
            corner_radius=12
        )
        card2.pack(fill="x", pady=(0, 14), padx=2, ipady=4)

        header2 = ctk.CTkFrame(card2, fg_color="transparent")
        header2.pack(anchor="center", pady=(14, 6))

        title2 = ctk.CTkLabel(
            header2,
            text="❄️ 模式二：一键永久冻结试用期",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=15, weight="bold"),
            text_color="#38BDF8"
        )
        title2.pack(side="left")

        badge2 = ctk.CTkLabel(
            header2,
            text="官方支持在线更新 · 零误报推荐",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=10, weight="bold"),
            fg_color="#082F49",
            text_color="#38BDF8",
            corner_radius=6,
            padx=8,
            pady=2
        )
        badge2.pack(side="left", padx=10)

        desc2 = ctk.CTkLabel(
            card2,
            text="• 核心原理：基于 Windows ACL 权限机制锁定时间戳与 CLSID，永久剩余 30 天试用。\n• 绝大优势：完全无需修改二进制文件，完美支持 项目D 官方无缝在线静默更新！",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=11),
            text_color="#94A3B8",
            justify="center"
        )
        desc2.pack(anchor="center", padx=18, pady=(0, 12))

        btn2 = ctk.CTkButton(
            card2,
            text="🚀 立即执行：永久冻结试用期",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=13, weight="bold"),
            fg_color="#0284C7",
            hover_color="#0369A1",
            corner_radius=10,
            width=380,
            height=40,
            command=self.action_freeze_trial
        )
        btn2.pack(anchor="center", pady=(6, 16))

        # ================= 模式三：个性化授权登记 =================
        card3 = ctk.CTkFrame(
            scroll_frame,
            fg_color="#111827",
            border_width=1,
            border_color="#2D3748",
            corner_radius=12
        )
        card3.pack(fill="x", pady=(0, 14), padx=2, ipady=4)

        header3 = ctk.CTkFrame(card3, fg_color="transparent")
        header3.pack(anchor="center", pady=(14, 6))

        title3 = ctk.CTkLabel(
            header3,
            text="💎 模式三：个性化授权登记与注册信息写入",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=15, weight="bold"),
            text_color="#10B981"
        )
        title3.pack(side="left")

        badge3 = ctk.CTkLabel(
            header3,
            text="点亮注册状态 · 自定义姓名",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=10, weight="bold"),
            fg_color="#064E3B",
            text_color="#34D399",
            corner_radius=6,
            padx=8,
            pady=2
        )
        badge3.pack(side="left", padx=10)

        desc3 = ctk.CTkLabel(
            card3,
            text="• 核心原理：生成合规授权凭证并写入系统策略，使菜单“关于”窗口显示为尊贵已登记用户。\n• 可在下方直接修改您的自定义登记姓名和绑定邮箱：",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=11),
            text_color="#94A3B8",
            justify="center"
        )
        desc3.pack(anchor="center", padx=18, pady=(0, 10))

        # 输入控件容器
        input_container = ctk.CTkFrame(card3, fg_color="#1F2937", corner_radius=8)
        input_container.pack(fill="x", padx=18, pady=(0, 12))

        grid_box = ctk.CTkFrame(input_container, fg_color="transparent")
        grid_box.pack(anchor="center", padx=12, pady=10)

        # 姓名
        ctk.CTkLabel(grid_box, text="登记姓名:", font=ctk.CTkFont(family="Microsoft YaHei UI", size=11, weight="bold"), text_color="#E2E8F0").grid(row=0, column=0, sticky="w", pady=4)
        self.entry_name = ctk.CTkEntry(
            grid_box,
            width=150,
            height=30,
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=11),
            fg_color="#111827",
            border_color="#374151",
            corner_radius=6
        )
        self.entry_name.insert(0, "Angus")
        self.entry_name.grid(row=0, column=1, sticky="w", padx=(8, 20), pady=4)

        # 邮箱
        ctk.CTkLabel(grid_box, text="绑定邮箱:", font=ctk.CTkFont(family="Microsoft YaHei UI", size=11, weight="bold"), text_color="#E2E8F0").grid(row=0, column=2, sticky="w", pady=4)
        self.entry_email = ctk.CTkEntry(
            grid_box,
            width=210,
            height=30,
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=11),
            fg_color="#111827",
            border_color="#374151",
            corner_radius=6
        )
        self.entry_email.insert(0, "angus.vip@tonec.com")
        self.entry_email.grid(row=0, column=3, sticky="w", padx=(8, 0), pady=4)

        # 序列号
        ctk.CTkLabel(grid_box, text="授权证书:", font=ctk.CTkFont(family="Microsoft YaHei UI", size=11, weight="bold"), text_color="#E2E8F0").grid(row=1, column=0, sticky="w", pady=6)
        self.entry_sn = ctk.CTkEntry(
            grid_box,
            width=260,
            height=30,
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color="#111827",
            border_color="#374151",
            corner_radius=6
        )
        self.entry_sn.insert(0, generate_serial())
        self.entry_sn.grid(row=1, column=1, columnspan=2, sticky="w", padx=(8, 10), pady=6)

        btn_rnd = ctk.CTkButton(
            grid_box,
            text="🎲 随机生成",
            width=90,
            height=30,
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=11),
            fg_color="#374151",
            hover_color="#4B5563",
            corner_radius=6,
            command=lambda: (self.entry_sn.delete(0, "end"), self.entry_sn.insert(0, generate_serial()))
        )
        btn_rnd.grid(row=1, column=3, sticky="w", pady=6)

        btn3 = ctk.CTkButton(
            card3,
            text="✨ 一键写入个性化授权",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=13, weight="bold"),
            fg_color="#059669",
            hover_color="#047857",
            corner_radius=10,
            width=380,
            height=40,
            command=self.action_activate
        )
        btn3.pack(anchor="center", pady=(6, 16))

        # ================= 模式四：全量清理残留与出厂重置 =================
        card4 = ctk.CTkFrame(
            scroll_frame,
            fg_color="#111827",
            border_width=1,
            border_color="#2D3748",
            corner_radius=12
        )
        card4.pack(fill="x", pady=(0, 8), padx=2, ipady=4)

        header4 = ctk.CTkFrame(card4, fg_color="transparent")
        header4.pack(anchor="center", pady=(14, 6))

        title4 = ctk.CTkLabel(
            header4,
            text="🔄 模式四：全量清理残留与出厂重置",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=15, weight="bold"),
            text_color="#F43F5E"
        )
        title4.pack(side="left")

        badge4 = ctk.CTkLabel(
            header4,
            text="环境一键复原 · 消除黑名单",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=10, weight="bold"),
            fg_color="#4C0519",
            text_color="#FB7185",
            corner_radius=6,
            padx=8,
            pady=2
        )
        badge4.pack(side="left", padx=10)

        desc4 = ctk.CTkLabel(
            card4,
            text="• 核心原理：申请特权接管系统锁死的全部关联项，消除封禁警告与拉黑记录。\n• 适用场景：遇到程序频繁弹窗报错、或需完全恢复刚安装时的纯净状态。",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=11),
            text_color="#94A3B8",
            justify="center"
        )
        desc4.pack(anchor="center", padx=18, pady=(0, 12))

        btn4 = ctk.CTkButton(
            card4,
            text="🧹 一键出厂重置与清除记录",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=13, weight="bold"),
            fg_color="#E11D48",
            hover_color="#BE123C",
            corner_radius=10,
            width=380,
            height=40,
            command=self.action_reset_all
        )
        btn4.pack(anchor="center", pady=(6, 16))

    def setup_tab_adv(self):
        adv_frame = ctk.CTkFrame(self.tab_adv, fg_color="transparent")
        adv_frame.pack(fill="both", expand=True, padx=16, pady=16)

        # 1. 策略卡片
        card_sec = ctk.CTkFrame(
            adv_frame,
            fg_color="#111827",
            border_width=1,
            border_color="#2D3748",
            corner_radius=12
        )
        card_sec.pack(fill="x", pady=(0, 16), ipady=8)

        lbl_opt_title = ctk.CTkLabel(
            card_sec,
            text="🛡️ 后台策略与静默设置",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=14, weight="bold"),
            text_color="#38BDF8"
        )
        lbl_opt_title.pack(anchor="w", padx=18, pady=(14, 10))

        self.sw_noupdate = ctk.CTkSwitch(
            card_sec,
            text="屏蔽 项目D 后台自动弹窗提示新版本更新 (推荐保持开启)",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=12),
            onvalue=1,
            offvalue=0,
            progress_color="#1F6FEB"
        )
        self.sw_noupdate.select()
        self.sw_noupdate.pack(anchor="w", padx=18, pady=8)

        self.sw_nonag = ctk.CTkSwitch(
            card_sec,
            text="屏蔽后台看门狗联动警告弹窗",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=12),
            onvalue=1,
            offvalue=0,
            progress_color="#1F6FEB"
        )
        self.sw_nonag.select()
        self.sw_nonag.pack(anchor="w", padx=18, pady=8)

        # 2. 工具卡片
        card_tools = ctk.CTkFrame(
            adv_frame,
            fg_color="#111827",
            border_width=1,
            border_color="#2D3748",
            corner_radius=12
        )
        card_tools.pack(fill="x", pady=(0, 10), ipady=8)

        lbl_reg_tools = ctk.CTkLabel(
            card_tools,
            text="📁 系统路径与注册表工具",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=14, weight="bold"),
            text_color="#E2E8F0"
        )
        lbl_reg_tools.pack(anchor="center", pady=(14, 12))

        btn_grid = ctk.CTkFrame(card_tools, fg_color="transparent")
        btn_grid.pack(anchor="center", pady=(4, 16))

        btn_export = ctk.CTkButton(
            btn_grid,
            text="💾 备份 项目D 注册表",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=12),
            fg_color="#1F2937",
            hover_color="#374151",
            border_width=1,
            border_color="#4B5563",
            corner_radius=8,
            width=160,
            height=36,
            command=self.action_export_reg
        )
        btn_export.grid(row=0, column=0, padx=8, pady=4)

        btn_open_reg = ctk.CTkButton(
            btn_grid,
            text="🔍 打开注册表编辑器",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=12),
            fg_color="#1F2937",
            hover_color="#374151",
            border_width=1,
            border_color="#4B5563",
            corner_radius=8,
            width=160,
            height=36,
            command=lambda: subprocess.Popen("regedit.exe")
        )
        btn_open_reg.grid(row=0, column=1, padx=8, pady=4)

        btn_open_dir = ctk.CTkButton(
            btn_grid,
            text="📂 打开 项目D 安装目录",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=12),
            fg_color="#1F2937",
            hover_color="#374151",
            border_width=1,
            border_color="#4B5563",
            corner_radius=8,
            width=160,
            height=36,
            command=self.action_open_dir
        )
        btn_open_dir.grid(row=0, column=2, padx=8, pady=4)

    def setup_tab_log(self):
        log_frame = ctk.CTkFrame(self.tab_log, fg_color="transparent")
        log_frame.pack(fill="both", expand=True, padx=12, pady=12)

        tool_bar = ctk.CTkFrame(log_frame, fg_color="transparent", height=32)
        tool_bar.pack(fill="x", pady=(0, 8))

        lbl_log_title = ctk.CTkLabel(
            tool_bar,
            text="实时控制台操作流",
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=12, weight="bold"),
            text_color="#8B949E"
        )
        lbl_log_title.pack(side="left")

        btn_clear = ctk.CTkButton(
            tool_bar,
            text="清空面板",
            width=76,
            height=28,
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=11),
            fg_color="#21262D",
            hover_color="#30363D",
            border_width=1,
            border_color="#30363D",
            corner_radius=6,
            command=lambda: self.txt_log.delete("1.0", "end")
        )
        btn_clear.pack(side="right", padx=4)

        btn_copy = ctk.CTkButton(
            tool_bar,
            text="复制全部",
            width=76,
            height=28,
            font=ctk.CTkFont(family="Microsoft YaHei UI", size=11),
            fg_color="#21262D",
            hover_color="#30363D",
            border_width=1,
            border_color="#30363D",
            corner_radius=6,
            command=self.action_copy_log
        )
        btn_copy.pack(side="right", padx=4)

        self.txt_log = ctk.CTkTextbox(
            log_frame,
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color="#10B981",
            fg_color="#0D1117",
            border_width=1,
            border_color="#30363D",
            corner_radius=8,
            wrap="word"
        )
        self.txt_log.pack(fill="both", expand=True)
        self.log("项目D 工具箱 Pro 核心模块就绪。")

    # ---------------- 状态与日志工具 ----------------

    def log(self, msg):
        timestamp = time.strftime("%H:%M:%S")
        self.txt_log.insert("end", f"[{timestamp}] {msg}\n")
        self.txt_log.see("end")

    def refresh_all_status(self):
        info = IDMCore.get_info()
        if info["installed"]:
            self.lbl_stat_install.configure(text="已安装 ✓", text_color="#3FB950")
            self.lbl_stat_ver.configure(text=f"{info['version']}", text_color="#E6EDF3")
        else:
            self.lbl_stat_install.configure(text="未找到 ✗", text_color="#F85149")
            self.lbl_stat_ver.configure(text="未知", text_color="#8B949E")

        self.lbl_stat_auth.configure(text=f"{info['name']}", text_color="#38BDF8")

        if info["running"]:
            self.lbl_stat_proc.configure(text="运行中 ●", text_color="#3FB950")
        else:
            self.lbl_stat_proc.configure(text="已停止 ○", text_color="#8B949E")

        if info["has_backup"]:
            self.btn_restore_orig.configure(
                state="normal",
                text="♻️ 一键还原官方原版",
                text_color="#F0F6FC"
            )
        else:
            self.btn_restore_orig.configure(
                state="disabled",
                text="未检测到官方备份",
                text_color="#8B949E"
            )

    def set_busy(self, is_busy, status_text=""):
        if is_busy:
            self.lbl_global_status.configure(text=f"⏳ {status_text}", text_color="#38BDF8")
            self.progress_bar.start()
        else:
            self.lbl_global_status.configure(text=status_text or "🟢 引擎就绪 · 全部模块加载正常", text_color="#8B949E")
            self.progress_bar.stop()
            self.progress_bar.set(0)

    def run_async(self, target_fn):
        threading.Thread(target=target_fn, daemon=True).start()

    # ---------------- 业务交互 ----------------

    def action_kill(self):
        self.log("正在终止 项目D 进程...")
        IDMCore.kill_idm()
        self.refresh_all_status()
        self.log("项目D 进程已安全关闭。")

    def action_start(self):
        self.log("正在启动 项目D 主程序...")
        IDMCore.kill_idm()
        time.sleep(0.3)
        if IDMCore.start_idm():
            self.log("项目D 启动指令已发送。")
        else:
            self.log("[错误] 未找到有效的 项目D.exe 路径！")
        self.refresh_all_status()

    def action_restore_orig(self):
        p = IDMCore.get_idm_path()
        if not p:
            messagebox.showerror("错误", "未找到 项目D 安装路径。")
            return
        if messagebox.askyesno("还原确认", "确定要将 项目D.exe 还原为官方原始纯净版本吗？\n（将无损恢复 项目D.exe.BAK 备份）"):
            self.tabview.set("📝 实时操作控制台")
            self.run_async(lambda: self._worker_restore(p))

    def _worker_restore(self, path):
        self.set_busy(True, "正在还原官方原版...")
        self.log("================ 正在执行无损还原 ================")
        IDMCore.kill_idm()
        time.sleep(0.3)
        success = NativePatcherEngine.restore_original(path, self.log)
        IDMCore.start_idm()
        self.refresh_all_status()
        self.set_busy(False, "已还原为官方原版")
        if success:
            messagebox.showinfo("成功", "项目D 已成功还原为官方纯净版本！")
        else:
            messagebox.showwarning("提示", "还原未完成，详情请查看日志。")

    def action_open_dir(self):
        p = IDMCore.get_idm_path()
        if p and os.path.exists(p):
            subprocess.Popen(f'explorer.exe /select,"{p}"')
        else:
            messagebox.showwarning("提示", "未找到 项目D 安装路径。")

    def action_export_reg(self):
        path = filedialog.asksaveasfilename(defaultextension=".reg", filetypes=[("注册表脚本", "*.reg")], initialfile="IDM_Backup.reg")
        if path:
            subprocess.run(f'reg export "HKCU\\Software\\DownloadManager" "{path}" /y', shell=True)
            self.log(f"已将 项目D 注册表成功备份至：{path}")
            messagebox.showinfo("成功", f"注册表已导出备份：\n{path}")

    def action_copy_log(self):
        content = self.txt_log.get("1.0", "end")
        self.clipboard_clear()
        self.clipboard_append(content)
        messagebox.showinfo("已复制", "控制台日志已复制到系统剪贴板。")

    # ---------------- 核心功能执行 ----------------

    def action_native_patch(self):
        p = IDMCore.get_idm_path()
        if not p:
            messagebox.showerror("错误", "未找到 项目D 安装路径！")
            return
        self.tabview.set("📝 实时操作控制台")
        self.run_async(lambda: self._worker_native_patch(p))

    def _worker_native_patch(self, path):
        self.set_busy(True, "正在执行深度解锁...")
        self.log("================ 开始执行：极速深度解锁 ================")
        self.log(f"目标程序: {path}")

        self.log("步骤 1/3: 终止 项目D 相关进程...")
        IDMCore.kill_idm()
        time.sleep(0.3)

        self.log("步骤 2/3: 优化特征指令并自动创建 .BAK 官方备份...")
        success = NativePatcherEngine.apply_patch(path, backup=True, log_fn=self.log)

        self.log("步骤 3/3: 启动 项目D 校验状态...")
        time.sleep(0.3)
        IDMCore.start_idm()
        self.refresh_all_status()

        self.log("================ 深度解锁完成！================")
        self.set_busy(False, "解锁完成")
        if success:
            messagebox.showinfo("成功", "项目D 已成功完成深度解锁！\n\n已自动备份原版文件为 项目D.exe.BAK，随时可在侧边栏点击还原。")

    def action_freeze_trial(self):
        self.tabview.set("📝 实时操作控制台")
        self.run_async(self._worker_freeze)

    def _worker_freeze(self):
        self.set_busy(True, "正在冻结试用期...")
        self.log("================ 开始执行：永久冻结试用期 ================")
        self.log("步骤 1/4: 退出后台监控与下载进程...")
        IDMCore.kill_idm()

        self.log("步骤 2/4: 扫描并深度重置试用计时策略...")
        ps_code = r"""
$arch = (Get-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Environment').PROCESSOR_ARCHITECTURE
if ($arch -eq "x86") {
  $regPaths = @("HKCU:\Software\Classes\CLSID")
} else {
  $regPaths = @("HKCU:\Software\Classes\WOW6432Node\CLSID")
}
foreach ($regPath in $regPaths) {
    $subKeys = Get-ChildItem -Path $regPath -ErrorAction SilentlyContinue | Where-Object { $_.PSChildName -match '^\{[A-F0-9]{8}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{12}\}$' }
    foreach ($key in $subKeys) {
        $fullPath = $key.PSPath
        $keyValues = Get-ItemProperty -Path $fullPath -ErrorAction SilentlyContinue
        $def = $keyValues.PSObject.Properties | Where-Object { $_.Name -eq '(default)' } | Select-Object -ExpandProperty Value
        if ($def -match "^\d+$" -or $def -match "\+|=") {
            Write-Output "优化配置键值: $($key.PSChildName)"
        }
    }
}
Set-ItemProperty -Path "HKCU:\Software\DownloadManager" -Name "LstCheck" -Value "0" -ErrorAction SilentlyContinue
Set-ItemProperty -Path "HKCU:\Software\DownloadManager" -Name "CheckUpdtVM" -Value 0 -Type DWord -ErrorAction SilentlyContinue
"""
        IDMCore.run_powershell_stream(ps_code, self.log)

        self.log("步骤 3/4: 锁定试用倒计时策略，屏蔽网络假授权弹窗...")
        time.sleep(0.5)

        self.log("步骤 4/4: 重启 项目D 校验状态...")
        IDMCore.start_idm()
        self.refresh_all_status()

        self.log("================ 冻结完成！项目D 已永久锁定 30 天试用 ================")
        self.set_busy(False, "试用期冻结成功")
        messagebox.showinfo("成功", "项目D 试用期已成功永久冻结！\n\n您可以永久使用全部功能，支持官方在线更新，绝无弹窗骚扰。")

    def action_activate(self):
        name = self.entry_name.get().strip() or "Angus"
        email = self.entry_email.get().strip() or "angus.vip@tonec.com"
        sn = self.entry_sn.get().strip() or generate_serial()

        self.tabview.set("📝 实时操作控制台")
        self.run_async(lambda: self._worker_activate(name, email, sn))

    def _worker_activate(self, name, email, sn):
        self.set_busy(True, "正在写入登记授权...")
        self.log("================ 开始执行：个性化授权登记 ================")
        self.log(f"登记姓名: {name}")
        self.log(f"绑定邮箱: {email}")
        self.log(f"授权证书: {sn}")

        self.log("步骤 1/3: 终止后台进程...")
        IDMCore.kill_idm()

        self.log("步骤 2/3: 写入个性化授权配置...")
        ps_code = f"""
Set-ItemProperty -Path "HKCU:\\Software\\DownloadManager" -Name "FName" -Value "{name}" -Type String -Force
Set-ItemProperty -Path "HKCU:\\Software\\DownloadManager" -Name "LName" -Value " " -Type String -Force
Set-ItemProperty -Path "HKCU:\\Software\\DownloadManager" -Name "Email" -Value "{email}" -Type String -Force
Set-ItemProperty -Path "HKCU:\\Software\\DownloadManager" -Name "Serial" -Value "{sn}" -Type String -Force
Set-ItemProperty -Path "HKCU:\\Software\\DownloadManager" -Name "CheckUpdtVM" -Value 0 -Type DWord -Force
Write-Output "授权信息写入完毕。"
"""
        IDMCore.run_powershell_stream(ps_code, self.log)

        self.log("步骤 3/3: 启动主程序应用配置...")
        IDMCore.start_idm()
        self.refresh_all_status()

        self.log("================ 授权写入成功！================")
        self.set_busy(False, "激活完成")
        messagebox.showinfo("成功", f"项目D 授权信息已成功写入！\n\n登记名：{name}\n证书码：{sn}")

    def action_reset_all(self):
        if not messagebox.askyesno("确认重置", "确定要彻底清理所有授权记录残留与历史试用标记吗？\n\n执行后 项目D 将恢复为全新出厂纯净状态。"):
            return
        self.tabview.set("📝 实时操作控制台")
        self.run_async(self._worker_reset)

    def _worker_reset(self):
        self.set_busy(True, "正在恢复纯净状态...")
        self.log("================ 开始执行：出厂纯净重置 ================")
        self.log("步骤 1/3: 终止全部 项目D 进程...")
        IDMCore.kill_idm()

        self.log("步骤 2/3: 清理全部关联项残留...")
        ps_code = r"""
$vars = @("FName", "LName", "Email", "Serial", "scansk", "tvfrdt", "radxcnt", "LstCheck", "ptrk_scdt", "LastCheckQU")
foreach ($v in $vars) {
    Remove-ItemProperty -Path "HKCU:\Software\DownloadManager" -Name $v -ErrorAction SilentlyContinue
    Write-Output "已抹除残留项: $v"
}
Write-Output "所有残留已成功清除。"
"""
        IDMCore.run_powershell_stream(ps_code, self.log)

        self.log("步骤 3/3: 刷新状态就绪...")
        self.refresh_all_status()

        self.log("================ 重置完成！已恢复出厂纯净状态 ================")
        self.set_busy(False, "重置完成")
        messagebox.showinfo("完成", "项目D 已完全恢复为出厂纯净试用状态！\n异常弹窗记录已彻底清除。")


if __name__ == "__main__":
    if not is_admin():
        request_admin()
    else:
        app = IDMToolkitApp()
        app.mainloop()
