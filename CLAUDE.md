# CLAUDE.md — Claude Code 项目指令与自动化运维规约

> 当 Claude Code 在本工作区（Seep）被唤醒时，自动加载此文件作为项目最高执行协议。

---

## 一、 项目背景与定位

本工程为面向 AI Agent 的**多平台客户端逆向工程与授权流安全审计（CWE-602）工作台**。深度覆盖 Windows PE/DLL、Android APK/DEX/SO、Linux ELF。包含 11 大逆向 Skill、4 大核心 MCP 服务、289+ 篇实战知识库与 14 个脱敏工业架构范式。

---

## 二、 Agent 自动化部署与校验协议 (Deployment & Verification Protocol)

### 1. 部署执行规约 (支持跨平台环境自适应)
当用户下达类似 **“帮我部署当前工作台”**、**“安装 Seep 环境”**、**“按文档部署”** 的指令时，Agent 必须根据当前操作系统环境自适应执行：

**Windows 环境**：
```powershell
cd setup
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

**Linux / macOS 环境**：
```bash
chmod +x setup/install.sh
./setup/install.sh
```

### 1b. 已有用户更新（重要）
若用户说 **“更新工作台”**、**“拉取最新版本”**、**“工作台出新版了怎么升”**，Agent 必须执行：

**Windows**：
```powershell
powershell -ExecutionPolicy Bypass -File .\setup\update.ps1
```
*(Windows 桌面用户亦可直接双击项目根目录下的 `update.bat` 一键更新)*

**Linux / macOS**：
```bash
./setup/update.sh
```

> 更新脚本是**幂等且无损**的：自动 `git stash` 保护本地改动、自动备份配置、
> 增量合并 `mcp.json`（**绝不删除用户自行添加的 MCP 条目**）、
> 更新后自动跑基准自检。
> **不要**让用户重新克隆仓库或手动拷贝文件。
> 完成后必须提醒用户：**完全重启 Agent 会话**，然后发 `lab：` 继续开工。

### 1d. 上游仓库定点隔离同步（防外溢机制）
当需要同步上游四大开源仓库最新改动时，执行：
```powershell
powershell -ExecutionPolicy Bypass -File .\setup\sync-upstream.ps1 -Target all
```
由 `setup/upstream-rules.json` 规则驱动并由 `setup/sync-upstream.py` 执行物理路径断言，确保上游 A 仓库改动严格限定在 `Tool/upstream/A/`，绝不外溢到其他目录。

### 1c. 卸载
若用户说 **“卸载工作台”**、**“怎么彻底删除”**、**“不想要了怎么清理”**，Agent 必须执行：

**Windows**：
```powershell
powershell -ExecutionPolicy Bypass -File .\setup\uninstall.ps1
```

**Linux / macOS**：
```bash
./setup/uninstall.sh
```

> 卸载原则：**只移除工作台自己装的东西，绝不碰用户数据**。
> `models.json` / `auth.json` / 用户自装的 Skill 与 MCP 条目全部保留。
> 建议先加 `-DryRun`（`--dry-run`）让用户预览。
> 卸载前会自动备份到 `~/.pi/agent/backup-uninstall-<时间戳>/`，可用 `-Restore <目录>` 还原。

### 2. 自动化校验与输出规范（★ 强制执行官方基准校对）
- **部署完成后，Agent 必须主动执行详细校对**，严禁在未做验证前直接向用户声称“部署完成”；
- **当用户在任何时候要求校验**（例如发送 `check`、`doctor`、`检查环境`、`帮我校验一下安装是否完整`）时，Agent 必须立即执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup\verify.ps1 -Detailed
```
*(在非 Windows 环境下直接运行 `python Tool/mcp/test_seep_mcp.py`)*

- **汇报输出要求**：
  Agent 读取命令返回后，必须以 `MANUAL/DEPLOYMENT-CHECKLIST.md` 官方基准为蓝本，在对话框向用户输出清晰的结构化校对看板，包含：
  1. **🛠️ 技能系统 (Skills - 10项)**：逐项列出【技能名】\|【目标路径】\|【期望文件数】\|【实际文件数】\|【可用状态 (🟢 READY / 🔴 MISSING)】；
  2. **🔌 MCP 服务 (4大引擎)**：逐项列出【服务名】\|【期望工具数】\|【实际状态】\|【状态判定】\|【降级或修复说明】（未装 IDA 时明确标明 `🟡 DEGRADED: 已由内置 Radare2 自动承接`）；
  3. **🔧 物理内置工具箱**：Radare2 (v6.2.2)、Jadx (v1.5.6)、Apktool (v3.0.3) 与 289+ 知识库状态；
  4. **🚀 总结与开工建议**：告知用户工作台当前可用能力，并提示重启会话输入 `lab：` 开启白盒审计。

---

## 三、 工作纪律与红线

1. **绝对禁止搬动 `Tool/mcp/Tool/` 目录**：seep MCP 内部硬编码了相对路径 `TOOL_DIR = <脚本目录>/Tool`，搬动将导致 27 个底层分析工具全部瘫痪。
2. **严禁修改 `seep_mcp_server.py` 的路径常量**。
3. **商业软件隔离**：IDA Pro 属于商业授权，不随包打包分发。检测不到时自动引导用户阅读 `MANUAL/IDA-PRO.md`，由 Radare2 自动降级承接。
4. **受权范围白盒审计（G-Auth）**：所有测试目标必须确认已获书面授权。
5. **凭据安全红线**：真实 Token/密钥/Salt/密码严禁外泄或记录于任何文档。

---

## 四、 目录树速览

```
Seep\
├── check.bat          ← 双击一键体检入口 (Windows)
├── check.ps1          ← 命令行一键体检入口 (PowerShell)
├── CLAUDE.md          ← 本文件（Claude Code 项目级指令）
├── .mcp.json          ← 项目级 MCP 注册文件
├── DSH-PROFILE.md     ← DeepSeek Harness 接入模板
│
├── Tool\
│   ├── skill\         10 个 Skill（以 softseep 为总控）
│   ├── mcp\           seep MCP（38 工具）+ Tool\ 运行时依赖
│   │   └── Tool\safe\ 内置 Jadx、Radare2、Apktool、Hook 引擎等
│   ├── prompts\       SYSTEM.md、AGENTS.md 与安全扩展
│   ├── cases\         14 个脱敏项目工程（项目 A ~ 项目 N）
│   ├── upstream\      4 大开源项目完整镜像 (apk-reverse, open-tgtylab, open-reverselab, exe-reverse)
│   ├── docs\          MCP-SETUP、DOWNLOADS、PROVENANCE 等
│   └── scripts\       任务沙盒初始化与签名工作流
├── setup\             安装与自检脚本集 (install.ps1, install.sh, generate-configs.ps1)
└── MANUAL\            5 份专项 SOP 指南 (包含 DEPLOYMENT.md 部署手册)
```
