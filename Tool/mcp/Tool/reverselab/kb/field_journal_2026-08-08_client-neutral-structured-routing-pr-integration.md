# 2026-08-08 平台无关结构化路由 PR 集成

## 场景分类

代码审计 / 工具链维护 / 多平台路由

## 目标概述

对多组高冲突 PR 做增量价值审查，并将有价值部分重构为平台无关核心后集成。

## Scope 摘要（脱敏）

- auth_basis: repository_owner_authorized
- network_profile: authorized_upstream_only
- asset_types: [source_repository, pull_request_refs, local_tests]

## 角色

- lead_role: lead
- specialists: [cae, doc]

## 完整执行链路

1. 从远端抓取 PR refs，在隔离 worktree 中比较各 PR 与当前主线。
2. 先按增量价值判断，再用 merge parent 保留来源关系，并按语义解决冲突。
3. 将结构化路由从客户端接入中解耦，以 JSON 作为 PowerShell/Bash 共同事实源。
4. 对大 PR 只取授权门禁和 Bash parity，排除客户端专属与生成资产。
5. 运行全量路由、结构门禁、语言单测、语法与 manifest 校验。

## Evidence 链摘要（脱敏）

| E-id | source_type | 可复用命令模式 | 关联 Finding |
|------|-------------|----------------|--------------|
| E-001 | git diff | `git diff <main>...<pr-ref>` | F-001 |
| E-002 | regression | `test-routing.ps1` + coherence + smoke | F-001 |
| E-003 | unit tests | Python unittest + Node test + Bash parity | F-002 |

## Finding / Path 摘要

- top_finding: 客户端集成不是结构化路由的核心价值，单一事实源与自动门禁才是。
- path_type: callflow
- path_one_liner: 任意宿主 → 可选适配器 → routing.json → 跨平台 router → 统一回归门禁

## 踩坑记录

| 问题 | 原因 | 解决方案 | 耗时 |
|------|------|---------|------|
| 大 PR 同时混入客户端清单、GIF、脚本和文档 | 关注点未拆分 | 只合并最小跨平台子集 | 中 |
| Bash router 与 PowerShell 各自硬编码 | 两份事实源必然漂移 | Bash 通过 Python 读取同一 JSON | 中 |
| 新 pin gate 首次失败 | Kali manifest 保留浮动源 | pin manifest 且让实际安装命令使用 pin | 中 |
| Gradle wrapper 下载 TLS 中断 | 外部网络握手异常 | 记录并在最终验证重试 | 低 |
| Bash CaseName 可写出 work 根 | 选择性合并时漏掉 PowerShell 已有的路径约束 | 补跨平台等价校验与负向 CI | 中 |
| 授权 URL 被标成 offline | Bash 默认值未与 PowerShell 对齐 | 网络目标默认 authorized_target_only；offline 仅本地样本 | 低 |
| INDEX 在开发机通过、clean clone 失败 | 生成器扫描了被忽略的本地私有模块 | 只枚举 Git 已跟踪 SKILL.md | 中 |

## 工具链发现

Git merge parent 能保留 PR 来源关系，同时允许在 merge commit 内做语义删减。供应链 gate 只有在 manifest 元数据与实际安装命令共同固定时才有效。

## 关键代码/命令

```text
git merge --no-ff --no-commit <pr-ref>
powershell -File skills/scripts/test-routing.ps1
powershell -File skills/scripts/verify-routing-coherence.ps1
bash skills/scripts/master-route.sh --hint "case review evidence graph"
```

## 对本包的改进建议

所有客户端适配器放在独立边界；禁止将客户端配置写进核心路由 PR。大型 PR 必须按核心、适配器、演示资产和文档拆分。

## 可复用的模式/脚本片段

结构化路由 parity 测试至少覆盖普通路由、冲突优先级路由和最新新增路由，防止某个平台入口滞后。

对同一 163 条基准做旧/新 A/B：旧硬编码实现 137/163（84.05%），结构化实现 163/163（100%）。只有这种同输入量化对比，才能证明重构是实质提升而非文件数量增长。

## 进化动作

- [x] 更新了路由矩阵
- [ ] 更新了 tool-index
- [x] 更新了 bootstrap-manifest
- [x] 更新了子 skill 文档
- [x] 新增了 pitfalls 记录
- [ ] 无需更新

## 环境信息

- OS: Windows（主验证）+ Linux CI 定义
- 工具版本: Git / PowerShell / Python 3 / Node.js / Bash
- 目标平台/版本: client-neutral repository core

## 脱敏要求

本条目不包含真实目标、凭据、内部地址或个人身份信息。

---
<!-- [社区贡献] 已按仓库所有者指示准备推送主线。 -->
