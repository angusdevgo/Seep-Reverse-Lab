# 2026-08-17 reverse-skill

## 场景分类
工具链与环境（引导阶段缺陷修复）

## 目标概述
修复本机引导过程中的三类被层层掩盖的缺陷：tool-index 把 radare2 主分析器 `r2` 误报为 no；多个测试脚本硬编码 `powershell` 子进程调用在仅装 PowerShell 7+ 的机器上失败；以及被该失败掩盖的 pin gate StrictMode 属性访问 bug。

## Scope 摘要（脱敏）
- auth_basis: own_system（本仓库自身）
- network_profile: offline / 无外部目标 ACT
- asset_types: [本地脚本与工具索引]

## 角色
- lead_role: lead
- specialists: [bootstrap, test-infra]

## 完整执行链路

1. 按 `README_AI.md` 第 0 节执行引导：`refresh-tool-index.ps1` 生成 tool-index.md（37 工具）。
2. 读 `tool-index.md` 发现异常：`r2`（radare2 主分析器）= no，但同目录 `rabin2/rasm2/radiff2/rahash2/rax2/r2pm` 全部 = yes。
3. 列 `C:\Users\{username}\Tools\radare2\bin` 确认：存在 `r2.bat`（21 字节，内容 `@"%~dp0\radare2" %*`）与 `radare2.exe`，**无 `r2.exe`**。
4. 读 `lib/ToolDiscovery.ps1:131-141`，`r2` 的 Fallbacks 只找 `r2.exe`，漏掉 `r2.bat`/`radare2.exe`。对比 `jadx`/`apktool`/`analyzeHeadless` 都为 `.bat` 工具配了 fallback。
5. 修复：给 `r2` Fallbacks 补 `r2.bat` 与 `radare2.exe` 路径（覆盖 `%USERPROFILE%\Tools\radare2\bin`、根目录、`C:\Tools\` 三套位置），保留原 `r2.exe` fallback 兼容其他机器。
6. 重跑 `refresh-tool-index.ps1`，`r2` 转 yes，路径 `r2.bat`，版本 `radare2 6.2.0`，来源 `FallbackPath`。
7. 跑 `smoke.ps1` 仍 FAIL：`verify-routing-coherence exit 1`。直接跑 verify 看错误，定位到 `verify-routing-coherence.ps1:257` 硬编码 `& powershell`，本机无 `powershell`（只有 `pwsh` 7.6.4）。
8. grep 全仓 `.ps1` 的 `powershell\s(-NoProfile|-ExecutionPolicy|-File|-Command)`，发现 5 个脚本共 20+ 处硬编码 `& powershell` 子进程调用（verify 7 处 / test-p0-friction 18 处 / test-routing 1 处 / case-init 1 处；其余为注释示例）。
9. 发现 `smoke.ps1:31-46` 已正确用 `$SmokeHostExe`（当前进程路径优先 → pwsh → Windows PowerShell 路径兜底）。提取该已验证逻辑为共享函数 `Resolve-ReverseHostExe`，新建 `lib/HostRuntime.ps1`，解析顺序：当前进程 → `pwsh` → `powershell` → `%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe`。
10. 4 个子脚本 dot-source `HostRuntime.ps1` 并定义 `$HostExe`，`replaceAll` 把 `& powershell -NoProfile -ExecutionPolicy Bypass -File` → `& $HostExe -NoProfile -ExecutionPolicy Bypass -File`；`test-p0-friction.ps1:244` 的 `cmd /c "powershell ..."` 单独改为 `cmd /c "`"$HostExe`" ..."`（路径可能含空格需引号包裹）。
11. 重跑 smoke，verify 走过 257，但暴露 `verify-routing-coherence.ps1:414` pin gate 在 `Set-StrictMode -Version Latest` 下访问 `$cap.pinnedVersion` 等不存在属性报错——这是被 powershell bug 掩盖至今的预存在 bug。
12. 修复 414：把 `$cap` 转 hashtable（`$capMap`），用索引访问不存在的 key 返回 `$null` 不报错，pin gate 语义不变。
13. 重跑 smoke → ALL PASS（VERIFY_EXIT=0 / PARSE 11/11 / ROUTE 9/9）。
14. 跑 `test-routing.ps1` → 166/166 ALL PASS。
15. 跑 `test-p0-friction.ps1` → 大部分过，但 `:343` 与 `:364` 又遇 `Start-Process -FilePath 'powershell.exe'`（之前 grep 模式 `powershell\s+(-NoProfile...)` 漏了 `powershell.exe` 字面）。
16. grep `powershell\.exe`，确认仅 test-p0-friction 的 343/364 两处是硬编码 Start-Process（其余为兼容查找或 fallback 路径），`replaceAll` 改为 `Start-Process -FilePath $HostExe`。
17. 重跑 `test-p0-friction.ps1` → ALL PASS（FAIL_COUNT=0）。三套件全绿。

## Evidence 链摘要（脱敏）
> 本次为本仓库自身引导修复，无外部目标 ACT，不产出 case 目录下的 evidence 文件。以下为可复现验证命令（等价 Evidence）。

| E-id | severity | status | source_type | 可复用命令模式 | 关联 Finding |
|------|----------|--------|-------------|----------------|--------------|
| E-r2 | info | validated | command | `pwsh -File skills/scripts/refresh-tool-index.ps1` 后 tool-index.md 中 `r2` 行 = yes | F-r2 |
| E-smoke | info | validated | command | `pwsh -File skills/scripts/smoke.ps1` → `OVERALL: ALL PASS` | F-host |
| E-route | info | validated | command | `pwsh -File skills/scripts/test-routing.ps1` → `166/166 ALL PASS` | F-host |
| E-p0 | info | validated | command | `pwsh -File skills/scripts/test-p0-friction.ps1` → `OVERALL: ALL PASS` | F-host |

## Finding / Path 摘要
- top_finding: 三类缺陷层层掩盖——`r2` fallback 遗漏 `.bat` 入口 → `verify` 硬编码 `powershell` 失败中断 → 掩盖 pin gate StrictMode 属性访问 bug；grep 兼容扫描又漏 `powershell.exe` 字面。
- path_type: solve
- path_one_liner: 用共享 `Resolve-ReverseHostExe`（当前进程优先）统一子进程入口、为 `r2` 补 `.bat`/`radare2.exe` fallback、用 hashtable 安全访问 PSCustomObject 可选属性。

## 踩坑记录

| 问题 | 原因 | 解决方案 | 耗时 |
|------|------|---------|------|
| tool-index 把 `r2` 标 no，但同目录其他 r2* 工具 yes | `ToolDiscovery.ps1` 的 `r2` Fallbacks 只找 `r2.exe`，而 radare2 Windows 发行版用 `r2.bat` 包装 `radare2.exe`，无 `r2.exe` | 补 `r2.bat` 与 `radare2.exe` 路径 fallback | 短 |
| smoke 仍 FAIL：verify exit 1 | verify 内部硬编码 `& powershell`，本机仅装 pwsh 7+，无 `powershell` | 新建 `lib/HostRuntime.ps1` 的 `Resolve-ReverseHostExe`，4 脚本替换为 `& $HostExe` | 中 |
| verify 修好 powershell 后又失败在 414 | 被 257 的 powershell bug 掩盖的预存在 bug：StrictMode 下访问 `$cap.pinnedVersion` 等不存在属性报错 | `$cap` 转 hashtable `$capMap`，索引访问不报错 | 短 |
| test-p0-friction 在 343/364 又失败 | `Start-Process -FilePath 'powershell.exe'` 硬编码；之前 grep 模式 `powershell\s+(-NoProfile...)` 漏了 `powershell.exe` 字面 | grep `powershell\.exe` 补全，改用 `$HostExe` | 短 |
| test-p0-friction 输出大量 `Exception: case-init.ps1:54` | 测试 14b 故意用非法 CaseName 触发 case-init 抛异常，属预期 | 无需处理，最终 FAIL_COUNT=0 即通过 | — |

## 工具链发现
- **radare2 Windows 发行版结构**：主程序是 `radare2.exe`，`r2.bat`（`@"%~dp0\radare2" %*`）是其批处理包装器，**没有 `r2.exe`**。任何按 `r2.exe` 探测的工具扫描都会误报。同目录 `rabin2.exe`/`rasm2.exe` 等是独立 `.exe`，可正常探测。
- **PowerShell 7+ 单装环境**：本机 `pwsh` 7.6.4（路径 `C:\Program Files\WindowsApps\Microsoft.PowerShell_7.6.4.0_x64__8wekyb3d8bbwe\pwsh.exe`），**无 `powershell` / `powershell.exe`**。所有 `& powershell ...` 子进程调用在此环境直接失败。
- **StrictMode 属性访问**：`Set-StrictMode -Version Latest` 下访问 `PSCustomObject` 不存在的属性会抛错；用 hashtable 索引访问不存在的 key 返回 `$null`，是 pin gate 这类"可选属性多"场景的安全写法。
- **grep 兼容扫描盲区**：用 `powershell\s+(-NoProfile...)` 只能抓 `& powershell -File` 形式，漏掉 `Start-Process -FilePath 'powershell.exe'` 与 `cmd /c "powershell ..."`。兼容性扫描应同时覆盖 `powershell\s` 与 `powershell\.exe` 两类。

## 关键代码/命令

```powershell
# lib/HostRuntime.ps1 —— 统一子进程 PowerShell 入口（当前进程优先）
function Resolve-ReverseHostExe {
    [CmdletBinding()] [OutputType([string])] param()
    $hostExe = $null
    try { $p = (Get-Process -Id $PID -ErrorAction Stop).Path; if ($p -and (Test-Path -LiteralPath $p)) { $hostExe = $p } } catch { }
    if (-not $hostExe) { $c = Get-Command pwsh -ErrorAction SilentlyContinue; if ($c -and $c.Source) { $hostExe = $c.Source } }
    if (-not $hostExe) { $c = Get-Command powershell -ErrorAction SilentlyContinue; if ($c -and $c.Source) { $hostExe = $c.Source } }
    if (-not $hostExe -and $env:SystemRoot) { $f = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'; if (Test-Path -LiteralPath $f) { $hostExe = $f } }
    if (-not $hostExe) { throw 'No usable PowerShell host executable found.' }
    return $hostExe
}

# ToolDiscovery.ps1 r2 Fallbacks —— 补 .bat/.exe 入口
Fallbacks = @(
    @{ Type = 'command'; Value = 'r2' },
    @{ Type = 'command'; Value = 'radare2' },
    @{ Type = 'path'; Value = (Join-Path $userProfile 'Tools\radare2\bin\r2.bat') },
    @{ Type = 'path'; Value = (Join-Path $userProfile 'Tools\radare2\bin\radare2.exe') },
    @{ Type = 'path'; Value = (Join-Path $userProfile 'Tools\radare2\bin\r2.exe') }
    # ... 根目录与 C:\Tools 镜像
)

# verify-routing-coherence.ps1:412 —— pin gate 安全属性访问
foreach ($cap in $mc.capabilities) {
    $capMap = @{}
    foreach ($prop in $cap.PSObject.Properties) { $capMap[$prop.Name] = $prop.Value }
    if (-not $capMap['canAutoInstall']) { continue }
    $hasPin = ($capMap['pinnedVersion'] -or $capMap['pinnedCommit'] -or $capMap['pinPolicy'])
    # ... switch ($capMap['bootstrapKind']) ...
}
```

## 对本包的改进建议
- **兼容性扫描脚本化**：在 `verify-routing-coherence.ps1` 或独立 lint 中，扫描所有 `.ps1` 的子进程调用，禁止裸 `powershell` / `powershell.exe`，统一要求经 `Resolve-ReverseHostExe`。本次靠手工 grep，易漏（已踩 `powershell.exe` 盲区）。
- **tool catalog 的 `.bat` 约定**：Windows 上 `jadx`/`apktool`/`r2`/`analyzeHeadless` 都是 `.bat` 包装 `.exe`，catalog 应为每个这类工具同时配 `.bat` 与对应 `.exe` fallback，避免逐个踩坑。
- **CI 应包含"仅 pwsh"矩阵**：在 GitHub Actions 的 `windows-latest` 上，若不预装 Windows PowerShell 5.1，本类 bug 会被暴露。当前 `smoke.ps1` 已用 `$SmokeHostExe` 做对了，但子脚本没复用。
- **StrictMode 下遍历 PSCustomObject**：pin gate 这类"对象 schema 宽松"的检查，统一用 hashtable 转换访问，或提供 `Get-SafeProp` 辅助函数。

## 可复用的模式/脚本片段
- `Resolve-ReverseHostExe`：任何脚本需要启动子 PowerShell 进程时，dot-source `lib/HostRuntime.ps1` 后 `& $HostExe -NoProfile -ExecutionPolicy Bypass -File <script> ...`，兼容 pwsh-only / powershell-only / 混装环境。
- `$capMap` 转换：遍历 `PSCustomObject` 属性到 hashtable 后索引访问，规避 StrictMode 属性不存在异常。
- `r2.bat` → `radare2.exe` 透传：版本检测 `r2.bat -v` 能正确返回 `radare2 6.2.0`，证明 `.bat` 包装器透传参数有效，可放心用作 catalog 入口。

## 进化动作
- [x] 更新了 tool-index（r2 转为 yes，路径 r2.bat）
- [x] 新增 `skills/scripts/lib/HostRuntime.ps1`
- [x] 修复 `ToolDiscovery.ps1` r2 Fallbacks
- [x] 修复 `verify-routing-coherence.ps1` powershell 硬编码 + pin gate StrictMode
- [x] 修复 `case-init.ps1` / `test-routing.ps1` / `test-p0-friction.ps1` powershell 硬编码
- [ ] 更新了路由矩阵（无）
- [ ] 更新了 bootstrap-manifest（无）
- [ ] 新增了 pitfalls 记录（本条即）

## 环境信息
- OS: Windows（win32）
- Shell/Host: pwsh 7.6.4（`C:\Program Files\WindowsApps\Microsoft.PowerShell_7.6.4.0_x64__8wekyb3d8bbwe\pwsh.exe`）；本机无 `powershell` / `powershell.exe`
- radare2: 6.2.0 +1 abi:132 @ windows-x86_64（安装于 `C:\Users\{username}\Tools\radare2\bin\`）
- 仓库根: `D:\Sources\reverse-skill`

## 脱敏要求
本次为本仓库自身脚本修复，无真实目标域名/IP/凭据，无需脱敏。

## 索引同步（提交前最后一步）

写完本日志后，同步更新 `_index.md`：
1. 「工具链与环境」小节新增一行 ✓
2. 「高频成功模式」追加本文件名（PowerShell 子进程入口统一）✓
3. 「实体倒排」追加本文件名（reverse-skill 引导脚本）✓
4. 更新「统计」总数与最近更新日期 ✓

---
<!-- [进化统计] 本包累计完成项目: 19 | 本次新增模式: 1 (Resolve-ReverseHostExe 子进程入口统一) | 本次修复工具链问题: 3 (r2 fallback / powershell 硬编码 / pin gate StrictMode) -->
<!-- [社区贡献] 本修复为仓库自身引导缺陷修复，符合 CONTRIBUTING.md 的修复类 PR；完成後询问用户是否提交。 -->
