# CLAUDE.md — Claude Code 项目指令与自动化运维规约

> 当 Claude Code 在本工作区（Seep）被唤醒时，自动加载此文件作为项目最高执行协议。

---

## 一、 项目背景与定位

本工程为面向 AI Agent 的**多平台客户端逆向工程与授权流安全审计（CWE-602）工作台**。深度覆盖 Windows PE/DLL、Android APK/DEX/SO、Linux ELF。包含 9 大逆向 Skill、4 大核心 MCP 服务、289 篇实战知识库与 10 个脱敏工业架构范式。

---

## 二、 Agent 自动化部署与校验协议 (Deployment & Verification Protocol)

### 1. 部署执行规约
当用户下达类似 **“帮我部署当前工作台”**、**“安装 Seep 环境”**、**“按文档部署”** 的指令时，Agent 必须直接在终端执行：

```powershell
cd setup
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

### 2. 自动化校验与输出规范（★ 关键）
- **部署完成后，Agent 必须主动执行校验**，严禁在未做验证前直接向用户声称“部署完成”；
- **当用户在任何时候要求校验**（例如发送 `check`、`doctor`、`检查环境`、`帮我校验一下安装是否完整`）时，Agent 必须立即执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\check.ps1
```

- **汇报输出要求**：
  Agent 读取命令返回后，必须在对话框中向用户输出结构化 Markdown 体检卡片，包含以下 6 维度的明确反馈：
  1. **📁 核心架构**：`Tool/` 根目录与 9 大案例库是否完备；
  2. **🛠️ 技能系统**：`softseep`（总控）、`apkseep`、`ida-reverse` 等 9 个 Skill 是否已全部挂载；
  3. **🔌 MCP 服务**：`seep` MCP（22项工具）、`ida`、`playwright`、`js-reverse` 的注册状态与路径是否有效；
  4. **🧠 提示词与 Lab 状态机**：`SYSTEM.md` / `AGENTS.md` 及安全拦截扩展是否就绪；
  5. **🔧 内置工具箱**：Jadx (v1.5.6)、Radare2 (v6.2.2)、Apktool (v3.0.3) 二进制是否可用；
  6. **📚 战术知识库**：289 篇实战笔记与 3 个内置 MCP 源码组件是否可检索。

若全项通过，明确告知用户：**“工作台处于 [READY / 完备就绪] 状态，输入 lab： 即可开启测试。”**

---

## 三、 工作纪律与红线

1. **绝对禁止搬动 `Tool/mcp/Tool/` 目录**：seep MCP 内部硬编码了相对路径 `TOOL_DIR = <脚本目录>/Tool`，搬动将导致 22 个底层分析工具全部瘫痪。
2. **严禁修改 `seep_mcp_server.py` 的路径常量**。
3. **商业软件隔离**：IDA Pro 属于商业授权，不随包打包分发。检测不到时自动引导用户阅读 `MANUAL/IDA-PRO.md`，由 Radare2 自动降级承接。
4. **受权范围白盒审计（G-Auth）**：所有测试目标必须确认已获书面授权。
5. **凭据安全红线**：真实 Token/密钥/Salt/密码严禁外泄或记录于任何文档。

---

## 四、 目录树速览

```
Seep\
├── check.bat          ← 双击一键体检入口
├── check.ps1          ← 命令行一键体检入口
├── CLAUDE.md          ← 本文件（Claude Code 项目级指令）
├── .mcp.json          ← 项目级 MCP 注册文件
├── DSH-PROFILE.md     ← DeepSeek Harness 接入模板
│
├── Tool\
│   ├── skill\         9 个 Skill（以 softseep 为总控）
│   ├── mcp\           seep MCP（22 工具）+ Tool\ 运行时依赖
│   │   └── Tool\safe\ 内置 Jadx、Radare2、Apktool、Hook 引擎等
│   ├── prompts\       SYSTEM.md、AGENTS.md 与安全扩展
│   ├── cases\         10 个脱敏项目工程（项目 A ~ 项目 J）
│   ├── upstream\      apk-reverse 上游测试与验证集
│   ├── docs\          MCP-SETUP、DOWNLOADS、PROVENANCE 等
│   └── scripts\       任务沙盒初始化与签名工作流
├── setup\             安装与自检脚本集
└── MANUAL\            环境依赖与商业授权自备指引
```
