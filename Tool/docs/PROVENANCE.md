# 组件溯源清单 (PROVENANCE)

> 回答一个问题：**每个 Skill / MCP 由哪些文件夹组成，依赖什么，装到哪。**
> 用于理解"为什么不能只复制一个配置文件"。

---

## 一、核心原则

> **Skill / MCP 不是单个文件，而是「配置 + 文件夹」的组合。**
> 只复制配置，目标机器必然跑不起来。

| 类别 | 由什么组成 |
| :--- | :--- |
| **Skill** | 一个目录（`SKILL.md` + `references/` + `scripts/` + `evals/` + `evidence/`） |
| **MCP** | 一个启动脚本 + 它读取的**外部数据目录** + 依赖的**外部工具** |
| **提示词** | `SYSTEM.md` / `AGENTS.md` + `extensions/*.ts` |

---

## 二、Skill 溯源（9 个）

| # | Skill | 本包位置 | 安装目标 | 文件数 | 体积 |
| :--- | :--- | :--- | :--- | :---: | :--- |
| 1 | **softseep** ⭐总控 | `Tool/skill/softseep/` | `~/.pi/agent/skills/softseep/` | 9 | 364 KB |
| 2 | **apkseep** | `Tool/skill/apkseep/` | `~/.pi/agent/skills/apkseep/` | 115 | 2.2 MB |
| 3 | **ida-reverse** | `Tool/skill/ida-reverse/` | `~/.pi/agent/skills/ida-reverse/` | 1 | 4 KB |
| 4 | **client-license-validation-bypass** | `Tool/skill/client-license-validation-bypass/` | `~/.pi/agent/skills/` | 1 | 32 KB |
| 5 | **reverse-engineering** | `Tool/skill/safe-skills/reverse-engineering/` | 同上 | 15 | 380 KB |
| 6 | **apk-reverse** | `Tool/skill/safe-skills/apk-reverse/` | 同上 | 8 | 52 KB |
| 7 | **radare2** | `Tool/skill/safe-skills/radare2/` | 同上 | 3 | 20 KB |
| 8 | **mcp-js-reverse-playbook** | `Tool/skill/safe-skills/mcp-js-reverse-playbook/` | 同上 | 13 | 24 KB |
| 9 | **ida-reverse**（safe 版） | `Tool/skill/safe-skills/ida-reverse/` | 同上 | 3 | 28 KB |

### ⚠ apkseep 的上游归属（合规声明）

**`apkseep` 衍生自开源项目，已按 MIT 许可保留署名。**

| 项 | 值 |
| :--- | :--- |
| **上游仓库** | https://github.com/newliver666/apk-reverse |
| **许可** | MIT License — Copyright (c) 2026 apk-reverse contributors |
| **本包位置** | `Tool/upstream/apk-reverse/`（178 文件 / 3.1 MB） |
| **归属声明位置** | `apkseep/SKILL.md` frontmatter 内（`ATTRIBUTION` 注释块） |

**上游比 apkseep 多出的部分**（apkseep 是精简衍生版）：

| 上游独有 | 本包位置 | 价值 |
| :--- | :--- | :--- |
| `docs/tool-verification/`（**26 文件**） | `Tool/upstream/apk-reverse/docs/tool-verification/` | ⭐ 自审证据记录：逐脚本 `TOOL-VERDICTS`、`FINDINGS`（含推翻自己的结论）、20+ `EXTENSION-*` 实测记录 |
| `tests/`（**24 文件**） | `Tool/upstream/apk-reverse/tests/` | ⭐ stdlib 离线测试套件（unit/cli/integration），**无需设备与网络** |
| `tests/benchmark.md` | 同上 | B1–B13 公开靶场矩阵（含负面结果） |
| `capabilities.py` | `Tool/upstream/apk-reverse/skills/apk-reverse/scripts/` | 能力自检（G2 门依赖） |
| `check_routing.py` 等 5 个 | `Tool/upstream/apk-reverse/` | 一致性检查（CI 跑） |
| `skills/apk-reverse/`（114 文件） | `Tool/upstream/apk-reverse/skills/apk-reverse/` | 上游原版，可与 apkseep 对照 |

> **为什么入包**：apkseep 的 `SKILL.md` 声称的“四大硬性质量门禁（G1-G4）”与“离线测试套件”，
> 其**证据**在上游的 `tests/` 与 `docs/tool-verification/` 里。不入包，实习生就无法验证
> 这些声明是否成立。

> **运行测试**（可选）：`cd Tool/upstream/apk-reverse && python -m pytest -q`
> （需先 `pip install pytest`；不连设备、不联网）

### softseep 内部构成（总控 + 按需加载的 references）

```
softseep/
├── SKILL.md                    ← 总控（253 行）：G-Auth 门 + 自动判型 + 路由矩阵
└── references/                 ← 按需加载，不预先全读
    ├── windows-sop.md          6 步标准化流水线
    ├── patching-dictionary.md  汇编打桩速查字典
    ├── defense-in-depth.md     五层纵深防御
    ├── ui-verification.md      跨进程 UI 验收工装
    ├── compiler-pitfalls.md    编译器陷阱（写代理 DLL 前必读）
    ├── project-paradigms.md    九型范式库（项目A~I 的技术内核）
    ├── license-validation.md   许可/激活/卡密校验手册（16 节）
    └── tooling.md              工具脚本索引
```

### apkseep 内部构成（渐进式披露）

```
apkseep/
├── SKILL.md        （432 行）
├── references/     45 个（symptom index / gates / 13 问分类 …）
├── scripts/        56 个（dex_patch_bytes / dex_mem_scan / doctor …）
├── evals/          （评测用例）
└── evidence/       （能力矩阵与已知限制）
```

---

## 三、MCP 溯源（3 个默认注册）

> 📖 **完整的 MCP 配置、验证与排障** → 见 **`Tool/docs/MCP-SETUP.md`**
> 本节只讲“由哪些文件夹组成”。
> 📦 **各工具下载来源** → 见 **`Tool/docs/DOWNLOADS.md`**

### ① seep MCP（22 工具）— 自研

| 组成 | 位置 | 说明 |
| :--- | :--- | :--- |
| **启动脚本** | `Tool/mcp/seep_mcp_server.py` | 42 KB，主程序 |
| **自检脚本** | `Tool/mcp/test_seep_mcp.py` | 9 个测试套件 |
| **启动器** | `Tool/mcp/run_seep_mcp.bat` | Windows 启动封装 |
| **⭐ 运行时根目录** | **`Tool/mcp/Tool/`** | MCP 内部硬编码 `TOOL_DIR = <脚本目录>/Tool` |
| **⭐ 知识库依赖** | `Tool/mcp/Tool/reverselab/kb/`（**289 篇 .md**） | `seep_kb_search` 等 4 个工具读这里 |
| **LLM 索引** | `Tool/mcp/Tool/reverselab/docs/llms.txt` | MCP 启动时读取 |
| **外部工具依赖** | `Tool/mcp/Tool/safe/radare2/bin/`（脚本下载） | `seep_r2_*` 8 个工具 |
| **外部工具依赖** | `Tool/mcp/Tool/safe/jadx/bin/` + `.../apktool/`（脚本下载） | `seep_apk_*` 5 个工具 |
| **Hook 模板** | `Tool/mcp/Tool/safe/hook-mcp/templates/` | `seep_apk_gen_hook` |

> **关键（排障必读）**：`seep_mcp_server.py` 第 28–44 行硬编码：
> ```python
> BASE_DIR = os.path.dirname(os.path.abspath(__file__))   # = Tool/mcp/
> TOOL_DIR = os.path.join(BASE_DIR, "Tool")               # = Tool/mcp/Tool/
> SAFE_DIR = os.path.join(TOOL_DIR, "safe")               # = Tool/mcp/Tool/safe/
> R2_BIN_DIR = os.path.join(SAFE_DIR, "radare2", "bin")
> KB_DIR = os.path.join(TOOL_DIR, "reverselab", "kb")
> ```
> **所以 `Tool/` 必须与 `seep_mcp_server.py` 同级，不能搬动。**

**工具分组**：
```
状态环境(2)   seep_status · seep_ida_status
二进制 r2(8)  seep_r2_info · _cmd · _strings · _functions · _disasm · _decompile · _diff · _asm
Android(5)    seep_apk_info · _decompile · _unpack · _smali_search · _gen_hook
知识库(4)     seep_kb_search · _read · _checklist · _payloads
流程编排(3)   seep_task_init · seep_auto_triage · seep_gen_security_report
```

### ② ida MCP（~243 工具）

| 组成 | 位置 | 说明 |
| :--- | :--- | :--- |
| **MCP 服务** | `tools/ida-pro-mcp/`（脚本下载） | `server.py` + 插件 |
| **⭐ 宿主依赖** | **你自备的 IDA Pro** | 商业授权，**不随包分发** |
| **Python 运行时** | IDA 内置的 `python311` | 由 `install-pi.ps1` 探测 |

> 没有 IDA Pro 时，该 MCP 不可用；用 `seep_r2_*` + Ghidra 替代（见 `MANUAL/IDA-PRO.md`）。

### ③ playwright MCP

| 组成 | 位置 | 说明 |
| :--- | :--- | :--- |
| **MCP 服务** | npm `@playwright/mcp` | `npx` 按需拉取 |
| **扩展 token** | `mcp.json` 中 `PLAYWRIGHT_MCP_EXTENSION_TOKEN` | **需你自填** |

### 可选注册：reverselab 自带的 3 个 MCP

源码在 `Tool/mcp/Tool/reverselab/tools/skills/mcp/`，**默认不注册**，需要时手动加入 `mcp.json`：

| MCP | 位置 | 用途 |
| :--- | :--- | :--- |
| **ReverseLabToolsMCP** | `Tool/mcp/Tool/reverselab/tools/skills/mcp/ReverseLabToolsMCP/` | reverselab 主 MCP（150+ 工具） |
| **JSHookLocal** | `Tool/mcp/Tool/reverselab/tools/skills/mcp/JSHookLocal/` | JS Hook 本地服务 |
| **GhidraMCP** | `Tool/mcp/Tool/reverselab/tools/skills/mcp/GhidraMCP/` | Ghidra 桥接 |

---

## 四、提示词与扩展溯源

| 文件 | 本包位置 | 安装目标 | 作用 |
| :--- | :--- | :--- | :--- |
| **SYSTEM.md** | `Tool/prompts/SYSTEM.md` | `~/.pi/agent/SYSTEM.md` | 主提示词：人格 + **lab 开关协议** + 思维重定向 + 反退缩十项 + 提效规则 |
| **AGENTS.md** | `Tool/prompts/AGENTS.md` | `~/.pi/agent/AGENTS.md` | 跨 agent 通用版（Codex / Claude Code / OpenCode） |
| **security-audit-interceptor.ts** | `Tool/prompts/extensions/` | `~/.pi/agent/extensions/` | 底座 BLOCK_NONE 注入 + **lab 标志文件门控** + 快捷口令 + 敏感词替换 |
| **load-system-prompt.ts** | `Tool/prompts/extensions/` | `~/.pi/agent/extensions/` | 加载自定义提示词 |

### lab 模式状态文件

| 项 | 值 |
| :--- | :--- |
| 路径 | `~/.pi/agent/lab-mode.flag` |
| 写入时机 | 输入 `lab：` |
| 删除时机 | 输入 `退出实验` |
| 作用 | 扩展每次读此文件决定是否启用敏感词替换；**状态在磁盘，切模型/长上下文都不丢** |

---

## 五、知识库溯源

| 组成 | 本包位置 | 说明 |
| :--- | :--- | :--- |
| **kb/** | `Tool/mcp/Tool/reverselab/kb/` | **289 篇 .md**（ctf-website / apk-reverse / pe-reverse / general） |
| **boards/** | `Tool/mcp/Tool/reverselab/boards/` | 攻击网（按信号路由到技术文件） |
| **tools/skills/mcp/** | `Tool/mcp/Tool/reverselab/tools/skills/mcp/` | 3 个 MCP 源码 |
| **docs/** | `Tool/mcp/Tool/reverselab/docs/` | 含 `llms.txt`（seep MCP 引用的 LLM 索引） |
| **scripts/** | `Tool/mcp/Tool/reverselab/scripts/` | 知识库辅助脚本 |
| **AGENTS.md / CLAUDE.md / SKILLS.md / AI-USAGE.md** | `Tool/mcp/Tool/reverselab/` | reverselab 自带的 agent 协议 |

> 已剔除工作目录：`cases/ logs/ tmp/ exports/ samples/ projects/ patches/ reports/ notes/ site/`

---

## 六、脚本溯源

| 脚本 | 本包位置 | 作用 |
| :--- | :--- | :--- |
| `case-init.ps1` | `Tool/scripts/` | 任务建档门禁（一任务一目录） |
| `refresh-tool-index.ps1` | `Tool/scripts/` | 工具链健康自检 |
| `trigger_ida_mcp.ps1` | `Tool/scripts/` | 静默唤醒 IDA + 挂 MCP |
| `master-route.ps1` | `Tool/scripts/` | 主路由 |
| `start_mcp.py` | `Tool/scripts/` | MCP 启动 |
| `shot_ida.ps1` / `temp_ocr.ps1` | `Tool/scripts/` | 截图 / OCR 辅助 |
| `apk/decode.ps1` | `Tool/scripts/apk/` | jadx + apktool 一键解包 |
| `apk/rebuild-sign-install.ps1` | `Tool/scripts/apk/` | 重打包 → 对齐 → 签名 → 装机 |
| `apk/frida-run.ps1` | `Tool/scripts/apk/` | 设备枚举 + Spawn/Attach 注入 |
| `apk/manifest-summary.ps1` | `Tool/scripts/apk/` | Manifest 摘要 |

（`.sh` 版为 macOS/Linux 等价脚本）

---

## 七、外部工具依赖（脚本下载，不在包内）

> 下载目标统一为 **`Tool/mcp/Tool/safe/`**（MCP 硬编码要求）。

| 工具 | 服务的 MCP / Skill | 下载目标 | 体积 |
| :--- | :--- | :--- | :--- |
| **radare2** | `seep_r2_*`（8 工具） | `Tool/mcp/Tool/safe/radare2/` | ~39 MB |
| **jadx** | `seep_apk_decompile` | `Tool/mcp/Tool/safe/jadx/` | ~460 MB |
| **apktool** | `seep_apk_unpack` | `Tool/mcp/Tool/safe/apktool/` | ~24 MB |
| **playwright-mcp** | playwright MCP | `Tool/mcp/Tool/safe/playwright-mcp/` | ~45 MB |
| **js-reverse-mcp** | js-reverse-mcp MCP | `Tool/mcp/Tool/safe/js-reverse-mcp/` | ~234 MB |
| **ida-pro-mcp** | ida MCP | `Tool/mcp/Tool/safe/ida-pro-mcp/` | ~79 MB |

---

## 八、依赖链速查（排障用）

```
seep_kb_* 四个工具   →  Tool/mcp/Tool/reverselab/kb/（289 篇）
seep_r2_* 八个工具   →  Tool/mcp/Tool/safe/radare2/bin/
seep_apk_* 五个工具  →  Tool/mcp/Tool/safe/jadx/ + apktool/
seep_apk_gen_hook   →  Tool/mcp/Tool/safe/hook-mcp/templates/
ida MCP              →  自备 IDA Pro + Tool/mcp/Tool/safe/ida-pro-mcp/
playwright MCP       →  npx + PLAYWRIGHT_MCP_EXTENSION_TOKEN
softseep 路由         →  Tool/skill/softseep/（含 8 个 references）
apkseep 全链路        →  Tool/skill/apkseep/（45 refs + 56 scripts）
```

**排障口诀**：某个 MCP 工具报错 → 先看它读哪个目录 → 检查该目录是否存在且非空。
**特别注意**：`Tool/mcp/Tool/` 不可搬动 —— MCP 内部硬编码了 `TOOL_DIR = <脚本目录>/Tool`。

---

## 九、案例层溯源（项目A~I）

| 案例 | 源（脱敏前） | 范式类型 |
| :--- | :--- | :--- |
| 项目A | 单进程经典工具 | 单进程纯离线 |
| 项目B | 多进程模拟器 | 多进程混合 |
| 项目C | 压缩工具商业套件 | 资源模板 + 显示层伪造 |
| 项目D | 下载工具 | 壳保护 + 多策略 |
| 项目E | 卸载工具 | VM + 在线 → patch |
| 项目F | 搜索工具 | .NET 混淆 → Keygen |
| 项目G | 播放工具 | 自引用校验 → 补判定点 |
| 项目H | 截图工具 | 公钥替换 Keygen |
| 项目I | 开始菜单工具 | RSA 弱模 → 验签入口 |

**脱敏范围**：产品名 / 公司名 / 同厂兄弟产品 / 哈希 / 绝对路径 / 版本号 / 厂商域名 → 全部替换。
**保留**：RVA / 文件偏移 / 原始字节 / 补丁字节 / 汇编指令 / 算法常量 / CWE 编号 / 工具名。
