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
import zipfile
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Any

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
R2_EXE = os.path.join(R2_BIN_DIR, "radare2.exe")
RABIN2_EXE = os.path.join(R2_BIN_DIR, "rabin2.exe")
RADIFF2_EXE = os.path.join(R2_BIN_DIR, "radiff2.exe")
RASM2_EXE = os.path.join(R2_BIN_DIR, "rasm2.exe")
RAHASH2_EXE = os.path.join(R2_BIN_DIR, "rahash2.exe")

JADX_BAT = os.path.join(SAFE_DIR, "jadx", "bin", "jadx.bat")
APKTOOL_JAR = os.path.join(SAFE_DIR, "apktool", "apktool.jar")
APKTOOL_BAT = os.path.join(SAFE_DIR, "apktool", "apktool.bat")

KB_DIR = os.path.join(TOOL_DIR, "reverselab", "kb")
LLMS_TXT = os.path.join(TOOL_DIR, "reverselab", "docs", "llms.txt")
HOOK_TEMPLATES_DIR = os.path.join(SAFE_DIR, "hook-mcp", "templates")

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
3. 动态 Hook 插件自动生成 (Frida JS, LSPilot / BeanShell)
4. ReverseLab 183+ 逆向与 Web/PE/CVE 攻防战术知识库检索与即用 Payload
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
    """寻找 Java 运行时可执行路径"""
    if shutil.which("java"):
        return "java"
    candidates = [
        r"D:\Tool\JDK\bin\java.exe",
        r"D:\Tool\Android Studio\jbr\bin\java.exe",
        r"C:\Program Files\Java",
        r"C:\Program Files\Eclipse Adoptium",
        r"C:\Program Files\Microsoft"
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
        if os.path.isdir(c):
            for root, _, files in os.walk(c):
                if "java.exe" in files:
                    return os.path.join(root, "java.exe")
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

    status = {
        "name": "seep",
        "description": "AI-Native Reverse Engineering Toolkit MCP Server",
        "base_directory": BASE_DIR,
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
def seep_r2_disasm(binary_path: str, target: str = "main", lines: int = 60) -> str:
    """反汇编指定函数或地址，输出包含交叉引用 (XREF)、局部变量与源码行号提示的汇编代码。

    Args:
        binary_path: 目标二进制文件路径
        target: 目标函数名、符号或虚拟地址（例如 'main', 'sym.imp.puts', '0x1013ef0'）
        lines: 当以地址为目标时反汇编的最大指令行数，默认 60
    """
    if not os.path.isfile(binary_path):
        return f"[ERROR]: Target file does not exist: {binary_path}"

    # 优先尝试函数级反汇编 pdf，若不是已知函数则按指令行数 pd 反汇编
    cmd = f"aaa; pdf @ {target}"
    out = _run_cmd([R2_EXE, "-q", "-e", "scr.color=0", "-c", cmd, os.path.abspath(binary_path)], timeout=60)
    cleaned = _clean_r2_output(out)
    output_lines = [l for l in cleaned.splitlines() if not l.startswith("INFO:") and not l.startswith("WARN:")]
    
    if not output_lines or all(not l.strip() for l in output_lines):
        cmd = f"pd {lines} @ {target}"
        out = _run_cmd([R2_EXE, "-q", "-e", "scr.color=0", "-c", cmd, os.path.abspath(binary_path)], timeout=60)
        cleaned = _clean_r2_output(out)
        output_lines = [l for l in cleaned.splitlines() if not l.startswith("INFO:") and not l.startswith("WARN:")]

    return "\n".join(output_lines) or "[Disassembly empty or symbol not found]"

@server.tool()
def seep_r2_decompile(binary_path: str, target: str = "main") -> str:
    """将目标函数反编译为类 C 伪代码（使用 radare2 内置反编译引擎 pdc）。

    Args:
        binary_path: 目标二进制文件路径
        target: 目标函数名称或虚拟地址（例如 'main', 'sym.verify_key'）
    """
    if not os.path.isfile(binary_path):
        return f"[ERROR]: Target file does not exist: {binary_path}"

    cmd = f"aaa; pdc @ {target}"
    out = _run_cmd([R2_EXE, "-q", "-e", "scr.color=0", "-c", cmd, os.path.abspath(binary_path)], timeout=60)
    cleaned = _clean_r2_output(out)
    output_lines = [l for l in cleaned.splitlines() if not l.startswith("INFO:") and not l.startswith("WARN:")]
    return "\n".join(output_lines) or "[Decompile output empty]"

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
# 3. Android APK 逆向与动态 Hook 生成
# ---------------------------------------------------------------------------
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
# 4. ReverseLab 攻防战术知识库与 CTF Payload 库
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
# 5. 战术助手与安全评估增强工具 (Task Isolation, Triage, Report & IDA Bridge)
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
    
    server.run(transport="stdio")

if __name__ == "__main__":
    main()
