# 项目B — 现代多进程混合客户端架构与跨版本热补丁演进

> 案例类型：Windows PE (x64) · 客户端授权流审计 (CWE-602) · 多进程拓扑 · 跨版本攻防演进  
> 目标组件：`项目BNxMain.exe` (UI 主程序) / `项目BNxService.exe` (后台守护) / `项目BRemoteService.exe` (云控服务) / `项目BNxUpdater.exe` (自动更新)  
> 版本谱系：v12.0 早期方案 (`2ead96f7...` / `b229f56e...`) → v6.8.1 最新架构 (`f1f507b9...` / 全量 52 点位)

---

## 案例定位与架构演进

本项目完整复盘了一个拥有“**前台 UI + 核心守护 Service + 远程推流 RemoteService + 独立升级 Updater**”的复杂多进程桌面客户端，从早期的多 DLL 转发脆弱打桩，到最新版实现**单文件 `winhttp.dll` 原生裸汇编桩 (Naked Jmp Thunks) 免重命名透明劫持 + 自动更新自毁阻断**的完整演进全过程。

```
【v12.0 初代方案】
  sentry.dll + version.dll 双 DLL 代理
  • 依赖改名 sentry_orig.dll 与外部转发表 (.def)
  • 广告闸门粗暴短路函数入口 (导致 Qt member_remove_ad_ok 信号丢失)
  • Service 侧依赖脆弱的 CC 空洞跳板 (33 c0 -> eb 21)
  • 无法阻断后台 项目BNxUpdater.exe 静默拉取 CDN 补丁覆盖
            │
            ▼ 厂商重编译与架构重构 (v6.8.1, 体积与节区大规模位移)
【v6.8.1 现代演进方案】
  全量 52 处微创点位标定 + 单文件 winhttp.dll 原生劫持
  • 广告决策闸门升级：NOP 掉 0x12ada3 判定跳转，100% 触发信号发射管线
  • Service 闭环：is_valid_infos 门控置真 + v1/member/local 端点降级，终结回写闪退
  • 远程云控彻底阻断：短路 isCurrentSessionRemoteSession() + 阻断推流双进程
  • 极致单文件落位：利用 winhttp.dll 覆盖全部 4 个主程序，原生裸汇编桩动态桥接
  • 升级自毁防御：Updater 启动瞬间安全触发 ExitProcess(0)，永久阻断版本覆盖
```

---

## 核心技法与攻防演进

| 维度 | v12.0 早期方案 | v6.8.1 演进方案 | 攻防机制与底层突破 |
|---|---|---|---|
| **广告剥离闸门 (Ad-Gate)** | `sub_14012A640` 入口写 `mov eax, 1; ret` | `sub_14012B960` 的非会员分支跳转（`0x12ada3`）6×`NOP` | **改法关键升级**：旧方案短路整个分发函数导致 Qt 信号 `member_remove_ad_ok` 无法发射；新方案仅 NOP 掉条件跳转（`0f 84 ...` -> `90...`），**100% 触发 Qt 信号系统正常发射通知**，彻底根除开屏广告与侧边栏。 |
| **试用营销流阻断 (Promo-Flow)** | `0xce9989` 处的 `jle` 跳转 | `0xcef5df` 处 `jle` 改无条件 `jmp +0xee; nop` | 强制阻断试用提示与充值引导弹窗流程。 |
| **网络响应反序列化** | 分散于旧版 account/user 函数 | `0xd1907a`–`0xd196c6` 区间 6 个连续 call | 截获服务端回包，将提取字段的 call 改为立即数赋值：到期时间写死 `0xF485E67F` (2099-12-31)、会员状态 1 (VIP)、设备数 5。 |
| **Service 防回写闭环** | 依赖 CC 空洞做远跳转跳板 (`33 c0` -> `eb 21`) | 覆盖 `parse_a/b` + `serialize` + 2 处 `is_valid_infos` + 端点本地化 | **淘汰脆弱跳板**：改用 `is_valid_infos` 置真 (`b0 01 90...` / `b1 01 90...`) 作为默认会员兜底，配合 `v1/member/trial` 原地改 `v1/member/local`，实现数据闭环，彻底解决 VIP 闪退回退死穴。 |
| **远程云控与推流** | 仅阻断 Healthd / Backend 启动函数入口 | 阻断启动入口 + 引入 RTTI 符号 `isCurrentSessionRemoteSession()` | 在 `0x17d9b0` 处短路 `GetSystemMetrics(SM_REMOTESESSION)` 判定，防止远程会话误激活并彻底关停后台推流。 |
| **代理劫持形态** | `sentry.dll` + `version.dll` 双文件转发 | **`winhttp.dll` 单文件全量原生 64 位裸桩劫持** | 发现四大主程序全部静态导入 `winhttp.dll`，无需重命名任何原版文件，92 项系统 API 原生裸汇编桥接，即插即用。 |
| **版本更新截断** | 无（容易被 CDN 静默更新冲刷补丁） | **Updater 握手瞬间安全自毁 (`ExitProcess(0)`)** | 利用 `winhttp.dll` 被 Updater 自动加载的契机，检测到宿主即刻退出进程，终结静默更新。 |

---

## 目录结构

```
项目B/
├── README.md                                      ← 本文件（项目B 整体架构与演进总览）
├── 项目B-12.0_nx_main_manual_patch_points.txt      ← v12.0 早期版本 53 点十六进制速查
├── 项目B-6.8.1_nx_main_manual_patch_points.txt     ← v6.8.1 最新版本 52 点全量十六进制速查
├── Analysis_Summary.md                            ← v12.0 早期分析报告
├── Proxy_DLL_Development_Summary.md               ← v12.0 早期双 DLL 代理报告
├── localize/                                      ← v12.0 历史归档与工程
│   ├── config/nx_main_pure.json                   ← 纯净配置模板
│   ├── scripts/                                   ← 部署与还原脚本
│   └── src/                                       ← sentry_proxy.c / version_proxy.c 早期源码
│
└── v6.8.1/                                        ← v6.8.1 完整工程与交付归档
    ├── 项目B-6.8.1_nx_main_manual_patch_points.txt ← 52 处十六进制手动修改点位表
    ├── docs/
    │   ├── v6.8.1_analysis_summary.md             ← 完整安全审计与逆向分析报告
    │   ├── v6.8.1_verification_checklist.md       ← 五场景（启动/登录/刷新/登出/重启）验证清单
    │   └── v6.8.1_patch_points_all.csv            ← 52 点位完整元数据表（CSV）
    ├── src/
    │   ├── winhttp_proxy.rs                       ← ⭐ 推荐：单文件全量原生 64 位裸桩代理源码
    │   ├── sentry_proxy.rs                        ← 双 DLL 备选：sentry 代理源码
    │   └── version_proxy.rs                       ← 双 DLL 备选：version 代理源码
    ├── tools/
    │   ├── build.ps1                              ← 代理 DLL 自动化编译脚本
    │   ├── Deploy-ProxyDll.ps1                    ← 自动化安全部署脚本
    │   └── Restore-ProxyDll.ps1                   ← 自动化安全还原脚本
    └── dist/                                      ← 编译就绪的原生 x64 代理二进制
        ├── winhttp.dll                            ← ⭐ 单文件即插即用代理（850 KB）
        ├── sentry.dll                             ← 双文件方案 sentry（258 KB）
        └── version.dll                            ← 双文件方案 version（242 KB）
```

---

## 关键技术发现与陷阱复盘

1. **跨模块非均匀平移律**：
   - 厂商重编译后，同一编译单元内的函数保持严格平移（如账号缓存通道 A/B 保持 `+0xcf00`，相邻字段相对间距 `+0x101/+0xf1/+0x1f0` 100% 吻合）；
   - 但跨编译单元的平移量各不相同（UI 层 `+0x9530`、网络层 `+0xadc0`、广告层 `+0x1320`），必须分单元锚定。
2. **信号分发 vs 闸门短路的语义陷阱**：
   - 在复杂的事件驱动架构中，如果把上游信号分发函数直接在入口处 `ret`，表面上看跳过了判定，实际上也导致下游响应逻辑断链；
   - 正确解法为**下沉至分支条件跳转处执行 NOP 旁路**，确保通知信号完整发射。
3. **多进程持久化回写死穴**：
   - 纯改前端 UI 无法抵抗后端常驻守护的数据覆写。必须将 Service 守护进程的解析、序列化、与数据有效性门控（`is_valid_infos`）三者同时收敛，才能实现断网与重启后特权不退。
4. **单 DLL 裸汇编桥接新范式**：
   - 传统的 DLL 劫持高度依赖目标目录现成的第三方库或通过 `.def` 静态转发。
   - 通过在 Rust 中使用 `#[unsafe(naked)]` 和 `naked_asm!`，直接将 92 个 WinHTTP API 用 64 位汇编动态跳转（`mov rax, [rip + slot]; jmp rax`）桥接到系统 `C:\Windows\System32\winhttp.dll`，实现了“零改名、免 _orig.dll、单文件即插即用”的极客体验。

---

## 关联知识库笔记

| 笔记路径 | 关联技术 |
|---|---|
| `pe-reverse/02-analysis/03-proxy-dll-hijacking` | Windows 动态链接库搜索劫持与原生汇编裸桩桥接 |
| `pe-reverse/03-patching/02-inline-hooking` | 内存热补丁与无损控制流改写 |
| `frameworks/cwe-602-client-enforcement` | CWE-602 客户端强判服务端特权脆弱性走查 |
