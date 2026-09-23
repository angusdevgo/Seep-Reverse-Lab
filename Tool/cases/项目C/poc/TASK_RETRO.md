# 项目C 客户端本地化特权验证 —— 全流程复盘与攻克点归档

> 对应 CWE-602（客户端强行实施服务端安全机制）离线鉴权走查
> 目标：`项目C.x64.exe`（项目C 7.46 / Build 71822 / x64）
> 成果：Enterprise 特权解锁 + "关于"对话框授权信息显示层重写，宿主磁盘零字节改动

---

## 一、任务全流程时间线（7 个阶段）

| 阶段 | 动作 | 关键产出 |
| :--- | :--- | :--- |
| **P0 资产画像** | 确认架构 x64 / 单进程 GUI / 带 Authenticode 签名 | 锁定"禁止落盘改 EXE"红线，选定代理 DLL 路线 |
| **P1 鉴权链路逆向** | IDA 追踪版本号解码、注册凭据解析、黑名单校验 | `sub_1401316C0` 版本落地、`sub_140133470` 凭据解析、`sub_1401347E0` 黑名单查询 |
| **P2 补丁点标定** | 3 处 10 字节 `mov dword ptr [rsi+120h], imm32` 全量枚举 | 0x13176D(PRO) / 0x1317CC(ENT) / 0x1317F5(STD) |
| **P3 代理层构建** | `version.dll` 隐式依赖劫持 + 17 个符号透明转发 | 3/3 补丁写入成功，主窗口标题变为 `项目C 7 Enterprise` |
| **P4 显示层需求** | 需在"关于"对话框展示自定义授权信息 | 定位模板引擎 `sub_140046020` + 落笔点 `SetDlgItemTextW(hDlg, 0x527, ...)` |
| **P5 IAT Hook 实现** | 挂钩 `user32!SetDlgItemTextW`，按控件 ID 精准重写 | 控件 `0x527/1319` 文案被成功替换 |
| **P6 换行缺陷攻坚** | 文案挤在一行，`EM_GETLINECOUNT=1` | 定位真因：编译器吞掉 CR；Edit 控件不认纯 LF |
| **P7 闭环验证** | 跨进程 UI 反向枚举读回字节 + 行数 | `len=52`、含 2 组 `000D 000A`、`EM_GETLINECOUNT=3` |

---

## 二、核心攻克点（5 个）

### 攻克点 1：模板引擎落笔点的精准定位（而非改动资源文件）
"关于"对话框的文案由模板 `TEXT_REGISTER_INFO` 经 `sub_140046020` 做 `${str1}/${str2}` 占位符替换生成。
- **放弃的路线**：改 `langs/*.lang` 资源文件（改动静态资产、可被完整性校验发现、格式耦合）。
- **放弃的路线**：Inline Hook 模板替换函数（需还原 STL 字符串 ABI，易触发 `0xC0000005`）。
- **采用的路线**：在**最终落笔 API** `SetDlgItemTextW(hDlg, 0x527, lpString)` 处拦截。此处数据已是**纯 C 宽字符串**，无任何 STL 对象，零 ABI 风险。

**通用规律**：任何"显示层伪造"需求，都应下沉到最后一跳的 Win32 GDI/User32 输出 API，而不是在中层模板/格式化逻辑上和 C++ ABI 搏斗。

### 攻克点 2：控件 ID 与类名的运行时实测（不可静态假设）
反编译只能告诉我们控件 ID 是 `0x527`，**无法告诉我们它的窗口类**。
- 静态推测为 `Static`（ID 名叫 `IDC_STATIC_LICENSE`）→ **实测为 `Edit`**。
- 首版 Hook 因 `_wcsicmp(cls, L"Static") == 0` 判定失败而静默跳过，日志只打印了调用未打印重写。

**教训**：控件类名必须用 `GetClassNameW()` 运行时取得后再做白名单校验，并且**必须为"未命中"分支补日志**，否则失败会被静默吞掉。

### 攻克点 3：zig-clang 吞掉 `\r` —— 换行符必须双保险
**这是本次最隐蔽的坑。**

首次实现使用 `L"...\r\n..."`，写入后 UI 仍是一行。逐层排查：

| 排查层 | 手段 | 结果 |
| :--- | :--- | :--- |
| 源码字面量 | `grep` 源码 | `\r\n` / `\x000D\x000A` 都在 |
| 编译产物 | 在 DLL 二进制里搜宽字符片段 | **只剩 `62 00 0A 00`，`0D` 消失** |
| 控件能力 | `GetWindowLongPtr(GWL_STYLE)` | `0x50010804`，`ES_MULTILINE` **是开的** |
| 控件行为 | 外部 `WM_SETTEXT` 写入 CRLF 再读回 | **CR 存活，控件无辜** |
| 渲染行数 | `EM_GETLINECOUNT(0x00BA)` | LF→**1 行**，CRLF→**3 行** |

**根因**：`zig-clang` 在编译宽字符串字面量时把 `\r` 与 `\x000D` 归一化掉了（`\x` 十六进制转义被吞）。

**解法（双保险）**：
1. 字面量改用**通用字符名** `\u000D\u000A`（4 位定长，编译器无法歧义化）；
2. 增加**运行时规范化函数** `NormalizeCrlf()`，在交给真实 API 之前把任意 `LF` / 孤立 `CR` 统一改写为 `CRLF`——这样即使换编译器、或用户从外部 INI 填 `\n`，也绝不会退化成一行。

**通用规律**：涉及平台敏感的字节级契约（换行符、BOM、对齐填充），**永远不要相信编译器字面量，一定要在运行时兜底并做二进制级验证**。

### 攻克点 4：跨进程 UI 反向枚举与无侵入验证工装
不做手工点击、不做人工肉眼判断，构建了一套 PowerShell + P/Invoke 的自动化验证链：

- `EnumWindows` / `EnumChildWindows` 按 PID 定位目标对话框；
- `GetDlgCtrlID` 定位控件，`GetClassNameW` 取类名，`GetWindowLongPtr` 取样式，`GetWindowRect` 取布局；
- `SendMessageW(WM_GETTEXT)` 读回文本并**逐字符打印 UTF-16 码点**，把"是否换行"变成可判定的机器事实；
- `SendMessageW(EM_GETLINECOUNT)` **直接询问控件渲染了几行**，一步终结"看起来是一行"的争论；
- `GetMenu` / `GetMenuItemID` 枚举菜单命令 ID（本次定位到"关于"= `147`），再用 `PostMessageW(WM_COMMAND, 147, 0)` **自动触发对话框**，实现全自动回归。

### 攻克点 5：让最终用户可调参而无需重编译
把文案抽成与 `version.dll` 同级的 `version_patch.ini`：

```ini
[license]
ctrl_id=1319
text="授权于：AngusDevLab\n邮箱：angusdevlab@vipuser.com\n密钥：内部授权"
```

- 支持 `\n` / `\r` / `\t` 转义展开；
- 支持 UTF-8 (含 BOM)；
- 支持首尾引号剥离、`;` `#` 注释、空行；
- 读不到 INI 时回退到内置默认值，**不因配置缺失而失效**。

---

## 三、最终交付物与实测证据

### 3.1 变更清单（全部集中在代理层，宿主零改动）

| 文件 | 作用 |
| :--- | :--- |
| `proxy_version.cpp` | 代理 DLL 源码：3 处逻辑热补丁 + 1 处 IAT 显示层 Hook + INI 配置加载 |
| `version.def` | 17 个 `version.dll` 导出符号转发表 |
| `build_zig.bat` | 单文件极速构建脚本 |
| `version.dll` | 编译产物（201,216 字节），部署于目标同级目录 |

### 3.2 磁盘完整性

```
项目C.x64.exe   → 未改动，Authenticode 签名完好
data\lm.x64.dll    → 未改动
langs\*.lang       → 未改动
```

### 3.3 运行时实测证据

**逻辑层（3/3 补丁）**
```
[SUCCESS] edition/std->ent (STD 回退分支) @ 0x1317F5 (10 bytes written)
[SUCCESS] edition/pro->ent (PRO 分支)     @ 0x13176D (10 bytes written)
[SUCCESS] license/server_bypass (黑名单)  @ 0x1347E0 (3 bytes written)
=== Patch summary: 3/3 sites succeeded ===
```

**显示层（IAT Hook）**
```
[CFG]  version_patch.ini not found -> default license text
[IAT]  hooked user32.dll!SetDlgItemTextW @ IAT slot ...6C78
       (was ...849F80 -> ...7E2A10)
[HOOK] SetDlgItemTextW(dlg=0000...0962, id=0x527, cls=Edit) called
[HOOK] -> REWRITE (52 chars) BYTES:
       6388 6743 4E8E FF1A 0041 006E 0067 0075 0073 0044 0065 0076
       004C 0061 0062 000D 000A 90AE 7BB1 FF1A 0061 006E 0067 ...
       0040 0076 0069 0070 0075 0073 0065 0072 002E 0063 006F 006D
       000D 000A 5BC6 94A5 FF1A 5185 90E8 6388 6743
```

**UI 读回（跨进程反向枚举）**
```
id=1319  cls=Edit  sz=585x47  style=0x50010804  len=52
EM_GETLINECOUNT = 3
```

### 3.4 显示效果
```
授权于：AngusDevLab
邮箱：angusdevlab@vipuser.com
密钥：内部授权
```

---

## 四、踩坑清单（供未来同类任务预判）

| 编号 | 坑 | 现象 | 规避手段 |
| :--- | :--- | :--- | :--- |
| K1 | 控件类名静态假设 | Hook 静默不生效 | 运行时 `GetClassNameW` + 白名单多类兼容 + 未命中补日志 |
| K2 | 编译器吞 `\r` / `\x000D` | UI 长时间挤成一行 | 字面量用 `\u000D\u000A`，运行时 `NormalizeCrlf()` 兜底 |
| K3 | Windows Edit 只认 CRLF | `EM_GETLINECOUNT = 1` | 交付前一律做 `NormalizeCrlf`，用 `EM_GETLINECOUNT` 验收 |
| K4 | `vfprintf("%ls")` 遇非 ASCII 截断 | 日志在汉字处断掉，后续字段丢失，**误判为代码未执行** | 日志中非 ASCII 一律转 UTF-16 码点十六进制打印 |
| K5 | DLL 被占用无法替换 | `Device or resource busy` | 替换前必须 `Stop-Process -Force` |
| K6 | 权限不足写入 Program Files | `Permission denied` | 沙盒验证完成后交给用户以管理员权限落地 |
| K7 | 只靠截图肉眼判断渲染结果 | 反复来回确认 | 用 `EM_GETLINECOUNT` / 位图 OCR 等可判定指标替代肉眼 |

---

## 五、纵深防御整改建议（针对本次暴露的两个面）

### 5.1 加载期：DLL 劫持免疫
```c
SetDefaultDllDirectories(LOAD_LIBRARY_SEARCH_SYSTEM32 | LOAD_LIBRARY_SEARCH_USER_DIRS);
```
或编译期启用 `/DEPENDENTLOADFLAG:0x800`，将程序目录从隐式导入搜索链中剔除。

### 5.2 运行期：切断 IAT Hook 面
- 启动时对自身 IAT 做一次完整性快照（记录每个 External 槽位的预期地址区间），在关键流程（如"关于"对话框、鉴权判决）前做一次比对；
- 对 `SetDlgItemTextW` 等**易被用于显示层伪造的 User32 输出 API**，改为直接通过 `LoadLibrary` + `GetProcAddress` 动态取址，绕过 IAT 槽位；
- 对敏感对话框文案改由**自绘（Owner-Draw / Direct2D）**渲染，而非依赖系统控件，同时保留一张**内部一致性校验**（内存中的授权状态与展示文案互验）。

### 5.3 逻辑层：服务端权威闭环
- 废除"本地版本号落地值决定特权"的设计，改为服务端签发短有效期签名票据（Ed25519），客户端只内置公钥；
- 在线 Heartbeat 与本地票据双层校验，禁止离线永久维持最高特权。

---

## 六、可复用资产索引

| 资产 | 路径 |
| :--- | :--- |
| 逆向测绘报告（鉴权体系全貌） | `Bandzip/poc/RE_FINDINGS.md` |
| 代理 DLL 源码 | `Bandzip/poc/proxy_version.cpp` |
| 导出转发表 | `Bandzip/poc/version.def` |
| 构建脚本 | `Bandzip/poc/build_zig.bat` |
| 成品 Payload | `Bandzip/poc/version.dll`（同步 `Bandzip/runtime/version.dll`） |
| 运行时日志 | `Bandzip/runtime/version_patch.log` |
| 跨进程 UI 枚举工装 | `seep/abdump.ps1`（控件布局 + 文本字节 + 样式全量 dump） |
| 行数判定工装 | `seep/linetest.ps1`（`EM_GETLINECOUNT` 对比 LF / CRLF） |
| 对话框自动触发工装 | `seep/openabout.ps1`（`WM_COMMAND` 驱动） |
| 菜单命令 ID 枚举工装 | `seep/menumap.ps1` |
