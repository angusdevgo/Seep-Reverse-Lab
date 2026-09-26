# 项目B 模拟器逆向分析与本地化纯净加固报告

## 1. 目标资产与环境基线
- **目标可执行文件**：`<本地路径>
- **文件指纹**：SHA-256 `<实测哈希>`
- **数字签名**：<厂商> (Hangzhou) Network Co., Ltd.（有效 Authenticode 签名）
- **分析工作区**：`<本地路径>

---

## 2. 逆向分析关键成果 (IDA Pro MCP)

### 2.1 会员状态判定与广告拦截链路
通过 IDA Pro MCP 反编译与符号流追踪，精确定位了以下核心判定点：
1. **`sub_140144310` (VIP/会员特权虚表判定)**：
   - 虚表偏移调用：`(*(void (__fastcall **)(__int64))(*(_QWORD *)v38 + 40LL))(v38)`
   - 用于判定当前本地登录用户或设备标识是否具备免广告与高级多开权益。
2. **`sub_14012A640` (广告剥离逻辑)**：
   - 会员特权检查通过后，向 UI 层发送 `member_remove_ad_ok` 信号，从而彻底抑制启动图广告与侧边推荐栏。
3. **`sub_140A60130` & `sub_140A7B270` (本地配置读写与同步)**：
   - 处理 `<本地路径> 的读写。
   - `member_status.last_info.device_member_status` 为核心字段（`"1"` 代表已激活免广告设备特权）。

### 2.2 云端恶意/动态注入通道审计
- **CEF / JSBridge 桥接**：通过 `CallBridge.invoke` 动态执行云端脚本（包括 `getCloudPhoneConfig`, `openCloudPhoneWebView` 等云手机推广页面）。
- **外部更新进程**：`项目BNxUpdater.exe` 会在后台静默请求<厂商> CDN 接口并下发补丁模块与热更新包。
- **崩溃与行为上报**：`项目BNxCrashReporter.exe` 与 `sentry.dll` 定期收集设备信息并向远程地址推送日志。

---

## 3. 本地化加固与无损防护方案

为确保**原始 <厂商> 数字签名 100% 保持有效**，本方案采用**配置阻断与组件免疫**策略：

1. **纯净本地配置模板 (`localize/config/nx_main_pure.json`)**：
   - 永久锁定 `device_member_status = "1"`。
   - 禁用云手机及远程引导弹窗 (`cloud_phone.guide_need_shown = "false"`, `项目B_remote.guide_need_shown = "false"`)。
   - 清空埋点上报时间戳与日志策略。
2. **免疫加固工具 (`localize/artifacts/项目BImmuneTool.exe`)**：
   - C# 源码位于 `localize/src/项目BImmuneTool.cs`，使用系统内置 .NET 编译器生成。
   - 支持 `--restore` 一键无损还原。
3. **PowerShell 自动化部署脚本**：
   - `localize/scripts/Apply-LocalPurePatch.ps1`：一键加固。
   - `localize/scripts/Restore-Original.ps1`：一键还原。

---

## 4. 交付产物清单

| 产物路径 | 说明 |
| :--- | :--- |
| `项目B/module_inventory.csv` | 模块依赖与导入导出清单 |
| `项目B/module_signatures.csv` | 核心可执行文件与 DLL 签名校验结果 |
| `项目B/pe_sections.csv` | PE 节区段分析（DEP/ASLR/CFG 等保护属性） |
| `项目B/target_strings.csv` | 关键 API、URL 与云端控制信令特征字符串 |
| `项目B/localize/config/nx_main_pure.json` | 纯净去广告与特权激活配置模板 |
| `项目B/localize/src/项目BImmuneTool.cs` | 本地免疫与守护工具 C# 源码 |
| `项目B/localize/artifacts/项目BImmuneTool.exe` | 编译生成的加固可执行工具 |
| `项目B/localize/scripts/Apply-LocalPurePatch.ps1` | 一键防御与纯净化脚本 |
| `项目B/localize/scripts/Restore-Original.ps1` | 一键还原初始状态脚本 |
