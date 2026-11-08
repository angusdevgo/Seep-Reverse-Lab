# Changelog

> 本文件面向**已部署用户**，说明每次更新带来什么变化、需要注意什么。
> 更新操作见 [MANUAL/DEPLOYMENT.md — 更新指南](MANUAL/DEPLOYMENT.md#八-已有用户更新指南)。
>
> **模型选型与拒答排查**见 [MANUAL/MODEL-REFUSAL-MATRIX.md](MANUAL/MODEL-REFUSAL-MATRIX.md)（实测对照表）。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## [Unreleased]

## [1.9.2] - 2026-11-08

### 部署链路重写：把「代码更新」与「能力补齐」拆成两层

**问题**：工作台有三个层次，旧链路只覆盖第一层。

```
第 3 层  能用吗？   ← 外部依赖：ffmpeg / frida / APKiD / Aotopsy / nuclei / ffuf
                     ↑ 完全没覆盖
第 2 层  装上了吗？ ← 技能 / 脚本 / MCP 工具定义
                     ↑ 只覆盖了一半（技能走目录枚举有，脚本没同步）
第 1 层  代码新吗？ ← git pull
                     ↑ 已覆盖
```

后果就是一句话：**工具在 `tools/list` 里看得见，一调用返回「未部署」。**

### 新增 `setup/install-capabilities.ps1`：外部能力包统一入口

| 组件 | 默认安装 | 成本 |
|---|:---:|---|
| `aotopsy`（Flutter AOT 分析） | ✅ | 零网络，从 `Tool/aotopsy` 直接复制 |
| `web`（ffmpeg + ffprobe） | ✕ | 约 80 MB 下载 |
| `android`（frida / objection / APKiD） | ✕ | pip + 独立 venv |
| `scanners`（nuclei / ffuf） | ✕ | 约 40 MB 下载 |

- 纪律：**默认只装零成本件**；要下载/装包的必须显式点名，任何组件失败只警告，绝不中断部署。
- `-CheckOnly` 只报表不动盘；`-ToolboxRoot` 一次性改根目录；`-Strict` 供 CI 用。
- 组件安装器不带 `exit`，改为同进程 splatting 调用 —— 顺带修掉了 `-Only a,b` 经 `-File` 传递时
  被当成单个字符串、触发 `ValidateSet` 失败的问题。

### `install.ps1` / `update.ps1` 接入

- `install.ps1` 新增能力包步骤（`-SkipCapabilities` / `-WithWeb` / `-WithAndroid` / `-WithScanners`）。
- `update.ps1` 新增 `-WithTools`（顺带补 ffmpeg + frida + APKiD）与
  `-CheckCapabilities`（**只补能力、不动代码**，网络拉不动代码时用）；结束报告重写：
  技能数与工具数改为**动态统计**，新增能力看板，并把「必须完全重启会话」写成独立段落
  （原来混在一段提示里，容易被略过；而 MCP 工具是启动时握手的，不重开就看不到新工具）。
- `install-pi.ps1`：不再往 `mcp.json` 写裸 `"python"`，改为**探测一个真正 `import mcp` 成功**的解释器
  并写绝对路径。此前若机器上的 `python` 指向没装 `mcp` 的解释器（系统 Python 3.10 / 商店别名 /
  conda base），服务端一启动就 ImportError，而体检只表现为「MCP 没连上」，排查成本极高。

### `verify.ps1`：从「文件在不在」到「现在能不能真跑」

- 新增 `[5b] 外部能力包可用性` 小节，逐组判定 Web 取证 / Flutter AOT / Android 动态 / 加固指纹 / 扫描器。
  缺失归入 🟡 DEGRADED 而非 🔴 MISSING —— 外部程序缺失是正常状态，不该判失败。
- 新增 `Resolve-VerifyPython`：Python 相关检查统一使用**探测后可执行**的解释器。
  此前直接调 `python`，若它是商店占位别名或指向已删 venv 的 `.cmd` 垫片，
  会连带把「语法自洽」「stdio 冒烟」「规则表同步」三项误报为红 —— 一次环境问题伪装成三个功能故障。
- 隐私走查的非 git 分支补排除「安装时生成的本地配置」（`opencode.jsonc`、`cordis.generated.yml`、
  `relay-config.json`、`tool-index.*`）。这些文件含本机绝对路径属正常，且已被 `.gitignore` 排除；
  此前用 ZIP 部署（无 `.git`）的用户每次体检都会误报隐私残留。
- `install.ps1` 的环境检测改为校验退出码与版本串。此前只看 `Get-Command python` 有没有结果，
  垫片失效时会打印 `[OK] Python 可用: 系统找不到指定的路径`。

### 验证记录（双路实跑）

**路径 A · 全新安装**（干净目录 + 沙盒 HOME，等价首次 clone）：

```
解压离线依赖包 → 技能 11 个（含 webseep）→ seep MCP 解释器: D:\Tool\IDA Pro\python311\python.exe
→ 补齐外部能力包（auto）→ [OK] 全部外部能力已就绪
→ 体检报告 核心检查通过 61 项 → 🎉 READY
```

**路径 B · 老用户升级**（克隆到 v1.8.2 `e9b6c9e`，跑的仍是**旧版** `update.ps1`）：

```
版本已更新: v1.8.2  ->  v1.9.2
技能 11 个（含 webseep）· MCP 工具定义 38 个 · 新增 setup/install-capabilities.ps1
补齐外部能力包（auto）→ [OK] 全部外部能力已就绪
体检报告 核心检查通过 61 项 → 🎉 READY
[!!] 警告 0 条 · git stash 0 条 · 工作区 0 项改动
```

**路径 B 二次执行**（此时已是新版 `update.ps1`，验幂等与新报告格式）：

```
[..] 版本未变化（v1.9.2）—— 将执行一次幂等重同步（补齐可能缺失的组件）
本次同步: 逆向技能 11 个 · MCP 工具定义 38 个
外部能力看板: ffmpeg / ffprobe / frida / objection / apkid / aotopsy / adb 全部 [READY]
体检报告 核心检查通过 61 项 → 🎉 READY
```

> 双路验证过程中又发现并修掉三个部署缺陷：
> ① `install-python.ps1` 用裸 `python`，垫片失效时 pip 全线失败，且**把错误文本当成功打印**；
> ② 验证 pytest 时 `| Select-Object -First 1` 提前终止管线，装好的包被判「不可用」；
> ③ `generate-configs.ps1` 每次重写内容相同的 `.mcp.json`，mtime 变化让 `git status` 报「已修改」，
> 于是 `update.ps1` 每次都弹一次「本地改动已 stash」——用户以为自己的文件被动过。

`clean-format.py` 零问题；中继单测 84/84。

### 已部署用户注意

```powershell
powershell -ExecutionPolicy Bypass -File .\setup\update.ps1 -WithTools
```

更新后**完全关闭并重开 Agent 会话**。想只补能力不动代码，用 `-CheckCapabilities`。


## [1.9.1] - 2026-11-08

### 修复：`seep_pe_*` 等工具在 stdio 模式下无限挂起（issue #13 / PR #14，致谢 @MrUncleXiang）

`_run_cmd()` 用 `subprocess.run()` 派生外部进程时没有重定向 `stdin`，子进程因此继承了
MCP 服务端自己的 stdin —— 那是一条由客户端（Claude Code / DSH / OpenCode / Pi）持有、
会话结束前永远不会关闭的 JSON-RPC 管道。

后果：在 stdio 传输下，**Python 子进程**在解释器启动阶段就卡住，脚本业务代码一行都没执行，
工具表现为「永久挂起」直到客户端超时。r2 / jadx / apktool 这些原生 exe 不受影响 ——
这正好解释了为什么当时只有 `seep_pe_*` 四条路径出问题（它们经由 `_run_pe_script()` → `_run_cmd()`
启动 Python 子进程）。

**本机实测复现**（`mcp` 1.30.0 / Python 3.11）：

```
修复前：  seep_pe_triage -> TIMEOUT (>20s)   seep_pe_aob_scan -> TIMEOUT (>20s)
修复后：  seep_pe_triage -> OK (5983 chars)  seep_pe_aob_scan -> OK (679 chars)
```

- **`Tool/mcp/seep_mcp_server.py`**：两处 `subprocess` 调用点补 `stdin=subprocess.DEVNULL`
  （`_run_cmd()` 与 `_run_web_script()`）。工作台 38 个工具的外部进程调用全部收敛在这两个函数，
  改一处即全覆盖，对不需要交互输入的工具零副作用。
- **新增 `Tool/mcp/test_stdio_smoke.py`**（303 行，纯标准库）：两层回归。
  - 静态层 `--quick`：AST 遍历，要求每个 `subprocess.run/Popen/call/check_*` 调用点显式给出
    `stdin=`，缺失即报出具体行号。零依赖、毫秒级。
  - 端到端层：真的以 stdio 拉起服务端，走 `initialize` → `tools/list` → `tools/call`
    （含一次真实 `seep_pe_triage`）。这是唯一能复现原始故障的层级。
- **`setup/verify.ps1`**：新增检查项「stdio 子进程不继承 stdin」（跑 `--quick`），
  核心检查项 54 → **55**。
- **`setup/install-python.ps1`**：补 `PIP_BREAK_SYSTEM_PACKAGES=1`。uv 托管的解释器与多数
  Linux 发行版自带 Python 都带 PEP 668 `externally-managed` 标记，裸 `pip install` 会直接
  以 `error: externally-managed-environment` 退出，导致 `mcp` 装不上、MCP 服务起不来。

### 为什么原有体检发现不了

`verify.ps1` 对 `seep_mcp_server.py` 只做 `ast.parse` 语法自洽检查 —— 漏写 `stdin=` 语法完全合法；
手动在普通 shell 里跑同一个脚本也只要 0.09 s。只有**以 stdio 服务方式真实调用**才暴露。
所以这次补的不是"再检查一遍语法"，而是一条端到端调用链 + 一个静态不变量。

### 已部署用户注意

修复只改服务端脚本，**无需重装依赖**：`git pull` 后完全重启 Agent 会话即可。
若仍遇到挂起，运行 `python Tool/mcp/test_stdio_smoke.py` 可自证当前副本是否已带修复。


## [1.9.0] - 2026-11-08

### 新增能力域：Web / 流媒体取证

- **第 11 个技能 `webseep`**（`Tool/skill/webseep/`，17 文件）——Web 源与接口取证方法论：
  HLS 六类根因判定（防盗链 / key 鉴权 / AES-128 / SAMPLE-AES / DRM / 源失效）、
  CMS 家族与采集接口指纹、TVBox / CatVod spider 三入口、头变体矩阵重放。
  素材来源已在 `Tool/skill/webseep/PROVENANCE.md` 与 `Tool/docs/PROVENANCE.md` 完整标注。
- **8 个 Web MCP 工具**：`seep_web_pipeline`（一键总入口）、`seep_web_gate`（阶段门，缺前置产物直接 BLOCK）、
  `seep_cms_fingerprint`、`seep_hls_analyze`、`seep_http_replay`、`seep_spider_extract`、
  `seep_web_report`、`seep_web_toolbox`。
- **9 个 PowerShell 取证脚本**（`Tool/scripts/web/`）+ 自测夹具（`_test/`，含本地 CMS / 门槛服务器与假 HLS 样本）。
- 判决纪律写进提示词：`EXT-X-KEY` 存在 ≠ 加密；key 非 16 字节 ≠ 解密成功；
  命中 Widevine / FairPlay / PlayReady / pssh → 立即 STOP，不探测许可证服务器。
- 硬约束写进脚本：`cms-fingerprint.ps1` 只发 GET、≤20 路径、400ms 间隔，不爆破、不提交表单、不尝试登录。

### 新增能力域：Android 外部工具箱

- **3 个 MCP 工具**：`seep_android_toolbox`（就绪检查）、`seep_apkid_scan`（加固 / 混淆器指纹）、
  `seep_aotopsy`（Flutter / Dart AOT `libapp.so` 静态分析与符号还原）。
- **6 个 PowerShell 脚本**（`Tool/scripts/android/`）：幂等安装 Frida / objection / frida-dexdump / APKiD / Aotopsy
  并生成 `.cmd` 垫片，另有 recon / dexdump / objection / apkid / aotopsy 五个作战脚本。
- **Aotopsy 安装载荷**（`Tool/aotopsy/`，11 MB，MIT）随仓库分发，`install-android-toolbox.ps1` 直接复制，无需构建。
- 公共库：`Tool/scripts/lib/WebToolbox.ps1`、`Tool/scripts/lib/AndroidToolbox.ps1`。

### MCP 工具数 27 → 38

与原 PE 四件套（`seep_pe_triage` / `_aob_scan` / `_diff` / `_patch`）合并，工具分组扩为**八大类**。
`seep_status()` 现在同时报告 `pe_engine_exe_reverse`、`android_toolbox`、`web_toolbox` 三块就绪度。

### 体检改动态断言（修复「体检假红 / 假绿」）

- `setup/verify.ps1` 不再写死「27 个原生工具定义」，改为从 `seep_mcp_server.py` 源码统计 `def seep_*`。
- 技能数改为遍历 `Tool/skill/` 目录统计，不再写死「10 大组件」。
- 新增 `webseep` 完整性检查（SKILL.md + ≥3 refs + 模板）。

### 文档

- `README.md` / `README.zh.md`：工具矩阵新增「Android 工具箱」「Web / 流媒体」两组，计数 27 → 38。
- `Tool/docs/MCP-SETUP.md`：工具清单刷新为 38，补充两段外部依赖说明与一键补全命令。
- 新增 `Tool/docs/WEB-TOOLBOX.md`、`Tool/docs/ANDROID-TOOLBOX.md`、`Tool/docs/SKILL-ROUTING.md`。
- `Tool/docs/TOOLKIT_GUIDE.md` 升级为六章版（新增 Android 工具箱、Web 取证工具箱两章）。
- `Tool/docs/PROVENANCE.md`：Skill 溯源扩至 11 个，新增 web/android 脚本溯源与第三方素材归属。
- `Tool/prompts/SYSTEM.md`：新增「Web / 流媒体取证路由」章节（三步入场 + 判决纪律 + 工具映射）。
- `Tool/skill/softseep/SKILL.md`：MCP 路由表补 `seep_web_*` / `seep_hls_*` / `seep_cms_*`。

### 已部署用户注意

1. 更新后**必须完全重启 Agent 会话**（MCP 工具在启动时握手，`/reload` 不够），否则看不到新增的 11 个工具。
2. 新增 11 个工具里有 4 个依赖外部工具箱：`seep_hls_analyze` 需 ffmpeg/ffprobe，
   `seep_apkid_scan` 需 APKiD，`seep_aotopsy` 需 Aotopsy，`seep_android_toolbox` 只做就绪检查。
   未安装时这些工具返回明确的修复指引，**不会**导致整个 MCP 服务不可用。
   补全命令见 `Tool/docs/WEB-TOOLBOX.md` 与 `Tool/docs/ANDROID-TOOLBOX.md`。
3. `Tool/aotopsy/`（11 MB）随仓库分发，`git pull` 会一并拉取，无需另行下载。


### 案例库：项目D 合并原地演进至 v1.6.1（build 16 支持）

- `Tool/cases/项目D/docs/reverse-engineering.md` 新增 §10：build 16 代码重排迁移（.text +245 KB、段内位移非均匀、capstone 局部定向反汇编、操作数补丁识别）
- `Tool/cases/项目D/docs/algorithm.md` 位点表扩为**六版本**矩阵，新增 §3.3（签名长度上限决策、IAT 地址常量导致左扩展收缩）
- `Tool/cases/项目D/README.md` 新增 v1.6.1 演进章节（回归断言 98 → 118）
- `Tool/cases/项目D/tools/09_multiversion_extend.py` 新增**一体化扩展流水线**（JSON 配置驱动，三级定位自动降级）
- KB 笔记 `10-multiversion-signature-narrowing.md` 新增陷阱三（签名长度上限）与陷阱四（验证方法本身会骗你）

## [1.8.2] - 2026-10-24

### 修复：作战模式隔离不彻底（真实泄漏，不是理论问题）

用户需求：**只有输入 `lab：` 才触发工作台，日常使用不应被逆向纪律污染。**

上一版把开关改成了会话级内存，但只做了一半 —— 全局 `AGENTS.md` 仍然**每个会话无条件加载**，
里面写着思维重定向、反退缩十项、G-Auth 授权门、Zero-Waste Recon 提效路由。
结果是：哪怕你没输入 `lab：`，写个普通脚本也在"反退缩十项硬约束"之下运行。

### 变更

- **`AGENTS.md` 瘦身（9.5 KB → 6.4 KB，去人格化）**：只保留
  ① 作战模式开关说明 ② **非 lab 会话禁令** ③ 部署/更新/卸载/校验命令。
  所有逆向纪律移出，改由 `seep-system.md` 在 `lab：` 后注入。
- **新增非 lab 禁令（硬规则）**：未输入 `lab：` 的会话中，禁止加载任何逆向技能、
  禁止调用 `seep_*` MCP 工具、禁止主动推销逆向能力、禁止套用反退缩话术。
- **`SYSTEM.md` 协议改写**：实验环境开关从"磁盘标志文件"改为**会话级内存**；
  新增 G-Auth 授权门与配套资源路径（从 AGENTS.md 迁入）。
- **中继开关解耦（`relay.py`）**：改写开关改为独立的 `~/.pi/agent/compliance-relay.flag`，
  不再依赖 `lab-mode.flag`。旧文件仍识别（向后兼容）。
  原因：lab 改为内存状态后磁盘上不再有人写该文件，继续以它为门会让中继**永久关闭**。
- 文档同步：`README.md` / `README.zh.md` / `DEPLOYMENT-CHECKLIST.md` / `DEPLOYMENT.md` /
  `COMPLIANCE-RELAY.md` / `PROVENANCE.md` / 中继 `README.md` 全部改口径。

### 验证记录（observed）

用 esbuild 打包扩展后，以 mock ExtensionAPI 驱动全部 5 个钩子，8 项断言全过：

| # | 场景 | 结果 |
|---|---|---|
| 1 | 新会话 + 普通输入"帮我写个 Python 脚本" | `action: continue`（原样放行） |
| 2 | 未激活时 `before_agent_start` | `undefined`（**不注入**任何提示词） |
| 3 | 输入 `lab：` | 激活，返回"已开启（仅限当前会话）" |
| 4 | 激活后 `before_agent_start` | 注入 8589 字符，含 `G-Auth` 与 `反退缩` |
| 5 | 激活后敏感词输入 | 转译为"白盒鉴权脆弱性测试 / 受限权限功能模块"+ 合规前缀 |
| 6 | 输入 `退出实验` | 立即关闭 |
| 7 | 退出后 `before_agent_start` | `undefined`（注入停止） |
| 8 | 退出后普通输入 | `action: continue`（恢复纯净） |

中继单元测试：**84/84 通过**（开关改动未破坏既有行为）。
`verify.ps1`：53/53 核心检查通过。

## [1.8.1] - 2026-10-24

### 新增

- **🔌 PE 引擎统一收口进 `seep` MCP（23 → 27 工具）**：
  - `seep_pe_triage`：一次过 PE 体检（节区/熵、导入导出、TLS、资源、PDB、CLR、校验和比对、保护信号）。
  - `seep_pe_aob_scan`：AOB 特征码定位 + `unique` / `ambiguous` / `pervasive` / `no-match` 裁决，支持 `across` 跨版本命中数对比。
  - `seep_pe_diff`：归一化易变头字段（TimeDateStamp / CheckSum）后的构建差分，差异区间映射回 RVA。
  - `seep_pe_patch`：可验证等长补丁（校验和重算 + 写盘后逐字节回读），支持 `dry_run`。
  - 四个工具与 `seep_r2_*` / `seep_apk_*` 保持同一返回风格与命名规范；`seep_status` 新增 `pe_engine_exe_reverse` 组件状态。
  - 实现方式为**薄包装**：不重写引擎，只做参数校验、路径解析（兼容工作台内嵌 / 上游镜像 / 已安装技能三种布局）、输出有界截断与错误归一化。

### 安全护栏（工具层强制，不依赖模型自觉）

- `seep_pe_patch` 拒绝 `out_path == pe_path`（原地覆盖一律拒绝）。
- 非 `dry_run` 时必须显式给出 `out_path`；`at_rva` / `at_offset` / `pattern` 三选一，多给或少给都拒绝。
- `expect=` 与实际字节不符时底层脚本直接中止，**且不产生输出文件**（已验证）。
- 四个 PE 工具中只有 `seep_pe_patch` 会写盘，其余三个严格只读。

### 验证记录（observed）

- 工具注册数：**23 → 27**（`seep_pe_triage` / `seep_pe_aob_scan` / `seep_pe_diff` / `seep_pe_patch` 均已注册）。
- `seep_status()` 正确报告 `pe_engine_exe_reverse.status = Ready` 并给出解析到的 scripts 路径。
- 功能实测（合成 PE fixture）：
  - `seep_pe_triage` → 完整报告（校验和 match、5 个节区、保护信号 4 条）；
  - `seep_pe_aob_scan` → 植入两处 → 正确裁决 `ambiguous`，并列出 `0x410` / `0x424` 两个命中；
  - `seep_pe_diff` → 自身对自身 → 只报告被归一化的易变字段，无内容差异；
  - `seep_pe_patch` → 原地覆盖/缺 out/双定位器/无定位器四种误用全部被拒；`dry_run` 正确预览；实际落盘后 `checksum recomputed` + `every patched byte re-read from the written file`；`expect` 不匹配时中止且**未创建输出文件**。

## [1.8.0] - 2026-10-24

### 新增

- **🪟 Windows PE 深水区执行层 `exe-reverse`（第 10 个技能）**：
  - 纳入 `https://codeberg.org/dabao1955/exe-reverse`（MIT，上游 SHA `c6ef186`），**上游文件零修改**，仅加 `ATTRIBUTION` 注释块与本地 `LOCAL-NOTES.md`，因此上游同步始终是纯拷贝。
  - 41 篇带门禁的参考文档 + **16 个零依赖 Python 引擎**（纯标准库）：
    `peutil`（RVA↔偏移双向、导入/导出/资源/TLS/重定位/PDB、微软算法校验和、逐节熵）、
    `pe_triage`、`pepatch`（等长补丁 + 歧义守卫 + 校验和重算 + **写盘后逐字节回读**）、
    `aob_scan`（unique / ambiguous / pervasive / no-match 裁决）、`pe_diff`、`hwprobe`、`capabilities`、
    `plan`、`preflight`、`fold`、`trace_reduce`（可选 SMT 证明）、`scan_leaks`、`make_fixture_pe`、
    `dart_snapshot_strings`、`gate_probe.js`。
  - 覆盖：PE 结构、补丁纪律、AOB 签名、完整性校验、保护壳、虚拟化/控制流平坦化、算法还原、
    符号执行、.NET 托管程序集、Unity IL2CPP、打包 Python、Flutter Dart AOT、内核驱动、
    硬件追踪与 Hypervisor 观测。
- **🚦 三层门禁命名空间消歧（`gate-crosswalk.md`）**：
  - 发现 `softseep` / `apkseep` / `exe-reverse` 各自使用 `G1–G4` 但**同名不同义**（同一个 `G2` 在三处分别指“写入判死归因 / 环境真实性 / 主机真实性”），已建立 `AUTH-G0…G4` / `APK-G1…G4` / `EXE-G1…G5` 前缀约定与执行顺序图，并将“裸 G2 视为歧义”写入 SKILL.md 硬规则。
- **🌉 Windows 深水区中文桥接（`windows-deep.md`）**：
  - 中文大白话 → `exe-reverse` 参考文件的唯一映射表（补丁/壳/虚拟化/.NET/IL2CPP/Python 打包/驱动/硬件追踪/算法还原）。
  - 明确与 `windows-sop.md` 的分工：后者是**交付流水线**，前者是**机制字典**。
- **🔄 上游第 4 条声明式规则**：`setup/upstream-rules.json` 新增 `exe-reverse` → `Tool/upstream/exe-reverse`（`preserve_local: []`），Codeberg 源已通过 `git ls-remote` 可达性验证，防外溢单测 6/6 通过。

### 变更

- `softseep` 路由矩阵新增 Windows 深水区 6 类意图（补丁工程 / 保护壳·虚拟化 / 托管程序集 / 运行时捆绑 / 内核·硬件层 / 模块开发），并补充平台判型信号（`.msi` / `.node` / `GameAssembly.dll` / `python3xx.dll` / `_internal` / `pyarmor_runtime`）。
- `softseep` references 由 8 篇增至 **10 篇**；体检技能项由 9 项增至 **10 项**，`verify.ps1` / `verify.sh` 新增 `exe-reverse` 校验（SKILL.md + ≥41 refs + ≥16 scripts）。
- `README.md` / `README.zh.md` / `PROVENANCE.md` / `DEPLOYMENT-CHECKLIST.md` / `CLAUDE.md` / `AGENTS.md` / `DEPLOYMENT.md` 全面同步第 10 个技能与第 4 个上游。
- 体检新增 Windows 无 Python-in-PATH 时的**常见安装路径自愈探测**（`C:\Program Files\Python3xx`、`%LOCALAPPDATA%\Programs\Python\Python3xx`），消除“明明装了 Python 却报 MISSING”的误判。

### 验证记录（observed）

- `scripts/doctor.py`：**16/16 脚本可运行**；本机 28 项能力中 14 项 `ok`，14 项 `BLK`（缺调试器/IDA/测试签名，属宿主限制而非缺陷）。
- 端到端往返：`make_fixture_pe` → `pe_triage` → `aob_scan`（植入两处 → 正确报 `ambiguous`）→ `pepatch`（dry-run → 落盘）→ 独立复核：原文件 SHA256 不变、补丁文件校验和 `0x10bad → 0x1181` 重算正确、RVA `0x1010` 处字节确为 `90 90 90`。
- 红线取证：上游 `0 strong / 16 weak / 102 suppressed`，`RESULT=clean`；`docs/tool-acquisition.md` 明确写明 “No cracked builds, no key generators, no patched installers”；外部链接仅官方厂商文档 / GitHub / Microsoft Learn。

## [1.7.0] - 2026-10-23

### 新增

- **🚀 现代 LSPosed 与 Vector 双模架构支持 (API 101+)**：
  - 更新 `Tool/skill/apkseep/references/lsposed-and-modules.md`：
    - 详述经典 XposedBridge (API 82) 与现代 Vector / libxposed (API 100/101/102) 差异（`META-INF/xposed/java_init.list`、`io.github.libxposed.api.XposedModule`、拦截器链式 Hooker 模型、`xposedscope`）；
    - 制定第三方未知模块逆向分析 4 步 SOP（入口定位、作用域提取、混淆方法与特征指纹反查、JNI Native 挂钩剖析）；
    - 引入动态 ClassLoader 构造 Hook 方案（针对动态解密 Dex、插件化与加壳应用）；
    - 整合真机免逆向动态辅助武器库（算法助手 Algorithm Aide、SimpleHook、LSPilot）；
    - 提供三大 AI 逆向协同 Prompt 模板（入口分析、混淆还原、Native 意图解析）。
- **🛡️ KernelSU 内核级 Root 与 Systemless 深度防御与对抗**：
  - 更新 `Tool/skill/apkseep/references/kernel-and-environment-hardening.md`：
    - 引入 `preinit/preinit.conf`（SELinux 策略前阶段执行最高权限 `insmod`/`exec`/`write`）；
    - 引入 `initrc/` 系统级 RC 脚本透明注入机制；
    - 详述 Linux 内核原生 OverlayFS 机制（Whiteout `mknod c 0 0` 虚拟删除、Opaque 属性整块目录替换）；
    - 解析 BusyBox ash 独立运行环境 (`ASH_STANDALONE=1`) 与 ZygiskNext 桥接规范。
- **⚙️ 双模 LSPosed 脚手架引擎升级**：
  - 增强 `Tool/skill/apkseep/scripts/lsposed_scaffold.py`：新增 `--api {legacy, modern}` 参数与 `--with-classloader-hook` 选项，一键生成经典 API 82 或现代 libxposed Vector API 101 骨架，并支持无 Gradle 极速编译链。
- **📚 ReverseLab 攻防知识库扩展**：
  - 新增 `09-lsposed-root/01-modern-lsposed-module-analysis.md` 与 `09-lsposed-root/02-kernelsu-root-mechanisms.md`，同步更新 `kb-index.json` 索引。
- **🧠 总控判型与调度升级 (`softseep`)**：
  - `Tool/skill/softseep/SKILL.md` 新增对 LSPosed、Xposed、Vector、KernelSU、APatch、Magisk 等大白话意图的自动判型与精准路由。

- **🌐 上游定点隔离同步与防外溢体系 (Zero-Spillover Upstream Sync)**：
  - 新增 `setup/upstream-rules.json`：声明式上游规则清单，严格绑定每个上游仓库的唯一目标目录与白名单边界。
  - 新增 `setup/sync-upstream.py`（纯标准库）：物理边界硬性断言 (`realpath` 严格前缀匹配)，上游 A 仓库更新只能并入 A 目录，绝对阻断跨目录外溢；保留本地定制文档。
  - 新增 `setup/sync-upstream.ps1` / `setup/sync-upstream.sh`：本地一键定点同步脚本，支持 `-Target`、`-DryRun`、`-CheckOnly`。
  - 新增 `.github/workflows/upstream-sync.yml`：云端定时巡检工作流，发现上游新提交自动按仓库切独立分支提 PR，Diff 严格限定在专属目录内。
  - 新增 `setup/test_sync_upstream.py`：防外溢熔断与路径越界安全单元测试套件（6 项全部通过）。
- **⚡ 下游使用者极简更新体验升级**：
  - 项目根目录新增 **`update.bat`** 与 **`update.ps1`**：双击即可全自动检测代理、安全暂存修改、无损增量拉取并跑完 52 项体检。
  - 增强 `setup/update.ps1` 与 `setup/update.sh`：新增 `-Check` / `--check` 轻量版本检查，支持非阻塞版本探测。
  - 体检系统升级至 **52 项核心校验**：全面覆盖上游规则与防外溢引擎在位状态。

### 变更

- **📦 项目D 案例更新至 v1.5.0**（跨版本补丁迁移 · 五版本 AOB 特征码）
  - 版本谱系由 3 个扩展到 **5 个**（新增 build 12 / build 15），位点偏移表与特征码表全面刷新。
  - 新增 **§8「静默自动更新 + 数据段填充漂移」**：记录官方内置更新器静默覆盖已打补丁主程序导致的授权失效链，
    以及数据段填充漂移使滑动汉明距离误命中（距离仅 2、位置早 2 字节）的陷阱与修正流程。
  - `docs/algorithm.md`：五版本指纹表、五版本位点偏移对照、新增 §3.2 填充漂移专项。
  - `tools/` 流水线脚本改为**基于脚本位置自动解析路径**，去除作者本地绝对路径。
  - 回归断言由 61 项扩充至 **89 项**（五版本端到端），并断言既有版本产物哈希零变化。
- **📚 知识库新增笔记**：`pe-reverse/10-license-keygen/10-multiversion-signature-narrowing.md`
  —— 多版本特征码收窄与数据段填充漂移陷阱（含三重确认流程与零回归断言清单）。

---

## [Unreleased]

### 新增

- **🌐 项目D 案例更新至 v1.6.0**（全栈中英双语国际化架构）
  - 纯代码内嵌双语字典（零 `.resx` / 零附属程序集），保持单源码 `csc.exe` 秒级编译。
  - 首启自动探测 `CultureInfo.CurrentUICulture`，非中文系统直接呈现专业英文。
  - 侧边栏 `[ 🌐 EN / 简 ]` 胶囊按钮实现毫秒级内存热重绘（保留 Tab 状态与控制台日志）。
  - 运行日志实时翻译层（`TranslateLog`）：115+ 条模式替换，覆盖 AOB 补丁 / ACL 冻结 / 备份归档全链路。
  - 回归断言由 89 项扩充至 **98 项**（新增 9 项国际化单元测试）。
  - 文档新增「全栈中英双语国际化架构」章节，含四项关键工程决策（为何弃用 `.resx`、为何热重绘而非重建、日志为何必须走翻译层、CLI 同步国际化）。

---

## [1.6.0] — 2026-10-11

### 新增

- **🔁 中继拒答自动重试**（`Tool/scripts/compliance-relay/refusal.py`）★
  - Gemini 对「命令式要求对具体目标执行攻击性分析」的请求会**静默拦截**：
    `HTTP 200 + {"choices": [], "usage": {"completion_tokens": 377}}` ——
    模型生成了 token 但内容被丢弃，**不报错、不提示**，异常处理根本捕获不到。
  - 中继现在会检测这类拒答，**自动换一种写法重发**，对客户端完全透明。
  - 策略级联（全部**保留用户指定的目标**）：
    `original` → `S1 评审清单式` → `S2 设计评审框架` → `S3 英文评审式`
  - 实测：原句被拦（377 tokens 丢弃）→ 改写后返回 **2611~3324 字**完整回答。
  - 支持非流式（OpenAI / Anthropic / Google 原生形状）与流式 SSE 两类拒答检测。
  - 性能保障：只缓冲到「可判定」为止（SSE 8KB / JSON 4MB），超出上限即视为肯定没被拦，直接透传。
  - 可配置：`relay-config.json` 中 `refusalRetry` / `refusalRetryAttempts`（默认开、3 次）。
  - 新增 **40 项单元与集成测试**（共 84 项全绿），含「上游先拒答再放行」的端到端验证。

### 变更

- `relay.py` 响应转发改为「缓冲到可判定 → 需要时重试 → 再透传」，
  非拒答的正常长回答仍为流式透传。

---

## [1.5.0] — 2026-10-11

### 新增

- **🔍 L1 可观测性日志**（`security-audit-interceptor.ts`）
  - 动机：L1 有两类**不会报错的失效方式** —— 对 OpenAI 兼容端点乱注入会 400；
    对「名字叫 gemini 但实际走 OpenAI 格式」的链路注入则**被中转静默丢弃**。
  - 设 `PI_SAFETY_LOG=1` 后，每次判定写入 `~/.pi/agent/logs/l1-safety.log`，
    判定分为 `INJECT` / `SKIP` / **`SKIP-INEFFECTIVE`**（名字像 Gemini 但形状是 `messages`，
    注入必然无效的告警）。日志超 512KB 自动截断。
- **🧪 Gemini 安全设置验证工具**（`Tool/scripts/check-gemini-safety.py`）
  - 用同一提示词分别以「不注入 / 注入 `BLOCK_NONE`」请求 Google 原生接口，
    对比 `finishReason` 给出**可证伪的结论**：有效 / 无法区分 / 无效。
  - 纯标准库，密钥仅从 `GEMINI_API_KEY` 环境变量读取，**绝不打印、绝不落盘**。
  - 支持 `--list-models` / `--model` / `--prompt`。
- **🗑️ 一键卸载脚本**（`setup/uninstall.ps1` / `setup/uninstall.sh`）—— 回应 Issue #8
  - 原则：**只移除工作台自己装的东西，绝不碰你的数据**
  - 移除范围：工作台自带的 9 大技能、`AGENTS.md` / `SYSTEM.md`、`extensions/*.ts`、
    `mcp.json` 中的 `seep` / `js-reverse` / `playwright`、工作台加入的 12 个 packages、`lab-mode.flag`
  - **永不触碰**：`models.json` / `auth.json` / `sessions/` / `logs/`、
    你自己添加的 Skill 与 MCP 条目、`settings.json` 的其他字段
  - MCP 条目采用**外科手术式**判定：只有 `args` 确实指向工作台组件时才认为归工作台所有
  - 支持 `-DryRun` 预览、逐项 `-Keep*` 保留、`-Purge` 深度清理、`-Restore` 反向恢复
  - 卸载前自动整体备份到 `~/.pi/agent/backup-uninstall-<时间戳>/`
  - 手册：[MANUAL/DEPLOYMENT.md — 卸载与回滚](MANUAL/DEPLOYMENT.md)
- **🔁 已有用户一键更新机制**（`setup/update.ps1` / `update.sh` + `VERSION` + 本 CHANGELOG）
  - 自动 `git stash` 保护本地改动 → `git pull` → 预览变更 → 备份 → 幂等增量同步 → 校验零丢失 → 全量自检

### 修复

- **🚨 安装/更新会静默覆盖用户 `mcp.json`（严重）**
  - 根因：`$raw.StartsWith([char]0xFEFF)` 在**无 BOM** 的文件上也会返回 `TRUE`。
    .NET 默认 `StartsWith` 使用**文化敏感比较**，而 `U+FEFF`（BOM 字符）是
    「可忽略字符」，等价于空字符串，因此**任何字符串都「以它开头」**，
    随后的 `Substring(1)` 便削掉了首个 `{`，把合法 JSON 破坏成非法。
  - 后果：`install-pi.ps1` 读取失败后静默回退到空配置，
    用模板**覆盖**用户 `mcp.json`，丢失自定义 MCP 条目（如 `ida`）与真实 Playwright token。
  - 修复：`install-pi.ps1`（mcp.json + settings.json）、`install-ida.ps1`、`update.ps1`
    共 4 处改为序数/字符比较。
- **🧩 3 个技能被 Agent 静默跳过**（Issue #6，由 @xiaozhi1218 报告）
  - 根因：`safe-skills/{apk-reverse,ida-reverse,radare2}/SKILL.md` 带 UTF-8 BOM，
    而 DSH 的 frontmatter 解析要求首行**严格等于** `---`，于是整条技能被静默丢弃（9 条只发现 6 条）。
  - 修复：`setup/clean-format.py` 新增 Markdown / JSON **剥离 BOM** 规则（`.ps1` 仍保留 BOM），
    并排除 `Tool/upstream/` 以保持上游镜像字节保真；共修复 8 个文件。
  - 新增门禁：`verify.ps1` / `verify.sh` 会阻断任何带 BOM 的 `SKILL.md`，防止回归。
- **🛑 Ctrl+C 退出时 MCP 子进程打印 KeyboardInterrupt 堆栈**（Issue #7）
  - `seep_mcp_server.py` 现在捕获 `KeyboardInterrupt` / `BrokenPipeError` / `EOFError` 静默收尾，
    并为 POSIX 注册 `SIGTERM` 处理器。
- **🔌 Gemini 私有字段被注入到所有 provider（由 PR #9 @linbei0 贡献）**
  - L1 底座级解封不再无差别写入 `safetySettings` / `config`，
    改为**仅对 Google/Gemini 端点注入**；OpenAI 兼容网关不再返回 `400 UNKNOWN_FIELD`。
  - 可用环境变量 `PI_SAFETY_PAYLOAD=off|all|auto` 覆盖（默认 `auto`）。
- **🍎 macOS / Linux 自动安装 radare2（由 PR #5 @iscodeminister 贡献）**
  - `setup/install.sh` 新增引擎探测：macOS + Homebrew 自动安装，其他平台给出清晰指引；幂等且非致命。
- **🔒 隐私门禁改为只扫描 git 跟踪文件**
  - 本地已 gitignore 的生成配置不再造成误报，同时更准确地反映「实际会发布的内容」。

### 变更

- `verify.ps1` 增至 **52 项**核心检查，`verify.sh` 增至 **51 项**。

---

## [1.4.0] — 2026-09-30

### 新增

- **🌐 链路层合规转译中继**（`Tool/scripts/compliance-relay/`）
  - 本机回环中继，在请求离开本机前把口语平滑转译为合规术语
  - 覆盖三种协议：`openai-completions`（Pi Agent 主力）、`anthropic-messages`（Claude Code）、`openai-responses`（Codex）
  - 纯 Python 标准库实现，**零新增依赖**；**零落盘**（日志只记命中条数）
  - 默认关闭，需显式运行 `python relay.py`；受 `lab-mode.flag` 门控，mtime 热加载
  - 手册：[MANUAL/COMPLIANCE-RELAY.md](MANUAL/COMPLIANCE-RELAY.md)
- **🔒 脱敏与个人隐私门禁**（`verify.ps1` / `verify.sh` 第 9 节）
  - 全深度递归扫描个人路径、身份标识、私有域名、凭据
  - 生成物追踪检查（含本机路径的配置文件不得入库）
  - 脱敏基准表 D1–D6 记录于 `MANUAL/DEPLOYMENT-CHECKLIST.md`
- **🖥️ 跨平台支持**（macOS / Linux）
  - 新增 `setup/install.sh`、`setup/verify.sh` 原生 Bash 脚本
  - `seep_mcp_server.py` 自动探测系统 `radare2` / `rabin2` 与各平台 JDK 路径
  - 手册：[MANUAL/CROSS-PLATFORM.md](MANUAL/CROSS-PLATFORM.md)
- **📖 部署与校验体系**
  - `MANUAL/DEPLOYMENT.md` 全景部署手册（含 4 大 Agent 接入 SOP 与排障 FAQ）
  - `MANUAL/DEPLOYMENT-CHECKLIST.md` 官方基准核验清单（单一真值源）
  - `verify.ps1 -Detailed` 输出结构化基准校对看板
- **📦 案例库扩充至 14 个**（项目 A ~ 项目 N）
  - 新增 项目M（Java + install4j 双层鉴权）、项目N（.NET x64 + VM 混淆加固）

### 变更

- **⚙️ 安装脚本重构为幂等 + 无损模式**
  - `install-pi.ps1` 改为**增量合并** `mcp.json` / `settings.json`，不再覆盖用户自定义 MCP
  - 所有 JSON 配置统一以 **UTF-8 无 BOM** 写入，修复 Node.js `JSON.parse` 报错
  - 路径统一转为正斜杠，修复 Windows 反斜杠导致的 JSON 非法转义
- **🛡️ 安全审计扩展双加固**（`security-audit-interceptor.ts`）
  - 新增 25 项 `INJECTED_PREFIXES` 上下文守卫：Agent 自注入的环境 / AGENTS.md / 技能清单**不再被误改写**
  - 顺序 `replace` 改为**单趟最长优先匹配**：算法保证「绕过会员」优先于「绕过」，且替换产物不回扫（杜绝级联污染）
- **🔍 IDA Pro 探测强化**（`install-ida.ps1`）
  - 支持 `-IdaRoot` 参数、注册表探测、交互式输入自定义路径
  - 支持 IDA 9.x 原生 `idalib_supervisor` 模块模式
- **🔗 上游镜像归位**
  - `apk-reverse`、`open-tgtylab`、`open-reverselab` 三大开源项目完整镜像至 `Tool/upstream/`
- **⚖️ 许可证更正为 GPL-3.0**
  - 因整合了两个 GPL-3.0 上游项目，整体许可证由 MIT 更正为 **GNU GPL-3.0**

### 修复

- 修复 Windows PowerShell 5.1 下 `Set-Content -Encoding UTF8` 写入 BOM 导致 Node.js JSON 解析崩溃
- 修复 Windows 路径反斜杠未转义导致的 `Bad escaped character in JSON`
- 修复 `install-pi.ps1` 全量覆盖导致用户自定义 MCP（如 x64dbg）被抹除
- 修复 IDA 路径写死 `D:\Tool\IDA Pro`、非标准安装位置无法识别
- 修复 Bash 脚本 CRLF 换行污染导致的 `bad interpreter` 报错（13 个脚本）
- 修复 70 个 PowerShell 脚本缺失 UTF-8 BOM 导致的中文乱码与语法解析中断

### 安全

- **清理个人隐私与凭据残留**（发布前强制门禁）
  - 移除全部个人绝对路径、个人身份标识、私有中转站域名
  - 移除案例中残留的真实产品名 / 厂商域名 / **真实加密 Salt**
  - 含本机路径的生成物（`opencode.jsonc`、`cordis.generated.yml`）不再入库
  - 中继运行配置 `relay-config.json`（含访问 token）纳入 `.gitignore`

---

## [1.3.0] — 2026-09-28

### 新增

- 案例库扩充至 13 个（新增 项目L Qt5 C++、项目M Java + install4j）
- `seep_r2_xrefs` 工具：交叉引用查询，内置分页与统计摘要
- 上下文预算控制：`seep_r2_decompile` 支持 `fold`（省 ~60% Token）/ `summary`（省 ~90%）

### 变更

- `MANUAL/` 战术手册扩充至 6 份

---

## [1.2.0] — 2026-09-26

### 新增

- `MANUAL/ANTI-DEBUG.md`：反调试绕过字典与代理 DLL 框架
- `MANUAL/UNPACKING.md`：UPX / MPRESS / Themida / VMP 脱壳 SOP
- `MANUAL/POC-VALIDATION.md`：Frida 自愈循环与 PoC 沙箱验证

### 变更

- `verify.ps1` 升级为 7 大维度体检

---

## [1.1.0] — 2026-09-25

### 新增

- `check.bat` / `check.ps1` 根目录一键体检入口
- `setup/verify.ps1 -Detailed` 结构化基准校对看板
- 部署完备性校验体系（7 大维度）

---

## [1.0.0] — 2026-09-24

### 新增

- 首个公开版本
- 9 大逆向 Skill（`softseep` 总控 + `apkseep` + `ida-reverse` + `safe-skills` 5 组）
- 自研 `seep` MCP 服务（23 项原生工具）
- 289+ 篇攻防知识库
- 9 个脱敏工业案例范式（项目 A ~ 项目 I）
- Lab Mode 磁盘状态机与三层防拒体系

---

## 更新类型说明

| 变更类型 | 含义 | 用户需要做什么 |
|---|---|---|
| **新增** | 新功能、新工具、新案例 | 跑一次更新脚本即可 |
| **变更** | 行为或接口调整 | 建议读一下具体条目 |
| **修复** | 缺陷修复 | 跑一次更新脚本即可 |
| **安全** | 安全或隐私相关 | **强烈建议立即更新** |

> **兼容性承诺**：本工作台的用户自有数据（`models.json`、`auth.json`、自定义 MCP 条目、
> `lab-mode.flag`）在更新过程中**永不被覆盖**。若某次更新需要用户手工干预，
> 会在对应条目中显式标注「**需要手工操作**」。
