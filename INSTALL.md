# 安装：先选 Agent，再照着做

> **这是全仓库最该先看的一份文档。**
> 只回答两件事：**你要装什么**、**怎么装**。
>
> 装错了会白忙 —— 因为 Pi Agent、DeepSeek Harness、Antigravity 是**三套不同的框架**，
> 接线方式、配置文件、甚至连 lab 闸门都各有各的实现。

---

## 第 0 步：30 秒做决定

| 你用的是 | 走哪条路 | 一句话 |
| :--- | :--- | :--- |
| **Pi Agent** | → [路线 A](#路线-a-pi-agent) | 写 `mcp.json` + 拷技能目录 |
| **DeepSeek Harness（DSH）** | → [路线 B](#路线-b-deepseek-harness) | 装一个插件包 |
| **Antigravity（agy）** | → [路线 C](#路线-c-antigravityagy) | 改两个 JSON：MCP + 技能清单 |
| 不确定 | 继续往下看 [共同前提](#共同前提三个-agent-都需要) | 先把前提装好，再回来选 |

**装多个？** 三条路互不干扰，先后顺序随意，但**各自都要做一遍**。
它们共享同一份仓库内容，不重复占空间。

---

## 共同前提（三个 Agent 都需要）

### 1. 系统与运行时

| 需要 | 最低 | 检查命令 | 说明 |
| :--- | :--- | :--- | :--- |
| 操作系统 | Windows 10 1809+ / Linux / macOS | — | Web 取证那 8 个工具是 PowerShell 实现，Unix 需装 `pwsh` |
| **Python** | 3.11+（**必须能 `import mcp`**） | `python -c "import mcp; print('ok')"` | seep 的 MCP 服务端靠它跑 |
| **Node.js** | 18+ | `node -v` | js-reverse / playwright 这两个 MCP 靠它 |
| **Java** | 11+ | `java -version` | jadx / apktool 反编译 APK 用 |
| Git | 任意 | `git --version` | 拉仓库、面板里更新都要 |

Python 那个 `import mcp` 最容易翻车：系统装的是 3.10、或 `python` 指向商店占位别名，
都会让 MCP 一启动就挂，而现象只是「工具连不上」。**先跑一遍这条命令再往下走。**

### 2. 把仓库拉下来（三个 Agent 都要）

```bash
git clone https://github.com/angusdevgo/Seep-Reverse-Lab.git seep
cd seep
```

仓库里已经带了全部工具本体（jadx / apktool / radare2 / aotopsy…，约 561 MB），
不需要另外下载。只有两个 `node_modules` 被打包成 zip，第一次要解压：

```bash
powershell -File setup/extract-deps.ps1        # Windows：单独跑，只解压
```

**Linux / macOS 没有单独的这一个脚本** —— `./setup/install.sh` 会顺带把 zip 解好。
想先只解压、不做别的，用 `unzip` 手动解：

```bash
cd Tool/mcp/Tool/safe/js-reverse-mcp && unzip -q node_modules.zip
cd ../playwright-mcp && unzip -q node_modules.zip
```

### 3. 装 Python 依赖（三个 Agent 都要）

```bash
powershell -File setup/install-python.ps1      # Windows：建 venv 并装 mcp
```

**Linux / macOS 走 `./setup/install.sh`**，它内部处理 PEP 668（系统 pip 被锁的情况）
并建好同一套 venv。想单独装也行：

```bash
python3 -m venv ~/.pi/agent/seep-venv
~/.pi/agent/seep-venv/bin/pip install mcp
```

这个 venv 两边共用：pi 的 `mcp.json` 与 DSH 插件都指向它。

---

## 路线 A：Pi Agent

### 装什么

| 东西 | 落到哪 |
| :--- | :--- |
| MCP 注册表 | `~/.pi/agent/mcp.json`（**增量合并**，不覆盖你已有的条目） |
| 10 个技能 | `~/.pi/agent/skills/`（**拷贝**一份过去） |
| 纪律正文 | `~/.pi/agent/seep-system.md` |
| lab 闸门 + 词替换 | `~/.pi/agent/extensions/security-audit-interceptor.ts` |
| 提示词 | `~/.pi/agent/AGENTS.md` / `SYSTEM.md` |

### 怎么装

```bash
powershell -File setup/install-pi.ps1
```

它会先**备份** `~/.pi/agent`，再逐项合并。加上 `-SkipPackages` 可跳过 npm 依赖检查。

### 怎么验

```bash
powershell -File setup/verify.ps1
```

看到 `核心检查通过: 64 项` 就对了。里面包含 pi 的那几项（技能是否同步、mcp.json 是否写对）。

### 装完必须做

**完全退出并重开 Pi**（含终端）。MCP 是会话启动时握手的，不重开看不到工具。

然后发一句 `lab：` 试一下。

### 怎么更新

```bash
cd seep && git pull
powershell -File setup/install-pi.ps1      # 技能/扩展/mcp.json 变了才需要
```

pi 的技能是**拷贝**的，所以 `git pull` 之后**必须**重跑 `install-pi.ps1` 才能同步技能。
（DSH 是直接指过去的，没这一步 —— 这是两边最大的差别。）

---

> 装完之后怎么更新、插件发在哪、更新时会连带什么：见 [MANUAL/UPDATING.md](MANUAL/UPDATING.md)。

## 路线 B：DeepSeek Harness

### 装什么

| 东西 | 落到哪 |
| :--- | :--- |
| **插件包** `seep-lab` | `~/.dsh/profiles/web/node_modules/` |
| 一条挂载配置 | `~/.dsh/profiles/web/cordis.patch.yml` |
| 运行状态 | `~/.dsh/seep-workbench.status.json`（只有 DSH 写这个文件） |

**不需要**改 `~/.pi/agent` 下任何东西，也不需要装任何技能副本 ——
插件会在运行时把 MCP 和技能直接指向仓库。

### 怎么装

```bash
python setup/dsh-plugin-setup.py
```

常用参数：

```bash
python setup/dsh-plugin-setup.py --check              # 只报状态，不改文件
python setup/dsh-plugin-setup.py --with-playwright    # 多挂 25 个浏览器工具
python setup/dsh-plugin-setup.py --with-ida           # 多挂 48 个 IDA 工具
python setup/dsh-plugin-setup.py --root D:\新位置\seep # 仓库搬家后重跑这条
```

### 两种装法，差别只在「以后怎么更新」

| | 默认（本地目录） | `--from-npm` |
| :--- | :--- | :--- |
| 命令 | `python setup/dsh-plugin-setup.py` | `python setup/dsh-plugin-setup.py --from-npm` |
| 插件从哪来 | 仓库里的 `packages/seep-lab/` | npm 上的 `seep-lab` |
| 改了 `lib/*.js` | **重启就生效**（硬链接） | 不生效，要等发新版 |
| 面板「更新插件」 | 灰色不可点 | **可点，自动拉新版** |
| 适合谁 | 想改代码 / 没网 | 只想用，不想管插件版本 |

> 两者都需要先 clone 仓库 —— 561 MB 的工具本体在仓库里，不进 npm 包。
> 装完想换装法，直接跑另一条命令即可（脚本会自动卸掉旧的再装新的）。

### 怎么验

```bash
python setup/verify-dsh.py
```

要看到 `100.0% (102 / 102 分)`。它查的是 DSH 专属接线：
插件装了没、MCP 能不能真起来（**真的启动数工具**，不是看配置）、技能进没进注册表、面板在不在。

### 装完必须做

**完全退出并重开 DSH。** 然后：设置 → **Seep Lab**，能看到运行状态就对了。

### 怎么更新

```bash
cd seep && git pull      # 工具 / 技能 / 知识库
dsh plugin update --profile web seep-lab   # 只更新插件（从 npm 装时才有意义）
```

或者全在面板上点：**更新插件** / **更新工作台** / **更新内容**。

**技能不用重装**：插件直接指向仓库目录，`git pull` 就生效（新会话可见）。
只有 MCP 服务端变了才需要重启 DSH。

---

## 路线 C：Antigravity（agy）

Antigravity 是 Google 的 Agent IDE（VS Code 派生）。它认三种定制：**规则 / 技能 / MCP**。
我们的仓库三种都能喂，只有后两种要写配置。

### 装什么

| 东西 | 落到哪 | 谁负责 |
| :--- | :--- | :--- |
| **规则**（`AGENTS.md`） | 仓库根，已经有了 | agy 自己会自动向上找到，**零配置** |
| **技能清单** | `~/.gemini/config/skills.json` | `agy-setup.py` 写 |
| **MCP 服务** | `~/.gemini/config/mcp_config.json` | `agy-setup.py` 写（优先走 `agy mcp add`）|
| **钩子** | `~/.gemini/config/hooks.json`（全局） | `agy-setup.py --with-hooks` 生成 |

**不动 Antigravity 的用户设置和模型配置。** 只写上面这三处。

> **钩子默认装成全局**，因为规则/技能/MCP 都是全局的，钩子如果只装在仓库里，
> 你换了工作区就失效。全局装的效果是：**打开 agy、不管在哪个项目，发 `lab：` 都能用**。

### 怎么装

```bash
python setup/agy-setup.py
```

常用参数：

```bash
python setup/agy-setup.py --list              # 只报现状，不改文件
python setup/agy-setup.py --dry-run           # 只说会改什么
python setup/agy-setup.py --with-playwright   # 额外挂 25 个浏览器工具
python setup/agy-setup.py --with-ida          # 额外挂 48 个 IDA 工具
python setup/agy-setup.py --root D:\新位置\seep   # 仓库搬家后重跑
python setup/agy-setup.py --force             # 覆盖已存在的同名 server
```

默认挂两个：`seep`（38 个工具）+ `js-reverse`（24 个工具）。

> **你已有的 MCP 条目不会被删。** 脚本只做「加」，同名条目默认跳过（保住你自己加的参数，
> 比如 playwright 的扩展 token）。要覆盖才加 `--force`。

### 钩子：为什么装全局

| 装法 | 命令 | 什么时候生效 |
| :--- | :--- | :--- |
| **全局（默认）** | `--with-hooks` | 打开 agy 就能用，任何工作区 |
| 仅本仓库 | `--with-hooks --hooks-scope workspace` | 只有用 agy 打开这个仓库才生效 |

**全局不会污染别的项目**，钩子自己分得清：

| 你在哪 | 开场说什么 | `lab：` | 审计流水 |
| :--- | :--- | :--- | :--- |
| 本仓库 | 完整说明（工具/技能/授权范围） | 纪律 + 术语表 + 授权范围 | 记 |
| 别的项目 | 一句「Seep 工具可用，要开工发 lab：」 | 纪律 + 术语表（**不贴本仓库工单**） | lab 开了才记 |

也就是说：**不开 lab 就等于不存在**，别的项目里你感觉不到它。

### 钩子：lab 闸门怎么补上的

agy 本身没有运行时改写钩子，但它有**生命周期钩子**（`SessionStart` / `PreInvocation` /
`PostToolUse`），可以往上下文里注入内容。`--with-hooks` 就是把这套接起来：

| 事件 | 脚本 | 干什么 |
| :--- | :--- | :--- |
| `SessionStart` | `.agents/hooks/session_start.py` | 开场说明一次：这个仓库有什么、`seep_*` 怎么调、lab 怎么开 |
| `PreInvocation` | `.agents/hooks/pre_invocation.py` | **lab 闸门**：`lab：` 开、`退出实验` 关；开着就注入审计约定 + 术语对照 |
| `PostToolUse` | `.agents/hooks/post_tool_use.py` | 审计流水：每次工具调用记一行到 `~/.seep/agy-audit.jsonl` |

**能做和不能做的，说清楚：**

| | agy | pi / DSH |
| :--- | :--- | :--- |
| 追加系统消息 | ✅ 可以 | ✅ |
| **改写你的原话** | ❌ 做不到（契约不支持） | ✅ 可以 |
| 拦截词表替换 | ⚠️ 只能注入「对照表」让模型理解，不能替换原文 | ✅ 真替换 |

也就是说：agy 这边用户的字还是用户说的，我们只是**补充上下文**。
想真替换措辞，得用 pi 或 DSH。

**一条命令回答「到底能不能调」：**

```bash
python setup/agy-setup.py --probe
```

它不看配置，**真起一次 MCP 进程**走完握手数工具，再逐个检查 10 个技能的
frontmatter（agy 靠 `description` 决定要不要激活，缺了会被静默跳过）。期望：

```
  [ok] seep MCP 起得来，拿到 38 个工具
  [ok] 技能 10 个，frontmatter 全合规（name + description 都在）
  MCP 已注册 : 4 个（ida, js-reverse, playwright, seep）
  技能清单   : 已指向仓库
  钩子       : 已装（lab： 可用）
```

**怎么确认钩子真的生效**（三段，从离线到线上）：

```bash
# ① 离线自检：钩子脚本本身对不对（不用开 agy）
python setup/test_agy_hooks.py          # 应看到 Ran 12 tests ... OK

# ② 打开探针，去 agy 里发一句 lab：
python setup/agy-watch.py
```

探针跑着的时候，在 Antigravity 里发 `lab：`，终端应立刻出现：

```
  lab 状态 : 有记录
      🟢 lab 开  17:21:34  会话 ec33ebf9-0cba-41
  ✅ 钩子在跑
```

再让它调一次工具（例如「用 seep_status 看下环境」），审计流水应多一行：

```
  审计流水 : 1 条
      2026-11-21T17:21:34+0800  seep_status   ok
```

```bash
# ③ 反向验证（证明因果，不是巧合）
mv .agents/hooks.json .agents/hooks.json.off
#   → 回 agy 重新发 lab：，探针应该毫无反应
mv .agents/hooks.json.off .agents/hooks.json
```

**探针什么都不显示 = 钩子没被调用**，按这三条排查：

| 症状 | 原因 | 处理 |
| :--- | :--- | :--- |
| 两个文件都不生成 | agy 的工作区不是这个仓库根 | 用 agy 打开 `<仓库根>`，不是它的子目录 |
| 同上 | 生成 hooks.json 后没重启 | 完全退出 Antigravity 再开 |
| `hooks.json` 标 ✗ | 忘了 `--with-hooks` | `python setup/agy-setup.py --with-hooks` |
| lab 有记录、流水没有 | 模型没调工具（只在聊天） | 明确让它调一个 `seep_*` 工具 |

**lab 状态存在哪**：`~/.seep/agy-lab.json`，按 `conversationId` 记，天然会话级。
不用了直接删这个文件（连同 `agy-audit.jsonl` 一起删就是全清）。

**审计流水怎么看**：

```bash
tail -f ~/.seep/agy-audit.jsonl
```

一行一条：时间、会话、工具名、参数摘要（大字段只存 sha256，不会把整个 APK 写进日志）、成功与否。

**关掉钩子**：删掉 `~/.gemini/config/hooks.json`，或把里面某一段的 `"enabled"` 设成 `false`。

### 怎么验

```bash
agy mcp list
```

应该看到 `seep` 和 `js-reverse` 都是 `enabled`。

然后在 agy 里打开这个仓库，随便点一个文件 —— `AGENTS.md` 会自动进上下文；
再让它「用 `seep_auto_triage` 看一眼这个 apk」，能调起来就通了。

### 装完必须做

**重启 Antigravity**（或新建一个会话）。配置是启动时读的。

### 怎么更新

```bash
cd seep && git pull
python setup/agy-setup.py      # 仓库路径变了才需要重跑，一般不用
```

技能和 MCP 都直接指向仓库目录，`git pull` 就生效（新会话可见）。
Antigravity 没有面板插件，所以**没有一键更新按钮** —— 更新就是 `git pull`。

钩子脚本改了（`.agents/hooks/*.py`）不用重跑 setup，下一次触发就用新版。

### 它没有的东西

| 能力 | Pi | DSH | agy |
| :--- | :--- | :--- | :--- |
| `lab：` 闸门按钮 | 输入 `lab：` | 输入框右侧 `Lab` 按钮 | 输入 `lab：`（规则层生效） |
| 面板一键更新 | `update.ps1` | 面板按钮 | 无，`git pull` |
| 敏感词改写 | 扩展拦截 | 插件拦截 | 无（不影响工具使用） |

---

## 一次装全部（图省事）

```bash
powershell -File setup/install.ps1
```

这一条会依次做：解压依赖 → 检测环境 → 装 Python 依赖 → 配 Pi → 生成各家配置 →
装 DSH 插件（装了 DSH 才有）→ 接 Antigravity（装了 agy 才有）→ 可选能力包 →
跑 `verify.ps1` → 跑 `verify-dsh.py`。

**没装的框架会自动跳过**，不会报错。

**适合「我全都要」，不适合「只想装一个」** —— 只想装 DSH 就别用这条，
用路线 B 的两条命令更干净。

---

## 装完之后：怎么用

在对话框里发：

```
lab：
```

只有这一句（或 `实验：` / `enter lab`）才会进入作战模式。
**聊到 APK、破解、hook 都不算激活** —— 这是刻意的安全边界。

退出：`退出实验`。

DSH 还可以直接点面板上的 Lab 开关，效果一样。
Antigravity 没有按钮，同样在输入框里打 `lab：`。

---

## 常见失败对照表

| 症状 | 大概是 | 怎么办 |
| :--- | :--- | :--- |
| `verify` 说 Python 没 `import mcp` | `python` 指向了错误解释器 | `SEEP_PYTHON=<正确路径>` 或重跑 `install-python.ps1` |
| MCP 工具一个都看不到 | Agent 没重启 | 完全退出重开（不是新开一个标签页） |
| `verify-dsh.py` 说插件没装 | 装到了别的 profile | 加 `--profile <名字>` 重跑 |
| DSH 面板一片空白 / 没有「Seep Lab」 | 插件没生效 | `python setup/dsh-plugin-setup.py --check` |
| 提示「工作台路径不存在」 | 仓库搬过家 | 面板改路径，或 `--root` 重跑，然后**重启 DSH** |
| pi 的技能是旧的 | 技能是拷贝的 | 重跑 `install-pi.ps1` |
| `未找到 jadx` | 依赖 zip 没解压 | `setup/extract-deps.ps1` |
| Windows 上 `tar` 报错 | Git Bash 把 `C:` 当主机名 | 用 PowerShell，或加 `--force-local` |

---

## 三家到底差在哪（防止装混）

| | Pi | DSH | Antigravity（agy） |
| :--- | :--- | :--- | :--- |
| 技能 | **拷贝**到 `~/.pi/agent/skills` | 插件**直接指向**仓库目录 | `skills.json` **指向**仓库目录 |
| MCP 写在 | `~/.pi/agent/mcp.json` | 插件运行时挂载 | `~/.gemini/config/mcp_config.json` |
| 指令入口 | `~/.pi/agent/seep-system.md` | 插件注入 | 仓库根 `AGENTS.md`（自动） |
| `git pull` 后 | 要重跑 `install-pi.ps1` | 技能直接生效，MCP 要重启 | 技能直接生效，MCP 要重启 |
| lab 闸门 | TS 扩展 | 插件里的 JS | 无拦截（规则层生效） |
| 设置面板 | 没有 | 有（设置 → Seep Lab） | 没有 |
| 校验命令 | `verify.ps1` | `verify-dsh.py` | `agy-setup.py --list` |

更细的对照见 [MANUAL/AGENTS.md](MANUAL/AGENTS.md)。

---

## 只想看目录结构

```
seep/
├── INSTALL.md          ← 你在看的这份
├── setup/              所有安装/校验脚本
├── Tool/
│   ├── mcp/            MCP 服务端 + 内置工具本体
│   ├── skill/          10 个技能
│   ├── cases/          14 个脱敏案例
│   └── prompts/        纪律正文（SYSTEM.md）与指令入口（AGENTS.md）
├── packages/seep-lab/   DSH 插件源码（发布到 npm 的就是它）
└── MANUAL/             部署细节、校验基准、发布章程
```
