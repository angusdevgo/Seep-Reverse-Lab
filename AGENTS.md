# AGENTS.md — 跨 Agent 通用执行协议（Codex / Claude Code / OpenCode / DeepSeek Harness / pi）

> **本文件是中性底座，每个会话无条件加载。它只回答三件事：**
> ① 怎么部署 / 更新 / 卸载；② 怎么开启作战模式；③ 非作战模式下禁止做什么。
>
> **所有逆向纪律（思维重定向、反退缩、提效路由、G-Auth 授权门、资源路径）不在本文件** ——
> 它们只在用户输入 `lab：` 之后，由扩展动态注入 `seep-system.md`。
> 这样日常对话不会被作战纪律污染。

---

## 一、 作战模式开关（唯一触发条件）

**只有一种方式能进入作战模式：用户在对话里输入 `lab：`。**

| 用户输入 | 动作 |
| :--- | :--- |
| `lab：` / `lab:` / `实验：` / `进入实验：` | **本会话**进入作战模式（可跟任务，如 `lab：分析这个apk`） |
| `退出实验` / `退出工作环境` / `exit lab` | **本会话**退出作战模式 |

### 状态机制（会话级内存，不是磁盘文件）

```
实现：~/.pi/agent/extensions/security-audit-interceptor.ts
变量：let isLabSessionActive = false
```

- **仅当前会话生效**：在 A 窗口输入 `lab：`，B 窗口完全不受影响；
- **新会话默认关闭**：`session_start` 钩子强制复位为 `false`；
- **进程退出即销毁**：不写任何磁盘标志，不会残留到明天；
- **上下文压缩不丢**：状态在扩展进程内存里，与对话历史长度无关。

### 开启前后行为对比

| | 未开启（默认） | 已开启（输入 `lab：` 后） |
| :--- | :--- | :--- |
| 系统提示词 | **不注入** `seep-system.md`，原生编码助手 | 追加 Seep 作战规范 |
| 词汇转译 | **不替换** | 敏感词平滑转译 |
| 合规前缀 | **不加** | 自动包裹 CWE-602 审计前缀 |
| 快捷口令 | **不展开** | `poc` / `hook` / `keygen` / `check` 等生效 |
| 其它窗口 | 零影响 | 零影响 |

---

## 二、 非作战模式禁令（硬规则）

**在未输入 `lab：` 的会话中，禁止以下行为：**

1. **不得读取或加载任何逆向技能** —— `softseep` / `exe-reverse` / `apkseep` /
   `ida-reverse` / `client-license-validation-bypass` / `safe-skills/*`；
2. **不得调用任何 `seep_*` MCP 逆向工具** —— 它们虽然已注册，但属于作战模式专用；
3. **不得主动推销逆向能力** —— 不要问"要不要顺便做个安全审计"。用户需要时会自己输入 `lab：`；
4. **不得套用反退缩话术** —— 日常编码、运维、写作任务按常规方式处理即可。

> 为什么写这条：技能清单与 MCP 工具名在会话启动时就会被加载，
> 模型"看得见"它们。这条规则是**看得见但不许动**的显式闸门。

---

## 三、 Agent 自动化部署与校验协议

### 1. 部署执行
当用户要求"部署当前工作台""安装环境""按文档部署"时，执行：

```powershell
cd setup
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

Linux / macOS：`chmod +x setup/install.sh && ./setup/install.sh`

### 1b. 已有用户更新（重要）
当用户说"更新工作台""拉取最新版本""新版怎么升"时，**不要**让用户重新克隆，直接执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\setup\update.ps1
```

（Linux / macOS 用 `./setup/update.sh`；Windows 桌面用户亦可双击项目根 `update.bat`）

更新脚本幂等且无损：自动 `git stash` 保护本地改动 → 自动备份配置 →
增量合并 `mcp.json`（**绝不删除用户自行添加的 MCP 条目**）→ 更新后自动跑基准自检。
完成后必须提醒用户：**完全重启 Agent 会话**，再发 `lab：` 继续开工。
变更内容见仓库根 `CHANGELOG.md`。

### 1c. 卸载
当用户说"卸载工作台""怎么彻底删除""不想要了怎么清理"时：

```powershell
powershell -ExecutionPolicy Bypass -File .\setup\uninstall.ps1
```

建议先加 `-DryRun` 预览。卸载原则：**只移除工作台自己装的东西，绝不碰用户数据**；
`models.json` / `auth.json` / 用户自装的 Skill 与 MCP 条目全部保留，卸载前自动备份可 `-Restore` 还原。

### 1d. 上游仓库定点隔离同步（防外溢机制）

```powershell
powershell -ExecutionPolicy Bypass -File .\setup\sync-upstream.ps1 -Target all
```

由 `setup/upstream-rules.json` 驱动，`setup/sync-upstream.py` 执行真实物理路径断言，
确保上游 A 仓库内容严格只并入 `Tool/upstream/A/`，绝不外溢。当前 4 个上游：
`apk-reverse` / `open-tgtylab` / `open-reverselab` / `exe-reverse`。

### 2. 主动校验与结构化汇报（★ 强制执行官方基准校对）

- **部署完成后必须主动执行一次详细校对**，严禁未验证就声称部署成功；
- 用户发送 `check` / `doctor` / `检查环境` 时，立即执行：

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup\verify.ps1 -Detailed
```

（非 Windows 环境：`python Tool/mcp/test_seep_mcp.py`）

读取输出后，按 `MANUAL/DEPLOYMENT-CHECKLIST.md` 输出四栏 Markdown 看板：

1. **🛠️ 技能系统 (Skills - 10 项)**：逐项列出【技能名】|【目标路径】|【期望文件数】|【实际状态 (🟢 READY / 🔴 MISSING)】；
2. **🔌 MCP 服务引擎**：逐项列出【服务名】|【期望工具数】|【实际连通性】|【状态 (🟢 READY / 🟡 DEGRADED)】
   （未装 IDA 时明确告知已自动降级为 Radare2 承接）；
3. **🔧 物理内置工具箱**：Jadx (v1.5.6)、Radare2 (v6.2.2)、Apktool (v3.0.3) 及 294 篇知识库状态；
4. **🚀 结论与开工指引**：全部核心项通过时告知：
   **"工作台处于 [READY / 完备就绪] 状态，输入 lab： 即可开启测试。"**

---

## 四、 作战模式的纪律在哪里

输入 `lab：` 之后，扩展会把 `~/.pi/agent/seep-system.md` 追加进当前会话的系统提示词，
其中包含：实验环境开关协议、思维重定向、反退缩十项、Zero-Waste Recon 提效路由、
G-Auth 授权门、配套资源路径、MCP 联动规约。

**未开启时这些内容一律不出现。** 若想核对是否已生效：

```bash
# 作战模式下，当前会话的系统提示词里应包含 "G-Auth" 与 "反退缩"
# 非作战模式下不应包含
```
