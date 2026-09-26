# 项目A · v2 —— 授权激活机制白盒审计（版本演进：28.30 → 28.40）

> 本目录是 `Tool/cases/项目A/` 的**版本演进归档（v2）**。
> v1 已完成第三方破解件 `version.dll` 的载荷解构、鉴权函数位点测绘（`0x8E6D83` / `0x8E75ED`）与《软件安全防护与加固设计规范》。
> v2 面向**新版本 28.40.0100** 重新测绘授权模型，并发现一项 **v1 未覆盖的更高危缺陷**。

---

## 1. 本轮新增（v2 Delta）

| # | 新增成果 | 价值 |
| :-- | :--- | :--- |
| **1** | ★ **激活码校验仅为 4 字符前缀匹配**（`xy01`…`xy05`） | 无需 DLL / 调试器 / 内存篡改，**仅改配置文件**即被宿主自身判定为 Lifetime License |
| **2** | 新版本 28.40 授权模型完整测绘（全局变量、版本覆盖判定、消费点） | 授权状态变量全部落在可写 `.data`，无写保护、无使用前重算 |
| **3** | **版本自适应自研劫持 DLL**（28.30 + 28.40 双版本） | 不依赖第三方破解件，源码可复现、可演进 |
| **4** | 完整偏移映射表（28.30 ↔ 28.40 对照） | 后续版本迁移可直接沿用方法论 |
| **5** | 动态验证工装（内存读写 PoC / 静态区差分 / PrintWindow 取证 / 标题探针） | 形成可复用的"授权状态取证"工具链 |
| **6** | 破解件版本适配性缺陷结论 | 原破解件偏移仅对 28.30 有效，28.40 上补丁点错位并触发 `0xC0000374` 堆损坏 |

---

## 2. 漏洞结论

**存在"跳过激活码直接使用许可证功能"漏洞（CWE-602）。**

* 授权判定**完全依赖进程内可写全局变量**：`license_type` / `ver_flag` / 许可证名与码的 WideString 全局；
* **零网络 API**（导入表仅 7 个本地 DLL）→ 无服务端权威、无在线回执；
* 目标 EXE **未做 Authenticode 签名** → 文件级/内存级补丁均无阻碍；
* 校验链对 `Code` **只做 4 字符前缀比较**，无签名 / 校验和 / HMAC；
* 伪造的 `xy01-…` 码 + 状态 `5` 被完全接受 → 状态变量与许可证原文**无一致性校验**。

---

## 3. 关键偏移速查表

| 名称 | 28.40.0100 | 28.30.2600 | 说明 |
| :--- | :--- | :--- | :--- |
| `license_type` | `0x22FD724` | `0x22E4D5C` | `0`=试用；`1..5` = `xy01..xy05` 代次；`5`=Lifetime |
| `ver_flag`（版本覆盖） | `0x230170C` | `0x22E8D44` | `1`=覆盖本版本；`2`=许可证不覆盖；`0`=强制跳过 |
| 许可证名 WideString 全局 | `0x2235A88` | `0x221CEF8` | 明文保存 |
| 许可证码 WideString 全局 #1 | `0x2281C70` | `0x22694A0` | 明文保存 |
| 许可证码 WideString 全局 #2 | `0x21FDDE0` | `0x21E52F0` | 明文保存 |
| `OLEAUT32!SysAllocString` IAT 槽 | `0x2675408` | `0x265E408` | 伪造字符串写入跳板 |
| 版本覆盖预检 word | `0x23ACDEA` | `0x22F434A` | 覆盖判定分支入口 |
| 授权校验函数（前缀比较链） | `0x66A600` | `0x66A600` | 参数 `(Name, Code)` |
| 版本覆盖判定块 | `0x670D0D` | `0x66FC95` | 破解件补丁点 |
| 许可证前缀字面量池 | `0x21B3A44` | `0x21B3A44` | `xy01..xy05` |
| 许可证类型文案池 | `0x2283B9C` | `0x226B39C` | Lifetime / Standard / Rookie |

---

## 4. 复现（三种路径）

```powershell
cd <工作区>\project\项目A

# 路径 A：自研劫持 DLL（28.40 / 28.30 双版本）
copy dist\version.dll <安装目录>\
python tools\poc_license.py --exe "<安装目录>\<项目A>.exe" --mode read --wait 15
# 期望：license_type=5 + 许可证名/码 = 伪造值

# 路径 B：纯配置文件伪造（无需 DLL，最致命）
#   编辑 <配置目录>\<项目A>.ini 的 [Register] 段：
#   Name=poc-user
#   Code=xy05-Lifetime-License-Pro-poc-user
#   dc=0
#   启动后宿主自身即把 license_type 置为 5

# 路径 C：第三方破解件对照（仅 28.30）
copy lab\version.dll.hold lab\v2830\version.dll
python tools\poc_license.py --exe lab\v2830\<项目A>.exe --version 28.30 --mode read --wait 15
```

详细手动验证步骤见 `dist/手动验证指南.md`；完整审计报告见 `docs/授权旁路漏洞分析报告.md`。

---

## 5. 已知残留现象（不影响漏洞成立）

标题栏 `### 30-Day Trial Version - Day N ###` 标签由宿主在启动早期计算并**缓存**，
属"强校验分支结论"的 UI 呈现层；改写授权状态变量（含 v1 破解件所用的 word 全局）并强制刷新标题后该标签仍在。
**授权状态变量本身已被成功伪造**（内存实证为准），第三方破解件在 28.30 上亦通过**函数重定向**（`0x8E6D83` / `0x8E75ED` → `SysAllocString`）翻转了同一结论。
彻底翻转标题栏需进一步 hook 许可证访问器函数 —— 列为 v3 待办。

---

## 6. 交付物

| 路径 | 说明 |
| :--- | :--- |
| `docs/授权旁路漏洞分析报告.md` | 完整审计报告（含载荷字节、IOC、偏移表、修复建议） |
| `dist/version.dll` | 自研版本自适应劫持 DLL（Rust，导出全部 17 个 version.dll 接口） |
| `dist/手动验证指南.md` | 手动验证步骤（三种路径 + 已知现象说明） |
| `src/version_dll_poc/lib.rs` | DLL 源码（可 `rustc --crate-type cdylib` 重编译） |
| `tools/poc_license.py` | 授权状态读取/写入 PoC（支持 28.30 / 28.40） |
| `tools/linear_dis.py` | capstone 线性反汇编（RVA → 函数序言回溯） |
| `tools/ida_rpc.py` | IDA Pro MCP JSON-RPC 直连客户端 |
| `tools/dump_diff.py` | 进程静态区差分（定位授权状态变量） |
| `tools/verify_dll.ps1` / `run_case.ps1` / `shot_windows.ps1` | 动态取证工装（内存 + 窗口 PrintWindow） |

---

*归档：小π · seep 工作台*
