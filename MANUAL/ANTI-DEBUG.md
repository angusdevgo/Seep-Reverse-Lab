# MANUAL — 反调试对抗与强反调试绕过 (Anti-Debug Bypass SOP)

> 本文件是当 Agent 在 G0/G1 阶段检测到目标存在**反调试或强对抗机制**时的标准化处置手册。
> 覆盖 Windows 用户态全量反调试技法、通用补丁模板与代理 DLL 框架接入指引。
>
> 读取顺序：先通过 `seep_auto_triage` 识别壳类型 → 与本文档对比签名 → 选择对应打桩策略。

---

## 一、 快速诊断表：常见反调试信号 → 处置路由

| 检测到的信号 | 最可能机制 | 首选处置策略 |
|---|---|---|
| `IsDebuggerPresent` 出现在导入表 | PEB.BeingDebugged | NOP / 硬编码返回 0 |
| `NtQueryInformationProcess` + 0x7 | ProcessDebugPort | Syscall Stub 替换 |
| `CheckRemoteDebuggerPresent` | 同上 | Hook 返回 FALSE |
| `GetTickCount` / `QueryPerformanceCounter` 频繁调用 | 时序反调试 | 钩子固定返回值 |
| `CreateToolhelp32Snapshot` + 进程名比对 | 调试器进程名检测 | Hook 过滤快照列表 |
| `OutputDebugString` 后检测错误码 | ODS 陷阱 | 无操作（正常运行不受影响） |
| `NtSetInformationThread` 0x11 | ThreadHideFromDebugger | Hook 丢弃该调用 |
| 注册表 `HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\AeDebug` | AeDebug 检测 | 值打补丁 / Hook RegQueryValueEx |
| 断点扫描 / 自校验 CRC | 内存完整性自检 | 修正 CRC 或 NOP 校验逻辑 |
| 驱动 `\Device\DebuggerDetect` / ObRegisterCallbacks | 内核级反调试 | → 参考第五节：内核层对抗 |

---

## 二、 用户态 PEB 系列反调试 —— 最常见（通用补丁）

### 2.1 `IsDebuggerPresent` → 返回值强制为 0

**原理**：`kernel32!IsDebuggerPresent` 本质只读 `PEB.BeingDebugged (offset 0x2)`。

**代理 DLL / Frida 修补（推荐）**：

```javascript
// Frida 方案
Interceptor.attach(Module.getExportByName('kernel32.dll', 'IsDebuggerPresent'), {
  onLeave: function(retval) { retval.replace(0); }
});
```

```cpp
// 内联汇编补丁（静态，适用于代理 DLL）
// 定位 IsDebuggerPresent 首地址，写入：
// XOR EAX, EAX
// RET
// 原始字节（x64）通常是: 65 48 8B 04 25 60 00 00 00 → 替换前 3 字节
BYTE patch[] = { 0x33, 0xC0, 0xC3 }; // xor eax,eax; ret
WriteProcessMemory(hProc, pIsDebuggerPresent, patch, sizeof(patch), nullptr);
```

### 2.2 `NtQueryInformationProcess` 信息类 7 (ProcessDebugPort) / 30 (ProcessDebugObjectHandle)

**原理**：成功连接调试器时 Port != 0。

```javascript
// Frida 方案
const NtQIP = Module.getExportByName('ntdll.dll', 'NtQueryInformationProcess');
Interceptor.attach(NtQIP, {
  onEnter(args) { this.cls = args[1].toInt32(); this.out = args[2]; },
  onLeave(retval) {
    if (this.cls === 7 || this.cls === 30) {
      this.out.writePointer(ptr(0));  // 清零 DebugPort / DebugObject
    }
  }
});
```

### 2.3 `NtSetInformationThread` → ThreadHideFromDebugger (0x11)

调用此系统调用后，调试器事件将对该线程不可见，导致断点失效。

```javascript
const NtSIT = Module.getExportByName('ntdll.dll', 'NtSetInformationThread');
Interceptor.attach(NtSIT, {
  onEnter(args) {
    if (args[1].toInt32() === 0x11) {
      args[1] = ptr(0);  // 替换为无害的 ThreadBasicInformation
    }
  }
});
```

---

## 三、 时序反调试 —— 高频坑（修复固定返回值）

调试状态下，`GetTickCount` / `QueryPerformanceCounter` 的推进速度远慢于正常运行，常被用来识别单步调试。

```javascript
// Frida 方案：固定时钟
let baseTick = Date.now();
Interceptor.replace(Module.getExportByName('kernel32.dll', 'GetTickCount'),
  new NativeCallback(() => {
    baseTick += 15;  // 模拟正常 15ms 系统时钟步进
    return baseTick;
  }, 'uint32', [])
);
```

---

## 四、 进程名 / 窗口名 / 文件路径特征检测 —— 改名或 Hook 快照

目标程序扫描进程快照（`CreateToolhelp32Snapshot + Process32Next`）比对调试器进程名：
`x64dbg.exe`、`ollydbg.exe`、`ida.exe`、`ida64.exe`、`cheatengine.exe` 等。

**最简单处置**：把调试器改名为 `explorer2.exe`、`chrome_x.exe` 等。

**进阶 Hook 方案**：

```javascript
// 过滤 Process32Next 快照，抹去调试器进程条目
const blacklist = ['x64dbg.exe', 'ida64.exe', 'ollydbg.exe', 'wireshark.exe'];
const Process32Next = Module.getExportByName('kernel32.dll', 'Process32NextW');
Interceptor.attach(Process32Next, {
  onLeave(retval) {
    if (retval.toInt32() !== 0) {
      const entry = this.context.rdx;  // PROCESSENTRY32W 结构
      const exeName = entry.add(44).readUtf16String();
      if (blacklist.some(b => exeName && exeName.toLowerCase().includes(b))) {
        // 递归调用直到返回非黑名单进程（简化处理：置为无害进程名）
        entry.add(44).writeUtf16String('System');
      }
    }
  }
});
```

---

## 五、 内核级反调试对抗（Ring0 / 驱动层）

> **适用场景**：游戏反作弊（ACE/EAC/BattlEye）、强保护商业软件、带 Ring0 驱动的许可校验模块。
> **注意**：内核对抗超出 Agent 全自动范畴，以下为指导性 SOP，需结合 WinDbg + 内核调试器手工处理。

### G0 阶段主动识别信号：
- `triage` 输出中存在 `.sys` 驱动签名或服务注册（HKLM\SYSTEM\CurrentControlSet\Services）
- 导入表出现 `NtLoadDriver`、`ZwCreateSection` 等内核接口
- 运行时观察到 `ObRegisterCallbacks` / `PsSetCreateProcessNotifyRoutine` 回调注册

### 处置策略（按难度升序）：
| 方案 | 适用条件 | 操作要点 |
|---|---|---|
| **Kernel Patch Guard 绕过** | 测试用 VM / Hyper-V | 关闭 Driver Signature Enforcement，加载调试补丁驱动 |
| **VirtualBox + DKOM** | 沙箱分析 | 修改 `EPROCESS.DebugPort = NULL` 绕过内核调试器检测 |
| **全量内存 Dump + 用户态重放** | 驱动已运行 | 在内核加载完毕后 dump 进程内存，在用户态 Loader 中重放 |
| **Emulation (Unidbg/QEMU)** | 需脱离真实 OS | 在模拟环境中重跑关键算法，完全规避内核对抗 |

---

## 六、 代理 DLL 注入框架模板（统一打桩方式）

> 适用于不能直接修改宿主 EXE（如有数字签名）的场景。

所有上述 Hook 均可集成在以下代理 DLL 框架中，加载即自动注入，宿主签名完好：

```cpp
// anti_debug_patch.cpp — 代理 DLL 打桩框架（以 version.dll 为例）
#include <Windows.h>

// 实际 version.dll 导出函数转发（保留原功能）
#pragma comment(linker, "/export:GetFileVersionInfoA=C:\\Windows\\System32\\version.GetFileVersionInfoA")
// ... 其他导出

void ApplyAntiDebugPatches() {
    // 1. 清除 PEB.BeingDebugged
    __asm {
        mov eax, fs:[30h]  // PEB
        mov byte ptr [eax+2], 0  // BeingDebugged = 0
    }
    // 2. Hook NtQueryInformationProcess (如上 Frida 方案的 C++ 等效)
    // ...
}

BOOL APIENTRY DllMain(HMODULE hModule, DWORD reason, LPVOID lpvReserved) {
    if (reason == DLL_PROCESS_ATTACH) ApplyAntiDebugPatches();
    return TRUE;
}
```

---

## 七、 两击熔断纪律 —— 反调试对抗的止损规则

| 情形 | 触发条件 | 处置 |
|---|---|---|
| 用户态 Hook 无效（程序仍检测到调试器）| 同构打桩 2 次失败 | 停止，升级为内核层分析 |
| 内核层方案部署失败 | 同构 2 次失败 | 停止，改用 Emulation（Unidbg/QEMU）路线 |
| Emulation 行为无法覆盖 | 无法还原算法 | 输出"该目标超出当前工具链全自动范畴"，转人工分析 |
