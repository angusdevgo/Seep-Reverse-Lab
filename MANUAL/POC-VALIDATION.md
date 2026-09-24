# MANUAL — PoC 闭环自动化验证 SOP (Automated PoC Validation & Self-Healing)

> 本文件定义了从 Agent 生成 PoC（Frida 脚本 / Smali 补丁 / 代理 DLL）到
> **自动化执行、捕获回显、报错自愈** 的完整端到端验证流程。
>
> 目标：让 Agent 交付的 PoC 从"推测可行的代码"进化为"**100% 执行验证过的有效 PoC**"。

---

## 一、 三阶段闭环验证模型

```
G4/G5：生成 PoC
  │
  ▼
[阶段 1] 静态自检 —— 语法解析、类名/方法签名格式校验
  │ 通过
  ▼
[阶段 2] 沙箱执行 —— 注入目标进程 / 模拟器，捕获 stdout/stderr
  │ 通过      失败
  ▼           ▼
[阶段 3]  [自愈循环（最多 2 次）]
结论确认   解析报错 → Agent 定位错误类型 → 修正代码 → 重跑
输出验证   若 2 次自愈失败 → 标注"需人工校准"，输出 diff 报告
闭环报告
```

---

## 二、 Frida 脚本静态自检 → 自动执行 → 报错自愈（P0 优先实现）

### 2.1 Agent 执行序列（写入 AGENTS.md 执行纪律）

在 Agent 生成 Frida 脚本（`hook_verify.js`）后，必须立即执行以下序列，不得跳过直接进报告：

```powershell
# Step 1：Node.js 语法快检（不启动 Frida，仅校验 JS 语法）
node --check hook_verify.js
if ($LASTEXITCODE -ne 0) {
    Write-Error "[自愈 Step 1] JS 语法错误，Agent 自动修正后重跑"
    # → 回传报错给 Agent，Agent 修正后重新生成并再次检查
}

# Step 2：连接模拟器/测试机 (adb)，注入目标包并捕获输出
$pkg = "com.example.target"   # 从 seep_apk_info 获取
frida -U -f $pkg -l hook_verify.js --no-pause 2>&1 | Tee-Object -FilePath frida_run.log &
Start-Sleep -Seconds 10       # 给 Frida 10 秒采集输出
Stop-Process -Name frida -ErrorAction SilentlyContinue

# Step 3：分析 frida_run.log，由 Agent 读取并判定结果
Get-Content frida_run.log
```

### 2.2 常见报错 → 自愈映射表

| 报错特征 | 根因 | 自愈操作 |
|---|---|---|
| `Java.ClassNotFoundException: com.x.y.Auth` | 类名拼写错误或混淆 | 重新调 `seep_apk_smali_search` 找正确类路径 |
| `Error: expected a pointer` | 参数类型声明错误 | 修正 `Java.use` 链中的类型签名 |
| `Process not found` | 目标 App 未前台运行 | 先启动目标 App 再 attach：改 `-f` 为 `-n` |
| `Error: unable to find module` | so 库未加载 | 加 `waitForModule()` 等待动态加载后 hook |
| `Script terminated` 无任何 console 输出 | onEnter/onLeave 挂钩点在 Dalvik 解释模式 | 改用 `Java.deoptimizeEverything()` 强制解释执行 |
| `Access violation` / 程序崩溃 | 内存写越界或返回类型错误 | 检查 `retval.replace()` 的参数类型一致性 |

---

## 三、 Windows Smali / Binary Patch 本地加载器验证

### 3.1 Smali 补丁验证流程

```powershell
# 前置：已用 apktool d 解包并修改 smali，现在重打包
cd task_sandbox\<task_name>

# 重打包
.\Tool\mcp\Tool\safe\apktool\apktool.bat b smali_patched -o target_repacked.apk

# Zipalign 4 字节对齐（必须，否则 ART 拒绝加载）
zipalign -v 4 target_repacked.apk target_aligned.apk

# 签名（测试用 debug 密钥）
apksigner sign --ks ~/.android/debug.keystore --ks-pass pass:android `
  --out target_signed.apk target_aligned.apk

# 安装到测试机并捕获 logcat
adb install -r target_signed.apk
adb logcat -c && adb logcat | Select-String "VIP|Premium|License|granted|unlocked|ERROR"
```

### 3.2 Windows 代理 DLL 本地加载验证

```powershell
# 在隔离沙箱副本中加载代理 DLL，捕获函数返回值
# 前提：已编译生成 anti_debug_patch.dll

# 创建进程副本（绝对不要在生产环境直接测试）
$targetCopy = ".\sandbox\target_copy.exe"
Copy-Item "target.exe" $targetCopy

# 将代理 DLL 放置在 target_copy.exe 同目录（version.dll 劫持）
Copy-Item ".\patches\version.dll" ".\sandbox\version.dll"

# 启动进程并监控退出码与关键窗口
$proc = Start-Process $targetCopy -PassThru
Start-Sleep -Seconds 5
if (-not $proc.HasExited) {
    Write-Host "[PASS] 进程正常运行，代理 DLL 注入无崩溃"
    # 截图或 spy++ 检查目标窗口状态（标题栏是否出现"专业版"字样）
} else {
    Write-Host "[FAIL] 进程崩溃，退出码 $($proc.ExitCode)"
    # → 回传报错，Agent 检查 DLL 导出表是否与 system32\version.dll 一致
}
```

---

## 四、 离线确证（断网铁证 — CWE-602 终极验证）

PoC 执行成功后，**必须在飞行模式 / 断网状态下补做终极确证**，否则无法区分本地决策与服务端下发：

```text
验证步骤：
1. 关闭所有网络接口（或开飞行模式）
2. 重启目标 App（清除任何本地缓存）
3. 在断网状态下重新触发受限功能
4. 观察是否依然解锁/生效

结论判定：
  ✓ 断网后受限功能依然生效 → 确认为 CWE-602 本地决策脆弱性，PoC 有效
  ✗ 断网后功能失效 → 服务端权威强依赖，本地 PoC 无法构成完整绕过，报告需标注"需服务端协同"
```

---

## 五、 PoC 自愈循环上限与熔断规则

| 轮次 | 操作 | 若失败 |
|---|---|---|
| 第 1 次 | 生成 PoC → 静态自检 → 沙箱执行 | 解析报错 → 进入自愈 |
| 第 2 次 | Agent 分析报错 → 修正代码 → 重跑 | 解析报错 → 再试一次 |
| 第 3 次 | 最终修正 → 重跑 | **触发熔断：停止自动化，输出 diff 报告，标注"需人工校准"** |

熔断后 Agent 必须输出：
```markdown
## PoC 自动化验证受阻通知

- **PoC 文件**：`task_sandbox/<name>/hook_verify.js`
- **失败原因**：[具体报错摘要]
- **自愈尝试次数**：3 次（已达上限）
- **建议**：将 `frida_run.log` 与当前 PoC 提交人工校准，或改用 Unidbg 模拟路线。
```

---

## 六、 验证成功后的三段式报告触发

PoC 通过所有验证后，调用 `seep_gen_security_report` 自动生成结构化交付报告：

```python
# Agent 内部调用
seep_gen_security_report(
    task_name="项目X_CWE602_验证",
    vuln_title="客户端本地鉴权旁路 (CWE-602)",
    cwe_id="CWE-602",
    severity="HIGH",
    affected_component="LicenseManager.checkPremium()",
    root_cause="受限功能完全由本地布尔标志位控制，服务端无二次校验",
    poc_summary="Frida Hook 拦截 checkPremium() 返回值，强制返回 true，断网状态下受限功能正常解锁，确认为本地决策脆弱性。",
    remediation="将特权决策迁移至服务端，客户端仅持有短期、加密的会话票据，每次解锁必须通过服务端签名验证。"
)
```
