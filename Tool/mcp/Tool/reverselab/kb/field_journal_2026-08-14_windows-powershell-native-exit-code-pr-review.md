# 2026-08-14 Windows PowerShell 原生命令退出码 PR 审查

## 场景分类

其他（工具链、供应链引导脚本、开放 PR 审查）

## 目标概述

评估一个固定来源与提交的引导脚本 PR，并验证它在 Windows PowerShell 5.1 下是否保持 fail-closed 且不误拒绝合法 checkout。

## Scope 摘要（脱敏）

- auth_basis: 仓库维护者授权审查公开 PR 并提交 review
- network_profile: 公开代码托管平台；取证阶段只读，结论确认后提交 review
- asset_types: [公开源代码, CI 结果, Windows PowerShell 引导脚本]

## 角色

- lead_role: lead
- specialists: [supply-chain-reviewer, windows-compatibility-reviewer]

## 完整执行链路

1. 固定 PR head commit，读取变更、讨论、CI 和目标脚本，避免审查移动目标。
2. 将安全目标拆成来源固定、提交固定、原子替换、脏目录拒绝、锁文件安装和平台兼容性六项。
3. 确认 manifest 单一来源、staged checkout、dirty-tree fail-closed 与 frozen lockfile 的设计方向有效。
4. 定位 checkout 验证函数，分别在 Windows PowerShell 5.1 中执行原生命令和带 `Select-Object` 的管道版本。
5. 观察到两种执行都返回相同 commit 文本，但管道版本读取到 `-1` 的 `$LASTEXITCODE`，导致合法 checkout 被误拒绝。
6. 运行供应链测试脚本，确认失败在进入预期的 dirty-tree 断言前发生，排除测试夹具本身的问题。
7. 在 PR 上提交 changes-requested review，要求先保存原生命令退出码再处理输出，并增加 Windows PowerShell 5.1 验证。
8. 将复现方法和审查准则脱敏回写，供后续 PowerShell 引导脚本审查复用。

## Evidence 链摘要（脱敏）

| E-id | severity | status | source_type | 可复用命令模式 | 关联 Finding |
|------|----------|--------|-------------|----------------|--------------|
| E-001 | info | observed | command | `powershell.exe -NoProfile -Command "& git -C {install_dir} rev-parse HEAD; $LASTEXITCODE"` | F-001 |
| E-002 | medium | validated | command | `powershell.exe -NoProfile -Command "& git -C {install_dir} rev-parse HEAD \| Select-Object -First 1; $LASTEXITCODE"` | F-001 |
| E-003 | medium | validated | command | `powershell.exe -NoProfile -File skills/scripts/tests/test-bootstrap-supply-chain.ps1` | F-001 |

## Finding / Path 摘要

- top_finding: Windows PowerShell 5.1 中，原生命令输出接入对象管道后再读取 `$LASTEXITCODE`，可能得到 `-1`，即使输出的 commit 与固定值完全一致，也会触发错误的 checkout verification failure。
- path_type: callflow
- path_one_liner: `git rev-parse` 成功 → 输出进入 `Select-Object` → `$LASTEXITCODE` 被改写 → 合法 checkout 被 fail-closed 分支误拒绝

## 踩坑记录

| 问题 | 原因 | 解决方案 | 耗时 |
|------|------|---------|------|
| 所有现有 CI 通过但 Windows 仍有回归 | CI 覆盖了新版 PowerShell 和 Bash，未覆盖 Windows PowerShell 5.1 的原生命令管道语义 | 用 `powershell.exe` 运行最小复现与完整供应链测试 | 约 20 分钟 |
| commit 文本相同却被判定不一致 | 验证逻辑同时依赖输出和延后读取的 `$LASTEXITCODE` | 原生命令返回后立即保存退出码，再单独规范化输出 | 约 10 分钟 |
| PR 显示 clean 容易被误认为可直接合并 | mergeable 只说明 Git 合并状态，不证明目标运行时兼容 | 将 base 新鲜度、平台矩阵和本地复现作为独立门禁 | 约 5 分钟 |

## 工具链发现

- GitHub API 适合固定 PR head、读取 CI 和提交状态；审查记录应绑定已验证的 commit。
- `powershell.exe` 与 `pwsh` 不是可互换的测试入口。面向 Windows PowerShell 5.1 的脚本必须由对应宿主执行测试。
- `$LASTEXITCODE` 是会变化的会话状态；任何后续管道或命令都可能让延后读取失去原生命令语义。

## 关键代码/命令

```powershell
# 先捕获原生命令的输出，并立刻保存退出码。
$output = & git -C $CheckoutPath rev-parse HEAD 2>$null
$gitExitCode = $LASTEXITCODE
$resolvedCommit = [string]($output | Select-Object -First 1)

if ($gitExitCode -ne 0 -or $resolvedCommit.Trim() -ne $PinnedCommit) {
    throw "Checkout verification failed"
}
```

## 对本包的改进建议

- 为修改 PowerShell 引导脚本的 PR 增加 `powershell.exe` 5.1 测试任务，避免只由 `pwsh` 覆盖。
- 在供应链审查清单中加入“原生命令退出码是否在下一条命令前保存”。
- 合并前同时检查 PR head、最新 main 差异和目标平台测试，不用 GitHub 的 clean 状态替代运行时验证。

## 可复用的模式/脚本片段

对所有 PowerShell 原生命令采用三段式处理：执行并捕获输出、立即保存 `$LASTEXITCODE`、最后使用 PowerShell 管道解析输出。错误判定只能使用已保存的退出码。

## 进化动作

- [ ] 更新了路由矩阵
- [ ] 更新了 tool-index
- [ ] 更新了 bootstrap-manifest
- [ ] 更新了子 skill 文档
- [x] 新增了 pitfalls 记录
- [ ] 无需更新

## 环境信息

- OS: Windows
- 工具版本: Windows PowerShell 5.1，Git 2.x
- 目标平台/版本: PowerShell 兼容引导脚本，公开 PR head commit

## 脱敏检查

- [x] 无真实域名、IP、凭证、Token、Cookie 或 PII
- [x] 本机安装路径已替换为 `{install_dir}`
- [x] 未附带用户项目文件或私有仓库内容

---
<!-- [进化统计] 本包累计完成项目: 18 | 本次新增模式: 1 | 本次修复工具链问题: 0 -->
<!-- [社区贡献] 用户已授权通过独立 PR 回写本条脱敏经验。 -->
