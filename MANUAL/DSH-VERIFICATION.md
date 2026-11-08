# DSH 部署完整度校验（DSH-VERIFICATION.md）

> **用途**：工作台部署到 DeepSeek Harness 之后，用这份文档判断「部署全了没有、缺什么」。
> **配套脚本**：`setup/verify-dsh.py`（可自动跑完整张表并给出百分比）。
>
> **最重要的一条**：本文的**分母是「DSH 上本来应该有什么」**，不是「Pi Agent 上有什么」。
> DSH 没有 skill 加载器，所以 10 个 skill 按 **N/A** 处理，不计入分母。
> 用 pi 的 135 个工具 / 10 个 skill 去要求 DSH，任何部署都会被算成「缺了 70%」，
> 那是错的。

---

## 一、DSH 与 Pi 的预期差异（核对前必读）

| 维度 | Pi Agent | DSH | 说明 |
| :--- | :---: | :---: | :--- |
| MCP 服务 | 4 | **2** | DSH 默认只挂 `seep` + `js-reverse` |
| MCP 工具 | 135 | **62** | 差的是 `ida`(48) + `playwright`(25) |
| Skill | 10 | **0** | DSH 无 skill 机制，靠 `AGENTS.md` 指令层 |
| 纪律注入 | 扩展自动注入 | **模型自己读** `Tool/prompts/SYSTEM.md` | 指令层，非代码层强制 |

`ida` / `playwright` 想挂进 DSH 也可以（改 `dsh-merge.py --ida-root`），但**不属于默认基线**，
本文把它们归入「可选能力」，不计分。

---

## 二、评分表（满分 100）

### 第 1 组 · 配置层（25 分）

| 编号 | 检查项 | 分值 | 判据 | 采集方式 |
| :---: | :--- | :---: | :--- | :--- |
| A1 | `cordis.patch.yml` 含 `seep-workbench` 标记块 | 6 | 文件里能找到 `>>> seep-workbench` | 读 `$DSH_HOME/profiles/<p>/cordis.patch.yml` |
| A2 | 合成配置里有 `serverName: seep` | 6 | `dsh --dump-config` 输出包含该行 | `dsh --profile web --dump-config` |
| A3 | 合成配置里有 `serverName: js-reverse` | 5 | 同上 | 同上 |
| A4 | `seep` 的 `toolCallTimeoutMs` ≥ 300000 | 4 | 正则取数值比对 | 同上 |
| A5 | `seep` 的 `cwd` 指向仓库根 | 2 | 等于 `<repo>` | 同上 |
| A6 | `failOnStartupError: false` | 2 | 出现该行 | 同上 |

> **A4 为什么必须查**：DSH 默认超时是 **60000（60 秒）**。jadx 全量反编译、HLS 分片解密、
> Flutter AOT 分析都会跑几分钟，不显式设成 900000 就会被 DSH 按超时杀掉，
> 表现为「工具调用莫名中断」，极难排查。
>
> **A5 为什么必须查**：`seep_mcp_server.py` 用**相对路径** `Tool/mcp/Tool/safe/...` 定位
> 内置工具。`cwd` 不对，`seep_status` 会报一堆 MISSING，但文件其实都在。

### 第 2 组 · MCP 可用性（30 分）★ 核心

| 编号 | 检查项 | 分值 | 判据 |
| :---: | :--- | :---: | :--- |
| B1 | `seep` 能 `initialize` | 8 | 按合成配置真启动，收到 `result` |
| B2 | `seep` `tools/list` = **38** 个工具 | 10 | 工具数组长度 ≥ 38 |
| B3 | `js-reverse` 能 `initialize` | 6 | 同上 |
| B4 | `js-reverse` `tools/list` ≥ **24** | 6 | 工具数组长度 ≥ 24 |

这一组是**唯一能证明「真的能用」**的部分。前一组看的是配置文本，
这一组是**真启动进程、真发 JSON-RPC、真数工具**。

> 判定「成功启动」的标准：能收到 `initialize` 的 `result`，且 `tools/list` 返回非空数组。
> **只看进程没退出是不够的** —— 服务可能起来但握手失败。

### 第 3 组 · 仓库资产（20 分）

| 编号 | 检查项 | 分值 | 期望 |
| :---: | :--- | :---: | :--- |
| C1 | 内置二进制工具箱 5 件齐 | 6 | `Tool/mcp/Tool/safe/` 下 jadx / apktool / radare2 / playwright-mcp / js-reverse-mcp |
| C2 | 知识库篇数 | 5 | ≥ 294 篇 `.md` |
| C3 | 脱敏案例数 | 3 | ≥ 14 个目录 |
| C4 | `MANUAL/` 手册 | 3 | ≥ 7 份 `.md` |
| C5 | 技能源目录 | 3 | 10 个唯一名（DSH 不加载，但内容是纪律与知识的来源） |

### 第 4 组 · 指令层（15 分）

| 编号 | 检查项 | 分值 | 判据 |
| :---: | :--- | :---: | :--- |
| D1 | 仓库根 `AGENTS.md` 存在 | 5 | DSH 启动时自动读取 |
| D2 | 根 `AGENTS.md` 与 `Tool/prompts/AGENTS.md` 一致 | 5 | 内容完全相同（无漂移） |
| D3 | `Tool/prompts/SYSTEM.md` 存在 | 5 | 用户发 `lab：` 时模型要读的那份 18 KB 纪律 |

### 第 5 组 · 运行时（10 分）

| 编号 | 检查项 | 分值 | 判据 |
| :---: | :--- | :---: | :--- |
| E1 | Python 能 `import mcp` | 6 | 真执行 `python -c "import mcp"` 返回 0 |
| E2 | Node 可用 | 4 | `node --version` 返回 0 |

---

## 三、怎么跑

```powershell
# 完整校验（会真启动两个 MCP，约 10–30 秒）
python setup\verify-dsh.py

# 只看配置，不启动（快，但 B 组会记为失败）
python setup\verify-dsh.py --skip-spawn

# 换 profile
python setup\verify-dsh.py --profile tui

# 机器可读
python setup\verify-dsh.py --json
```

Linux / macOS 同样适用（脚本纯标准库）。

退出码：`0` = 全部通过；`1` = 有缺失；`2` = PATH 里找不到 `dsh`。

### 输出样例（本机实测，100%）

```
【配置层】   A1..A6   25/25
【MCP 可用性】B1..B4   30/30     seep 38 工具 / js-reverse 24 工具
【仓库资产】 C1..C5   20/20
【指令层】   D1..D3   15/15
【运行时】   E1..E2   10/10
------------------------------------------------------------------
完整率  ████████████████████████████████████████  100.0%   (100 / 100 分)
```

---

## 四、分数怎么解读

| 完整率 | 含义 | 该怎么办 |
| :---: | :--- | :--- |
| **100%** | 配置、MCP、资产、指令、运行时全部就位 | 可以开工 |
| **85–99%** | 核心链路通，缺的是次要资产（KB 篇数、案例数等） | 重新克隆仓库补齐 |
| **60–84%** | 缺 MCP 或运行时，工具基本用不了 | 看「缺失清单」逐项修 |
| **< 60%** | 配置层就没挂上 | 先跑 `python setup/dsh-merge.py --profile web` |

### 完整的含义边界

100% **只说明「配置与资产就位」，不说明「模型会遵守 `lab：` 闸门」**。

后半句是指令层的事：

- DSH 读到 `AGENTS.md` 后**应该**在用户发 `lab：` 时去读 `Tool/prompts/SYSTEM.md`；
- 但这是**指令约束**，不是代码强制。模型换一个、上下文压缩、长对话漂移，都可能失效；
- 想抽验：开一个 DSH 会话，**不发 `lab：`**，直接问「这个 APK 是怎么校验会员的？」，看它是否
  只讲原理而不动手。再发 `lab：` 重问，看它是否会先读 `SYSTEM.md` 再作答。

---

## 五、常见缺项与修复

| 症状 | 根因 | 修复 |
| :--- | :--- | :--- |
| A1 全组 FAIL | 没挂载 | `python setup/dsh-merge.py --profile web` |
| A2/A3 FAIL 但 A1 PASS | profile 名不对（挂到了别的 profile） | `--profile <你启动的那个>`，或 `--global` |
| A4 FAIL | 手改过补丁，把 timeout 删了 | 重跑 `dsh-merge.py`（会重写整块） |
| A5 FAIL | 仓库被移动/复制过，`cwd` 是旧路径 | 重跑 `dsh-merge.py`（按当前 `--root` 重算） |
| B1 FAIL，报 `ImportError: mcp` | `seep` 用的解释器没装 mcp | `powershell -File setup\install-python.ps1`，或设 `SEEP_PYTHON` |
| B2 工具数 < 38 | 启动的是旧副本 | 确认 `args` 指向当前仓库的 `seep_mcp_server.py` |
| B3/B4 FAIL | `npx js-reverse-mcp` 网络/缓存问题 | 先手动跑一次 `npx -y js-reverse-mcp` 预热 |
| C1 缺目录 | 克隆不完整 | 重新 `git clone`（`node_modules` 由 `install` 解压） |
| D2 FAIL | 改过根 `AGENTS.md` 没同步源 | `python setup/generate-configs.py --root .` |
| E1 FAIL | `python` 指向没装 mcp 的解释器 | 同上，或用 `setup\resolve-tools.ps1 -Tool python -Verify` 定位 |

---

## 六、可选能力（不计入分母）

这些装了更好，没装不影响主链路，状态只会是 `OPTIONAL` / `DEGRADED`：

| 工具 | 用途 | 补全命令 |
| :--- | :--- | :--- |
| `ida` | 商业反编译（DSH 默认未挂） | `powershell -File setup\install-ida.ps1 -IdaRoot <目录>` |
| `playwright` | 浏览器自动化（DSH 默认未挂） | 需要时改 `dsh-merge.py` 追加条目 |
| `ffmpeg` | HLS 取证 | `setup\install-capabilities.ps1 -Only web` |
| `frida` / `objection` | 动态插桩 | `-Only android` |
| `apkid` | 查壳 | `-Only android` |
| `aotopsy` | Flutter AOT（Windows only） | `-Only aotopsy`（仓库自带） |

单项四态可用 `setup\resolve-tools.ps1 -Verify` 单独查。

---

## 七、与 Pi 侧的一致性核对（可选）

想确认「DSH 少了什么」而不是「DSH 坏了什么」时，两边各跑一次：

```powershell
# DSH 侧
python setup\verify-dsh.py

# pi 侧
powershell -File setup\verify.ps1 -Detailed

# 工具级逐个实探（两边通用，可指定任意 mcp.json）
python setup\probe-mcp.py
python setup\probe-mcp.py --config <别的 mcp.json> --only seep,js-reverse
```

对照关系：

| 项目 | pi 应有 | DSH 应有 | 差异性质 |
| :--- | :---: | :---: | :--- |
| MCP 服务 | 4 | 2 | 架构决定（`ida`/`playwright` 可选挂） |
| MCP 工具 | 135 | 62 | 同上 |
| Skill | 10 | 0 | 架构决定（DSH 无 skill 机制） |
| 纪律注入 | 自动 | 手动读文件 | 架构决定 |

**只要这三处差异之外还有缺失，才是真的部署问题。**
