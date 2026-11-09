# DSH 部署完整度校验（DSH-VERIFICATION.md）

> **用途**：工作台部署到 DeepSeek Harness 之后，用这份文档判断「部署全了没有、缺什么」。
> **配套脚本**：`setup/verify-dsh.py`（自动跑完整张表并给出百分比）。
>
> **分母是「DSH 上本来应该有什么」。** DSH 与 pi 的架构差异（skill 图层默认关闭、
> 可选 MCP 未挂）属于设计选择，不算缺失；只有该有的没有，才扣分。

---

## 一、DSH 与 Pi 的预期差异

| 维度 | Pi Agent | DSH | 差异性质 |
| :--- | :---: | :---: | :--- |
| MCP `seep` / `js-reverse` | 2 | **2** | 一致 |
| MCP `ida` / `playwright` | 2 | **0**（可选挂） | 设计选择，不计分 |
| MCP 工具总数 | 135 | **62**（34 + 24 之外还有 ida/playwright 的差） | 同上 |
| Skill | 10 | **10（需显式开启）** | 机制存在，默认关闭 |
| `lab：` 会话状态机 | 代码层强制 | **1.14.0 起同为代码层强制**（插件内实现） | 一致 |
| 纪律自动注入 | 自动 | **1.14.0 起 `lab：` 之后由插件注入** | 一致 |

> **重要**：DSH **有** skill 机制 —— `dsh-skill-filesystem`（发现）+ `dsh-tool-skill`（加载），
> 只是在 `web` profile 里默认 `disabled: true`。开启后能直接吃 pi 的 `<name>/SKILL.md` 布局，
> 不需要改任何技能文件。见第三组 F1–F3。

---

## 二、评分表（满分 100）

### 第 1 组 · 配置层（20 分）

1.14.0 起接线由插件包完成，不再往 profile patch 里塞 MCP 条目。
所以这一组查的是「包装了没、跑过没、指向对不对、lab 开着没」。

| 编号 | 检查项 | 分值 | 判据 | 采集方式 |
| :---: | :--- | :---: | :--- | :--- |
| A1 | 插件包 `seep-dsh-workbench` 已装进 profile | 8 | `dsh.profile.bundles` 含该包名 | 读 `$DSH_HOME/profiles/<p>/package.json` |
| A2 | 插件已启动并写出状态文件 | 5 | `$DSH_HOME/seep-workbench.status.json` 存在 | 启动一次 dsh 后读文件 |
| A3 | 状态 `ok:true` 且 `repoRoot` 指向当前仓库 | 4 | 路径规范化后相等 | 同上 |
| A4 | `labGate` 已启用 | 3 | 状态里 `labGate: true` | 同上 |

> 旧路线（`dsh-merge.py`）残留的 `>>> seep-workbench` 标记块**不扣分**，
> 但会提示「不要两条路线同时用」—— 同时用会把 MCP 挂两份。

### 第 2 组 · MCP 可用性（25 分）★ 核心

命令与参数从插件写出的状态文件里取 —— 校验的就是插件真正会启动的东西。

| 编号 | 检查项 | 分值 | 判据 |
| :---: | :--- | :---: | :--- |
| B1 | `seep` 能 `initialize` | 7 | 按合成配置真启动，收到 `result` |
| B2 | `seep` `tools/list` = **38** 个工具 | 8 | 工具数组长度 ≥ 38 |
| B3 | `js-reverse` 能 `initialize` | 5 | 同上 |
| B4 | `js-reverse` `tools/list` ≥ **24** | 5 | 工具数组长度 ≥ 24 |

这一组是**唯一能证明「真的能用」**的部分：真启动进程、真发 JSON-RPC、真数工具。
只看进程没退出不够 —— 服务可能起来但握手失败。

### 第 3 组 · 技能层（15 分）

| 编号 | 检查项 | 分值 | 判据 |
| :---: | :--- | :---: | :--- |
| F1 | 插件已挂载技能层 | 5 | 状态里 `skillsEnabled:true` 且 `mounted.skills:true` |
| F2 | 仓库里可发现 ≥ 10 个技能 | 6 | 两个技能根下各含 `SKILL.md` 的子目录计数 |
| F3 | 两个技能根都在仓库里 | 4 | `<repo>/Tool/skill` 与 `<repo>/Tool/skill/safe-skills` 均存在 |

两个根对应的技能：

| 根 | 贡献的技能 |
| :--- | :--- |
| `<repo>/Tool/skill` | `apkseep` `exe-reverse` `softseep` `webseep` `client-license-validation-bypass` |
| `<repo>/Tool/skill/safe-skills` | `apk-reverse` `ida-reverse` `mcp-js-reverse-playbook` `radare2` `reverse-engineering` |

> **代价**：开启后 10 个技能的 `name + description` 进入每个会话的上下文。
> 不想付这个成本就 `--dsh-skills none` 重新生成（整层关闭）。
> `customSkillDirs` 是「扫该目录下的直接子目录」，**无法只挑其中几个**。

### 第 4 组 · 仓库资产（15 分）

| 编号 | 检查项 | 分值 | 期望 |
| :---: | :--- | :---: | :--- |
| C1 | 内置二进制工具箱 5 件齐 | 5 | `Tool/mcp/Tool/safe/` 下 jadx / apktool / radare2 / playwright-mcp / js-reverse-mcp |
| C2 | 知识库篇数 | 4 | ≥ 294 篇 `.md` |
| C3 | 脱敏案例数 | 2 | ≥ 14 个目录 |
| C4 | `MANUAL/` 手册 | 2 | ≥ 7 份 `.md` |
| C5 | 技能源目录 | 2 | 10 个唯一名 |

### 第 5 组 · 指令层（15 分）

| 编号 | 检查项 | 分值 | 判据 |
| :---: | :--- | :---: | :--- |
| D1 | 仓库根 `AGENTS.md` 存在 | 5 | DSH 启动时自动读取 |
| D2 | 根 `AGENTS.md` 与 `Tool/prompts/AGENTS.md` 一致 | 5 | 内容完全相同（无漂移） |
| D3 | `Tool/prompts/SYSTEM.md` 存在 | 5 | 用户发 `lab：` 时模型要读的那份纪律 |

### 第 6 组 · 运行时（10 分）

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

### 输出样例

```
【配置层】   A1..A4   20/20
【MCP 可用性】B1..B4   25/25     seep 38 工具 / js-reverse 24 工具
【技能层】   F1..F3   15/15     插件已挂技能层，10 个技能可被发现
【仓库资产】 C1..C5   15/15
【指令层】   D1..D3   15/15
【运行时】   E1..E2   10/10
──────────────────────────────────────────────────────────
完整率  ████████████████████████████████████████  100.0%   (100 / 100 分)
```

用 `--no-skills` 装（或状态里 `skillsEnabled:false`）时会是 **85%** —— 这是**设计选择**，不是故障：

```
【技能层】
 [FAIL] F1  插件已挂载技能层                    5 分
 [FAIL] F2  仓库里可发现 ≥ 10 个技能             6 分
 [FAIL] F3  两个技能根都在仓库里                  4 分
完整率  ██████████████████████████████████░░░░░░   85.0%
```

---

## 四、分数怎么解读

| 完整率 | 含义 | 该怎么办 |
| :---: | :--- | :--- |
| **100%** | 配置、MCP、技能、资产、指令、运行时全部就位 | 可以开工 |
| **85%** | 只差技能层（`--no-skills` 装的） | `python setup/dsh-plugin-setup.py`（不带 `--no-skills`）重装 |
| **60–84%** | 缺 MCP 或运行时，工具基本用不了 | 看「缺失清单」逐项修；路径不对就重跑 `dsh-plugin-setup.py --root <正确路径>` |
| **< 60%** | 插件包根本没装上 | `python setup/dsh-plugin-setup.py` |

### 完整的含义边界

100% **只说明「配置与资产就位」，不说明「模型会遵守 `lab：` 闸门」**。

后者是指令层的事：

- DSH 读到 `AGENTS.md` 后**应该**在用户发 `lab：` 时去读 `Tool/prompts/SYSTEM.md`；
- 但这是**指令约束**，不是代码强制。换模型、上下文压缩、长对话漂移都可能失效；
- 抽验方法：开一个 DSH 会话，**不发 `lab：`**，直接问「这个 APK 是怎么校验会员的？」，
  看它是否只讲原理而不动手。再发 `lab：` 重问，看它是否先读 `SYSTEM.md` 再作答。

---

## 五、常见缺项与修复

| 症状 | 根因 | 修复 |
| :--- | :--- | :--- |
| A1 全组 FAIL | 没挂载 | `python setup/dsh-merge.py --profile web` |
| A2/A3 FAIL 但 A1 PASS | profile 名不对 | `--profile <你启动的那个>`，或 `--global` |
| A4 FAIL | 手改过补丁，把 timeout 删了 | 重跑 `dsh-merge.py`（重写整块） |
| A5 FAIL | 仓库被移动/复制过，`cwd` 是旧路径 | 重跑 `dsh-merge.py` |
| B1 FAIL，报 `ImportError: mcp` | `seep` 用的解释器没装 mcp | `setup\install-python.ps1`，或设 `SEEP_PYTHON` |
| B2 工具数 < 38 | 启动的是旧副本 | 确认 `args` 指向当前仓库 |
| B3/B4 FAIL | `npx js-reverse-mcp` 网络/缓存问题 | 手动跑一次 `npx -y js-reverse-mcp` 预热 |
| **F1/F2 FAIL** | **skill 图层没开** | `python setup/generate-configs.py --root . --dsh-skills all`，再重跑 `dsh-merge.py` |
| **F3 FAIL** | 两个技能根少了一个 | 同上；确认 `cordis.generated.yml` 里两行都在 |
| C1 缺目录 | 克隆不完整 | 重新 `git clone` |
| D2 FAIL | 改过根 `AGENTS.md` 没同步源 | `python setup/generate-configs.py --root .` |
| E1 FAIL | `python` 指向没装 mcp 的解释器 | `setup\resolve-tools.ps1 -Tool python -Verify` 定位 |

---

## 六、可选能力（不计入分母）

| 工具 | 用途 | 补全命令 |
| :--- | :--- | :--- |
| `ida` | 商业反编译（DSH 默认未挂） | `setup\install-ida.ps1 -IdaRoot <目录>` |
| `playwright` | 浏览器自动化（DSH 默认未挂） | 需手工在补丁里追加条目 |
| `ffmpeg` | HLS 取证 | `setup\install-capabilities.ps1 -Only web` |
| `frida` / `objection` | 动态插桩 | `-Only android` |
| `apkid` | 查壳 | `-Only android` |
| `aotopsy` | Flutter AOT（Windows only） | `-Only aotopsy`（仓库自带） |

单项四态可单独查：`setup\resolve-tools.ps1 -Verify`。

---

## 七、与 Pi 侧的一致性核对（可选）

```powershell
# DSH 侧
python setup\verify-dsh.py

# pi 侧
powershell -File setup\verify.ps1 -Detailed

# 工具级逐个实探（可指定任意 mcp.json）
python setup\probe-mcp.py
python setup\probe-mcp.py --config <别的 mcp.json> --only seep,js-reverse
```

对照关系：

| 项目 | pi 应有 | DSH 应有 | 差异性质 |
| :--- | :---: | :---: | :--- |
| MCP 服务 | 4 | 2 | `ida`/`playwright` 可选挂 |
| MCP 工具 | 135 | 62 | 同上 |
| Skill | 10 | 10（需开启） | 默认关闭，非不支持 |
| 纪律注入 | 自动 | 手动读文件 | 架构差异 |

**除这三处架构差异之外还有缺失，才是真的部署问题。**
