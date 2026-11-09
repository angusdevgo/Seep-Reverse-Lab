# 更新与发布：谁更新什么、顺带更新什么

> 这份文档把「插件发到哪、以后怎么更新、更新时连带什么」一次说清。
> 面向两类人：**维护者**（发版）与**使用者**（跟进更新）。
>
> 相关文档：[PUBLISHING.md](PUBLISHING.md)（发版纪律）· [AGENTS.md](AGENTS.md)（Pi 与 DSH 的差异）

---

## 一、先抓住一个模型：三层，各自独立

整个工作台不是「一个东西」，是**三个不同速度的层**：

```
┌─────────────────────────────────────────────────────────┐
│  接线层   30 KB    packages/dsh-workbench/              │
│                   把 MCP / 技能 / lab 挂到 DSH 上的代码 │
│                   走 npm，有版本号，能自动更新           │
├─────────────────────────────────────────────────────────┤
│  内容层   16 MB    Tool/skill/  kb/  Tool/cases/         │
│                   技能、知识库、脱敏案例                 │
│                   走 git，跟着仓库走                     │
├─────────────────────────────────────────────────────────┤
│  工具层  561 MB    Tool/mcp/Tool/safe/                  │
│                   jadx / apktool / radare2 / frida …     │
│                   走官网下载，永远不进任何包             │
└─────────────────────────────────────────────────────────┘
```

**为什么必须分开**：工具层 561 MB，塞进 npm 包等于每次发版让所有人重下 561 MB，
而且这些二进制本来就有自己的版本与许可证。接线层改一行就要发版，混在一起也不能用。

---

## 二、发布渠道（已确认）

**双发，主备分明。**

| 渠道 | 地址 | 作用 |
| :--- | :--- | :--- |
| **npm（主）** | `npmjs.com/package/seep-dsh-workbench` | 唯一能让「面板→更新插件」按钮生效的渠道 |
| **GitHub Release（备）** | `github.com/angusdevgo/Seep-Reverse-Lab/releases` | 挂同一份 `.tgz`，sha256 与 npm 一致 |

**为什么主渠道必须是 npm**：DSH 的 `dsh plugin add` 底层转发给 pnpm。
装 npm 上的包，pnpm 才会记下版本号、才知道「有新版可拉」；
装本地目录或本地 tgz，pnpm 只记 `file:...`，**没有远端可比，永远拉不到新版**。

> 这是机制限制，不是设计选择。想让「更新插件」按钮可用，只有 npm 这条路。

---

## 三、三种安装模式，三种更新方式

### 模式 A：本地目录（`file:`）—— 开发用

```json
// ~/.dsh/profiles/web/package.json
"dependencies": {
  "seep-dsh-workbench": "file:C:/Users/Angus/Desktop/dsh-seep/packages/dsh-workbench"
}
```

| 改了什么 | 怎么生效 |
| :--- | :--- |
| `lib/*.js`（插件代码） | 重启 DSH 就生效（硬链接，同一个 inode） |
| 仓库里的技能 / 知识库 / 案例 | `git pull`，新会话生效 |
| 工具 | `git pull` + 重启 DSH |

- ✅ 改代码立刻验证，不用发版
- ❌ 面板「更新插件」**灰色不可点**
- ❌ `dsh plugin update` → `Already up to date`（没有远端）

### 模式 B：npm —— 使用者默认

```json
"dependencies": { "seep-dsh-workbench": "^1.15.0" }
```

| 改了什么 | 怎么生效 |
| :--- | :--- |
| 插件代码 | 面板「更新插件」或 `dsh plugin add --profile web seep-dsh-workbench@latest` |
| 技能 / 知识库 / 案例 | 面板「更新工作台」（`git pull`）或手动 `git pull` |
| 工具 | 同上，然后**重启 DSH** |

- ✅ 面板两个按钮都能点，能自动更新
- ⚠️ **要点两下**：插件和工作台是两份不同的东西（详见下节）
- ❌ 改 `lib/*.js` 不生效，必须发新版

### 模式 C：本地 tgz

```bash
dsh plugin add --profile web "file:C:\...\seep-dsh-workbench-1.15.0.tgz"
```

- ✅ 内网 / 无 npm 环境可用
- ❌ 无自动更新，换版要重新下载 tgz 再装一次

> **不能混用**：A、B、C 三选一。同时存在会挂两份 MCP，
> 表现为工具列表里每个工具出现两次 —— `verify-dsh.py` 的 A6 项专查这个。

---

## 四、更新什么：插件包里到底装了什么

发出去的 `.tgz` **只有接线代码，7 个文件、31.7 KB**：

```
package.json          声明 dsh.bundle / engines / 版本号
cordis.patch.yml      加载链里插的那一条
lib/index.js          挂 MCP、读配置、起面板、管更新
lib/lab-gate.js       lab 开关（两会话级状态机）
lib/lab-rewrite.js    词替换（读 sensitive-rules.json）
lib/client.js         设置面板 + 输入框旁小圆点
README.md             说明
```

**明确不进包**：

| 不进包的东西 | 理由 |
| :--- | :--- |
| `Tool/mcp/Tool/safe/`（561 MB 工具） | 二进制有自己版本与许可证，且体积压垮发版 |
| `Tool/skill/`、`kb/`、`Tool/cases/`（16 MB 内容） | 更新频率与代码不同，改一篇文档不该发版 |
| `Tool/prompts/SYSTEM.md`（纪律正文） | 同上，属于内容层 |
| 任何绝对路径、令牌、本机配置 | 脱敏红线 |

---

## 五、顺带更新矩阵（最容易搞错的一节）

**问题**：我 `git pull` 了，为什么还是旧的？

因为「更新」不是一件事，是四件事：

| 你改 / 更新了 | pipi… 应该做 | DSH 应该做 |
| :--- | :--- | :--- |
| 插件代码（`packages/dsh-workbench/`） | 不适用 | 模式 A：重启；模式 B：**发新版后**点「更新插件」 |
| 技能（`Tool/skill/**`） | `git pull` **+ 重跑 `install-pi.ps1`**（pi 是拷贝的） | `git pull`，**新会话**生效（直接指仓库） |
| 知识库 / 案例（`kb/`、`cases/`） | `git pull` + 重启 pi | `git pull`，立即生效（MCP 每次查盘） |
| 工具本体（`Tool/mcp/Tool/safe/`） | `git pull` + 重启 pi | `git pull` + **重启 DSH**（MCP 是启动时拉起的） |
| `tool_registry`、`tool-paths` | 重跑 `install-pi.ps1` | 面板改，**重启 DSH** |
| 纪律正文（`Tool/prompts/SYSTEM.md`） | 重跑 `install-pi.ps1`（拷到 `~/.pi/agent/`） | `git pull`，新会话生效（插件每次读文件） |
| 项目根 `AGENTS.md` | 不适用 | `generate-configs` 重新生成，新会话生效 |

**一句话记住**：

> `git pull` 对两边都必要，但**不是充分**。
> pi 侧最常漏「只 pull 不重跑 install-pi」（技能还是旧的）；
> DSH 侧最常漏「pull 了但没重启」（MCP 还是旧进程）。

---

## 六、npm 模式为什么要点两下

面板上有两个按钮，看着像重复，其实分工完全不同：

| 按钮 | 动作 | 更新 | 不更新 |
| :--- | :--- | :--- | :--- |
| **更新插件** | `dsh plugin add ...@latest` | 30 KB 接线代码 | 技能、知识库、案例、工具 |
| **更新工作台** | `git pull` 你的仓库 | 内容层 + 工具层 + 文档 | 插件代码 |

所以使用者要「拿全最新」= **两个都点**，顺序无所谓，最后重启一次 DSH。

> 模式 A（本地目录）下两个按钮是同一件事，因为插件本身就在那个仓库里。

---

## 七、发版 Runbook（维护者）

发布前四道门必须全绿：

```bash
node packages/dsh-workbench/test/lab-gate.test.mjs      # 39 项单测
python setup/verify-dsh.py                              # 100 / 100
powershell -File setup/verify.ps1                       # 64 项
python setup/pack-plugin.py --check                     # 版本三处一致
```

然后：

```bash
# 1. 升版本（三处必须一致）
#    VERSION
#    packages/dsh-workbench/package.json  → version
#    CHANGELOG.md                          → 加 ## [x.y.z] 段

# 2. 打包（只产出 tgz + 打印 sha256，绝不自动发布）
python setup/pack-plugin.py
#   → dist/seep-dsh-workbench-x.y.z.tgz

# 3. 试装（可选，建议每次做）
dsh plugin add --profile webtest "file:<tgz 绝对路径>"

# 4. 发布
npm publish packages/dsh-workbench --access public

# 5. 打 GitHub Release，挂同一份 tgz
gh release create vx.y.z dist/seep-dsh-workbench-x.y.z.tgz --notes-file CHANGELOG.md
```

**`pack-plugin.py` 永不自动发布** —— 它只打包、只打印 sha256。发布是人的动作。

---

## 八、切到 npm 模式（本机验收用）

前提：**npm 上已经有包**。没发布之前切不了。

```bash
# 1. 卸掉本地目录装法（关键：必须彻底移除，否则挂两份）
dsh plugin remove --profile web seep-dsh-workbench

# 2. 从 npm 装
dsh plugin add --profile web seep-dsh-workbench

# 3. 确认装法已变
cat ~/.dsh/profiles/web/package.json | grep seep-dsh

# 4. 重启 DSH，跑校验
python setup/verify-dsh.py    # 应仍是 100 / 100
```

### 回退（想继续改代码时）

```bash
dsh plugin remove --profile web seep-dsh-workbench
dsh plugin add --profile web "file:<仓库>/packages/dsh-workbench"
```

切换后必须**重启 DSH**，并确认状态文件里 `mounted` 没有重复项。

---

## 九、版本号约定

**插件版本 = 仓库版本**，一个数字，不要两套。

```
VERSION                              → 1.15.0
packages/dsh-workbench/package.json  → 1.15.0
CHANGELOG.md                         → ## [1.15.0]
```

`pack-plugin.py --check` 会强制这三处一致，不一致直接拒绝打包。

semver 规则（摘要，详见 PUBLISHING.md）：

| 改动 | 版本位 | 例子 |
| :--- | :--- | :--- |
| 修 bug、改文案 | patch | 1.15.0 → 1.15.1 |
| 加功能、加配置项（向后兼容） | minor | 1.15.1 → 1.16.0 |
| 改配置字段语义、改 lab 行为 | **major + 写迁移说明** | 1.16.0 → 2.0.0 |

**配置字段只增不删**，lab 语义永不改变 —— 这两条是兼容性红线。

---

## 十、已确认的四条（本次定案）

| # | 问题 | 定案 |
| :--- | :--- | :--- |
| 1 | 插件传到哪 | **npm 公共库（主）+ GitHub Release（备，同一份 tgz）** |
| 2 | 以后怎么更新 | npm 装：面板「更新插件」；内容：面板「更新工作台」；工具：`git pull` + 重启 |
| 3 | 更新什么 | 插件包只有 **30 KB 接线**；内容 16 MB 与工具 561 MB 都不进包 |
| 4 | 顺带更新什么 | `git pull` 只解决内容与工具；**pi 要重跑 `install-pi.ps1`，DSH 要重启** |

> 顺序约束：**先推代码 → 再发 npm → 才切 npm 装法做验收**。
> npm 上没有包之前，「更新插件」按钮不可能可用。
