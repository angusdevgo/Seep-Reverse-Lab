# CLAUDE.md — Claude Code 项目指令

> 当 Claude Code 在本目录工作时，自动读取此文件作为项目级指令。

---

## 项目是什么

这是一个**逆向工程工作台**（Seep），用于已授权的白盒安全测试与客户端逻辑验证（CWE-602）。包含 9 个 Skill、4 个 MCP、知识库与脱敏案例。

---

## 部署指令（agent 读到此处时执行）

如果用户要求你部署本工作台，执行：

```bash
cd setup
powershell -ExecutionPolicy Bypass -File .\install.ps1
```

脚本会自动：装 Python 依赖 → 复制 Skill/提示词/MCP → 配 pi → 探测 IDA → 自检。

**完成后告诉用户**：重启 pi → 输入 `lab：` → 开工。

---

## 工作约束

1. **不搬动 `Tool/mcp/Tool/`** —— seep MCP 硬编码了相对路径
2. **不修改 `seep_mcp_server.py` 的路径常量**
3. **不打包 IDA Pro**（商业授权，用户自备）
4. 所有测试目标须用户确认已获授权
5. 凭据/Token/Salt/密钥 → 停、报告、不记录

---

## 结构

```
Seep\
├── Tool\
│   ├── skill\         9 个 Skill（softseep 总控）
│   ├── mcp\           seep MCP + Tool\ 运行时
│   ├── prompts\       SYSTEM.md + AGENTS.md + 扩展
│   ├── cases\         9 个脱敏案例
│   ├── upstream\      apk-reverse（MIT）
│   ├── docs\          MCP-SETUP / DOWNLOADS / PROVENANCE
│   └── scripts\       工作流脚本
├── setup\             安装脚本
└── MANUAL\            自备指引
```

详见 `Tool/docs/PROVENANCE.md`。
