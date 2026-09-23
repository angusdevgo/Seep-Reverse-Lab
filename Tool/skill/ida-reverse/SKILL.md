---
name: ida-reverse
description: 当用户要求“使用IDA Pro进行逆向分析”、分析指定可执行文件/库、反编译函数或通过 IDA Pro 分析目标时触发此技能。能够全自动唤醒 IDA Pro、加载分析目标二进制、静默等待自动分析完成，并通过 MCP 协议无缝进行函数枚举、反编译及交叉引用分析。
license: MIT
compatibility: Windows 10 / Windows 11 x64, IDA Pro 9.x
---

# ida-reverse — IDA Pro 自动化逆向战术技能

当用户发出指令：**“使用IDA Pro进行逆向分析”** 或要求加载某个二进制目标时，严格按照本流程全自动执行。

---

## 一、 自动化启动与目标加载（Zero-Touch Launch）

当主人指定目标文件（或当前工作区中的题目二进制）时，使用 `powershell` 后台启动 IDA Pro 并加载目标：

```powershell
# 启动 IDA Pro 打开目标二进制文件并置于后台运行
$targetPath = "目标文件的绝对路径"
$idaExe = "D:\Tool\IDA Pro\ida.exe"
Start-Process -FilePath $idaExe -ArgumentList "`"$targetPath`""
```

### 握手检测与自愈等待：
目标启动后，后台内置的 `mcp-plugin.py` 与 `idapythonrc.py` 会自动在本地 `127.0.0.1:13337` 开启 JSON-RPC 服务。
通过执行以下轻量检查轮询确认 IDA 是否就绪：

```powershell
python -c "
import urllib.request, json, time

for i in range(15):
    try:
        req = urllib.request.Request('http://127.0.0.1:13337/mcp', data=json.dumps({'jsonrpc':'2.0','id':1,'method':'get_metadata','params':[]}).encode(), headers={'Content-Type':'application/json'})
        with urllib.request.urlopen(req, timeout=1) as resp:
            data = json.loads(resp.read().decode())
            if 'result' in data and data['result']:
                print('IDA Ready:', data['result'])
                break
    except Exception:
        time.sleep(1)
"
```

---

## 二、 逆向阶段与 MCP 战术调度

握手成功后，使用 Pi 的 MCP 工具（`mcp_ida_*`）或直接执行 RPC 进行分析：

1. **信息收集（Triage）**：
   - 获取元数据：调用 `get_metadata` 确认目标架构、基址与模块名称。
   - 获取入口与关键函数：调用 `get_entry_points`、`list_functions`。
   - 敏感字符串检索：调用 `list_strings_filter` 过滤 `flag`、`key`、`password`、`http` 等关键模式。

2. **控制流与逻辑拆解（Decompile & Trace）**：
   - 核心逻辑反编译：调用 `decompile_function` 获取目标函数的伪代码（Hex-Rays C 代码）。
   - 汇编与指令审计：调用 `disassemble_function` 分析关键汇编与加密循环分支。
   - 交叉引用追溯：调用 `get_xrefs_to` / `get_callers` 还原加密函数、检查函数的调用拓扑。

3. **动态协同（Annotate）**：
   - 对已识别的关键变量与子例程调用 `rename_function`、`rename_local_variable`、`set_comment` 实时回写至主人的 IDA 界面中。
