<p align="center">
  <img src="app_icon.png" alt="项目D Pro Tool Logo" width="128" height="128">
</p>

<h1 align="center">项目D Pro Tool</h1>

<p align="center">
  <strong>现代化、全功能 项目D 原生 C# / WPF 激活与状态维护套件</strong>
</p>

<p align="center">
  <a href="https://github.com/angusdevgo/IDM_Pro_Tool/stargazers"><img src="https://img.shields.io/github/stars/angusdevgo/IDM_Pro_Tool?style=for-the-badge&logo=github&color=blue" alt="GitHub Stars"></a>
  <a href="https://github.com/angusdevgo/IDM_Pro_Tool/releases"><img src="https://img.shields.io/github/v/release/angusdevgo/IDM_Pro_Tool?style=for-the-badge&logo=github&color=brightgreen" alt="Latest Release"></a>
  <a href="https://github.com/angusdevgo/IDM_Pro_Tool/blob/main/LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg?style=for-the-badge" alt="License"></a>
  <img src="https://img.shields.io/badge/Platform-Windows-0078D6?style=for-the-badge&logo=windows" alt="Windows Platform">
  <img src="https://img.shields.io/badge/.NET%20Framework-4.x%20(Native)-purple?style=for-the-badge&logo=dotnet" alt=".NET Framework 4.x">
  <img src="https://img.shields.io/badge/Architecture-x64-orange?style=for-the-badge" alt="Architecture x64">
</p>

<p align="center">
  <a href="#-项目特色">项目特色</a> •
  <a href="#-功能全景">功能全景</a> •
  <a href="#-核心实现原理">核心实现原理</a> •
  <a href="#-快速开始">快速开始</a> •
  <a href="#-命令行模式">命令行模式</a> •
  <a href="#-验证版本与指纹">验证版本与指纹</a> •
  <a href="#-构建指南">构建指南</a> •
  <a href="#-免责声明">免责声明</a>
</p>

---

## 🌟 项目特色

- 🚀 **零外部依赖，系统原生直驱**  
  无需安装任何 .NET SDK、Visual Studio 或繁重依赖，仅使用 Windows 系统自带的 `csc.exe` 即可毫秒级编译，产物仅 200 KB 左右。
- 🎨 **纯代码构建的精美 WPF 界面**  
  零 XAML 文件，全代码手工构建高精度矢量界面，集成 Windows DWM 沉浸式暗黑标题栏，原生支持高分屏（High DPI）自适应渲染。
- 🛡️ **严格的字节级安全防护机制**  
  打补丁前严格比对目标机器上的 `Expected` 原始机器码，版本或指纹不符自动中断并安全回滚，杜绝改坏 `项目D.exe`。
- 💾 **无损原子级安全备份**  
  首次修补时自动建立 `项目D.exe.BAK` 原始母版备份，仅当备份不存在时创建，确保回滚点始终为官方最纯净原版。
- ⚡ **多维度激活机制集成**  
  集成「底层二进制修补」、「Windows ACL 永久冻结试用」与「个性化授权登记」三大主流策略，满足不同场景下的使用与测试需求。

---

## 📋 功能全景

### 1. 核心授权模式 (Core Modes)

| 模式 | 运行机制 | 适用场景 |
| :--- | :--- | :--- |
| 🔥 **模式一：极速深度解锁** | 修补 `项目D.exe` 底层 18 处 / 31 字节指令，剥离数字签名，并写入终身授权登记信息。 | 追求彻底离线激活、解除所有限制的用户。 |
| ❄️ **模式二：永久冻结试用期** | 通过 Windows ACL 精确锁定注册表 CLSID 键与时间戳，固定锁定 30 天试用；不修改任何二进制。 | 需要保持原版哈希、支持官方在线静默升级的用户。 |
| 💎 **模式三：个性化授权登记** | 自定义登记姓名与邮箱（支持一键生成随机身份），自动写入系统注册表并联动底层解锁。 | 需要自定义个人专属软件授权展示界面的用户。 |
| 🔄 **模式四：全量清理出厂重置** | 清理系统内 CLSID 试用标记、黑名单特征项及注册表残留，重置为刚安装时的纯净状态。 | 解决弹窗异常、状态混乱或准备重装测试。 |
| ♻️ **一键还原官方原版** | 一键无缝从 `项目D.exe.BAK` 恢复原版主程序，并抹除注册项，还原为未注册评估状态。 | 快速回滚至初始状态。 |

### 2. 高级安全与策略盾牌 (Security & Shields)

- **🛡️ Hosts 验证盾牌**：智能向系统 Hosts 文件添加/移除 `tonec.com`、`registeridm.com` 等 8 组关键验证服务器的 `127.0.0.1` 回环映射，从网络层截断黑名单检测与序列号遥测。
- **⚙️ 官方更新策略控制**：一键切换 `CheckUpdtVM` 策略键，禁止烦人的更新弹窗，或按需重新放行。
- **🧰 注册表与路径百宝箱**：
  - **📍 手动定位 项目D 路径**：完美支持非系统盘（D盘、E盘等）或便携式 项目D 安装路径，支持文件选择对话框一键定位、多盘符智能轮询探测与永久记忆
  - 一键直达 项目D 程序根目录
  - 一键唤醒并自动跳转至注册表项 `HKEY_CURRENT_USER\Software\DownloadManager`
  - 一键将当前所有 项目D 注册表配置完整导出至桌面备忘（`IDM_Reg_Backup.reg`）
- **⚡ 进程控制**：支持一键安全终止、唤醒或重启 项目D 主程序。

---

## 🔬 核心实现原理

```
[原始 项目D.exe] ──> [哈希/字节校验] ──> [备份 项目D.exe.BAK]
                             │
                             ├──> 1. 精准修补 18 处 / 31 字节机器指令
                             ├──> 2. 剥离 PE 证书目录 + 截断尾部 10,608 字节签名
                             ├──> 3. 重算并修复 PE Checksum 校验和
                             └──> 4. 抹除 Serial 伪键，写入干净的授权信息
```

### 1. 拒绝假序列号弹窗的科学逻辑
项目D 会对注册表中的 `Serial` 键值执行严苛的非对称公钥校验，伪造任何假序列号都会触发弹窗提示「项目D 是使用假冒序列号注册的」。  
**正确的激活解法**：
1. **删除** `Serial` 键值；
2. 清理 `scansk`、`tvfrdt`、`radxcnt`、`ptrk_scdt`、`LastCheckQU`、`scTime`、`NextCheck`、`BList`、`md5pks` 等特征遥测键；
3. 仅写入 `FName` / `LName` / `Email`。

### 2. PE 签名剥离与校验和校正
修改二进制指令后，官方的 Authenticode 数字签名自然失效，会导致 Windows 驱动或杀毒软件报警签名损坏。  
本工具直接解析 PE 文件头：
- 清除 `IMAGE_DIRECTORY_ENTRY_SECURITY` 的 `VirtualAddress` 与 `Size`；
- 移除物理追加在文件尾部的 10,608 字节签名证书块（文件由 6,199,664 截断为 6,189,056 字节）；
- 使用微软标准算法重新计算 PE Checksum，确保二进制结构规范合法。

---

## 🚀 快速开始

### 方式一：直接运行成品

1. 从 [Releases 页面](https://github.com/angusdevgo/IDM_Pro_Tool/releases) 下载最新版本的压缩包；
2. 解压后确保 `app_icon.png` 与 `IDM_Pro_Tool.exe` 位于同一文件夹；
3. 右键选择 **以管理员身份运行** `IDM_Pro_Tool.exe`；
4. 在图形界面中选择您需要的功能并点击执行。

### 方式二：源码编译

只需机器拥有 Windows 原生环境（Win10 / Win11 自带 .NET 4.x），克隆仓库后双击 `build.bat`：

```powershell
# 1. 克隆本仓库
git clone https://github.com/angusdevgo/IDM_Pro_Tool.git
cd IDM_Pro_Tool

# 2. 运行构建脚本
.\build.bat
```

> **构建提示**：`build.bat` 内部通过 `%WINDIR%\Microsoft.NET\Framework64\v4.0.30319\csc.exe` 进行本地编译，耗时仅约 1~2 秒。

---

## 💻 命令行模式 (CLI Support)

工具支持无界面静默运行，非常便于集成到自动化运维、装机维护脚本或 CI/CD 流水线中：

```powershell
# 执行模式一：极速底层解锁
IDM_Pro_Tool.exe -patch

# 执行模式三：自定义身份登记
IDM_Pro_Tool.exe -register "VIP_User" "vip@domain.com"

# 一键还原为官方原版
IDM_Pro_Tool.exe -restore

# 手动指定 项目D 安装路径（针对非 C 盘或自定义安装目录）
IDM_Pro_Tool.exe -setpath "D:\Software\项目D"

# 查看命令行帮助
IDM_Pro_Tool.exe -help
```

---

## 📂 项目结构

```text
IDM_Pro_Tool/
├── src/
│   ├── Program.cs          # 核心代码（单文件 ~3000 行，集成 WPF 矢量 UI 与所有核心引擎）
│   ├── app.ico             # 包含多尺寸编码（16~256px）的应用程序原生图标
│   ├── app_icon.png        # 256x256 高清运行时矢量展示图
│   └── app.manifest        # Windows UAC 管理员提权与 DPI 感知清单
├── build.bat               # 原生批处理快速构建脚本（自动完成编译与资源归档）
├── IDM_Pro_Tool.exe        # 编译生成的目标 x64 GUI 可执行程序
├── app_icon.png            # 运行时窗口读取图标
├── LICENSE                 # MIT 开源许可证
└── README.md               # 详尽的项目说明文档
```

---

## 🔍 验证版本与指纹

本工具针对以下官方基准版本经过完整测试与哈希对齐：

| 校验项 | 基准原版 (Original) | 修补剥离后 (Patched) |
| :--- | :--- | :--- |
| **目标文件** | `项目D.exe` (<目标版本>.10.2) | `项目D.exe` |
| **文件大小** | 6,199,664 字节 | 6,189,056 字节 |
| **SHA-256** | `03CC62E9...D16D607C` | `E0C308B1...D166A72183` |

---

## ⚠️ 免责声明 (Disclaimer)

1. 本项目所提供的所有源码与可执行程序，**仅供逆向工程、Windows 内部机制、PE 文件结构以及 WPF 编程等技术学习与安全研究之用**。
2. 请在下载测试后的 24 小时内自行删除。严禁将本项目及其产物用于任何商业用途或非法侵权行为。
3. 如果您长期使用 项目D (项目D)，请前往 [官方正版网站](https://www.internetdownloadmanager.com/) 购买正版软件授权，支持优秀的软件开发者。
4. 使用本工具产生的任何软件冲突或不可预知后果，由使用者自行承担，与本项目作者无关。

---

## 📄 开源许可证

本项目基于 [MIT License](LICENSE) 协议开源。欢迎提交 Issue 或 Pull Request 完善支持！
 
## 🤝 社区与支持
- **LINUX DO 社区**: [https://linux.do](https://linux.do)
