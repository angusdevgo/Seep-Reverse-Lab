> **第一次来？先看 [INSTALL.md](INSTALL.md)** —— 讲清楚 Pi Agent 和 DeepSeek Harness 各装什么、怎么装，选错会白忙。

<p align="center">
  <img src="app_logo.svg" alt="Seep Reverse Lab Logo" width="120" height="120">
</p>

<h1 align="center">Seep Reverse Lab</h1>

<p align="center">
  <strong>面向 AI Agent 的多平台客户端逆向工程 · 授权流审计（CWE-602）· 自动化安全工作台</strong>
</p>

<p align="center">
  <a href="https://github.com/angusdevgo/seep-reverse-lab"><img src="https://img.shields.io/badge/Release-v1.13.0-brightgreen.svg?style=for-the-badge&logo=github" alt="Release"></a>
  <a href="https://github.com/angusdevgo/seep-reverse-lab/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-GPL--3.0-blue.svg?style=for-the-badge" alt="License"></a>
  <img src="https://img.shields.io/badge/Platform-Windows%20%7C%20Android%20%7C%20Linux-0078D6?style=for-the-badge&logo=windows" alt="Platform">
  <img src="https://img.shields.io/badge/Architecture-x86%20%7C%20x64%20%7C%20ARM64-orange?style=for-the-badge" alt="Architecture">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/MCP%20工具-23%20已集成-purple?style=for-the-badge&logo=fastapi" alt="MCP Tools">
  <img src="https://img.shields.io/badge/健康体检-52%2F52%20全绿通过-brightgreen?style=for-the-badge&logo=checkmarx" alt="Verifier">
  <img src="https://img.shields.io/badge/实战知识库-289%20篇战术笔记-teal?style=for-the-badge" alt="Knowledge Base">
  <img src="https://img.shields.io/badge/脱敏范式-14%20大案例%20(A~N)-blue?style=for-the-badge" alt="Paradigms">
  <img src="https://img.shields.io/badge/MANUAL%20SOP-9%20份专项手册-red?style=for-the-badge" alt="MANUAL SOPs">
  <a href="https://linux.do/"><img src="https://img.shields.io/badge/社区-LINUX%20DO-23272A?style=for-the-badge&logo=discourse" alt="LINUX DO"></a>
</p>

<p align="center">
  [ <a href="README.md">English</a> | <strong>中文文档</strong> ]
</p>

<p align="center">
  <a href="#-项目定位">项目定位</a> •
  <a href="#️-运转原理">运转原理</a> •
  <a href="#-30-秒感受一下">30 秒 Demo</a> •
  <a href="#-mcp-工具矩阵">MCP 工具</a> •
  <a href="#-快速开始与部署">快速开始</a> •
  <a href="#-核心技术范畴">技术范畴</a> •
  <a href="#-智能体消费规范">消费规范</a> •
  <a href="#-免责声明">免责声明</a>
</p>

---

> 🔗 **致敬与开源参考源**：
> - 移动端逆向工程与门禁验证套件源自：[**newliver666/apk-reverse**](https://github.com/newliver666/apk-reverse)（MIT License）。
> - 安全实验室架构与 Zero-Waste Recon 攻防提效体系： [**GeniusHu-tgty/Open-tgtylab**](https://github.com/GeniusHu-tgty/Open-tgtylab)（GPL-3.0 License）
> - 攻击网拓扑与 MCP 自动化工具生态：[**LING71671/open-reverselab**](https://github.com/LING71671/open-reverselab)（GPL-3.0 License）
> - 社区支持与技术讨论：[**LINUX DO**](https://linux.do/)。

---

## 🌟 项目定位

把分散的逆向工具链（Radare2 / JADX / Apktool / Frida / IDA）、战术知识库、提示词工程与实战经验深度组装为一套 **AI Agent 能直接消费并自主驱动的自动化工作台** —— 用户仅需输入自然语言，智能体即可自发展开平台识别、漏洞判型、微创打桩与证据链闭环交付。

### 核心解决的五大痛点

| 痛点 | 解决方案 |
|---|---|
| 🔧 **工具链高度碎片化** | 38 个 MCP 工具封装 Radare2/JADX/Apktool/Frida/PE 引擎，统一调度，零手动切换 |
| 🧠 **大模型缺乏决断逻辑** | `softseep` 总控：两级自动判型（平台 × 9 类业务）+ 七道门决策树 |
| 🛡️ **云端模型频繁拒绝** | 三层保险：底座级 `BLOCK_NONE` 注入 + 动态口语合规转译 + 推理级思维重定向 |
| 📚 **实战经验无法沉淀** | 294 篇战术实战笔记 + 14 大脱敏工业范式 + "先查知识库再动手"强制纪律 |
| 📦 **环境部署摩擦高昂** | 一键 `install.ps1`，两个 Agent 各自一条路：Pi Agent / DeepSeek Harness |

---

## ⚙️ 运转原理

```
用户输入一句大白话（"帮我分析 FooBar.apk 的会员验证"）
    │
    ▼
┌──────────────────────────────────────────────────────────────────┐
│  Lab Mode  (会话级内存；只在本窗口输入 lab：才生效)              │
│  • 口语 → 合规术语自动转译（"破解" → CWE-602 旁路验证）           │
│  • BLOCK_NONE 注入 + 推理级防拒绝认知重定向                       │
│  • 状态持久化：切换模型/压缩上下文后依然生效                       │
└──────────────────────────┬───────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────────────┐
│  softseep  总控调度器                                            │
│  ① 平台判型 → Windows PE / Android APK / Linux ELF / Web        │
│  ② 业务判型 → 9 大范式 × 七道门（G0–G6 决策树）                  │
│  ③ 路由分发 → exe-reverse / apkseep / ida-reverse / seep MCP / 知识库 │
└─────────┬────────────────┬──────────────────┬─────────────────────┘
          │                │                  │
          ▼                ▼                  ▼
    seep MCP          IDA Pro MCP         知识库检索
    38 个工具          (可选联动)          294 篇战术笔记
    (R2/JADX/                             (Zero-Waste Recon)
     Apktool/Frida)
          │
          ▼
┌──────────────────────────────────────────────────────────────────┐
│  上下文预算控制 Context Budget Control（v1.1 降噪）               │
│  • seep_r2_decompile: full / fold（省 60% Token）/ summary（省 90%）│
│  • seep_r2_disasm:   full / branch（仅控制流骨架）               │
│  • seep_r2_xrefs:    分页返回，默认 limit=10，附总数统计摘要       │
└──────────────────────────┬───────────────────────────────────────┘
                           │
                           ▼
       PoC 生成 → 沙箱执行 → Frida 报错自愈循环（最多 3 次）
                           │
                           ▼
       断网铁证确认（CWE-602 唯一可信证据）
                           │
                           ▼
       三段式咨询级安全报告  ✓
```

---

## ⚡ 30 秒感受一下

<p align="center">
  <img src="docs/images/agent-workflow.png" alt="Seep 智能体全自动逆向与决策链路实录" width="880">
</p>

部署完成后，直接在 Agent 对话框发一句大白话：

```
lab：分析 FooBar.apk，找到会员验证并绕过
```

Agent 自主完成：

1. **`seep_auto_triage`** → 识别 DEX + ARM64 SO，未检测到壳
2. **`seep_apk_decompile`** with `output_mode=fold` → 仅提取控制流骨架 *(省约 60% Token)*
3. **`seep_kb_search`** → 命中知识库战术笔记 #142，CWE-602 匹配模式
4. **`seep_apk_gen_hook`** → 自动生成 `hook_verify.js` Frida 探针脚本
5. 注入测试机 → 捕获 stdout → **自愈** `ClassNotFoundException` → 自动修正类路径重跑
6. 飞行模式断网确认 ✓ → **`seep_gen_security_report`** → 三段式审计报告交付

> 典型客户端应用全程耗时：**8–20 分钟，完全无人值守**。

---

## ⚡ 核心能力

- 🎯 **自然语言穿透与两级自动判型**：无需记忆命令或参数，大白话直接驱动，文件魔数 + 语义动词自动收敛攻击路径
- 🔍 **客户端鉴权脆弱性走查（CWE-602）**：分钟级判定受限功能是本地布尔还是服务端权威，规避"伪 VIP 白屏"经典陷阱
- 🛡️ **Authenticode 数字签名保全**：对具备数字签名的 Windows PE，通过代理 DLL（`version.dll`）劫持在内存打桩，宿主签名完好
- 🔄 **PoC 自愈循环**：Frida 报错 → 根因映射 → 自动修正代码 → 重跑（最多 3 次，超限后结构化移交人工）
- 💎 **14 大工业级脱敏范式**：单进程离线 → 多进程 IPC → VM 集中判定 → .NET 算号 → 弱模 RSA 旁路 → Java 动态插桩 → .NET VM 逆向，全覆盖（项目 A ~ 项目 N）
- 🌐 **链路层合规转译中继与自动重试**：纯标准库实现的本地中继，支持流式拒答自动重试级联（`S1 评审清单` → `S2 架构走查` → `S3 英文重塑`），100% 保留目标参数不漂移，84 项单元测试全绿
- ⚡ **DeepSeek Harness (DSH) 接入**：`python setup/dsh-plugin-setup.py` 装一个几十 KB 的插件包并写入工作台路径 —— MCP（`toolCallTimeoutMs` 900 秒，DSH 默认 60 秒会掐断长任务）与 10 个技能由插件在运行时自己挂，仓库搬家只改这一处；`lab：` 闸门也升级为**插件内代码实现**（会话级、默认关、聊到 APK 不算激活）；另带**设置面板**（设置 → Seep 工作台），能看运行状态、直接改路径、列 20 个工具的四态清单。校验：`python setup/verify-dsh.py`（6 组 24 项 100 分）
- 🛡️ **实测抗拒答综合防线**：Gemini-Safe 提示词语义重塑（`gemini-safe.flag`，377 token 拒答 → 3300 字深度分析）、L1 拦截器动态可观测日志（`l1-log.flag`）、底座级 `BLOCK_NONE` 注入
- 🔌 **离线预置全量内置**：所有工具链物理打包（251 MB），部署后零外网依赖
- 🪟 **Windows PE 深水区引擎（`exe-reverse`）**：41 篇带门禁的参考文档 + **16 个零依赖 Python 引擎** —— `peutil`（RVA↔偏移、导入导出/TLS/重定位、微软校验和、逐节熵）、`pe_triage`、`pepatch`（等长补丁 + 校验和重算 + **写盘后逐字节回读**）、`aob_scan`（unique/ambiguous/pervasive 裁决）、`pe_diff`、`hwprobe`、`trace_reduce`（可选 SMT 证明）、`fold`。覆盖保护壳、虚拟化/控制流平坦化、.NET、Unity IL2CPP、打包 Python、内核驱动、硬件追踪与 Hypervisor 观测

---

## 📋 目录架构体系

<details>
<summary>📁 完整目录树（点击展开）</summary>

```
Seep\ (251 MB)
├── README.md                      ← 全局说明（英文默认）
├── README.zh.md                   ← 本文件（中文文档）
├── DSH-PROFILE.md                 ← DeepSeek Harness 接入：字段表 / 挂载方式 / 校验
├── check.bat                      ← ⭐ 双击一键体检入口（Windows）
├── check.ps1                      ← PowerShell 体检入口
├── VERSION                        ← 当前版本标识
├── CHANGELOG.md                   ← 面向用户的版本变更日志
│
├── Tool\
│   ├── skill\                     ← 10 大逆向专业技能
│   │   ├── softseep\              ← ⭐ 总控调度器（路由 + 10 专题按需库）
│   │   ├── exe-reverse\           ← Windows PE 深水区（41 篇规范 + 16 个引擎）
│   │   ├── apkseep\               ← Android 全链路逆向（115 个工程文件）
│   │   ├── ida-reverse\           ← IDA Pro 自动化联动
│   │   ├── client-license-validation-bypass\ ← 跨运行时卡密/授权攻防手册
│   │   └── safe-skills\           ← 5 个独立战术工具包
│   │
│   ├── mcp\                       ← MCP 服务引擎
│   │   ├── seep_mcp_server.py     ← 核心服务端，38 个底层分析工具
│   │   └── Tool\                  ← ⚠️ 硬编码相对路径，禁止重命名/搬移
│   │       ├── safe\              ← 物理内置工具箱
│   │       │   ├── jadx\          ← 75 MB（v1.5.6）
│   │       │   ├── radare2\       ← 39 MB（v5.9.8 全套）
│   │       │   ├── apktool\       ← 24 MB（v2.11.0）
│   │       │   ├── hook-mcp\      ← Frida / LSPosed 动态注入模板
│   │       │   ├── ida-pro-mcp\   ← IDA 桥接适配层
│   │       │   ├── js-reverse-mcp\← Web / JS 调试引擎
│   │       │   └── playwright-mcp\← 无头浏览器自动化
│   │       └── reverselab\        ← 294 篇战术笔记 + 攻击链模板
│   │
│   ├── prompts\                   ← 智能体协同规范与运行时扩展
│   │   ├── SYSTEM.md              ← Pi Agent 系统指令
│   │   ├── AGENTS.md              ← 跨 Agent 通用指令规范
│   │   └── extensions\            ← BLOCK_NONE 注入 + 口语合规转译
│   │
│   ├── cases\                     ← 14 大脱敏工业案例库（项目 A ~ N，含版本演进归档 v2）
│   ├── upstream\                  ← 上游溯源验证层（4 大开源项目完整镜像）
│   │   ├── apk-reverse\           ← newliver666/apk-reverse（Android 逆向与离线测试集）
│   │   ├── open-tgtylab\          ← GeniusHu-tgty/Open-tgtylab（攻防流水线与提效路由）
│   │   ├── open-reverselab\       ← LING71671/open-reverselab（知识库、boards 与工具生态）
│   │   └── exe-reverse\           ← dabao1955/exe-reverse（Windows PE 深水区证据记录与回归套件）
│   ├── docs\                      ← 工程参考文档
│   └── scripts\                   ← 工作流自动化脚本
│       └── compliance-relay\      ← 🌐 链路层合规转译中继（纯标准库，三协议）
│
├── setup\                         ← 安装、修复、更新、卸载与校验脚本集
└── MANUAL\                        ← 9 份战术专项 SOP 手册
    ├── PREREQUISITES.md           ← 环境与依赖预要求指南
    ├── IDA-PRO.md                 ← IDA Pro 商业软件接入指南（支持 idalib 原生与传统 stdio 双模式）
    ├── ANTI-DEBUG.md              ← 反调试绕过字典与代理 DLL 框架
    ├── UNPACKING.md               ← UPX/MPRESS/Themida/VMP 脱壳 SOP
    ├── POC-VALIDATION.md          ← Frida 自愈循环与 PoC 沙箱验证
    ├── DEPLOYMENT.md              ← 全景部署与多 Agent 集成指南
    ├── DEPLOYMENT-CHECKLIST.md    ← 官方部署资产核验基准清单（51 项）
    ├── CROSS-PLATFORM.md          ← 跨平台（Windows/Linux/macOS）运行与战术等价指南
    ├── COMPLIANCE-RELAY.md        ← 链路层合规转译中继与防拒自动重试指南
    └── MODEL-REFUSAL-MATRIX.md    ← 实测大模型拒答矩阵与提示词重塑研究
```

</details>

---

## 🛠️ MCP 工具矩阵

自研 `seep` MCP 服务暴露 **38 个原生工具**，分八大功能组：

| 分类 | 工具 | 核心功能 | 上下文控制 |
|---|---|---|---|
| **状态检测** | `seep_status` | Radare2 / JADX / Apktool / KB 就绪检测 | — |
| | `seep_ida_status` | IDA Pro MCP 服务连通性探测 | — |
| **二进制分析** | `seep_r2_info` | 架构 / 位宽 / DEP / ASLR / Canary / PIE | — |
| | `seep_r2_strings` | 字符串提取 + 正则过滤 | `limit=` |
| | `seep_r2_functions` | 函数枚举 / 导入导出 / 入口点 | `limit=` |
| | `seep_r2_disasm` | 反汇编 + 交叉引用标注 | `full` / `branch` |
| | `seep_r2_decompile` | 类 C 伪代码（pdc 引擎） | `full` / `fold` / `summary` |
| | `seep_r2_xrefs` | 交叉引用图，分页返回 | `limit=10` 默认 |
| | `seep_r2_diff` | 两份二进制代码 / Hex 差分 | — |
| | `seep_r2_asm` | 汇编 ↔ 机器码互转 | — |
| | `seep_r2_cmd` | 底层 Radare2 管道命令 | — |
| **Windows PE** | `seep_pe_triage` | PE 一次过体检：节区/熵、导入表、PDB、CLR、校验和、保护信号 | — |
| | `seep_pe_aob_scan` | AOB 特征码定位 + `unique` / `ambiguous` / `pervasive` 裁决 | `limit=` |
| | `seep_pe_diff` | 跨版本差分（归一化易变头字段，差异映射回 RVA） | — |
| | `seep_pe_patch` | 可验证等长补丁：校验和重算 + 写盘后逐字节回读 | `dry_run=` |
| **Android 工具箱** | `seep_android_toolbox` | 外部 Frida / objection / APKiD / Aotopsy 工具箱就绪检查 | — |
| | `seep_apkid_scan` | APKiD 加固与对抗指纹识别（壳商、混淆器） | — |
| | `seep_aotopsy` | Flutter / Dart AOT（`libapp.so`）静态分析、Dart 符号还原 | `keyword=` |
| **Web / 流媒体** | `seep_web_pipeline` | 一键串联：授权门 → 指纹 → 举证 → 复测 → 报告 | `authorized=` |
| | `seep_web_gate` | Web 阶段门，前置产物缺失直接 BLOCK | — |
| | `seep_cms_fingerprint` | CMS 家族 / 采集接口 / 播放器链路 / 暴露面指纹 | `deep=` |
| | `seep_hls_analyze` | HLS 六类根因判定：防盗链 / 鉴权 / AES-128 / DRM / 源失效 | — |
| | `seep_http_replay` | 头变体矩阵重放，定位真正的门槛头 | — |
| | `seep_spider_extract` | TVBox / CatVod spider 三入口提取 | — |
| | `seep_web_report` | 生成 Web 源与暴露面安全评估报告 | — |
| | `seep_web_toolbox` | Web 工具箱就绪检查（ffmpeg / nuclei / ffuf） | — |
| **Android 逆向** | `seep_apk_info` | APK 清单 / 权限 / 签名（免 Java）| — |
| | `seep_apk_decompile` | JADX 全量 Java 源码反编译 | — |
| | `seep_apk_unpack` | Apktool 资源 + Smali 解包 | — |
| | `seep_apk_smali_search` | Smali 关键词/密钥/门禁位点检索 | `limit=` |
| | `seep_apk_gen_hook` | 自动生成带堆栈打印的 Frida 探针 | — |
| **知识库** | `seep_kb_search` | 294 篇战术笔记全文检索 | `limit=` |
| | `seep_kb_read` | 按主题精确读取完整技术手册 | — |
| | `seep_kb_checklist` | 应急排查清单与攻击矩阵 | — |
| | `seep_kb_payloads` | JWT / SSRF / SSTI / SQLi 载荷模板 | — |
| **流水线编排** | `seep_task_init` | 初始化隔离审计沙盒目录 | — |
| | `seep_auto_triage` | 未知样本全量自动体检 | — |
| | `seep_gen_security_report` | 三段式合规安全报告生成 | — |

> 💡 **PE 引擎护栏**：`seep_pe_patch` 拒绝原地覆盖、默认拒绝改变长度、`expect=` 与实际字节不符时直接中止。四个 PE 工具中只有 `seep_pe_patch` 会写盘，其余三个只读。
>
> 💡 **上下文预算控制（v1.1）**：`seep_r2_decompile` 使用 `output_mode=fold` 可减少约 60% Token 消耗；`summary` 模式减少约 90%。使用 `seep_r2_xrefs` 替代原始 `axt` 命令，避免数百条引用直接灌满上下文窗口。

---

## 🚀 快速开始与部署

### 1. 运行依赖
- **操作系统**：Windows 10 / 11 x64（推荐），兼容 Linux / macOS
- **核心运行时**：Python 3.11+、Node.js 18+、Git

### 2. 一键自动化部署 (跨平台支持)

**Windows 环境 (PowerShell)**:
```powershell
cd setup
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

**Linux / macOS 环境 (Bash)**:
```bash
chmod +x setup/install.sh
./setup/install.sh
```

> **脚本全自动完成**：解压内置依赖包 (`node_modules.zip`) → 校验内置工具完整性 →
> 安装 Python mcp 库 → 注册 MCP 服务（自动挑选真正装了 `mcp` 的解释器）→ 展开绝对物理路径 →
> 补齐外部能力包（默认只装零成本的 Aotopsy）→ 执行全量自检 + 能力看板。

**可选：补齐外部能力包**

38 个 MCP 工具里有几个依赖仓库外的程序。首次部署只自动装零成本件，其余按需一条命令补齐：

```powershell
powershell -File setup\install-capabilities.ps1 -Only all   # 全补：ffmpeg / frida / APKiD / nuclei / ffuf
powershell -File setup\install-capabilities.ps1 -CheckOnly  # 只看现状
```

**Linux / macOS**：

```bash
./setup/install-capabilities.sh --only all
```

> 缺件不会让 MCP 起不来：相关工具会返回明确的修复指引，`check.ps1` / `verify.sh` 以 🟡 DEGRADED 标出，不判失败。
> **平台边界**：`aotopsy`（Flutter AOT）为 Windows-only；8 个 `seep_web_*` 工具依赖 PowerShell 脚本，
> Unix 需先装 PowerShell 7。详见 [CROSS-PLATFORM.md](MANUAL/CROSS-PLATFORM.md)。
> 详见 [MANUAL/DEPLOYMENT.md — 外部能力包](MANUAL/DEPLOYMENT.md#5-外部能力包为什么需要单独一步)。

### 3. 多 Agent 接入方式

| 智能体平台 | 核心指令 | MCP 服务配置 | 详细接入步骤 |
|---|---|---|---|
> 四个 Agent 的接线点、lab 在哪、更新怎么做，逐项对照见 [MANUAL/AGENTS.md](MANUAL/AGENTS.md)。

| **Pi Agent** | `Tool/prompts/SYSTEM.md` | `~/.pi/agent/mcp.json` | 运行 `install.ps1` 自动写入，完成后**必须重启当前终端与 Pi 会话**。 |
| **DeepSeek Harness** | 项目根 `AGENTS.md`（自动生成） | `DSH-PROFILE.md` | `python setup/dsh-plugin-setup.py` 装插件包并写入路径（推荐）；旧路线 `dsh-merge.py` 保留兼容。校验：`python setup/verify-dsh.py`。 |

> 📖 **咨询级部署与全套排障手册**：关于四大 Agent 的具体配置细则、常见报错（`No module named mcp`、执行策略受限、Java环境缺省等）的解决方案，请详阅 [**MANUAL/DEPLOYMENT.md**](MANUAL/DEPLOYMENT.md)。

### 4. 已有用户如何更新

已经部署过？**不需要重新克隆或手动拷贝文件**。更新脚本是**幂等且无损**的 —— 你的模型凭据与自行添加的 MCP 条目永不会被覆盖。

- **最简方式（双击批处理）**：Windows 用户直接双击项目根目录下的 **`update.bat`** 即可全自动执行；
- **智能对话方式**：在支持的 Agent 会话中直接对 AI 发送 **“更新工作台”**，Agent 会原地自动调用更新脚本并向你汇报；
- **命令行方式**：
```powershell
# Windows
powershell -ExecutionPolicy Bypass -File .\setup\update.ps1

```
```bash
# Linux / macOS
./setup/update.sh
```

它会：自动 stash 本地改动 → `git pull` → 打印变更日志 → 备份配置 → 增量同步 Skill/提示词/MCP → 校验用户数据零丢失 → 跑全量健康体检。

| 参数 | 作用 |
|---|---|
| `-DryRun` / `--dry-run` | 只显示将要做什么，不修改任何文件 |
| `-Check` / `--check` | 仅检查远程是否有新版本发布，不执行拉取 |
| `-NoPull` / `--no-pull` | 跳过 `git pull`（适用于压缩包部署） |

> ⚠️ **更新后务必完全重启 Agent 会话**，新 Skill 与扩展才会加载。
> 各版本变更内容见 [CHANGELOG.md](CHANGELOG.md)。

### 4b. 上游仓库定点隔离同步（防外溢机制）

工作台整合了四个开源上游项目（`apk-reverse`、`open-tgtylab`、`open-reverselab`、`exe-reverse`）。为了解决上游作者在 GitHub 更新后手动合并繁琐且易污染其他模块的问题，工作台确立了**「单源单目录、零外溢」**的声明式同步机制：

- **声明式规则清单**：`setup/upstream-rules.json` 严格绑定每一个上游仓库的唯一目标目录与边界白名单；
- **物理防外溢断言**：`setup/sync-upstream.py` 纯标准库引擎在写入前执行 `realpath` 前缀物理路径断言，若 A 仓库的内容试图写到 B/C 目录或主工程，立即抛出 `SpilloverSecurityViolation` 异常并熔断拦截；
- **CI 独立隔离 PR**：云端配置 `.github/workflows/upstream-sync.yml` 定时巡检，发现 A 仓库更新时仅切出独立分支提 PR，Diff 严格限定在 A 目录内；
- **本地一键维护**：
  ```powershell
  powershell -ExecutionPolicy Bypass -File .\setup\sync-upstream.ps1 -Target apk-reverse
  ```

### 5. 如何卸载

只移除工作台自己装的东西 —— 你的模型凭据、会话记录、以及自行添加的 MCP 条目都不会被触碰。

```powershell
powershell -ExecutionPolicy Bypass -File ./setup/uninstall.ps1 -DryRun   # 先预览
powershell -ExecutionPolicy Bypass -File ./setup/uninstall.ps1          # 再执行
```
```bash
./setup/uninstall.sh --dry-run && ./setup/uninstall.sh
```

所有受影响文件会先整体备份到 `~/.pi/agent/backup-uninstall-<时间戳>/`，用 `-Restore <目录>` 可一键还原。详见 [MANUAL/DEPLOYMENT.md](MANUAL/DEPLOYMENT.md)。

### 6. 部署完备性校验（9 大维度 52 项全绿）

严格对照 `MANUAL/DEPLOYMENT-CHECKLIST.md` 官方基准核验：

| 方式 | 操作 |
|---|---|
| ⭐ 双击一键（最简单）| 双击项目根目录下的 `check.bat` |
| PowerShell | `powershell -ExecutionPolicy Bypass -File .\check.ps1` |
| Agent 对话框 | 发送 `check`（或 `检查` / `doctor`）— Agent 自动运行并内联输出报告 |

<p align="center">
  <img src="docs/images/verifier-check.png" alt="Seep 部署完备性体检全绿看板 (9 大维度 51 项全部通过)" width="880">
</p>

---

## 🎮 操作工作流与 Lab Mode

### Lab Mode 协议（会话级触发）
```
激活：  lab：                          # 或：lab：分析 FooBar.exe
退出：  退出实验
```
- **触发条件唯一**：不输入 `lab：` 就什么都不发生，新会话默认干净
- **隔离范围是会话**：状态存在扩展进程内存（`isLabSessionActive`），由 `session_start` 复位；
  其他终端窗口完全不受影响，进程退出即销毁，不会残留
- 全局 `AGENTS.md` 明文禁止非 lab 会话加载逆向技能或调用 `seep_*` 工具，日常编码/运维保持纯净
- 激活后：口语自动合规转译、防拒绝覆盖、快捷口令展开全部生效
- 日常闲聊在 Lab Mode 外原样透传，零干扰

### 任务快捷口令（Lab Mode 激活时有效）

| 口令 | 触发动作 |
|---|---|
| `poc <目标>` | CWE-602 客户端鉴权脆弱性排查 + 验证代码生成 |
| `find-auth <目标>` | 定位授权/许可证/到期时间/机器码相关函数与分支 |
| `hook <函数/方法>` | 生成带堆栈打印与返回值拦截的 Frida 脚本 |
| `gen-patch <位点>` | 输出二进制补丁字节序列或代理 DLL 脚手架 |
| `triage <样本>` | 全量体检：架构/导入表/壳/关键字符串 |
| `check` | 执行工作台 7 维度自检，内联输出健康报告 |
| `report` | 归纳当前目录证据 → 导出三段式审计报告 |

---

## 🔬 核心技术范畴

<details>
<summary>点击展开完整技术范畴</summary>

### 1. 客户端授权流审计（CWE-602）

**权威归属定性**：断网 + 回环劫持 + 时间戳伪造，分钟级判定本地布尔 vs 服务端权威。

**十四大工业级脱敏范式**：

| 项目 | 架构类型 | 核心技法 |
|---|---|---|
| **A** | 单进程纯离线 PE | 标量返回值强制（`mov eax,1; ret`）|
| **B** | 多进程复杂拓扑 | 代理 DLL 分流 + 三层状态持久化 (v12.0 → v6.8.1 → v6.8.10.0: winhttp 单文件裸桩 + 语义重标定 54 点 + 软阻断更新) |
| **C** | 资源模板 + UI 层 | 双射掩码解码 + `SetDlgItemTextW` IAT Hook |
| **D** | 重编译非均匀位移 | **AOB 双态特征码迁移**（3 版本）+ **可选位点版本自适应** + PE 结构门禁 + **运行时调用栈定位** + ACL 冻结 |
| **E** | EXECryptor VM 仲裁 | 2 点 Call 指令重定向至内存 Stub |
| **F** | .NET 动态混淆 | Harmony 内存转储 + 96 位组合哈希算号 |
| **G** | 自引用 SHA-384 | 5 字节函数入口补丁 + 启动项守护 |
| **H** | Ed25519 公钥替换 | 密码流推导内置公钥密文替换 |
| **I** | 弱模 RSA 验签 | CNG 分析 + 滑动窗口旁路 + 导出接口注入 |
| **J** | 在线卡密 + 网络通信 | 协议解密 + 内存补丁 + 本地凭证伪造 |
| **K** | .NET WPF + Themida 加固 | 内存转储脱壳 + 特权决策分支走查 + 注册表状态固化 |
| **L** | Qt5 C++ 客户端 | 代理 DLL Hook + 11 处特权决策常数折叠 + 翻译端点本地 LLM 网关重写 |
| **M** | Java + install4j 双层架构 | DLL 搜索顺序劫持 (version.dll IAT Hook) + JVM 原生 ClassFile 字节码插桩 (burp.Zfqu / burp.Zwxg.Zu) + 授权状态/AI Token 偏好播种 |
| **N** | .NET x64 + VM 混淆加固 | 运行时内存抓取 + 特权标志位反转 + 自动静默注入 |

### 2. Android 移动安全与 DEX/SO 逆向
- 等长字节 DEX 微创修补，自动重算 Adler-32 / SHA-1
- 加壳分类：Java2C / 原生落地壳 / 抽取壳 / 私有 DEX-VMP
- Root 检测规避、多层 SSL Pinning 剥离、Frida-RPC 跨进程桥接
- 自动化重打包：STORED 资源 + 4 字节 Zipalign + v1+v2+v3 签名

### 3. 二进制 / Native 逆向（PE / ELF / Mach-O）
- **`exe-reverse` 深水区层**：PE 结构与体检、等长补丁（校验和重算 + 写盘回读）、AOB 特征码唯一性裁决、跨版本差分、壳/保护识别、虚拟化与控制流平坦化、算法还原、符号执行
- **运行时专项路线**：托管 .NET（含混淆）、Unity IL2CPP 元数据、打包 Python（PyInstaller / Nuitka / pyarmor）、Flutter Dart AOT、内核驱动
- **硬件观测层**：硬件断点、Intel PT 指令追踪、ETW、Hypervisor 辅助观测 —— 用于“所有软件 hook 都被检测”的目标
- Radare2 无头模式：架构识别、熵扫描、符号提取、类 C 伪代码
- IDA Pro MCP 全链路：Hex-Rays 反编译、交叉引用、结构体恢复
- 反调试对抗：故意崩溃 Stub、`svc` 直接系统调用、内核级驱动检测（参见 `MANUAL/ANTI-DEBUG.md`）

### 4. CTF 竞赛与 Web 目标分析
- 攻击网路由：信号 → `seep_kb_search` → 模板装配 → MCP 工具执行
- JWT 弱签 / KID 注入 / SSRF / SSTI / Protobuf 逆向 / 反序列化 Gadget Chain
- 漏洞载荷种子库（`seep_kb_payloads`）+ 应急清单（`seep_kb_checklist`）

</details>

---

## 🤖 智能体消费规范

- **G-Auth 授权门**：每个新目标第一步确认测试授权，无授权即停止。
- **七道门决策树（G0–G6）**：先判鉴权权威（服务端 vs 客户端本地），再选交付形态（补丁 / 内存劫持 / 算号 / 中继 / 载荷提取）。
- **两击失败熔断纪律**：同构路径失败两次 → 强制回退判型，禁止第三次盲试。
- **Zero-Waste Recon**：发现信号先查知识库，禁止从零手写分析脚本。
- **完工严格定义**：控制台无报错 ≠ 完成。必须闭环：目标指纹 → RVA 定位 → PoC 执行 → 断网确认 → 三段式报告。

---

## 📝 交付标准（三段式咨询级报告）

1. **脆弱性原理与业务危害** — 精确 RVA / 文件偏移、调用链根因、CWE-602 映射与业务风险等级
2. **复现路径与可验证 PoC** — 代理 DLL 源码 / Frida 脚本 + 断网铁证（确证脱离服务端依然生效）
3. **纵深防御修复方案**：
   - `SetDefaultDllDirectories` → 封堵 DLL 劫持面
   - `ProcessDynamicCodePolicy` → 阻断非法内存执行
   - 服务端权威原则：加密签名 + 短期令牌，严禁本地强判特权

---

## 🤝 致谢与开源许可 (Acknowledgements & License)

- **开源协议**：本项目基于 **GNU General Public License v3.0 (GPL-3.0)** 协议全面开源。
- 特别致谢开源项目 [**newliver666/apk-reverse**](https://github.com/newliver666/apk-reverse)（MIT License）提供的 Android 逆向门控范式与验证体系。
- 特别致谢开源项目 [**GeniusHu-tgty/Open-tgtylab**](https://github.com/GeniusHu-tgty/Open-tgtylab)（GPL-3.0 License）提供的安全实验室架构与 Zero-Waste Recon 攻防提效体系。
- 特别致谢开源项目 [**LING71671/open-reverselab**](https://github.com/LING71671/open-reverselab)（GPL-3.0 License）提供的实战攻防知识库、攻击网拓扑与 MCP 自动化工具生态。
- 特别致谢开源项目 [**dabao1955/exe-reverse**](https://codeberg.org/dabao1955/exe-reverse)（MIT License）提供的 Windows PE 深水区方法论、带门禁的作业流程与零依赖 PE 引擎。
- 感谢 [**LINUX DO**](https://linux.do/) 社区提供的高质量技术交流氛围。

---

## ⚖️ 免责声明

**本工作台及所载文档、脚本与范例仅供合法授权的安全研究、白盒审计、合规漏洞测试及 CTF 教学演练使用。**

- **严格授权约束**：分析任何目标前必须取得资产所有者完备的书面测试授权。
- **无附带保证**：所有方案基于特定沙盒实测结果按"现状"提供，不构成对任何生产环境的适用性保证。
- **最小侵入原则**：优先在隔离虚拟机或独立副本中开展，严禁对生产系统实施未受控的逆向测试。
- **免责条款**：作者与贡献者不对因不当使用、超出授权或违反法律法规导致的任何后果承担责任。
