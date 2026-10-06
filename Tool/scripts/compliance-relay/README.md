# compliance-relay — Seep 合规转译中继

把「敏感口语 → 合规术语」的转译从 **Agent 插件能力** 下沉为 **网络传输能力**，
一次配置即可覆盖任意支持自定义 `baseUrl` 的 Agent。

> 战术原理、安全边界与三 Agent 完整接入步骤见 [`MANUAL/COMPLIANCE-RELAY.md`](../../../MANUAL/COMPLIANCE-RELAY.md)。

---

## 为什么需要它

| | Agent 插件层（`security-audit-interceptor.ts`） | 中继层（本模块） |
|---|---|---|
| 生效范围 | 仅 Pi Agent | 任意支持自定义 `baseUrl` 的 Agent |
| 依赖 | 各 Agent 私有的扩展 API | 通用 HTTP 协议 |
| 覆盖协议 | 取决于 Harness | `openai-completions` / `anthropic-messages` / `openai-responses` |

---

## 快速开始

```bash
# 1. 从 TS 扩展提取规则表（首次 / 规则变更后执行）
python extract-rules.py

# 2. 扫描 Pi 的 provider，生成 upstream 映射（Pi 用户）
python relay.py --scan-pi

# 3. 启动中继
python relay.py
```

启动后控制台会打印接入示例与访问令牌。**默认关闭改写**：只有 `~/.pi/agent/lab-mode.flag`
存在（即已在 Agent 中发送过 `lab：`）时才启用。

### 常用参数

| 参数 | 说明 |
|---|---|
| `--port 17891` | 覆盖监听端口（默认 17890） |
| `--force-on` | 强制启用改写（忽略 lab flag，排障用） |
| `--force-off` | 强制关闭改写（纯透传，A/B 对比用） |
| `--scan-pi` | 扫描 `~/.pi/agent/models.json` 生成 upstream 映射后退出 |
| `--verbose` | 额外输出透传日志（仍然只记条数，不记内容） |
| `--lab-flag <path>` | 自定义 lab 标志文件路径 |

---

## 路由格式

```
http://127.0.0.1:<port>/r/<token>/<upstream-key>/<原始路径>
                                    ↓
                    <upstreams[upstream-key]> + <原始路径>
```

例：`upstreams["pi-CPAMP"] = "https://angusdev.top/v1"`

| 客户端请求 | 实际转发到 |
|---|---|
| `/r/<token>/pi-CPAMP/chat/completions` | `https://angusdev.top/v1/chat/completions` |
| `/r/<token>/anthropic/v1/messages` | `https://api.anthropic.com/v1/messages` |
| `/r/<token>/openai/v1/responses` | `https://api.openai.com/v1/responses` |

协议由路径自动识别（`/chat/completions`、`/messages`、`/responses`），无需配置。

---

## 配置说明

### `relay-config.json`（运行时自动生成）

```json
{
  "schema": 1,
  "port": 17890,
  "token": "<自动生成的随机令牌>",
  "upstreams": {
    "pi-CPAMP": "https://angusdev.top/v1",
    "anthropic": "https://api.anthropic.com",
    "openai": "https://api.openai.com"
  }
}
```

> **凭据提醒**：`token` 是本机访问凭据，请勿外传或提交到公开仓库
> （本目录的 `.gitignore` 已排除该文件）。

### `sensitive-rules.json`（自动生成，请勿手改）

由 `extract-rules.py` 从 `Tool/prompts/extensions/security-audit-interceptor.ts`
单向提取。**TS 源文件是唯一真值源**，改规则请改 TS 后重新提取。

### `guard-prefixes.json`（手工维护）

三协议各自的「上下文注入前缀白名单」。命中白名单的文本整条跳过转译，
防止改写 Agent 自注入的环境/AGENTS.md/技能清单。

---

## 测试

```bash
python -m unittest discover -s tests -v
```

覆盖：规则提取、最长优先、单趟不回扫、上下文守卫、三协议适配、
协议识别、路由与 token 校验、零落盘纪律、端到端转发与响应透传。

---

## 安全纪律（硬约束）

1. **零落盘**：绝不写入请求体 / 响应体 / 鉴权头；日志只输出命中条数；
2. **零改动上游语义**：只改 `role == "user"` 的用户输入，`system` / `instructions` /
   `tools` / `assistant` 一律不动；
3. **零新增依赖**：纯 Python 标准库，不引入任何第三方包；
4. **默认关闭**：不随系统启动，不做常驻服务，需用户显式运行；
5. **不改写用户配置**：不自动修改任何 Agent 的配置文件，只输出配置指引。
