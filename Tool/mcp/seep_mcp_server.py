#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
seep - AI-Native Reverse Engineering & Security Analysis MCP Server
整合 Radare2 跨架构二进制逆向、JADX/Apktool/Smali 安卓逆向、
动态 Hook 生成以及 ReverseLab 183+ 攻防知识库与 CTF 战术模板。
"""

import os
import sys
import json
import re
import glob
import shutil
import signal
import zipfile
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

try:
    from mcp.server.mcpserver import MCPServer
except ImportError:
    from mcp.server.fastmcp import FastMCP as MCPServer

# ---------------------------------------------------------------------------
# 基础路径定义与环境初始化
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOOL_DIR = os.path.join(BASE_DIR, "Tool")
SAFE_DIR = os.path.join(TOOL_DIR, "safe")
R2_BIN_DIR = os.path.join(SAFE_DIR, "radare2", "bin")

def _resolve_binary(tool_name: str) -> str:
    """跨平台解析可执行工具路径（Windows 优先内置 exe，Linux/macOS 优先查找系统 PATH，fallback 回内置）"""
    exe_name = f"{tool_name}.exe" if sys.platform == "win32" else tool_name
    built_in = os.path.join(R2_BIN_DIR, exe_name)
    if os.path.isfile(built_in) and (sys.platform == "win32" or os.access(built_in, os.X_OK)):
        return built_in
    which_path = shutil.which(tool_name)
    if which_path:
        return which_path
    return built_in

R2_EXE = _resolve_binary("radare2")
RABIN2_EXE = _resolve_binary("rabin2")
RADIFF2_EXE = _resolve_binary("radiff2")
RASM2_EXE = _resolve_binary("rasm2")
RAHASH2_EXE = _resolve_binary("rahash2")

def _resolve_jadx() -> str:
    """跨平台解析 JADX 启动脚本"""
    if sys.platform == "win32":
        bat = os.path.join(SAFE_DIR, "jadx", "bin", "jadx.bat")
        return bat if os.path.isfile(bat) else (shutil.which("jadx") or bat)
    else:
        sh = os.path.join(SAFE_DIR, "jadx", "bin", "jadx")
        return sh if os.path.isfile(sh) else (shutil.which("jadx") or sh)

JADX_BAT = _resolve_jadx()
APKTOOL_JAR = os.path.join(SAFE_DIR, "apktool", "apktool.jar")
# 注意：apktool 一律以 `java -jar apktool.jar` 调用（见 seep_apk_unpack），
# 不存在跨平台启动脚本；早期这里还定义过一个 APKTOOL_BAT，在 Unix 上恒指向不存在的
# 文件，容易让人误判 "apktool 缺失"，已移除。

KB_DIR = os.path.join(TOOL_DIR, "reverselab", "kb")
LLMS_TXT = os.path.join(TOOL_DIR, "reverselab", "docs", "llms.txt")
HOOK_TEMPLATES_DIR = os.path.join(SAFE_DIR, "hook-mcp", "templates")

# 外部 Android 工具箱（Frida/objection/frida-dexdump/APKiD/Aotopsy）。
# 默认根目录按平台区分 —— 在 Linux/macOS 上沿用 "D:\Tool\Android" 是无意义的，
# 而且会让 seep_status 报出一个根本不存在的路径。
#   Windows : D:\Tool\Android      （Tool/scripts/android/install-android-toolbox.ps1）
#   Unix    : ~/.seep/android        （setup/install-capabilities.sh）
ANDROID_TOOLBOX_DIR = os.environ.get(
    "SEEP_ANDROID_TOOLBOX",
    r"D:\Tool\Android" if sys.platform == "win32" else os.path.join(os.path.expanduser("~"), ".seep", "android"),
)

# 外部 Web / 流媒体工具箱（ffmpeg / ffprobe）。
#   Windows : D:\Tool\Web          （Tool/scripts/web/install-web-toolbox.ps1）
#   Unix    : ~/.seep/web            （setup/install-capabilities.sh）
WEB_TOOLBOX_DIR = os.environ.get(
    "SEEP_WEB_TOOLBOX",
    r"D:\Tool\Web" if sys.platform == "win32" else os.path.join(os.path.expanduser("~"), ".seep", "web"),
)
# 仓库内取证脚本位于 <repo>\Tool\scripts\web；BASE_DIR 是 <repo>\Tool\mcp
WEB_SCRIPT_DIR = os.path.join(os.path.dirname(BASE_DIR), "scripts", "web")


def _resolve_web_tool(name: str) -> Optional[str]:
    """解析 Web 工具箱内工具路径（真实 exe 优先于 .cmd 垫片 → 系统 PATH）。"""
    exe = f"{name}.exe"
    candidates = [
        os.path.join(WEB_TOOLBOX_DIR, "ffmpeg", "bin", exe),
        os.path.join(WEB_TOOLBOX_DIR, "bin", exe),
        os.path.join(WEB_TOOLBOX_DIR, "bin", f"{name}.cmd"),
        os.path.join(WEB_TOOLBOX_DIR, exe),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return shutil.which(name)


def _web_toolbox_status() -> Dict[str, Any]:
    names = ["ffmpeg", "ffprobe", "nuclei", "ffuf", "whatweb", "node"]
    return {n: (_resolve_web_tool(n) or None) for n in names}


def _find_powershell() -> Optional[str]:
    """优先 pwsh(7+)，回退 Windows PowerShell 5.1。"""
    for cand in ("pwsh", "powershell"):
        p = shutil.which(cand)
        if p:
            return p
    for p in (r"C:\Program Files\PowerShell\7\pwsh.exe",
              r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"):
        if os.path.isfile(p):
            return p
    return None


def _run_web_script(script_name: str, args: List[str], timeout: int = 600) -> Tuple[bool, str, Optional[dict]]:
    """调用 Tool/scripts/web 下的取证脚本（统一用 -Json 模式），返回 (ok, raw, parsed_json)。"""
    ps = _find_powershell()
    if not ps:
        if sys.platform == "win32":
            hint = "请确认 PowerShell 未被禁用，或用 Setup/repair-tools.ps1 修复"
        else:
            hint = ("Web 取证脚本是 PowerShell 实现，Unix 需自行安装 PowerShell 7：\n"
                    "  macOS : brew install --cask powershell\n"
                    "  Debian: sudo apt-get install -y powershell\n"
                    "  Fedora: sudo dnf install -y powershell\n"
                    "（Windows-only 的能力；详见 MANUAL/CROSS-PLATFORM.md）")
        return False, "[ERROR]: 未找到 PowerShell（pwsh / powershell）—— " + hint, None
    script_path = os.path.join(WEB_SCRIPT_DIR, script_name)
    if not os.path.isfile(script_path):
        return False, f"[ERROR]: 脚本不存在: {script_path}", None

    cmd = [ps, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script_path, "-Json"] + args
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return False, f"[ERROR]: 脚本超时 (>{timeout}s): {script_name}", None

    raw = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    payload = None
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            payload = json.loads(raw[start:end + 1])
        except Exception:
            payload = None
    if payload is None:
        return False, _clean_r2_output(raw), None
    return True, raw, payload


def _resolve_android_tool(name: str) -> Optional[str]:
    """解析 Android 外部工具箱内工具路径（bin 垫片 → venv → aotopsy → platform-tools → 系统 PATH）。"""
    candidates = [
        os.path.join(ANDROID_TOOLBOX_DIR, "bin", f"{name}.cmd"),
        os.path.join(ANDROID_TOOLBOX_DIR, "frida-env", "Scripts", f"{name}.exe"),
        os.path.join(ANDROID_TOOLBOX_DIR, "aotopsy", f"{name}.exe"),
        os.path.join(ANDROID_TOOLBOX_DIR, "platform-tools", f"{name}.exe"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    return shutil.which(name)


def _android_toolbox_status() -> Dict[str, Any]:
    names = ["frida", "frida-ps", "frida-trace", "objection", "frida-dexdump", "apkid", "aotopsy", "adb"]
    return {n: (_resolve_android_tool(n) or None) for n in names}

# 将 r2 bin 目录添加到 PATH 中，确保子进程加载依赖 dll
if os.path.isdir(R2_BIN_DIR) and R2_BIN_DIR not in os.environ.get("PATH", ""):
    os.environ["PATH"] = R2_BIN_DIR + os.pathsep + os.environ.get("PATH", "")

# ---------------------------------------------------------------------------
# MCP Server 实例
# ---------------------------------------------------------------------------
server = MCPServer(
    "seep",
    instructions="""seep 是一个专为安全分析师与 AI Agent 设计的全能逆向工程与 CTF 战术 MCP Server。
能力包含：
1. 二进制分析与逆向 (Radare2 / Rabin2 / Radiff2 / Rasm2)
2. Android APK / DEX 反编译、解包与 Smali 检索 (JADX, Apktool)
3. Android 加固指纹与 Flutter AOT 分析 (APKiD, Aotopsy) 及动态工具链桥接 (Frida, objection, frida-dexdump)
4. Web / 流媒体取证 (HLS 解密可行性 + DRM 判定 + 防盗链举证 + TVBox/CatVod spider 三入口提取)
5. 动态 Hook 插件自动生成 (Frida JS, LSPilot / BeanShell)
6. ReverseLab 289+ 逆向与 Web/PE/CVE 攻防战术知识库检索与即用 Payload
"""
)

# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------
def _run_cmd(cmd: List[str], cwd: Optional[str] = None, timeout: int = 60) -> str:
    """运行外部命令并返回标准输出或捕获错误"""
    try:
        proc = subprocess.run(
            cmd,
            # 关键：必须显式 DEVNULL。以 stdio 传输运行时，服务端自己的 stdin 是
            # 客户端持有的 JSON-RPC 管道；子进程若继承它，Python 子解释器会卡在
            # 启动阶段（业务代码一行未执行），工具表现为永久挂起。
            # 详见 issue #13 / Tool/mcp/test_stdio_smoke.py。
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout
        )
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        if proc.returncode != 0 and not out:
            return f"[ERROR code {proc.returncode}]: {err}"
        if out and err:
            return f"{out}\n[STDERR]: {err}"
        return out or err or "[Success, no output]"
    except subprocess.TimeoutExpired:
        return f"[ERROR]: Command timed out after {timeout} seconds."
    except Exception as e:
        return f"[ERROR]: Exception executing command: {str(e)}"

def _clean_r2_output(text: str) -> str:
    """移除 ANSI 颜色控制字符"""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

def _find_java() -> Optional[str]:
    """寻找 Java 运行时可执行路径（跨平台探测：PATH -> macOS JVM -> Linux JVM -> Windows JDK）"""
    if shutil.which("java"):
        return "java"
    candidates = [
        # Windows
        r"D:\Tool\JDK\bin\java.exe",
        r"D:\Tool\Android Studio\jbr\bin\java.exe",
        r"C:\Program Files\Java",
        r"C:\Program Files\Eclipse Adoptium",
        r"C:\Program Files\Microsoft",
        # macOS
        "/Library/Java/JavaVirtualMachines",
        "/System/Library/Frameworks/JavaVM.framework",
        "/opt/homebrew/opt/openjdk/bin/java",
        "/usr/local/opt/openjdk/bin/java",
        # Linux
        "/usr/lib/jvm",
        "/usr/java"
    ]
    for c in candidates:
        if os.path.isfile(c) and (sys.platform == "win32" or os.access(c, os.X_OK)):
            return c
        if os.path.isdir(c):
            bin_name = "java.exe" if sys.platform == "win32" else "java"
            for root, _, files in os.walk(c):
                if bin_name in files:
                    full_p = os.path.join(root, bin_name)
                    if sys.platform == "win32" or os.access(full_p, os.X_OK):
                        return full_p
    return None

# ---------------------------------------------------------------------------
# 1. 状态与环境工具
# ---------------------------------------------------------------------------
@server.tool()
def seep_status() -> str:
    """检查 seep 逆向工具链状态、内置组件就绪度及系统环境配置。"""
    java_path = _find_java()
    java_ver = "NOT FOUND (JDK 17 LTS recommended)"
    if java_path:
        out = _run_cmd([java_path, "-version"])
        first_line = out.splitlines()[0] if out else "Found"
        java_ver = f"{java_path} ({first_line})"

    r2_ver = "NOT FOUND"
    if os.path.isfile(R2_EXE):
        out = _run_cmd([R2_EXE, "-v"])
        r2_ver = out.splitlines()[0] if out else "Ready"

    jadx_status = "Ready (Batch/Jar present)" if os.path.isfile(JADX_BAT) else "Missing"
    apktool_status = "Ready (Jar present)" if os.path.isfile(APKTOOL_JAR) else "Missing"
    kb_status = f"Ready ({len(glob.glob(os.path.join(KB_DIR, '**', '*.md'), recursive=True))} documents)" if os.path.isdir(KB_DIR) else "Missing"

    # 平台边界：如实上报哪些能力在当前系统上根本不成立，
    # 避免 Unix 用户看着 38 个工具却不知道其中 8 个（Web 取证）与 1 个（Flutter AOT）用不了。
    _win = sys.platform == "win32"
    _has_pwsh = _find_powershell() is not None
    platform_boundaries = {
        "platform": sys.platform,
        "web_forensics": {
            "status": "ready" if (_win and _has_pwsh) or _has_pwsh else "windows-only",
            "requires": "PowerShell 7 + ffmpeg/ffprobe",
            "tools": [
                "seep_web_pipeline", "seep_web_gate", "seep_cms_fingerprint",
                "seep_hls_analyze", "seep_http_replay", "seep_spider_extract",
                "seep_web_report", "seep_web_toolbox",
            ],
            "note": "取证脚本为 PowerShell 实现；Unix 需安装 pwsh 才能驱动。",
        },
        "flutter_aot": {
            "status": "ready" if _win else "windows-only",
            "requires": "aotopsy.exe（Windows PE 单文件）",
            "tools": ["seep_aotopsy"],
            "note": "Unix 上请用 apktool 解包后把 libapp.so 交给 radare2 / IDA。",
        },
    }

    status = {
        "name": "seep",
        "description": "AI-Native Reverse Engineering Toolkit MCP Server",
        "base_directory": BASE_DIR,
        "platform_boundaries": platform_boundaries,
        "components": {
            "radare2_suite": {
                "status": "Ready" if os.path.isfile(R2_EXE) else "Missing",
                "binary": R2_EXE,
                "version": r2_ver
            },
            "jadx_decompiler": {
                "status": jadx_status,
                "path": JADX_BAT
            },
            "apktool": {
                "status": apktool_status,
                "path": APKTOOL_JAR
            },
            "java_runtime": {
                "status": "Ready" if java_path else "Not Installed / Not in PATH",
                "detail": java_ver
            },
            "reverselab_knowledge_base": {
                "status": kb_status,
                "path": KB_DIR
            },
            "hook_templates": {
                "status": "Ready" if os.path.isdir(HOOK_TEMPLATES_DIR) else "Missing",
                "path": HOOK_TEMPLATES_DIR
            },
            "pe_engine_exe_reverse": {
                "status": "Ready" if EXE_REV_SCRIPTS else "Missing",
                "path": EXE_REV_SCRIPTS or "not found",
                "tools": ["seep_pe_triage", "seep_pe_aob_scan", "seep_pe_diff", "seep_pe_patch"]
            },
            "android_toolbox": {
                "status": f"Ready ({sum(1 for v in _android_toolbox_status().values() if v)}/{len(_android_toolbox_status())} tools)",
                "path": ANDROID_TOOLBOX_DIR,
                "detail": {k: (v or "MISSING") for k, v in _android_toolbox_status().items()}
            },
            "web_toolbox": {
                "status": f"Ready ({sum(1 for v in _web_toolbox_status().values() if v)}/{len(_web_toolbox_status())} tools)",
                "path": WEB_TOOLBOX_DIR,
                "scripts": WEB_SCRIPT_DIR,
                "detail": {k: (v or "MISSING") for k, v in _web_toolbox_status().items()}
            }
        }
    }
    return json.dumps(status, indent=2, ensure_ascii=False)

# ---------------------------------------------------------------------------
# 2. 二进制逆向分析工具 (Radare2 引擎)
# ---------------------------------------------------------------------------
@server.tool()
def seep_r2_info(binary_path: str) -> str:
    """提取二进制文件 (PE/ELF/Mach-O) 的关键元信息：架构、位数、大小、大小端、编译器、语言以及关键安全防御机制 (Canary, NX, PIE, RELRO, ASLR)。

    Args:
        binary_path: 目标二进制文件的绝对路径或相对路径
    """
    if not os.path.isfile(binary_path):
        return f"[ERROR]: Target file does not exist: {binary_path}"
    if not os.path.isfile(RABIN2_EXE):
        return f"[ERROR]: rabin2.exe not found at {RABIN2_EXE}"
    
    out = _run_cmd([RABIN2_EXE, "-I", os.path.abspath(binary_path)])
    return _clean_r2_output(out)

@server.tool()
def seep_r2_cmd(binary_path: str, command: str, analyze: bool = True) -> str:
    """在目标二进制文件上执行任意 radare2 命令。

    Args:
        binary_path: 目标二进制文件路径
        command: radare2 命令字符串（例如 'afl', 'pdf @ main', 'iz', 'px 64 @ 0x1000'，多条命令用分号分隔）
        analyze: 是否在执行命令前先执行基本代码分析 (aaa)。默认 True。
    """
    if not os.path.isfile(binary_path):
        return f"[ERROR]: Target file does not exist: {binary_path}"
    if not os.path.isfile(R2_EXE):
        return f"[ERROR]: radare2.exe not found at {R2_EXE}"

    full_cmd = f"aaa; {command}" if analyze else command
    cmd_args = [
        R2_EXE,
        "-q",
        "-e", "scr.color=0",
        "-c", full_cmd,
        os.path.abspath(binary_path)
    ]
    out = _run_cmd(cmd_args, timeout=90)
    return _clean_r2_output(out)

@server.tool()
def seep_r2_strings(binary_path: str, filter_text: Optional[str] = None, all_sections: bool = False, limit: int = 100) -> str:
    """从二进制文件中提取字符串（包含数据段或全段字符串），支持关键词过滤。

    Args:
        binary_path: 目标二进制文件路径
        filter_text: 可选过滤关键词（不区分大小写）
        all_sections: 是否检索全段字符串 (-zz)，默认 False 只检索数据段 (-z)
        limit: 返回最大结果行数，默认 100
    """
    if not os.path.isfile(binary_path):
        return f"[ERROR]: Target file does not exist: {binary_path}"
    
    flag = "-zz" if all_sections else "-z"
    out = _run_cmd([RABIN2_EXE, flag, os.path.abspath(binary_path)])
    lines = out.splitlines()
    
    if filter_text:
        pat = filter_text.lower()
        header = lines[:2] if len(lines) >= 2 else []
        matched = [l for l in lines[2:] if pat in l.lower()]
        result = header + matched[:limit]
        if len(matched) > limit:
            result.append(f"... [Truncated: showing {limit} of {len(matched)} matched strings]")
        return "\n".join(result)
    else:
        result = lines[:limit]
        if len(lines) > limit:
            result.append(f"... [Truncated: showing {limit} of {len(lines)} strings]")
        return "\n".join(result)

@server.tool()
def seep_r2_functions(binary_path: str, filter_name: Optional[str] = None, limit: int = 100) -> str:
    """列出二进制文件的函数列表、入口点与导入导出符号。

    Args:
        binary_path: 目标二进制文件路径
        filter_name: 过滤函数名或符号名（不区分大小写）
        limit: 最大返回行数，默认 100
    """
    if not os.path.isfile(binary_path):
        return f"[ERROR]: Target file does not exist: {binary_path}"

    cmd = "aaa; afl"
    out = _run_cmd([R2_EXE, "-q", "-e", "scr.color=0", "-c", cmd, os.path.abspath(binary_path)], timeout=60)
    lines = _clean_r2_output(out).splitlines()

    # 剔除分析阶段日志
    clean_lines = [l for l in lines if not l.startswith("INFO:") and not l.startswith("WARN:")]
    
    if filter_name:
        pat = filter_name.lower()
        filtered = [l for l in clean_lines if pat in l.lower()]
        res = filtered[:limit]
        if len(filtered) > limit:
            res.append(f"... [Truncated: showing {limit} of {len(filtered)} functions]")
        return "\n".join(res) or "[No matching functions found]"
    else:
        res = clean_lines[:limit]
        if len(clean_lines) > limit:
            res.append(f"... [Truncated: showing {limit} of {len(clean_lines)} functions]")
        return "\n".join(res)

@server.tool()
def seep_r2_disasm(
    binary_path: str,
    target: str = "main",
    lines: int = 60,
    output_mode: str = "full",
    limit_tokens: int = 0,
) -> str:
    """反汇编指定函数或地址，支持三种输出模式以控制上下文消耗（Context Budget Control）。

    Args:
        binary_path: 目标二进制文件路径
        target: 目标函数名、符号或虚拟地址（例如 'main', 'sym.imp.puts', '0x1013ef0'）
        lines: 当以地址为目标时反汇编的最大指令行数，默认 60
        output_mode: 输出模式：
            'full'   = 完整原始反汇编（默认，适合精细分析）
            'branch' = 仅保留条件跳转与调用指令（cmp/test/jcc/call/ret），聚焦控制流骨架
            'summary'= 不输出指令，只统计：函数大小、块数、调用链、导入函数列表（最省 Token）
        limit_tokens: 最大输出字符数（0=不限制），超出时尾部截断并附注 Truncated 标记
    """
    if not os.path.isfile(binary_path):
        return f"[ERROR]: Target file does not exist: {binary_path}"

    if output_mode == "summary":
        # 仅抽取函数级摘要统计，不输出原始指令
        info_cmd = f"aaa; afi @ {target}"
        xref_cmd = f"axt @ {target}"
        call_cmd = f"axf @ {target}"
        info_out = _run_cmd([R2_EXE, "-q", "-e", "scr.color=0", "-c", info_cmd, os.path.abspath(binary_path)], timeout=60)
        xref_out = _run_cmd([R2_EXE, "-q", "-e", "scr.color=0", "-c", xref_cmd, os.path.abspath(binary_path)], timeout=60)
        call_out = _run_cmd([R2_EXE, "-q", "-e", "scr.color=0", "-c", call_cmd, os.path.abspath(binary_path)], timeout=60)
        summary = (
            f"[DISASM SUMMARY MODE — 上下文降噪 Token 节省模式]\n"
            f"Target: {target}\n"
            f"--- Function Info (afi) ---\n{_clean_r2_output(info_out)[:800]}\n"
            f"--- Callers (axt / xrefs-to) ---\n{_clean_r2_output(xref_out)[:600]}\n"
            f"--- Callees (axf / xrefs-from) ---\n{_clean_r2_output(call_out)[:600]}\n"
            f"提示: 使用 output_mode='branch' 或 'full' 获取指令级详情。"
        )
        return summary

    # 获取完整反汇编
    cmd = f"aaa; pdf @ {target}"
    out = _run_cmd([R2_EXE, "-q", "-e", "scr.color=0", "-c", cmd, os.path.abspath(binary_path)], timeout=60)
    cleaned = _clean_r2_output(out)
    output_lines = [l for l in cleaned.splitlines() if not l.startswith("INFO:") and not l.startswith("WARN:")]

    if not output_lines or all(not l.strip() for l in output_lines):
        cmd = f"pd {lines} @ {target}"
        out = _run_cmd([R2_EXE, "-q", "-e", "scr.color=0", "-c", cmd, os.path.abspath(binary_path)], timeout=60)
        cleaned = _clean_r2_output(out)
        output_lines = [l for l in cleaned.splitlines() if not l.startswith("INFO:") and not l.startswith("WARN:")]

    if output_mode == "branch":
        # 过滤：仅保留含有控制流关键词的行（条件跳转、调用、返回）
        branch_keywords = ("cmp ", "test ", "je ", "jne ", "jz ", "jnz ", "jb ", "jbe ",
                           "ja ", "jae ", "jl ", "jle ", "jg ", "jge ", "jmp ", "call ",
                           "ret", "jcc", "cbz ", "cbnz ", "bl ", "bne ", "beq ")
        filtered = [l for l in output_lines if any(kw in l.lower() for kw in branch_keywords)]
        total = len(output_lines)
        kept = len(filtered)
        header = (
            f"[DISASM BRANCH MODE — 控制流骨架截面，已过滤 {total - kept}/{total} 行纯数据指令]\n"
            f"Target: {target} | 保留行: {kept} | 完整输出请用 output_mode='full'\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )
        output_lines = filtered
        result = header + "\n".join(output_lines)
    else:
        result = "\n".join(output_lines)

    if limit_tokens > 0 and len(result) > limit_tokens:
        result = result[:limit_tokens] + f"\n... [TRUNCATED at {limit_tokens} chars — use offset/target narrowing for full output]"

    return result or "[Disassembly empty or symbol not found]"

@server.tool()
def seep_r2_decompile(
    binary_path: str,
    target: str = "main",
    output_mode: str = "full",
    limit_tokens: int = 8000,
) -> str:
    """将目标函数反编译为类 C 伪代码，支持三档输出模式以控制 Token 消耗（Context Budget Control）。

    Args:
        binary_path: 目标二进制文件路径
        target: 目标函数名称或虚拟地址（例如 'main', 'sym.verify_key'）
        output_mode: 输出控制模式（默认 full）：
            'full'    = 完整伪代码（适合深度分析，默认）
            'fold'    = 折叠纯计算/赋值语句，仅保留 if/else/switch/return/API调用行（减少 ~60% Token）
            'summary' = 不输出伪代码，仅返回：函数签名、入参、出参、直接调用的 API/函数名列表（最省 Token）
        limit_tokens: 最大输出字符数（默认 8000），超出则截断附 Truncated 标记；设 0 表示不限制
    """
    if not os.path.isfile(binary_path):
        return f"[ERROR]: Target file does not exist: {binary_path}"

    if output_mode == "summary":
        # 获取函数摘要信息（不输出函数体）
        cmds = f"aaa; afi @ {target}; axf @ {target}"
        out = _run_cmd([R2_EXE, "-q", "-e", "scr.color=0", "-c", cmds, os.path.abspath(binary_path)], timeout=60)
        clean = _clean_r2_output(out)
        return (
            f"[DECOMPILE SUMMARY MODE — 最省 Token 函数摘要]\n"
            f"Target: {target}\n"
            f"{clean[:1200]}\n"
            f"提示: 使用 output_mode='fold' 或 'full' 获取伪代码详情。"
        )

    cmd = f"aaa; pdc @ {target}"
    out = _run_cmd([R2_EXE, "-q", "-e", "scr.color=0", "-c", cmd, os.path.abspath(binary_path)], timeout=60)
    cleaned = _clean_r2_output(out)
    output_lines = [l for l in cleaned.splitlines() if not l.startswith("INFO:") and not l.startswith("WARN:")]

    if output_mode == "fold":
        # 折叠模式：去除纯赋值/加减乘除/临时变量行，仅保留控制流与 API 调用
        def _is_control_or_call(line: str) -> bool:
            stripped = line.strip()
            keywords = ("if ", "else", "switch", "case ", "return", "while ", "for ",
                        "do {", "goto ", "break", "continue",
                        "call ", "(", "->")
            # 包含括号 = 可能是函数调用，包含关键词 = 控制流
            return any(k in stripped for k in keywords) or stripped.startswith("//")

        folded = [l for l in output_lines if _is_control_or_call(l)]
        total = len(output_lines)
        kept = len(folded)
        header = (
            f"[DECOMPILE FOLD MODE — 已折叠 {total - kept}/{total} 行纯赋值/计算语句，上下文降噪约 {int((total-kept)/max(total,1)*100)}%]\n"
            f"Target: {target} | 保留行: {kept} | 完整输出请用 output_mode='full'\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        )
        result = header + "\n".join(folded)
    else:
        result = "\n".join(output_lines)

    if limit_tokens > 0 and len(result) > limit_tokens:
        result = result[:limit_tokens] + f"\n... [TRUNCATED at {limit_tokens} chars — 使用 target 缩小范围或 output_mode='fold'/'summary' 降低消耗]"

    return result or "[Decompile output empty]"

@server.tool()
def seep_r2_diff(file_a: str, file_b: str, mode: str = "code") -> str:
    """使用 radiff2 比对两个二进制文件的差异。

    Args:
        file_a: 第一个二进制文件路径
        file_b: 第二个二进制文件路径
        mode: 比对模式，支持 'code' (函数代码比对 -C), 'hex' (十六进制比对 -x), 'stats' (差异摘要统计 -s)
    """
    if not os.path.isfile(file_a) or not os.path.isfile(file_b):
        return f"[ERROR]: One or both files do not exist: '{file_a}', '{file_b}'"

    flag_map = {
        "code": "-C",
        "hex": "-x",
        "stats": "-s"
    }
    flag = flag_map.get(mode.lower(), "-C")
    out = _run_cmd([RADIFF2_EXE, flag, os.path.abspath(file_a), os.path.abspath(file_b)], timeout=60)
    return _clean_r2_output(out)

@server.tool()
def seep_r2_asm(code_or_hex: str, arch: str = "x86", bits: int = 64, disasm: bool = False) -> str:
    """使用 rasm2 进行机器码组装 (汇编) 或逆向反汇编。

    Args:
        code_or_hex: 汇编指令字符串 (如 'xor eax, eax; ret') 或 十六进制机器码 (如 '31c0c3')
        arch: 目标架构 (x86, arm, mips, riscv 等)，默认 x86
        bits: 位数 (16, 32, 64)，默认 64
        disasm: 为 True 时将 hex 转换为汇编代码；为 False 时将汇编代码转换为 hex 机器码。
    """
    if not os.path.isfile(RASM2_EXE):
        return f"[ERROR]: rasm2.exe not found at {RASM2_EXE}"

    cmd = [RASM2_EXE, "-a", arch, "-b", str(bits)]
    if disasm:
        cmd.extend(["-d", code_or_hex.strip()])
    else:
        cmd.append(code_or_hex.strip())

    out = _run_cmd(cmd)
    return out.strip()

# ---------------------------------------------------------------------------
# 3. Windows PE 深水区引擎（包装 exe-reverse 的零依赖脚本）
# ---------------------------------------------------------------------------
# 设计原则：
#   1. 不重写引擎，只做「统一收口」—— 参数解析、路径校验、输出截断、错误归一化；
#   2. 与 seep_r2_* / seep_apk_* 保持一致的返回风格（纯文本 / JSON 字符串）；
#   3. 只读工具绝不写盘；唯一的写盘工具 seep_pe_patch 强制要求显式 out 路径，
#      且拒绝覆盖输入文件（exe-reverse 的 O3「不声称未验证产物」在工具层兜底）。

def _resolve_exe_reverse_scripts() -> Optional[str]:
    """定位 exe-reverse 的 scripts 目录（兼容工作台内嵌、上游镜像与已安装技能三种布局）。"""
    candidates = [
        os.path.join(BASE_DIR, "..", "skill", "exe-reverse", "scripts"),
        os.path.join(BASE_DIR, "..", "upstream", "exe-reverse", "skills", "exe-reverse", "scripts"),
        os.path.join(BASE_DIR, "..", "..", "Tool", "skill", "exe-reverse", "scripts"),
        os.path.join(os.path.expanduser("~"), ".pi", "agent", "skills", "exe-reverse", "scripts"),
    ]
    for c in candidates:
        p = os.path.normpath(c)
        if os.path.isfile(os.path.join(p, "peutil.py")):
            return p
    return None

EXE_REV_SCRIPTS = _resolve_exe_reverse_scripts()

# pe_triage 默认输出已经很克制；这里只防「超大 --full-out 或异常样本」把上下文撑爆
_PE_MAX_CHARS = 12000


def _cap_output(text: str, limit: int = _PE_MAX_CHARS) -> str:
    """有界输出：截断时明确告知截断了多少字符，避免「看起来读完了」。"""
    if len(text) <= limit:
        return text
    head = text[:limit]
    return (f"{head}\n... [OUTPUT TRUNCATED: kept {limit} of {len(text)} chars. "
            f"Use the --full-out option of the underlying script, or a narrower "
            f"--limit/--section filter, to get the rest.]")


def _run_pe_script(script: str, args: List[str], timeout: int = 180) -> str:
    """用当前解释器执行 exe-reverse 脚本（不依赖 PATH 上的 python）。"""
    if not EXE_REV_SCRIPTS:
        return ("[ERROR]: exe-reverse scripts not found. Expected one of:\n"
                "  <root>/Tool/skill/exe-reverse/scripts\n"
                "  ~/.pi/agent/skills/exe-reverse/scripts\n"
                "Run: powershell -File setup/install-pi.ps1")
    path = os.path.join(EXE_REV_SCRIPTS, script)
    if not os.path.isfile(path):
        return f"[ERROR]: script missing: {path}"
    out = _run_cmd([sys.executable, path] + args, timeout=timeout)
    return _cap_output(out)


@server.tool()
def seep_pe_triage(pe_path: str, json_mode: bool = False, no_strings: bool = False) -> str:
    """对未知 Windows PE (.exe/.dll/.sys) 做一次过体检：身份/架构/子系统、构建证据（时间戳、链接器、Rich 头、PDB、CLR、证书）、
    节区表与逐节熵、校验和比对、导入导出/TLS/资源目录，并输出带阈值与数值的「保护信号」清单。

    这是 Windows 目标的第一步（对应 EXE-G3 代码定位的输入），比通用 r2 更懂 PE 语义：能识别「节区熵异常 / 导入表空 / 校验和不匹配」这类加壳与自校验线索。

    Args:
        pe_path: 目标 PE 文件路径
        json_mode: 输出结构化 JSON（便于程序化消费），默认人类可读文本
        no_strings: 跳过字符串采样，速度更快（大文件或只要结构时使用）
    """
    if not os.path.isfile(pe_path):
        return f"[ERROR]: Target file does not exist: {pe_path}"
    args = [os.path.abspath(pe_path)]
    if json_mode:
        args.append("--json")
    if no_strings:
        args.append("--no-strings")
    return _run_pe_script("pe_triage.py", args)


@server.tool()
def seep_pe_aob_scan(pe_path: str, pattern: str, section: Optional[str] = None,
                     context: int = 0, limit: int = 50, across: Optional[str] = None) -> str:
    """在 PE 中定位字节特征码（AOB），并给出**能不能当定位器用**的裁决：
    unique / ambiguous / pervasive / no-match，附每个命中点的文件偏移、RVA 与所在节区。

    为什么需要它：特征码「打上了」不等于「打对了」。命中 2 处的模式是抛硬币，不是定位器——本工具把这个判断变成可读的结论。

    Args:
        pe_path: 目标 PE 文件路径
        pattern: 特征码，如 "48 8B 05 11 22 33 00 48 85 C0 74 05"，通配符用 ??
        section: 只在该节区内报告命中（如 ".text"）
        context: 每个命中点额外打印的上下文字节数
        limit: 每个特征码最多报告多少个命中
        across: 第二个版本的文件路径，用于对比命中数（判断补丁能否跨版本存活）
    """
    if not os.path.isfile(pe_path):
        return f"[ERROR]: Target file does not exist: {pe_path}"
    if not pattern or not pattern.strip():
        return "[ERROR]: pattern is empty"
    args = [os.path.abspath(pe_path), "--patterns", pattern.strip()]
    if section:
        args += ["--section", section]
    if context:
        args += ["--context", str(context)]
    if limit:
        args += ["--limit", str(limit)]
    if across:
        if not os.path.isfile(across):
            return f"[ERROR]: across build does not exist: {across}"
        args += ["--across", os.path.abspath(across)]
    return _run_pe_script("aob_scan.py", args)


@server.tool()
def seep_pe_diff(old_build: str, new_build: str, summary_only: bool = False) -> str:
    """对比同一程序的两个构建版本：归一化易变头字段（TimeDateStamp / CheckSum）后按内容哈希差分，
    报告差异区间并映射回 RVA，用于跨版本补丁迁移与「同一份代码为什么行为不同」的判定。

    Args:
        old_build: 基线版本（旧）
        new_build: 候选版本（新）
        summary_only: 只输出每节区一行的小计，不展开字节区间
    """
    for p in (old_build, new_build):
        if not os.path.isfile(p):
            return f"[ERROR]: file does not exist: {p}"
    args = [os.path.abspath(old_build), os.path.abspath(new_build)]
    if summary_only:
        args.append("--summary")
    return _run_pe_script("pe_diff.py", args)


@server.tool()
def seep_pe_patch(pe_path: str, out_path: str, at_rva: Optional[str] = None,
                  at_offset: Optional[str] = None, new_bytes: str = "",
                  expect: Optional[str] = None, pattern: Optional[str] = None,
                  pattern_offset: int = 0, at_hit: Optional[int] = None,
                  dry_run: bool = False) -> str:
    """对 PE 做**可验证的等长字节补丁**：只读输入、输出到新文件、校验和自动重算、
    并在写盘后逐字节回读证明补丁真的落在文件里。

    纪律（来自 exe-reverse，工具层强制执行）：
      · 输入文件永不被修改；out_path 必须显式给出且不得等于输入；
      · 默认拒绝改变长度（长度变化会移动后续所有偏移，属结构性编辑）；
      · expect 提供「你相信原址是什么字节」，不匹配立即中止——这是防打错地址的最后一道闸。

    Args:
        pe_path: 输入 PE（只读打开）
        out_path: 输出文件路径（必须是新文件，不能等于输入）
        at_rva: 按 RVA 定位，如 "0x1010"
        at_offset: 按文件偏移定位，如 "0x410"（与 at_rva 二选一）
        new_bytes: 替换字节，如 "90 90 90" 或 "EB 0A"
        expect: 你预期的原始字节，如 "48 8B 05"；不匹配则中止，其长度同时作为等长基准
        pattern: 用特征码定位补丁点（与 at_rva/at_offset 二选一）
        pattern_offset: 在特征码命中点基础上的偏移（如 5 跳到分支指令）
        at_hit: 特征码命中多处时指定打第几处（从 1 开始）；不指定则多处命中会拒绝执行
        dry_run: 只报告将要改什么，不写任何文件
    """
    if not os.path.isfile(pe_path):
        return f"[ERROR]: Target file does not exist: {pe_path}"
    if not new_bytes or not new_bytes.strip():
        return "[ERROR]: new_bytes is required, e.g. '90 90 90'"
    if not dry_run:
        if not out_path or not out_path.strip():
            return "[ERROR]: out_path is required (the input is never modified in place)"
        if os.path.abspath(out_path) == os.path.abspath(pe_path):
            return "[ERROR]: out_path must differ from pe_path; patching in place is refused by design"

    locators = [x for x in (at_rva, at_offset, pattern) if x]
    if len(locators) != 1:
        return "[ERROR]: give exactly one of at_rva / at_offset / pattern"

    args = [os.path.abspath(pe_path), "--bytes", new_bytes.strip()]
    if at_rva:
        args += ["--at-rva", at_rva]
    elif at_offset:
        args += ["--at-offset", at_offset]
    else:
        args += ["--pattern", pattern.strip()]
        if pattern_offset:
            args += ["--pattern-offset", str(pattern_offset)]
        if at_hit is not None:
            args += ["--at-hit", str(at_hit)]
    if expect:
        args += ["--expect", expect.strip()]
    if dry_run:
        args.append("--dry-run")
    else:
        args += ["--out", os.path.abspath(out_path)]
    return _run_pe_script("pepatch.py", args)

# ---------------------------------------------------------------------------
# 4. Android APK 逆向与动态 Hook 生成
# ---------------------------------------------------------------------------
@server.tool()
def seep_r2_xrefs(
    binary_path: str,
    target: str,
    direction: str = "to",
    limit: int = 10,
) -> str:
    """获取指定地址/函数的交叉引用关系，内置分页与统计摘要避免大量 xref 结果内爆上下文。

    Args:
        binary_path: 目标二进制文件路径
        target: 目标函数名或地址（如 'sym.check_license', '0x401234'）
        direction: 方向— 'to'=谁引用了它(调用方), 'from'=它引用了谁(被调用方)
        limit: 最多返回多少条引用（默认 10），超出部分附加统计摘要
    """
    if not os.path.isfile(binary_path):
        return f"[ERROR]: Target file does not exist: {binary_path}"

    r2_cmd = f"aaa; {'axt' if direction == 'to' else 'axf'} @ {target}"
    out = _run_cmd([R2_EXE, "-q", "-e", "scr.color=0", "-c", r2_cmd, os.path.abspath(binary_path)], timeout=60)
    cleaned = _clean_r2_output(out)
    lines = [l for l in cleaned.splitlines() if l.strip() and not l.startswith("INFO:") and not l.startswith("WARN:")]

    total = len(lines)
    shown = lines[:limit]
    result_lines = [
        f"[XREFS {direction.upper()} — {target} | 共 {total} 条引用，显示前 {min(limit, total)} 条]",
        f"注意: 若 total 远大于 limit，考虑缩小 limit 或先查 summary 模式确定目标函数。",
        "━" * 60,
    ] + shown

    if total > limit:
        result_lines.append(f"... [已截断，剩余 {total - limit} 条未展示 | 增大 limit 或用 filter_name 缩小目标范围]"
                            f"\n模块来源分布小计: {dict(list({l.split()[2] if len(l.split())>2 else '?' for l in lines}))[:3]}"
        )

    return "\n".join(result_lines)
@server.tool()
def seep_apk_info(apk_path: str) -> str:
    """原生解析 APK 压缩包结构：统计 DEX 文件、Native .so 架构动态库、资源分布，并提取 AndroidManifest.xml 关键字符串（免 Java 环境）。

    Args:
        apk_path: 目标 APK 文件路径
    """
    if not os.path.isfile(apk_path):
        return f"[ERROR]: APK file not found: {apk_path}"

    try:
        with zipfile.ZipFile(apk_path, 'r') as z:
            namelist = z.namelist()
            dex_files = [f for f in namelist if f.endswith(".dex")]
            so_files = [f for f in namelist if f.endswith(".so")]
            meta_files = [f for f in namelist if f.startswith("META-INF/")]
            
            # 统计原生架构
            arches = set()
            for s in so_files:
                parts = s.split('/')
                if len(parts) >= 2 and parts[0] == "lib":
                    arches.add(parts[1])

            # 提取 Manifest 二进制中的可读 ASCII/UTF-8 字符串
            manifest_strings = []
            if "AndroidManifest.xml" in namelist:
                raw = z.read("AndroidManifest.xml")
                # 过滤出 4 字符以上的可打印字符串
                found = re.findall(rb'[\x20-\x7e]{4,}', raw)
                for item in found:
                    s = item.decode('ascii', errors='ignore')
                    if any(k in s.lower() for k in ["android", "permission", "activity", "service", "receiver", "provider", "package"]):
                        manifest_strings.append(s)

            summary = {
                "file_size": os.path.getsize(apk_path),
                "dex_count": len(dex_files),
                "dex_files": dex_files,
                "native_architectures": sorted(list(arches)),
                "native_libraries_count": len(so_files),
                "signed_certificates": meta_files[:5],
                "manifest_key_markers": manifest_strings[:30]
            }
            return json.dumps(summary, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"[ERROR]: Failed to parse APK zip: {str(e)}"

@server.tool()
def seep_apk_decompile(apk_path: str, output_dir: Optional[str] = None, deobfuscate: bool = True) -> str:
    """使用内置 JADX 反编译器将 APK 或 DEX 文件全量反编译为 Java 源码工程。

    Args:
        apk_path: 目标 APK 或 DEX 文件路径
        output_dir: 源码输出目录（若不指定则在 APK 旁生成 <apk_name>_src 目录）
        deobfuscate: 是否启用混淆名还原 (-r/--deobf)，默认 True
    """
    if not os.path.isfile(apk_path):
        return f"[ERROR]: Target APK does not exist: {apk_path}"

    java_path = _find_java()
    if not java_path:
        return "[ERROR]: Java runtime (JDK 17 LTS) is required to run JADX. Please install JDK or set JAVA_HOME."

    if not output_dir:
        stem = Path(apk_path).stem
        output_dir = os.path.join(os.path.dirname(os.path.abspath(apk_path)), f"{stem}_jadx_src")

    os.makedirs(output_dir, exist_ok=True)

    cmd = [JADX_BAT, "-d", output_dir]
    if deobfuscate:
        cmd.append("--deobf")
    cmd.append(os.path.abspath(apk_path))

    out = _run_cmd(cmd, timeout=300)
    return f"Decompilation finished.\nOutput directory: {output_dir}\nLog: {out[:500]}..."

@server.tool()
def seep_apk_unpack(apk_path: str, output_dir: Optional[str] = None, no_src: bool = False) -> str:
    """使用内置 Apktool 解包 APK 资源文件、清晰明文 AndroidManifest.xml 以及 Smali 汇编代码。

    Args:
        apk_path: 目标 APK 文件路径
        output_dir: 解包输出目录（若不指定则在 APK 旁生成 <apk_name>_apktool 目录）
        no_src: 是否跳过 smali 反编译 (-s)，若只需提取资源可设为 True
    """
    if not os.path.isfile(apk_path):
        return f"[ERROR]: Target APK does not exist: {apk_path}"

    java_path = _find_java()
    if not java_path:
        return "[ERROR]: Java runtime (JDK 17 LTS) is required to run Apktool. Please install JDK or set JAVA_HOME."

    if not output_dir:
        stem = Path(apk_path).stem
        output_dir = os.path.join(os.path.dirname(os.path.abspath(apk_path)), f"{stem}_apktool")

    cmd = [java_path, "-jar", APKTOOL_JAR, "d", "-f"]
    if no_src:
        cmd.append("-s")
    cmd.extend(["-o", output_dir, os.path.abspath(apk_path)])

    out = _run_cmd(cmd, timeout=300)
    return f"Apktool unpack finished.\nOutput directory: {output_dir}\nLog: {out[:500]}..."

@server.tool()
def seep_apk_smali_search(directory: str, pattern: str, case_sensitive: bool = False, limit: int = 50) -> str:
    """在解包后的 Smali 代码或源码目录中进行敏感词/签名/加解密密钥快速排查。

    Args:
        directory: 解包后的 smali 或源码根目录
        pattern: 正则表达式或搜索文本（例如 'AES', 'SecretKeySpec', 'token', 'http://', 'firebase'）
        case_sensitive: 是否大小写敏感，默认 False
        limit: 最大匹配结果条数，默认 50
    """
    if not os.path.isdir(directory):
        return f"[ERROR]: Directory not found: {directory}"

    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        regex = re.compile(pattern, flags)
    except re.error as e:
        return f"[ERROR]: Invalid regex pattern: {str(e)}"

    matches = []
    for root, _, files in os.walk(directory):
        for f in files:
            if f.endswith((".smali", ".java", ".xml", ".json", ".txt")):
                fpath = os.path.join(root, f)
                try:
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as fh:
                        for idx, line in enumerate(fh, 1):
                            if regex.search(line):
                                rel = os.path.relpath(fpath, directory)
                                matches.append(f"{rel}:{idx}: {line.strip()[:200]}")
                                if len(matches) >= limit:
                                    break
                except Exception:
                    pass
        if len(matches) >= limit:
            break

    if not matches:
        return f"No matches found for '{pattern}' in {directory}"
    res = matches[:limit]
    if len(matches) >= limit:
        res.append(f"... [Truncated: reached limit of {limit} matches]")
    return "\n".join(res)

@server.tool()
def seep_apk_gen_hook(
    framework: str = "frida",
    class_name: str = "com.example.app.MainActivity",
    method_name: str = "checkFlag",
    param_types: Optional[List[str]] = None,
    return_type: str = "boolean",
    hook_timing: str = "after"
) -> str:
    """根据类名与方法签名自动生成动态 Hook 脚本（支持 Frida JavaScript 与 LSPilot/BeanShell 两种框架）。

    Args:
        framework: Hook 框架，'frida' (默认) 或 'bsh' / 'lspilot'
        class_name: 目标完整类名（如 com.example.app.SecurityHelper）
        method_name: 目标方法名（如 verifyLicense）
        param_types: 方法形参类型列表，例如 ['java.lang.String', 'int']，若重载方法需指定
        return_type: 返回值类型，默认 'boolean'
        hook_timing: Hook 时机，'before', 'after', 或 'replace'
    """
    params_str = ", ".join(param_types) if param_types else ""
    
    if framework.lower() == "frida":
        # 生成 Frida 脚本
        joined_types = "', '".join(param_types) if param_types else ""
        overload_args = f"'{joined_types}'" if param_types else ""
        js_code = f"""// Frida Hook Script for {class_name}.{method_name}
// Generated by seep MCP Toolkit
Java.perform(function () {{
    var target = Java.use("{class_name}");
    var method = target["{method_name}"];
    if ({'true' if param_types else 'false'}) {{
        method = method.overload({overload_args});
    }}
    
    method.implementation = function () {{
        console.log("[*] Hooked {class_name}.{method_name} called");
        for (var i = 0; i < arguments.length; i++) {{
            console.log("    arg[" + i + "]: " + arguments[i]);
        }}
"""
        if hook_timing.lower() == "replace":
            default_ret = "true" if return_type == "boolean" else "null" if return_type == "void" else "0"
            js_code += f"""        console.log("[*] Return value hijacked to: {default_ret}");
        return {default_ret};
    }};
}});"""
        else:
            js_code += f"""        var ret = this.{method_name}.apply(this, arguments);
        console.log("[*] Original return value: " + ret);
        return ret;
    }};
}});"""
        return js_code

    else:
        # 生成 LSPilot / BeanShell 脚本
        template_file = os.path.join(HOOK_TEMPLATES_DIR, f"hook_{hook_timing.lower()}.bsh")
        if not os.path.isfile(template_file):
            template_file = os.path.join(HOOK_TEMPLATES_DIR, "hook_after.bsh")
        
        with open(template_file, "r", encoding="utf-8", errors="replace") as fh:
            content = fh.read()

        pre_find = ""
        if param_types:
            param_classes = ", ".join([f'ReflectUtils.findClass("{p}", hostLoader)' for p in param_types])
            pre_find = f'Class[] paramTypes = new Class[] {{ {param_classes} }};\n    java.lang.reflect.Method targetMethod = ReflectUtils.findMethod(targetClass, "{method_name}", paramTypes);'
        else:
            pre_find = f'java.lang.reflect.Method targetMethod = ReflectUtils.findMethod(targetClass, "{method_name}", null);'

        content = content.replace("${GEN_TIME}", "Now")
        content = content.replace("${PLUGIN_NAME}", f"hook_{method_name}")
        content = content.replace("${TARGET_CLASS}", class_name)
        content = content.replace("${TARGET_METHOD}", method_name)
        content = content.replace("${TARGET_DESC}", f"({params_str})")
        content = content.replace("${PRE_FIND_METHOD}", pre_find)
        content = content.replace("${CALLBACK_CODE}", f'// TODO: Add custom manipulation for {method_name}')
        return content

# ---------------------------------------------------------------------------
# 4.5 外部 Android 工具箱桥接 (Frida / objection / frida-dexdump / APKiD / Aotopsy)
# ---------------------------------------------------------------------------
@server.tool()
def seep_android_toolbox() -> str:
    """检查 Android 外部动态/静态工具箱就绪状态（frida / objection / frida-dexdump / APKiD / Aotopsy / adb）。

    返回每个工具的解析路径与缺失项。缺失时调用方应运行：
    powershell -ExecutionPolicy Bypass -File Tool\\scripts\\android\\install-android-toolbox.ps1
    """
    status = _android_toolbox_status()
    devices = ""
    adb = status.get("adb")
    if adb:
        devices = _run_cmd([adb, "devices"], timeout=20)
    payload = {
        "toolbox_root": ANDROID_TOOLBOX_DIR,
        "tools": {k: ({"ready": bool(v), "path": v or "—"}) for k, v in status.items()},
        "ready_count": sum(1 for v in status.values() if v),
        "total_count": len(status),
        "devices": _clean_r2_output(devices) if devices else "(adb 不可用)",
        "hint": "缺项请运行 Tool/scripts/android/install-android-toolbox.ps1 补全",
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


@server.tool()
def seep_apkid_scan(apk_path: str) -> str:
    """用 APKiD 对 APK 做加固/对抗指纹识别：壳商(packer/protector)、反调试、反模拟器、混淆器、资源操纵。

    这是 Android 逆向的第一道 Recon 门，结论直接决定路线：
    - 命中 packer/protector → 先 frida-dexdump 内存脱壳，不要直接啃 JADX
    - 命中 anti_vm/anti_debug → 先用 objection 伪装环境
    - 命中 Flutter 特征 → 转 seep_aotopsy 分析 libapp.so

    Args:
        apk_path: 目标 APK 绝对路径
    """
    if not os.path.isfile(apk_path):
        return f"[ERROR]: Target file does not exist: {apk_path}"
    exe = _resolve_android_tool("apkid")
    if not exe:
        return "[ERROR]: APKiD 未安装。请运行 Tool/scripts/android/install-android-toolbox.ps1 -Only apkid"

    raw = _run_cmd([exe, "-j", os.path.abspath(apk_path)], timeout=300)
    start = raw.find("{")
    if start < 0:
        return _clean_r2_output(raw)
    try:
        doc = json.loads(raw[start:])
    except Exception:
        return _clean_r2_output(raw)

    summary: Dict[str, List[str]] = {}
    for f in doc.get("files", []):
        matches = f.get("matches") or {}
        fname = f.get("filename", "")
        short = fname.split("!")[-1] if "!" in fname else os.path.basename(fname)
        for k, v in matches.items():
            vals = v if isinstance(v, list) else [str(v)]
            summary.setdefault(k, []).append(f"{short} :: {', '.join(vals)}")

    routes = []
    if "packer" in summary or "protector" in summary:
        routes.append("加壳 → 先内存脱壳：Tool/scripts/android/frida-dexdump-run.ps1 -Package <pkg> -Spawn -DeepSearch")
    if "anti_vm" in summary or "anti_debug" in summary:
        routes.append("反调试/反模拟器 → 先伪装：Tool/scripts/android/objection-run.ps1 -Package <pkg>")
    if not routes:
        routes.append("无壳无强对抗 → 可直接 JADX-GUI + seep_apk_decompile 静态推进")

    payload = {
        "apk": os.path.abspath(apk_path),
        "apkid_version": doc.get("apkid_version"),
        "findings": summary,
        "route_advice": routes,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


@server.tool()
def seep_aotopsy(target_path: str, action: str = "find-libapp", keyword: Optional[str] = None) -> str:
    """Flutter / Dart AOT（libapp.so）静态分析：还原 Dart 函数名、类结构、字符串引用与调用图。

    Flutter 应用的业务逻辑、网络签名密钥、API 路由全部编译进 libapp.so，JADX 只能看到引擎壳。
    Aotopsy 直接解析 Dart Snapshot 二进制语法（不需要 Dart VM / SDK）。

    Args:
        target_path: APK 路径，或已抽出的 libapp.so 路径
        action: find-libapp（定位并报告 Dart 版本，最快）
                doctor（快诊支持度）
                signal（全管线：反汇编 + 调用边 + 行为信号）
                strings（需配合 keyword，检索字符串并反查引用函数 —— 找签名密钥的最短路径）
                export-dart（重建整个 Dart 源码工程，最慢）
        keyword: action=strings 时的检索关键词，例如 'X-Sign' / 'sign' / 'token'
    """
    if not os.path.isfile(target_path):
        return f"[ERROR]: Target file does not exist: {target_path}"
    exe = _resolve_android_tool("aotopsy")
    if not exe:
        return "[ERROR]: Aotopsy 未部署。请运行 Tool/scripts/android/install-android-toolbox.ps1 -Only aotopsy"

    target = os.path.abspath(target_path)
    out_dir = os.path.join(os.path.dirname(target), os.path.splitext(os.path.basename(target))[0] + ".aotopsy")
    os.makedirs(out_dir, exist_ok=True)
    is_apk = target.lower().endswith((".apk", ".aab", ".apks"))

    lib_path = target
    if is_apk:
        _run_cmd([exe, "find-libapp", "-apk", target, "-out", out_dir], timeout=300)
        json_candidates = glob.glob(os.path.join(out_dir, "*_find_libapp.json"))
        if not json_candidates:
            return "[ERROR]: Aotopsy 未生成 find_libapp.json（该 APK 可能不是 Flutter 应用）"
        with open(json_candidates[0], "r", encoding="utf-8") as fh:
            info = json.load(fh)
        if not info.get("found"):
            return f"[INFO]: 未检出 Dart AOT 快照，reason={info.get('reason')}（可能非 Flutter，或已被加固剥离）"
        if action == "find-libapp":
            return json.dumps({"apk": target, "best": info["best"], "candidates": len(info.get("candidates", []))}, indent=2, ensure_ascii=False)

        lib_path = os.path.join(out_dir, "libapp.so")
        if not os.path.isfile(lib_path) and is_apk:
            try:
                with zipfile.ZipFile(target) as zf:
                    with zf.open(info["best"]["path_in_apk"]) as src, open(lib_path, "wb") as dst:
                        shutil.copyfileobj(src, dst)
            except Exception as e:
                return f"[ERROR]: 抽取 libapp.so 失败: {e}"

    if action == "doctor":
        return _clean_r2_output(_run_cmd([exe, "doctor", lib_path], timeout=600))
    if action == "signal":
        out = _run_cmd([exe, "signal", lib_path, "--out", os.path.join(out_dir, "signal")], timeout=1800)
        return _clean_r2_output(out) + f"\n[产物] {os.path.join(out_dir, 'signal')}"
    if action == "strings":
        if not keyword:
            return "[ERROR]: action=strings 需要 keyword 参数"
        return _clean_r2_output(_run_cmd([exe, "_debug", "strings", "--lib", lib_path, "--find", keyword, "--xref"], timeout=600))
    if action == "export-dart":
        out = _run_cmd([exe, "export-dart", "--lib", lib_path, "--out", os.path.join(out_dir, "dart_src")], timeout=3600)
        return _clean_r2_output(out) + f"\n[产物] {os.path.join(out_dir, 'dart_src')}"

    return f"[ERROR]: 未知 action: {action}（可选 find-libapp / doctor / signal / strings / export-dart）"


# ---------------------------------------------------------------------------
# 4.6 外部 Web / 流媒体取证桥接 (HLS / 防盗链 / Spider)
# ---------------------------------------------------------------------------
@server.tool()
def seep_web_toolbox() -> str:
    """检查 Web / 流媒体取证工具箱就绪状态（ffmpeg / ffprobe / node）。

    ffmpeg 是 HLS 取证的核心：既能 -headers 携带防盗链头，也能直接解密 AES-128 分片。
    缺失时调用方应运行：
    powershell -ExecutionPolicy Bypass -File Tool\\scripts\\web\\install-web-toolbox.ps1
    """
    status = _web_toolbox_status()
    _ps = _find_powershell()
    _supported = _ps is not None
    payload = {
        "toolbox_root": WEB_TOOLBOX_DIR,
        "script_dir": WEB_SCRIPT_DIR,
        # 平台可用性必须显式上报：8 个 Web 工具都靠 PowerShell 脚本驱动，
        # 在未装 pwsh 的 Linux/macOS 上它们一律不可用。此前只报「缺 ffmpeg」，
        # 会让人误以为装上 ffmpeg 就能跑。
        "platform_supported": _supported,
        "required_runtime": {
            "powershell": _ps or "未找到（Unix 需安装 PowerShell 7）",
            "platform": sys.platform,
        },
        "tools": {k: {"ready": bool(v), "path": v or "—"} for k, v in status.items()},
        "ready_count": sum(1 for v in status.values() if v),
        "total_count": len(status),
        "capabilities": [
            "seep_hls_analyze   : m3u8 解密可行性 + DRM 判定 + 防盗链 + 实解验证",
            "seep_http_replay   : 头部变体矩阵重放，定位防盗链门槛头",
            "seep_spider_extract: TVBox/CatVod spider 三入口与硬编码凭据提取",
            "seep_cms_fingerprint: 影视站 CMS 家族 / 采集接口 / 播放器 / 暴露面指纹",
            "nuclei / ffuf      : 模板化漏扫 / 目录爆破（需自行准备目标与字典）",
        ],
        "wordlists": os.path.join(WEB_TOOLBOX_DIR, "wordlists"),
        "nuclei_templates": os.path.join(os.path.expanduser("~"), "nuclei-templates"),
        "hint": "缺项请运行 Tool/scripts/web/install-web-toolbox.ps1 补全",
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


@server.tool()
def seep_hls_analyze(
    url: Optional[str] = None,
    playlist_path: Optional[str] = None,
    referer: Optional[str] = None,
    user_agent: Optional[str] = None,
    cookie: Optional[str] = None,
    headers: Optional[List[str]] = None,
    variant: str = "best",
    verify_seconds: int = 15,
    no_verify: bool = False,
    out_dir: Optional[str] = None,
) -> str:
    """HLS / m3u8 取证：一次性判定「为何播不出」的 6 种根因，并给出可取证结论。

    影视源逆向的核心工具。它区分这些完全不同的情况：
      ① 防盗链（缺 Referer / UA / Origin）② key 鉴权（需登录态或一次性 token）
      ③ AES-128 可解  ④ SAMPLE-AES/fMP4 需专用解封装  ⑤ DRM（不可逆向，必须终止）
      ⑥ 返回 HTML 错误页伪装成 m3u8

    Args:
        url: m3u8 地址（master 或 media 均可，自动下钻选最高码率）
        playlist_path: 本地 playlist 文件路径（与 url 二选一）
        referer: 防盗链 Referer（影视站最常见门槛）
        user_agent: User-Agent（部分站点分片要求 UA 含 Mozilla）
        cookie: Cookie（需登录态的源）
        headers: 额外请求头，形如 ["X-Token: abc"]
        variant: best(默认，最高码率) | all | 序号(0 起)
        verify_seconds: ffmpeg 实解验证秒数，默认 15
        no_verify: 跳过 ffmpeg 实解（只做静态判定）
        out_dir: 证据输出目录（默认 D:\\Tool\\Web\\work\\hls-<时间戳>）
    """
    if not url and not playlist_path:
        return "[ERROR]: 必须提供 url 或 playlist_path"

    args: List[str] = []
    if url:
        args += ["-Url", url]
    if playlist_path:
        args += ["-Playlist", playlist_path]
    if referer:
        args += ["-Referer", referer]
    if user_agent:
        args += ["-UserAgent", user_agent]
    if cookie:
        args += ["-Cookie", cookie]
    for h in (headers or []):
        args += ["-Header", h]
    args += ["-Variant", variant, "-VerifySeconds", str(verify_seconds)]
    if no_verify:
        args += ["-NoVerify"]
    if out_dir:
        args += ["-OutDir", out_dir]

    ok, raw, payload = _run_web_script("hls-analyze.ps1", args, timeout=900)
    if not ok:
        return f"[ERROR]: HLS 取证失败\n{raw}"

    media = payload.get("Media") or {}
    verify = payload.get("Verify") or {}
    summary = {
        "verdict": payload.get("Verdict", {}).get("Text"),
        "level": payload.get("Verdict", {}).get("Level"),
        "fetch": payload.get("Fetch"),
        "chosen_uri": payload.get("Chosen"),
        "segment_count": media.get("SegmentCount"),
        "total_duration": media.get("TotalDuration"),
        "encryption": (payload.get("Decrypt") or {}).get("Scheme"),
        "drm": (payload.get("Decrypt") or {}).get("Drm"),
        "decryptable": (payload.get("Decrypt") or {}).get("Possible"),
        "key_probes": payload.get("KeyProbes"),
        "verify": {
            "attempted": verify.get("Attempted"),
            "ok": verify.get("Ok"),
            "file": verify.get("File"),
            "skipped": verify.get("Skipped"),
            "error": verify.get("Error"),
            "ffprobe": verify.get("Ffprobe"),
        },
        "diagnosis": payload.get("Diagnosis"),
        "evidence_json": os.path.join(payload.get("OutDir", out_dir or ""), "evidence.json"),
        "report_md": os.path.join(payload.get("OutDir", out_dir or ""), "report.md"),
    }
    return json.dumps(summary, indent=2, ensure_ascii=False)


@server.tool()
def seep_http_replay(
    url: Optional[str] = None,
    curl: Optional[str] = None,
    referer: Optional[str] = None,
    user_agent: Optional[str] = None,
    cookie: Optional[str] = None,
    headers: Optional[List[str]] = None,
    method: str = "GET",
    body: Optional[str] = None,
    content_type: Optional[str] = None,
    rate_test: int = 0,
    out_dir: Optional[str] = None,
) -> str:
    """HTTP 重放与防盗链举证：把「能不能访问」变成一个可控实验，定位真正的门槛头。

    做法：拿原始请求 → 生成头变体矩阵（全头 / 无头 / 只留 UA / 只留 Referer /
    逐项剔除 / 移动端 UA）→ 逐条重放 → 对比状态码与正文指纹 → 出结论。

    Args:
        url: 目标 URL
        curl: 从浏览器复制的 curl 命令（自动抽 URL、-H 与 --data；与 url 二选一）
        referer: Referer
        user_agent: User-Agent
        cookie: Cookie
        headers: 额外请求头，形如 ["X-Token: abc"]
        method: GET | POST | PUT | DELETE
        body: POST 体
        content_type: 请求 Content-Type
        rate_test: >0 时连续请求 N 次，检测 429 / 频控
        out_dir: 证据输出目录
    """
    if not url and not curl:
        return "[ERROR]: 必须提供 url 或 curl"

    args: List[str] = []
    if url:
        args += ["-Url", url]
    if curl:
        args += ["-Curl", curl]
    if referer:
        args += ["-Referer", referer]
    if user_agent:
        args += ["-UserAgent", user_agent]
    if cookie:
        args += ["-Cookie", cookie]
    for h in (headers or []):
        args += ["-Header", h]
    args += ["-Method", method]
    if body:
        args += ["-Body", body]
    if content_type:
        args += ["-ContentType", content_type]
    if rate_test > 0:
        args += ["-RateTest", str(rate_test)]
    if out_dir:
        args += ["-OutDir", out_dir]

    ok, raw, payload = _run_web_script("http-replay.ps1", args, timeout=900)
    if not ok:
        return f"[ERROR]: 重放举证失败\n{raw}"

    summary = {
        "verdict": payload.get("Verdict", {}).get("Text"),
        "level": payload.get("Verdict", {}).get("Level"),
        "gate_headers": payload.get("Verdict", {}).get("GateHeaders"),
        "semantic_diff": payload.get("Verdict", {}).get("SemanticDiff"),
        "rate": payload.get("Verdict", {}).get("Rate"),
        "matrix": [
            {"variant": r.get("Variant"), "status": r.get("Status"),
             "length": r.get("Length"), "msn": r.get("Msn"),
             "body_hash": r.get("BodyHash"), "sketch": r.get("Sketch")}
            for r in (payload.get("Results") or [])
        ],
        "evidence_json": os.path.join(payload.get("OutDir", out_dir or ""), "evidence.json"),
        "report_md": os.path.join(payload.get("OutDir", out_dir or ""), "report.md"),
    }
    return json.dumps(summary, indent=2, ensure_ascii=False)


@server.tool()
def seep_spider_extract(
    target_path: str,
    out_dir: Optional[str] = None,
    skip_decompile: bool = False,
) -> str:
    """TVBox / CatVod spider 提取：反编译 jar/dex/apk，定位三入口并抽出硬编码线索。

    影视源聚合器的「源」就是一个 spider.jar。入口固定为：
      homeContent / categoryContent / detailContent / playerContent
    其中 detailContent（详情下发）与 playerContent（取流解析）就是核心链路。

    Args:
        target_path: spider.jar / .dex / .apk 路径
        out_dir: 输出目录（默认 D:\\Tool\\Web\\work\\spider-<名称>-<时间戳>）
        skip_decompile: 复用已有反编译产物（<out_dir>\\src 已存在时）
    """
    if not os.path.exists(target_path):
        return f"[ERROR]: Target does not exist: {target_path}"

    args: List[str] = ["-Path", target_path]
    if out_dir:
        args += ["-OutDir", out_dir]
    if skip_decompile:
        args += ["-SkipDecompile"]

    ok, raw, payload = _run_web_script("spider-extract.ps1", args, timeout=1800)
    if not ok:
        return f"[ERROR]: Spider 提取失败\n{raw}"

    summary = {
        "verdict": payload.get("Verdict", {}).get("Text"),
        "level": payload.get("Verdict", {}).get("Level"),
        "risks": payload.get("Verdict", {}).get("Risks"),
        "source_files": payload.get("SourceFiles"),
        "entries": [
            {"entry": e.get("Entry"), "found": e.get("Found"), "files": e.get("Files")}
            for e in (payload.get("Entries") or [])
        ],
        "domains": payload.get("Domains"),
        "api_paths": [p.get("Match") for p in (payload.get("ApiPaths") or [])],
        "secrets": payload.get("Secrets"),
        "header_sets": payload.get("HeaderSets"),
        "crypto_kinds": payload.get("CryptoKinds"),
        "obfuscation": payload.get("Obfuscation"),
        "evidence_json": os.path.join(payload.get("OutDir", out_dir or ""), "evidence.json"),
        "report_md": os.path.join(payload.get("OutDir", out_dir or ""), "report.md"),
    }
    return json.dumps(summary, indent=2, ensure_ascii=False)


@server.tool()
def seep_cms_fingerprint(
    url: str,
    referer: Optional[str] = None,
    user_agent: Optional[str] = None,
    cookie: Optional[str] = None,
    headers: Optional[List[str]] = None,
    deep: bool = False,
    out_dir: Optional[str] = None,
) -> str:
    """影视站 CMS / 源站指纹识别：一次告知「对面是什么站、源能不能直取、哪里开着门」。

    识别六个维度：
      ① 服务栈（Server / X-Powered-By / CDN·WAF 特征）
      ② CMS 家族（苹果CMS maccms10 / 海洋CMS seacms / 织梦 / WordPress / 自建）
      ③ 采集接口（/api.php/provide/vod/ 是否可直连 —— 影视站核心资产）
      ④ 播放器链路（MacPlayer / DPlayer / hls.js / aliplayer…）
      ⑤ TVBox 源配置（/tvbox/config.json 类聚合配置）
      ⑥ 暴露面（后台入口 / .env / .git / 备份文件 / install / phpinfo）

    行为约束：只发 GET，固定小规模探测（≤20 个路径），默认 400ms 间隔；
    不做字典爆破、不提交表单、不尝试登录。

    Args:
        url: 站点根地址（可省略协议，自动补 https://）
        referer: Referer
        user_agent: User-Agent（默认浏览器 UA）
        cookie: Cookie（站点需登录态时）
        headers: 额外请求头，形如 ["X-Token: abc"]
        deep: 是否追加暴露面探测（.env / .git / 备份 / install / phpinfo）
        out_dir: 证据输出目录
    """
    if not url:
        return "[ERROR]: 必须提供 url"

    args: List[str] = ["-Url", url]
    if referer:
        args += ["-Referer", referer]
    if user_agent:
        args += ["-UserAgent", user_agent]
    if cookie:
        args += ["-Cookie", cookie]
    for h in (headers or []):
        args += ["-Header", h]
    if deep:
        args += ["-Deep"]
    if out_dir:
        args += ["-OutDir", out_dir]

    ok, raw, payload = _run_web_script("cms-fingerprint.ps1", args, timeout=900)
    if not ok:
        return f"[ERROR]: CMS 指纹识别失败\n{raw}"

    summary = {
        "verdict": payload.get("Verdict", {}).get("Text"),
        "level": payload.get("Verdict", {}).get("Level"),
        "advice": payload.get("Verdict", {}).get("Advice"),
        "http": payload.get("Http"),
        "cdn_waf": payload.get("Cdn"),
        "cms_candidates": payload.get("Cms"),
        "confidence": payload.get("Confidence"),
        "players": payload.get("Players"),
        "m3u8_in_html": payload.get("M3u8InHtml"),
        "api_endpoint": payload.get("Api"),
        "tvbox_config": payload.get("TvBox"),
        "exposures": payload.get("Exposures"),
        "evidence_json": os.path.join(payload.get("OutDir", out_dir or ""), "evidence.json"),
        "report_md": os.path.join(payload.get("OutDir", out_dir or ""), "report.md"),
    }
    return json.dumps(summary, indent=2, ensure_ascii=False)


@server.tool()
def seep_web_pipeline(
    url: str,
    authorized: bool = False,
    scope: str = "",
    operator: str = "未填写",
    nuclei: bool = False,
    ffuf: bool = False,
    delay_ms: int = 300,
    out_dir: Optional[str] = None,
    stop_after: int = 4,
) -> str:
    """【Web 自动逆向流程】一条命令跑完：授权 → 指纹 → 举证 → （可选）nuclei/ffuf → 复测 → 报告。

    每一步都过硬阶段门（web-gate），跳步即停。这是「是否有泄露源风险」这类问题的标准入口：
    - 先指纹（对面是什么站、采集接口是否裸奔、有哪些暴露面）
    - 再逐条做可利用性举证（不是看到 200 就当漏洞）
    - 再复测（确认漏洞仍在，而非缓存/瞬时）
    - 最后出报告（专门针对源泄露，不是客户端 CWE-602 模板）

    Args:
        url: 目标站点根地址
        authorized: **必须为 True**，表示已获授权（G-Auth 门）；否则直接返回 BLOCK
        scope: 授权依据（如「站长自有站点全量授权」），必填
        operator: 授权人
        nuclei: 是否跑 nuclei 模板化漏扫（会慢 1-2 分钟）
        ffuf: 是否跑 ffuf 目录探测
        delay_ms: 请求间隔毫秒，默认 300
        out_dir: 案件目录（默认 D:\\Tool\\Web\\work\\webcase-<target>-<时间戳>）
        stop_after: 只跑到指定阶段（1-4），用于分次执行
    """
    if not authorized or not scope:
        return json.dumps({
            "status": "BLOCK",
            "stage": 0,
            "name": "AUTHORIZE",
            "action": "G-Auth 门未过：请确认目标为自有或已书面授权站点，然后传 authorized=true 与 scope='<授权依据>'",
        }, indent=2, ensure_ascii=False)

    args: List[str] = ["-Url", url, "-Authorized", "-Scope", scope, "-Operator", operator,
                       "-DelayMs", str(delay_ms), "-StopAfter", str(stop_after)]
    if nuclei:
        args += ["-Nuclei"]
    if ffuf:
        args += ["-Ffuf"]
    if out_dir:
        args += ["-OutDir", out_dir]

    ok, raw, payload = _run_web_script("web-pipeline.ps1", args, timeout=3600)
    if not ok:
        return f"[ERROR]: Web 流程执行失败\n{raw}"
    return json.dumps(payload, indent=2, ensure_ascii=False)


@server.tool()
def seep_web_gate(
    action: str,
    case_dir: str,
    stage: int = 1,
    source: Optional[str] = None,
    scope: Optional[str] = None,
    operator: Optional[str] = None,
    target: Optional[str] = None,
) -> str:
    """Web 审计硬阶段门：查/写/验 4 段证据链（0 授权 → 1 指纹 → 2 举证 → 3 复测 → 4 报告）。

    用途：手动分次执行时逐阶段推进；或审计他人产出的案件是否完整。

    Args:
        action: check（能不能进入某阶段）| record（收录某阶段产物）| status（全局状态）| init（建案）| authorize（登记授权）
        case_dir: 案件目录
        stage: 阶段号 0-4（check/record 必填）
        source: record 时的源 JSON 路径（工具输出的 evidence.json / proof JSON）
        scope: authorize 时的授权依据
        operator: authorize 时的授权人
        target: init 时的目标地址
    """
    args: List[str] = ["-Action", action, "-Dir", case_dir]
    if action in ("check", "record"):
        args += ["-Stage", str(stage)]
    if source:
        args += ["-Source", source]
    if scope:
        args += ["-Scope", scope]
    if operator:
        args += ["-Operator", operator]
    if target:
        args += ["-Target", target]

    ok, raw, payload = _run_web_script("web-gate.ps1", args, timeout=300)
    # BLOCK 也会返回合法 JSON，因此不能只看 ok
    if payload is None:
        return f"[ERROR]: gate 执行失败\n{raw}"
    return json.dumps(payload, indent=2, ensure_ascii=False)


@server.tool()
def seep_web_report(case_dir: str, out_file: Optional[str] = None) -> str:
    """从案件目录生成「Web 源与暴露面安全评估报告」（不重发请求，保证报告与证据一一对应）。

    与 seep_gen_security_report 的区别：后者是客户端 CWE-602 模板（branch_location / 内存补丁话术），
    对 .env / .git / 备份文件泄露是错的话术。本工具专适用源与暴露面场景，修复建议可执行（deny 规则/
    密钥轮换/日志审计/备份外迁）。

    stage 0/1 缺失时拒绕生成（证据链不完整不出报告）。

    Args:
        case_dir: 案件目录（由 web-pipeline 或 web-gate init 建立）
        out_file: 报告输出路径（默认 <case_dir>\\report.md）
    """
    if not os.path.isdir(case_dir):
        return f"[ERROR]: 案件目录不存在: {case_dir}"
    args: List[str] = ["-Dir", case_dir]
    if out_file:
        args += ["-OutFile", out_file]
    ok, raw, payload = _run_web_script("web-report.ps1", args, timeout=300)
    if payload is None:
        return f"[ERROR]: 报告生成失败\n{raw}"
    return json.dumps(payload, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 5. ReverseLab 攻防战术知识库与 CTF Payload 库
# ---------------------------------------------------------------------------
@server.tool()
def seep_kb_search(query: str, category: Optional[str] = None, limit: int = 10) -> str:
    """在 ReverseLab 183+ 逆向与 Web/PE/CVE 攻防知识库中进行全文搜索，快速定位战术指南。

    Args:
        query: 检索关键词（例如 'JWT', 'SSRF', 'vmp', 'proto pollution', 'heap', 'yara'）
        category: 可选限定目录分类（例如 'ctf-website', 'pe-reverse', 'apk-reverse', 'general'）
        limit: 最大返回文章数，默认 10
    """
    search_root = os.path.join(KB_DIR, category) if category else KB_DIR
    if not os.path.isdir(search_root):
        search_root = KB_DIR

    md_files = glob.glob(os.path.join(search_root, "**", "*.md"), recursive=True)
    pat = query.lower()
    
    hits = []
    for fpath in md_files:
        try:
            with open(fpath, "r", encoding="utf-8", errors="ignore") as fh:
                content = fh.read()
                title = ""
                for line in content.splitlines()[:5]:
                    if line.startswith("# "):
                        title = line.lstrip("# ").strip()
                        break
                
                score = 0
                if pat in Path(fpath).name.lower():
                    score += 10
                if pat in title.lower():
                    score += 8
                if pat in content.lower():
                    score += content.lower().count(pat)

                if score > 0:
                    rel = os.path.relpath(fpath, KB_DIR)
                    hits.append({
                        "path": rel.replace("\\", "/"),
                        "title": title or Path(fpath).stem,
                        "score": score,
                        "snippet": content[:300].strip().replace("\n", " ")
                    })
        except Exception:
            pass

    hits.sort(key=lambda x: x["score"], reverse=True)
    top = hits[:limit]
    if not top:
        return f"No articles found matching '{query}' in ReverseLab knowledge base."

    return json.dumps(top, indent=2, ensure_ascii=False)

@server.tool()
def seep_kb_read(article_path: str, max_chars: int = 6000) -> str:
    """读取 ReverseLab 知识库中某篇战术文档或技巧手册的全文内容。

    Args:
        article_path: 相对 KB 根目录的路径（可通过 seep_kb_search 获得，例如 'ctf-website/checklists/web-ctf-first-30-min.md'）
        max_chars: 最大返回字符数，默认 6000
    """
    target = os.path.join(KB_DIR, article_path)
    if not os.path.isfile(target):
        # 尝试模糊匹配
        matches = glob.glob(os.path.join(KB_DIR, "**", f"*{article_path}*"), recursive=True)
        if matches and os.path.isfile(matches[0]):
            target = matches[0]
        else:
            return f"[ERROR]: Article not found: {article_path}"

    with open(target, "r", encoding="utf-8", errors="replace") as fh:
        text = fh.read()
        if len(text) > max_chars:
            return text[:max_chars] + f"\n\n... [Truncated: Total {len(text)} characters, showing first {max_chars}]"
        return text

@server.tool()
def seep_kb_checklist(checklist_type: str = "web_first_30_min") -> str:
    """获取精炼的 CTF 竞技战术排查清单与工作流。

    Args:
        checklist_type: 清单类型，支持：
            - 'web_first_30_min': Web CTF 前 30 分钟应急排查指南
            - 'attack_matrix': 攻击面全景矩阵
            - 'evidence': 证据链归档标准模板
            - 'pe_ioc': PE 逆向 IOC 提取指南
            - 'pe_persistence': PE 启动持久化链路排查
            - 'yara_rules': YARA 规则编写指南
    """
    map_dict = {
        "web_first_30_min": "ctf-website/checklists/web-ctf-first-30-min.md",
        "attack_matrix": "ctf-website/checklists/attack-matrix.md",
        "evidence": "ctf-website/checklists/evidence.md",
        "pe_ioc": "pe-reverse/techniques/06-ioc-extraction/01-ioc-extraction.md",
        "pe_persistence": "pe-reverse/techniques/06-ioc-extraction/02-persistence-startup-chain.md",
        "yara_rules": "pe-reverse/techniques/07-yara-sigma/01-yara-rule-writing.md"
    }
    rel_path = map_dict.get(checklist_type.lower(), "ctf-website/checklists/web-ctf-first-30-min.md")
    return seep_kb_read(rel_path)

@server.tool()
def seep_kb_payloads(category: str = "all") -> str:
    """检索 CTF 常用高危漏洞 Exploit 种子与 Payload 集合（含 SQLi, SSTI, Prototype Pollution, JWT, SSRF, Deserialization 等）。

    Args:
        category: 类别过滤（'all', 'jwt', 'ssrf', 'sqli', 'ssti', 'prototype'），默认 'all'
    """
    payload_file = os.path.join(KB_DIR, "ctf-website", "payloads", "web-payload-seeds.md")
    if not os.path.isfile(payload_file):
        return "[ERROR]: Payload seeds file not found."

    with open(payload_file, "r", encoding="utf-8", errors="replace") as fh:
        content = fh.read()

    if category.lower() == "all":
        return content

    # 提取对应章节
    lines = content.splitlines()
    selected_lines = []
    capturing = False
    target = category.lower()

    for line in lines:
        if line.startswith("#"):
            if target in line.lower():
                capturing = True
            elif capturing and (line.startswith("## ") or line.startswith("# ")):
                break
        if capturing:
            selected_lines.append(line)

    if selected_lines:
        return "\n".join(selected_lines)
    return f"No section matching '{category}' in payloads file. Returning full document header:\n" + "\n".join(lines[:60])


# ---------------------------------------------------------------------------
# 6. 战术助手与安全评估增强工具 (Task Isolation, Triage, Report & IDA Bridge)
# ---------------------------------------------------------------------------

@server.tool()
def seep_task_init(task_name: str, description: str = "") -> str:
    """
    【工作空间铁律保障】为新任务一键在根目录下初始化独立的任务沙箱工作区。
    自动创建规范子目录：samples/, exports/, patches/, reports/，
    杜绝文件乱堆乱放和根目录污染。
    """
    clean_name = re.sub(r'[^\w\-]', '_', task_name.strip())
    if not clean_name:
        return "[ERROR] task_name 不能为空"
    
    task_path = os.path.join(BASE_DIR, clean_name)
    subdirs = ["samples", "exports", "patches", "reports"]
    
    try:
        os.makedirs(task_path, exist_ok=True)
        created_dirs = [clean_name]
        for sub in subdirs:
            p = os.path.join(task_path, sub)
            os.makedirs(p, exist_ok=True)
            created_dirs.append(f"{clean_name}/{sub}")
            
        readme_path = os.path.join(task_path, "README.md")
        if not os.path.exists(readme_path):
            with open(readme_path, "w", encoding="utf-8") as f:
                f.write(f"# 任务工作区: {clean_name}\n\n")
                f.write(f"- 创建时间: {subprocess.getoutput('date /t') if sys.platform == 'win32' else subprocess.getoutput('date')}\n")
                f.write(f"- 任务描述: {description or '授权软件安全检测与白盒鉴权脆弱性走查任务'}\n\n")
                f.write("## 目录约定\n")
                f.write("- `samples/`: 原始目标程序与待测样本\n")
                f.write("- `exports/`: 反编译伪代码、字符串导出、日志与分析证据\n")
                f.write("- `patches/`: 验证 PoC 代码、代理 DLL 跳板工程、热补丁\n")
                f.write("- `reports/`: 最终安全评估与漏洞复现报告\n")
        
        return json.dumps({
            "status": "Success",
            "task_directory": task_path,
            "created_directories": created_dirs,
            "message": f"任务工作区 [{clean_name}] 已成功创建！后续所有产物请严格保存于该目录内部。"
        }, indent=2, ensure_ascii=False)
    except Exception as e:
        return f"[ERROR] 初始化任务工作区失败: {str(e)}"


@server.tool()
def seep_auto_triage(target_path: str, task_name: Optional[str] = None) -> str:
    """
    一键全自动靶向侦察 (Auto Triage)：
    对给定目标（PE/EXE/DLL/APK/ELF）进行 360° 综合体检：
    1. 计算 MD5 / SHA256 文件哈希
    2. 探测文件类型与架构位数 (32/64 bit, x86/ARM)
    3. 枚举关键安全缓解机制 (Canary/NX/PIE/ASLR)
    4. 提取高价值鉴权/密钥/网络特征字符串
    5. 若提供 task_name，自动将完整报告输出到该任务的 reports/ 目录
    """
    if not os.path.exists(target_path):
        return f"[ERROR] Target path not found: {target_path}"
    
    t_path = Path(target_path).resolve()
    file_size = os.path.getsize(t_path)
    
    # 1. 计算哈希
    md5_cmd = [RABIN2_EXE, "-k", "md5", str(t_path)] if os.path.exists(RABIN2_EXE) else None
    sha256_cmd = [RABIN2_EXE, "-k", "sha256", str(t_path)] if os.path.exists(RABIN2_EXE) else None
    
    import hashlib
    with open(t_path, "rb") as f:
        data = f.read(1024 * 1024 * 50) # 最大前 50MB 计算
        md5_val = hashlib.md5(data).hexdigest()
        sha256_val = hashlib.sha256(data).hexdigest()

    # 2. 调用 r2 获取架构和安全缓解
    sec_info = "Unknown"
    bin_info = {}
    if os.path.exists(RABIN2_EXE):
        raw_info = _run_cmd([RABIN2_EXE, "-Ij", str(t_path)])
        try:
            bin_info = json.loads(raw_info).get("info", {})
        except Exception:
            pass
            
    # 3. 提取高价值安全关键词（License / VIP / Auth / Expire 等）
    sensitive_keywords = ["vip", "license", "auth", "expire", "token", "subscri", "register", "check", "trial", "valid"]
    matched_strings = []
    
    if os.path.exists(RABIN2_EXE):
        raw_str = _run_cmd([RABIN2_EXE, "-zj", str(t_path)])
        try:
            str_list = json.loads(raw_str).get("strings", [])
            for s in str_list:
                val = s.get("string", "")
                v_lower = val.lower()
                if any(k in v_lower for k in sensitive_keywords):
                    matched_strings.append({
                        "vaddr": hex(s.get("vaddr", 0)),
                        "string": val[:80]
                    })
                if len(matched_strings) >= 20:
                    break
        except Exception:
            pass

    triage_result = {
        "file_name": t_path.name,
        "file_size": f"{file_size / (1024 * 1024):.2f} MB",
        "hashes": {
            "md5": md5_val,
            "sha256": sha256_val
        },
        "binary_profile": {
            "arch": bin_info.get("arch", "unknown"),
            "bits": bin_info.get("bits", "unknown"),
            "format": bin_info.get("bintype", "unknown"),
            "canary": bin_info.get("canary", False),
            "nx": bin_info.get("nx", False),
            "pic": bin_info.get("pic", False),
            "stripped": bin_info.get("stripped", False),
            "compiler": bin_info.get("compiler", "unknown")
        },
        "auth_related_strings_sampled": matched_strings[:15],
        "recommended_action": (
            "检测到高价值鉴权关键词与符号，建议下一步："
            "1. 若存在 IDA 环境，直接使用 mcp_ida_get_function_by_name 或地址枚举决策分支；"
            "2. 若为本地逻辑判定，使用 seep_apk_gen_hook 或生成免杀热补丁跳板验证；"
            "3. 报告与验证代码请归档入对应任务的 reports/ 与 patches/。"
        )
    }
    
    if task_name:
        clean_task = re.sub(r'[^\w\-]', '_', task_name.strip())
        report_dir = os.path.join(BASE_DIR, clean_task, "reports")
        if os.path.exists(report_dir):
            out_file = os.path.join(report_dir, f"{t_path.stem}_triage.json")
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(triage_result, f, indent=2, ensure_ascii=False)
            triage_result["saved_report"] = out_file
            
    return json.dumps(triage_result, indent=2, ensure_ascii=False)


@server.tool()
def seep_ida_status() -> str:
    """
    检查本地 IDA Pro 逆向分析服务与 MCP 桥接器是否在线就绪。
    探测端口 127.0.0.1:13337。
    """
    import urllib.request
    url = "http://127.0.0.1:13337"
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=2) as resp:
            return json.dumps({
                "status": "Online",
                "code": resp.status,
                "message": "IDA Pro MCP 服务正在稳定运行！可直接调用 mcp_ida_* 工具链展开反编译与交叉引用深度分析。"
            }, indent=2, ensure_ascii=False)
    except Exception as e:
        return json.dumps({
            "status": "Offline / Unreachable",
            "detail": str(e),
            "hint": "若需使用 IDA 深度分析，请在 IDA Pro GUI 中确认插件已加载，或按下 Ctrl+Alt+M 唤醒。"
        }, indent=2, ensure_ascii=False)


@server.tool()
def seep_gen_security_report(
    task_name: str,
    target_name: str,
    vuln_type: str = "CWE-602: 客户端鉴权与状态判定缺陷",
    branch_location: str = "0x0",
    description: str = "",
    poc_summary: str = "",
    defense_recommendation: str = ""
) -> str:
    """
    自动生成专业级白盒安全漏洞评估报告。
    按照正规合规标准排版，包含漏洞成因、位点、复现 PoC 与企业级防护加固方案。
    报告自动落入任务文件夹的 reports/ 目录。
    """
    clean_task = re.sub(r'[^\w\-]', '_', task_name.strip())
    report_dir = os.path.join(BASE_DIR, clean_task, "reports")
    os.makedirs(report_dir, exist_ok=True)
    
    report_file = os.path.join(report_dir, f"{target_name}_security_assessment_report.md")
    
    now_str = subprocess.getoutput('date /t') if sys.platform == 'win32' else subprocess.getoutput('date')
    
    default_remediation = (
        "1. **服务端统一鉴权 (Server-side Enforcement)**：将核心特权逻辑迁移至云端，客户端仅作为渲染终端，所有受限资源由服务端颁发带有时间戳和数字签名的 Token 换取。\n"
        "2. **非对称公钥防篡改**：若需支持离线场景，必须使用 RSA/ECC 非对称签名，客户端仅保留公钥验签，私钥由授权服务器持有。\n"
        "3. **内存完整性保护**：启用 Windows `ProcessDynamicCodePolicy` 抑制动态内存写入，并在核心敏感模块增加代码段自校验哈希。"
    )
    
    remediation_text = defense_recommendation or default_remediation
    
    content = f"""# 软件安全评估与鉴权脆弱性走查报告

- **目标资产**: `{target_name}`
- **评估类型**: 白盒代码走查 / 客户端决策逻辑安全性验证
- **缺陷分类**: `{vuln_type}`
- **评估时间**: {now_str}
- **报告归属**: `{clean_task}/reports/`

---

## 1. 风险概述与脆弱性成因 (Vulnerability Summary)
{description or "在白盒审计过程中，发现该客户端采用本地离线决策逻辑，缺乏服务端强鉴权与非对称加密验签。客户端程序完全依据本地存储状态或单一标志位分支进行权限放行，构成 CWE-602 本地判定信任缺陷。"}

---

## 2. 关键判定决策位点 (Decision Branch Location)
- **判定函数 / 偏移位点**: `{branch_location}`
- **汇编指令与分支模式**:
```text
; 典型本地鉴权判断分支
TEST EAX, EAX
JZ   loc_restricted_feature  ; 本地跳转决定受限功能
```

---

## 3. 验证 PoC 与复现过程 (Proof of Concept)
{poc_summary or "通过动态 Hook / 内存标志位修正，成功验证在不经过服务端鉴权的前提下，本地逻辑可以直接放行相关受限功能。验证代码已归档至 patches/ 目录。"}

---

## 4. 纵深防护与企业级加固修复建议 (Remediation)
{remediation_text}
"""

    with open(report_file, "w", encoding="utf-8") as f:
        f.write(content)
        
    return json.dumps({
        "status": "Success",
        "report_path": report_file,
        "message": f"安全评估报告已正式生成并归档至: {clean_task}/reports/{os.path.basename(report_file)}"
    }, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------
def main():
    """MCP Server 启动入口，使用 stdio 协议与 AI Client 通信"""
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8")
            sys.stderr.reconfigure(encoding="utf-8")
            sys.stdin.reconfigure(encoding="utf-8")
        except Exception:
            pass

    # 父进程（dsh web / pi / codex）退出时，POSIX 下可能发 SIGTERM。
    # 转成 SystemExit 走正常收尾，避免裸抛堆栈。
    if hasattr(signal, "SIGTERM"):
        try:
            signal.signal(signal.SIGTERM, lambda *_a: sys.exit(0))
        except (ValueError, OSError, AttributeError):
            pass  # 非主线程或平台不支持时忽略

    try:
        server.run(transport="stdio")
    except KeyboardInterrupt:
        # Ctrl+C 会广播给整个控制台进程组：父进程与 MCP 子进程会同时收到。
        # 这属于正常关闭流程，静默退出即可，不要让异常沿着
        # anyio.run → asyncio.run → runpy.run_path 一路裸抛打印堆栈。
        pass
    except (BrokenPipeError, EOFError):
        # 父进程先退出导致 stdin/stdout 关闭，同样属于正常收尾
        pass


if __name__ == "__main__":
    main()
