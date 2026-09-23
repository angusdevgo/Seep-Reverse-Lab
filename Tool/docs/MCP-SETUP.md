# MCP 配置与验证 (MCP-SETUP)

> 本工作台靠 **3 个 MCP** 提供工具能力。本文说明：**它们是什么、装到哪、怎么验证、出问题怎么办。**
>
> 📦 **各 MCP 依赖的工具从哪里下载** → 见 **`Tool/docs/DOWNLOADS.md`**

---

## 一、MCP 与 Skill 的关系

```
Skill（提示词层）       →  告诉 agent「该做什么、走哪条路」
MCP（工具层）           →  给 agent「实际干活的手」
```

**举例**：`apkseep` Skill 说「用 jadx 反编译这个 APK」→ agent 调 `seep_apk_decompile`
→ seep MCP 内部驱动 jadx 完成反编译。

> **Skill 是说明书，MCP 是工具。** 两者都装好才能干活。

---

## 二、3 个已注册 MCP

| MCP | 工具数 | 用途 | 依赖 | 安装方式 |
| :--- | :---: | :--- | :--- | :--- |
| **seep** ⭐ | **22** | 二进制逆向 + APK 逆向 + Frida 生成 + 知识库 | radare2 / jadx / apktool | 本包自带 + 脚本下载工具 |
| **ida** | **~243** | IDA 全套分析链 | **你自备的 IDA Pro** | 脚本装 MCP + 你装 IDA |
| **playwright** | — | 浏览器自动化 | npx | 自动（npx 按需拉取） |

### seep MCP 的 22 个工具

| 分组 | 工具 |
| :--- | :--- |
| 状态环境 (2) | `seep_status` · `seep_ida_status` |
| 二进制 r2 (8) | `seep_r2_info` · `_cmd` · `_strings` · `_functions` · `_disasm` · `_decompile` · `_diff` · `_asm` |
| Android (5) | `seep_apk_info` · `_decompile` · `_unpack` · `_smali_search` · `_gen_hook` |
| 知识库 (4) | `seep_kb_search` · `_read` · `_checklist` · `_payloads` |
| 流程编排 (3) | `seep_task_init` · `seep_auto_triage` · `seep_gen_security_report` |

---

## 三、安装过程（`install-pi.ps1` 自动完成）

```
1. 备份现有 ~/.pi/agent/ 配置
2. 复制 Skill  →  ~/.pi/agent/skills/
3. 复制提示词  →  ~/.pi/agent/SYSTEM.md · AGENTS.md
4. 复制扩展    →  ~/.pi/agent/extensions/
5. 生成 mcp.json：
     · <SEEP_ROOT>  → 本包实际路径
     · <IDA_ROOT>   → 自动探测（D:\Tool\IDA Pro / C:\Program Files\IDA Pro / C:\IDA Pro）
     · <IDA_PYTHON> → 探测到的 IDA Python
     · playwright token → 需你自填（不用浏览器自动化可留空）
6. 写 settings.json（12 个 pi packages）
7. 执行 pi update --extensions
```

**生成的 `~/.pi/agent/mcp.json` 结构**：

```json
{
  "mcpServers": {
    "seep": {
      "command": "python",
      "args": ["<本包路径>\\Tool\\mcp\\seep_mcp_server.py"],
      "env": { "PYTHONIOENCODING": "utf-8" },
      "transport": "stdio"
    },
    "ida": {
      "command": "<IDA Python 路径>",
      "args": ["<IDA 安装目录>\\Lib\\site-packages\\ida_pro_mcp\\server.py"],
      "transport": "stdio",
      "lifecycle": "eager",
      "requestTimeoutMs": 180000
    },
    "playwright": {
      "command": "npx",
      "args": ["-y", "@playwright/mcp@latest", "--extension"],
      "env": { "PLAYWRIGHT_MCP_EXTENSION_TOKEN": "<你的token>" },
      "transport": "stdio"
    }
  }
}
```

---

## 四、⚠️ 关键约束：`Tool/mcp/Tool/` 不可搬动

`seep_mcp_server.py` **内部硬编码**了运行时目录：

```python
BASE_DIR = os.path.dirname(os.path.abspath(__file__))   # = Tool/mcp/
TOOL_DIR = os.path.join(BASE_DIR, "Tool")               # = Tool/mcp/Tool/
SAFE_DIR = os.path.join(TOOL_DIR, "safe")               # = Tool/mcp/Tool/safe/
KB_DIR   = os.path.join(TOOL_DIR, "reverselab", "kb")   # = Tool/mcp/Tool/reverselab/kb
```

因此：

| 依赖 | 必须位于 |
| :--- | :--- |
| radare2 | `Tool/mcp/Tool/safe/radare2/bin/` |
| jadx | `Tool/mcp/Tool/safe/jadx/bin/` |
| apktool | `Tool/mcp/Tool/safe/apktool/` |
| Hook 模板 | `Tool/mcp/Tool/safe/hook-mcp/templates/` |
| 知识库 | `Tool/mcp/Tool/reverselab/kb/` |

> **搬走任何一个，对应的 MCP 工具就会失效。**

---

## 五、验证 MCP 是否就绪

### 方法 1：跑自检脚本（推荐）

```powershell
cd Desktop\Seep\setup
powershell -ExecutionPolicy Bypass -File .\verify.ps1
```

### 方法 2：在 pi 里问

```
你：seep_status 能跑吗？
pi：[返回 radare2 / jadx / apktool / 知识库 的就绪状态]
```

### 方法 3：手工检查

```powershell
# 1. 配置无占位符残留
Select-String -Path "$env:USERPROFILE\.pi\agent\mcp.json" -Pattern "<[A-Z_]+>"

# 2. seep MCP 语法可解析
python -c "import ast; ast.parse(open(r'C:\...\Seep\Tool\mcp\seep_mcp_server.py',encoding='utf-8').read())"

# 3. 知识库在位
(Get-ChildItem "C:\...\Seep\Tool\mcp\Tool\reverselab\kb" -Recurse -Filter *.md).Count   # 期望 ≥289
```

---

## 六、工具 → MCP 依赖对照（排障用）

| MCP 工具 | 依赖的目录 / 工具 | 缺失时的现象 |
| :--- | :--- | :--- |
| `seep_kb_*`（4 个） | `Tool/mcp/Tool/reverselab/kb/` | 检索返回空 / 报路径不存在 |
| `seep_r2_*`（8 个） | `Tool/mcp/Tool/safe/radare2/bin/` | "radare2 not found" |
| `seep_apk_decompile` | `Tool/mcp/Tool/safe/jadx/bin/` | "jadx not found" |
| `seep_apk_unpack` | `Tool/mcp/Tool/safe/apktool/` | "apktool not found" |
| `seep_apk_gen_hook` | `Tool/mcp/Tool/safe/hook-mcp/templates/` | 模板缺失 |
| `mcp_ida_*`（~243 个） | 自备 IDA Pro + `Tool/mcp/Tool/safe/ida-pro-mcp/` | "IDA not available" |
| playwright 工具 | npx + token | 浏览器不可用 |

**排障口诀**：工具报错 → 看它读哪个目录 → 检查该目录是否存在且非空。

---

## 七、IDA Pro 不可用时的降级路线

> **原则**：不阻塞、不报错，直接用 `seep_r2_*` 继续推进。

| 需求 | seep MCP 替代 |
| :--- | :--- |
| 架构 / 壳 / 熵 / 字符串 | `seep_r2_info` · `seep_r2_strings` |
| 反汇编 + 交叉引用 | `seep_r2_disasm` · `seep_r2_functions` |
| 类 C 伪代码 | `seep_r2_decompile` |
| 二进制差分 | `seep_r2_diff` |
| 汇编 ↔ 机器码 | `seep_r2_asm` |

报告中应标注：**"未使用 IDA 反编译器，伪代码质量受限"**。

详见 `MANUAL/IDA-PRO.md`（含 3 种方案对比）。

---

## 八、可选注册的 MCP（默认关闭）

`reverselab` 自带 3 个 MCP，源码在 `Tool/mcp/Tool/reverselab/tools/skills/mcp/`，
**默认不注册**。需要时手工加入 `mcp.json`：

| MCP | 位置 | 用途 |
| :--- | :--- | :--- |
| **ReverseLabToolsMCP** | `.../mcp/ReverseLabToolsMCP/` | reverselab 主 MCP（150+ 工具） |
| **JSHookLocal** | `.../mcp/JSHookLocal/` | JS Hook 本地服务 |
| **GhidraMCP** | `.../mcp/GhidraMCP/` | Ghidra 桥接 |

**注册示例**：

```json
"reverselab": {
  "command": "python",
  "args": ["<本包路径>\\Tool\\mcp\\Tool\\reverselab\\tools\\skills\\mcp\\ReverseLabToolsMCP\\reverse_lab_tools_mcp.py"],
  "cwd": "<本包路径>\\Tool\\mcp\\Tool\\reverselab",
  "transport": "stdio"
}
```

> ⚠️ 需先装其 Python 依赖（见该目录 `requirements.txt`）。

---

## 九、常见问题

| 问题 | 处理 |
| :--- | :--- |
| pi 启动后 MCP 没加载 | **重启 pi**（MCP 在启动时注册） |
| `seep` 工具全部不可用 | 检查 `mcp.json` 的 `seep.args[0]` 路径是否存在 |
| `seep_kb_*` 报错 | 检查 `Tool/mcp/Tool/reverselab/kb/` 是否 ≥289 篇 |
| `seep_r2_*` 报错 | 重跑 `setup\install-tools.ps1` |
| `ida` 工具报错 | 确认 IDA 已装 + `mcp.json` 里 ida 路径正确 |
| MCP 配置文件被我改坏了 | 重跑 `setup\install-pi.ps1`（会自动备份旧配置） |
| 想看 MCP 报错日志 | pi 启动时的 stderr；或手工 `python Tool\mcp\seep_mcp_server.py` 看输出 |

---

## 十、手工验证 seep MCP（不通过 pi）

```powershell
cd Desktop\Seep\Tool\mcp
python seep_mcp_server.py
# 正常应挂起等待 stdio 输入（无报错即 OK）
# Ctrl+C 退出
```

若报 `ModuleNotFoundError: mcp` → 重跑 `setup\install-python.ps1`。
