# 项目D Toolkit Pro Native 逆向分析报告：功能界面与实现原理

## 1. 软件架构与技术栈概览

- **程序架构**: 纯托管 C# / WPF 桌面应用程序（.NET Framework 4.0）
- **UI 渲染**: WPF 矢量图形系统 + Windows 11 DWM 特性（暗黑模式 `DWMWA_USE_IMMERSIVE_DARK_MODE` + 窗口圆角 `DWMWA_WINDOW_CORNER_PREFERENCE`）
- **设计风格**: 现代 Obsidian 深色卡片式 UI，左侧边栏（系统信息+快捷控制）+ 顶部 3 个功能标签页 + 底部日志监控

---

## 2. 界面功能与模块拆解

### 2.1 左侧边栏 (Sidebar)
1. **系统状态仪表盘 (Live Status Dashboard)**
   - `lblStatInstall`: 检测 项目D 是否已安装（检查默认路径及注册表）。
   - `lblStatVer`: 获取 项目D 当前内核版本（如 v6.4x）。
   - `lblStatAuth`: 监控当前授权登记状态（已登记用户/未登记）。
   - `lblStatProc`: 监控后台 `项目D.exe` 进程状态（运行中/未运行）。
2. **快捷进程控制 (Quick Process Actions)**
   - `刷新全部状态` (`RefreshAllStatus`): 重新扫描并更新看板数据。
   - `强制终止 项目D 进程` (`KillIDM`): 安全关闭所有 `项目D.exe` 实例。
   - `启动 / 重启 项目D`: 快速拉起 项目D 客户端。
   - `一键还原官方原版` (`RestoreOriginal`): 自动还原 `项目D.exe.BAK`。
   - `管理员权限指示`: 实时显示 UAC Admin 权限运行状态。

### 2.2 标签页 1：核心授权模式 (Core Activation Modes)
- **模式一：永久激活补丁 (ExecutePatch)**
  - 基于 AOB 特征码扫描，直接在底层机器码层级切断 11 处校验与看门狗线程，自动备份原版为 `项目D.exe.BAK`。
- **模式二：一键冻结重置试用 (ExecuteTrialFreeze)**
  - 不修改二进制文件，通过修改 Windows Classes CLSID 试用标记与权限锁定，使试用期永久锁定在 30 天。
- **模式三：个性化授权登记 (ExecuteRegister)**
  - 支持自定义登记姓名 (`txtAuthName`)、登记邮箱 (`txtAuthEmail`) 及一键随机生成合法校验格式的序列号 (`GenerateSerial`)，写入注册表。
- **模式四：全量清理出厂重置 (ExecuteReset)**
  - 彻底清理 项目D 注册表配置、黑名单标记（BList, md5pks, itb_r 等）及 CLSID 隐藏试用键值，彻底消除假序列号弹窗。

### 2.3 标签页 2：高级安全与更新策略 (Advanced Security)
1. **自动更新拦截策略**
   - `一键禁用 项目D 后台更新检测` (`ToggleUpdateCheck(true)`): 修改注册表 `CheckUpdtVM = 0`。
   - `恢复 项目D 官方自动更新` (`ToggleUpdateCheck(false)`): 恢复 `CheckUpdtVM = 1`。
2. **Hosts 官方验证服务器阻断**
   - `一键屏蔽 Hosts 验证服务器` (`ToggleHostsBlock(true)`): 写入 127.0.0.1 映射到系统 hosts。
   - `移除 Hosts 阻断规则` (`ToggleHostsBlock(false)`): 清理 hosts 规则。
3. **系统路径与注册表工具**
   - `备份并导出 项目D 当前注册表配置`
   - `打开 Windows 注册表编辑器` (定位到 `HKCU\Software\DownloadManager`)
   - `打开 项目D 本地安装目录` (Explorer 直达)

### 2.4 标签页 3：实时输出控制台 (Live Log Console)
- 实时打印操作流、底层补丁命中地址、备份还原结果以及异常诊断信息。

---

## 3. 核心功能实现原理

### 3.1 模式一：11 组 AOB 特征码补丁原理 (`NativeBinaryPatcher`)

补丁引擎内置了 11 条精确规则，直接对 `项目D.exe` 机器码进行特征搜索与字节替换：

| 规则名称 | 搜索特征 (Search AOB) | 替换特征 (Replace AOB) | 逆向原理解析 |
|---------|---------------------|----------------------|------------|
| **1. 解除授权分支检测** | `00 51 FF 15 04 40 69 00 85 C0 0F 85 1B 01 00 00 C6` | `... 33 C0 0F 85 ...` | 将 `test eax, eax` 替换为 `xor eax, eax`，强制让函数判定授权分支通过 |
| **2. 锁定试用期最大值** | `DC 9C 77 00 F7 D8 1B C0 83 E0 0F 83 C0 0F A3 ...` | `... B8 FF FF FF 7F 90 A3 ...` | 强制将天数变量赋值为 `0x7FFFFFFF`（`mov eax, 0x7FFFFFFF` + `nop`） |
| **3. 屏蔽假序列号警告弹窗 A** | `10 E8 AA 03 0E 00 84 C0 74 2A ...` | `... EB 2A ...` | 将条件跳转 `jz` 改为无条件跳转 `jmp`，绕过弹窗逻辑 |
| **4. 阻断自检守护线程 A** | `EC 00 00 00 C3 CC CC CC 6A FF 68 3B 84 66 ...` | `... C3 FF 68 3B ...` | 在守护线程入口直接插入 `ret` (`0xC3`)，彻底废除后台校验线程 |
| **5. 阻断自检守护线程 B** | `01 00 00 C3 CC CC CC CC 6A FF 68 78 84 66 ...` | `... C3 FF 68 78 ...` | 同样在线程入口直接 `ret` (`0xC3`) 立即返回 |
| **6. 阻断自检守护线程 C** | `CC CC CC CC CC CC CC CC 6A FF 68 CB 8C 66 ...` | `... C3 FF 68 CB ...` | 线程入口首字节打补丁 `0xC3` |
| **7. 阻断自检守护线程 D** | `CC CC CC CC CC CC CC CC 6A FF 68 9C 8D 66 ...` | `... C3 FF 68 9C ...` | 线程入口首字节打补丁 `0xC3` |
| **8. 切断外部看门狗关联** | `C4 1C 10 00 00 C3 CC CC 6A FF 68 9C 8D 66 ...` | `... C3 FF 68 9C ...` | 将 Hook 回调函数首字节置为 `ret` (`0xC3`) |
| **9. 屏蔽假序列号警告弹窗 B** | `00 E8 14 D2 03 00 84 C0 74 2A ...` | `... EB 2A ...` | 同样将条件弹窗跳转强制改为 `jmp` |
| **10. 阻断过期强退逻辑** | `C9 75 F9 2B C2 83 F8 02 0F 85 D2 01 00 00 ...` | `... 90 E9 D2 01 00 00 ...` | 将条件跳转替换为 `nop` + `jmp`，跳过过期终止进程逻辑 |
| **11. 修正试用天数限制常量** | `01 00 00 00 01 00 00 00 1E 00 00 00 38 83 ...` | `... FF FF FF 7F 38 83 ...` | 将限制常量从 `0x1E` (30天) 改为 `0x7FFFFFFF` (极大值) |

---

### 3.2 模式三：序列号生成算法 (`GenerateSerial`)

- **字符集**: `ABCDEFGHJKLMNPQRSTUVWXYZ23456789`（32个去除了易混淆字符 0, 1, I, O 的字符集合）
- **格式**: `XXXXX-XXXXX-XXXXX-XXXXX`（4 组，每组 5 位字符，共 20 位）
- **写入注册表位置**: `HKCU\Software\DownloadManager`
  - `FName`: 登记名（如 `Angus`）
  - `LName`: 留空或空格
  - `Email`: 登记邮箱（如 `angus.vip@tonec.com`）
  - `Serial`: 生成的 20 位序列号
  - `CheckUpdtVM`: 设为 `0`
  - `LstCheck`: 设为 `0`

---

### 3.3 模式四：出厂重置与注册表清理原理 (`ExecuteReset`)

分两阶段清理：
1. **第一阶段：清理 `HKCU\Software\DownloadManager`**
   - 彻底删除 16 个敏感鉴权与黑名单键值：
     `FName`, `LName`, `Email`, `Serial`, `scansk`, `tvfrdt`, `radxcnt`, `LstCheck`, `ptrk_scdt`, `LastCheckQU`, `CheckUpdtVM`, `scTime`, `NextCheck`, `BList`, `md5pks`, `itb_r`, `ncl_r`。
2. **第二阶段：清理 `Software\Classes\CLSID` 与 `WOW6432Node\CLSID`**
   - 遍历系统所有 CLSID GUID 项（正则匹配 `^\{[A-F0-9]{8}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{4}-[A-F0-9]{12}\}$`）。
   - 扫描 项目D 在 CLSID 中注入的试用计数器与时间戳（纯数字键名 `^\d+$` 及特定 base64/混淆试用键），将这些项递归删除。

---

### 3.4 网络防护：Hosts 拦截原理 (`ToggleHostsBlock`)

向系统 `C:\Windows\System32\drivers\etc\hosts` 文件追加如下专用阻断规则：

```hosts
# >>> 项目D Toolkit Block >>>
127.0.0.1 tonec.com
127.0.0.1 www.tonec.com
127.0.0.1 registeridm.com
127.0.0.1 www.registeridm.com
127.0.0.1 secure.internetdownloadmanager.com
127.0.0.1 mirror.internetdownloadmanager.com
127.0.0.1 mirror2.internetdownloadmanager.com
127.0.0.1 mirror3.internetdownloadmanager.com
# <<< 项目D Toolkit Block <<<
```
