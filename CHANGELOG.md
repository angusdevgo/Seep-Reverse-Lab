# Changelog

> 本文件面向**已部署用户**，说明每次更新带来什么变化、需要注意什么。
> 更新操作见 [MANUAL/DEPLOYMENT.md — 更新指南](MANUAL/DEPLOYMENT.md#八-已有用户更新指南)。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## [1.4.0] — 2026-09-30

### 新增

- **🌐 链路层合规转译中继**（`Tool/scripts/compliance-relay/`）
  - 本机回环中继，在请求离开本机前把口语平滑转译为合规术语
  - 覆盖三种协议：`openai-completions`（Pi Agent 主力）、`anthropic-messages`（Claude Code）、`openai-responses`（Codex）
  - 纯 Python 标准库实现，**零新增依赖**；**零落盘**（日志只记命中条数）
  - 默认关闭，需显式运行 `python relay.py`；受 `lab-mode.flag` 门控，mtime 热加载
  - 手册：[MANUAL/COMPLIANCE-RELAY.md](MANUAL/COMPLIANCE-RELAY.md)
- **🔒 脱敏与个人隐私门禁**（`verify.ps1` / `verify.sh` 第 9 节）
  - 全深度递归扫描个人路径、身份标识、私有域名、凭据
  - 生成物追踪检查（含本机路径的配置文件不得入库）
  - 脱敏基准表 D1–D6 记录于 `MANUAL/DEPLOYMENT-CHECKLIST.md`
- **🖥️ 跨平台支持**（macOS / Linux）
  - 新增 `setup/install.sh`、`setup/verify.sh` 原生 Bash 脚本
  - `seep_mcp_server.py` 自动探测系统 `radare2` / `rabin2` 与各平台 JDK 路径
  - 手册：[MANUAL/CROSS-PLATFORM.md](MANUAL/CROSS-PLATFORM.md)
- **📖 部署与校验体系**
  - `MANUAL/DEPLOYMENT.md` 全景部署手册（含 4 大 Agent 接入 SOP 与排障 FAQ）
  - `MANUAL/DEPLOYMENT-CHECKLIST.md` 官方基准核验清单（单一真值源）
  - `verify.ps1 -Detailed` 输出结构化基准校对看板
- **📦 案例库扩充至 14 个**（项目 A ~ 项目 N）
  - 新增 项目M（Java + install4j 双层鉴权）、项目N（.NET x64 + VM 混淆加固）

### 变更

- **⚙️ 安装脚本重构为幂等 + 无损模式**
  - `install-pi.ps1` 改为**增量合并** `mcp.json` / `settings.json`，不再覆盖用户自定义 MCP
  - 所有 JSON 配置统一以 **UTF-8 无 BOM** 写入，修复 Node.js `JSON.parse` 报错
  - 路径统一转为正斜杠，修复 Windows 反斜杠导致的 JSON 非法转义
- **🛡️ 安全审计扩展双加固**（`security-audit-interceptor.ts`）
  - 新增 25 项 `INJECTED_PREFIXES` 上下文守卫：Agent 自注入的环境 / AGENTS.md / 技能清单**不再被误改写**
  - 顺序 `replace` 改为**单趟最长优先匹配**：算法保证「绕过会员」优先于「绕过」，且替换产物不回扫（杜绝级联污染）
- **🔍 IDA Pro 探测强化**（`install-ida.ps1`）
  - 支持 `-IdaRoot` 参数、注册表探测、交互式输入自定义路径
  - 支持 IDA 9.x 原生 `idalib_supervisor` 模块模式
- **🔗 上游镜像归位**
  - `apk-reverse`、`open-tgtylab`、`open-reverselab` 三大开源项目完整镜像至 `Tool/upstream/`
- **⚖️ 许可证更正为 GPL-3.0**
  - 因整合了两个 GPL-3.0 上游项目，整体许可证由 MIT 更正为 **GNU GPL-3.0**

### 修复

- 修复 Windows PowerShell 5.1 下 `Set-Content -Encoding UTF8` 写入 BOM 导致 Node.js JSON 解析崩溃
- 修复 Windows 路径反斜杠未转义导致的 `Bad escaped character in JSON`
- 修复 `install-pi.ps1` 全量覆盖导致用户自定义 MCP（如 x64dbg）被抹除
- 修复 IDA 路径写死 `D:\Tool\IDA Pro`、非标准安装位置无法识别
- 修复 Bash 脚本 CRLF 换行污染导致的 `bad interpreter` 报错（13 个脚本）
- 修复 70 个 PowerShell 脚本缺失 UTF-8 BOM 导致的中文乱码与语法解析中断

### 安全

- **清理个人隐私与凭据残留**（发布前强制门禁）
  - 移除全部个人绝对路径、个人身份标识、私有中转站域名
  - 移除案例中残留的真实产品名 / 厂商域名 / **真实加密 Salt**
  - 含本机路径的生成物（`opencode.jsonc`、`cordis.generated.yml`）不再入库
  - 中继运行配置 `relay-config.json`（含访问 token）纳入 `.gitignore`

---

## [1.3.0] — 2026-09-28

### 新增

- 案例库扩充至 13 个（新增 项目L Qt5 C++、项目M Java + install4j）
- `seep_r2_xrefs` 工具：交叉引用查询，内置分页与统计摘要
- 上下文预算控制：`seep_r2_decompile` 支持 `fold`（省 ~60% Token）/ `summary`（省 ~90%）

### 变更

- `MANUAL/` 战术手册扩充至 6 份

---

## [1.2.0] — 2026-09-26

### 新增

- `MANUAL/ANTI-DEBUG.md`：反调试绕过字典与代理 DLL 框架
- `MANUAL/UNPACKING.md`：UPX / MPRESS / Themida / VMP 脱壳 SOP
- `MANUAL/POC-VALIDATION.md`：Frida 自愈循环与 PoC 沙箱验证

### 变更

- `verify.ps1` 升级为 7 大维度体检

---

## [1.1.0] — 2026-09-25

### 新增

- `check.bat` / `check.ps1` 根目录一键体检入口
- `setup/verify.ps1 -Detailed` 结构化基准校对看板
- 部署完备性校验体系（7 大维度）

---

## [1.0.0] — 2026-09-24

### 新增

- 首个公开版本
- 9 大逆向 Skill（`softseep` 总控 + `apkseep` + `ida-reverse` + `safe-skills` 5 组）
- 自研 `seep` MCP 服务（23 项原生工具）
- 289+ 篇攻防知识库
- 9 个脱敏工业案例范式（项目 A ~ 项目 I）
- Lab Mode 磁盘状态机与三层防拒体系

---

## 更新类型说明

| 变更类型 | 含义 | 用户需要做什么 |
|---|---|---|
| **新增** | 新功能、新工具、新案例 | 跑一次更新脚本即可 |
| **变更** | 行为或接口调整 | 建议读一下具体条目 |
| **修复** | 缺陷修复 | 跑一次更新脚本即可 |
| **安全** | 安全或隐私相关 | **强烈建议立即更新** |

> **兼容性承诺**：本工作台的用户自有数据（`models.json`、`auth.json`、自定义 MCP 条目、
> `lab-mode.flag`）在更新过程中**永不被覆盖**。若某次更新需要用户手工干预，
> 会在对应条目中显式标注「**需要手工操作**」。
