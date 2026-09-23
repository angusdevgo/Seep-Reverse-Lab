# 2026-09-03 多 Issue/PR 安全边界集成

## 场景

维护一个公开安全技能路由仓库：本地主工作树包含大量用户改动且落后远端，需要同时审查多个开放 PR、解决历史 Issue、补功能、发布安全复审，并确保 GitHub 状态和跨平台 CI 闭环。

## 可复用模式

1. **脏工作树隔离：** 先 fetch 远端，再从 `origin/main` 创建独立 worktree；所有 PR merge、冲突解决、测试和提交都在隔离目录完成。
2. **保留 PR 归属：** 将接受的 PR head 作为 merge commit 父提交合入集成分支；最终快进推送 main 后，GitHub 自动把对应 PR 标记为 merged/closed。
3. **状态冻结：** 合并前记录每个 PR 的 head SHA；推送前重新 fetch，要求远端 main 仍等于审查基线，并验证所有接受的 PR head 都是最终 HEAD 的祖先。
4. **AV 隔离下审查：** 对可能被 Defender 隔离的 payload 文档，不依赖工作树文件；用 `git show :path` / Git index blob 做哈希、链接和内容边界检查。
5. **参考/可执行分层：** 被动 Markdown/JSON payload 可以保留，但可执行脚本不得引用它；CI 固定 corpus hash、二进制 allowlist、符号链接、危险模式和 GitHub Action full-SHA。
6. **功能 PR 不盲合：** 除运行原 PR 测试外，还要检查跨实例状态、路径/端口隔离和主线新约束。本次发现 IDA keepalive 文件未按端口隔离，并在合并提交中修正。
7. **Issue 清仓有依据：** 每个 Issue 先回可追溯结论，再用 completed / duplicate / not_planned 关闭；不以“批量清理”为理由省略说明。

## 踩坑

| 问题 | 原因 | 处理 |
|---|---|---|
| PR 在 GitHub 显示 mergeable，但合入最新主线仍有语义冲突 | PR base 落后，且多个 PR 修改同一 CI/路由文件 | 本地模拟 merge，按最新 SSoT 解决后重跑全套测试 |
| AV 删除 payload 工作树文件导致普通扫描漏检 | 扩展名为 Markdown 也会命中特征签名 | 从 Git index blob 读取，禁止“读不到就跳过” |
| Binary Ninja MCP 来源易被误认为官方 | MCP 项目是社区 GPL 插件，不是 Vector 35 官方组件 | 在 skill 中明确来源、审查 commit、bridge 版本与回环绑定 |
| Git Bash 无法等价模拟 Linux Python→bash 子进程 | Windows CreateProcess 优先解析系统 `bash.exe`/WSL | 本地跑 Bash 语法和直接契约，最终以 Ubuntu/macOS CI 为准 |

## 验证

- 路由回归：175/175
- Windows PowerShell 5.1 与 PowerShell 7：P0、编码、Evidence、IDA、smoke 全通过
- Python：case-review、文档链接、repository security 全通过
- Bash：语法、case workflow、新 Binary Ninja 路由通过
- GitHub：Windows、Ubuntu、macOS、Gradle Wrapper Validation 全通过
- 远端开放 Issue / PR：均为 0

## 环境

- OS：Windows
- Git：隔离 worktree + PR head ancestor verification
- CI：Windows、Ubuntu、macOS
- 数据处理：仅公开仓库元数据和脱敏方法记录
