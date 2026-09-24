# DeepSeek Harness Profile — Seep 逆向工作台

> 将此文件放到 DSH profile 目录，或在 `cordis.yml` 中引用。
> DeepSeek Harness 的 MCP 通过 `@deepseek-ai/dsh-mcp-client` 插件桥接。

---

## 一、 Agent 自动化部署与校验指令 (DSH 专属)

当用户在 DSH WebUI 或 CLI 对话框要求 **“部署工作台”** 或 **“校验安装是否完整”** 时：

### 1. 部署执行
```bash
cd setup
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

### 2. 校验与汇报输出
Agent 必须运行根目录校验脚本并向用户输出结构化 Markdown 体检卡片：
```bash
powershell -NoProfile -ExecutionPolicy Bypass -File .\check.ps1
```
依次核验并汇报：
* 📁 核心架构 (Tool/ 完整性)
* 🛠️ 技能系统 (softseep, apkseep 等 9 个 Skill)
* 🔌 MCP 服务 (seep, ida, playwright, js-reverse)
* 🧠 提示词与 Lab 状态机
* 🔧 内置工具箱 (Jadx, Radare2, Apktool)
* 📚 战术知识库 (289篇)

全部通过后，提示用户在对话框发送 `lab：` 正式开工。

---

## 二、 MCP 配置（写入 cordis.yml）

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
> `<IDA_*>` = 有 IDA Pro 时填，没有则删掉整个 ida-mcp 块（自动降级为 Radare2）

---

## 三、 Skill 加载与指令连接

DeepSeek Harness 的 `agent-instructions` 插件会自动读取项目根的 `AGENTS.md`。
本包已在 `Tool/prompts/AGENTS.md` 提供跨 agent 通用指令。

**推荐方式**：在 DSH 工作目录直接引用或软链：
```bash
cp Tool/prompts/AGENTS.md ./AGENTS.md
```

---

## 四、 约束

- 不搬动 `Tool/mcp/Tool/`（seep MCP 硬编码相对路径）
- IDA Pro 需自备授权（不随包分发，无授权时自动由 Radare2 替代）
- 所有测试目标须用户确认已获授权（G-Auth 门）
