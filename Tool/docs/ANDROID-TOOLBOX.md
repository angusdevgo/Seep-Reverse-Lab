# Android 动态/静态外部工具箱（Frida / objection / frida-dexdump / APKiD / Aotopsy）

> 本文件说明 Seep Lab如何把 Android 逆向的**外部专业工具链**落地到本机，并在工作台内
> 建立统一的调用入口（PowerShell 脚本 + MCP 工具），使 Agent 与人都不必再记路径、不必临时 pip install。

---

## 一、为什么需要这一层

Seep 仓库内置的是**纯文件型**工具（JADX / Apktool / Radare2 / 知识库），可以随仓库分发。
而下面这些能力本质上是**运行时/生态型**工具，体积大、依赖 Python 运行时、且需要与设备端版本对齐，
不适合塞进仓库，所以采用「**本机工具箱 + 工作台垫片**」的方式接入：

| 能力 | 工具 | 缺了它会怎样 |
| :--- | :--- | :--- |
| 运行时插桩 / 绕过 | **Frida** | 无法动态验证任何客户端鉴权分支（CWE-602 的 PoC 只能靠静态猜测） |
| 自动化运行时 | **objection** | 每条「关 SSL Pinning / 关 Root 检测」都要手写 Frida 脚本 |
| 内存脱壳 | **frida-dexdump** | 遇到加固包（如易盾/顶象/DexGuard）直接卡关，JADX 只能看到壳存根 |
| 加固指纹识别 | **APKiD** | 不知道有没有壳、有没有反模拟器，路线选择全靠猜 |
| Flutter / Dart AOT | **Aotopsy** | Flutter 应用的业务逻辑、签名密钥全在 `libapp.so`，JADX 里是空的 |

---

## 二、目录布局（本机）

默认根目录：`D:\Tool\Android`（可用环境变量 `SEEP_ANDROID_TOOLBOX` 覆盖）

```
D:\Tool\Android\
├── bin\                    统一垫片目录（已在用户 PATH）
│   ├── frida.cmd           frida CLI
│   ├── frida-ps.cmd        进程枚举
│   ├── frida-trace.cmd     调用追踪
│   ├── frida-ls-devices.cmd
│   ├── objection.cmd
│   ├── frida-dexdump.cmd
│   ├── apkid.cmd
│   └── aotopsy.cmd
├── frida-env\              独立 Python venv（不污染系统 Python / 不污染工作台）
│   └── Scripts\            frida / frida-tools / objection / frida-dexdump / apkid
├── aotopsy\                aotopsy.exe + ghidra_scripts\ + ida_scripts\
├── platform-tools\         adb
└── build-tools\<ver>\      aapt2 / zipalign / apksigner
```

**为什么用独立 venv**：Frida 的 Python 绑定与 frida-server 必须版本严格对齐，独立 venv 让
「换 frida 版本」变成一次 `pip install -U`，而不会影响工作台自身或其他工具。

---

## 三、安装 / 修复（幂等）

```powershell
cd <工作台根目录>
powershell -ExecutionPolicy Bypass -File Tool\scripts\android\install-android-toolbox.ps1
```

常用变体：

```powershell
# 只补 APKiD
powershell -ExecutionPolicy Bypass -File Tool\scripts\android\install-android-toolbox.ps1 -Only apkid

# 换安装根目录 + 不改 PATH
powershell -ExecutionPolicy Bypass -File Tool\scripts\android\install-android-toolbox.ps1 -Root E:\Android -SkipPath

# 指定用于建 venv 的 Python（必须 3.10 ~ 3.13，frida 暂无 3.14 轮子）
powershell -ExecutionPolicy Bypass -File Tool\scripts\android\install-android-toolbox.ps1 -PythonExe "C:\Program Files\Python312\python.exe"
```

脚本行为：已存在的 venv 直接复用 → 只做增量 `pip install` → 重写垫片 → 输出就绪看板。
**不会**删除用户自己装进该 venv 的包。

---

## 四、四个作战脚本

### 1. `android-recon.ps1` —— 一键资产画像（先跑这个）

```powershell
powershell -File Tool\scripts\android\android-recon.ps1 -ApkPath .\target.apk
powershell -File Tool\scripts\android\android-recon.ps1 -ApkPath .\a.apk,.\b.apk -OutDir .\recon
```

产出四块 + 一条路线建议：

1. **包体结构**：体积、DEX 数量与合计体积、SO 数量与 ABI、是否含 `libflutter.so` / `libapp.so`
2. **加固与对抗指纹**：`packer` / `protector` / `anti_vm` / `anti_debug` / `anti_hook` / `obfuscator` / `manipulator`
3. **清单摘要**：包名、版本、minSdk/targetSdk、启动组件、危险权限、`allowBackup`、`usesCleartextTraffic`
4. **技术栈判定 + Dart 版本**
5. **路线建议**（脚本直接给结论）：
   - 有壳 → 先 `frida-dexdump`
   - 有反调试/反模拟器 → 先 `objection` 伪装
   - 有 `libapp.so` → 走 Aotopsy
   - 都没有 → 直接 JADX 静态推进

证据落盘：`<OutDir>\<apk名>\recon.json`

### 2. `apkid-scan.ps1` —— 只看加固指纹

```powershell
powershell -File Tool\scripts\android\apkid-scan.ps1 -ApkPath .\target.apk
powershell -File Tool\scripts\android\apkid-scan.ps1 -ApkPath .\target.apk -OutDir .\recon
powershell -File Tool\scripts\android\apkid-scan.ps1 -ApkPath .\target.apk -Raw
```

### 3. `frida-dexdump-run.ps1` —— 内存脱壳

```powershell
# 冷启动 + 深度搜索（脱壳标准姿势）
powershell -File Tool\scripts\android\frida-dexdump-run.ps1 -Package com.example.app -Spawn -DeepSearch

# 加固壳首包解密慢，延长等待
powershell -File Tool\scripts\android\frida-dexdump-run.ps1 -Package com.example.app -Spawn -SleepSeconds 12 -DeepSearch
```

脚本会先做两道前置检查，避免白跑：

1. `adb devices` 是否有 `device` 状态
2. `frida-ps -U` 是否能枚举进程（即 frida-server 在跑且**版本与主机一致**）

不通过时直接打印修复命令（含按版本拼好的 `adb push` 步骤），并询问是否继续。

产物：`.\dexdump_<包名>\*.dex`，按体积倒序列出，最大的那个就是主业务 DEX。

### 4. `aotopsy-run.ps1` —— Flutter / Dart AOT

```powershell
# 第一步：确认是不是 Flutter、Dart 版本多少
powershell -File Tool\scripts\android\aotopsy-run.ps1 -Target .\app.apk -Action find-libapp

# 快诊
powershell -File Tool\scripts\android\aotopsy-run.ps1 -Target .\app.apk -Action doctor

# 全管线（反汇编 + 调用边 + 行为信号，可加伪代码）
powershell -File Tool\scripts\android\aotopsy-run.ps1 -Target .\app.apk -Action signal -Decompile

# 找签名密钥 / API 路由的最短路径：字符串 → 反查引用函数
powershell -File Tool\scripts\android\aotopsy-run.ps1 -Target .\app.apk -Action strings -Find "X-Sign"

# 定点反编译（按类名或地址）
powershell -File Tool\scripts\android\aotopsy-run.ps1 -Target .\app.apk -Action decompile -Find "Sign"

# 重建 Dart 源码工程（最慢）
powershell -File Tool\scripts\android\aotopsy-run.ps1 -Target .\app.apk -Action export-dart -AppOnly
```

APK 场景下脚本会自动完成 `find-libapp → 抽取 libapp.so → 分析`，不用手动解压找路径。

### 5. `objection-run.ps1` —— 运行时自动化 REPL

```powershell
powershell -File Tool\scripts\android\objection-run.ps1 -Package com.example.app
# 冷启动后直接进 REPL
powershell -File Tool\scripts\android\objection-run.ps1 -Package com.example.app -Spawn
# 一次性执行（不进 REPL）
powershell -File Tool\scripts\android\objection-run.ps1 -Package com.example.app -Command "android sslpinning disable"
```

脚本使用 objection 1.12+ 的新 CLI（`-n <pkg> start` / `run <命令>`），已避开旧的 `-g` 弃用告警。
进入 REPL 后用这几条（脚本启动时也会打印）：

| 命令 | 作用 |
| :--- | :--- |
| `android sslpinning disable` | 关证书固定（抓包第一步） |
| `android root disable` | 关 root / 越狱检测 |
| `android root simulate` | 反向伪装成已 root |
| `android hooking list classes` | 枚举已加载类 |
| `android hooking watch class_method <类>.<方法> --dump-args --dump-return --dump-backtrace` | 观察鉴权方法入参/返回值/调用栈 |
| `memory list modules` | 已加载 SO（判断壳是否已解出真身） |
| `env` | 沙盒路径 / 数据目录 |

---

## 五、MCP 工具（Agent 原生调用）

seep MCP 新增 3 个工具（`Tool/mcp/seep_mcp_server.py`）：

| 工具 | 用途 |
| :--- | :--- |
| `seep_android_toolbox()` | 8 项工具就绪状态 + `adb devices` 在线设备 |
| `seep_apkid_scan(apk_path)` | 结构化加固指纹 + 路线建议（JSON） |
| `seep_aotopsy(target_path, action, keyword)` | Flutter AOT 分析（`find-libapp` / `doctor` / `signal` / `strings` / `export-dart`） |

`seep_status()` 的 `components` 中也新增了 `android_toolbox` 段，可直接看到整体就绪度。

---

## 六、两条不可绕过的版本门（重点）

### 1. Frida 主机 ↔ 设备版本必须严格一致

主机侧由 `install-android-toolbox.ps1` 固定，设备侧需自行推送同版本：

```powershell
# 版本必须与 frida --version 完全一致
adb push frida-server-<版本>-android-arm64 /data/local/tmp/frida-server
adb shell "su -c 'chmod 755 /data/local/tmp/frida-server'"
adb shell "su -c '/data/local/tmp/frida-server &'"
frida-ps -U        # 能列出进程才算通
```

版本漂移的典型症状：`frida -U` 报错但目标本身完全正常。
**这时"抓不到"是工具问题，不是漏洞不存在** —— 不要把工具失败当成样本结论。

### 2. Aotopsy ↔ Dart 版本

Aotopsy 以结构建模支持 Dart 2.10 → 3.13，并在 `find-libapp` / `doctor` 直接报出检测到的版本。
若输出 `Support: NOK`，**立即停止**，不要继续把反汇编当正确答案读 ——
跨版本的正确做法是换工具（如 blutter + 对应 Dart SDK），而不是"先跑跑看"。

---

## 七、与内置工具链的分工

| 阶段 | 工具 | 谁提供 |
| :--- | :--- | :--- |
| 加固/对抗指纹 | APKiD | 本机工具箱 |
| 结构/清单快照 | aapt2 | 本机 Android SDK |
| Java 语义层 | JADX（含 JADX-GUI） | 仓库内置 |
| Smali / 资源层 | Apktool | 仓库内置 |
| Native / SO 反汇编 | Radare2（内置）、IDA Pro（可选） | 仓库内置 / 商业 |
| Flutter / Dart AOT | Aotopsy | 本机工具箱 |
| 运行时插桩 / 伪装 | Frida + objection | 本机工具箱 |
| 内存脱壳 | frida-dexdump | 本机工具箱 |
| 重打包签名 | apktool + zipalign + apksigner | 仓库内置 + SDK |
| 方法论 / 战术检索 | 294 篇知识库 | 仓库内置 |

---

## 八、排障速查

| 现象 | 原因 | 处理 |
| :--- | :--- | :--- |
| `frida-ps -U` 报错 | frida-server 未跑 / 版本不一致 / 非 root | 按第六节重推 server |
| `frida-dexdump` 只产出壳 DEX | spawn 时机太早或搜索不够深 | `-Spawn -SleepSeconds 12 -DeepSearch` |
| `apkid` 无输出 | 目标不是有效 APK / 路径含特殊字符 | 用绝对路径，先 `unzip -l` 验证 |
| Aotopsy `Support: NOK` | Dart 版本超出建模范围 | 换 blutter + 对应 SDK，勿硬读 |
| `objection` 连不上 | 与 frida-server 版本不匹配 | 同步 frida 版本 |
| 新终端找不到 `frida` | PATH 只在用户级生效且需新开终端 | 重开终端，或用绝对路径 `D:\Tool\Android\bin\frida.cmd` |
