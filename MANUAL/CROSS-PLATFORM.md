# MANUAL — macOS 与 Linux 跨平台运行与战术等价映射指南 (Cross-Platform SOP)

> 本手册专门指导 **macOS (Apple Silicon M系列 / Intel x86_64)** 与 **Linux (Ubuntu / Debian / Arch / Fedora)** 用户如何原生运行 Seep Reverse Lab 工作台，并实现逆向分析战术的平滑等价映射。

---

## 一、 系统适应性与能力支持矩阵

Seep 工作台经过跨平台路径与工具抽象后，对不同操作系统具备分工清晰的顶级支持：

| 战术能力板块 | macOS (Darwin) | Linux (Ubuntu/Debian) | Windows 10/11 | 跨平台替代与支撑技术 |
|---|---|---|---|---|
| **Android 逆向 (apkseep)** | 🟢 **原生完美支持** | 🟢 **原生完美支持** | 🟢 原生支持 | JADX + Apktool (Java跨平台) + ADB + Frida |
| **Web 方法论 / JS 签名取证** | 🟢 原生支持 | 🟢 原生支持 | 🟢 原生支持 | Playwright + `js_reverse_*` + 知识库（与平台无关） |
| **Web / 流媒体取证工具链**（8 个 `seep_web_*`） | 🟡 **需 PowerShell 7** | 🟡 **需 PowerShell 7** | 🟢 原生支持 | 取证脚本为 PowerShell 实现；另需自装 ffmpeg/ffprobe |
| **Flutter / Dart AOT**（`seep_aotopsy`） | 🔴 **不支持** | 🔴 **不支持** | 🟢 原生支持 | `aotopsy.exe` 是 Windows PE 单文件；Unix 请用 apktool 解包后交给 r2/IDA |
| **跨平台二进制分析 (seep)** | 🟢 **原生支持** (系统r2) | 🟢 **原生支持** (系统r2) | 🟢 内置r2.exe | Radare2 自动探测系统 `radare2` / `rabin2` / `rasm2` |
| **IDA Pro 自动化联动** | 🟡 **需本地 Mac 版 IDA** | 🟡 **需本地 Linux 版 IDA** | 🟢 内置脚本探测 | 均通过 13337 端口 MCP 通用协议直连 |
| **Windows PE 客户端逆向** | 🟡 **交叉静态分析** | 🟡 **交叉静态分析** | 🟢 本地动态执行 | 在 Mac/Linux 下使用 R2/Ghidra 提取逻辑，或使用 Wine/虚拟机 |
| **Linux ELF / macOS Mach-O** | 🟢 **Mach-O 专属** | 🟢 **ELF 原生专属** | 🟡 交叉静态 | 支持本地无缝调试、动态 Hook 与符号导出 |

---

## 一之二、 外部能力包（Unix）

工作台的 `seep` MCP 有 38 个工具，其中一部分算力来自**仓库之外**的程序。
这些程序体积大、平台相关、版本还要和目标对齐，所以不进 git 仓库，
由独立的能力层补齐 —— 与代码更新解耦。

| 组件 | 谁在用 | Unix 是否支持 | 补全方式 |
|---|---|---|---|
| `ffmpeg` + `ffprobe` | `seep_hls_analyze`（HLS 六类根因判定） | 🟢 支持（走包管理器） | `./setup/install-capabilities.sh --only web` |
| `frida` / `objection` | `seep_android_toolbox`、动态插桩与脱壳 | 🟢 支持（独立 venv） | `./setup/install-capabilities.sh --only android` |
| `apkid` | `seep_apkid_scan`（加固/混淆器指纹） | 🟢 支持（独立 venv） | `./setup/install-capabilities.sh --only android` |
| `nuclei` / `ffuf` | `seep_web_report` 的可选漏扫环节 | 🟡 优先 brew，其余需手动 | `./setup/install-capabilities.sh --only scanners` |
| `aotopsy` | `seep_aotopsy`（Flutter AOT） | 🔴 不支持（Windows PE） | 不适用；改用 apktool + r2/IDA |

```bash
./setup/install-capabilities.sh                  # 默认：检测/安装 ffmpeg
./setup/install-capabilities.sh --only all       # 一次补齐（缺什么补什么，可重复执行）
./setup/install-capabilities.sh --check-only     # 只报表，不动磁盘
```

> **缺件不会导致 MCP 服务起不来。** 相关工具会返回明确的修复指引
> （例如 `[ERROR]: Aotopsy 未部署…`），其余工具照常工作。
> `./setup/verify.sh` 会以 `[! OPTN]`（DEGRADED）如实标出，**不会**因此判失败。

**装在哪里 / 怎么改位置**：Unix 默认 `~/.seep/android` 与 `~/.seep/web`，
可用环境变量 `SEEP_ANDROID_TOOLBOX` / `SEEP_WEB_TOOLBOX` 覆盖，
或用 `--root <路径>` 一次性改根目录（此时落在 `<路径>/android` 与 `<路径>/web`）。

---

## 二、 macOS 极速一键初始化 (Apple Silicon / Intel)

在 macOS 下，推荐使用 Homebrew 快速补齐系统级逆向套件。

### 1. 终端一行命令装齐依赖
```bash
# 1. 补齐基础逆向套件与运行库
brew install python@3.11 node radare2 openjdk@17 git

# 2. 软链接 Java (若系统未配)
sudo ln -sfn /opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk /Library/Java/JavaVirtualMachines/openjdk-17.jdk
```

### 2. 克隆与一键部署
```bash
git clone https://github.com/angusdevgo/Seep-Reverse-Lab.git
cd Seep-Reverse-Lab

# 执行跨平台自动化安装
chmod +x setup/install.sh setup/verify.sh
./setup/install.sh
```

### 3. 原生全彩自检核对
```bash
./setup/verify.sh
```
看到全部 `[√ PASS]`（可选能力会以 `[! OPTN]` 列出，不算失败）即代表工作台已就绪。

### 4. 外部工具定位核对
```bash
python Tool/mcp/tool_resolver.py --verify
```
这一步实跑每个工具，区分「文件存在」与「真的能启动」。工具装在非常规位置时，
用 `SEEP_PYTHON` / `SEEP_IDA_ROOT` / `SEEP_WEB_TOOLBOX` / `SEEP_ANDROID_TOOLBOX` 显式指定，
规则集中声明在 `setup/tool-registry.json`，与 Windows 侧完全一致。

---

## 三、 Linux 极速一键初始化 (Ubuntu / Debian / Kali)

### 1. 包管理器一键安装依赖
```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv nodejs npm radare2 openjdk-17-jdk git unzip
```

### 2. 克隆与一键部署
```bash
git clone https://github.com/angusdevgo/Seep-Reverse-Lab.git
cd Seep-Reverse-Lab

chmod +x setup/install.sh setup/verify.sh
./setup/install.sh
```

### 3. 原生全彩自检
```bash
./setup/verify.sh
```

---

## 四、 核心战术跨平台等价映射表 (Tactical Mapping)

当分析不同平台的目标时，Windows 下的常见打桩手法在 Linux / macOS 下有严格的对应技术：

### 1. 动态加载期劫持打桩 (Injection & Hooking)

| 场景 | Windows 经典战术 | Linux 等价战术 | macOS 等价战术 |
|---|---|---|---|
| **加载期函数拦截** | 代理 DLL 劫持 (`version.dll`) | `LD_PRELOAD=/path/to/patch.so` | `DYLD_INSERT_LIBRARIES=/path/to/patch.dylib` |
| **内存热补丁** | `WriteProcessMemory` + `VirtualProtect` | `process_vm_writev` 或 `mprotect` | `mach_vm_write` + `mach_vm_protect` |
| **导出表/符号替换** | IAT Hook (`SetDlgItemTextW`) | GOT/PLT Hook (`dlsym` 封装) | Dylib Interposing / Fishhook |
| **运行时插桩** | Frida Windows 模式 | Frida Linux 注入 (`frida -p`) | Frida macOS SIP 绕过 / 注入 |

### 2. 本地许可凭据存储位点 (Credential Storage)

| 目标数据类型 | Windows 常见位点 | Linux 常见位点 | macOS 常见位点 |
|---|---|---|---|
| **注册表项 / 试用期** | `HKCU\Software\...` | `~/.config/<app>/` 或 `~/.local/share/` | `~/Library/Preferences/<bundle.id>.plist` |
| **硬件绑定机器码** | SMBIOS / 硬盘序列号 / MAC | `/etc/machine-id` 或 `/sys/class/dmi/id/` | `IOPlatformExpertDevice` / `IOPlatformUUID` |
| **安全存储区** | DPAPI / Credential Manager | Secret Service API / GNOME Keyring | macOS Keychain (`security` CLI) |

---

## 五、 跨平台常见踩坑排障指南

### 1. macOS 报 `zsh: permission denied: ./setup/install.sh`
- **解决**：赋予执行权限即可：
  ```bash
  chmod +x setup/*.sh
  ```

### 2. macOS 提示 `radare2` 来自未知开发者或被 Gatekeeper 拦截
- **解决**：在终端放开隔离标记：
  ```bash
  xattr -dr com.apple.quarantine Tool/
  ```

### 3. Linux 报 `externally-managed-environment` (PEP 668)
- **根因**：Debian 12 / Ubuntu 23+ 默认禁止直接全局 `pip install`。
- **解决**：
  加上 `--break-system-packages`，或使用当前 Agent 专属虚拟环境：
  ```bash
  python3 -m pip install "mcp>=1.20,<1.29" --break-system-packages
  ```
