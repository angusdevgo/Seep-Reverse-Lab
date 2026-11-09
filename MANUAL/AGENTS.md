# 四个 Agent，四套接线（别混）

> 这份文档只解决一件事：**说清楚同一个工作台，在不同 Agent 上到底是怎么接进去的。**
>
> 结论：**东西是共享的，接线是各自的。** 把 pi 和 DSH 当成一套东西看，一定会出事。

---

## 一、先记住这张总表

| | **Pi Agent** | **DeepSeek Harness (DSH)** | Claude Code | OpenCode / Codex |
| :--- | :--- | :--- | :--- | :--- |
| 怎么装 | `setup/install-pi.ps1` | `python setup/dsh-plugin-setup.py` | `setup/generate-configs.ps1` | 同上 |
| 接线物 | `~/.pi/agent/mcp.json` + `~/.pi/agent/skills/`（**拷贝**） | **插件包** `seep-dsh-workbench` + profile patch | 项目根 `.mcp.json` | `opencode.jsonc` |
| MCP 注册方式 | 静态 JSON 文件 | 插件在**运行时**用 `ctx.plugin(McpClient)` 挂 | 静态 JSON 文件 | 静态 JSON 文件 |
| 技能怎么进来 | 启动时扫 `~/.pi/agent/skills` | 插件挂 `SkillFilesystem`，指到仓库两个目录 | 不适用（无技能机制） | 不适用 |
| 纪律注入 | `~/.pi/agent/seep-system.md` + 扩展 | 插件里的 `systemPrompt.section` | `CLAUDE.md` | 根 `AGENTS.md` |
| lab 闸门 | `Tool/prompts/extensions/security-audit-interceptor.ts` | `packages/dsh-workbench/lib/lab-gate.js` | 无 | 无 |
| 词替换 | 同一个 TS 扩展 | `packages/dsh-workbench/lib/lab-rewrite.js` | 无 | 无 |
| 校验命令 | `setup/verify.ps1`（含 pi 项） | `setup/verify-dsh.py`（24 项 100 分） | `verify.ps1` 的 Agent 段 | 同上 |
| 换路径怎么办 | 重跑 `install-pi.ps1` | 面板改 / `--root` + 重启 | 重跑 `generate-configs` | 重跑 `generate-configs` |

---

## 二、共享的是什么（这部分只有一份）

```
<仓库>/
├── Tool/mcp/                MCP 服务端（seep 38 个工具）
├── Tool/mcp/Tool/safe/      工具本体 561MB（jadx/apktool/radare2/…）
├── Tool/skill/              5 个主技能
├── Tool/skill/safe-skills/  5 个安全技能
├── Tool/mcp/Tool/reverselab/kb/   知识库 294 篇
├── Tool/cases/              14 个脱敏案例
└── Tool/prompts/            SYSTEM.md（纪律正文）/ AGENTS.md
```

**所有 Agent 都指向这同一份。** 这是「一个工作台」的含义。

---

## 三、各自独有的东西（这部分千万别互相套）

### pi 独有

| 文件 | 作用 |
| :--- | :--- |
| `~/.pi/agent/mcp.json` | pi 自己读的 MCP 注册表 |
| `~/.pi/agent/skills/` | **技能副本**（含个人技能 github / codeberg / cf / muse） |
| `~/.pi/agent/seep-system.md` | 纪律正文的 pi 版本 |
| `Tool/prompts/extensions/security-audit-interceptor.ts` | pi 扩展：lab 闸门 + 词替换 |

### DSH 独有

| 文件 | 作用 |
| :--- | :--- |
| `packages/dsh-workbench/` | 插件包（发布到 npm 的就是它） |
| `~/.dsh/profiles/web/cordis.patch.yml` | 插件插进加载链的那一条 |
| `~/.dsh/seep-workbench.status.json` | 插件自检状态（只有 DSH 会写） |
| `lib/lab-gate.js` / `lib/lab-rewrite.js` | DSH 版的 lab 与词替换 |
| `lib/client.js` | 设置面板 + 小圆点（pi 没有这套） |

---

## 四、一个必须盯住的隐患：两套 lab 实现会漂

pi 的 lab 在 TS 扩展里，DSH 的在插件里 —— **两份代码**。

词表曾经也复制成两份（TS 一份、插件一份），改一处另一处就过期。
现在已经收成一条链：

```
Tool/prompts/extensions/security-audit-interceptor.ts       ← 唯一真值
        │  python Tool/scripts/compliance-relay/extract-rules.py
        ▼
Tool/scripts/compliance-relay/sensitive-rules.json          ← 中间产物
        │  运行时读取
        ▼
DSH 插件 lab-rewrite.js（读不到才用内置兜底表）
```

**加词的正确做法**：改 TS → 跑 extract-rules.py → 两个框架同时生效。
改完可以用 `python Tool/scripts/compliance-relay/extract-rules.py --check` 验一致性。

> 行为逻辑（闸门怎么开、什么时候注入）仍是两套实现，
> 我们只保证**规则数据**单源。行为上的一致性靠测试：pi 侧 `verify.ps1`，DSH 侧 39 项单测。

---

## 五、更新方式也不一样

| 改了什么 | pi 这边 | DSH 这边 |
| :--- | :--- | :--- |
| 仓库里的工具/技能/知识库 | `git pull`，**重启 pi** | `git pull`，**技能热更 / MCP 要重启** |
| `mcp.json` 或 `SEEP_*` 环境变量 | 重跑 `install-pi.ps1` | 面板改，重启 |
| pi 扩展（TS） | 重跑 `install-pi.ps1` | 不适用 |
| DSH 插件代码 | 不适用 | `file:` 安装自动生效；npm 安装要 `dsh plugin update` |
| 工作台换目录 | 重跑 `install-pi.ps1` | 面板 / `--root`，重启 |

**一句话**：`git pull` 对两边都必要，但**不是充分**——各自还有各自的接线步骤。

---

## 六、发布章程只覆盖 DSH

`MANUAL/PUBLISHING.md` 里说的 npm 包 = **只服务 DSH**。

pi 没有被包化，也**不打算**包化：它的接法是「写 JSON + 拷技能目录」，
由 `install-pi.ps1` 完成，没有版本号、没有 registry、没有自动更新。

所以：

- 别人问「怎么装到你那个工作台」→ 先回答**用哪个 Agent**
- 说「装插件」→ 指的是 DSH
- 说「跑 install.ps1」→ 一次给所有 Agent 接线

---

## 七、校验也要分开看

| 命令 | 覆盖范围 |
| :--- | :--- |
| `setup/verify.ps1` | **仓库本身**：技能内容、知识库篇数、工具在位、手册、脱敏扫描 |
| `setup/verify-dsh.py` | **DSH 接线**：插件是否装、MCP 是否真能起、技能是否进注册表、lab、面板 |
| `pi` 相关项（在 verify.ps1 里） | `~/.pi/agent/skills/softseep` 是否同步等 |

**`verify.ps1` 里没有 DSH 的深查，`verify-dsh.py` 里没有 pi 的东西。**
分数不能互相替代。

---

## 八、自查：一条命令看两边接没接

```bash
# pi：看它自己的 MCP 表
python -c "import json;print(json.load(open(r'$HOME/.pi/agent/mcp.json'))['mcpServers'].keys())"

# DSH：看插件自己写的状态
cat ~/.dsh/seep-workbench.status.json
```

两边列出的 server 名字可以相同（都叫 seep），但**进程是各自拉起的**：
pi 的子进程跑 `pi/seep/Tool/mcp/seep_mcp_server.py`，
DSH 的子进程跑 `<部署目录>/Tool/mcp/seep_mcp_server.py` —— 路径不同就是两套。
