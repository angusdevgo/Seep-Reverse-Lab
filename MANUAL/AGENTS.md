# 三个 Agent，三套接线（别混）

> 本工作台支持三个 Agent：**Pi Agent**、**DeepSeek Harness（DSH）**、**Antigravity（agy）**。
> 这份文档只解决一件事：**同一个工作台，在它们身上分别是怎么接进去的。**
>
> 结论：**东西是共享的，接线是各自的。** 当成一套东西看，一定会出事。

---

## 一、先记住这张总表

| | **Pi Agent** | **DeepSeek Harness (DSH)** | **Antigravity (agy)** |
| :--- | :--- | :--- | :--- |
| 安装脚本 | `setup/install-pi.ps1` | `python setup/dsh-plugin-setup.py` | `python setup/agy-setup.py` |
| 接线物 | `~/.pi/agent/mcp.json` + `~/.pi/agent/skills/`（**拷贝**） | **插件包** `seep-lab` + profile patch | `~/.gemini/config/` 下两个 JSON |
| MCP 怎么注册 | 静态 JSON 文件 | 插件在**运行时**用 `ctx.plugin(McpClient)` 挂 | 静态 `mcp_config.json`（或 `agy mcp add`） |
| 技能怎么进来 | 启动时扫 `~/.pi/agent/skills`（副本） | 插件挂 `SkillFilesystem`，**直接指**仓库两个目录 | `skills.json` 的 `entries` **直接指**仓库两个目录 |
| 纪律注入 | `~/.pi/agent/seep-system.md` + 扩展 | 插件里的 `systemPrompt.section` | 仓库根 `AGENTS.md`（agy 自动向上找） |
| lab 闸门 | `Tool/prompts/extensions/security-audit-interceptor.ts` | `packages/seep-lab/lib/lab-gate.js` | **无拦截**（规则层仍然生效） |
| 词替换 | 同一个 TS 扩展 | `packages/seep-lab/lib/lab-rewrite.js` | 无 |
| 设置面板 | 无 | 有（设置 → Seep Lab + 输入框旁 `Lab` 按钮） | 无 |
| 校验命令 | `setup/verify.ps1` | `setup/verify-dsh.py`（25 项 / 102 分） | `python setup/agy-setup.py --list` |
| 换路径怎么办 | 重跑 `install-pi.ps1` | 面板改 / `--root`，然后**重启 DSH** | `--root` 重跑，然后**重启 agy** |
| 更新插件 | 没有「插件」这个概念 | `dsh plugin update`（npm 装时）/ 本地装改代码即生效 | 没有插件，`git pull` 就够 |

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

**三个 Agent 都指向这同一份。** 这就是「一个工作台」的含义。

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
| `packages/seep-lab/` | 插件包源码（发布到 npm 的就是它） |
| `~/.dsh/profiles/web/cordis.patch.yml` | 插件插进加载链的那一条 |
| `~/.dsh/seep-workbench.status.json` | 插件自检状态（只有 DSH 会写） |
| `lib/lab-gate.js` / `lib/lab-rewrite.js` | DSH 版的 lab 与词替换 |
| `lib/client.js` | 设置面板 + 输入框旁的 `Lab` 按钮（pi 没有） |

### Antigravity（agy）独有

| 路径 | 作用 |
| :--- | :--- |
| `~/.gemini/config/mcp_config.json` | MCP 注册表（全局，所有项目共用） |
| `~/.gemini/config/skills.json` | 技能清单，`entries` 里写目录路径 |
| `<仓库>/AGENTS.md` | 规则入口，agy 从当前文件向上走到仓库根自动加载 |
| `~/.gemini/antigravity/builtin/skills/agy-customizations/` | agy 自带的定制系统说明书（权威依据，值得一读） |

**agy 没有的东西**：没有插件包、没有面板、没有 lab 拦截器。
它的强项是「规则 + 技能 + MCP 三件套都认标准格式」，所以接线最省事 —— 但也最没特权。

---

## 四、一个必须盯住的隐患：lab 只有两个实现在真干活

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
>
> **agy 没有 lab 拦截器**（它的定制系统只认规则文件，不认运行时改写），
> 所以第三边没有「实现漂移」这回事 —— 也意味着它拿不到自动词替换。
> 要用 lab 的完整行为，走 pi 或 DSH。

---

## 五、更新方式不一样

| 改了什么 | pi 这边 | DSH 这边 | agy 这边 |
| :--- | :--- | :--- | :--- |
| 仓库里的工具 / 知识库 / 案例 | `git pull`，**重启 pi** | `git pull`，**重启 DSH** | `git pull`，**重启 agy** |
| 技能（`Tool/skill/**`） | `git pull` **+ 重跑 `install-pi.ps1`**（因为是拷贝） | `git pull` 即可（新会话生效） | `git pull` 即可（新会话生效） |
| MCP 配置 / `SEEP_*` 环境变量 | 重跑 `install-pi.ps1` | 面板改，重启 | 重跑 `agy-setup.py`，重启 |
| pi 扩展（TS） | 重跑 `install-pi.ps1` | 不适用 | 不适用 |
| DSH 插件代码 | 不适用 | `file:` 安装＝改代码即生效；npm 安装＝`dsh plugin update` | 不适用 |
| 工作台换目录 | 重跑 `install-pi.ps1` | 面板 / `--root`，重启 | `--root` 重跑，重启 |

**一句话**：`git pull` 对两边都必要，但**不是充分** —— 各自还有各自的接线步骤。
最容易漏的是：**pi 那边只 `git pull` 而不重跑 `install-pi.ps1`，技能还是旧的。**

---

## 六、发布范围只覆盖 DSH

`MANUAL/PUBLISHING.md` 里说的 npm 包 = **只服务 DSH**。

pi 和 agy 都没有被包化，也**不打算**包化：它们的接法都是「写配置」，
分别由 `install-pi.ps1` 和 `agy-setup.py` 完成，没有版本号、没有 registry、没有自动更新。

---

## 七、校验也要分开看

| 命令 | 覆盖范围 |
| :--- | :--- |
| `setup/verify.ps1` | **仓库本身** + pi 接线：技能内容、知识库篇数、工具在位、手册、脱敏扫描、`~/.pi/agent/skills` 是否同步 |
| `setup/verify-dsh.py` | **DSH 接线**：插件是否装、MCP 是否真能起（真启动数工具）、技能是否进注册表、lab、面板 |
| `python setup/agy-setup.py --list` | **agy 接线**：两个 JSON 在不在、挂了哪几个 server、技能清单指向哪 |

**三份校验各查各的，分数不能互相替代。** `verify.ps1` 顺带会看一眼 agy 有没有接上（只是提示，不判失败）。

---

## 八、自查：三边到底接没接

```bash
# pi：看它自己的 MCP 表
python -c "import json,os;print(list(json.load(open(os.path.expanduser('~/.pi/agent/mcp.json')))['mcpServers']))"

# DSH：看插件自己写的状态
cat ~/.dsh/seep-workbench.status.json

# agy：看它挂了什么
agy mcp list
python setup/agy-setup.py --list
```

三边列出的 server 名字可以相同（都叫 seep），但**进程是各自拉起的、跑的是各自配的那份文件**：

```
pi  →  <pi 配置里的仓库>/Tool/mcp/seep_mcp_server.py
DSH →  <面板里配的仓库>/Tool/mcp/seep_mcp_server.py
agy →  <~/.gemini/config/mcp_config.json 里写的仓库>/Tool/mcp/seep_mcp_server.py
```

**同一个 `seep` 名字底下可能是三个不同路径。** 仓库搬家后三边都要各自改。

路径不同就是两套，别拿一个的证据去证明另一个。
