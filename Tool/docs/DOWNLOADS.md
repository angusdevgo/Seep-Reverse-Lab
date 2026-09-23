# 下载清单 (DOWNLOADS)

> ⚠️ **本包已内置全部工具（≈880 MB）—— 正常情况下你不需要下载任何东西。**
>
> 本文用于：
> 1. 了解内置工具**是什么、从哪来、装在哪**（便于排障与溯源）
> 2. 内置工具损坏/缺失时，用 `setup\repair-tools.ps1` 重新下载
> 3. 唯一需你自行准备的软件：**IDA Pro**（商业授权，见 `MANUAL/IDA-PRO.md`）

---

## 零、内置 vs 需自备

| 类别 | 组件 | 处理方式 |
| :--- | :--- | :--- |
| ✅ **已内置** | jadx · radare2 · apktool · playwright-mcp · js-reverse-mcp · ida-pro-mcp · hook-mcp | 随包提供，解压即用 |
| 🔴 **需自备** | **IDA Pro 本体**（商业授权） | 见 `MANUAL/IDA-PRO.md` |
| 🔴 **需自填** | 模型 API 密钥 · playwright token | 由你自行配置（本包不含凭据） |
| ⚙️ **需 pip 装** | `mcp` · `pytest` · `frida-tools` | `install-python.ps1` 自动 |

---

## 一、内置工具清单（已随包提供）

| # | 组件 | 上游来源 | 本包位置 | 体积 |
| :-: | :--- | :--- | :--- | :--- |
| 1 | **jadx** | GitHub `skylot/jadx` | `Tool/mcp/Tool/safe/jadx/` | 461 MB |
| 2 | **radare2** | GitHub `radareorg/radare2` | `Tool/mcp/Tool/safe/radare2/` | 39 MB |
| 3 | **apktool** | GitHub `iBotPeaches/Apktool` | `Tool/mcp/Tool/safe/apktool/` | 24 MB |
| 4 | **playwright-mcp** | npm `@playwright/mcp` | `Tool/mcp/Tool/safe/playwright-mcp/` | 45 MB |
| 5 | **js-reverse-mcp** | npm `js-reverse-mcp` | `Tool/mcp/Tool/safe/js-reverse-mcp/` | 234 MB |
| 6 | **ida-pro-mcp** | PyPI `ida-pro-mcp` | `Tool/mcp/Tool/safe/ida-pro-mcp/` | 79 MB |
| 7 | **hook-mcp** | 自研 | `Tool/mcp/Tool/safe/hook-mcp/` | 331 KB |
| | | | **合计** | **≈ 880 MB** |

> 工具位置由 `seep_mcp_server.py` 硬编码决定：`TOOL_DIR = <脚本目录>/Tool`。
> 即 `Tool/mcp/` 旁边必须有 `Tool/` 目录。**不可搬动。**

---

## 二、需自备：IDA Pro（商业授权）

IDA Pro **不随包分发**。两种处理：

| 方案 | 操作 |
| :--- | :--- |
| **已有授权** | 跑 `setup\install-ida.ps1`（自动探测 + 装 ida-pro-mcp + 写配置） |
| **无授权** | 用免费替代：`seep_r2_*`（Radare2 八件套）+ Ghidra —— 见 `MANUAL/IDA-PRO.md` |

> **IDA 缺失不会阻塞任务** —— agent 会自动降级到 `seep_r2_*` 并标注“未使用 IDA 反编译器”。

---

## 三、需 pip 安装（`install-python.ps1` 自动）

| 包 | 版本约束 | 来源 | 用途 |
| :--- | :--- | :--- | :--- |
| **mcp** | `>=1.20,<1.29` | PyPI | **seep MCP 运行时** |
| **pytest** | 最新 | PyPI | 跑 apkseep 离线测试套件 |
| **frida-tools** | 最新 | PyPI | 动态 Hook（可选） |

**国内源回退**：失败时自动重试 `https://pypi.tuna.tsinghua.edu.cn/simple`

> ⚠️ **`mcp` 版本上限很重要**：`mcp>=1.29` 移除了 `mcp.server.fastmcp`，
> seep MCP 会启动失败。**不要手工升级到 1.29+。**

---

## 四、pi 扩展包（12 个 npm 包）

由 `install-pi.ps1` 写入 `~/.pi/agent/settings.json` 的 `packages` 字段，
然后执行 `pi update --extensions` 安装：

```
npm:pi-open-tui
npm:pi-web-access
npm:@juicesharp/rpiv-todo
npm:@narumitw/pi-btw
npm:@narumitw/pi-plan-mode
npm:@narumitw/pi-usage
npm:pi-mcp-extension
npm:@smoose/pi-themes
npm:pi-tool-display
npm:@juicesharp/rpiv-ask-user-question
npm:pi-playwright
npm:pi-goal-x
```

**目标**：`~/.pi/agent/npm/node_modules/` · 体积约 80 MB

---

### 1. jadx — Java/APK 反编译

| 项 | 值 |
| :--- | :--- |
| **上游** | https://github.com/skylot/jadx |
| **下载地址** | `https://api.github.com/repos/skylot/jadx/releases/latest` → asset `jadx-<版本>.zip` |
| **实测版本** | `jadx-1.5.6.zip` |
| **正则匹配** | `^jadx-[\d.]+\.zip$` |
| **目标** | `Tool/mcp/Tool/safe/jadx/` |
| **服务的工具** | `seep_apk_decompile` |
| **许可** | Apache-2.0 |

### 2. radare2 — 二进制逆向引擎

| 项 | 值 |
| :--- | :--- |
| **上游** | https://github.com/radareorg/radare2 |
| **下载地址** | `https://api.github.com/repos/radareorg/radare2/releases/latest` → asset `radare2-<版本>-w64.zip` |
| **实测版本** | `radare2-6.2.2-w64.zip` |
| **正则匹配** | `^radare2-.*-w64\.zip$` ⚠️ **注意是 `w64` 不是 `windows`** |
| **目标** | `Tool/mcp/Tool/safe/radare2/` |
| **服务的工具** | `seep_r2_*`（**8 个工具**） |
| **许可** | LGPL-3.0 |

> ⚠️ **易错点**：radare2 的 Windows 包名用 `w64`（如 `radare2-6.2.2-w64.zip`），
> 不是 `windows`。早期若写成 `windows.*\.zip$` 会**匹配不到任何 asset**，导致下载静默失败。

### 3. apktool — APK 解包/重打包

| 项 | 值 |
| :--- | :--- |
| **上游** | https://github.com/iBotPeaches/Apktool |
| **下载地址** | `https://api.github.com/repos/iBotPeaches/Apktool/releases/latest` → asset `apktool_<版本>.jar` |
| **实测版本** | `apktool_3.0.3.jar` |
| **正则匹配** | `^apktool_[\d.]+\.jar$` |
| **目标** | `Tool/mcp/Tool/safe/apktool/`（脚本另写 `apktool.bat`） |
| **服务的工具** | `seep_apk_unpack` |
| **许可** | Apache-2.0 |

**前置依赖**：需 JDK 17+（`apktool.bat` 会读 `JAVA_HOME`）

### 4. playwright-mcp — 浏览器自动化

| 项 | 值 |
| :--- | :--- |
| **上游** | https://github.com/microsoft/playwright-mcp（npm `@playwright/mcp`） |
| **安装** | `npm install @playwright/mcp` |
| **目标** | `Tool/mcp/Tool/safe/playwright-mcp/` |
| **备注** | 也可直接用 `npx -y @playwright/mcp@latest`（无需安装） |
| **需自填** | `PLAYWRIGHT_MCP_EXTENSION_TOKEN`（由你自行配置） |

### 5. js-reverse-mcp — JS 逆向

| 项 | 值 |
| :--- | :--- |
| **上游** | https://github.com/zhizhuodemao/js-reverse-mcp |
| **方式** | **npx 免安装**：`npx -y js-reverse-mcp` |
| **目标** | 无需下载（已在 `mcp.json.template` 中预置） |
| **可选本地安装** | `git clone` + `npm install` + `npm run build` |
| **许可** | 见上游仓库 |

> **优点**：零下载、零磁盘占用。首次调用时 npx 自动拉取。

### 6. ida-pro-mcp — IDA 桥接

| 项 | 值 |
| :--- | :--- |
| **上游** | https://github.com/mrexodia/ida-pro-mcp |
| **PyPI** | https://pypi.org/project/ida-pro-mcp/ |
| **实测版本** | **1.4.0** |
| **安装** | `pip install ida-pro-mcp` |
| **目标** | Python site-packages |
| **服务的工具** | `mcp_ida_*`（~243 个） |
| **⚠️ 前置** | **需自备 IDA Pro**（见 `MANUAL/IDA-PRO.md`） |

---

## 三、Python 依赖（3 个）

`install-python.ps1` 执行：

| 包 | 版本约束 | 来源 | 用途 |
| :--- | :--- | :--- | :--- |
| **mcp** | `>=1.20,<1.29` | PyPI | **seep MCP 运行时**（版本上限由 reverselab 约定） |
| **pytest** | 最新 | PyPI | 跑 apkseep 的离线测试套件 |
| **frida-tools** | 最新 | PyPI | 动态 Hook（可选） |

**国内源回退**：脚本失败时自动重试 `https://pypi.tuna.tsinghua.edu.cn/simple`

> ⚠️ **`mcp` 的版本上限很重要**：`mcp>=1.29` 移除了 `mcp.server.fastmcp`，
> seep MCP 会启动失败。**不要手工升级到 1.29+。**

---

## 四、pi 扩展包（12 个 npm 包）

由 `install-pi.ps1` 写入 `~/.pi/agent/settings.json` 的 `packages` 字段，
然后执行 `pi update --extensions` 安装：

```
npm:pi-open-tui
npm:pi-web-access
npm:@juicesharp/rpiv-todo
npm:@narumitw/pi-btw
npm:@narumitw/pi-plan-mode
npm:@narumitw/pi-usage
npm:pi-mcp-extension
npm:@smoose/pi-themes
npm:pi-tool-display
npm:@juicesharp/rpiv-ask-user-question
npm:pi-playwright
npm:pi-goal-x
```

**目标**：`~/.pi/agent/npm/node_modules/`

**手工安装**：
```powershell
pi update --extensions
# 或逐个装
pi install npm:pi-mcp-extension
```

---

## 五、免下载项（零磁盘占用）

| 组件 | 方式 | 说明 |
| :--- | :--- | :--- |
| **js-reverse-mcp** | `npx -y js-reverse-mcp` | 首次调用时自动拉取 |
| **playwright MCP** | `npx -y @playwright/mcp@latest` | 同上（也可本地装） |

---

## 六、镜像回退策略

`install-tools.ps1` 内置三级回退（**按顺序尝试**）：

```
1. 官方源          https://github.com/...          （直连）
2. ghproxy.net     https://ghproxy.net/https://github.com/...
3. gh-proxy.com    https://gh-proxy.com/https://github.com/...
```

**触发条件**：下载失败、超时（300s）、或文件 < 1 KB（视为无效）

**日志示例**：
```
[..] 尝试 official ...
[!!] 失败: The operation has timed out
[..] 尝试 ghproxy.net ...
[OK] 下载成功 (ghproxy.net)
```

---

## 七、手动下载清单（脚本全失败时）

| 工具 | 手动下载 | 放到 | 备注 |
| :--- | :--- | :--- | :--- |
| **jadx** | https://github.com/skylot/jadx/releases → `jadx-x.x.x.zip` | `Tool/mcp/Tool/safe/jadx/` | 解压后 `bin/jadx.bat` 应在 |
| **radare2** | https://github.com/radareorg/radare2/releases → `radare2-x.x.x-w64.zip` | `Tool/mcp/Tool/safe/radare2/` | 解压后 `bin/radare2.exe` 应在 |
| **apktool** | https://github.com/iBotPeaches/Apktool/releases → `apktool_x.x.x.jar` | `Tool/mcp/Tool/safe/apktool/apktool.jar` | 需另建 `apktool.bat` |
| **ida-pro-mcp** | `pip install ida-pro-mcp` | Python site-packages | — |
| **playwright-mcp** | `npm i @playwright/mcp` | `Tool/mcp/Tool/safe/playwright-mcp/` | 或用 npx |

### apktool 的 `.bat` 内容（手动装时需要）

```bat
@echo off
if "%JAVA_HOME%"=="" (set JAVA=java) else (set JAVA="%JAVA_HOME%\bin\java.exe")
%JAVA% -jar -Duser.language=en "%~dp0apktool.jar" %*
```

---

## 八、验证下载是否成功

```powershell
cd Desktop\Seep\setup
powershell -ExecutionPolicy Bypass -File .\verify.ps1
```

**期望存在**：

| 路径 | 期望内容 |
| :--- | :--- |
| `Tool/mcp/Tool/safe/jadx/bin/jadx.bat` | jadx 启动器 |
| `Tool/mcp/Tool/safe/radare2/bin/radare2.exe` | r2 主程序 |
| `Tool/mcp/Tool/safe/apktool/apktool.jar` | apktool jar |
| `Tool/mcp/Tool/safe/hook-mcp/templates/` | Hook 模板（本包自带） |
| `Tool/mcp/Tool/reverselab/kb/` | 289 篇知识库（本包自带） |

---

## 九、不下载什么（刻意排除）

| 项 | 原因 |
| :--- | :--- |
| **IDA Pro 本体**（1.6 GB） | 商业授权，不得分发 —— 见 `MANUAL/IDA-PRO.md` |
| **模型 API 密钥** | 隐私，由使用者自行配置 |
| **GitHub PAT / Sentry DSN** | 上游 `.env.example` 仅留空模板 |
| **Playwright token** | 需自备，由使用者自行配置 |

---

## 十、网络问题速查

| 现象 | 处理 |
| :--- | :--- |
| GitHub API 超时 | 脚本会报 `无法获取 release 信息`，改用镜像或手动下载 |
| 下载中断 | 重跑 `install-tools.ps1`（已存在的会跳过） |
| `pip` 慢 | `pip install -i https://pypi.tuna.tsinghua.edu.cn/simple <包>` |
| `npm` 慢 | `npm config set registry https://registry.npmmirror.com` |
| 全部失败 | 按 §七 手动下载，放到对应目录 |

---

## 十一、磁盘空间预估

| 阶段 | 增量 |
| :--- | :--- |
| 解压本包 | 16 MB |
| 装工具（jadx 460 + r2 39 + apktool 24 + playwright 45 + ida-pro-mcp 1） | ~570 MB |
| Python 依赖（mcp + pytest + frida-tools） | ~50 MB |
| pi 扩展包（12 个） | ~80 MB |
| **合计** | **≈ 700 MB** |

> 若只装核心链路（**跳过 jadx**）：可省 460 MB。
> 命令：`powershell -File .\install-tools.ps1 -Only radare2,apktool,ida-pro-mcp`
