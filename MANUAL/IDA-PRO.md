# IDA Pro 准备指引

> **IDA Pro 是商业软件，不随本包分发。** 你需要自备授权，或使用免费替代方案。

---

## 方案 A：已有 IDA Pro 授权（推荐，功能最全）

### 支持版本
IDA Pro **8.4+ / 9.x**（含 Hex-Rays 反编译器）

### 安装后需要做的

1. **确认 Python 运行时存在**（IDA 自带）：
   ```
   <IDA安装目录>\python311\python.exe
   ```

2. **安装 ida-pro-mcp 到 IDA 的 Python**：
   ```powershell
   & "<IDA安装目录>\python311\python.exe" -m pip install ida-pro-mcp
   ```

3. **运行 `install.ps1`** —— 它会自动探测 IDA 路径并写入 `mcp.json`。
   若探测失败，手工填 `~/.pi/agent/mcp.json`（见下方【两种运行模式】）。

4. **使用方式**：在 pi 里说「用 IDA 分析这个文件」，`ida-reverse` Skill 会自动唤醒 IDA 并挂载 MCP
   （轮询 `http://127.0.0.1:13337` 就绪）。

### 两种运行模式（IDA 9.x 起）

`install-ida.ps1` 会**优先探测 IDA 9.x 原生模块模式**，失败才回退到传统脚本模式。

#### 模式 A：IDA 9.x 原生 `idalib_supervisor`（推荐，无需 GUI 常驻）

IDA 9.4+ 把 MCP 服务做成了可独立运行的 `idalib` 模块，由 supervisor 拉起，
**不需要手工打开 IDA 图形界面**：

```json
"ida": {
  "command": "<IDA安装目录>\\python311\\python.exe",
  "args": ["-m", "ida_pro_mcp.idalib_supervisor", "--stdio"],
  "env": { "PYTHONIOENCODING": "utf-8" },
  "transport": "stdio",
  "lifecycle": "eager",
  "requestTimeoutMs": 180000
}
```

#### 模式 B：传统 `server.py` 脚本模式（IDA 8.4 ~ 9.3）

```json
"ida": {
  "command": "<IDA安装目录>\\python311\\python.exe",
  "args": ["<IDA安装目录>\\python311\\Lib\\site-packages\\ida_pro_mcp\\server.py"],
  "env": { "PYTHONIOENCODING": "utf-8" },
  "transport": "stdio",
  "lifecycle": "eager",
  "requestTimeoutMs": 180000
}
```

> 不确定用哪种？直接跑 `powershell -File .\setup\install-ida.ps1`，脚本会自动判定并打印
> 实际选用的模式（`配置为 IDA 原生模块运行模式` 或 `配置为 server.py 脚本模式`）。

#### DSH 风格的配置示例

```yml
- id: ida-mcp
  name: '@deepseek-ai/dsh-mcp-client'
  config:
    serverName: ida
    transport: stdio
    command: '<IDA安装目录>\python311\python.exe'
    args:
      - '-m'
      - 'ida_pro_mcp.idalib_supervisor'
      - '--stdio'
    env:
      PYTHONIOENCODING: utf-8
```

### 购买渠道
- 官方：https://hex-rays.com/ida-pro
- 免费版 IDA Free（无 Hex-Rays 反编译）：https://hex-rays.com/ida-free

---

## 方案 B：免费替代（无 IDA 授权时）

**核心结论：seep MCP 的 8 个 Radare2 工具已覆盖大部分场景，无需 IDA 也能干活。**

| 能力 | IDA MCP | 免费替代 |
| :--- | :--- | :--- |
| 快速侦察（架构/壳/熵/字符串） | — | ✅ `seep_r2_info` / `seep_r2_strings` |
| 反汇编（含交叉引用） | ✅ | ✅ `seep_r2_disasm` |
| 反编译为类 C 伪代码 | ✅ Hex-Rays | ✅ `seep_r2_decompile` |
| 二进制差分 | — | ✅ `seep_r2_diff` |
| 汇编 ↔ 机器码 | — | ✅ `seep_r2_asm` |
| 函数表 / 导入导出 | ✅ | ✅ `seep_r2_functions` |
| 结构体恢复 | ✅ | ⚠️ Ghidra |
| 类型推断 | ✅ | ⚠️ Ghidra |

### 推荐组合

```
基础层：seep MCP（r2 八件套）      ← 脚本自动装，开箱可用
增强层：Ghidra（免费，含反编译）    ← 需要时下载
可选层：IDA Free（无反编译）        ← 需要 GUI 时
```

### Ghidra 安装

```powershell
# 需先装 JDK 17+
winget install EclipseAdoptium.Temurin.17.JDK
# 下载 Ghidra
# https://github.com/NationalSecurityAgency/ghidra/releases
```

> `Tool/kb/tools/skills/mcp/GhidraMCP/` 提供了 Ghidra 桥接 MCP，可按需注册。

---

## 方案 C：只用 Radare2（最轻量）

**完全跳过 IDA**，只依赖 seep MCP：

```powershell
# install.ps1 已自动装 radare2 到 tools/radare2/
# 直接用这些工具：
#   seep_r2_info / _strings / _functions / _disasm / _decompile / _diff / _asm
```

对以下任务**足够**：
- 壳检测与熵分析
- 字符串与端点提取
- 授权判定点定位
- 补丁点确认（配合 `seep_r2_asm` 验字节）
- Android SO 分析

**不足**：
- 复杂 C++ 逆向的类型恢复
- 大规模交叉引用图谱
- 大型二进制的交互式分析

---

## 三种方案对比

| | 方案 A（IDA Pro） | 方案 B（免费组合） | 方案 C（仅 r2） |
| :--- | :--- | :--- | :--- |
| **成本** | 商业授权 | 免费 | 免费 |
| **反编译** | ✅ Hex-Rays（最强） | ⚠️ Ghidra（次之） | ⚠️ r2 伪代码 |
| **结构体恢复** | ✅ | ⚠️ 部分 | ❌ |
| **上手成本** | 低（自动联动） | 中 | 最低 |
| **覆盖场景** | 全部 | 90% | 70% |

> **建议**：先用**方案 C** 跑通流程，遇到真正需要深度反编译的目标再上方案 A。
