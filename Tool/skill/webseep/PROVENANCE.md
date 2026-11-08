# 第三方素材来源与许可（PROVENANCE）

## 来源

| 项 | 值 |
| :--- | :--- |
| 仓库 | `WhiteNightShadow/hello_js_reverse_skill` |
| 地址 | https://github.com/WhiteNightShadow/hello_js_reverse_skill |
| 版本 | v3.9.0 |
| 导入时 commit | `ec3cc38` |
| 导入日期 | 2026-11-03 |

## 导入清单（只取 5 项，不装整套）

| 本地路径 | 上游路径 | 行数 | 补的缺口 |
| :--- | :--- | ---: | :--- |
| `scripts/sandbox-runner.js` | `scripts/sandbox-runner.js` | 379 | JS 沙盒执行器（免费替代 iv8 补环境路线） |
| `references/protocol-analysis.md` | 同名 | 273 | 协议层对抗：TLS 指纹 / HTTP2 / 频控 |
| `references/crypto-patterns.md` | 同名 | 424 | 加密算法识别与 Node/Python 双语言复现 |
| `references/common-pitfalls.md` | 同名 | 24 | 反模式清单（observer effect 等） |
| `templates/python-request/` | 同名（11 文件） | — | 带分页 / 断点续采 / 去重的采集工程骨架 |

**未导入**（刻意排除，避免路由膨胀与技能边界模糊）：`general-collection.md`、`task-preflight.md`、`mcp-*` 系列、
`templates/{node-request,vm-sandbox,wasm-loader,browser-auto}`、`cases/`、`scripts/real_cases/`。

原因：这套内容 40% 是**采集工程**（分页/断点/基线），与本工作台「影视源逆向 + 判权审计」主业重叠度低；
且它的工作流绑定 `camoufox-reverse-mcp`，本机未安装该 MCP，流程无法一一对应。

---

## ⚠️ 许可状态（重要）

**上游仓库根目录没有 LICENSE 文件**（已确认：仅有 README / SKILL / cases / docs / examples /
references / scripts / templates / tests，无 LICENSE / COPYING）。按默认版权法，这属于
**保留所有权利（All rights reserved）**，即上游未显式授予再分发许可。

因此：

| 允许 | 禁止 |
| :--- | :--- |
| ✅ 本机自用、阅读、改造 | ⛔ 再次分发（推送到公开仓库 / 打包对外发布） |
| ✅ 用于自己已授权目标的作业 | ⛔ 以任何形式声称这些文件由本工作台原创 |

> 若要对外发布含这些文件的工作台，必须先从上游取得明确授权，或自行重写等价内容。

---

## 本地适配说明

导入时**未修改文件正文**，仅：

1. 保持原始目录语义（`references/`、`scripts/`、`templates/`），使其相对引用仍然成立；
2. 在 `webseep/SKILL.md` 中登记入口，说明何时读哪个文件；
3. 绕开 `/skill:name` 路由负担：这些文件属于 `webseep` Skill 的按需加载内容，**不新增技能**。

上游文件内部若提到 `camoufox-reverse-mcp` 的特定工具名（`launch_browser` / `search_code` /
`hook_function` 等），本机请映射为已有的 `js_reverse_*` 工具面；方法论本身与 MCP 无关。
