---
name: ida-reverse
description: 当用户要求“使用IDA Pro进行逆向分析”、分析指定可执行文件/库、反编译函数或通过 IDA Pro 分析目标时触发此技能。能够全自动唤醒 IDA Pro、加载分析目标二进制、静默等待自动分析完成，并通过 MCP 协议无缝进行函数枚举、反编译及交叉引用分析。
license: GPL-3.0
compatibility: Windows 10 / Windows 11 x64, macOS, Linux, IDA Pro 7.7~9.x
---

# ida-reverse — IDA Pro 自动化逆向战术技能

当用户发出指令：**“使用IDA Pro进行逆向分析”** 或要求加载某个二进制目标时，严格按照本流程全自动执行。

---

## 一、 自动化智能定位与目标加载（Zero-Touch Launch）

当主人指定目标文件（或当前工作区中的题目二进制）时，使用以下自适应脚本**动态定位 IDA 可执行文件**并启动：

```powershell
# 1. 动态自适应探测 IDA 可执行文件路径（杜绝写死盘符）
$candidates = @(
    'D:\Tool\IDA Pro\ida.exe',
    'C:\Program Files\IDA Pro\ida.exe',
    'C:\Program Files\IDA Professional 9.0\ida.exe',
    'C:\Program Files\IDA Pro 9.4\ida.exe',
    'C:\Program Files\IDA Professional 9.4\ida.exe',
    'C:\IDA Pro\ida.exe',
    'C:\IDA\ida.exe',
    'D:\IDA Pro\ida.exe',
    'E:\IDA Pro\ida.exe',
    'F:\IDA Pro\ida.exe',
    (Join-Path $env:USERPROFILE 'Desktop\IDA Pro\App\IDA Pro\ida.exe'),
    (Join-Path $env:USERPROFILE 'Desktop\IDA Pro 9.4\App\IDA Pro\ida.exe'),
    (Join-Path $env:USERPROFILE 'Tools\IDA Pro 9.4\App\IDA Pro\ida.exe')
)

$idaExe = $null
foreach ($c in $candidates) {
    if (Test-Path $c) { $idaExe = (Resolve-Path $c).Path; break }
}

if (-not $idaExe) {
    # 注册表探测
    foreach ($rp in @('HKCU:\Software\Hex-Rays\IDA Pro', 'HKLM:\SOFTWARE\Hex-Rays\IDA Pro')) {
        if (Test-Path $rp) {
            $p = (Get-ItemProperty $rp -ErrorAction SilentlyContinue).InstallDir
            if ($p -and (Test-Path (Join-Path $p 'ida.exe'))) { $idaExe = Join-Path $p 'ida.exe'; break }
        }
    }
}

# 2. 拉起 IDA Pro 加载目标二进制
$targetPath = "目标文件的绝对路径"
if ($idaExe) {
    Start-Process -FilePath $idaExe -ArgumentList "`"$targetPath`""
} else {
    Write-Host "[!] 未检测到本地 IDA Pro，自动降级为内置 Radare2 无头分析 (seep_r2_*)" -ForegroundColor Yellow
}
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
        with urllib.request.urlopen(req, timeout=2) as resp:
            if resp.status == 200:
                print('IDA MCP Connected')
                break
    except:
        time.sleep(1)
"
```

---

## 二、 核心分析能力矩阵（MCP 工具映射）

当连接就绪后，直接通过 `ida` MCP 工具调度分析：

| 战术动作 | 对应 MCP 工具 / API | 产出与用途 |
|---|---|---|
| **元数据提取** | `mcp_ida_get_metadata` | 获取目标架构、位宽、编译器与基址信息 |
| **入口点探测** | `mcp_ida_get_entry_points` | 快速锁定 main / OEP / 初始化入口 |
| **函数列表枚举** | `mcp_ida_list_functions` | 检索 `verify_license`、`check_vip`、`sub_*` |
| **C-Like 伪代码反编译** | `mcp_ida_decompile_function` | 获得 Hex-Rays 反编译高质量 C 伪代码 |
| **交叉引用回溯** | `mcp_ida_get_xrefs_to` / `_from` | 逆向回溯调用链，寻找鉴权判断上游来源 |
| **结构体/局部变量重命名**| `mcp_ida_set_local_name` | 动态修复混淆符号，增强可读性 |

---

## 三、 降级处理策略

如果目标机器未安装 IDA Pro 或端口未监听，**严禁向用户抛出异常中断**，立即无缝降级为工作台内置的 **`seep_r2_*`** 系列工具（Radare2 无头反编译与交叉引用分析）。
