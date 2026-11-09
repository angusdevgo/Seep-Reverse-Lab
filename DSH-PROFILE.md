# DeepSeek Harness (DSH) 接入 — Seep 逆向工作台

> DSH 通过 `@deepseek-ai/dsh-mcp-client` 桥接外部 MCP 服务，配置以 **Cordis Overlay 补丁**
> 形式挂载。本工作台的 `seep` MCP 暴露 **38 个工具**，挂载后模型看到的名字形如
> `mcp__seep__seep_pe_triage`（`mcp__<serverName>__<原始工具名>`）。

适配基准：**DSH 0.2.2-rc.1**（`dsh --version`）。字段定义取自该版本
`@deepseek-ai/dsh-mcp-client` 的 `lib/types/index.d.ts`。

---

## 一、 四种挂载方式

| 方式 | 命令 | 适用 |
| :--- | :--- | :--- |
| **插件包（1.14.0 起，推荐）** | `python setup/dsh-plugin-setup.py` | 长期使用。装一个几十 KB 的插件包，路径写在配置里；MCP 与技能由插件在运行时自己挂 |
| 持久挂载（旧路线，保留兼容） | `python setup/dsh-merge.py` | 没有 `dsh` CLI 或不想装包时。直接往 profile patch 里写条目 |
| 全局挂载 | `python setup/dsh-merge.py --global` | 本机所有 profile 都生效（`$DSH_HOME/cordis.patch.yml`） |
| 临时挂载 | `dsh web --patch "<工作台绝对路径>/setup/cordis.generated.yml"` | 一次性试用，不落盘 |

`setup/install.ps1` / `setup/install.sh` 会**自动检测** `$DSH_HOME`（默认 `~/.dsh`）：
存在则**先试插件包路线**，失败才回退旧路线（两条不能同时上，否则 MCP 会挂两份）。
跳过该步骤用 `-SkipDsh`（Windows）/ `--skip-dsh`（Unix）。

### 面板上的「对比 / 更新工作台」

| 按钮 | 做什么 | 会不会改文件 |
| :--- | :--- | :--- |
| **对比** | `git fetch` 后报：落后几个提交、领先几个、工作区多少改动、差哪几条（列前 10 条） | 不改 |
| **更新工作台** | `git pull --ff-only`：把仓库（工具、MCP、技能、插件代码全在里面）更到远端 | 会，但只快进 |
| **更新内容** | 对内容目录做同样的事，不碰工具仓库 | 会，但只快进 |

只用 `--ff-only`：本地有冲突时它直接失败并告诉你，**不会替你合并、不会丢你的改动**。

更新完要不要重启：

- 仓库里的 **MCP 服务端 / 插件代码** 变了 → 重启 DSH
- 只是 **技能 / 知识库 / 案例** 变了 → 不用重启（技能层带 watch，知识库查询时现读）

### 内容层单独更新（不碰 561MB 的工具仓库）

工具和内容可以分开住：

| 层 | 放哪 | 更新方式 |
| :--- | :--- | :--- |
| 工具（jadx / apktool / radare2 / node_modules） | 仓库 `Tool/mcp/Tool/safe` | `git pull`（561MB，改得少） |
| **内容（技能 / 知识库 / 案例）** | **独立的 git 仓库**，例如 `D:\seep-content` | 面板上一键，或 `git pull` |

内容仓库的约定布局（目录名固定，缺哪个就退回仓库自带的那份）：

```
<内容目录>/
  skill/          # 与 Tool/skill 同级，每个子目录一个 SKILL.md
  safe-skills/    # 可选
  kb/             # 等价于 Tool/mcp/Tool/reverselab/kb
  cases/          # 等价于 Tool/cases
```

配置两条就够（面板「配置」区）：

- **内容目录**：`contentRoot`，填本地路径。留空 = 用仓库自带的。
- 想让它能被命令拉：那个目录本身得是 `git clone` 出来的（面板上的「更新内容」执行 `git pull --ff-only`）。

**实测结果（都是真的跑出来的）**

| 动作 | 结果 |
| :--- | :--- |
| 换 `contentRoot` 后启动 | 技能注册表只剩内容仓的（`testlab-content`），不再扫仓库那份 |
| 内容仓里跑 `git pull`（1 个提交） | 新 KB 条目 `apk-reverse/second.md` 立刻能搜到 |
| 同上，内容仓新加一个技能 | 注册表**立刻**变成 3 个，含 `hot-added-skill` —— **不用重启** |

技能层带 watch，知识库是查询时现读，所以内容更新**不需要重启 DSH**；
工具层（MCP 服务进程）才是必须重启的那一层。

> **这份是 DSH 专属文档。** Pi Agent 的接线完全不同（写 mcp.json + 拷技能），
> 两者的对照见 [MANUAL/AGENTS.md](MANUAL/AGENTS.md)；
> 更新与发布路线见 [MANUAL/UPDATING.md](MANUAL/UPDATING.md)。

### 发布与分发

插件怎么发、别人怎么更新、版本号怎么走、出事了怎么退 —— 见
[MANUAL/PUBLISHING.md](MANUAL/PUBLISHING.md)。

### 更新什么要怎么做（一张表说清）

**结论先说：所有内容都靠仓库更新（`git pull`），插件包本身不是下载源。**
`file:` 安装是**硬链接**，装进来的就是仓库里那几个文件，没有第二份拷贝。

| 改了什么 | 怎么更新 | 为什么要这么做 |
| :--- | :--- | :--- |
| 插件已有的文件（`lib/*.js`、`package.json`、`cordis.patch.yml`） | `git pull` 后**重启 DSH** | 硬链接，改仓库等于改已装副本；代码在进程启动时加载 |
| 插件**新增**的文件（比如加了一个 `lib/xxx.js`） | `git pull` → `python setup/dsh-plugin-setup.py` → 重启 | 硬链接只链安装那一刻存在的文件，新文件得重新 add |
| MCP 服务端（`Tool/mcp/*.py`） | `git pull` 后**重启 DSH** | MCP 是启动时拉起的子进程 |
| 技能（`Tool/skill/**`） | `git pull`，**新会话生效** | 技能层是运行时扫仓库目录（带 watch） |
| 知识库 / 内置工具 / 手册 | `git pull`，**不用重启** | 用的时候才去读仓库里的文件 |
| 工作台换目录 | `dsh-plugin-setup.py --root <新路径>` + 重启 | MCP 连接在启动时建立，路径是那时定的 |
| 依赖（`node_modules` / Python venv） | `setup/extract-deps.ps1` / `setup/install-python.ps1` | 太大，不进插件包 |

为什么工具层不能走插件：`Tool/` 是 **660MB+**（jadx / apktool / radare2 / node_modules），
npm 与插件机制都装不下，也不该塞进 `~/.dsh`。插件只负责「把 MCP 指向仓库里那份」。

所以 `dsh plugin update` 现在什么都做不了 —— 实测输出 `Already up to date`。
它只在将来插件发布到 npm 之后才有意义，而且那时它也只更新插件本身（~96KB），
工具、技能、知识库照样得跟着仓库走。

### 插件包路线（1.14.0 起）

为什么加这一条：旧路线把 MCP 条目写死在 profile patch 里，路径是绝对路径，
仓库一搬家就全断。改成插件包之后，**只有一个地方要改：工作台路径**。

```powershell
python setup\dsh-plugin-setup.py                          # 装包 + 写入当前仓库路径
python setup\dsh-plugin-setup.py --root D:\新位置\Seep     # 仓库搬家后重跑这一条
python setup\dsh-plugin-setup.py --check                   # 只报状态，不改任何文件
python setup\dsh-plugin-setup.py --no-skills               # 不在 DSH 里列技能
python setup\dsh-plugin-setup.py --no-lab-gate             # 关掉 lab 开关
python setup\dsh-plugin-setup.py --dry-run                 # 只看会改什么
python setup\dsh-plugin-setup.py --with-playwright         # 额外挂 Playwright MCP（+25 工具）
python setup\dsh-plugin-setup.py --with-ida                # 额外挂 IDA MCP（+48 工具，需本机有 IDA）
```

默认只挂 `seep` + `js-reverse`（62 个工具）。那两个可选的不默认开：
IDA 要本机装了 IDA、Playwright 走 npx 要联网，且多几十个工具会挤上下文。
面板里也能直接勾选，效果一样。

`--check` 会报：包装了没、路径写了没、配置里的路径跟当前仓库一不一致、
**有没有旧路线残留**、插件上次启动时接线了哪些。排查先跑它。

> **只装 DSH 的话，还要补一条 `generate-configs`**：全新 clone 里没有
> `setup/cordis.generated.yml`（它是生成物，不进 git）。插件路线用不到它，
> 但 `verify.ps1` 会拿它当一项核心检查，不生成就是 65/66。
>
> ```powershell
> powershell -ExecutionPolicy Bypass -File setup\generate-configs.ps1
> ```

它做的事：

1. `dsh plugin --profile web remove seep-dsh-workbench`（没装过时失败属正常）
2. `dsh plugin --profile web add file:<仓库>/packages/dsh-workbench`
3. 往 `$DSH_HOME/profiles/<p>/cordis.patch.yml` 写：

```yaml
- id: seep-workbench-boot
  config:
    repoRoot: '<仓库绝对路径>'
```

装好之后插件做的事：路径自检 → 挂 `seep` / `js-reverse` 两个 MCP（超时 900s / 600s）
→ 挂技能层 → 起 lab 开关。结果写进 `$DSH_HOME/seep-workbench.status.json`，
`setup/verify-dsh.py` 读那份文件，不用去猜合成配置。

> **旧路线会自动清掉**：如果 profile 里还留着 `dsh-merge.py` 写的标注块，
> `dsh-plugin-setup.py` 装完会把它删掉 —— 两条路线同时生效会把 MCP 挂两份。
> `verify-dsh.py` 的 A6 项专门查这个。

> **一个坑（实测）**：`file:` 安装是**硬链接**，不是拷贝。
> 手工往包里加新文件后必须 `remove` + `add` 重装才生效，
> 只改已有文件则是即时生效。`dsh plugin update` 对 `file:` 会回一句
> "Already up to date"，别信。`dsh-plugin-setup.py` 每次都先 remove 再 add，
> 所以重跑它一定能拿到最新代码。

> **另一个坑（实测，必须知道）**：DSH 0.2.2 的「设置 → 内置插件」列表里能看到
> `seep-workbench-boot` 这一条，但**第三方插件包不显示自动生成的配置表单**
> （只有内置插件有那种卡片）。所以工作台路径**不能在网页上填**，
> 只能用 `dsh-plugin-setup.py` 写，或者手改上面那个 `cordis.patch.yml`
> （设置 → 打开配置文件 可以直接打开它）。

### Lab 模式下会做什么（不做 Lab 就什么都不做）

| 行为 | 不开 Lab | 开了 Lab |
| :--- | :--- | :--- |
| 注入作战纪律（`Tool/prompts/SYSTEM.md`） | ✗ | ✓ 每一轮都在系统提示词里 |
| 敏感词替换（破解→白盒鉴权脆弱性测试 等 28 条） | ✗ | ✓ |
| 补合规前缀（命中审计词时） | ✗ | ✓ |
| 认 `lab：` / `退出实验` 口令 | ✗（总闸关时） | ✓ |
| MCP 工具 / 技能 | ✓ 一直可用 | ✓ |

**替换只发生在「发给模型的那一份消息」上**，聊天界面里永远显示你打的原文 ——
所以肉眼看不到替换是正常的。要自证：

- 小卡片里「最近一次改写」会显示 原 / 改 两行（改写过的才会出现）
- `GET /seep-workbench/api` 的 `lab.rewrites` 是累计次数、`lab.lastRewrite` 是最近一次
- 日志：启动时设 `SEEP_LAB_DEBUG=1`，会打出 `[lab] 改写前 / 改写后`

### Lab 模式开关（点了就进 / 点了就出）

三处都能切，等价：

| 位置 | 形态 |
| :--- | :--- |
| 小卡片（点 ● Seep） | `Lab 工作台模式  未进入 [开启]` |
| 设置 → Seep 工作台 | 配置区里的「当前：不在 lab 模式 [进入 lab]」 |
| 对话框 | 发 `lab：` 进入，发 `退出实验` 退出 |

语义分两层，别再混：

- **总闸**（配置里的「允许 lab 模式」，持久化）：关掉后连 `lab：` 口令都不认，什么都不触发。
- **运行时开关**（内存，不持久化）：切换立刻生效，**不用重启**。
  打开后当前会话立刻注入纪律，之后新建的会话也继承；关掉立刻停止注入。

只有一样东西要重启：**工作台路径换位置**（MCP 连接是启动时建立的）。

### 三个入口（同一个面板/状态）

| 入口 | 位置 | 适合 |
| :--- | :--- | :--- |
| **小圆点 Seep** | 新会话时输入框上方那行（工作区 / 标准模式 旁边），有对话时在输入框右侧 | **平时最常用**：一眼看状态，点开看明细 |
| 设置 → Seep 工作台 | 设置左侧导航 | 改路径、看全部 20 个工具、给单个工具指定路径 |
| 设置 → 插件 → 本包 → 配置 | 插件列表 | 同上（DSH 给的官方位置） |

小圆点的颜色就是结论：**绿=就绪，黄=能跑但有工具缺，红=没接上**。

点开的小卡片里显示：版本、已接线哪几路、lab 开关状态、工具有几个就绪/缺哪些、仓库路径，
外加「重新检查」和「复制校验命令」。

### 工具装在别处怎么办

绝大多数人的工具不在我们猜的那些路径上。三层处理，从自动到手动：

1. **自动找**：`setup/tool-registry.json` 里每个工具都有一串候选
   （环境变量 → 候选目录 → 仓库内置 → PATH），面板上「找到：bundled / candidates / path」就是这个结果
2. **环境变量**：`SEEP_PYTHON` / `SEEP_IDA_ROOT` / `SEEP_NODE` 等，见注册表每项的 `env`
3. **人工指定**（对所有 20 个工具都有效）：

```powershell
python Tool/mcp/tool_resolver.py --set jadx "D:/tools/jadx/bin/jadx.bat"
python Tool/mcp/tool_resolver.py --set radare2 "D:/tools/radare2/bin"
python Tool/mcp/tool_resolver.py --clear jadx          # 恢复自动查找
```

或者在面板里点某个工具的「指定路径」，填完保存 —— 写的是同一个文件：

```
<仓库>/setup/tool-paths.local.json      # 已在 .gitignore，不会提交，也不泄漏本机路径
```

人工路径排在整条链**最前面**；填错了会在面板里标出来并继续往下找，不会把工具判死。

> 那条「路径不存在」的提示是刻意留的：填错比找不到更值得提醒。

### 设置面板（1.14.0 起）

插件带一个浏览器侧的面板，在 DSH 网页里能直接看到状态、改配置。
两个入口，同一个组件：

| 入口 | 位置 | 宿主传什么 |
| :--- | :--- | :--- |
| 独立一页 | 设置 → **Seep 工作台** | 不传，组件自己从 `ctx.configForms` 取 |
| 插件行配置 | 设置 → 插件 → `seep-dsh-workbench` → 「配置」 | 传 `{ view, form: { state, mutate } }` |

面板显示三块：

1. **运行状态** —— 就绪/未就绪、仓库版本、已接线哪些、当前工作台路径；
   失败时直接给出可复制的修复命令（比如「路径不存在，先 git clone」）。
2. **配置** —— 工作台路径、Python、技能开关、lab 开关。改完点保存，
   写回 profile 的 `cordis.patch.yml`（走 DSH 官方 configForms/config-editor 通道）。
3. **工具清单** —— 20 个工具逐个标 ✅READY / ⚠️DEGRADED / ○OPTIONAL / ❌MISSING。
   默认「快速检查」（只看找没找到）；点「深度检测」会真的启动每个工具验一遍
   （调 `Tool/mcp/tool_resolver.py --verify`）。

实现要点（自己改的时候别踩）：

- 面板是**浏览器侧**的一半：`package.json` 里 `dsh.client` 声明 + `exports["./client"]`
  指向 `lib/client.js`，格式必须是客户端模块系统的懒加载 CJS 工厂
  （`window.__ModuleLoader__.load({ id, factory: (require) => ... })`）。
- 宿主侧在 `lib/index.js` 里注册了只读接口 `GET /seep-workbench/api`
  （只放本机回环访问）。浏览器读不到磁盘，工具在不在只有宿主知道 —— 所以绕这一趟。
- **配置字段必须声明 `.volatile()`**。DSH 只把 volatile 字段投影到设置表单，
  普通字段根本进不了表单，面板就既看不到也改不了。宿主里要用 `config.x.get()` 取值。
- keyed 槽位的注册用 `key`（不是 `id`），值是 `<包名>#<行 id>`。
- `ConfigForm` 要**每次渲染重新取**：保存后 profile 会重载，旧控制器被销毁，
  拿旧对象再写会报 `writeGeneration undefined`。
- 改完配置**不会**自动重挂 MCP —— 路径类改动需要重启 DSH；
  技能 / lab 开关对下一个会话生效。面板上已写明这一点。

### Skill 图层（默认开启）

DSH 自带 skill 机制 —— `dsh-skill-filesystem`（发现）+ `dsh-tool-skill`（模型侧加载），
只是 `web` profile 里默认 `disabled: true`。工作台会在补丁里显式打开它，
把两个技能根挂进去，让 DSH 看到与 pi 相同的 10 个技能：

```yaml
- id: skill-filesystem
  disabled: false
  config:
    customSkillDirs:
      - '<repo>/Tool/skill'            # apkseep exe-reverse softseep webseep client-license-...
      - '<repo>/Tool/skill/safe-skills' # apk-reverse ida-reverse mcp-js-reverse-playbook radare2 reverse-engineering
- id: tool-skill
  disabled: false
```

| 控制方式 | 命令 | 效果 |
| :--- | :--- | :--- |
| 默认（开启） | `install.ps1` / `install.sh` | 10 个技能可被发现 |
| 关闭整层 | `install.ps1 -DshSkills none`<br>`install.sh --no-dsh-skills` | 不写 skill 块，省上下文 |
| 事后改 | `python setup/generate-configs.py --root . --dsh-skills {all,none}` → 重跑 `dsh-merge.py` | 重写补丁块 |

> **代价**：10 个技能的 `name + description` 会进入每个会话的上下文。
> `customSkillDirs` 是「扫该目录下的直接子目录」，**无法只挑其中几个** ——
> 要少挂只能关整层，或在仓库外自建一个只含所需技能的根目录。

### 隔离部署（不动 Pi Agent）

如果只想在一个独立文件夹里玩 DSH，不想碰 `~/.pi/agent` 的 skill 与 mcp.json：

```powershell
powershell -File setup\dsh-isolated-setup.ps1                 # 默认落到 Desktop\dsh-lab
powershell -File setup\dsh-isolated-setup.ps1 -LabDir "D:\dsh-lab"
```

它自举独立的 `DSH_HOME`、生成配置、挂载补丁、端到端验证，并在前后各拍一张
pi agent 指纹快照做比对（`setup/pi-agent-snapshot.py`）。**不会**运行
`install-pi.ps1` / `install-ida.ps1`，所以 `~/.pi/agent` 一个字节都不会变。

启动时带上隔离的 DSH_HOME：

```powershell
$env:DSH_HOME = "<LabDir>\.dsh"
dsh --profile web
```

> 隔离 DSH_HOME 是全新的，**没有登录态**：首次启动需在 DSH 里重新登录，
> 或自行把 `~/.dsh/.credentials.yaml` 复制过去（脚本不代劳，避免搬运凭据）。

### 卸载

```bash
python setup/dsh-merge.py --remove      # 只移除标注块，其余配置不动
```

---

## 二、 配置字段（DSH 0.2.2 实际支持的）

`dsh-mcp-client` 的一条 stdio 配置：

| 字段 | 必填 | 默认 | 说明 |
| :--- | :---: | :--- | :--- |
| `transport` | ✅ | — | `stdio` 或 `streamable-http` |
| `serverName` | ✅ | — | 工具命名空间，须匹配 `[A-Za-z0-9_-]{1,32}`，同一作用域内唯一 |
| `command` | ✅ | — | 可执行文件（stdio） |
| `args` | — | `[]` | 参数，**不经 shell 解释** |
| `env` | — | `{}` | 追加到「清洗过的环境」之上（不是替换） |
| `cwd` | — | — | 子进程工作目录 |
| `toolCallTimeoutMs` | — | **60000** | 单次 `tools/call` 超时 |
| `failOnStartupError` | — | `false` | 初始连接失败时是否拒绝插件激活 |
| `maxInstructionBytes` | — | 32768 | 服务端指令的 UTF-8 字节上限 |
| `reconnect.*` | — | 自动重连 | `enabled` / `initialDelayMs` / `maxDelayMs` / `maxAttempts` |

> ⚠️ **`toolCallTimeoutMs` 必须显式设置。** DSH 默认 60 秒，而本工作台的长任务远超这个量级：
> HLS 取证（ffmpeg 解密分片）、Flutter AOT 分析、jadx 全量反编译都可能跑几分钟。
> 生成器已写死 `900000`（15 分钟）；`js-reverse` 为 `600000`。
> 不设就会表现为「工具跑到一半突然返回超时」，而且日志里看不出是 DSH 掐断的。

---

## 三、 生成物长什么样

旧路线（`dsh-merge.py`）的生成物 `setup/cordis.generated.yml`：

```yaml
- insert:
    - id: seep-mcp
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: seep
        transport: stdio
        command: python                      # 持久挂载时会被替换成解析出的绝对路径
        args:
          - '<工作台绝对路径>/Tool/mcp/seep_mcp_server.py'
        env:
          PYTHONIOENCODING: utf-8
        cwd: '<工作台绝对路径>'
        toolCallTimeoutMs: 900000
        failOnStartupError: false

    - id: seep-js-reverse-mcp
      name: '@deepseek-ai/dsh-mcp-client'
      config:
        serverName: js-reverse
        transport: stdio
        command: npx
        args: ['-y', 'js-reverse-mcp']
        cwd: '<工作台绝对路径>'
        toolCallTimeoutMs: 600000
        failOnStartupError: false
```

- 生成物里 `command: python` 是为了**可移植**（该文件会入库）。
- `setup/dsh-merge.py` 落盘时会把它换成**真的能 `import mcp` 的解释器绝对路径**，
  避免用户在 DSH 里踩到「`python` 指向没装 mcp 的解释器」。
- `cordis.patch.yml` 顶层就是「补丁条目数组」，而生成物本身也是数组，
  所以追加即合法合并 —— 不需要 YAML 解析器，也不会动到你的既有条目。

插件包路线（1.14.0 起）的补丁只有一条，其余全在代码里：

```yaml
# packages/dsh-workbench/cordis.patch.yml
- insert:
    - id: seep-workbench-boot
      name: 'seep-dsh-workbench'
```

MCP 条目与技能层由 `lib/index.js` 在运行时用 `ctx.plugin()` 挂：

```js
ctx.plugin(McpClient, { serverName: 'seep', command: python, args: [入口脚本],
                        cwd: repoRoot, toolCallTimeoutMs: 900000, failOnStartupError: false });
if (enableSkills) {
  ctx.plugin(SkillFilesystem, { customSkillDirs: [`${repoRoot}/Tool/skill`,
                                                  `${repoRoot}/Tool/skill/safe-skills`] });
  ctx.plugin(ToolSkill, {});
}
```

于是「仓库搬家」只需重跑一次 `dsh-plugin-setup.py --root <新位置>`，
不需要改生成物、也不需要手工编辑 YAML 里的绝对路径。

---

## 四、 校验

插件包路线下，最直接的判据是插件自己写的状态文件：

```bash
cat "$DSH_HOME/seep-workbench.status.json"     # Windows: type %USERPROFILE%\.dsh\seep-workbench.status.json
# {"ok":true,"repoRoot":"...","version":"1.14.0",
#  "python":"...python.exe","mounted":{"seep":true,"jsReverse":true,"skills":true},
#  "skillsEnabled":true,"labGate":true,"lines":[]}
```

```bash
# 1. 完整度评分（6 组 / 24 项 / 100 分，输出百分比与缺失清单）
python setup/verify-dsh.py

# 2. 插件有没有挂上（合成配置里应有 seep-workbench-boot）
dsh --profile web --dump-config | grep -A3 "seep-workbench-boot"

# 3. lab 开关单测（不需 DSH、不需模型，纯逻辑）
node packages/dsh-workbench/test/lab-gate.test.mjs

# 4. 旧路线的自查（只在用 dsh-merge.py 时有意义）
python setup/dsh-merge.py --check
python setup/test_dsh_mount.py
```

`check.ps1` / `setup/verify.sh` 也会检查：
项目根 `AGENTS.md` 与源同步、Cordis 生成物结构合法、DSH 已装时是否已挂载。

---

## 五、 指令来源（AGENTS.md）

`dsh-agent-instructions` 会按「宽泛 → 具体」的顺序加载：
`$DSH_HOME/AGENTS.md` → `~/.agents/AGENTS.md` → 项目根到会话目录每一层的
`AGENTS.md`（Pi 读的是 `~/.pi/agent/AGENTS.md`）。

所以本工作台做了两件事：

1. **项目根 `AGENTS.md`** —— 由 `setup/generate-configs` 从 `Tool/prompts/AGENTS.md`
   复制生成（逐字节一致，`verify` 会查漂移）。DSH 从项目根读它，无需手工 `cp`。
2. Pi 走另一条：`~/.pi/agent/AGENTS.md`，由 `install-pi.ps1` 同步。

> Pi 与 DSH 加载的是**两份不同的文件**，各自生效，互不干扰。

---

## 六、 与 Pi Agent 的对照

| | Pi Agent | DeepSeek Harness |
| :--- | :--- | :--- |
| 配置文件 | `~/.pi/agent/mcp.json` | `$DSH_HOME/profiles/<p>/cordis.patch.yml` |
| 挂载方式 | `install-pi.ps1` 写入，解释器为解析后的绝对路径 | 插件包在运行时挂；旧路线 `dsh-merge.py` |
| 技能 | 拷贝到 `~/.pi/agent/skills` | 插件直接指向仓库两个目录 |
| 校验 | `setup/verify.ps1` | `setup/verify-dsh.py` |

细节见 [MANUAL/AGENTS.md](MANUAL/AGENTS.md)。

---

## 七、 约束与边界

- **lab 开关只管提示词，不管工具可用性。** 无论开不开 lab，`seep` 的 38 个工具
  都挂在模型眼前；lab 开关只决定「要不要把 `Tool/prompts/SYSTEM.md` 的纪律正文
  注入这个会话的系统提示词」。跟 pi 侧强度一致，不夸大。
- **lab 状态只在内存里。** 进程退出即清，不写磁盘；新会话、`resume`、
  `compact` 都从关闭开始。A 窗口开不影响 B 窗口。
- **插件自检失败不抛异常**（除非 `strict: true`）。路径没填、工具没下载这类问题
  只打印修复提示，绝不让整条 profile 起不来。
- 不搬动 `Tool/mcp/Tool/` —— `seep_mcp_server.py` 内部按相对路径解析运行时依赖。
- IDA Pro 需自备授权；无授权时自动由内置 Radare2 承接。
- 所有测试目标须确认已获授权（G-Auth 门）。
- **平台边界**：8 个 `seep_web_*` 工具依赖 PowerShell 取证脚本（Unix 需装 pwsh），
  `seep_aotopsy` 是 Windows PE 单文件（Unix 不适用）。详见
  [MANUAL/CROSS-PLATFORM.md](../MANUAL/CROSS-PLATFORM.md)。
- 部署与排障详见 [MANUAL/DEPLOYMENT.md](../MANUAL/DEPLOYMENT.md)。
