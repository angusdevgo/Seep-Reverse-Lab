# seep-dsh-workbench

Seep 逆向工作台的 DeepSeek Harness 插件包。

**这个包只装接线，不装工具。** 工具本体（jadx / radare2 / apktool / 知识库 / 案例 …）
在你的工作台仓库里，靠配置里的路径指过去 —— 所以这个包只有几十 KB。

## 装

```powershell
# 在工作台仓库目录里
python setup/dsh-plugin-setup.py

# 仓库搬家后重跑这一条
python setup/dsh-plugin-setup.py --root D:\新位置\Seep-Reverse-Lab
```

装完重启 DSH 生效。想手工装也行：

```bash
dsh plugin --profile web add file:<仓库>/packages/dsh-workbench
```

## 它做什么

| 事情 | 说明 |
| :--- | :--- |
| 开机自检 | 路径对不对、仓库全不全、版本够不够；缺什么直接说怎么补 |
| 挂 MCP | `seep`（38 工具，超时 900s）+ `js-reverse`（24 工具，超时 600s） |
| 挂技能 | DSH 的 skill 图层（默认关）+ 两个技能根 → 10 个技能 |
| lab 开关 | 会话级、默认关；消息里出现 `lab：` 才注入作战纪律 |
| 设置面板 | 设置 → Seep 工作台：状态 / 改路径 / 工具四态清单 |

## 配置

在 DSH 里 设置 → Seep 工作台（或 设置 → 插件 → 本包 → 「配置」）能改：

| 字段 | 默认 | 说明 |
| :--- | :--- | :--- |
| `repoRoot` | 空 | 工作台仓库路径。留空则读环境变量 `SEEP_ROOT` |
| `pythonPath` | 空 | 能 `import mcp` 的解释器。留空按 `setup/tool-registry.json` 的候选链自动找 |
| `enableSkills` | `true` | 是否在 DSH 里列出 10 个技能 |
| `labGate` | `true` | 关掉则永不注入纪律正文（排查用） |

> 四个字段都是 **volatile**：DSH 只把 volatile 字段投影到设置表单，
> 普通字段进不了表单，面板也就看不到、改不了。

改路径后需要**重启 DSH**（MCP 连接在启动时建立，没法热替换）；
技能与 lab 开关对下一个会话生效。

## 面板

两个入口，同一个组件：

- 设置 → **Seep 工作台**（独立一页）
- 设置 → 插件 → `seep-dsh-workbench` → 「配置」（官方 bundle row 配置位）

工具清单用四态：`READY` 找到 / `DEGRADED` 找不到但曾经在 / `OPTIONAL` 可选且没装 /
`MISSING` 核心项缺失。「深度检测」会调 `Tool/mcp/tool_resolver.py --verify` 真跑一遍（慢）。

## 边界

- **lab 开关只管提示词，不管工具可用性**：38 个工具始终挂在模型眼前。
- 状态只在内存里，进程退出即清；不动你的 `~/.dsh` 以外任何东西。
- 自检失败不抛异常（除非 `strict: true`）：路径没填不该让整条 profile 起不来。

## 开发

```bash
node packages/dsh-workbench/test/lab-gate.test.mjs   # lab 开关单测，25 项，不需要 DSH
```

面板格式是 DSH 客户端模块系统的懒加载 CJS 工厂，**不需要打包器** ——
只 `require('react')`，其余走 `ctx` 服务。改完 `lib/client.js` 直接重启 DSH 即可。
