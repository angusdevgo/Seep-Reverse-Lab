# 两个 Agent，两套接线（别混）

> 本工作台**只支持两个 Agent**：**Pi Agent** 与 **DeepSeek Harness（DSH）**。
> 这份文档只解决一件事：**同一个工作台，在两者身上分别是怎么接进去的。**
>
> 结论：**东西是共享的，接线是各自的。** 当成一套东西看，一定会出事。

---

## 一、先记住这张总表

| | **Pi Agent** | **DeepSeek Harness (DSH)** |
| :--- | :--- | :--- |
| 安装脚本 | `setup/install-pi.ps1` | `python setup/dsh-plugin-setup.py` |
| 接线物 | `~/.pi/agent/mcp.json` + `~/.pi/agent/skills/`（**拷贝**） | **插件包** `seep-dsh-workbench` + profile patch |
| MCP 怎么注册 | 静态 JSON 文件 | 插件在**运行时**用 `ctx.plugin(McpClient)` 挂 |
| 技能怎么进来 | 启动时扫 `~/.pi/agent/skills`（副本） | 插件挂 `SkillFilesystem`，**直接指**仓库两个目录 |
| 纪律注入 | `~/.pi/agent/seep-system.md` + 扩展 | 插件里的 `systemPrompt.section` |
| lab 闸门 | `Tool/prompts/extensions/security-audit-interceptor.ts` | `packages/dsh-workbench/lib/lab-gate.js` |
| 词替换 | 同一个 TS 扩展 | `packages/dsh-workbench/lib/lab-rewrite.js` |
| 设置面板 | 无 | 有（设置 → Seep 工作台 + 输入框旁小圆点） |
| 校验命令 | `setup/verify.ps1` | `setup/verify-dsh.py`（24 项 / 100 分） |
| 换路径怎么办 | 重跑 `install-pi.ps1` | 面板改 / `--root`，然后**重启 DSH** |
| 更新插件 | 没有「插件」这个概念 | `dsh plugin update`（npm 装时）/ 本地装改代码即生效 |

---

## 二、共享的是什么（只有一份）

```
<仓库>/
├── Tool/mcp/                     MCP 服务端（seep 38 个工具）
├── Tool/mcp/Tool/safe/           工具本体 561MB（jadx/apktool/radare2/…）
├── Tool/skill/                   5 个主技能
├── Tool/skill/safe-skills/       5 个安全技能
├── Tool/mcp/Tool/reverselab/kb/  知识库 294 篇
├── Tool/cases/                   14 个脱敏案例
└── Tool/prompts/                 SYSTEM.md（纪律正文）/ AGENTS.md（指令底座）
```

**两个 Agent 都指向这同一份。** 这就是「一个工作台」的含义。

---

## 三、各自独有的东西（别互相套）

### Pi 独有

| 路径 | 作用 |
| :--- | :--- |
| `~/.pi/agent/mcp.json` | pi 自己读的 MCP 注册表 |
| `~/.pi/agent/skills/` | **技能副本**（还混着个人技能：github / codeberg / cf / muse） |
| `~/.pi/agent/seep-system.md` | 纪律正文的 pi 版本 |
| `~/.pi/agent/extensions/security-audit-interceptor.ts` | pi 扩展：lab 闸门 + 词替换 |
| `~/.pi/agent/AGENTS.md` | pi 的指令入口 |

### DSH 独有

| 路径 | 作用 |
| :--- | :--- |
| `packages/dsh-workbench/` | 插件包源码（发布到 npm 的就是它） |
| `~/.dsh/profiles/web/cordis.patch.yml` | 插件插进加载链的那一条 |
| `~/.dsh/seep-workbench.status.json` | 插件自检状态（只有 DSH 会写） |
| `lib/lab-gate.js` / `lib/lab-rewrite.js` | DSH 版的 lab 与词替换 |
| `lib/client.js` | 设置面板 + 小圆点（pi 没有） |

---

## 四、一个必须盯住的隐患：两套 lab 实现会漂

pi 的 lab 在 TS 扩展里，DSH 的在插件里 —— **两份代码**。

词表曾经也复制成两份，改一处另一处就过期。现在已经收成一条链：

```
Tool/prompts/extensions/security-audit-interceptor.ts       ← 唯一真值
        │  python Tool/scripts/compliance-relay/extract-rules.py
        ▼
Tool/scripts/compliance-relay/sensitive-rules.json          ← 中间产物
        │  运行时读取
        ▼
DSH 插件 lab-rewrite.js（读不到才退回内置兜底表）
```

**加词的正确做法**：改 TS → 跑 `extract-rules.py` → 两边同时生效。
一致性可以随时验：`python Tool/scripts/compliance-relay/extract-rules.py --check`。

> 行为逻辑（闸门怎么开、什么时候注入）仍是两套实现，
> 我们只保证**规则数据**单源；行为一致性靠测试：pi 侧 `verify.ps1`，DSH 侧 39 项单测。

---

## 五、更新方式不一样

| 改了什么 | pi 这边 | DSH 这边 |
| :--- | :--- | :--- |
| 仓库里的工具 / 知识库 / 案例 | `git pull`，**重启 pi** | `git pull`，**重启 DSH**（MCP 是启动时拉起的） |
| 技能（`Tool/skill/**`） | `git pull` **+ 重跑 `install-pi.ps1`**（因为是拷贝） | `git pull` 即可（直接指向仓库，**新会话生效**） |
| `mcp.json` 或 `SEEP_*` 环境变量 | 重跑 `install-pi.ps1` | 面板改，重启 |
| pi 扩展（TS） | 重跑 `install-pi.ps1` | 不适用 |
| DSH 插件代码 | 不适用 | `file:` 安装＝改代码即生效；npm 安装＝`dsh plugin update` |
| 工作台换目录 | 重跑 `install-pi.ps1` | 面板 / `--root`，重启 |

**一句话**：`git pull` 对两边都必要，但**不是充分** —— 各自还有各自的接线步骤。
最容易漏的是：**pi 那边只 `git pull` 而不重跑 `install-pi.ps1`，技能还是旧的。**

---

## 六、发布范围只覆盖 DSH

`MANUAL/PUBLISHING.md` 里说的 npm 包 = **只服务 DSH**。

pi 没有被包化，也**不打算**包化：它的接法是「写 JSON + 拷技能目录」，
由 `install-pi.ps1` 完成，没有版本号、没有 registry、没有自动更新。

---

## 七、校验也要分开看

| 命令 | 覆盖范围 |
| :--- | :--- |
| `setup/verify.ps1` | **仓库本身** + pi 接线：技能内容、知识库篇数、工具在位、手册、脱敏扫描、`~/.pi/agent/skills` 是否同步 |
| `setup/verify-dsh.py` | **DSH 接线**：插件是否装、MCP 是否真能起（真启动数工具）、技能是否进注册表、lab、面板 |

**`verify.ps1` 里没有 DSH 的深查，`verify-dsh.py` 里没有 pi 的东西。分数不能互相替代。**

---

## 八、自查：两边到底接没接

```bash
# pi：看它自己的 MCP 表
python -c "import json,os;print(list(json.load(open(os.path.expanduser('~/.pi/agent/mcp.json')))['mcpServers']))"

# DSH：看插件自己写的状态
cat ~/.dsh/seep-workbench.status.json
```

两边列出的 server 名字可以相同（都叫 seep），但**进程是各自拉起的、跑的是不同文件**：

```
pi  →  <pi 的仓库>/Tool/mcp/seep_mcp_server.py
DSH →  <panel 里配的仓库>/Tool/mcp/seep_mcp_server.py
```

路径不同就是两套，别拿一个的证据去证明另一个。
