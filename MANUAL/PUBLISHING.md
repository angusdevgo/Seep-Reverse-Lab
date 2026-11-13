# 插件发布章程

> 这份文档回答三个问题：**发到哪、发什么、别人怎么更新。**
>
> 使用者视角的「怎么更新、更新什么」见 [UPDATING.md](UPDATING.md)。
> 面向所有人（包括三个月后忘了细节的我们）。

> **范围声明：本包只服务 DeepSeek Harness（DSH）。**
> Pi Agent 的接线是另一套（写 mcp.json + 拷技能），不走 npm、没有版本号。
> 四个 Agent 的对照见 [AGENTS.md](AGENTS.md)。

---

## 一、结论先行

| 问题 | 答案 |
| :--- | :--- |
| 主发到哪 | **npm**（`seep-lab`，公开包） |
| 备用呢 | **GitHub Release** 挂同版本 `.tgz`，给装不了 npm 的人 |
| 包里装什么 | 只有**接线代码**（约 100 KB） |
| 包里不装什么 | **工具（561 MB）、技能、知识库、案例** —— 这些永远在仓库里 |
| 别人怎么更新 | `dsh plugin update --profile web seep-lab`，或面板上点「更新插件」 |
| 更新后要重启吗 | **要**（插件代码是启动时加载的） |

**一句话**：插件是个「遥控器」，不是「工具箱」。遥控器可以更新，电视还得你自己搬。

---

## 二、为什么是 npm，不是只用 GitHub

`dsh plugin add` 底层就是 pnpm，它能装三类东西：

| 来源 | 更新方式 | 问题 |
| :--- | :--- | :--- |
| npm 包名 | `dsh plugin update` —— **官方通道，自动认版本** | 需要 npm 账号 |
| GitHub Release 的 `.tgz` | 得手动换 URL 重装 | 每次发版要改链接 |
| git 地址 | 装得到，但版本语义不清 | 分支一改就悄悄变，不可复现 |

只有 npm 那条能让「更新」变成一个**确定的动作**：有版本号、能回滚、能锁版本。

GitHub Release 留着当**镜像**：谁那边 npm 装不上（网络、公司内网），就用它。

---

## 三、包里到底装了什么

```
seep-lab-0.x.y.tgz      约 100 KB
├── package.json          身份、版本、DSH 兼容范围
├── cordis.patch.yml      告诉 DSH「把我插进加载链」
├── lib/index.js          宿主侧：挂 MCP、挂技能、lab 闸门、面板接口
├── lib/lab-gate.js       lab 开关（不依赖 DSH，可单测）
├── lib/lab-rewrite.js    敏感词替换与合规前缀
├── lib/client.js         浏览器侧面板
├── README.md             安装与配置说明
└── test/lab-gate.test.mjs
```

**明确不进包的三类**，理由都是「体积」和「更新频率」不匹配：

| 不进包 | 多大 | 理由 |
| :--- | :--- | :--- |
| `Tool/mcp/Tool/safe/`（jadx / apktool / radare2 / node_modules） | 561 MB | npm 装不动，也不该塞进 `~/.dsh` |
| 技能 `Tool/skill/` | 4.5 MB | 更新频率比插件高，走内容仓更快 |
| 知识库 / 案例 | 11 MB | 同上 |

所以**使用者永远需要一个仓库副本**。插件只负责「把 MCP 指向那份副本」。

---

## 四、三种人，三条路

### 1. 使用者（只想用）

```bash
git clone https://github.com/angusdevgo/Seep-Reverse-Lab.git seep
cd seep
powershell -File setup\install.ps1      # 解压依赖、装 Python 依赖、装插件、自检
```

之后更新：

```bash
dsh plugin update --profile web seep-lab   # 只更插件
cd seep && git pull                                  # 更工具/技能/知识库
```

或者干脆在 DSH 面板上点：**「更新插件」**（npm 装的才亮）和 **「更新工作台」**（拉仓库）。

### 2. 装不了 npm 的人

从 GitHub Release 下载 `seep-lab-<版本>.tgz`，然后：

```bash
dsh plugin --profile web add "file:D:/下载/seep-lab-0.3.0.tgz"
```

更新 = 下载新 tgz 再执行一遍。**没有自动更新**，这是选这条路的代价。

### 3. 自己改代码的（我们）

```bash
dsh plugin --profile web add "file:<仓库>/packages/seep-lab"
```

`file:` 安装是**硬链接** —— 改仓库文件，插件立刻跟着变，不用重装。

> 这条和上面两条**互斥**。`file:` 安装时面板上的「更新插件」会灰掉，
> 因为「更新」对本地链接没有意义。

---

## 五、版本号怎么走

用语义化版本 `主.次.修`：

| 改动 | 版本 | 例子 |
| :--- | :--- | :--- |
| 修 bug、改文案 | 修（patch） | 0.2.0 → 0.2.1 |
| 新增功能、新增配置项 | 次（minor） | 0.2.1 → 0.3.0 |
| 破坏性变更（配置字段改名、删功能、改 DSH 最低版本） | 主（major） | 0.3.0 → 1.0.0 |

**破坏性变更必须做三件事**：
1. 主版本号 +1
2. CHANGELOG 里单独写一段「升级注意」
3. 插件启动时**检测旧配置并给出明确提示**（不能静默失效）

---

## 六、兼容性承诺

| 维度 | 承诺 |
| :--- | :--- |
| DSH 版本 | `package.json` 的 `engines.dsh` 写死最低版本；低于它启动时直接说「请先升 DSH」 |
| 仓库版本 | 插件里 `MIN_REPO_VERSION` 校验；仓库太旧就提示「先 `git pull`」，而不是报一堆看不懂的错 |
| 配置字段 | 只增不改；必须改时保留旧字段一个版本，给弃用警告 |
| lab 语义 | 默认关、只认 `lab：`、关掉就什么都不触发 —— **这条永不变**（安全边界） |

---

## 七、发布检查清单（每次发版照着走）

```bash
# 1. 全绿才往下走
node packages/seep-lab/test/lab-gate.test.mjs     # 单测
python setup/verify-dsh.py                             # DSH 完整度 100 分
powershell -File setup/verify.ps1                      # 仓库基准 64 项

# 2. 隐私扫描（绝不能把本机路径、真实姓名带出去）
#   规则内置在 setup/verify.ps1 第 10 组（脱敏与隐私走查），含本机路径/真名/私人域名
powershell -File setup/verify.ps1 -Detailed   # 看「脱敏」那几行是否全绿

# 3. 版本号 + CHANGELOG 同步
#    VERSION、packages/seep-lab/package.json、CHANGELOG.md 三处一致

# 4. 打包（不发布，只产出 tgz 并打印校验和）
python setup/pack-plugin.py

# 5. 本地试装（用真包，不用 file:）
dsh plugin --profile web add "file:<刚才的 tgz>"
dsh --profile web --dump-config | grep seep-workbench   # 确认插进加载链了

# 6. 发布
npm publish packages/seep-lab                       # 或 npm publish --access public（scoped 包）

# 7. GitHub Release 挂同一个 tgz（备用通道）
```

**任何一步红了就停，不要带着问题发版。**

---

## 八、出事了怎么退

| 情况 | 怎么退 |
| :--- | :--- |
| 新版本插件有问题 | `dsh plugin --profile web add seep-lab@0.2.2`（装回旧版） |
| 插件完全起不来 | `dsh plugin remove --profile web seep-lab`，DSH 恢复干净状态 |
| 配置被改坏 | 插件写过的东西只有两处：profile 的 `cordis.patch.yml`（有 `.bak`）和 `setup/tool-paths.local.json` |
| 想彻底重来 | 删 `~/.dsh/profiles/web`，重新 `dsh --profile web` 让它自建 |

**插件从不删用户数据**：不碰 `~/.dsh` 以外的文件，不改你的 git 配置。

---

## 九、谁负责什么

| 角色 | 责任 |
| :--- | :--- |
| 我们（维护者） | 发版、写 CHANGELOG、保证「更新后不会静默坏掉」、回滚可用 |
| 使用者 | 保持仓库 `git pull` 到最新；插件版本与仓库版本不必严格同步，但仓库过旧会被提示 |

---

## 十、不做的事（划清边界）

- ❌ 不把工具打进插件（561 MB，也不该进 `~/.dsh`）
- ❌ 不做「插件自己下载自己覆盖」—— 运行中改自己的文件必然出半崩状态
- ❌ 不在插件里存 API Key / Cookie / 凭据
- ❌ 不自动更新（不加静默升级）—— 更新必须是用户主动点的动作
