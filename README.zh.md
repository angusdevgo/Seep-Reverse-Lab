<p align="center">
  <img src="app_logo.svg" alt="Seep Reverse Lab Logo" width="128" height="128">
</p>

<h1 align="center">Seep Reverse Lab</h1>

<p align="center">
  <strong>面向 AI Agent 的多平台客户端逆向工程 · 授权流审计（CWE-602）· 自动化攻防工作台</strong>
</p>

<p align="center">
  <a href="https://github.com/angusdevgo/seep-reverse-lab"><img src="https://img.shields.io/badge/Release-v1.0.0-brightgreen.svg?style=for-the-badge&logo=github" alt="Release"></a>
  <a href="https://github.com/angusdevgo/seep-reverse-lab/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-blue.svg?style=for-the-badge" alt="License"></a>
  <img src="https://img.shields.io/badge/Platform-Windows%20%7C%20Android%20%7C%20Linux-0078D6?style=for-the-badge&logo=windows" alt="Platform">
  <img src="https://img.shields.io/badge/Architecture-x86%20%7C%20x64%20%7C%20ARM64-orange?style=for-the-badge" alt="Architecture">
  <img src="https://img.shields.io/badge/MCP%20Tools-22%20Integrated-purple?style=for-the-badge&logo=fastapi" alt="MCP Tools">
  <a href="https://linux.do/"><img src="https://img.shields.io/badge/Community-LINUX%20DO-23272A?style=for-the-badge&logo=discourse" alt="LINUX DO"></a>
</p>

<p align="center">
  [ <a href="README.md">English</a> | <strong>中文文档</strong> ]
</p>

<p align="center">
  <a href="#-项目定位与解决痛点">项目定位</a> •
  <a href="#-核心能力">核心能力</a> •
  <a href="#-目录架构体系">目录架构</a> •
  <a href="#-核心技术范畴">核心范畴</a> •
  <a href="#-mcp-工具矩阵">MCP 工具</a> •
  <a href="#-快速开始">快速开始</a> •
  <a href="#-智能体消费规范">消费规范</a> •
  <a href="#-致谢与社区">致谢社区</a> •
  <a href="#-免责声明">免责声明</a>
</p>

---

> 🔗 **致敬与参考源**：
> - 核心移动端逆向工程与验证规范参考自标杆开源项目：[**newliver666/apk-reverse**](https://github.com/newliver666/apk-reverse)（完整上游镜像与验证测试集内置于 [`Tool/upstream/apk-reverse/`](./Tool/upstream/apk-reverse/)）。
> - 社区支持与技术讨论：[**LINUX DO**](https://linux.do/)（真诚、友善、团结、专业的技术论坛）。

---

## 🌟 项目定位与解决痛点

它把分散的逆向工具链（Radare2 / JADX / Apktool / Frida / IDA）、战术知识库、提示词与实战经验，深度组装为一套 **AI Agent 能直接消费并自主驱动的自动化工作台（Agent-Native Workbench）** —— 用户仅需输入自然语言大白话，智能体即可自发展开平台识别、漏洞类型判型、微创打桩与证据链闭环交付。

### 核心解决的五大痛点：
- 🚀 **工具链高度碎片化**：传统逆向需要手动切换七八个离散工具，路径四散 —— 本工作台全量内置，通过标准化 MCP 统一调度。
- 🧠 **大模型缺乏决断逻辑**：面对混淆二进制或未知 APK，模型容易陷入盲目逆向 —— `softseep` 总控协议自发展开平台（Win/Android/Linux/Web）与业务类型（9 大类）自动判型，零摩擦分发。
- 🛡️ **云端模型误报防拒**：日常逆向与合规白盒审计易触发模型敏感词安全熔断 —— 内置底座级 `BLOCK_NONE` 注入、动态口语合规转译与推理级思维重定向三层保险。
- 📚 **实战经验无法沉淀**：多数逆向任务沦为一次性消耗 —— 内置 9 种脱敏工业架构范式（项目 A ~ I）与 289 篇系统化战术实战笔记，确立“先查知识库再动手”纪律。
- 📦 **环境部署摩擦高昂**：实习生或新机器配置繁琐 —— 提供全自动一键配置脚本，原生支持 **Pi Agent**、**Claude Code**、**DeepSeek Harness (DSH)** 及 **Codex / OpenCode**。

---

## ⚡ 本工作台的核心能力 (What it is good at)

- 🎯 **自然语言穿透与两级自动判型**：使用者无需记忆特定选单或参数，下达“分析这个程序特权验证”、“定位本地卡密校验”、“去广告”等日常指令，总控协议自主结合文件特征（魔数与导入表）与语义动词，瞬时收敛攻击路径。
- 🔍 **客户端鉴权脆弱性走查（CWE-602）**：在几分钟内定性受限特权是由本地布尔/时间戳驱动，还是由服务端强验签与远程资产下发决定。严密规避“强改本地标志位导致客户端向服务端索要数据失败从而发生白屏或静默崩溃”的经典伪 VIP 陷阱。
- 🛡️ **Authenticode 数字签名完备性保全**：对于具备官方签名的 Windows 核心进程，杜绝落地修改 EXE 文件，统一通过 DLL 搜索顺序劫持（代理 `version.dll`、`sentry.dll`）在内存加载期实施微创打桩，保全宿主二进制的合法数字签名。
- 💎 **九大工业级架构范式全覆盖**：覆盖从单进程纯离线内存打桩、多进程架构分流过滤、资源模板与 IAT Hook 显示层伪造、压缩壳处理与 ACL 注册表冻结，到 VM 集中判定重定向、.NET 算法还原离线 Keygen、自引用哈希破局、Ed25519 公钥密文替换及弱模 RSA 验签入口旁路。
- 🔌 **全量离线预置与零外网依赖**：底层工具集（Radare2、JADX、Apktool、Playwright 自动化引擎、IDA 桥接适配层等）均物理打包内置，解压即用，在完全隔离沙箱中稳定执行。

---

## 📋 目录架构体系 (Structure)

本工作台遵循严密的渐进式披露（Progressive Disclosure）与分层管理规范：

```
Seep\ (251 MB)
├── README.md                      ← 全局架构与工作台标准规范说明（本文件）
├── CLAUDE.md                      ← 面向 Claude Code 的项目级原生指令
├── .mcp.json                      ← 项目级标准 MCP 注册配置文件（供 Claude Code / OpenCode 读取）
├── DSH-PROFILE.md                 ← 面向 DeepSeek Harness 的 Cordis 插件配置模板
│
├── Tool\                          ← 工作台核心资产仓
│   ├── skill\                     ← 9 大逆向与白盒审计专业 Skill
│   │   ├── softseep\              ← ⭐ 核心总控 Skill（主控路由 + 8 大专题按需加载库）
│   │   ├── apkseep\               ← Android 移动端一体化逆向全链路专精 Skill（115 个工程文件）
│   │   ├── ida-reverse\           ← IDA Pro 自动化唤醒、无头探测与 MCP 深度分析协同
│   │   ├── client-license-validation-bypass\ ← 跨运行时通用许可/卡密校验战术手册
│   │   └── safe-skills\           ← 5 组独立战术包（通用逆向 / APK 差分 / Radare2 / JS 逆向 / IDA 辅助）
│   │
│   ├── mcp\                       ← 自动化工具服务层（MCP Engine）
│   │   ├── seep_mcp_server.py     ← seep 核心自研 MCP 服务端（承载 22 个底层分析与知识库工具）
│   │   ├── mcp.json.template      ← 全局 MCP 挂载配置标准模板
│   │   └── Tool\                  ← ⚠️ MCP 内部强约束底层工具运行时（严格保持相对路径）
│   │       ├── safe\              ← 已物理内置的跨平台逆向工具箱（JADX、Radare2、Apktool、Hook 引擎等）
│   │       │   ├── jadx\          ← 75 MB（v1.5.6 纯净优化版）
│   │       │   ├── radare2\       ← 39 MB（v6.2.2 全套二进制套件）
│   │       │   ├── apktool\       ← 24 MB（v3.0.3 原生环境）
│   │       │   ├── hook-mcp\      ← 331 KB（Frida/LSPosed 动态注入模板）
│   │       │   ├── ida-pro-mcp\   ← 28 MB（IDA 桥接适配依赖）
│   │       │   ├── js-reverse-mcp\← 61 MB（Web/JS 动态调试核心）
│   │       │   └── playwright-mcp\← 8.8 MB（无头浏览器控制台）
│   │       └── reverselab\        ← 攻防知识库核心（687 个架构文件，含 289 篇系统化战术实战笔记）
│   │
│   ├── prompts\                   ← 智能体协同规范与扩展注入层
│   │   ├── SYSTEM.md              ← Pi Agent 专用系统指令（包含 Lab 状态机、反退缩规则、SOP 约束）
│   │   ├── AGENTS.md              ← 跨 Agent（Codex、OpenCode 等）无状态通用指令规范
│   │   └── extensions\            ← 运行时底层拦截器（安全解封注入与口令自动转译）
│   │
│   ├── cases\                     ← 9 大经典实战脱敏架构工程库（项目 A ~ 项目 I）
│   │   ├── 项目A\ (单进程离线)     ├── 项目B\ (多进程协同)     ├── 项目C\ (资源模板与显示层伪造)
│   │   ├── 项目D\ (壳保护多策略)   ├── 项目E\ (VM 保护在线核验)├── 项目F\ (.NET 混淆可逆算法算号)
│   │   ├── 项目G\ (自引用校验补丁) ├── 项目H\ (公钥密文替换)   ├── 项目I\ (弱模 RSA 验签入口补丁)
│   │
│   ├── upstream\                  ← 上游溯源验证层（apk-reverse 开源验证集与离线回归测试套件）
│   ├── docs\                      ← 运维与工程标准文档库（MCP 验证、下载溯源、资产依赖总清单）
│   └── scripts\                   ← 工作空间管理与自动化辅助脚本集（建档、签名、IDA 启动挂载等）
│
├── setup\                         ← 自动化安装、依赖配置与环境健康自检脚本集
└── MANUAL\                        ← 基础设施依赖与商业环境自备说明（Python、Node、IDA Pro 授权等）
```

---

## 🔬 核心技术范畴 (Scope)

本工作台将常见的商业软件防御、虚拟机加固与授权体系抽象归纳为四大纵深战术域：

### 1. CTF 攻防竞赛与 Web/二进制靶标分析 (CTF & Challenge Workflows)
- **实战攻防网络路由（Attack-Network Routing）**：基于内置 `reverselab` 体系，以“信号检测 → 战术检索（`seep_kb_search`）→ 现成 PoC/模板装配 → MCP 工具执行”的确定性链条驱动。
- **Web 靶标与复杂协议研判**：覆盖 JWT 弱签及 KID 注入、SSRF 链路穿透、SSTI 模板注入、原型链污染、反序列化 Gadget Chain 匹配及无 Schema 约束的 Protobuf 逆向解析。
- **竞赛自动化提效支撑**：提供标准化的漏洞测试种子库（`seep_kb_payloads`）与应急排查清单（`seep_kb_checklist`），杜绝临场手写脆弱性探测脚本。

### 2. 客户端决策与授权体系审计（CWE-602）
- **权威归属定性模型**：通过断网隔离、回环重定向（`netsh` 回环抢占）、时间戳伪造等动态手段，快速判定受限功能是由本地布尔值驱动还是由服务端强校验闭环。
- **九大典型架构范式闭环**：
  - **项目 A 型（单进程单点布尔）**：标量函数出口修正（如 `mov eax, 1; ret`）。
  - **项目 B 型（多进程复杂拓扑）**：前台渲染层、守护服务与虚拟机 IPC 通信的跨进程分流过滤与三层状态护航。
  - **项目 C 型（资源模板与显示层重构）**：双射掩码混淆解析；针对自研皮肤引擎下沉至 `SetDlgItemTextW` 的 IAT Hook 显示层文案伪造。
  - **项目 D 型（压缩壳与混合激活）**：MPRESS 壳分析、18 点微创二进制修补、签名数据目录截断剥离与 Windows ACL 注册表试用期冻结。
  - **项目 E 型（代码虚拟化与集中裁决）**：面对不可直接还原的 EXECryptor VM 验签过程，利用判定函数高复用特征，实施 2 点 Call 指令重定向至内存 Stub。
  - **项目 F 型（托管混淆与纯算号路径）**：针对 .NET 动态方法体剥离实施 Harmony 内存转储，还原 96 位组合哈希算法，构造离线合规 Keygen。
  - **项目 G 型（自引用校验处理）**：识别载荷对自身 SHA-384 哈希校验的死结特征，转向入口点 5 字节微创修补并部署登录项守护。
  - **项目 H 型（非对称公钥密文替换）**：利用 Ed25519 内嵌公钥密文流的单向推导漏洞，在二进制内部以相同密码流重写自持公钥，签发自定义载荷。
  - **项目 I 型（高阶数字签名入口旁路）**：分析 CNG 结构与弱模数 RSA 滑动窗口特征，直接对导出接口施加激活态注入。

### 3. Android 移动安全与全链路逆向 (Android & DEX/SO Deep Analysis)
- **DEX 层微创手术与字节级修补**：提供等长字节修补机制（规避重排校验与方法膨胀）、Dex 头部校验和/SHA-1 签名逆向重算规则，对抗 R8 深度优化代码混淆。
- **加壳防护与抽取壳深度辨析**：建立 Java2C（编译下沉至 SO）、原生落地壳、抽取壳（Trivial-body ratio 判定）与私有 Dex-VMP 差分分析的明确诊断树，杜绝盲目倾倒空壳 DEX。
- **运行时环境自检与对抗绕过**：涵盖设备 Root 检测规避、多层 SSL Pinning 证书绑定剥离、基于 Frida 的 Native 动态插桩与基于 Frida-RPC 的跨进程服务化调用。
- **构建与签名工程完备性**：封装自动化重打包流水线，原生处理 `resources.arsc` 的 STORED 状态与 4 字节边界对齐（Zipalign），实施 v1+v2+v3 完整数字证书重签名。

### 4. 二进制反编译、动态分析与 Native 逆向 (PE/ELF/Mach-O Native RE)
- **多平台底层静态解剖**：基于内置 Radare2 执行无头模式的架构探测、节区熵分析、符号提取、反汇编与类 C 伪代码生成；挂载 IDA Pro MCP 服务，全自动反编译函数、重命名局部符号、恢复复杂结构体与交叉引用追踪。
- **底层防御机制识别与规避**：深入研判进程自杀式故意崩溃（如特意触发 `fault addr 0x4` 等空指针陷阱以伪装缺陷）、线程守卫注入、系统调用（Raw `svc`）直接调用以及内核级驱动对抗，给出“以返回正常状态代替强制挂起死循环”的防进程锁死规范。

---

## 🛠️ MCP 工具矩阵 (Tools & MCP Matrix)

工作台底层挂载的自研 `seep` MCP 服务直接暴露出 **22 项** 专用分析工具，由智能体在分析过程中依据战术需要自主调用：

| 分类 | 工具标识 | 核心功能 |
|---|---|---|
| **状态检测** | `seep_status` | 快速核对底层 Radare2、JADX、Apktool 及知识库的就绪状态 |
| | `seep_ida_status` | 探测 IDA Pro 远程 MCP 服务的连通性 |
| **二进制分析 (R2)** | `seep_r2_info` | 读取目标文件架构、位宽、大小端以及安全缓解机制（DEP/ASLR/Canary/PIE） |
| | `seep_r2_strings` | 提取可读字符串并支持基于关键词的正则过滤 |
| | `seep_r2_functions` | 枚举二进制内部函数拓扑、导入导出表及入口点 |
| | `seep_r2_disasm` | 输出指定函数或虚拟地址的高精度反汇编文本与交叉引用标记 |
| | `seep_r2_decompile` | 调用反编译引擎直接输出类 C 伪代码 |
| | `seep_r2_diff` | 对两个二进制样本实施代码级或十六进制差异比对 |
| | `seep_r2_asm` | 汇编单条指令为机器码或将 Hex 反解析为汇编语法 |
| | `seep_r2_cmd` | 执行底层 radare2 管道命令 |
| **Android 逆向** | `seep_apk_info` | 免安装快速解析 APK 的清单文件、组件声明、签名与架构 |
| | `seep_apk_decompile` | 调度内置 JADX 引擎输出反混淆后的 Java 源码工程 |
| | `seep_apk_unpack` | 调度 Apktool 解析明文资源与 Smali 汇编树 |
| | `seep_apk_smali_search`| 在 Smali 代码树中极速搜索密钥、API 路由或安全门禁位点 |
| | `seep_apk_gen_hook` | 根据类与方法签名自动生成开箱即用的 Frida 运行时拦截脚本 |
| **知识库检索** | `seep_kb_search` | 在 289 篇战术实战笔记中进行全文检索，输出最佳匹配的攻击面与代码片段 |
| | `seep_kb_read` | 精确读取特定技术主题手册全文 |
| | `seep_kb_checklist` | 输出专项安全排查核对清单与战术矩阵 |
| | `seep_kb_payloads` | 提取针对特定常见漏洞与认证协议的高危安全测试载荷模板 |
| **流水线编排** | `seep_task_init` | 在隔离工作区内一键初始化标准化白盒审计沙盒任务档案 |
| | `seep_auto_triage` | 对未知二进制样本执行全量快速体检 |
| | `seep_gen_security_report`| 自动归纳当前任务目录的逆向成果并输出三段式合规交付报告 |

---

## 🚀 快速开始与部署规范 (Quick Start & Deployment)

### 1. 运行依赖要求 (Prerequisites)
- **操作系统**：Windows 10 / 11 x64（推荐主环境）或兼容 Linux / macOS。
- **核心运行时**：Python 3.11+、Node.js 18+、Git。

### 2. 一键自动化部署 (One-Click Setup)
在终端中进入项目根目录下的 `setup/` 目录执行一键初始化脚本：
```powershell
cd setup
powershell -ExecutionPolicy Bypass -File .\install.ps1
```
> **该脚本全自动执行**：解压内置压缩依赖（`node_modules.zip` / `venv.zip`）→ 校验内置 Jadx/R2 工具完整性 → 安装 Python `mcp` 协议依赖 → 注册 MCP 服务至智能体客户端 → 执行环境健康自检。

### 3. 多智能体环境接入方式

| 智能体平台 | 核心指令来源 | MCP 服务挂载点 | 接入说明 |
|---|---|---|---|
| **Pi Agent** | `Tool/prompts/SYSTEM.md` | `~/.pi/agent/mcp.json` | 运行 `install.ps1` 自动完成用户级配置写入与技能注册 |
| **Claude Code** | 项目根 `CLAUDE.md` | 项目根 `.mcp.json` | 在工作台根目录直接执行 `claude` 命令，自动读取项目级上下文 |
| **DeepSeek Harness (DSH)** | `Tool/prompts/AGENTS.md` | `DSH-PROFILE.md` (Cordis YAML) | 将通用指令部署至工作目录，将 MCP 插件配置写入 DSH Profile |
| **OpenCode / Codex** | 项目根 `AGENTS.md` | 客户端全局配置 | 复制 `AGENTS.md` 至当前项目工作根目录即可 |

---

## 🎮 操作工作流与交互规范 (Workflow & Lab Mode)

### 1. 实验工作环境打卡 (Lab Mode Protocol)
为了在日常自由对话与严格的逆向白盒测试之间建立清晰边界，工作台设计了不依赖模型长文本记忆的磁盘状态切换机制：
- **进入测试工作环境**：向智能体发送：
  ```
  lab：
  ```
  *(或一步到位：`lab：分析目标样本 X.exe`)*  
  智能体将在本地磁盘生成状态标记文件，随后全量启用逆向技术映射、思维重定向与防拒绝策略。在后续工作中，**无需重复携带任何前缀**。
- **退出测试工作环境**：发送 `退出实验`，智能体即刻卸载状态标记，恢复日常常规对话。

### 2. 常用任务口令 (Task Shortcuts)
在实验环境开启状态下，可直接通过标准化前置口令触发全套审计流水线：
- `poc <目标>`：快速展开客户端特权决策脆弱性（CWE-602）排查并生成验证代码。
- `find-auth <目标>`：全局检索本地授权、许可证、到期时间、机器码相关函数与判定分支。
- `hook <函数/方法>`：针对指定符号自动生成带堆栈打印与返回值拦截的 Frida 验证脚本。
- `gen-patch <位点>`：输出指定 RVA 或文件偏移的二进制内存补丁代码或代理 DLL 框架。
- `triage <样本>`：执行包括架构、导入表、加壳形态与关键字符串在内的快速体检。
- `report`：一键扫描当前分析目录留存的全部技术证据，自动导出符合行业交付规格的三段式安全审计报告。

---

## 🤖 智能体消费规范 (How an agent is expected to consume this)

本仓库的指令集与核心入口文件并非供人类漫读的参考文档，而是针对大模型“容易陷入幻觉、偏离授权目标或在长推理链条中发生退缩”这一常见缺陷设计的**程序化执行门禁（Procedures with Gates）**。

- **强制门禁（G-Auth & G0–G6）**：任何任务开展前，第一行为永远是判定目标是否属于受权白盒测试资产；随后通过“四问”确定鉴权权威（服务端 vs 客户端本地）与交付形态（补丁 / 内存劫持 / 算号 / 协议中继 / 载荷提取）。任何一步通不过则立即终止或重定向，严禁凭第一性原理盲目逆向。
- **两击失败熔断纪律（Two-Strike Rule）**：同一假设、同一种内存补丁或逆向利用路径若连续失败两次，立即视为当前技术模型错误，强制回退至上一级判型，严禁进行第三次同构盲试。
- **先查知识库再动手（Zero-Waste Recon）**：发现特征信号（如特定加壳混淆、JWT、加密通信、驱动对抗、自引用校验）时，禁止从零手写分析脚本，必须优先通过 `seep_kb_search` 索引成熟战术库并直接映射 MCP 工具调用。
- **完工严格定义（Definition of Done）**：仅有控制台日志无错误绝不等于任务完成。“完成”必须满足端到端证据链闭环：从原始目标指纹、判定点 RVA 逆向还原、补丁或验证 PoC 实施、断网离线实测（确证无云端依赖）到结构化三段式报告交付，缺一不可。

---

## 📝 交付与报告标准 (Deliverable Specification)

任何针对客户端脆弱性的研判与审计，最终产物统一固化为咨询级安全报告架构，杜绝模糊推测：

1. **脆弱性原理与业务危害 (Vulnerability Detail & Risk)**：
   - 准确定位问题指令所处的 RVA / 文件偏移与调用链上下文。
   - 深入阐述客户端判定与业务剥离的根因，明确关联 CWE-602 等行业安全分类与威胁等级。
2. **复现路径与可验证工程 (Reproduction & PoC)**：
   - 提供 100% 可在本地沙盒复算的指令证据、代理 DLL 源代码工程或 Frida 动态注入脚本。
   - 提供严格的断网测试验证结论（证明相关特权或决策分支脱离服务端验证依然能够在离线状态下强行生效）。
3. **纵深防御修复方案 (Defense-in-Depth Remediation)**：
   - **加载期**：收敛动态链接库搜索路径（`SetDefaultDllDirectories`）杜绝环境劫持。
   - **运行期**：启用进程级动态代码策略（`ProcessDynamicCodePolicy`）封锁非法内存属性改写。
   - **逻辑层**：确立“服务端权威”原则，关键受限资源以服务端动态签名与短期令牌为唯一授权凭据。

---

## 🤝 致谢与社区 (Acknowledgements & Community)

- 特别致谢开源项目 [**newliver666/apk-reverse**](https://github.com/newliver666/apk-reverse) 提供的卓越 Android 逆向门控范式与工具验证体系。
- 感谢 [**LINUX DO**](https://linux.do/) 社区提供的高质量技术交流与探索氛围。

---

## ⚖️ 免责声明 (Disclaimer)

**本工作台及其所载之一切文档、规则、脚本与工程范例仅供合法授权的安全研究、白盒安全走查、合规漏洞测试及 CTF 教学演练使用。**

- **严格授权约束**：使用者在针对任何具体软件、客户端或系统展开分析前，必须自行确保已取得资产所有者完备、合法的书面测试授权。
- **无附带保证**：本工作台提供的所有技术方案与分析结论均基于特定沙盒环境与软件版本的实测结果按“现状”提供，不构成对任何特定商业软件或生产环境的适用性保证。
- **最小侵入原则**：针对二进制目标的测试工作应优先在隔离虚拟机或独立副本中开展，严禁在生产系统或未经许可的网络中实施未受控的逆向测试与补丁注入。
- **免责条款**：工作台作者与贡献者不对任何因不当使用、超出授权范围操作或违反属地法律法规所导致的任何直接或间接后果承担法律责任。
