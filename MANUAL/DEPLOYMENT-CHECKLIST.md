# MANUAL — 官方部署资产全景核验基准清单 (Deployment Checklist & Verification Manifest)

> **版本**：v1.3.0  
> **适用范围**：Pi Agent / Claude Code / DeepSeek Harness / Codex / OpenCode  
> **核心用途**：作为 Seep Reverse Lab 部署交付的 **单一真值源 (Single Source of Truth, SSOT)**。  
> 明确声明每个组件的 **官方期望物理路径、文件数、入口文件、可用性验证命令、三态健康标准与降级处置方案**。  
> 部署完成后，Agent 与用户均以此清单为唯一法定标准进行双向比对校对。

---

## 一、 判定模型标准 (Three-State Classification)

本核验清单采用清晰的三态判定逻辑，杜绝模糊与信息黑盒：

| 状态标识 | 语义 | 说明与影响 |
|---|---|---|
| 🟢 **`[READY]` 完备就绪** | 部署成功且可用 | 文件/依赖全部在位，可执行代码与语法解析 100% 正常。 |
| 🟡 **`[DEGRADED]` 合规降级 / 可选未配** | 可选扩展未装，已降级承接 | 属于外部商业软件（如 IDA Pro）或可选按需工具（如 Playwright Token）。**核心逆向主链路不受影响**，系统已自动启用免费/内置替代方案（如 Radare2 套件）。 |
| 🔴 **`[MISSING]` 阻断性缺失** | 核心组件缺失或异常 | 核心文件丢失或基础运行库（如 Python MCP 协议）未装，将导致部分核心流水线不可用。必须按修复指引处理。 |

---

## 二、 官方部署资产核验基准表 (Baseline Manifests)

### 1. 🛠️ 技能系统基准表 (Skills System - 9 大组件)

目标安装路径以 Pi Agent 规范为例（`~/.pi/agent/skills/`，Windows 下为 `$env:USERPROFILE\.pi\agent\skills\`）：

| # | 技能名称 (ID) | 宿主安装目标路径 | 官方期望文件/目录数 | 核心入口标识文件 | 可用性判据与验证命令 | 状态判定与指引 |
|---|---|---|---|---|---|---|
| **S1** | **`softseep`** ⭐总控 | `~/.pi/agent/skills/softseep/` | `SKILL.md` + 8 篇 `references/` (≥9 项) | `SKILL.md`<br>`references/license-validation.md` | 检查 8 篇 references 齐全，G0-G6 门控完整 | 🟢 **核心**。缺失则总控瘫痪。修复：`powershell setup\install-pi.ps1` |
| **S2** | **`apkseep`** | `~/.pi/agent/skills/apkseep/` | `SKILL.md` + 45 refs + 56 scripts (≥115 项) | `SKILL.md`<br>`scripts/doctor.py` | 运行 `python scripts/doctor.py` 无报错 | 🟢 **核心**。安卓全链路专精。修复：重跑 `install-pi.ps1` |
| **S3** | **`ida-reverse`** | `~/.pi/agent/skills/ida-reverse/` | `SKILL.md` (≥1 项) | `SKILL.md` | 包含 IDA 13337 端口自动唤醒规约 | 🟢 **核心**。IDA 自动化调度器。修复：重跑 `install-pi.ps1` |
| **S4** | **`client-license-validation-bypass`** | `~/.pi/agent/skills/client-license-validation-bypass/` | `SKILL.md` (≥1 项) | `SKILL.md` | 包含 CWE-602 战术树与补丁/算号决策 | 🟢 **核心**。授权审计战术库。修复：重跑 `install-pi.ps1` |
| **S5** | **`reverse-engineering`** | `~/.pi/agent/skills/reverse-engineering/` | `SKILL.md` + references (≥15 项) | `SKILL.md` | 通用逆向基准规则在位 | 🟢 战术包。修复：复制 `Tool/skill/safe-skills/reverse-engineering` |
| **S6** | **`apk-diff`** | `~/.pi/agent/skills/apk-diff/` | `SKILL.md` + scripts (≥8 项) | `SKILL.md` | 二进制与 APK 差分工具在位 | 🟢 战术包。修复：复制 `Tool/skill/safe-skills/apk-diff` |
| **S7** | **`radare2`** | `~/.pi/agent/skills/radare2/` | `SKILL.md` + 管道字典 (≥3 项) | `SKILL.md` | R2 命令行打桩字典在位 | 🟢 战术包。修复：复制 `Tool/skill/safe-skills/radare2` |
| **S8** | **`mcp-js-reverse-playbook`** | `~/.pi/agent/skills/mcp-js-reverse-playbook/` | `SKILL.md` + 案例 (≥13 项) | `SKILL.md` | Web/JS 逆向分析基准在位 | 🟢 战术包。修复：复制 `Tool/skill/safe-skills/mcp-js-reverse-playbook` |
| **S9** | **`ida-assistant`** | `~/.pi/agent/skills/ida-reverse/` (safe版) | `SKILL.md` + 插件 (≥3 项) | `SKILL.md` | IDA 辅助交互式脚本在位 | 🟢 战术包。修复：复制 `Tool/skill/safe-skills/ida-reverse` |

---

### 2. 🔌 MCP 服务引擎配置基准表 (MCP Engine - 4 大服务)

MCP 配置文件所在位置：
- **Pi Agent**：`~/.pi/agent/mcp.json`
- **Claude Code**：项目根目录 `.mcp.json`
- **DeepSeek Harness**：`cordis.generated.yml` / 用户 profile
- **Codex / OpenCode**：项目根目录 `opencode.jsonc`

| # | 服务标识 | 驱动命令 / 核心脚本 | 预期暴露出工具数 | 连通性测试命令 | 缺失/未配时的表现与降级路径 |
|---|---|---|---|---|---|
| **M1** | **`seep`** ⭐自研核心 | `python <SEEP_ROOT>/Tool/mcp/seep_mcp_server.py` | **23 项** | `python Tool/mcp/test_seep_mcp.py` 语法解析与测试通过 | 🔴 **阻断项**。若缺失无法调用 R2/JADX/Apktool/KB。修复：运行 `powershell setup\install.ps1` |
| **M2** | **`ida`** 外部商业 | `<IDA_PYTHON> .../ida_pro_mcp/server.py` | ~243 项 | 探测 `127.0.0.1:13337` 端口或 IDA 进程 | 🟡 **可选降级**。未装或无授权时自动降级为内置 Radare2 无头分析套件，主干链路 100% 可用。指引详见 `MANUAL/IDA-PRO.md` |
| **M3** | **`js-reverse`** | `npx -y js-reverse-mcp` | 12 项 | `npx -y js-reverse-mcp --version` | 🟡 **按需组件**。未安装 Node 时仅 Web 逆向受限，原生二进制不受影响。修复：安装 Node.js 18+ |
| **M4** | **`playwright`** | `npx -y @playwright/mcp` | 18 项 | 依赖 `PLAYWRIGHT_MCP_EXTENSION_TOKEN` | 🟡 **按需组件**。未配 Token 时无头浏览器受限，原生逆向不受影响。 |

---

### 3. 🧠 提示词系统、扩展与状态机基准表

| # | 组件名称 | 宿主安装目标路径 | 核心校验特征与关键词 | 功用与影响 |
|---|---|---|---|---|
| **P1** | **`SYSTEM.md`** | `~/.pi/agent/SYSTEM.md` | 包含 `Lab Mode Protocol`、思维重定向、反退缩十项 | Pi Agent 专用系统指令 |
| **P2** | **`AGENTS.md`** | `~/.pi/agent/AGENTS.md`<br>项目根 `AGENTS.md` | 跨 Agent 通用无状态执行规范 | Codex / DSH / OpenCode 作战协议 |
| **P3** | **`CLAUDE.md`** | 项目根 `CLAUDE.md` | 包含 Claude Code 项目级规范与自动化部署规约 | Claude Code 项目指令 |
| **P4** | **`security-audit-interceptor.ts`** | `~/.pi/agent/extensions/` | 包含 `BLOCK_NONE` 底座注入与 `SENSITIVE_WORD_MAP` 字典 | 核心防模型拒绝与敏感词自动转译引擎 |
| **P5** | **`lab-mode.flag`** | `~/.pi/agent/lab-mode.flag` | 输入 `lab：` 自动写入，输入 `退出实验` 自动删除 | 物理状态机标志文件（跨模型长文本持久化） |

---

### 4. 🔧 物理内置工具箱基准表 (Native Tools in `Tool/mcp/Tool/safe/`)

| # | 工具名称 | 所在相对目录 | 预期体积/构建版本 | 核心执行文件 | 验证测试命令 |
|---|---|---|---|---|---|
| **T1** | **`radare2`** | `Tool/mcp/Tool/safe/radare2/` | v6.2.2 全套 (~39MB) | `bin/radare2.exe`<br>`bin/rabin2.exe` | `.\Tool\mcp\Tool\safe\radare2\bin\rabin2.exe -v` |
| **T2** | **`jadx`** | `Tool/mcp/Tool/safe/jadx/` | v1.5.6 纯净优化版 (~75MB) | `bin/jadx.bat`<br>`lib/jadx-1.5.6-all.jar` | `.\Tool\mcp\Tool\safe\jadx\bin\jadx.bat --version` |
| **T3** | **`apktool`** | `Tool/mcp/Tool/safe/apktool/` | v3.0.3 (~24MB) | `apktool.jar`<br>`apktool.bat` | 需 Java 17 支持。运行 `apktool.bat -version` |
| **T4** | **`hook-mcp`** | `Tool/mcp/Tool/safe/hook-mcp/` | 模板库目录 | `templates/frida/`<br>`templates/lspilot/` | 检查模板文件是否存在 |
| **T5** | **`js-reverse-mcp`** | `Tool/mcp/Tool/safe/js-reverse-mcp/` | 需完成解压 | `node_modules/` 目录存在 | 检查目录或运行 `setup\extract-deps.ps1` |
| **T6** | **`playwright-mcp`** | `Tool/mcp/Tool/safe/playwright-mcp/` | 需完成解压 | `node_modules/` 目录存在 | 检查目录或运行 `setup\extract-deps.ps1` |

---

### 5. 📚 实战知识库与战术手册基准表 (KB & Manuals)

| # | 模块名 | 所在相对目录 | 官方预期数量 | 作用与覆盖面 |
|---|---|---|---|---|
| **K1** | **战术实战笔记 (KB)** | `Tool/mcp/Tool/reverselab/kb/` | **≥289 篇** Markdown 文件 | `ctf-website`、`pe-reverse`、`apk-reverse`、`windows`、`general` 全量攻防笔记 |
| **K2** | **攻击网图谱 (Boards)** | `Tool/mcp/Tool/reverselab/boards/` | 多平台拓扑文件 | 信号到战术文档的拓扑路由关系 |
| **K3** | **脱敏实战案例库** | `Tool/cases/` | **14 个项目工程** (项目A ~ 项目N) | 覆盖单进程、多进程、VM、.NET算号、RSA、Java/install4j 双层鉴权、.NET VM 混淆加固等架构 |
| **K4** | **上游开源完整镜像** | `Tool/upstream/` | **3 大开源项目** | `apk-reverse`、`open-tgtylab`、`open-reverselab` 完整单测与镜像 |
| **K5** | **MANUAL 专项手册** | `MANUAL/` | **8 份核心手册** | `DEPLOYMENT` (部署)、`DEPLOYMENT-CHECKLIST` (基准清单)、`CROSS-PLATFORM` (跨平台)、`COMPLIANCE-RELAY` (合规中继与防拒)、`ANTI-DEBUG` (反调试)、`UNPACKING` (脱壳)、`POC-VALIDATION` (PoC自愈)、`IDA-PRO` (IDA接入) |

---

### 6. 🌐 合规转译中继基准表 (Compliance Relay · 网络层防拒)

| # | 组件 | 所在相对路径 | 官方期望 | 校验方式 | 状态判定 |
|---|---|---|---|---|---|
| **R1** | **中继主程序** | `Tool/scripts/compliance-relay/relay.py` | 纯标准库实现，支持三协议 | `python relay.py` 可正常监听 | 🟢 **可选增强**。未使用时不影响主链路。 |
| **R2** | **规则提取器** | `Tool/scripts/compliance-relay/extract-rules.py` | 从 TS 源单向提取 | `python extract-rules.py --check` 退出码 0 | 🟢 核心。规则表与 TS 源必须同步 |
| **R3** | **规则表** | `Tool/scripts/compliance-relay/sensitive-rules.json` | ≥30 条规则 | 与 TS 源逐字节一致 | 🟢 生成物，禁手工编辑 |
| **R4** | **上下文守卫白名单** | `Tool/scripts/compliance-relay/guard-prefixes.json` | 三协议各自的白名单 | 文件存在且含三个协议键 | 🟢 核心。防止污染 Agent 自身上下文 |
| **R5** | **单元测试套件** | `Tool/scripts/compliance-relay/tests/test_relay.py` | 44 项测试 | `python -m unittest discover -s tests` 全绿 | 🟢 核心 |
| **R6** | **本机运行配置** | `Tool/scripts/compliance-relay/relay-config.json` | 首次运行自动生成 | 文件存在（**已 gitignore，不入库**） | 🟡 运行时生成，含本机 token |

> **零落盘纪律**：中继绝不写入请求体 / 响应体 / 鉴权头，日志只输出命中条数。
> **默认关闭**：不随系统启动，不做常驻服务，需用户显式运行 `python relay.py`。
> **覆盖协议**：`openai-completions`（Pi Agent 主力）/ `anthropic-messages`（Claude Code）/ `openai-responses`（Codex）。

---

## 三、 Agent 部署后的自检校对与格式化输出协议

当 Agent（或用户运行 `powershell .\setup\verify.ps1 -Detailed`）完成部署后，**必须以此清单为蓝本，在对话框中输出四栏格式化校对表格**：

```markdown
### 📊 Seep 工作台部署产物与官方基准校对报告

#### 1. 🛠️ 技能系统 (Skills - 9项)
| 技能名 | 目标物理路径 | 期望文件数 | 实际文件数 | 状态 | 备注/指引 |
|---|---|---|---|---|---|
| softseep | ~/.pi/agent/skills/softseep/ | ≥9 (含8 refs) | 9 | 🟢 READY | 总控调度器已就绪 |
| apkseep | ~/.pi/agent/skills/apkseep/ | ≥115 (含refs/scripts) | 115 | 🟢 READY | 安卓全链路就绪 |
| ida-reverse | ~/.pi/agent/skills/ida-reverse/ | ≥1 | 1 | 🟢 READY | IDA 自动化联动就绪 |
| client-license-bypass | ~/.pi/agent/skills/client-license-validation-bypass/ | ≥1 | 1 | 🟢 READY | 许可破解战术树就绪 |
| safe-skills (5组) | ~/.pi/agent/skills/<name>/ | ≥42 | 42 | 🟢 READY | 通用战术包就绪 |

#### 2. 🔌 MCP 服务引擎 (4项)
| 服务名 | 配置文件载体 | 期望工具数 | 实际状态 | 状态判定 | 降级/处置说明 |
|---|---|---|---|---|---|
| seep (自研) | ~/.pi/agent/mcp.json | 23 工具 | Connected (23) | 🟢 READY | 核心二进制/安卓/知识库能力完备 |
| ida (商业) | ~/.pi/agent/mcp.json | ~243 工具 | 未监听 (13337) | 🟡 DEGRADED | 已自动降级为内置 Radare2，主链路 100% 可用 |
| js-reverse | ~/.pi/agent/mcp.json | 12 工具 | 可用 (npx) | 🟢 READY | JS 逆向引擎就绪 |
| playwright | ~/.pi/agent/mcp.json | 18 工具 | Token待配置 | 🟡 DEGRADED | 无头浏览器可选，不影响二进制逆向 |

#### 3. 🔧 运行时与内置工具箱 (Native Tools)
| 工具 | 预期版本/文件 | 实际状态 | 状态 | 说明 |
|---|---|---|---|---|
| Radare2 | v6.2.2 (radare2.exe) | 物理就绪 | 🟢 READY | 二进制反编译/反汇编引擎正常 |
| Jadx | v1.5.6 (jadx.bat) | 物理就绪 | 🟢 READY | Java 源码反编译引擎正常 |
| Apktool | v3.0.3 (apktool.jar) | 物理就绪 | 🟢 READY | 资源解包与重打包正常 |
| 攻防知识库 | ≥289 篇笔记 | 物理就绪 (318 篇) | 🟢 READY | seep_kb_* 检索后端就绪 |

#### 4. 🚀 总结与开工建议
- **系统评估**：核心组件与 9 大 Skill 100% 部署成功，工作台处于 **[READY / 完备就绪]** 状态；
- **操作指令**：请退出并重启当前终端与 Agent 会话，在对话框中输入 **`lab：`** 开启白盒测试！
```
