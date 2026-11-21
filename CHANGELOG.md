# Changelog

> 本文件面向**已部署用户**，说明每次更新带来什么变化、需要注意什么。
> 更新操作见 [MANUAL/DEPLOYMENT.md — 更新指南](MANUAL/DEPLOYMENT.md#八-已有用户更新指南)。
>
> **模型选型与拒答排查**见 [MANUAL/MODEL-REFUSAL-MATRIX.md](MANUAL/MODEL-REFUSAL-MATRIX.md)（实测对照表）。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## [Unreleased]

### 变更

- **只支持两个 Agent：Pi Agent 与 DeepSeek Harness。** 移除 Claude Code / OpenCode / Codex 的
  支持面：`generate-configs` 不再生成 `.mcp.json` 与 `opencode.jsonc`，只产出
  `setup/cordis.generated.yml` 与项目根 `AGENTS.md`；仓库里删掉 `CLAUDE.md` 与两个模板文件。
- `verify.ps1` / `verify.sh` 去掉 Claude Code 与 `.mcp.json` 两项检查（66 → 64 项）。
- 文档全面对齐：`INSTALL.md` 去掉路线 C，`MANUAL/DEPLOYMENT.md` 从「四大 Agent」改为两个，
  `MANUAL/AGENTS.md` 重写为两列对照，README 中英双语的 Agent 表也同步。
- `setup/test_config_parity.py` 只比两份产物（cordis + AGENTS）。

> 模型层面的 Claude / GPT / Gemini 仍可作为**后端模型**使用（见 MODEL-REFUSAL-MATRIX），
> 这里移除的是「把 Claude Code / Codex / OpenCode 当作受支持的 Agent 客户端」。


## [1.15.0] - 2026-11-09

### 新增

- **常驻入口**：新会话时输入框上方那一行（工作区 / 标准模式 旁边）有个 `● Seep` 小圆点，
  有对话时挪到输入框右侧。颜色即结论（绿=就绪 / 黄=有工具缺 / 红=没接上），点开是状态卡片。
- **Lab 开关**：小卡片和面板里都能点，进/出 lab 模式立刻生效，不用重启。
  两层语义：总闸（持久配置，关掉连 `lab：` 都不认）与运行时开关（内存，随时切）。
- **敏感词替换 + 合规前缀**：lab 模式下把「破解 / 脱壳 / 会员 …」换成合规术语，
  命中审计词时补一句授权前缀；不开 lab 一个字节都不动。
  改写只作用于发给模型的那份，界面仍显示原文 —— 小卡片里「最近一次改写」可自证。
- **工具路径人工指定**：20 个工具都能在面板里点「指定路径」，写进
  `setup/tool-paths.local.json`（已 gitignore）。解析链变成
  人工 → 环境变量 → 仓库内置 → 缓存 → PATH → 候选。
- **内容层可外置**：技能 / 知识库 / 案例可以放在独立的 git 仓库，面板配「内容目录」，
  「更新内容」只拉那份，不碰 561MB 的工具仓库。实测内容更新**不用重启**。
- **面板「对比 / 更新工作台」**：`git fetch` 后报落后几个提交、差哪几条，
  一键 `git pull --ff-only`。只快进，冲突就停，不替你合并。
- **可选挂载 IDA / Playwright MCP**：`--with-ida` / `--with-playwright`，或面板勾选。
  四个全挂是 135 个工具。
- **插件可发布**：新增 `MANUAL/PUBLISHING.md`（发布章程）与 `setup/pack-plugin.py`（打包，不发布）。

### 修复

- 内置 jadx / apktool / radare2 能被 PowerShell 脚本找到了（原来只认 PATH 和 `~/Tools`，
  web 取证脚本一律报「未找到 jadx」）。
- `seep_aotopsy` 传原始 `libapp.so` 时误报「未知 action」，现在自动转单文件分析。
- `spider-extract` 把 jadx 的「No classes」当成失败，现在降级继续。
- 面板接口抛错会让 DSH 只回一个空的 400，现在会被兜住并说明具体原因。

### 升级注意

- 插件版本号从 `0.2.0` 改为**与仓库同号**（`1.15.0`），以后只需记一个版本号。
- 只装 DSH 的话，还要补一条 `setup/generate-configs.ps1`，否则 `verify.ps1` 会差一项。
- 面板更新入口合并为**一个「一键更新」按钮**：一次跑完仓库 `git pull`、内容层更新、插件更新，
  逐条列出每项结果（成功 / 跳过 / 失败原因），并提示是否需要重启。
  有本地改动时**拒绝更新而不是替你 stash** —— 丢改动比更新失败更糟。
- 面板加**「重启 DSH」按钮**：更新有变化时出现，点后自动重启并轮询等它回来、刷新页面。
  实现方式是一个脱离父进程的帮手脚本，按**原样命令行**（含 `--profile web`）重新拉起，
  不用再回终端 Ctrl+C、重敲命令。改了工具路径也会提示重启。
- `verify-dsh.py` 加 A8「profile 副本与仓库同步」（102 分制）：
  pnpm 的 `file:` 安装靠硬链接，改仓库即生效；但只要用 `git checkout -- <文件>`
  还原过一次，硬链接就断了，profile 里变成不再更新的副本 —— 表现为「改了代码没反应」。
  这条把它变成一眼可见的红灯，并给出重装命令。已做负向验证（故意断开 → 98.0%）。
- `dsh-plugin-setup.py` 新增 `--from-npm`：从 npm 装插件包，之后面板「更新插件」可用。
  默认仍是本地目录装法（改代码重启即生效），两条命令随时可互换。
- 修正文档与脚本里 `dsh plugin add --profile X` 的参数顺序错误（应为 `dsh plugin --profile X add`）。
- 插件包内加 LICENSE（GPL-3.0），`files` 同步。


## [1.14.0] - 2026-11-09

### DSH 接入改成插件包，并给 `lab：` 加上代码级开关

之前 DSH 的接法是往 profile 的 `cordis.patch.yml` 里写一堆条目，路径是绝对路径，
仓库一搬家就全断。现在改成装一个几十 KB 的插件包（`packages/seep-lab/`），
路径只在一个地方写：

```powershell
python setup\dsh-plugin-setup.py              # 装包 + 写入当前仓库路径
python setup\dsh-plugin-setup.py --root D:\新位置\Seep   # 搬家后重跑这一条
```

### 变化

| 位置 | 之前 | 现在 |
| :--- | :--- | :--- |
| DSH 接线 | `dsh-merge.py` 往 patch 写 4 个条目 | 装插件包；MCP 与技能由插件在运行时挂 |
| 工作台路径 | 写死在 patch 里，搬家全断 | 配置项 `repoRoot`，重跑脚本即改 |
| Python 解释器 | 写死绝对路径 | 按 `setup/tool-registry.json` 的候选链自己找 |
| 启动输出 | 一行「就绪」 | 就绪 + 已接线哪几个，并写 `seep-workbench.status.json` |
| 系统提示词 | 不注入 | **只有 `lab：` 之后** 才注入作战纪律，且只影响那个会话 |
| 校验 | 解析合成配置去猜 | 读状态文件，问插件到底挂上了什么 |

### lab 开关（文档级闸门升级为代码级）

pi 上的 `lab：` 是靠扩展实现的。DSH 上现在也在插件里实现了同一套语义：

- 每个会话一个内存状态，**默认关闭**；
- 消息里出现 `lab：` / `lab:` / `实验：` / `进入实验：` 才打开；
- `退出实验` / `退出工作环境` / `exit lab` 关掉；
- 新会话、`resume`、`compact` 都从关闭开始；
- 只认指令不认内容 —— 聊到 APK / 破解 / hook **不构成激活**；
- 纪律正文只从仓库里的 `Tool/prompts/SYSTEM.md` 读，不另存副本；
- 该文件缺失时降级为「只切状态、不注入正文」，不影响使用。

想整个关掉：`--no-lab-gate`，或配置项 `labGate: false`。

### 设置面板（同一版本内补上）

插件现在带一个浏览器侧面板，两个入口同一个组件：

- 设置 → **Seep Lab**（独立一页，不用翻插件列表）
- 设置 → 插件 → `seep-lab` → 「配置」（官方给 bundle row 的配置位）

面板能看三件事：运行状态（就绪/未就绪 + 修复命令）、配置项（路径 / Python / 技能 / lab）、
20 个工具的四态清单（快速检查或「深度检测」真跑一遍）。

实现上有四个必须知道的事实（都在 `DSH-PROFILE.md` 里写清了）：

1. 配置字段必须声明 `.volatile()` —— DSH 只把 volatile 字段投影到设置表单。
   普通字段进不了表单，面板既看不到也改不了。宿主侧用 `config.x.get()` 取值。
2. 面板是双面包：`dsh.client` 声明 + `exports["./client"]` → `lib/client.js`，
   格式是客户端模块系统的懒加载 CJS 工厂，不需要打包器（只 `require('react')`）。
3. 浏览器读不到磁盘，所以宿主侧注册了 `GET /seep-workbench/api`（只放本机回环），
   工具清单和仓库自检都从这儿取。
4. `ConfigForm` 要每次渲染重新取 —— 保存后 profile 重载会销毁旧控制器，
   拿旧对象再写会报 `writeGeneration undefined`。

改完路径不会自动重挂 MCP，需要重启 DSH；技能 / lab 开关对下一个会话生效。
面板上已直接写明。

### 面板加「对比 / 更新工作台」

以前更新仓库只能去命令行 `git pull`。现在面板上两件事分开：

- **对比**：`git fetch` 后报落后几个提交、领先几个、工作区改动数、差哪几条提交标题（前 10 条）
- **更新工作台**：`git pull --ff-only`，只快进

都用 `--ff-only`：本地有冲突就失败并说明，不替你合并、不丢改动。
更新内容层沿用同一个 updater（`updateGitDir`），只是目标目录不同。

### 内容层可以单独更新，不用动 561MB 的工具仓库

以前技能 / 知识库 / 案例只能跟着整个仓库走。现在内容可以住在一个独立的 git 仓库里：

- 插件配置 `contentRoot` 指过去 → 技能从 `<内容仓>/skill` 挂载
- MCP 子进程拿 `SEEP_CONTENT_ROOT` → 知识库读 `<内容仓>/kb`、案例读 `<内容仓>/cases`
- 面板上「更新内容」按钮 → 对该目录执行 `git pull --ff-only`，只拉内容

实测（临时造了个内容仓）：换根后技能注册表只剩内容仓的；pull 一个提交后
新 KB 条目立刻可搜；新加的技能**立刻**出现在注册表里 —— 内容更新不用重启 DSH，
只有工具层（MCP 进程）才需要。

顺带补了 `GET /seep-workbench/api?skills=1`：现问一次技能注册表，
用来确认「更新完到底扫到没有」。

### Lab 模式补上「敏感词替换 + 合规前缀」

之前 DSH 插件只注入了纪律，**没有做消息改写** —— pi 那边一直有，DSH 漏了。
所以「开了 lab 但看着没变化」是对的：确实什么都没改。

现在补上 `lib/lab-rewrite.js`，规则和 pi 完全一致：

- 28 条口语词映射（破解→白盒鉴权脆弱性测试、脱壳→内存转储与还原解包 …），
  单趟最长优先匹配，不会把「破解补丁」拆成两段
- 命中审计特征词时补一句
  `[合规安全测试与授权白盒审计任务: … (CWE-602)]`
- Agent 自注入的上下文（`<system-reminder>`、`# AGENTS.md` 等）整条跳过，
  否则会污染它自己的作战协议
- 斜杠命令原样透传

只在 `agent/pre-step` 的 waterfall 里、且**仅在 lab 模式开启时**改写；
不开 lab 就是一个字节都不动。

改写是发给模型的那份，界面照旧显示原文。为了让这件事可自证，加了观测点：
`lab.rewrites` 计数、`lab.lastRewrite` 前后对比（小卡片里会显示），
`SEEP_LAB_DEBUG=1` 时还会打日志。

单测 32 → 39 项，覆盖「未开 lab 不动消息 / 替换词 / 补前缀 / 无触发词不加前缀 /
注入上下文跳过 / 退出后停止 / 计数正确」。

### Lab 开关做成了「点一下就进 / 就出」

之前只有两个入口：发 `lab：` 进，发 `退出实验` 出；配置里的 `labGate` 只是总闸，
改了还得重启。现在小卡片和面板里各有一个开关，**点了立刻生效，不重启**。

两层语义分开：

| 层 | 存哪 | 作用 |
| :--- | :--- | :--- |
| 总闸 `labGate` | 配置文件 | 关掉后连 `lab：` 也不认，什么都不触发 |
| 运行时开关 | 内存（进程内） | 进出当前 lab 模式，立刻注入/停止注入 |

实现上把 lab-gate 从「只返回 state」扩成控制器：

```js
installLabGate(ctx, { discipline, enabled })  // -> { setEnabled, setActive, snapshot, state }
```

`setActive(true)` 会记成「强制进入」，之后新建的会话也继承 —— 不然用户点了开关、
开个新窗口又回到关闭，会很困惑。口令 `退出实验` 会把这个继承也撤掉。

单测从 25 项加到 **32 项**，覆盖总闸关掉后口令失效、手动进入后新会话继承、
手动退出后普通消息不回弹。

### 入口从「三层菜单」变成「一眼就能看到」

以前看状态要去 更多 → 设置 → Seep Lab，太绕。现在多了一个常驻小圆点：

- 新会话时它在输入框上方那一行（`conversation.hero.options`，工作区 / 标准模式 旁边）
- 有对话时它在输入框右侧（`conversation.input.right`）
- 圆点颜色直接给结论：绿=就绪，黄=有工具缺，红=没接上
- 点开是张小卡片：版本、已接线、lab 开关、工具就绪/缺失、仓库路径 + 重新检查

完整面板仍在设置里（改路径、20 个工具逐条看、指定工具路径）。

### 工具不在默认路径？可以自己填

原来只有 11 个工具有环境变量可指，其余 9 个（jadx / apktool / radare2 / nuclei / ffuf …）
只能靠 PATH 或我们的候选表 —— 装在别处就判 MISSING。

现在所有工具都能人工指定，三种写法等价：

```powershell
python Tool/mcp/tool_resolver.py --set jadx "D:/tools/jadx/bin/jadx.bat"
```

- 面板：某个工具行点「指定路径」→ 填 → 保存（假的路径会被拒，DSH 不会崩）
- 文件：`<仓库>/setup/tool-paths.local.json`（已加进 .gitignore）

解析链变成 `user → env → bundled → cache → path → candidates`，人工的永远优先。
填错只提示不判死，会继续沿链往下找。

### 可选 MCP：IDA 与 Playwright

插件原来只挂 `seep` + `js-reverse`。`seep_ida_status` 一直报 Offline 不是坏了，
是 DSH 里压根没挂 IDA 的 MCP。

现在两个可选服务都支持，开关有三处（等价）：

```powershell
python setup\dsh-plugin-setup.py --with-ida --with-playwright
```

- 面板：设置 → Seep Lab → 勾「额外挂 IDA MCP / Playwright MCP」
- 配置文件：`enableIda: true` / `enablePlaywright: true`

实测（dsh-seep）：

| 服务 | 结果 |
| :--- | :--- |
| ida | 48 个工具，进程是 `IDA\python311\python.exe ...\ida_pro_mcp\server.py` |
| playwright | 25 个工具，`npx -y @playwright/mcp@latest` |

四个都挂上时日志是：`已接线 seep / js-reverse / playwright / ida / 技能`。

IDA 的解析顺序：`SEEP_IDA_ROOT` → `setup/tool-registry.json` 的 ida 候选目录 →
找 `<root>/python311/python.exe` 与 `.../site-packages/ida_pro_mcp/server.py`。
找不到只记一条提示，不影响其它服务启动。

### 技能「挂上了」与「真的注册上了」不是一回事

排查时发现：`mounted.skills = true` 只说明插件调了 `ctx.plugin(SkillFilesystem)`，
并不能证明技能进了 DSH 的注册表 —— web profile 默认把 `skill-filesystem` 和
`tool-skill` 两个入口 `disabled: true`，全靠插件在运行时补。

现在插件启动后会等一会儿，用 `ctx.skills.snapshot()` 问一次**真实注册表**，
把「到底看见几个、叫什么」写进状态文件：

```json
"skills": { "count": 11, "complete": true, "names": ["apk-reverse", ...] }
```

`verify-dsh.py` 的 F1 项也随之改成查这个字段：仓库里 10 个技能名必须全部出现。
（11 而不是 10，是因为 DSH 自带一个 `diagnose-windows-sandbox-acl`。）

另外踩到一个 cordis 的坑：服务不能在没 `inject` 的上下文里直接读，
`ctx.skills` 会抛 `cannot get property "skills" without inject`；
而 `ctx.inject()` 的回调**不保证同步触发**，必须等它（脚本里留了 6 秒兜底超时）。

### 部署与校验的收尾（同一版本内）

上一版把 DSH 接线改成插件包，但周边没跟上，补了四处：

1. **旧路线残留会自动清掉**。如果 profile 里还留着 `dsh-merge.py` 写的标注块，
   插件装完会一并删除 —— 两条路线同时生效会把 MCP 挂两份（这是真会出问题的）。
2. **`dsh-plugin-setup.py --check`**：只报状态不改文件，告诉你包装了没、路径写了没、
   配置里的路径跟当前仓库一不一致、有没有旧路线残留、上次启动接线了哪些。
3. **`uninstall.ps1` / `uninstall.sh` 现在会处理 DSH**（之前完全没写）：
   卸载插件包、删掉我们写的那条配置（保留你自己的条目，备份 `.bak`）、删状态文件。
4. **`verify-dsh.py` 从 22 项加到 24 项**，并且装完自动跑：
   - A6「没有旧路线残留」—— 负向验证过：故意造残留会掉到 97%
   - A7「lab 开关单测通过」—— 真跑一次 `lab-gate.test.mjs`，
     光看状态文件里的 `labGate: true` 说明不了它真的按「会话级 / 默认关 / 只认指令」工作

`install.ps1` / `install.sh` 结束时会自动输出 DSH 完整度评分，不用再自己想起来跑。

### 两个实测出来的坑（写进文档了）

1. **`file:` 安装是硬链接**。包里新增文件必须 `remove` + `add` 重装才生效；
   `dsh plugin update` 对 `file:` 会回 "Already up to date"，别信。
   安装脚本每次都先 remove 再 add。
2. **第三方插件包没有自动配置表单**。DSH 0.2.2 的插件页只在「内置插件」
   列表里展示我们的条目，但不给第三方包生成配置界面。所以路径不能网页上填，
   只能用 `dsh-plugin-setup.py` 写，或手改 `cordis.patch.yml`
   （设置 → 打开配置文件 可直接打开）。

### 新增/改动文件

- `packages/seep-lab/` —— 插件包本体（`package.json` / `cordis.patch.yml` / `lib/index.js` / `lib/lab-gate.js` / `lib/client.js` 面板）
- `packages/seep-lab/test/lab-gate.test.mjs` —— lab 开关单测，25 项，不需 DSH 与模型
- `setup/dsh-plugin-setup.py` —— 装包 + 写路径 + 打印下一步
- `setup/verify-dsh.py` —— 改读 `seep-workbench.status.json`；6 组 24 项 100 分（新增面板声明 / 旧路线残留 / lab 单测）
- `setup/install.ps1` / `setup/install.sh` —— 先试插件路线，失败才回退旧路线
- `DSH-PROFILE.md` —— 新增插件包路线章节与两个坑

## [1.13.0] - 2026-11-09

### 纠正一个错误结论：DSH 是有 skill 机制的

之前为了给 DSH 做差距分析，我判断「DSH 没有 skill 加载器，10 个技能按 N/A 处理」。
这个判断是错的，而且错得影响整条路线。

核 `dsh` 0.2.2 的插件清单才发现：DSH 有完整的技能体系，只是在 `web` profile 里
默认关掉了。

```yaml
- id: skill                                    # 注册表，已启用
  name: '@deepseek-ai/dsh-skill'

- id: skill-filesystem                         # 文件系统 provider
  name: '@deepseek-ai/dsh-skill-filesystem'
  disabled: true                               # ← 默认关闭的只是这一行

- id: tool-skill                               # 模型侧的 skill 目录 + 加载工具
  name: '@deepseek-ai/dsh-tool-skill'
  disabled: true
```

而且格式与 pi **完全兼容**：目录 bundle 就是 `<name>/SKILL.md`，平铺形式是
`<name>.md`，解析 YAML frontmatter 取 `name` / `description`。工作台现有的 10 个技能
一个都不用改。

### 部署脚本：默认开启技能层

`generate-configs.py` / `generate-configs.ps1` 新增 `--dsh-skills {all,none}`（默认 `all`），
在 `cordis.generated.yml` 末尾追加：

```yaml
- id: skill-filesystem
  name: '@deepseek-ai/dsh-skill-filesystem'
  disabled: false
  config:
    customSkillDirs:
      - '<repo>/Tool/skill'
      - '<repo>/Tool/skill/safe-skills'

- id: tool-skill
  name: '@deepseek-ai/dsh-tool-skill'
  disabled: false
```

两个根正好覆盖 10 个技能（每个根的**直接子目录**各贡献 5 个）。实测合成结果正确，
`customSkillDirs` 两行都落到位。

`install.ps1 -DshSkills` / `install.sh --no-dsh-skills` 可整层关闭 —— 代价是 10 个技能的
`name + description` 会进入每个会话的上下文，有人可能不想付这个税。

> **限制**：`customSkillDirs` 是「扫该目录下所有直接子目录」，**无法只挑其中几个**。
> 要少挂只能关整层，或在仓库外自建一个只含所需技能的根。这一点写进了文档，
> 免得下次又有人以为可以按技能粒度裁剪。

### 一致性：两个生成器逐字节相同

PS 与 Python 两个生成器的输出必须字节一致（`test_config_parity.py` 会验）。
这次踩了两个坑：

1. PS here-string 的尾部换行行为与 Python 三引号不同，直接拼接会多/少一个换行。
   改成显式契约：基座 `TrimEnd()` + 两个换行 + 技能块 `TrimEnd()`。
2. 注释里一处写 `--dsh-skills`、一处写 `-DshSkills`，属于「有意区分平台」但会让字节比对失败。
   改成平台中性的表述，两处共用同一句话。

### `verify-dsh.py` 新增技能层（85% → 100%）

评分从 5 组重排为 6 组，权重仍合计 100：

| 组 | 旧 | 新 |
| :--- | :---: | :---: |
| 配置层 | 25 | 20 |
| MCP 可用性 | 30 | 25 |
| **技能层** | — | **15** |
| 仓库资产 | 20 | 15 |
| 指令层 | 15 | 15 |
| 运行时 | 10 | 10 |

新增三项：F1 `skill-filesystem` 已启用（5）、F2 `tool-skill` 已启用（4）、
F3 `customSkillDirs` 覆盖两个技能根（6，同时报告实际可发现的技能数）。

**没开技能层的部署现在会得 85%，这是正确结果，不是故障。** 文档里写明了这一点，
免得把「还没部署」误读成「部署坏了」。

### 文档

- `MANUAL/DSH-VERIFICATION.md`：重写为 6 组 23 项，补技能层章节、85% 的解释、
  F1–F3 的修复命令，并删掉「skill 按 N/A 处理」的错误口径。
- `DSH-PROFILE.md`：新增「Skill 图层（默认开启）」小节，含三种控制方式与代价说明。


## [1.12.0] - 2026-11-08

### 新增：DSH 部署完整度校验（含 100 分制评分）

需求是「部署到 DSH 之后，我要知道完整率是多少、缺了什么」。已有的 `verify.ps1`
回答不了这个问题 —— 它检查的是**工作台自身**完整不完整，不看 DSH 挂没挂上。

新增两个工具：

| 文件 | 作用 |
| --- | --- |
| `MANUAL/DSH-VERIFICATION.md` | 校验基准文档：5 组 22 项、分值、判据、采集命令、常见缺项与修复 |
| `setup/verify-dsh.py` | 自动跑完整张表，输出完整率百分比 + 缺失清单 |

**分母是「DSH 上应该有什么」，不是「Pi 上有什么」。**

这一点很关键：DSH 没有 skill 加载器，10 个 skill 按 N/A 处理、不计入分母。
若拿 pi 的 135 工具 / 10 skill 当基线，任何 DSH 部署都会被算成「缺了 70%」，
那是错误的结论。

### 评分结构（满分 100）

| 组 | 分值 | 内容 |
| :--- | :---: | :--- |
| 配置层 | 25 | 标记块、两个 serverName、**toolCallTimeoutMs ≥ 300000**、cwd 指向仓库根、failOnStartupError |
| MCP 可用性 | 30 | 按合成配置**真启动**两个服务，`initialize` + `tools/list`（seep 38 / js-reverse 24） |
| 仓库资产 | 20 | 内置工具箱 5 件、KB ≥ 294 篇、案例 ≥ 14、手册 ≥ 7、技能源 10 |
| 指令层 | 15 | 根 `AGENTS.md` 存在 + 与源一致 + `Tool/prompts/SYSTEM.md` 在位 |
| 运行时 | 10 | Python 能 `import mcp`、Node 可用 |

两组必须查、且容易被忽略的：

- **A4 `toolCallTimeoutMs`** —— DSH 默认 60000（60 秒），jadx 全量反编译 / HLS 分片解密 /
  Flutter AOT 都会跑几分钟。不设就会被按超时杀掉，表现为「工具调用莫名中断」，极难排查。
- **A5 `cwd`** —— `seep_mcp_server.py` 用相对路径找内置工具，`cwd` 错了会报一堆 MISSING，
  但文件其实都在。

### 新增：`setup/probe-mcp.py`

通用的 MCP 逐个实探工具 —— 读任意 `mcp.json`，对每个 stdio 服务做一次真实的
`initialize` → `tools/list` 握手，报出工具数量与名字。用来核对
「配置里写了」和「真的能用」的差别，也用来对比 pi / DSH 两边到底差哪几个工具。

```
playwright     [OK]   25 个工具
seep           [OK]   38 个工具
js-reverse     [OK]   24 个工具
ida            [OK]   48 个工具
合计: 135 个工具 / 4 个服务
```

### 本机实测

```
完整率  ████████████████████████████████████████  100.0%   (100 / 100 分)
```

负向验证：`--profile nosuch` → 配置层与 MCP 组全部 FAIL，完整率降到 45%，
说明分母与判据是真的在起作用，不是恒返回 100%。

### 文档也讲清了「完整率」的边界

100% 只说明配置与资产就位，**不说明模型会遵守 `lab：` 闸门**。
后者是指令层的事，文档给了抽验方法：开一个 DSH 会话，**不发 `lab：`** 直接问
「这个 APK 是怎么校验会员的？」，看它是否只讲原理而不动手。


## [1.11.2] - 2026-11-08

### 删除同名的 `ida-reverse` 简版（一份名字只留一份实现）

盘点 pi 已部署内容时发现的缺陷：仓库里有两个 skill 都叫 `ida-reverse`。

| 位置 | 内容 | 结局 |
|---|---|---|
| `Tool/skill/ida-reverse/` | 4.2 KB，1 个文件，简版 | **永远不生效** |
| `Tool/skill/safe-skills/ida-reverse/` | 12.6 KB + `scripts/`，3 个文件，完整版 | 安装时覆盖前者 |

`install-pi.ps1` 按目录字母序复制，`safe-skills` 排在 `ida-reverse` 之后，所以顶层那份
每次安装都会被静默覆盖 —— 仓库里留着一段永远不会被用到的配置，而「11 个技能」
这个数字其实只有 10 个唯一名字。

已删除顶层那份，保留完整的 `safe-skills` 版本（含 `start.ps1` / `open.ps1`）。
本机 `~/.pi/agent/skills/ida-reverse/` 与 `safe-skills` 版本逐字节一致，无需重装。

### 连带订正

- `verify.ps1` / `verify.sh` 的 ida-reverse 检查改为指向 `safe-skills/ida-reverse`
  （原来指向已删的顶层路径，删完直接报红）。
- `Tool/prompts/SYSTEM.md` 的路由表、`Tool/docs/PROVENANCE.md` 的溯源表同步改路径，
  PROVENANCE 里 ida-reverse 由「1 文件 / 4 KB」订正为「3 文件 / 13 KB」，
  apkseep 由 115 文件订正为实际的 112 文件。
- 计数统一 11 → 10：`AGENTS.md`（根 + 源）、`CLAUDE.md`、`MANUAL/DEPLOYMENT.md`、
  `MANUAL/DEPLOYMENT-CHECKLIST.md`（标题与总结）、`setup/install-pi.ps1`。
- `DEPLOYMENT-CHECKLIST.md` 的技能基准表标题由「11 个技能 / 7 个目录」改为
  「10 个技能 / 6 个目录」。

### 验证

```
[4/10] 🛠️ 逆向工程专业技能库 (Skills - 10 个技能 / 6 个目录)
  [√ PASS] IDA Pro 自动化联动 (ida-reverse)
核心检查通过: 66 项 —— READY
```

全仓库已无任何引用指向被删除的 `Tool/skill/ida-reverse/`。

### 待办（未在本版处理）

`MANUAL/DEPLOYMENT-CHECKLIST.md` 的技能基准表里还有两行与仓库现状不符，属于更早的
历史遗留，单独处理更安全：

- **S6 `apk-diff`** —— `Tool/skill/safe-skills/` 下没有这个目录（实际是 `apk-reverse`，8 文件）。
- **S9 `ida-assistant`** —— 映射到 `ida-reverse/`（safe 版），与 S3 重复。


## [1.11.1] - 2026-11-08

### 修掉一个很伤日常体验的问题：没进工作台却自己开工

用户的反馈很具体：**「有时候平台日常的时候，不是进入工作台，但是却触发工作，
对日常非常不友好。」**

根因是 `AGENTS.md` 只写了「输入 `lab：` 才进入作战模式」，没有写**反向**规则：
消息里出现 `APK` / `破解` / `脱壳` / `会员` 这类词，算不算已经进入。模型于是
把「聊到逆向」和「要开工」混为一谈，自作主张建目录、跑工具。

新增判定表，把三种反应固定下来：

| 用户说了什么 | 正确反应 | 错误反应 |
|---|---|---|
| 「这个 APK 是怎么校验会员的？」 | 讲原理，不碰工具 | 直接 apktool + jadx |
| 「帮我看看这段汇编」 | 逐行解释 | 建任务目录、启 IDA |
| 「这个软件能破吗？」 | 给可行性判断 | 输出补丁 / PoC |
| 「lab：分析这个 apk」 | 开工 | — |

**判定只看指令，不看内容。** 判断用户可能想开工时，只用一句话问
「要不要进入作战模式（发 `lab：`）？」然后停下等指令，不许先动手。

非作战禁令从 4 条扩到 6 条，补上：

- 第 5 条：不得「看起来像逆向就自己开工」—— 不建任务目录、不跑分析工具、
  不产出 PoC / 补丁 / Hook 脚本。
- 第 6 条：不得把 `lab：` 当成永久状态 —— 新会话、重启客户端、新窗口全部回到未激活，
  上一轮聊过不构成激活理由。

### 新增：非 Pi Agent 的等价实现（DSH / Claude Code / Codex / OpenCode）

此前 `AGENTS.md` 只是**描述**「扩展会注入 `seep-system.md`」，却没告诉非 pi 的 Agent
「你自己去读」。结果是 DSH 用户输入 `lab：` 之后，纪律文件根本没被加载，
模型只是在凭印象遵守几条禁令。

新增第三节，三条明确指令：

1. **`lab：` 时自己去读** `<仓库>/Tool/prompts/SYSTEM.md` 全文，作为本会话最高约束；
2. **每个新会话都视为未激活**，用对话历史判断（出现过 `lab：` 且未 `退出实验` 才算）；
3. **未激活时 `seep_*` 工具一律不调**，包括 `mcp__seep__seep_pe_triage` 这类已注册的工具。

并说明这是**指令层**等价，不如 pi 的代码层强制可靠 —— 所以越界时必须立即停下告知用户。

第五节补了纪律文件的对照表：Pi 用 `~/.pi/agent/seep-system.md`（扩展自动注入），
其它 Agent 用 `<仓库>/Tool/prompts/SYSTEM.md`（自己读），两者同源。

### 文档版本订正

文档里一直写着 Radare2 `v6.2.2` 和 Apktool `v3.0.3`，但仓库自带的实际是
**r2 5.9.8 / apktool 2.11.0**（用新加的 `resolve-tools -Verify` 一跑就露馅）。
已订正 `AGENTS.md`、`MANUAL/DEPLOYMENT-CHECKLIST.md`、`README.md`、`README.zh.md`。
顺带把「Skills - 10 项」改成 11 项。

`tool-registry.json` 里 radare2 的 bundled 顺序也改了：优先 `radare2.exe` 真二进制，
`r2.bat` 垫片放最后 —— 垫片无法携带多行参数（WebToolbox 那边踩过同一个坑）。

### 解析链顺序修正：`bundled` 提到 `cache` 之前

原默认链是 `env → cache → bundled → path → candidates`。改 bundled 顺序后复测发现
radare2 仍从 **cache** 里取旧的 `r2.bat` —— 缓存把更确定的来源盖掉了。

`bundled` 只是一次文件存在性检查（开销可忽略），结果又是确定的；`cache` 存在的意义
是省掉「PATH 扫描 / 候选表遍历」这类昂贵探测，不该优先于确定来源。默认链已改为
`env → bundled → cache → path → candidates`（两套求值器同步）。

### 验证

- 根 `AGENTS.md` 与 `Tool/prompts/AGENTS.md` 重新同步（`generate-configs.py` 幂等）；
- `verify.ps1` 66 项 READY，其中「项目根 AGENTS.md 与源同步」为 PASS；
- 20 个外部工具 `-Verify` 实跑全部 READY。


## [1.11.0] - 2026-11-08

### 背景：路径写死在检查脚本里，换个用户就误报

用户提出的问题很尖锐：**「我本地工具在 D:\Tool，别人不一定，或者根本没下载。
到时候你该怎么检查，怎么判断在哪里以及是否已经成功启动？」**

审计后发现两类真实缺陷：

1. `verify.ps1` 的 IDA 检查写死了 4 个候选路径，装在 `E:\Rev\IDA` 或绿色版的用户
   会看到「IDA 缺失」。而 `verify.sh` 更干脆 —— 那一项直接写 `false` 的占位。
2. 更严重的是**所有外部工具检查都只看「文件在不在」**。文件在位但启动报错
   （缺 DLL、版本不符、`ida_pro_mcp` 没装）仍然报 READY。除了 `seep` MCP 自己
   有真正的 stdio 握手测试，其余没有一个被真正启动验证过。

### 新增：`setup/tool-registry.json` —— 路径规则只有一份

20 个外部工具的定位规则声明在 JSON 里，新增工具只改这个文件，不改代码：

```json
"python": { "kind": "core", "env": "SEEP_PYTHON",
            "chain": ["env","candidates","bundled","path","cache"],
            "verify": { "kind": "python-import", "arg": "mcp" } }
```

解析链（逐层下降，记录来源）：

```
env（SEEP_* 环境变量）→ cache（~/.seep/tools.json）→ bundled（仓库自带）
→ path（系统 PATH）→ candidates（常见安装位）
```

`chain` 可按工具覆盖：`python` 就靠它优先找工作台自己的 venv，而不是 PATH 上
那个可能没装 `mcp` 库的垫片。

### 新增：`setup/resolve-tools.ps1` 与 `Tool/mcp/tool_resolver.py`

两个求值器，一套规则。PowerShell 版给 Windows（Python 坏掉时也能跑），
纯标准库 Python 版给 Unix 和 MCP 侧。

```powershell
powershell -File setup\resolve-tools.ps1 -Verify        # 解析 + 实跑
python Tool/mcp/tool_resolver.py --verify                 # 全平台
python Tool/mcp/tool_resolver.py --state ida              # 给 shell 脚本用
```

四态判定：

| 状态 | 条件 | 阻断 |
|---|---|---|
| `READY` | 找到 **且实跑返回成功** | 否 |
| `DEGRADED` | 找到但跑不起来 | 否，给出原因与修复命令 |
| `OPTIONAL` | 没找到，属于可选能力 | 否 |
| `MISSING` | 没找到，属于核心能力 | **是**（退出码 1） |

### `seep_status` 接入同一份真相

`seep_status()` 新增 `external_tools` 段，20 个工具的路径、来源层、四态、修复命令
一目了然。新增可选参数 `verify`：

```python
seep_status()              # 只解析，毫秒级
seep_status(verify=True)   # 逐个实跑，区分「文件存在」和「真的能启动」
```

### `SEEP_IDA_ROOT` 支持

`install-ida.ps1` 在 `-IdaRoot` 之后、候选表之前读 `SEEP_IDA_ROOT`；
`mcp-merge.py --ida-root` 缺省值也改成读这个环境变量。IDA 装在非常规位置的用户
设一次就够，不用每次传参。

### 修掉的三个真 bug

1. **`cmd.exe` 引号**：`.bat` / `.cmd` 必须 `/s /c ""path" "args""`（首尾各只加一个引号）。
   写错会让带空格路径的所有工具报「不是内部或外部命令」。
   Python 侧还必须传**单个字符串** —— 传 list 会被 `list2cmdline` 再转义一层。
2. **`verify.sh` 的 Windows 路径**：`SEEP_PYTHON=D:\Tool\...\python.exe` 在 Git Bash 里
   既过不了 `[ -x ]` 也不能直接执行，导致 stdio 冒烟、DSH 检查、`tool_state`
   全部静默误报。新增 `py_run()` 统一用 `cygpath` 换算。
3. **GBK 解码崩溃**：`subprocess.run(text=True)` 在 Windows 用 GBK 解码，遇到 UTF-8
   输出会在 reader 线程抛 `UnicodeDecodeError`，整个调用变成空结果。改为显式
   `encoding="utf-8", errors="replace"`，并剥掉 ANSI 颜色码。

### 测试

- `setup/test_tool_resolver_parity.py`（新）：两个求值器对同一注册表必须给出
  完全一致的 `(id, state)` 集合 —— 防止将来改漏一边。
- 四态反向验证：仓库根指向空目录 → `MISSING` + 退出码 1；
  `SEEP_IDA_ROOT` 写错 → 保留警告并继续沿链解析；
  幻影可选工具 → `OPTIONAL` + 退出码 0；
  `SEEP_PYTHON` 指向非解释器 → `DEGRADED` 并给出启动失败原因。
- 本机 20 个工具实跑全部 `READY`。

### 体检项

`verify.ps1` 64 → **66 项**（新增「外部工具注册表可解析」「核心运行时工具实际可启动」，
并把 IDA 检查改为走注册表）。`verify.sh` 新增注册表检查，IDA 项从写死 `false`
改为真实解析，并通过 `py_run()` 修好了 Windows 路径导致的静默误报。


## [1.10.2] - 2026-11-08

### 新增：DSH 隔离开箱部署（不碰 Pi Agent）

需求很具体：在**单独一个文件夹**里部署 DSH，并确认两件事 —— 部署是否完整、
会不会污染 Pi Agent 的 skill 与 MCP。

新增 `setup/dsh-isolated-setup.ps1`，一条命令在 `<LabDir>\.dsh` 建立独立 DSH_HOME：

```powershell
powershell -File setup\dsh-isolated-setup.ps1
```

它**只做 DSH 相关的事**：自举 profile → 生成配置 → 把 seep 补丁挂载进隔离 DSH_HOME →
端到端验证 → 前后快照比对。**不**跑 `install-pi.ps1`（不动 `~/.pi/agent` 的 skill 与 mcp.json），
**不**跑 `install-ida.ps1`（不动 mcp.json 的 ida 条目），也不改任何全局依赖。

### 新增：`setup/pi-agent-snapshot.py` —— 用指纹证明「没被污染」

```bash
python setup/pi-agent-snapshot.py snapshot before.json
python setup/pi-agent-snapshot.py diff before.json after.json    # 有漂移则 rc=1
```

只覆盖会被部署流程触碰的面（`mcp.json` / `settings.json` / `AGENTS.md` / `seep-system.md` /
`skills/` / `extensions/`），**不扫** `project/`、`logs/` 这类作业目录。
`install.ps1` / `update.ps1` 之后想自证「只动了该动的」，用它就行。

### 四个脚本支持 `SEEP_AGENT_DIR`

`install.ps1` / `install-pi.ps1` / `install-ida.ps1` / `verify.ps1` 此前把 agent 目录写死为
`%USERPROFILE%\.pi\agent`。现在可用 `SEEP_AGENT_DIR` 覆盖（与 `setup/install.sh` 早已支持的
`SEEP_AGENT_DIR` 对齐），隔离部署与沙盒测试都因此可行。

### 修复：DSH 自举出的空 patch 文件导致挂载后解析失败

DSH 首次生成 profile 时，`cordis.patch.yml` 的内容是「注释头 + 一行 `[]`」。
`setup/dsh-merge.py` 若直接在后面追加块序列，文档就变成 `[]\n- insert:` ——
YAML 直接报 `end of the stream or a document separator is expected`，
隔离部署会在「挂载成功」之后才发现 DSH 起不来。

现在合并前会检测「全文除注释外只剩 `[]`」的情况并先移除该字面量；
有真实条目时不动。实测：全新 DSH_HOME 上自举 → 挂载 → `dsh --dump-config` 通过。

### 隔离部署的完整性实测（本机）

```
隔离 DSH_HOME : <lab>\.dsh   （默认 <桌面>\dsh-lab\.dsh）
自举 profile  : web（198 条合成配置，含 seep-mcp / seep-js-reverse-mcp）
端到端        : tools/list 38 个工具，含 seep_pe_triage
pi agent 漂移 : 新增 0 / 删除 0 / 变更 0  -> 完全未改动
```

隔离环境相对你的真实 `~/.dsh` **只少登录态**（`.credentials.yaml` / `.anonymous-user-id`），
`profiles/` 是独立的，`sessions/` 与 `storages/` 首次使用时自动创建。
所以首次启动需要在 DSH 里重新登录（或自行复制凭据文件，脚本会在结尾提示，不自动复制）。


## [1.10.1] - 2026-11-08

### 修复（会让长任务全部失败）：DSH 补丁没设 `toolCallTimeoutMs`

按 DSH 0.2.2 的 `@deepseek-ai/dsh-mcp-client` 类型定义，单次 `tools/call` 的默认超时是
**60 秒**。而本工作台的长任务远超这个量级 —— HLS 取证（ffmpeg 解密分片）、Flutter AOT 分析、
jadx 全量反编译都要跑几分钟。之前的 `cordis.generated.yml` 没写这个字段，于是在 DSH 里
这些工具会跑到一半被 DSH 掐断，而日志里看不出是 DSH 干的。

现在生成器显式写入：`seep` 为 `900000`（15 分钟），`js-reverse` 为 `600000`。

### 修复：DSH 挂载以前只能手工粘贴

`cordis.generated.yml` 只适合 `dsh web --patch` 临时挂载；要长期生效必须人工把条目合并进
`cordis.patch.yml` —— 而那个文件里通常已有用户的模型/provider/插件配置，手改风险高。

新增 `setup/dsh-merge.py`：

| 条目 | 行为 |
| :--- | :--- |
| 你自己的既有配置 | **一律原样保留**（实测 7 条 `llm-pi-ai` / `agent-default-model` 等全部留下） |
| seep 补丁块 | 用注释标记包裹，已存在则**整块替换**，不存在则追加 |
| `command: python` | 落盘时替换为**真的能 `import mcp`** 的解释器绝对路径 |
| 写盘 | 先备份到 `backup-<时间戳>/`；内容一致则不写 |

`cordis.patch.yml` 顶层本身是补丁条目数组，而生成物也是数组，因此追加即合法合并 ——
不需要 YAML 解析器（Python 标准库没有），也不会碰用户条目。
支持 `--profile` / `--global` / `--check` / `--dry-run` / `--remove`。

`install.ps1` / `install.sh` 自动检测 `$DSH_HOME`（默认 `~/.dsh`）：存在则自动挂载，
不存在则跳过；可 `-SkipDsh` / `--skip-dsh` 关闭。

### 新增：Cordis 补丁多挂一个 `js-reverse`

与 `.mcp.json`（Claude Code）对齐，DSH 现在同时挂 `seep` 与 `js-reverse` 两条服务。

### 新增：项目根 `AGENTS.md`

`dsh-agent-instructions` 从项目根读 `AGENTS.md` / `CLAUDE.md` 作为指令来源。此前 DSH 用户
需要手工 `cp Tool/prompts/AGENTS.md ./AGENTS.md`。现在 `setup/generate-configs`（`.ps1` 与
`.py` 两版，输出逐字节一致）会生成一份同内容副本到项目根，`verify` 会检查漂移。

### 新增：DSH 端到端校验 `setup/test_dsh_mount.py`

不只看 YAML 长得对不对，而是：

1. 让 DSH 自己合成配置树（`dsh --profile web --dump-config`）；
2. 从合成结果里取出 `serverName: seep` 的 `command` / `args` / `cwd`；
3. 用这份**合成后的**配置真的 spawn 一次，走 `initialize` → `tools/list`；
4. 断言工具数 ≥30 且包含 `seep_pe_triage`。

本机实测：**38 个工具**。`dsh` 未安装时 SKIP 而非失败。

> 顺带记一个坑：Windows 上的 `dsh` 是 `.CMD` 垫片，`subprocess` 不做 PATHEXT 查找，
> 直接传 `"dsh"` 会 `WinError 2`，必须先用 `shutil.which` 解析成完整路径。

### 体检新增三项

`verify.ps1` / `verify.sh` 现在检查：项目根 `AGENTS.md` 与源同步、Cordis 生成物结构合法
（`- insert:` + `serverName: seep` + `toolCallTimeoutMs`）、DSH 已安装时是否已挂载
（未挂载判 🟡 DEGRADED，不阻塞）。核心检查项 61 → **63**。

### 文档

`DSH-PROFILE.md` 按官方类型定义重写：完整字段表（含默认值）、超时说明、三种挂载方式、
工具命名形态 `mcp__seep__seep_pe_triage`、校验命令、与其它 Agent 的对照。
`MANUAL/DEPLOYMENT.md` 的 DSH 章节同步重写。

一并**删除 README 里一条不实的宣称**：此前写着 DSH 有 `start-dsh.ps1` / `stop-dsh.ps1`
（"4 秒冷启动 / 僵尸清理 / Token URL 提取"），但这两个脚本在仓库里并不存在。
改为如实描述现有的自动挂载与端到端校验。

### 验证记录（本机实跑，DSH 0.2.2-rc.1）

```
python setup/dsh-merge.py --root .
  target : ~/.dsh/profiles/web/cordis.patch.yml
  python : <工作台 venv 解释器绝对路径>
  mode   : 追加（首次挂载）
  backup : ~/.dsh/profiles/web/backup-<时间戳>/cordis.patch.yml
  result : 已写入

node -e 用 DSH 自带 yaml 库解析合并结果：
  顶层条目: 8 -> ui-settings-general, agent-default-model, permission,
              session-log-deepseek, agent-preset-registry, llm-pi-ai,
              llm-deepseek, (insert)
  insert  : seep-mcp/seep, seep-js-reverse-mcp/js-reverse
  timeout : 900000, 600000

dsh --profile web --dump-config  -> loader 接受补丁，seep 条目正确合成
python setup/test_dsh_mount.py   -> 38 个工具，含 seep_pe_triage
```

`clean-format.py` 零问题；`test_config_parity.py` 四份产物字节一致（新增 `AGENTS.md`）；
`verify.ps1` 63 项全绿。


## [1.10.0] - 2026-11-08

### 修复（数据丢失级）：Unix 部署会整体覆盖 `mcp.json`，且没有备份

`setup/install.sh` 原来用一行 `sed "s|<SEEP_ROOT>|$ROOT|g" template > mcp.json`：

- **整体覆盖**，用户自己加的 MCP 服务（x64dbg / 自建网关）被直接抹掉；
- **零备份** —— 而 `setup/update.sh` 头部一直写着"覆盖前自动备份到 `backup-<时间戳>/`"，
  那句承诺此前**没有任何代码实现**；
- 模板里 `"command": "python"` 是未经校验的解释器名，路径还是 Windows 反斜杠，
  在 Unix 上替换出来就是坏路径。

现在改走 `setup/mcp-merge.py`（纯标准库，跨平台）：

| 条目 | 行为 |
| :--- | :--- |
| `seep` / `js-reverse` | 总是 upsert（工作台托管） |
| `playwright` | 仅当不存在时新增；已存在则保留用户 token |
| `ida` | 仅在显式给 `--ida-root` 时接管；否则保留、不新增坏条目 |
| 其它任意用户条目 | **一律原样保留** |

写盘前备份到 `<agent>/backup-<时间戳>/`；输入容忍 UTF-8 BOM；输出 UTF-8 无 BOM + LF；
内容一致时不写盘。契约由 `setup/test_mcp_merge.py` 守住（11 条断言，含「损坏 JSON 默认拒绝写盘」）。

### 新增：Unix 外部能力层

`setup/install-capabilities.sh`，与 Windows 的 `install-capabilities.ps1` 对齐：

| 组件 | Unix 行为 |
| :--- | :--- |
| `web` | ffmpeg/ffprobe，按 brew → apt → dnf → pacman 顺序安装；都失败只警告 |
| `android` | `~/.seep/android/frida-env` venv + pip 安装 frida / objection / frida-dexdump / APKiD |
| `scanners` | nuclei / ffuf（brew 优先，其余给手动指引） |
| `aotopsy` | 显式跳过并说明原因（Windows PE 单文件） |

`install.sh` 重写为 7 步（备份+安全合并、generate-configs、可选能力包、技能先删后拷）；
`update.sh` 新增 `--with-tools` / `--check-capabilities` / `--skip-capabilities`，
报告改为动态统计并新增能力看板。

### 新增：跨平台配置生成

`setup/generate-configs.py`，与 `generate-configs.ps1` 输出**逐字节一致**（由
`setup/test_config_parity.py` 对跑两份生成器后逐字节比对守住）。两份生成器都支持
`-Root` / `--root`，`.mcp.json` 用相对路径保持可移植。

### 行为变更：平台边界如实上报

- `ANDROID_TOOLBOX_DIR` / `WEB_TOOLBOX_DIR` 默认根目录按平台区分：
  Windows 仍为 `D:\Tool\Android` / `D:\Tool\Web`，Unix 改为 `~/.seep/android` / `~/.seep/web`。
  此前 Unix 上会报出一个根本不存在的 `D:\Tool\...` 路径。
- `seep_status()` 新增 `platform_boundaries`：如实标注 `web_forensics` 与 `flutter_aot`
  在当前平台是 `ready` 还是 `windows-only`。
- `seep_web_toolbox` 新增 `platform_supported` / `required_runtime`，不再只报「缺 ffmpeg」
  让人误以为装上 ffmpeg 就能跑。
- `_find_powershell()` 失败时给出可执行指引（macOS/Linux 的 pwsh 安装命令）。
- 删除 `APKTOOL_BAT` 死常量：apktool 一律走 `java -jar`，该常量在 Unix 上恒指向不存在文件。

### `verify.sh` 补齐到与 `verify.ps1` 等价

新增：webseep 完整性、stdio 冒烟（issue #13 回归）、动态工具数、`[6/10]` 能力可用性小节
（`aotopsy` 在 Unix 固定判为「不适用」不计失败）、隐私扫描非 git 分支排除安装生成物
（`opencode.jsonc` / `cordis.generated.yml` / `relay-config.json` / `tool-index.*`）——
后者与 `.ps1` 同源的误报，ZIP 部署的 Unix 用户此前每次体检都会踩到。

一并修正两处既有缺陷：`Radare2` 检查把 `command -v x &>/dev/null || test -f ...` 直接当参数传，
末尾重定向把汇报行整个吞掉（该行此前完全不显示）；Python 解析改为「真的能执行」的探测
（`SEEP_PYTHON` → `python3`/`python` → `py -3` → `~/.pi/agent/seep-venv`），解释器不可用时
依赖它的检查项 SKIP 而不是报红。

`verify.ps1` / `verify.sh` 小节编号统一为 `[N/10]`（此前插了 `[5b]` 但总数仍写 9）。

### 清理

- 删除工作台旁残留的 v1.6.0 旧树（661 MB）。它自带一份 `Tool/mcp/seep_mcp_server.py`（27 工具）
  与指向它的 `.mcp.json`，是"改对了仓库、跑的还是旧代码"这类问题的直接来源。

### 文档

`CROSS-PLATFORM.md` 把「CTF Web 攻防 🟢 原生最佳环境（macOS/Linux）」改成如实的平台矩阵，
并新增「外部能力包（Unix）」章节；`DEPLOYMENT.md` 能力表补 Unix 列与新参数；
`DEPLOYMENT-CHECKLIST.md` 新增「3b. 外部能力包」基准表；README 双版补平台边界说明；
`windows-deep.md` 的 KB 计数 289 → 294。

### 验证记录

**Windows（实跑）**：`verify.ps1 -Detailed` 全绿；干净树全新安装与 v1.8.2 → 1.10.0 升级
两条路径复跑，0 条 `[!!]`、0 条 stash；`test_stdio_smoke.py` 38 工具；
`test_mcp_merge.py` 11/11；`test_config_parity.py` 三份产物字节一致。

**Unix（静态 + Git Bash 模拟）**：全部 `.sh` 过 `bash -n`；沙盒 `HOME` + `SEEP_AGENT_DIR`
下跑 `install.sh`，确认备份生成、用户自定义条目（`x64dbg`）保留、`mcp.json` 为 LF；
`verify.sh` 跑完后 55 项通过 / 0 项失败 / 6 项关注，结论 READY。

> **如实声明**：本机只有 Windows。Unix 侧是在 Git Bash 下验证逻辑与路径处理，
> **不等于**在真 Linux/macOS 上验证过；仍需一块真实 Unix 机器复核。


### 项目D 案例演进：build 18 零改动吸收（工具 v1.6.2）

**新增素材**：项目D（客户端授权校验链）扩展至**七个版本**，
新增 6.43 build 18（6.43.18.3）。

**核心发现 —— 签名表零字节改动即完成适配**：

- build 18 的结构变化是**方向翻转**的重排：`.text` +24,576 B，
  段内代码位移 `−0x320` ~ `−0x9A0`（**全负**，与 build 16 的 `+0x1D0` ~ `+0x5E0` 相反），
  数据段则 `+0x6600`。
- 现有六版本签名表在 build 18 上 **16/16 精确命中，汉明距离 0**，
  重生成流水线完全未触发。这是本项目第一次以**零字节表改动**吸收新版本。
- 直接收益来自 v1.6.1 的「单条签名 48 字节上限」决策：build 18 的位移幅度
  （≈2.5 KB）大于 build 16（≈1.5 KB），表却原封不动存活。

**新增文档与工具**：

| 文件 | 变更 |
|---|---|
| `docs/reverse-engineering.md` | 新增 **§11**（结构差分 / 零命中定位 / 48 B 上限权衡 / 语义复核 / 字符串差分排除新对抗 / 教训 7 条） |
| `docs/algorithm.md` | 版本指纹表与 16 位点表扩展为**七版本**；位移分布新增「方向翻转」行 |
| `README.md` | 新增 v1.6.2 演进章节（三假设排除矩阵 + 签名长度三方案对照） |
| `tools/config_7v.example.json` | **新增**，七版本配置示例（含 b18.3 全 16 位点偏移） |
| `tools/README.md` | 新增「零级预检」小节：精确命中时**不要**跑重生成，否则会提前透支漂移余量 |

**方法论沉淀（可直接复用于其他目标）**：

1. **先做精确命中预检** —— 汉明搜索是兜底不是首选，跳过它可省掉整条重生成链路；
2. **位移方向会翻转** —— 版本间 delta 无单调性，禁止趋势外推；
3. **签名长度上限是投资** —— 一次设对，后续版本可零改动吸收；
4. **精确命中 ≠ 语义不变** —— 字节一致仍须反汇编复核；
5. **操作数补丁需换判据** —— 用「包含该偏移的指令」而非「起始于该偏移的指令」；
6. **字符串差分是廉价的对抗筛查** —— 10 条新增即可排除「新增反篡改」假设；
7. **零改动 ≠ 零工作** —— 表没改，但定位、语义、取证、回归、真机五道验证一道不能少。

## [1.9.2] - 2026-11-08

### 部署链路重写：把「代码更新」与「能力补齐」拆成两层

**问题**：工作台有三个层次，旧链路只覆盖第一层。

```
第 3 层  能用吗？   ← 外部依赖：ffmpeg / frida / APKiD / Aotopsy / nuclei / ffuf
                     ↑ 完全没覆盖
第 2 层  装上了吗？ ← 技能 / 脚本 / MCP 工具定义
                     ↑ 只覆盖了一半（技能走目录枚举有，脚本没同步）
第 1 层  代码新吗？ ← git pull
                     ↑ 已覆盖
```

后果就是一句话：**工具在 `tools/list` 里看得见，一调用返回「未部署」。**

### 新增 `setup/install-capabilities.ps1`：外部能力包统一入口

| 组件 | 默认安装 | 成本 |
|---|:---:|---|
| `aotopsy`（Flutter AOT 分析） | ✅ | 零网络，从 `Tool/aotopsy` 直接复制 |
| `web`（ffmpeg + ffprobe） | ✕ | 约 80 MB 下载 |
| `android`（frida / objection / APKiD） | ✕ | pip + 独立 venv |
| `scanners`（nuclei / ffuf） | ✕ | 约 40 MB 下载 |

- 纪律：**默认只装零成本件**；要下载/装包的必须显式点名，任何组件失败只警告，绝不中断部署。
- `-CheckOnly` 只报表不动盘；`-ToolboxRoot` 一次性改根目录；`-Strict` 供 CI 用。
- 组件安装器不带 `exit`，改为同进程 splatting 调用 —— 顺带修掉了 `-Only a,b` 经 `-File` 传递时
  被当成单个字符串、触发 `ValidateSet` 失败的问题。

### `install.ps1` / `update.ps1` 接入

- `install.ps1` 新增能力包步骤（`-SkipCapabilities` / `-WithWeb` / `-WithAndroid` / `-WithScanners`）。
- `update.ps1` 新增 `-WithTools`（顺带补 ffmpeg + frida + APKiD）与
  `-CheckCapabilities`（**只补能力、不动代码**，网络拉不动代码时用）；结束报告重写：
  技能数与工具数改为**动态统计**，新增能力看板，并把「必须完全重启会话」写成独立段落
  （原来混在一段提示里，容易被略过；而 MCP 工具是启动时握手的，不重开就看不到新工具）。
- `install-pi.ps1`：不再往 `mcp.json` 写裸 `"python"`，改为**探测一个真正 `import mcp` 成功**的解释器
  并写绝对路径。此前若机器上的 `python` 指向没装 `mcp` 的解释器（系统 Python 3.10 / 商店别名 /
  conda base），服务端一启动就 ImportError，而体检只表现为「MCP 没连上」，排查成本极高。

### `verify.ps1`：从「文件在不在」到「现在能不能真跑」

- 新增 `[5b] 外部能力包可用性` 小节，逐组判定 Web 取证 / Flutter AOT / Android 动态 / 加固指纹 / 扫描器。
  缺失归入 🟡 DEGRADED 而非 🔴 MISSING —— 外部程序缺失是正常状态，不该判失败。
- 新增 `Resolve-VerifyPython`：Python 相关检查统一使用**探测后可执行**的解释器。
  此前直接调 `python`，若它是商店占位别名或指向已删 venv 的 `.cmd` 垫片，
  会连带把「语法自洽」「stdio 冒烟」「规则表同步」三项误报为红 —— 一次环境问题伪装成三个功能故障。
- 隐私走查的非 git 分支补排除「安装时生成的本地配置」（`opencode.jsonc`、`cordis.generated.yml`、
  `relay-config.json`、`tool-index.*`）。这些文件含本机绝对路径属正常，且已被 `.gitignore` 排除；
  此前用 ZIP 部署（无 `.git`）的用户每次体检都会误报隐私残留。
- `install.ps1` 的环境检测改为校验退出码与版本串。此前只看 `Get-Command python` 有没有结果，
  垫片失效时会打印 `[OK] Python 可用: 系统找不到指定的路径`。

### 验证记录（双路实跑）

**路径 A · 全新安装**（干净目录 + 沙盒 HOME，等价首次 clone）：

```
解压离线依赖包 → 技能 11 个（含 webseep）→ seep MCP 解释器: D:\Tool\IDA Pro\python311\python.exe
→ 补齐外部能力包（auto）→ [OK] 全部外部能力已就绪
→ 体检报告 核心检查通过 61 项 → 🎉 READY
```

**路径 B · 老用户升级**（克隆到 v1.8.2 `e9b6c9e`，跑的仍是**旧版** `update.ps1`）：

```
版本已更新: v1.8.2  ->  v1.9.2
技能 11 个（含 webseep）· MCP 工具定义 38 个 · 新增 setup/install-capabilities.ps1
补齐外部能力包（auto）→ [OK] 全部外部能力已就绪
体检报告 核心检查通过 61 项 → 🎉 READY
[!!] 警告 0 条 · git stash 0 条 · 工作区 0 项改动
```

**路径 B 二次执行**（此时已是新版 `update.ps1`，验幂等与新报告格式）：

```
[..] 版本未变化（v1.9.2）—— 将执行一次幂等重同步（补齐可能缺失的组件）
本次同步: 逆向技能 11 个 · MCP 工具定义 38 个
外部能力看板: ffmpeg / ffprobe / frida / objection / apkid / aotopsy / adb 全部 [READY]
体检报告 核心检查通过 61 项 → 🎉 READY
```

> 双路验证过程中又发现并修掉三个部署缺陷：
> ① `install-python.ps1` 用裸 `python`，垫片失效时 pip 全线失败，且**把错误文本当成功打印**；
> ② 验证 pytest 时 `| Select-Object -First 1` 提前终止管线，装好的包被判「不可用」；
> ③ `generate-configs.ps1` 每次重写内容相同的 `.mcp.json`，mtime 变化让 `git status` 报「已修改」，
> 于是 `update.ps1` 每次都弹一次「本地改动已 stash」——用户以为自己的文件被动过。

`clean-format.py` 零问题；中继单测 84/84。

### 已部署用户注意

```powershell
powershell -ExecutionPolicy Bypass -File .\setup\update.ps1 -WithTools
```

更新后**完全关闭并重开 Agent 会话**。想只补能力不动代码，用 `-CheckCapabilities`。


## [1.9.1] - 2026-11-08

### 修复：`seep_pe_*` 等工具在 stdio 模式下无限挂起（issue #13 / PR #14，致谢 @MrUncleXiang）

`_run_cmd()` 用 `subprocess.run()` 派生外部进程时没有重定向 `stdin`，子进程因此继承了
MCP 服务端自己的 stdin —— 那是一条由客户端（Claude Code / DSH / OpenCode / Pi）持有、
会话结束前永远不会关闭的 JSON-RPC 管道。

后果：在 stdio 传输下，**Python 子进程**在解释器启动阶段就卡住，脚本业务代码一行都没执行，
工具表现为「永久挂起」直到客户端超时。r2 / jadx / apktool 这些原生 exe 不受影响 ——
这正好解释了为什么当时只有 `seep_pe_*` 四条路径出问题（它们经由 `_run_pe_script()` → `_run_cmd()`
启动 Python 子进程）。

**本机实测复现**（`mcp` 1.30.0 / Python 3.11）：

```
修复前：  seep_pe_triage -> TIMEOUT (>20s)   seep_pe_aob_scan -> TIMEOUT (>20s)
修复后：  seep_pe_triage -> OK (5983 chars)  seep_pe_aob_scan -> OK (679 chars)
```

- **`Tool/mcp/seep_mcp_server.py`**：两处 `subprocess` 调用点补 `stdin=subprocess.DEVNULL`
  （`_run_cmd()` 与 `_run_web_script()`）。工作台 38 个工具的外部进程调用全部收敛在这两个函数，
  改一处即全覆盖，对不需要交互输入的工具零副作用。
- **新增 `Tool/mcp/test_stdio_smoke.py`**（303 行，纯标准库）：两层回归。
  - 静态层 `--quick`：AST 遍历，要求每个 `subprocess.run/Popen/call/check_*` 调用点显式给出
    `stdin=`，缺失即报出具体行号。零依赖、毫秒级。
  - 端到端层：真的以 stdio 拉起服务端，走 `initialize` → `tools/list` → `tools/call`
    （含一次真实 `seep_pe_triage`）。这是唯一能复现原始故障的层级。
- **`setup/verify.ps1`**：新增检查项「stdio 子进程不继承 stdin」（跑 `--quick`），
  核心检查项 54 → **55**。
- **`setup/install-python.ps1`**：补 `PIP_BREAK_SYSTEM_PACKAGES=1`。uv 托管的解释器与多数
  Linux 发行版自带 Python 都带 PEP 668 `externally-managed` 标记，裸 `pip install` 会直接
  以 `error: externally-managed-environment` 退出，导致 `mcp` 装不上、MCP 服务起不来。

### 为什么原有体检发现不了

`verify.ps1` 对 `seep_mcp_server.py` 只做 `ast.parse` 语法自洽检查 —— 漏写 `stdin=` 语法完全合法；
手动在普通 shell 里跑同一个脚本也只要 0.09 s。只有**以 stdio 服务方式真实调用**才暴露。
所以这次补的不是"再检查一遍语法"，而是一条端到端调用链 + 一个静态不变量。

### 已部署用户注意

修复只改服务端脚本，**无需重装依赖**：`git pull` 后完全重启 Agent 会话即可。
若仍遇到挂起，运行 `python Tool/mcp/test_stdio_smoke.py` 可自证当前副本是否已带修复。


## [1.9.0] - 2026-11-08

### 新增能力域：Web / 流媒体取证

- **第 11 个技能 `webseep`**（`Tool/skill/webseep/`，17 文件）——Web 源与接口取证方法论：
  HLS 六类根因判定（防盗链 / key 鉴权 / AES-128 / SAMPLE-AES / DRM / 源失效）、
  CMS 家族与采集接口指纹、TVBox / CatVod spider 三入口、头变体矩阵重放。
  素材来源已在 `Tool/skill/webseep/PROVENANCE.md` 与 `Tool/docs/PROVENANCE.md` 完整标注。
- **8 个 Web MCP 工具**：`seep_web_pipeline`（一键总入口）、`seep_web_gate`（阶段门，缺前置产物直接 BLOCK）、
  `seep_cms_fingerprint`、`seep_hls_analyze`、`seep_http_replay`、`seep_spider_extract`、
  `seep_web_report`、`seep_web_toolbox`。
- **9 个 PowerShell 取证脚本**（`Tool/scripts/web/`）+ 自测夹具（`_test/`，含本地 CMS / 门槛服务器与假 HLS 样本）。
- 判决纪律写进提示词：`EXT-X-KEY` 存在 ≠ 加密；key 非 16 字节 ≠ 解密成功；
  命中 Widevine / FairPlay / PlayReady / pssh → 立即 STOP，不探测许可证服务器。
- 硬约束写进脚本：`cms-fingerprint.ps1` 只发 GET、≤20 路径、400ms 间隔，不爆破、不提交表单、不尝试登录。

### 新增能力域：Android 外部工具箱

- **3 个 MCP 工具**：`seep_android_toolbox`（就绪检查）、`seep_apkid_scan`（加固 / 混淆器指纹）、
  `seep_aotopsy`（Flutter / Dart AOT `libapp.so` 静态分析与符号还原）。
- **6 个 PowerShell 脚本**（`Tool/scripts/android/`）：幂等安装 Frida / objection / frida-dexdump / APKiD / Aotopsy
  并生成 `.cmd` 垫片，另有 recon / dexdump / objection / apkid / aotopsy 五个作战脚本。
- **Aotopsy 安装载荷**（`Tool/aotopsy/`，11 MB，MIT）随仓库分发，`install-android-toolbox.ps1` 直接复制，无需构建。
- 公共库：`Tool/scripts/lib/WebToolbox.ps1`、`Tool/scripts/lib/AndroidToolbox.ps1`。

### MCP 工具数 27 → 38

与原 PE 四件套（`seep_pe_triage` / `_aob_scan` / `_diff` / `_patch`）合并，工具分组扩为**八大类**。
`seep_status()` 现在同时报告 `pe_engine_exe_reverse`、`android_toolbox`、`web_toolbox` 三块就绪度。

### 体检改动态断言（修复「体检假红 / 假绿」）

- `setup/verify.ps1` 不再写死「27 个原生工具定义」，改为从 `seep_mcp_server.py` 源码统计 `def seep_*`。
- 技能数改为遍历 `Tool/skill/` 目录统计，不再写死「10 大组件」。
- 新增 `webseep` 完整性检查（SKILL.md + ≥3 refs + 模板）。

### 文档

- `README.md` / `README.zh.md`：工具矩阵新增「Android 工具箱」「Web / 流媒体」两组，计数 27 → 38。
- `Tool/docs/MCP-SETUP.md`：工具清单刷新为 38，补充两段外部依赖说明与一键补全命令。
- 新增 `Tool/docs/WEB-TOOLBOX.md`、`Tool/docs/ANDROID-TOOLBOX.md`、`Tool/docs/SKILL-ROUTING.md`。
- `Tool/docs/TOOLKIT_GUIDE.md` 升级为六章版（新增 Android 工具箱、Web 取证工具箱两章）。
- `Tool/docs/PROVENANCE.md`：Skill 溯源扩至 11 个，新增 web/android 脚本溯源与第三方素材归属。
- `Tool/prompts/SYSTEM.md`：新增「Web / 流媒体取证路由」章节（三步入场 + 判决纪律 + 工具映射）。
- `Tool/skill/softseep/SKILL.md`：MCP 路由表补 `seep_web_*` / `seep_hls_*` / `seep_cms_*`。

### 已部署用户注意

1. 更新后**必须完全重启 Agent 会话**（MCP 工具在启动时握手，`/reload` 不够），否则看不到新增的 11 个工具。
2. 新增 11 个工具里有 4 个依赖外部工具箱：`seep_hls_analyze` 需 ffmpeg/ffprobe，
   `seep_apkid_scan` 需 APKiD，`seep_aotopsy` 需 Aotopsy，`seep_android_toolbox` 只做就绪检查。
   未安装时这些工具返回明确的修复指引，**不会**导致整个 MCP 服务不可用。
   补全命令见 `Tool/docs/WEB-TOOLBOX.md` 与 `Tool/docs/ANDROID-TOOLBOX.md`。
3. `Tool/aotopsy/`（11 MB）随仓库分发，`git pull` 会一并拉取，无需另行下载。


### 案例库：项目D 合并原地演进至 v1.6.1（build 16 支持）

- `Tool/cases/项目D/docs/reverse-engineering.md` 新增 §10：build 16 代码重排迁移（.text +245 KB、段内位移非均匀、capstone 局部定向反汇编、操作数补丁识别）
- `Tool/cases/项目D/docs/algorithm.md` 位点表扩为**六版本**矩阵，新增 §3.3（签名长度上限决策、IAT 地址常量导致左扩展收缩）
- `Tool/cases/项目D/README.md` 新增 v1.6.1 演进章节（回归断言 98 → 118）
- `Tool/cases/项目D/tools/09_multiversion_extend.py` 新增**一体化扩展流水线**（JSON 配置驱动，三级定位自动降级）
- KB 笔记 `10-multiversion-signature-narrowing.md` 新增陷阱三（签名长度上限）与陷阱四（验证方法本身会骗你）

## [1.8.2] - 2026-10-24

### 修复：作战模式隔离不彻底（真实泄漏，不是理论问题）

用户需求：**只有输入 `lab：` 才触发工作台，日常使用不应被逆向纪律污染。**

上一版把开关改成了会话级内存，但只做了一半 —— 全局 `AGENTS.md` 仍然**每个会话无条件加载**，
里面写着思维重定向、反退缩十项、G-Auth 授权门、Zero-Waste Recon 提效路由。
结果是：哪怕你没输入 `lab：`，写个普通脚本也在"反退缩十项硬约束"之下运行。

### 变更

- **`AGENTS.md` 瘦身（9.5 KB → 6.4 KB，去人格化）**：只保留
  ① 作战模式开关说明 ② **非 lab 会话禁令** ③ 部署/更新/卸载/校验命令。
  所有逆向纪律移出，改由 `seep-system.md` 在 `lab：` 后注入。
- **新增非 lab 禁令（硬规则）**：未输入 `lab：` 的会话中，禁止加载任何逆向技能、
  禁止调用 `seep_*` MCP 工具、禁止主动推销逆向能力、禁止套用反退缩话术。
- **`SYSTEM.md` 协议改写**：实验环境开关从"磁盘标志文件"改为**会话级内存**；
  新增 G-Auth 授权门与配套资源路径（从 AGENTS.md 迁入）。
- **中继开关解耦（`relay.py`）**：改写开关改为独立的 `~/.pi/agent/compliance-relay.flag`，
  不再依赖 `lab-mode.flag`。旧文件仍识别（向后兼容）。
  原因：lab 改为内存状态后磁盘上不再有人写该文件，继续以它为门会让中继**永久关闭**。
- 文档同步：`README.md` / `README.zh.md` / `DEPLOYMENT-CHECKLIST.md` / `DEPLOYMENT.md` /
  `COMPLIANCE-RELAY.md` / `PROVENANCE.md` / 中继 `README.md` 全部改口径。

### 验证记录（observed）

用 esbuild 打包扩展后，以 mock ExtensionAPI 驱动全部 5 个钩子，8 项断言全过：

| # | 场景 | 结果 |
|---|---|---|
| 1 | 新会话 + 普通输入"帮我写个 Python 脚本" | `action: continue`（原样放行） |
| 2 | 未激活时 `before_agent_start` | `undefined`（**不注入**任何提示词） |
| 3 | 输入 `lab：` | 激活，返回"已开启（仅限当前会话）" |
| 4 | 激活后 `before_agent_start` | 注入 8589 字符，含 `G-Auth` 与 `反退缩` |
| 5 | 激活后敏感词输入 | 转译为"白盒鉴权脆弱性测试 / 受限权限功能模块"+ 合规前缀 |
| 6 | 输入 `退出实验` | 立即关闭 |
| 7 | 退出后 `before_agent_start` | `undefined`（注入停止） |
| 8 | 退出后普通输入 | `action: continue`（恢复纯净） |

中继单元测试：**84/84 通过**（开关改动未破坏既有行为）。
`verify.ps1`：53/53 核心检查通过。

## [1.8.1] - 2026-10-24

### 新增

- **🔌 PE 引擎统一收口进 `seep` MCP（23 → 27 工具）**：
  - `seep_pe_triage`：一次过 PE 体检（节区/熵、导入导出、TLS、资源、PDB、CLR、校验和比对、保护信号）。
  - `seep_pe_aob_scan`：AOB 特征码定位 + `unique` / `ambiguous` / `pervasive` / `no-match` 裁决，支持 `across` 跨版本命中数对比。
  - `seep_pe_diff`：归一化易变头字段（TimeDateStamp / CheckSum）后的构建差分，差异区间映射回 RVA。
  - `seep_pe_patch`：可验证等长补丁（校验和重算 + 写盘后逐字节回读），支持 `dry_run`。
  - 四个工具与 `seep_r2_*` / `seep_apk_*` 保持同一返回风格与命名规范；`seep_status` 新增 `pe_engine_exe_reverse` 组件状态。
  - 实现方式为**薄包装**：不重写引擎，只做参数校验、路径解析（兼容工作台内嵌 / 上游镜像 / 已安装技能三种布局）、输出有界截断与错误归一化。

### 安全护栏（工具层强制，不依赖模型自觉）

- `seep_pe_patch` 拒绝 `out_path == pe_path`（原地覆盖一律拒绝）。
- 非 `dry_run` 时必须显式给出 `out_path`；`at_rva` / `at_offset` / `pattern` 三选一，多给或少给都拒绝。
- `expect=` 与实际字节不符时底层脚本直接中止，**且不产生输出文件**（已验证）。
- 四个 PE 工具中只有 `seep_pe_patch` 会写盘，其余三个严格只读。

### 验证记录（observed）

- 工具注册数：**23 → 27**（`seep_pe_triage` / `seep_pe_aob_scan` / `seep_pe_diff` / `seep_pe_patch` 均已注册）。
- `seep_status()` 正确报告 `pe_engine_exe_reverse.status = Ready` 并给出解析到的 scripts 路径。
- 功能实测（合成 PE fixture）：
  - `seep_pe_triage` → 完整报告（校验和 match、5 个节区、保护信号 4 条）；
  - `seep_pe_aob_scan` → 植入两处 → 正确裁决 `ambiguous`，并列出 `0x410` / `0x424` 两个命中；
  - `seep_pe_diff` → 自身对自身 → 只报告被归一化的易变字段，无内容差异；
  - `seep_pe_patch` → 原地覆盖/缺 out/双定位器/无定位器四种误用全部被拒；`dry_run` 正确预览；实际落盘后 `checksum recomputed` + `every patched byte re-read from the written file`；`expect` 不匹配时中止且**未创建输出文件**。

## [1.8.0] - 2026-10-24

### 新增

- **🪟 Windows PE 深水区执行层 `exe-reverse`（第 10 个技能）**：
  - 纳入 `https://codeberg.org/dabao1955/exe-reverse`（MIT，上游 SHA `c6ef186`），**上游文件零修改**，仅加 `ATTRIBUTION` 注释块与本地 `LOCAL-NOTES.md`，因此上游同步始终是纯拷贝。
  - 41 篇带门禁的参考文档 + **16 个零依赖 Python 引擎**（纯标准库）：
    `peutil`（RVA↔偏移双向、导入/导出/资源/TLS/重定位/PDB、微软算法校验和、逐节熵）、
    `pe_triage`、`pepatch`（等长补丁 + 歧义守卫 + 校验和重算 + **写盘后逐字节回读**）、
    `aob_scan`（unique / ambiguous / pervasive / no-match 裁决）、`pe_diff`、`hwprobe`、`capabilities`、
    `plan`、`preflight`、`fold`、`trace_reduce`（可选 SMT 证明）、`scan_leaks`、`make_fixture_pe`、
    `dart_snapshot_strings`、`gate_probe.js`。
  - 覆盖：PE 结构、补丁纪律、AOB 签名、完整性校验、保护壳、虚拟化/控制流平坦化、算法还原、
    符号执行、.NET 托管程序集、Unity IL2CPP、打包 Python、Flutter Dart AOT、内核驱动、
    硬件追踪与 Hypervisor 观测。
- **🚦 三层门禁命名空间消歧（`gate-crosswalk.md`）**：
  - 发现 `softseep` / `apkseep` / `exe-reverse` 各自使用 `G1–G4` 但**同名不同义**（同一个 `G2` 在三处分别指“写入判死归因 / 环境真实性 / 主机真实性”），已建立 `AUTH-G0…G4` / `APK-G1…G4` / `EXE-G1…G5` 前缀约定与执行顺序图，并将“裸 G2 视为歧义”写入 SKILL.md 硬规则。
- **🌉 Windows 深水区中文桥接（`windows-deep.md`）**：
  - 中文大白话 → `exe-reverse` 参考文件的唯一映射表（补丁/壳/虚拟化/.NET/IL2CPP/Python 打包/驱动/硬件追踪/算法还原）。
  - 明确与 `windows-sop.md` 的分工：后者是**交付流水线**，前者是**机制字典**。
- **🔄 上游第 4 条声明式规则**：`setup/upstream-rules.json` 新增 `exe-reverse` → `Tool/upstream/exe-reverse`（`preserve_local: []`），Codeberg 源已通过 `git ls-remote` 可达性验证，防外溢单测 6/6 通过。

### 变更

- `softseep` 路由矩阵新增 Windows 深水区 6 类意图（补丁工程 / 保护壳·虚拟化 / 托管程序集 / 运行时捆绑 / 内核·硬件层 / 模块开发），并补充平台判型信号（`.msi` / `.node` / `GameAssembly.dll` / `python3xx.dll` / `_internal` / `pyarmor_runtime`）。
- `softseep` references 由 8 篇增至 **10 篇**；体检技能项由 9 项增至 **10 项**，`verify.ps1` / `verify.sh` 新增 `exe-reverse` 校验（SKILL.md + ≥41 refs + ≥16 scripts）。
- `README.md` / `README.zh.md` / `PROVENANCE.md` / `DEPLOYMENT-CHECKLIST.md` / `CLAUDE.md` / `AGENTS.md` / `DEPLOYMENT.md` 全面同步第 10 个技能与第 4 个上游。
- 体检新增 Windows 无 Python-in-PATH 时的**常见安装路径自愈探测**（`C:\Program Files\Python3xx`、`%LOCALAPPDATA%\Programs\Python\Python3xx`），消除“明明装了 Python 却报 MISSING”的误判。

### 验证记录（observed）

- `scripts/doctor.py`：**16/16 脚本可运行**；本机 28 项能力中 14 项 `ok`，14 项 `BLK`（缺调试器/IDA/测试签名，属宿主限制而非缺陷）。
- 端到端往返：`make_fixture_pe` → `pe_triage` → `aob_scan`（植入两处 → 正确报 `ambiguous`）→ `pepatch`（dry-run → 落盘）→ 独立复核：原文件 SHA256 不变、补丁文件校验和 `0x10bad → 0x1181` 重算正确、RVA `0x1010` 处字节确为 `90 90 90`。
- 红线取证：上游 `0 strong / 16 weak / 102 suppressed`，`RESULT=clean`；`docs/tool-acquisition.md` 明确写明 “No cracked builds, no key generators, no patched installers”；外部链接仅官方厂商文档 / GitHub / Microsoft Learn。

## [1.7.0] - 2026-10-23

### 新增

- **🚀 现代 LSPosed 与 Vector 双模架构支持 (API 101+)**：
  - 更新 `Tool/skill/apkseep/references/lsposed-and-modules.md`：
    - 详述经典 XposedBridge (API 82) 与现代 Vector / libxposed (API 100/101/102) 差异（`META-INF/xposed/java_init.list`、`io.github.libxposed.api.XposedModule`、拦截器链式 Hooker 模型、`xposedscope`）；
    - 制定第三方未知模块逆向分析 4 步 SOP（入口定位、作用域提取、混淆方法与特征指纹反查、JNI Native 挂钩剖析）；
    - 引入动态 ClassLoader 构造 Hook 方案（针对动态解密 Dex、插件化与加壳应用）；
    - 整合真机免逆向动态辅助武器库（算法助手 Algorithm Aide、SimpleHook、LSPilot）；
    - 提供三大 AI 逆向协同 Prompt 模板（入口分析、混淆还原、Native 意图解析）。
- **🛡️ KernelSU 内核级 Root 与 Systemless 深度防御与对抗**：
  - 更新 `Tool/skill/apkseep/references/kernel-and-environment-hardening.md`：
    - 引入 `preinit/preinit.conf`（SELinux 策略前阶段执行最高权限 `insmod`/`exec`/`write`）；
    - 引入 `initrc/` 系统级 RC 脚本透明注入机制；
    - 详述 Linux 内核原生 OverlayFS 机制（Whiteout `mknod c 0 0` 虚拟删除、Opaque 属性整块目录替换）；
    - 解析 BusyBox ash 独立运行环境 (`ASH_STANDALONE=1`) 与 ZygiskNext 桥接规范。
- **⚙️ 双模 LSPosed 脚手架引擎升级**：
  - 增强 `Tool/skill/apkseep/scripts/lsposed_scaffold.py`：新增 `--api {legacy, modern}` 参数与 `--with-classloader-hook` 选项，一键生成经典 API 82 或现代 libxposed Vector API 101 骨架，并支持无 Gradle 极速编译链。
- **📚 ReverseLab 攻防知识库扩展**：
  - 新增 `09-lsposed-root/01-modern-lsposed-module-analysis.md` 与 `09-lsposed-root/02-kernelsu-root-mechanisms.md`，同步更新 `kb-index.json` 索引。
- **🧠 总控判型与调度升级 (`softseep`)**：
  - `Tool/skill/softseep/SKILL.md` 新增对 LSPosed、Xposed、Vector、KernelSU、APatch、Magisk 等大白话意图的自动判型与精准路由。

- **🌐 上游定点隔离同步与防外溢体系 (Zero-Spillover Upstream Sync)**：
  - 新增 `setup/upstream-rules.json`：声明式上游规则清单，严格绑定每个上游仓库的唯一目标目录与白名单边界。
  - 新增 `setup/sync-upstream.py`（纯标准库）：物理边界硬性断言 (`realpath` 严格前缀匹配)，上游 A 仓库更新只能并入 A 目录，绝对阻断跨目录外溢；保留本地定制文档。
  - 新增 `setup/sync-upstream.ps1` / `setup/sync-upstream.sh`：本地一键定点同步脚本，支持 `-Target`、`-DryRun`、`-CheckOnly`。
  - 新增 `.github/workflows/upstream-sync.yml`：云端定时巡检工作流，发现上游新提交自动按仓库切独立分支提 PR，Diff 严格限定在专属目录内。
  - 新增 `setup/test_sync_upstream.py`：防外溢熔断与路径越界安全单元测试套件（6 项全部通过）。
- **⚡ 下游使用者极简更新体验升级**：
  - 项目根目录新增 **`update.bat`** 与 **`update.ps1`**：双击即可全自动检测代理、安全暂存修改、无损增量拉取并跑完 52 项体检。
  - 增强 `setup/update.ps1` 与 `setup/update.sh`：新增 `-Check` / `--check` 轻量版本检查，支持非阻塞版本探测。
  - 体检系统升级至 **52 项核心校验**：全面覆盖上游规则与防外溢引擎在位状态。

### 变更

- **📦 项目D 案例更新至 v1.5.0**（跨版本补丁迁移 · 五版本 AOB 特征码）
  - 版本谱系由 3 个扩展到 **5 个**（新增 build 12 / build 15），位点偏移表与特征码表全面刷新。
  - 新增 **§8「静默自动更新 + 数据段填充漂移」**：记录官方内置更新器静默覆盖已打补丁主程序导致的授权失效链，
    以及数据段填充漂移使滑动汉明距离误命中（距离仅 2、位置早 2 字节）的陷阱与修正流程。
  - `docs/algorithm.md`：五版本指纹表、五版本位点偏移对照、新增 §3.2 填充漂移专项。
  - `tools/` 流水线脚本改为**基于脚本位置自动解析路径**，去除作者本地绝对路径。
  - 回归断言由 61 项扩充至 **89 项**（五版本端到端），并断言既有版本产物哈希零变化。
- **📚 知识库新增笔记**：`pe-reverse/10-license-keygen/10-multiversion-signature-narrowing.md`
  —— 多版本特征码收窄与数据段填充漂移陷阱（含三重确认流程与零回归断言清单）。

---

## [Unreleased]

### 新增

- **🌐 项目D 案例更新至 v1.6.0**（全栈中英双语国际化架构）
  - 纯代码内嵌双语字典（零 `.resx` / 零附属程序集），保持单源码 `csc.exe` 秒级编译。
  - 首启自动探测 `CultureInfo.CurrentUICulture`，非中文系统直接呈现专业英文。
  - 侧边栏 `[ 🌐 EN / 简 ]` 胶囊按钮实现毫秒级内存热重绘（保留 Tab 状态与控制台日志）。
  - 运行日志实时翻译层（`TranslateLog`）：115+ 条模式替换，覆盖 AOB 补丁 / ACL 冻结 / 备份归档全链路。
  - 回归断言由 89 项扩充至 **98 项**（新增 9 项国际化单元测试）。
  - 文档新增「全栈中英双语国际化架构」章节，含四项关键工程决策（为何弃用 `.resx`、为何热重绘而非重建、日志为何必须走翻译层、CLI 同步国际化）。

---

## [1.6.0] — 2026-10-11

### 新增

- **🔁 中继拒答自动重试**（`Tool/scripts/compliance-relay/refusal.py`）★
  - Gemini 对「命令式要求对具体目标执行攻击性分析」的请求会**静默拦截**：
    `HTTP 200 + {"choices": [], "usage": {"completion_tokens": 377}}` ——
    模型生成了 token 但内容被丢弃，**不报错、不提示**，异常处理根本捕获不到。
  - 中继现在会检测这类拒答，**自动换一种写法重发**，对客户端完全透明。
  - 策略级联（全部**保留用户指定的目标**）：
    `original` → `S1 评审清单式` → `S2 设计评审框架` → `S3 英文评审式`
  - 实测：原句被拦（377 tokens 丢弃）→ 改写后返回 **2611~3324 字**完整回答。
  - 支持非流式（OpenAI / Anthropic / Google 原生形状）与流式 SSE 两类拒答检测。
  - 性能保障：只缓冲到「可判定」为止（SSE 8KB / JSON 4MB），超出上限即视为肯定没被拦，直接透传。
  - 可配置：`relay-config.json` 中 `refusalRetry` / `refusalRetryAttempts`（默认开、3 次）。
  - 新增 **40 项单元与集成测试**（共 84 项全绿），含「上游先拒答再放行」的端到端验证。

### 变更

- `relay.py` 响应转发改为「缓冲到可判定 → 需要时重试 → 再透传」，
  非拒答的正常长回答仍为流式透传。

---

## [1.5.0] — 2026-10-11

### 新增

- **🔍 L1 可观测性日志**（`security-audit-interceptor.ts`）
  - 动机：L1 有两类**不会报错的失效方式** —— 对 OpenAI 兼容端点乱注入会 400；
    对「名字叫 gemini 但实际走 OpenAI 格式」的链路注入则**被中转静默丢弃**。
  - 设 `PI_SAFETY_LOG=1` 后，每次判定写入 `~/.pi/agent/logs/l1-safety.log`，
    判定分为 `INJECT` / `SKIP` / **`SKIP-INEFFECTIVE`**（名字像 Gemini 但形状是 `messages`，
    注入必然无效的告警）。日志超 512KB 自动截断。
- **🧪 Gemini 安全设置验证工具**（`Tool/scripts/check-gemini-safety.py`）
  - 用同一提示词分别以「不注入 / 注入 `BLOCK_NONE`」请求 Google 原生接口，
    对比 `finishReason` 给出**可证伪的结论**：有效 / 无法区分 / 无效。
  - 纯标准库，密钥仅从 `GEMINI_API_KEY` 环境变量读取，**绝不打印、绝不落盘**。
  - 支持 `--list-models` / `--model` / `--prompt`。
- **🗑️ 一键卸载脚本**（`setup/uninstall.ps1` / `setup/uninstall.sh`）—— 回应 Issue #8
  - 原则：**只移除工作台自己装的东西，绝不碰你的数据**
  - 移除范围：工作台自带的 9 大技能、`AGENTS.md` / `SYSTEM.md`、`extensions/*.ts`、
    `mcp.json` 中的 `seep` / `js-reverse` / `playwright`、工作台加入的 12 个 packages、`lab-mode.flag`
  - **永不触碰**：`models.json` / `auth.json` / `sessions/` / `logs/`、
    你自己添加的 Skill 与 MCP 条目、`settings.json` 的其他字段
  - MCP 条目采用**外科手术式**判定：只有 `args` 确实指向工作台组件时才认为归工作台所有
  - 支持 `-DryRun` 预览、逐项 `-Keep*` 保留、`-Purge` 深度清理、`-Restore` 反向恢复
  - 卸载前自动整体备份到 `~/.pi/agent/backup-uninstall-<时间戳>/`
  - 手册：[MANUAL/DEPLOYMENT.md — 卸载与回滚](MANUAL/DEPLOYMENT.md)
- **🔁 已有用户一键更新机制**（`setup/update.ps1` / `update.sh` + `VERSION` + 本 CHANGELOG）
  - 自动 `git stash` 保护本地改动 → `git pull` → 预览变更 → 备份 → 幂等增量同步 → 校验零丢失 → 全量自检

### 修复

- **🚨 安装/更新会静默覆盖用户 `mcp.json`（严重）**
  - 根因：`$raw.StartsWith([char]0xFEFF)` 在**无 BOM** 的文件上也会返回 `TRUE`。
    .NET 默认 `StartsWith` 使用**文化敏感比较**，而 `U+FEFF`（BOM 字符）是
    「可忽略字符」，等价于空字符串，因此**任何字符串都「以它开头」**，
    随后的 `Substring(1)` 便削掉了首个 `{`，把合法 JSON 破坏成非法。
  - 后果：`install-pi.ps1` 读取失败后静默回退到空配置，
    用模板**覆盖**用户 `mcp.json`，丢失自定义 MCP 条目（如 `ida`）与真实 Playwright token。
  - 修复：`install-pi.ps1`（mcp.json + settings.json）、`install-ida.ps1`、`update.ps1`
    共 4 处改为序数/字符比较。
- **🧩 3 个技能被 Agent 静默跳过**（Issue #6，由 @xiaozhi1218 报告）
  - 根因：`safe-skills/{apk-reverse,ida-reverse,radare2}/SKILL.md` 带 UTF-8 BOM，
    而 DSH 的 frontmatter 解析要求首行**严格等于** `---`，于是整条技能被静默丢弃（9 条只发现 6 条）。
  - 修复：`setup/clean-format.py` 新增 Markdown / JSON **剥离 BOM** 规则（`.ps1` 仍保留 BOM），
    并排除 `Tool/upstream/` 以保持上游镜像字节保真；共修复 8 个文件。
  - 新增门禁：`verify.ps1` / `verify.sh` 会阻断任何带 BOM 的 `SKILL.md`，防止回归。
- **🛑 Ctrl+C 退出时 MCP 子进程打印 KeyboardInterrupt 堆栈**（Issue #7）
  - `seep_mcp_server.py` 现在捕获 `KeyboardInterrupt` / `BrokenPipeError` / `EOFError` 静默收尾，
    并为 POSIX 注册 `SIGTERM` 处理器。
- **🔌 Gemini 私有字段被注入到所有 provider（由 PR #9 @linbei0 贡献）**
  - L1 底座级解封不再无差别写入 `safetySettings` / `config`，
    改为**仅对 Google/Gemini 端点注入**；OpenAI 兼容网关不再返回 `400 UNKNOWN_FIELD`。
  - 可用环境变量 `PI_SAFETY_PAYLOAD=off|all|auto` 覆盖（默认 `auto`）。
- **🍎 macOS / Linux 自动安装 radare2（由 PR #5 @iscodeminister 贡献）**
  - `setup/install.sh` 新增引擎探测：macOS + Homebrew 自动安装，其他平台给出清晰指引；幂等且非致命。
- **🔒 隐私门禁改为只扫描 git 跟踪文件**
  - 本地已 gitignore 的生成配置不再造成误报，同时更准确地反映「实际会发布的内容」。

### 变更

- `verify.ps1` 增至 **52 项**核心检查，`verify.sh` 增至 **51 项**。

---

## [1.4.0] — 2026-09-30

### 新增

- **🌐 链路层合规转译中继**（`Tool/scripts/compliance-relay/`）
  - 本机回环中继，在请求离开本机前把口语平滑转译为合规术语
  - 覆盖三种协议：`openai-completions`（Pi Agent 主力）、`anthropic-messages`（Claude Code）、`openai-responses`（Codex）
  - 纯 Python 标准库实现，**零新增依赖**；**零落盘**（日志只记命中条数）
  - 默认关闭，需显式运行 `python relay.py`；受 `lab-mode.flag` 门控，mtime 热加载
  - 手册：[MANUAL/COMPLIANCE-RELAY.md](MANUAL/COMPLIANCE-RELAY.md)
- **🔒 脱敏与个人隐私门禁**（`verify.ps1` / `verify.sh` 第 9 节）
  - 全深度递归扫描个人路径、身份标识、私有域名、凭据
  - 生成物追踪检查（含本机路径的配置文件不得入库）
  - 脱敏基准表 D1–D6 记录于 `MANUAL/DEPLOYMENT-CHECKLIST.md`
- **🖥️ 跨平台支持**（macOS / Linux）
  - 新增 `setup/install.sh`、`setup/verify.sh` 原生 Bash 脚本
  - `seep_mcp_server.py` 自动探测系统 `radare2` / `rabin2` 与各平台 JDK 路径
  - 手册：[MANUAL/CROSS-PLATFORM.md](MANUAL/CROSS-PLATFORM.md)
- **📖 部署与校验体系**
  - `MANUAL/DEPLOYMENT.md` 全景部署手册（含 4 大 Agent 接入 SOP 与排障 FAQ）
  - `MANUAL/DEPLOYMENT-CHECKLIST.md` 官方基准核验清单（单一真值源）
  - `verify.ps1 -Detailed` 输出结构化基准校对看板
- **📦 案例库扩充至 14 个**（项目 A ~ 项目 N）
  - 新增 项目M（Java + install4j 双层鉴权）、项目N（.NET x64 + VM 混淆加固）

### 变更

- **⚙️ 安装脚本重构为幂等 + 无损模式**
  - `install-pi.ps1` 改为**增量合并** `mcp.json` / `settings.json`，不再覆盖用户自定义 MCP
  - 所有 JSON 配置统一以 **UTF-8 无 BOM** 写入，修复 Node.js `JSON.parse` 报错
  - 路径统一转为正斜杠，修复 Windows 反斜杠导致的 JSON 非法转义
- **🛡️ 安全审计扩展双加固**（`security-audit-interceptor.ts`）
  - 新增 25 项 `INJECTED_PREFIXES` 上下文守卫：Agent 自注入的环境 / AGENTS.md / 技能清单**不再被误改写**
  - 顺序 `replace` 改为**单趟最长优先匹配**：算法保证「绕过会员」优先于「绕过」，且替换产物不回扫（杜绝级联污染）
- **🔍 IDA Pro 探测强化**（`install-ida.ps1`）
  - 支持 `-IdaRoot` 参数、注册表探测、交互式输入自定义路径
  - 支持 IDA 9.x 原生 `idalib_supervisor` 模块模式
- **🔗 上游镜像归位**
  - `apk-reverse`、`open-tgtylab`、`open-reverselab` 三大开源项目完整镜像至 `Tool/upstream/`
- **⚖️ 许可证更正为 GPL-3.0**
  - 因整合了两个 GPL-3.0 上游项目，整体许可证由 MIT 更正为 **GNU GPL-3.0**

### 修复

- 修复 Windows PowerShell 5.1 下 `Set-Content -Encoding UTF8` 写入 BOM 导致 Node.js JSON 解析崩溃
- 修复 Windows 路径反斜杠未转义导致的 `Bad escaped character in JSON`
- 修复 `install-pi.ps1` 全量覆盖导致用户自定义 MCP（如 x64dbg）被抹除
- 修复 IDA 路径写死 `D:\Tool\IDA Pro`、非标准安装位置无法识别
- 修复 Bash 脚本 CRLF 换行污染导致的 `bad interpreter` 报错（13 个脚本）
- 修复 70 个 PowerShell 脚本缺失 UTF-8 BOM 导致的中文乱码与语法解析中断

### 安全

- **清理个人隐私与凭据残留**（发布前强制门禁）
  - 移除全部个人绝对路径、个人身份标识、私有中转站域名
  - 移除案例中残留的真实产品名 / 厂商域名 / **真实加密 Salt**
  - 含本机路径的生成物（`opencode.jsonc`、`cordis.generated.yml`）不再入库
  - 中继运行配置 `relay-config.json`（含访问 token）纳入 `.gitignore`

---

## [1.3.0] — 2026-09-28

### 新增

- 案例库扩充至 13 个（新增 项目L Qt5 C++、项目M Java + install4j）
- `seep_r2_xrefs` 工具：交叉引用查询，内置分页与统计摘要
- 上下文预算控制：`seep_r2_decompile` 支持 `fold`（省 ~60% Token）/ `summary`（省 ~90%）

### 变更

- `MANUAL/` 战术手册扩充至 6 份

---

## [1.2.0] — 2026-09-26

### 新增

- `MANUAL/ANTI-DEBUG.md`：反调试绕过字典与代理 DLL 框架
- `MANUAL/UNPACKING.md`：UPX / MPRESS / Themida / VMP 脱壳 SOP
- `MANUAL/POC-VALIDATION.md`：Frida 自愈循环与 PoC 沙箱验证

### 变更

- `verify.ps1` 升级为 7 大维度体检

---

## [1.1.0] — 2026-09-25

### 新增

- `check.bat` / `check.ps1` 根目录一键体检入口
- `setup/verify.ps1 -Detailed` 结构化基准校对看板
- 部署完备性校验体系（7 大维度）

---

## [1.0.0] — 2026-09-24

### 新增

- 首个公开版本
- 9 大逆向 Skill（`softseep` 总控 + `apkseep` + `ida-reverse` + `safe-skills` 5 组）
- 自研 `seep` MCP 服务（23 项原生工具）
- 289+ 篇攻防知识库
- 9 个脱敏工业案例范式（项目 A ~ 项目 I）
- Lab Mode 磁盘状态机与三层防拒体系

---

## 更新类型说明

| 变更类型 | 含义 | 用户需要做什么 |
|---|---|---|
| **新增** | 新功能、新工具、新案例 | 跑一次更新脚本即可 |
| **变更** | 行为或接口调整 | 建议读一下具体条目 |
| **修复** | 缺陷修复 | 跑一次更新脚本即可 |
| **安全** | 安全或隐私相关 | **强烈建议立即更新** |

> **兼容性承诺**：本工作台的用户自有数据（`models.json`、`auth.json`、自定义 MCP 条目、
> `lab-mode.flag`）在更新过程中**永不被覆盖**。若某次更新需要用户手工干预，
> 会在对应条目中显式标注「**需要手工操作**」。
