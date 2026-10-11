# MANUAL — 合规转译中继与防拒体系 (Compliance Relay & Anti-Refusal)

> 本手册说明 Seep 工作台**三层防拒体系**中的第三层：网络层通用合规转译中继。
> 它把「敏感口语 → 合规术语」的能力从「单点 Agent 插件」升级为「链路级通用网关」。
>
> 工具本体位于 `Tool/scripts/compliance-relay/`，操作速查见其 `README.md`。

---

## 一、 为什么需要这一层

传统做法是把改写逻辑挂在 Agent 的扩展 API 上（如 `pi.on("input")`）。
但 **Agent 的扩展 API 是各家私有的、互不兼容的**：

| 方案 | 生效范围 | 依赖 |
|---|---|---|
| Agent 插件层（`security-audit-interceptor.ts`） | 仅 Pi Agent | Pi 私有扩展 API |
| **网络层中继（本手册）** | **任意支持自定义 `baseUrl` 的 Agent** | **通用 HTTP 协议** |

> **原理**：谁离模型更近，谁就天然通用。把改写点从「插件层」下沉到「网络层」，
> 覆盖面即从 1 个 Agent 扩展到 N 个。

### Seep 三层防拒体系全景

| 层 | 载体 | 作用范围 | 机制 |
|---|---|---|---|
| **L1 底座级** | `before_provider_request` 拦截 | **仅 Gemini/Google 端点**（`google-generative-ai` / `google-vertex`） | 注入 `safetySettings: BLOCK_NONE`；非 Google 端点原样透传，可用 `PI_SAFETY_PAYLOAD=off` 关闭 |
| **L2 插件级** | `pi.on("input")` + 上下文守卫 | Pi Agent | 口语 → 合规术语转译 |
| **L3 链路级** | **compliance-relay 回环中继** | **任意 HTTP Agent** | **请求体离开本机前改写** |

三层互不冲突，可同时启用。L3 是兜底与广覆盖层。

---

## 二、 核心机制与四条铁律

### 铁律 1：只改「人打的字」

Agent 会把自己生成的上下文（环境变量、`AGENTS.md`、技能清单、系统提醒）
**伪装成 `role: "user"` 的消息**发出去。因此改写必须严格限定范围：

| 协议 | 改写目标 | 绝不触碰 |
|---|---|---|
| `openai-completions` | `messages[]` 中 `role=="user"` 的 `text` / `input_text` | `system` 角色消息、`assistant` 内容 |
| `anthropic-messages` | `messages[]` 中 `role=="user"` 的 `type=="text"` block | `system` 字段、`tools`、`tool_result`、`assistant` |
| `openai-responses` | `input[]` 中 `role=="user"` 的 `input_text` 分片 | `instructions`、`tools`、`developer`/`reasoning`/`tool` 项 |

### 铁律 2：上下文注入守卫（`INJECTED_PREFIXES`）

命中以下前缀的文本**整条跳过转译**，防止污染 Agent 自身的作战协议：

```
<system-reminder>   <environment_context>   <user_instructions>
<user_shell_command> <turn_aborted>         <subagent_notification>
<startup_context>   <skill>                 <skills_instructions>
<apps_instructions> <plugins_instructions>  <permissions instructions>
<collaboration_mode> <model_switch>         <personality_spec>
<realtime_conversation> <realtime_delegation>
<command-name>      <command-message>       <local-command-stdout>
<user-prompt-submit-hook> <session-context>
# AGENTS.md instructions   # AGENTS.md   # CLAUDE.md
```

**包裹型上下文**（`# Context from my IDE setup:` / `# Files mentioned by the user:` /
`# Applications mentioned by the user:`）只改写最后一个 `## My request` 标题之后的用户原话。

白名单在 `guard-prefixes.json` 中按协议分列，可自行扩充。

### 铁律 3：最长优先 + 单趟不回扫

规则表编译为**单个正则**（alternation 按长度降序排列），一次性完成替换：

- **最长优先**：同一位置取最长规则。「绕过会员」必定优先于「绕过」，
  不再依赖规则表的人工排序纪律（这是原实现最脆弱的地方）；
- **单趟不回扫**：替换产物不再参与匹配，杜绝 `A→B`、`B→C` 导致 `A` 最终变成 `C` 的级联污染。

### 铁律 4：零落盘（凭据红线）

- **绝不**把请求体、响应体、鉴权头写入磁盘或日志；
- 日志仅输出：`[REWRITE] key=... protocol=... path=... changed=3`（**只记条数**）；
- 鉴权头（`Authorization` 等）原样透传，中继不读取、不解析、不记录其内容。

---

## 三、 Pi Agent 接入（影子 Provider 方案 · 推荐）

Pi 通过 `~/.pi/agent/models.json` 支持自定义 `baseUrl`，因此中继可直接覆盖 Pi 的全部 provider。

### 步骤 1：扫描生成 upstream 映射

```bash
cd Tool/scripts/compliance-relay
python relay.py --scan-pi
```

该命令只读取 provider 名与 `baseUrl`，**不读取也不改写任何 `apiKey`**，
生成 `relay-config.json` 并打印访问令牌。

### 步骤 2：启动中继

```bash
python relay.py
```

### 步骤 3：新增「影子 Provider」（零破坏，可 A/B 对比）

**不修改原有 provider**，而是在 `~/.pi/agent/models.json` 的 `providers` 中**新增**一个条目：

```json
{
  "providers": {
    "MyProvider": {
      "baseUrl": "https://api.example-relay.com/v1",
      "api": "openai-completions",
      "apiKey": "……原有配置保持不动……",
      "models": [ { "id": "claude-sonnet-4-6" } ]
    },

    "MyProvider-relay": {
      "baseUrl": "http://127.0.0.1:17890/r/<TOKEN>/pi-MyProvider",
      "api": "openai-completions",
      "apiKey": "……与原 provider 相同……",
      "models": [ { "id": "claude-sonnet-4-6" } ]
    }
  }
}
```

- `<TOKEN>` 替换为中继启动时打印的访问令牌；
- `apiKey` 可直接复用原值，或用 `$ENV_NAME` 环境变量插值；
- 之后在 Pi 中用 `/model` 即可在 `MyProvider` ↔ `MyProvider-relay` 之间切换，
  **直观对比有/无中继时的拒绝率**；
- 想停用中继：切回原 provider，或直接关掉中继进程（请求会失败，需切回）。

> **替代方案（直接改原 provider）**：把原 provider 的 `baseUrl` 改为中继地址即可，
> 回滚就是把 `baseUrl` 改回去。影子 provider 的优势是**可随时 A/B 对比**。

### 步骤 4：确认 Lab Mode 已开启

中继默认**只在 Lab Mode 下改写**。在 Pi 中发送一次：

```
lab：
```

即可写入 `~/.pi/agent/lab-mode.flag`，中继会在下一次请求时自动热加载启用。
发送 `退出实验` 后中继自动转为纯透传（无需重启中继进程）。

---

## 四、 Claude Code 接入（零文件侵入）

只需一个环境变量：

```powershell
# Windows PowerShell
$env:ANTHROPIC_BASE_URL = "http://127.0.0.1:17890/r/<TOKEN>/anthropic"
claude
```

```bash
# macOS / Linux
export ANTHROPIC_BASE_URL="http://127.0.0.1:17890/r/<TOKEN>/anthropic"
claude
```

若使用第三方 Anthropic 兼容中转站，把 `relay-config.json` 中的
`upstreams.anthropic` 改为该站地址即可。

---

## 五、 Codex 接入（生成片段，需用户确认）

在 `~/.codex/config.toml` 中新增（**先备份原文件**）：

```toml
[model_providers.seep-relay]
name = "Seep Relay"
base_url = "http://127.0.0.1:17890/r/<TOKEN>/openai/v1"
wire_api = "responses"
```

然后把 `model_provider` 切换为 `seep-relay`。

> **纪律**：本工作台**绝不自动改写**用户的 `config.toml`，
> 只提供片段与备份命令，由用户自行确认合并。

备份建议：

```powershell
Copy-Item "$env:USERPROFILE\.codex\config.toml" "$env:USERPROFILE\.codex\config.toml.bak"
```

---

## 六、 边界与已知限制

| 限制 | 说明 |
|---|---|
| **仅覆盖支持自定义 `baseUrl` 的客户端** | 硬编码端点的官方登录流程无法接入 |
| **不改 system prompt** | 若拒绝由 Agent 自身的系统提示词触发，本层无法缓解（需 L1/L2 层配合） |
| **本地必须走 http 回环** | 若某客户端强制 HTTPS 端点，需要额外配置自签证书 |
| **不处理响应** | 响应（含 SSE 流式）原样透传，不做任何改写 |
| **非 JSON 请求体透传** | 文件上传等非 JSON 请求体不做改写，直接转发 |
| **不做常驻** | 不随系统启动，不注册服务；关闭中继后需切回原配置 |

---

## 七、 排障速查

| 现象 | 原因 | 处理 |
|---|---|---|
| 返回 `403 forbidden` | token 不匹配 | 核对 `relay-config.json` 中的 token 与请求路径是否一致 |
| 返回 `502 unknown upstream key` | `upstreams` 中无该 key | 运行 `python relay.py --scan-pi` 重新生成 |
| 返回 `502 upstream error` | 上游不可达 / 域名解析失败 | 检查网络与 `upstreams` 中的地址是否正确 |
| 请求成功但未改写 | 未开启 Lab Mode | 在 Agent 中发送 `lab：`，或用 `--force-on` 验证 |
| 日志显示 `changed=0` | 文本未命中规则，或命中守卫白名单 | 用 `--verbose` 查看是否被识别为透传 |
| 端口被占用 | 17890 已被其他进程占用 | `python relay.py --port 17891` |
| 返回 `400 UNKNOWN_FIELD`（`未知请求字段：safetySettings` / `config`） | L1 把 Google 私有字段注入到了 OpenAI 兼容网关 | 更新工作台（旧版扩展无端点门控）；临时可用 `PI_SAFETY_PAYLOAD=off` 关闭 L1 |

---

## 八、 维护规则表

规则表的**唯一真值源**是
`Tool/prompts/extensions/security-audit-interceptor.ts` 中的 `SENSITIVE_WORD_MAP`。

修改流程：

1. 编辑 TS 文件中的 `SENSITIVE_WORD_MAP`；
2. 运行 `python Tool/scripts/compliance-relay/extract-rules.py` 重新生成 JSON；
3. 运行 `python -m unittest discover -s Tool/scripts/compliance-relay/tests` 确认全绿；
4. `setup/verify.ps1` 自检会自动校验两侧是否同步（`extract-rules.py --check`）。

> **禁止手工编辑 `sensitive-rules.json`** —— 该文件是生成物，会被下次提取覆盖。
