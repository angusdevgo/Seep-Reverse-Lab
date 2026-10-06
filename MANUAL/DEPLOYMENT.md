# MANUAL — 工作台全景部署与多 Agent 集成指南 (Deployment Guide)

> 本手册是 **Seep Reverse Lab** 的咨询级部署标准规范。
> 无论您使用的是 **Pi Agent**、**Claude Code**、**DeepSeek Harness (DSH)** 还是 **Codex / OpenCode**，亦或是运行在 **Windows**、**Linux** 或 **macOS** 环境，均可按照本手册实现 **100% 零错漏完整部署**。

---

## 一、 核心环境准入标准 (Prerequisites Matrix)

在安装与初始化工作台前，请确保宿主机满足以下基础依赖：

| 依赖项 | 最低版本要求 | 检查命令 | 验证标准 | 说明 |
|---|---|---|---|---|
| **操作系统** | Windows 10/11 x64<br>Ubuntu 20.04+ / macOS 12+ | `[Environment]::OSVersion` 或 `uname -a` | 64 位操作系统 | 推荐 Windows 10/11 作为逆向主环境 |
| **Python** | Python 3.11 或 3.12 | `python --version` | `>= 3.11.0` | 必须勾选 `Add to PATH`，支持 `venv` 与 `pip` |
| **Node.js** | Node.js 18.x 或 20.x LTS | `node --version` | `>= 18.0.0` | 支持 `npx`，供 JS 逆向与无头浏览器运行 |
| **Git** | Git 2.30+ | `git --version` | 可执行 | 用于代码拉取与版本控制 |
| **Java JDK** | OpenJDK 17 LTS (可选) | `java -version` | 17 LTS | **非强制**。未装 Java 时 Apktool/JADX 提示缺失，但 R2/PE 逆向 100% 可用 |
| **IDA Pro** | 7.7 ~ 9.0 (可选) | — | 拥有合规商业授权 | **非强制**。未装时工作台自动降级为内置 Radare2 套件 |

---

## 二、 自动化一键安装部署 (One-Click Setup)

工作台已将核心逆向套件（Radare2、JADX、Apktool、Playwright 自动化组件、JS 逆向引擎）物理内置在 `Tool/mcp/Tool/safe/` 中。安装脚本会自动解压离线依赖包并注册环境。

### 1. Windows 用户（推荐）
以普通用户或管理员身份打开 PowerShell，进入项目根目录：
```powershell
cd setup
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

> **自动化流水线动作**：
> 1. **离线解压**：自动检测并解压 `js-reverse-mcp` 与 `playwright-mcp` 的预置 `node_modules.zip`；
> 2. **协议依赖**：通过 pip 安装 Python 标准 `mcp` 协议库（`mcp>=1.20,<1.29`）；
> 3. **工具链校验**：检测内置 Radare2、JADX、Apktool 执行文件完整性；
> 4. **配置自愈**：读取本地实际物理路径，自动将绝对路径写入配置文件；
> 5. **自检门禁**：自动调用 `verify.ps1` 进行 37 项完备性体检。

### 2. Linux / macOS 用户
打开终端，进入项目根目录：
```bash
chmod +x setup/install.sh
./setup/install.sh
```

---

## 三、 四大主流 Agent 接入专属 SOP

### 1. 🟣 Pi Agent 专属接入流程

Pi Agent 是原生支持 Skill 渐进式披露、拦截扩展与 `lab：` 状态机的主力智能体。

1. **执行自动化安装脚本**（如已执行过第一步可跳过）：
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\setup\install.ps1
   ```
2. **确认写入目录**：
   - 技能包写入至：`~/.pi/agent/skills/`（包含 `softseep`、`apkseep` 等 9 个技能）；
   - 系统提示词写入至：`~/.pi/agent/SYSTEM.md` 与 `AGENTS.md`；
   - 安全放行扩展写入至：`~/.pi/agent/extensions/security-audit-interceptor.ts`；
   - MCP 服务注册至：`~/.pi/agent/mcp.json`（其中已将 `<SEEP_ROOT>` 自动替换为当前工作台绝对路径）。
3. **关键动作：重启 Pi Agent**：
   - ⚠️ **切记**：安装完成后，**必须完全关闭当前的 pi 终端会话并重新拉起 `pi`**，使得新挂载的 Skill 和扩展被内存加载。
4. **模型凭据配置 (API Key)**：
   - 编辑 `~/.pi/agent/models.json`（或在启动时按提示配置），填入您授权的大模型 API Key（推荐 Claude 3.5 Sonnet / DeepSeek-V3 / GPT-4o）。
5. **开工打卡**：
   在 Pi 对话框中发送：
   ```text
   lab：
   ```
   看到状态标记写入成功后，即可直接下达逆向大白话任务！

---

### 2. 🟠 Claude Code 专属接入流程

Claude Code 原生支持项目级上下文（`CLAUDE.md`）与项目级 MCP 注册（`.mcp.json`），是配置最简洁的智能体。

1. **环境自愈生成**：
   在项目根目录下运行一键配置生成脚本，确保 `.mcp.json` 中的命令指向当前实际路径：
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\setup\generate-configs.ps1
   ```
2. **确认依赖就绪**：
   确保运行 Claude Code 的当前终端能够执行 Python 并已安装 `mcp` 库：
   ```bash
   python -c "import mcp; print('MCP Ready')"
   ```
   若报错，执行：`pip install "mcp>=1.20,<1.29"`。
3. **启动 Claude Code**：
   在 Seep 项目根目录下直接运行：
   ```bash
   claude
   ```
4. **验证 MCP 挂载状态**：
   在 Claude 对话界面中输入：
   ```text
   /mcp
   ```
   检查 `seep` 服务是否显示为绿色 `connected`，且暴露出 23 个工具。
5. **执行一键校验**：
   在 Claude 对话框直接发送：
   ```text
   check
   ```
   Claude 会自动执行 `check.ps1` 并以内联卡片向您汇报当前环境健康度。

---

### 3. 🔵 DeepSeek Harness (DSH) 专属接入流程

DeepSeek Harness 采用基于 Cordis 插件协议的 YAML 配置。根据 [DSH 官方规范](https://deepseek-harness.github.io/deepseek-harness/guide/mcp-memory)，其补丁机制采用 `- insert:` 语法。

1. **自动生成官方标准 Cordis Overlay 补丁**：
   在项目根目录下执行：
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\setup\generate-configs.ps1
   ```
   脚本将自动读取当前物理路径并生成已填好真实路径的 `setup/cordis.generated.yml`（采用官方标准的 `- insert:` 顶层语法）。
2. **挂载运行（两种官方方式二选一）**：
   - **方式 A（命令行启动热挂载 · 最推荐）**：
     ```bash
     dsh web --patch "<SEEP_ROOT>/setup/cordis.generated.yml"
     ```
   - **方式 B（写入用户 Profile 持久生效）**：
     - 若针对单一 profile：将 `setup/cordis.generated.yml` 内容追加合并至 `$DSH_HOME/profiles/<name>/cordis.patch.yml`；
     - 若针对本机所有 profile：合并至 `$DSH_HOME/cordis.patch.yml`。
3. **加载核心指令**：
   将 `Tool/prompts/AGENTS.md` 复制或软链至 DSH 工作目录根路径。
4. **启动会话并开工**：
   在 DSH 中启动会话，发送 `check` 确认环境连通。

---

### 4. 🟢 Codex / OpenCode 专属接入流程

OpenCode 原生支持项目级与全局级 MCP 工具，其配置标准为 `opencode.jsonc`（顶层为 `"mcp"`，命令为数组格式）。

1. **自动生成 OpenCode 工作区配置文件**：
   运行：
   ```powershell
   powershell -ExecutionPolicy Bypass -File .\setup\generate-configs.ps1
   ```
   脚本将自动在项目根目录下生成合规的 `opencode.jsonc`。
2. **官方配置规范对照**：
   生成的文件结构完全符合 [OpenCode 官方 MCP 标准](https://dev.opencode.ai/docs/mcp-servers/)：
   ```jsonc
   {
     "$schema": "https://opencode.ai/config.json",
     "mcp": {
       "seep": {
         "type": "local",
         "command": [
           "python",
           "C:/实际路径/Tool/mcp/seep_mcp_server.py"
         ],
         "enabled": true,
         "environment": {
           "PYTHONIOENCODING": "utf-8"
         }
       }
     }
   }
   ```
3. **指令载入与启动**：
   在项目根目录下直接运行 `opencode`。OpenCode 会自动解析根目录的 `opencode.jsonc` 挂载 23 项 `seep` 工具，并自动加载项目根目录的 `AGENTS.md` 作为作战协议。发送 `check` 即可开启自检！
         "env": { "PYTHONIOENCODING": "utf-8" }
       }
     }
   }
   ```
3. **指令载入**：
   确保项目根目录下存在 `AGENTS.md`。启动 OpenCode 后，Agent 会自动解析该文件作为系统级作战协议。

---

## 四、 已有用户更新指南 (How to Update)

> 如果你**已经部署过**本工作台，不需要重新克隆或手动拷贝任何文件。
> 工作台的更新是**幂等且无损的**：你的模型凭据、自定义 MCP 配置永不会被覆盖。

### 1. 一键更新（推荐）

**Windows**：
```powershell
cd <你的工作台目录>
powershell -ExecutionPolicy Bypass -File .\setup\update.ps1
```

**Linux / macOS**：
```bash
cd <你的工作台目录>
./setup/update.sh
```

### 2. 更新脚本做了什么

| 步骤 | 动作 | 安全保障 |
|---|---|---|
| 1 | 记录当前版本与用户自有数据指纹 | — |
| 2 | 自动探测代理并 `git pull` 拉取最新代码 | 有本地改动时先 `git stash` 保存 |
| 3 | 打印 `CHANGELOG.md` 本次变更说明 | 更新前先预览 |
| 4 | 调用 `install.ps1` 幂等增量同步 | **自动备份**到 `~/.pi/agent/backup-<时间戳>/` |
| 5 | 校验用户自有数据零丢失 | 对比更新前后的 MCP 条目 |
| 6 | 跑官方基准自检并输出报告 | 47/46 项门禁 |

### 3. 永不被覆盖的用户数据

| 文件 | 说明 |
|---|---|
| `~/.pi/agent/models.json` | 你的模型凭据与自定义 provider |
| `~/.pi/agent/auth.json` | 登录凭证 |
| `~/.pi/agent/mcp.json` 中**你自行添加**的 MCP 条目 | 仅**增量合并**，不会删除已有项 |
| `~/.pi/agent/lab-mode.flag` | 实验环境状态 |
| `~/.codex/config.toml`、`.mcp.json`（项目根） | 脚本**从不**自动改写 |

> 脚本只会**新增**工作台自带的标准 MCP 条目（`seep` / `js-reverse` / `playwright`），
> 以及**更新**它自己管理的 Skill 与提示词。

### 4. 常用更新参数

| 参数 | 作用 |
|---|---|
| `-DryRun`（Windows）/ `--dry-run` | 只显示将要做什么，**不修改任何文件** |
| `-NoPull` / `--no-pull` | 跳过 `git pull`（适用于手动下载压缩包覆盖的场景） |
| `-SkipVerify` / `--skip-verify` | 跳过最终自检（不建议） |
| `-IdaRoot "<路径>"`（Windows） | 更新时顺带绑定 IDA Pro 路径 |

### 5. 压缩包部署的用户（非 Git）

如果你当初是下载 ZIP 解压的，没有 `.git` 目录：

1. 下载最新 ZIP 并解压到**临时目录**；
2. 用新目录**覆盖**旧目录中的 `Tool/`、`setup/`、`MANUAL/`、`README*.md`、`CHANGELOG.md`、`VERSION`；
   > **切勿**覆盖你自己的 `work/`、`project/`、`logs/` 等数据目录；
3. 进入新目录运行 `setup/update.ps1 -NoPull`（或 `setup/update.sh --no-pull`）完成配置同步。

### 6. 更新后必做的一步

> ⚠️ **必须完全关闭并重新打开 Agent 会话**（Pi / Claude Code / DSH / OpenCode）。
> 新同步的 Skill 与扩展需要重新加载才会生效。

### 7. 如何回滚

| 回滚对象 | 操作 |
|---|---|
| **配置** | 从 `~/.pi/agent/backup-<时间戳>/` 拷回 `mcp.json` / `settings.json` 等 |
| **代码** | `git -C <工作台目录> log --oneline -10` 找到目标提交后 `git reset --hard <commit>` |

### 8. 更新前先看变更

每次更新的内容都记录在 **[CHANGELOG.md](../CHANGELOG.md)**，包含新增 / 变更 / 修复 / 安全四类，
并标注哪些需要手工干预。建议更新前扫一眼。

---

## 五、 常见部署故障与排障速查表 (FAQ)

### Q1: 运行 `check.ps1` 报错 `Running scripts is disabled on this system`？
- **根因**：Windows PowerShell 默认的执行策略（ExecutionPolicy）为 `Restricted`。
- **解决**：
  - 临时允许当前脚本：在终端中显式加上 `-ExecutionPolicy Bypass`：
    `powershell -ExecutionPolicy Bypass -File .\check.ps1`
  - 或永久放开当前用户策略：在管理员 PowerShell 中执行：
    `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser`

---

### Q2: MCP 启动报错 `ModuleNotFoundError: No module named 'mcp'`？
- **根因**：系统存在多个 Python（例如系统 Python、Conda、嵌入式 Python、或者全局安装了但 Agent 启动的是另一个），`mcp` 库安装在了别的环境中。
- **解决**：
  1. 查看当前终端调用的 python 绝对路径：
     `Get-Command python | Select-Object Source`
  2. 强制为该绝对路径下的 Python 安装依赖：
     `python -m pip install "mcp>=1.20,<1.29"`
  3. 若使用虚拟环境，请在 `mcp.json` 中把 `"command": "python"` 改为虚拟环境的绝对路径（如 `"C:/Users/.../venv/Scripts/python.exe"`）。

---

### Q3: 运行 `seep_r2_*` 或 `seep_apk_*` 报 `node_modules` 或文件找不到？
- **根因**：GitHub 上传限制，部分工具依赖包以 `.zip` 形式预打包，用户未运行解压脚本。
- **解决**：
  运行离线解压修复脚本即可自动恢复：
  ```powershell
  powershell -ExecutionPolicy Bypass -File .\setup\extract-deps.ps1
  ```

---

### Q4: 提示词输入 `lab：` 后模型毫无反应，依然按普通模式闲聊？
- **根因**：
  1. Pi Agent 的拦截扩展 `security-audit-interceptor.ts` 未被正确复制到 `~/.pi/agent/extensions/`；
  2. 或者部署完成后未**重启 Pi Agent**。
- **解决**：
  1. 检查是否存在文件：`Test-Path "$env:USERPROFILE\.pi\agent\extensions\security-audit-interceptor.ts"`；
  2. 杀掉当前终端进程，重新打开终端启动 `pi`。

---

### Q5: 体检时 IDA Pro 显示黄色 `[! OPTN]`，这算报错吗？
- **解答**：**不算报错，完全不影响核心使用！**
  - IDA Pro 是商业闭源软件，根据合规与版权要求，工作台**绝不随包捆绑**；
  - 如果您本地未安装 IDA Pro，工作台内置的 **Radare2 全套二进制套件** 会全自动承接反汇编、反编译与函数枚举任务；
  - 如果您拥有合法的商业授权，可阅读 `MANUAL/IDA-PRO.md`，执行 `setup/install-ida.ps1 -IdaRoot "<您的IDA路径>"` 即可完成挂载。

---

### Q6: Git Push 或同步时报 Connection Reset / Failed to connect to github.com？
- **根因**：网络代理端口未对齐。
- **解决**：
  在终端临时指定本地代理端口（根据您的代理工具设置为 10808 / 7897 / 7890）：
  ```bash
  git -c http.proxy=http://127.0.0.1:10808 -c https.proxy=http://127.0.0.1:10808 push origin main
  ```
