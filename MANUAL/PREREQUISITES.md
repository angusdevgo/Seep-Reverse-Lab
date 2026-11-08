# 前置依赖 (PREREQUISITES)

> `install.ps1` 会尽量自动装，但以下**基础运行时**需要你先准备好。

---

## 必需

| 组件 | 版本要求 | 检查命令 | 下载 |
| :--- | :--- | :--- | :--- |
| **Python** | **3.11+**（推荐 3.12/3.13） | `python --version` | https://www.python.org/downloads/ |
| **Git** | 任意 | `git --version` | https://git-scm.com/download/win |
| **PowerShell** | 5.1+（推荐 7.x） | `$PSVersionTable.PSVersion` | 系统自带 |

> **Python 安装时务必勾选 "Add Python to PATH"**。

## 建议

| 组件 | 版本 | 用途 |
| :--- | :--- | :--- |
| **Node.js** | 18+ | playwright-mcp / js-reverse-mcp |
| **7-Zip** | 任意 | 解压部分工具包 |

---

## install.ps1 会自动装的部分

| 组件 | 方式 |
| :--- | :--- |
| `mcp` Python 库 | `pip install "mcp>=1.20,<1.29"` |
| `pytest` | `pip install pytest` |
| `frida-tools` | `pip install frida-tools` |
| radare2 / jadx / apktool | 从 GitHub 下载解压到 `Tool/mcp/Tool/safe/` |
| playwright-mcp | `npm i @playwright/mcp` |
| js-reverse-mcp | 源码 + `npm install && npm run build` |
| ida-pro-mcp | `pip install ida-pro-mcp` |
| pi 扩展包（12 个） | `pi update --extensions` |

---

## 手动下载清单（脚本失败时用）

若 `install-tools.ps1` 因网络问题失败，手动下载后放到对应位置：

| 工具 | 下载地址 | 放到 |
| :--- | :--- | :--- |
| **jadx** | https://github.com/skylot/jadx/releases （`jadx-x.x.x.zip`） | `Tool/mcp/Tool/safe/jadx/` |
| **radare2** | https://github.com/radareorg/radare2/releases （Windows zip） | `Tool/mcp/Tool/safe/radare2/` |
| **apktool** | https://github.com/iBotPeaches/Apktool/releases （`apktool_x.x.x.jar`） | `Tool/mcp/Tool/safe/apktool/` |
| **playwright-mcp** | `npm i -g @playwright/mcp` | 全局即可 |
| **ida-pro-mcp** | https://github.com/mrexodia/ida-pro-mcp | `Tool/mcp/Tool/safe/ida-pro-mcp/` |

### apktool 的 `.bat` 封装（手动装时需要）

在 `Tool/mcp/Tool/safe/apktool/` 下新建 `apktool.bat`：

```bat
@echo off
if "%JAVA_HOME%"=="" (set JAVA=java) else (set JAVA="%JAVA_HOME%\bin\java.exe")
%JAVA% -jar -Duser.language=en "%~dp0apktool.jar" %*
```

---

## 网络问题排查

| 现象 | 处理 |
| :--- | :--- |
| GitHub 下载超时 | 脚本会自动回退镜像 `ghproxy.net` / `gh-proxy.com` |
| 全部镜像都失败 | 用上面的手动清单，或配置代理后重跑 `install-tools.ps1` |
| `pip` 装不上 | 加国内源：`pip install -i https://pypi.tuna.tsinghua.edu.cn/simple <包名>` |
| `npm` 装不上 | 换源：`npm config set registry https://registry.npmmirror.com` |

---

## 工具装在了别处怎么办（SEEP_* 环境变量）

工作台不假设你的工具装在哪个盘。解析链是：

```
环境变量  →  ~/.seep/tools.json 缓存  →  仓库自带  →  系统 PATH  →  常见安装位
```

前三层基本能覆盖绝大多数情况（jadx / apktool / radare2 / playwright-mcp / js-reverse-mcp
都在仓库里，相对路径定位，任何机器一致）。如果你的外部工具装在非常规位置，用环境变量显式指定：

| 环境变量 | 指向 | 影响 |
|---|---|---|
| `SEEP_PYTHON` | 能 `import mcp` 的 python.exe | seep MCP 服务运行时 |
| `SEEP_IDA_ROOT` | IDA Pro 安装目录（含 ida.exe） | `ida` MCP 服务 |
| `SEEP_WEB_TOOLBOX` | ffmpeg 工具箱根目录 | `seep_hls_analyze` 等 8 个 Web 工具 |
| `SEEP_ANDROID_TOOLBOX` | frida 工具箱根目录 | `seep_android_toolbox` / `seep_apkid_scan` |
| `SEEP_AGENT_DIR` | agent 配置目录（默认 `~/.pi/agent`） | 安装目标 |

Windows 持久化（当前用户，重开终端生效）：

```powershell
[Environment]::SetEnvironmentVariable('SEEP_IDA_ROOT','E:\Rev\IDA','User')
```

Linux / macOS：写进 `~/.bashrc` / `~/.zshrc` 即可。

### 怎么确认「到底找到没、能不能跑」

```powershell
# Windows
powershell -File setup\resolve-tools.ps1 -Verify

# 全平台（纯标准库）
python Tool/mcp/tool_resolver.py --verify
```

输出四种状态：

| 状态 | 含义 | 要不要管 |
|---|---|---|
| `READY` | 找到且实跑返回成功 | 不用 |
| `DEGRADED` | 找到了但跑不起来（缺依赖/版本不符） | 要看 `└─` 后面的原因 |
| `OPTIONAL` | 没找到，属于可选能力 | 不影响主链路 |
| `MISSING` | 没找到，属于核心能力 | 必须修 |

规则全部在 `setup/tool-registry.json`，想加一个新工具只改那个文件，不用改代码。

---

## 装完自检

```powershell
cd Desktop\Seep\setup
powershell -ExecutionPolicy Bypass -File .\verify.ps1
```

期望输出 `READY`（或列出待手工项）。
