# DeepSeek Harness (DSH) 接入 — Seep 逆向工作台

> DSH 通过 `@deepseek-ai/dsh-mcp-client` 桥接外部 MCP 服务，配置以 **Cordis Overlay 补丁**
> 形式挂载。本工作台的 `seep` MCP 暴露 **38 个工具**，挂载后模型看到的名字形如
> `mcp__seep__seep_pe_triage`（`mcp__<serverName>__<原始工具名>`）。

适配基准：**DSH 0.2.2-rc.1**（`dsh --version`）。字段定义取自该版本
`@deepseek-ai/dsh-mcp-client` 的 `lib/types/index.d.ts`。

---

## 一、 三种挂载方式

| 方式 | 命令 | 适用 |
| :--- | :--- | :--- |
| **持久挂载（推荐）** | `python setup/dsh-merge.py` | 长期使用。写入 `$DSH_HOME/profiles/web/cordis.patch.yml`，**只替换标注块，你自己的模型/插件配置原样保留**，写前自动备份 |
| 全局挂载 | `python setup/dsh-merge.py --global` | 本机所有 profile 都生效（`$DSH_HOME/cordis.patch.yml`） |
| 临时挂载 | `dsh web --patch "<工作台绝对路径>/setup/cordis.generated.yml"` | 一次性试用，不落盘 |

`setup/install.ps1` / `setup/install.sh` 会**自动检测** `$DSH_HOME`（默认 `~/.dsh`）：
存在则自动执行持久挂载，不存在则跳过（不给你制造无关步骤）。
跳过该步骤用 `-SkipDsh`（Windows）/ `--skip-dsh`（Unix）。

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

`setup/generate-configs.ps1` / `.py` 生成的 `setup/cordis.generated.yml`：

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

---

## 四、 校验

```bash
# 1. 是否已挂载（0=已挂载 / 1=未挂载）
python setup/dsh-merge.py --check

# 2. DSH 自己合成的配置树里能不能看到 seep 条目
dsh --profile web --dump-config | grep -A12 "serverName: seep"

# 3. 端到端：按 DSH 合成后的配置真的启动 MCP，数工具
python setup/test_dsh_mount.py
#   [PASS] tools/list 返回 ≥30 个工具  -> 38
```

`check.ps1` / `setup/verify.sh` 也会检查：
项目根 `AGENTS.md` 与源同步、Cordis 生成物结构合法、DSH 已装时是否已挂载。

---

## 五、 指令来源（AGENTS.md）

`dsh-agent-instructions` 会按「宽泛 → 具体」的顺序加载：
`$DSH_HOME/AGENTS.md` → `~/.agents/AGENTS.md` → 项目根到会话目录每一层的
`AGENTS.md` / `CLAUDE.md`。

所以本工作台做了两件事：

1. **项目根 `AGENTS.md`** —— 由 `setup/generate-configs` 从 `Tool/prompts/AGENTS.md`
   复制生成（逐字节一致，`verify` 会查漂移）。DSH 与 Codex 都从项目根读它，
   无需手工 `cp`。
2. 项目根 `CLAUDE.md` 保持给 Claude Code 用。

> 两者内容不同，会**各自加载一次**（DSH 只对内容完全相同的重复项去重）。

---

## 六、 与其它 Agent 的对照

| Agent | 配置文件 | 挂载方式 |
| :--- | :--- | :--- |
| **Pi Agent** | `~/.pi/agent/mcp.json` | `install.ps1` 写入，解释器为解析后的绝对路径 |
| **Claude Code** | 项目根 `.mcp.json` | 相对路径，直接 `claude` 即可 |
| **Codex / OpenCode** | 项目根 `opencode.jsonc` | `generate-configs` 生成 |
| **DeepSeek Harness** | `$DSH_HOME/profiles/<p>/cordis.patch.yml` | `setup/dsh-merge.py` 持久挂载，或 `--patch` 临时挂载 |

---

## 七、 约束与边界

- 不搬动 `Tool/mcp/Tool/` —— `seep_mcp_server.py` 内部按相对路径解析运行时依赖。
- IDA Pro 需自备授权；无授权时自动由内置 Radare2 承接。
- 所有测试目标须确认已获授权（G-Auth 门）。
- **平台边界**：8 个 `seep_web_*` 工具依赖 PowerShell 取证脚本（Unix 需装 pwsh），
  `seep_aotopsy` 是 Windows PE 单文件（Unix 不适用）。详见
  [MANUAL/CROSS-PLATFORM.md](../MANUAL/CROSS-PLATFORM.md)。
- 部署与排障详见 [MANUAL/DEPLOYMENT.md](../MANUAL/DEPLOYMENT.md)。
