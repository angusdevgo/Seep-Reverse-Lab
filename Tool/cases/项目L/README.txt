===============================================================================
  INT0 REVERSE ENGINEERING RESEARCH SUITE
  Release: 项目L.v3.5.5.1.HookDll-INT0
  Target : 项目L v3.5.5.1  (Windows 桌面截图贴图工具 / Qt5 C++ / x64)
===============================================================================

[EN] English
-------------------------------------------------------------------------------
This release archive is an educational reverse engineering research suite
analyzing the authorization model, cloud-computing dependency and remote
control channel of 项目L v3.5.5.1.

Three capabilities were achieved - all inside a single proxy DLL, with the
official binaries left byte-for-byte pristine on disk:

  1. Membership privilege bypass   -> in-memory constant-folding of 11 local
                                      boolean decision functions (14 features)
  2. Translation backend hijack    -> {API_ENDPOINT} in-memory rewrite +
                                      embedded local LLM gateway (any OpenAI /
                                      Gemini / Anthropic compatible API)
  3. Cloud-control removal         -> in-memory constant-folding of 3 remote
                                      config / auto-update functions

KEY TECHNIQUE - PROXY DLL (PE Forwarder):
  The host EXE imports 282 C++ symbols from 项目L_Auth.dll via its IAT.
  We rename the official DLL to 项目L_AuthReal.dll, then drop in our own
  项目L_Auth.dll whose export table contains 282 PE forwarders pointing at
  the renamed original. The loader resolves everything transparently, and our
  code now lives inside the host process - able to patch memory and hook
  functions without touching a single official byte.

  +---------------------------------------------------------------+
  |  项目L.exe --IAT--> 项目L_Auth.dll (our proxy, 260 KB)          |
  |                        | 282 PE forwarders                    |
  |                        v                                      |
  |                    项目L_AuthReal.dll (official, 3.7 MB)        |
  |                        + in-process memory patch engine       |
  |                        + embedded 127.0.0.1 LLM gateway       |
  +---------------------------------------------------------------+

FOUR CRITICAL PITFALLS (all cause process crashes):
  P1. rel32 jump overflow       -> 9 GB distance exceeds +-2 GB, must use
                                   14-byte absolute jump
  P2. lost ctor return value rax -> factory returns rax as the new object
                                   pointer -> wild pointer -> delayed heap
                                   corruption
  P3. missing 3rd argument r8    -> base-class ctor receives garbage pointer
  P4. trampoline stack semantics -> shadow space written into hook frame,
                                   use unhook-call-rehook instead

DISCLAIMER:
This project is strictly for academic research, security auditing, and
educational purposes. Commercial exploitation is strictly prohibited.
If this software is valuable to your workflow, please support the original
authors by purchasing a genuine commercial license.

PACKAGE CONTENTS:
  - README.txt                       (bilingual documentation)
  - build.ps1                        (packaging + SHA256SUMS generator)
  - docs/reverse-engineering.md      (full RE walkthrough: proxy-DLL design,
                                      privilege decision chain, translation
                                      endpoint rewrite, cloud-control removal,
                                      four critical pitfalls, CWE-602 analysis,
                                      defense-in-depth remediation)
  - src/项目L_hook.c                   (hook engine: forwarder proxy, in-memory
                                      patch engine, UI injection, cloud kill)
  - src/项目L_bridge.c                 (embedded LLM gateway: minimal JSON,
                                      Winsock server, WinHTTP client)
  - src/项目L_bridge.h                 (gateway interface)

BUILD:
  Requires Zig (or any MinGW-w64 toolchain):
    zig cc -target x86_64-windows-gnu -shared -O2 ^
        -o 项目L_Auth.dll src\项目L_hook.c src\项目L_bridge.c ^
        -lkernel32 -lws2_32 -lwinhttp
  The .def forwarder table must be generated from the official DLL's export
  directory (282 symbols).

TECHNICAL HIGHLIGHTS:
  - Feature enum        : 14 FeatureType entries extracted from Qt meta-object
  - Patch sites         : 11 privilege decisions + 3 cloud-control functions
  - Endpoint rewrite    : 4 memory patches (string slot + mov/lea immediates)
  - UI injection        : QComboBox::insertItem via official-equivalent call
  - LLM gateway         : auto-detects OpenAI / Gemini / Anthropic protocols
  - Revert              : 100% official SHA256 verified, zero residue


[中文] 简体中文
-------------------------------------------------------------------------------
本发布包为学术研究性质的逆向工程研究套件，分析 项目L v3.5.5.1 的授权模型、
云端算力依赖与远程控制通道。

全部能力仅由**单个代理 DLL** 实现，磁盘上的官方二进制保持逐字节纯净：

  1. 会员特权旁路     -> 内存中恒值化 11 处本地布尔判定函数（14 项功能）
  2. 翻译后端接管     -> 内存改写 {API_ENDPOINT} + 内嵌本地大模型网关
                        （支持任意 OpenAI / Gemini / Anthropic 兼容 API）
  3. 云控剥离         -> 内存中恒值化 3 处远程配置 / 自动更新函数

关键技术 —— 代理 DLL（PE Forwarder）：
  宿主 EXE 通过 IAT 从 项目L_Auth.dll 导入 282 个 C++ 符号。
  我们把官方库改名为 项目L_AuthReal.dll，再用自建的 项目L_Auth.dll 顶替，
  其导出表包含 282 条 PE 转发器指向改名后的官方库。加载器透明解析全部符号，
  我们的代码由此进入宿主进程，从而能在**不改动任何官方字节**的前提下
  改写宿主内存、Hook 宿主函数。

四大致命坑点（均会导致进程崩溃）：
  坑 1  rel32 跳转溢出        -> 间距 9 GB 超出 ±2 GB，必须用 14 字节绝对跳转
  坑 2  构造函数返回值 rax 丢失 -> 工厂函数直接把 rax 作为新对象指针返回，
                                  产生野指针 -> 延迟堆损坏
  坑 3  漏转发第 3 个参数 r8   -> 基类构造函数拿到垃圾指针
  坑 4  trampoline 栈语义错误  -> 影子空间写入 Hook 栈帧，改用 unhook-call-rehook

免责声明：
本项目严格用于学术研究、安全审计与教育目的，严禁商业利用。
若该软件对您的工作有价值，请购买正版授权以支持原作者。

包内容：
  - README.txt                       双语说明文档
  - build.ps1                        打包 + SHA256SUMS 生成器
  - docs/reverse-engineering.md      完整逆向走查报告（代理 DLL 设计、特权判定
                                     链路、翻译端点改写、云控剥离、四大坑点、
                                     CWE-602 分析、纵深防御整改方案）
  - src/项目L_hook.c                    Hook 引擎（转发代理 / 内存补丁 / UI 注入 / 云控屏蔽）
  - src/项目L_bridge.c                  内嵌大模型网关（极简 JSON / Winsock 服务端 / WinHTTP 客户端）
  - src/项目L_bridge.h                  网关接口

构建：
  需要 Zig（或任意 MinGW-w64 工具链）：
    zig cc -target x86_64-windows-gnu -shared -O2 ^
        -o 项目L_Auth.dll src\项目L_hook.c src\项目L_bridge.c ^
        -lkernel32 -lws2_32 -lwinhttp
  .def 转发表需从官方 DLL 的导出目录生成（282 个符号）。

技术要点：
  - 功能枚举    : 从 Qt 元对象数据提取 14 项 FeatureType
  - 补丁点      : 11 处特权判定 + 3 处云控函数
  - 端点改写    : 4 处内存补丁（字符串槽 + mov/lea 立即数）
  - UI 注入     : 以官方等价调用注入 QComboBox::insertItem
  - 大模型网关  : 自动识别 OpenAI / Gemini / Anthropic 三种协议
  - 彻底还原    : 100% 官方 SHA256 校验通过，零残留

===============================================================================
  INT0 COLLECTIVE // 学术研究用途 // 支持正版 (https://项目L.cn/)
===============================================================================
