===============================================================================
  INT0 REVERSE ENGINEERING RESEARCH SUITE
  Release: 项目J.<目标版本>.Activator-INT0
  Target : 项目J <目标版本>  (Windows 商标文书制作工具 / 在线卡密授权)
===============================================================================

[EN] English
-------------------------------------------------------------------------------
This release archive is an educational reverse engineering research suite
analyzing the licensing model, authorization protocol and runtime memory
structures of 项目J <目标版本>.

DISCLAIMER:
This project is strictly for academic research, security auditing, and
educational purposes. Commercial exploitation is strictly prohibited.
If this software is valuable to your workflow, please support the original
authors by purchasing a genuine commercial license.

PACKAGE CONTENTS:
  - 项目J.<目标版本>.Activator-INT0.nfo
  - README.txt                     (Bilingual documentation)
  - build.ps1                      (packaging + SHA256SUMS generator)
  - docs/reverse-engineering.md    (full RE walkthrough & methodology)
  - docs/protocol-and-patch.md     (wire protocol + patch table + AOB)
  - src/apply_patch.py             (one-click patcher, Python)
  - src/apply_patch.ps1            (one-click patcher, PowerShell only)
  - src/poc_frida_run.py           (Frida injector entry)
  - src/poc_frida_bypass.js        (Frida bypass script)
  - src/run_repro.bat              (double-click reproduction, GBK encoded)

USAGE:
  1. Recommended (no Frida required):
       python src/apply_patch.py [path\to\target.exe]
     then type ANY card key (e.g. 123456) in the login box and click the
     login button. The full main window should open.
  2. PowerShell only:
       powershell -NoProfile -ExecutionPolicy Bypass -File src\apply_patch.ps1
  3. Frida (no file modification):
       pip install frida
       python src/poc_frida_run.py
  4. Double-click:
       src\run_repro.bat

NOTE:
  - The target ships with a requireAdministrator manifest; run the patcher
    as Administrator, or drop the manifest to asInvoker on a COPY first.
  - Disk files are never modified: the .ev3n section has rawsize = 0, so the
    patched instructions simply do not exist on disk. Patching is runtime-only
    and disappears when the process exits.

-------------------------------------------------------------------------------
[ZH] 简体中文
-------------------------------------------------------------------------------
本发布包为针对 项目J <目标版本> 软件授权机制、鉴权协议与运行期内存逻辑的
完整逆向工程学术研究套件。

免责声明：
本项目仅供计算机逆向工程、软件授权安全与密码学机制的学习和学术交流。
严禁用于任何商业牟利。若该软件对您的日常工作和学习带来帮助，
请支持原厂并购买官方正版授权。

套件内容：
  - 项目J.<目标版本>.Activator-INT0.nfo
  - README.txt                     （中英双语文档）
  - build.ps1                      （打包与 SHA256SUMS 生成）
  - docs/reverse-engineering.md    （完整逆向复盘与方法论）
  - docs/protocol-and-patch.md     （协议结构 + 补丁全表 + AOB 特征码）
  - src/apply_patch.py             （一键补丁器，Python）
  - src/apply_patch.ps1            （一键补丁器，纯 PowerShell）
  - src/poc_frida_run.py           （Frida 注入入口）
  - src/poc_frida_bypass.js        （Frida 旁路脚本）
  - src/run_repro.bat              （双击一键复现，GBK 编码）

使用方式：
  1. 推荐（无需 Frida）：
       python src/apply_patch.py [目标exe路径]
     然后在登录框输入【任意】卡密（例如 123456）并点击「登陆」，
     主功能界面应正常打开。
  2. 仅有 PowerShell：
       powershell -NoProfile -ExecutionPolicy Bypass -File src\apply_patch.ps1
  3. Frida（不改动任何文件）：
       pip install frida
       python src/poc_frida_run.py
  4. 双击运行：
       src\run_repro.bat

注意事项：
  - 目标自带 requireAdministrator 清单；请以管理员身份运行补丁器，
    或先对【副本】把清单降权为 asInvoker。
  - 磁盘文件永不修改：`.ev3n` 段 rawsize = 0，被改写的指令在磁盘上根本不存在。
    补丁仅作用于运行期内存，进程退出即失效。

-------------------------------------------------------------------------------
  TECHNICAL HIGHLIGHTS / 技术要点
-------------------------------------------------------------------------------
  [1] Packer analysis / 壳分析
      Whole-file entropy ~7.997 per 64KB, random 4-char section names, EP hidden
      inside the ciphertext section, imports relocated into .rsrc, only 23
      imports. BUT: DllCharacteristics = 0x0000 (no ASLR, no NX) and the code
      section is RWX -> runtime memory patching is trivially possible without
      ever unpacking the binary.
      全文件熵 ~7.997/64KB、随机 4 字符段名、EP 藏于密文段、导入表外置、
      仅 23 项导入。但 DllCharacteristics = 0x0000（无 ASLR/NX）且代码段 RWX
      -> 完全无需脱壳，直接改运行期内存即可。

  [2] Host language / 宿主语言
      E-language (EPL) statically compiled: manifest name "E.App", data-type
      constants 0x80000002/04/05 & 0x80000301, dispatcher `call 0x4474xx`,
      and the tell-tale `pushal / mov eax,1..6 / popal / fninit` dead-code
      prologue block at every function entry.
      易语言静态编译：清单 E.App、类型常量 0x8000000x、调度器 call 0x4474xx、
      以及每个函数入口的 pushal/mov eax,1..6/popal 死代码块。

  [3] Locating the decision point / 裁决点定位
      Hook ws2_32!recv, read `this.returnAddress` -> one shot pinpoints the
      network receive wrapper, then walk up to the login event handler.
      挂钩 ws2_32!recv 读取 this.returnAddress，一次回溯即可定位收包函数，
      再上溯到登录事件处理函数。

  [4] Patch discipline / 补丁纪律
      Change the CONDITIONAL JUMP, never the return value and never `ret` the
      whole function. Verified with an A/B/C/F control-experiment matrix.
      改条件跳转，绝不要改返回值、绝不要整体 ret。已用 A/B/C/F 对照实验矩阵验证。

  [5] Engineering pitfalls / 工程陷阱
      * .bat with Chinese text must be GBK (cp936) encoded, not UTF-8.
      * A GUI child launched from a .bat inherits the console; when the console
        closes it receives CTRL_CLOSE_EVENT and dies -> use
        CREATE_DETACHED_PROCESS.
      * 中文 .bat 必须用 GBK(cp936) 编码，不能用 UTF-8。
      * 从 .bat 启动的 GUI 子进程会继承控制台，控制台关闭时收到
        CTRL_CLOSE_EVENT 被连带杀掉 -> 必须加 CREATE_DETACHED_PROCESS。

-------------------------------------------------------------------------------
  CWE MAPPING
-------------------------------------------------------------------------------
  CWE-602  Client-Side Enforcement of Server-Side Security   (primary)
  CWE-693  Protection Mechanism Failure
  CWE-319  Cleartext Transmission of Sensitive Information
  CWE-522  Insufficiently Protected Credentials

-------------------------------------------------------------------------------
  REMEDIATION SUMMARY (defense-in-depth)
-------------------------------------------------------------------------------
  * Server-side authority: server issues SIGNED license credentials
    (HMAC-SHA256 / JWT); the client verifies signatures and NEVER decides.
    Core features (rendering / assets / export) move server-side or are
    exchanged for one-time nonce tokens. Bind card keys to machine
    fingerprints with concurrency control. Heartbeat failure must trigger
    SERVER-SIDE revocation, not client suicide.
  * Transport: TLS 1.2+ everywhere with certificate pinning; add
    timestamp + nonce + sign to requests; whitelist server-supplied UI text.
  * Client hardening: enable DYNAMIC_BASE | NX_COMPAT; drop the decrypted code
    section to RX after unpacking; move auth logic to native code with
    virtualization + integrity self-check; add anti-debug / anti-hook.
  * Data: never store card keys or third-party API credentials in plaintext
    (DPAPI / AES-GCM); proxy third-party API calls through your own backend.

===============================================================================
  Educational & security-audit research only. Support the original vendor.
  仅供学习与授权安全审计。请支持原厂正版。
===============================================================================
