# 逆向与客户端安全实战工具箱使用指南 (Toolkit Guide)

本工作空间已将业界顶尖的逆向工程规范（`reverse-skill`）与我们本地实战经验（`softseep`、`MuMu/XYplorer/Hills` 注入体系、`seep` MCP 服务）深度融合，为日常的客户端鉴权分析、功能本地化、安卓逆向与攻防测试提供一站式支持。

---

## 一、核心工具与脚本目录一览

所有脚本统一存放在 `Tool/scripts/` 下，严禁散落根目录：

| 脚本 / 工具 | 路径 | 核心用途 |
| :--- | :--- | :--- |
| **工具链自检** | `Tool/scripts/refresh-tool-index.ps1` | 秒级扫描系统已安装工具（IDA、Radare2、ADB、Python、Node 等）并生成状态表 |
| **任务建档门禁** | `Tool/scripts/case-init.ps1` | 新任务一键在 `work/<case_name>` 独立建档，自动生成 `scope.md` 与证据链 |
| **APK 反编译流水线** | `Tool/scripts/apk/decode.ps1` | 一键运行 `jadx` + `apktool` 解包反编译并生成组件摘要 |
| **APK 重打包与签名** | `Tool/scripts/apk/rebuild-sign-install.ps1` | 修改 Smali 后全自动执行 `apktool b` -> 4字节对齐 -> 签名 -> ADB 推送安装 |
| **Frida 动态注入** | `Tool/scripts/apk/frida-run.ps1` | 标准化设备枚举、进程列表与 Spawn/Attach 动态 Hook 运行 |
| **IDA Pro MCP 唤醒** | `Tool/scripts/trigger_ida_mcp.ps1` | 静默启动 IDA Pro 64 并自动挂载 MCP 分析链路 |

---

## 二、典型工作场景实战流程

### 场景 1：Windows 软件功能本地化与鉴权走查（如 XYplorer、Hills、MuMu 等）
1. **新建任务沙盒**：
   ```powershell
   powershell -File Tool/scripts/case-init.ps1 -CaseName "hills-localize" -Preset offline-sample -Sample "D:\Target\app.exe"
   ```
   *产物将完整隔离在 `work/hills-localize/` 下，不污染任何工作区根目录。*
2. **IDA 自动化辅助分析**：
   - 使用 `mcp_ida_*` 系列工具或唤醒 IDA Pro；
   - 检索 `License`、`VIP`、`Expire` 等关键函数，提取判断逻辑分支。
3. **编写免杀代理 DLL 热补丁**：
   - 遵循 `softseep` 战术，优先选取宿主必定隐式引用的系统库（如 `version.dll`、`dinput8.dll`）；
   - 利用 `DllMain` 线程或劫持跳板对目标整型返回值函数进行无损 Patch（保持原 EXE 数字签名）；
   - 使用 `zig cc` 或 MSVC 编译并部署验证。

---

### 场景 2：Android 应用本地化与逆向走查
1. **一键反编译**：
   ```powershell
   powershell -File Tool/scripts/apk/decode.ps1 -ApkPath "D:\Target\app.apk" -Clean
   ```
2. **定位与修改逻辑**：
   - 查看 Java 逻辑定位鉴权与广告拦截点；
   - 在生成的 `smali/` 目录下按位点打桩（如 `return-void` 或强制返回 `const/4 v0, 0x1`）。
3. **一键重打包、签名与安装**：
   ```powershell
   powershell -File Tool/scripts/apk/rebuild-sign-install.ps1 -ProjectDir "D:\Target\app_apktool" -Install
   ```
   *脚本将全自动处理 `zipalign` 对齐和测试证书签名，并自动推送到当前运行的 MuMu 模拟器中。*

---

### 三、全能 MCP 服务与知识库检索（seep）

当前知识库已扩展至 **69 篇** 专业攻防战术笔记，支持随时查询模式与代码：
- `search_knowledge_base(query="edr bypass")`：检索内核防护与动态代码抑制绕过
- `search_knowledge_base(query="js webpack sign")`：检索前端签名与本地补环境手册
- `generate_frida_hook(...)`：一键生成 Java / Native 运行时 Hook 脚本

---

### 四、防模型审查双轨保障
日常与小π沟通时：
- 您可以直接输入日常口语，底层扩展已启用 **协议级 `BLOCK_NONE` 解封** 与 **敏感词平滑脱敏**；
- 您也可以直接使用极简指令：
  - `poc <目标>`：快速生成本地逻辑脆弱性测试代码
  - `find-auth <目标>`：自动检索本地 License/VIP/分支判定位点
  - `hook <函数/位点>`：直接编写动态验证脚本
  - `gen-patch <位点>`：编写内存热补丁/代理DLL验证代码
  - `report`：一键归纳全流程白盒审计报告

---

## 五、Android 外部工具箱（动态插桩 / 内存脱壳 / Flutter AOT）

仓库内置的是可随包分发的文件型工具（JADX / Apktool / Radare2 / 知识库）；
而 **Frida / objection / frida-dexdump / APKiD / Aotopsy** 属于运行时工具，安装在
`D:\Tool\Android`（独立 venv，不污染系统 Python），并通过垫片进入 `PATH`。

### 一键安装 / 修复（幂等）

```powershell
powershell -ExecutionPolicy Bypass -File Tool\scripts\android\install-android-toolbox.ps1
```

### 四个作战脚本

| 脚本 | 作用 | 典型调用 |
| :--- | :--- | :--- |
| `android-recon.ps1` | 一键资产画像：结构清点 + APKiD 加固指纹 + 清单摘要 + Flutter 判定 → **直接给路线建议** | `-ApkPath .\target.apk` |
| `apkid-scan.ps1` | 只看壳 / 反调试 / 反模拟器 / 混淆器 | `-ApkPath .\target.apk` |
| `frida-dexdump-run.ps1` | 加固包内存脱壳（前置校验 adb + frida-server 版本一致性） | `-Package <包名> -Spawn -DeepSearch` |
| `aotopsy-run.ps1` | Flutter `libapp.so` 分析：函数名 / 字符串引用 / Dart 伪代码 / 源码重建 | `-Target app.apk -Action find-libapp\|signal\|strings` |
| `objection-run.ps1` | 运行时自动化 REPL（关 SSL Pinning / 关 Root / 观察鉴权方法） | `-Package <包名>` |

### MCP 原生工具

`seep_android_toolbox()` / `seep_apkid_scan(apk_path)` / `seep_aotopsy(target_path, action, keyword)`

### 两条硬门

1. **Frida 主机 ↔ 设备 frida-server 版本必须严格一致** —— 不一致时的"抓不到"是工具问题，不是漏洞不存在；
2. **Aotopsy ↔ Dart 版本** —— 输出 `Support: NOK` 必须停下来换工具，不能把反汇编当正确答案读。

完整说明见 **`Tool/docs/ANDROID-TOOLBOX.md`**。

---

## 六、Web / 流媒体取证工具箱（HLS · 防盗链 · Spider）

补的是 Web 维度的“手”：**能脱离浏览器发请求、改包、验流、拆 spider**。

### 一键安装 / 修复（幂等）

```powershell
powershell -ExecutionPolicy Bypass -File Tool\scripts\web\install-web-toolbox.ps1
```

默认落盘 `D:\Tool\Web`（`SEEP_WEB_TOOLBOX` 可覆盖），装 ffmpeg + ffprobe 并生成垫片入 PATH。

### 三个作战脚本

| 脚本 | 作用 | 典型调用 |
| :--- | :--- | :--- |
| `hls-analyze.ps1` | **HLS 取证主力**：判 6 类根因（防盗链 / key 鉴权 / AES-128 / SAMPLE-AES / DRM / 源失效）+ key 双态探测 + ffmpeg 实解 + ffprobe 验证 | `-Url <m3u8> -Referer <r> -UserAgent <ua>` |
| `http-replay.ps1` | 头变体矩阵重放，**定位真正的门槛头**（或证明头不是门槛） | `-Url <api>` 或 `-Curl "<浏览器复制>"`，`-RateTest 10` 检测频控 |
| `spider-extract.ps1` | TVBox/CatVod spider 三入口（home/category/detail/player）+ 硬编码域名/接口/**凭据**/**请求头**提取 | `-Path .\spider.jar` |

### MCP 原生工具

`seep_web_toolbox()` / `seep_hls_analyze(...)` / `seep_http_replay(...)` / `seep_spider_extract(target_path)`

### 两条硬门

1. **ffmpeg 只给 `-headers` 不给 `-user_agent`** → 分片必 403（影视站典型陷阱）。UA/Referer 必须用独立选项；
2. **命中 DRM（Widevine/FairPlay/PlayReady）立即 STOP** —— 写“不可逆向，需版权方授权”，不探测许可证服务器。

完整说明见 **`Tool/docs/WEB-TOOLBOX.md`**；战术纪律见 Skill **`webseep`**。