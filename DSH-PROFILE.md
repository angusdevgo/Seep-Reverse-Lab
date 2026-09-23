# DeepSeek Harness Profile — Seep 逆向工作台

> 将此文件放到 DSH profile 目录，或在 `cordis.yml` 中引用。
> DeepSeek Harness 的 MCP 通过 `@deepseek-ai/dsh-mcp-client` 插件桥接。

---

## MCP 配置（写入 cordis.yml）

```yaml
plugins:
  - id: seep-mcp
    name: '@deepseek-ai/dsh-mcp-client'
    config:
      serverName: seep
      transport: stdio
      command: python
      args:
        - '<SEEP_ROOT>/Tool/mcp/seep_mcp_server.py'
      env:
        PYTHONIOENCODING: utf-8

  - id: js-reverse-mcp
    name: '@deepseek-ai/dsh-mcp-client'
    config:
      serverName: js-reverse
      transport: stdio
      command: npx
      args:
        - '-y'
        - 'js-reverse-mcp'

  - id: ida-mcp
    name: '@deepseek-ai/dsh-mcp-client'
    config:
      serverName: ida
      transport: stdio
      command: '<IDA_PYTHON>'
      args:
        - '<IDA_ROOT>/Lib/site-packages/ida_pro_mcp/server.py'
      env:
        PYTHONIOENCODING: utf-8
```

> `<SEEP_ROOT>` = 本包根目录（如 `C:\Users\你\Desktop\Seep`）
> `<IDA_*>` = 有 IDA Pro 时填，没有则删掉整个 ida-mcp 块

---

## Skill 加载

DeepSeek Harness 的 `agent-instructions` 插件会自动读取项目根的 `AGENTS.md`。
本包已在 `Tool/prompts/AGENTS.md` 提供跨 agent 通用指令。

**方式 A（推荐）**：在 DSH 工作目录创建符号链接或复制：
```bash
cp Tool/prompts/AGENTS.md ./AGENTS.md
```

**方式 B**：在 `cordis.yml` 中指定 agent-instructions 的搜索路径。

---

## 部署步骤

```bash
# 1. 安装 Python 依赖
pip install "mcp>=1.20,<1.29" pytest frida-tools

# 2. 启动 DSH
npx @deepseek-ai/dsh web

# 3. 在 DSH 中创建/编辑 profile，粘贴上方 cordis.yml 配置

# 4. 开始工作（AGENTS.md 会被自动加载）
```

---

## 约束

- 不搬动 `Tool/mcp/Tool/`（seep MCP 硬编码相对路径）
- IDA Pro 需自备授权（不随包分发）
- 所有测试目标须用户确认已获授权
