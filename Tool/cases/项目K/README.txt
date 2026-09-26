===============================================================================
  INT0 REVERSE ENGINEERING RESEARCH SUITE
  Release: 项目K.v7.19.AuthBypass-INT0
  Target : 项目K v7.19  (Windows 桌面文件管理器 / .NET WPF / Themida 加固)
===============================================================================

[EN] English
-------------------------------------------------------------------------------
This release archive is an educational reverse engineering research suite
analyzing the licensing model, local license storage and runtime authorization
decision of 项目K v7.19.

Four protection layers were defeated:
  1. Themida / WinLicense native packer  -> in-memory .NET PE reconstruction
  2. Method-body virtualization          -> custom JIT vtable hook (9632 real ILs)
  3. String encryption + delegate stubs  -> 858 runtime delegate resolutions
  4. Runtime Assembly.Load(byte[]) core  -> in-process dump + full decompilation

DISCLAIMER:
This project is strictly for academic research, security auditing, and
educational purposes. Commercial exploitation is strictly prohibited.
If this software is valuable to your workflow, please support the original
authors by purchasing a genuine commercial license.

PACKAGE CONTENTS:
  - README.txt                       (bilingual documentation)
  - README.nfo                       (scene-style release info)
  - build.ps1                        (packaging + SHA256SUMS generator)
  - docs/reverse-engineering.md      (full RE walkthrough, protection layers,
                                      license architecture, CWE analysis,
                                      DLL-based bypass with cloud-control removal,
                                      remediation guidance, methodology)
  - src/ProjectKUnlock.cs            (AppDomainManager payload: license forgery +
                                      cloud-control block + App.Days memory lock)
  - src/install.ps1                  (one-click deploy, PowerShell)
  - src/uninstall.ps1                (one-click uninstall / restore)
  - src/reset_license.py             (remove local license storage, reset trial)

VULNERABILITY SUMMARY
  CWE-602  client-side enforcement of server-side security
  CWE-321  use of hard-coded cryptographic key material
  CWE-327  broken/risky cryptographic algorithm (key derived from local machine code)
  CWE-345  insufficient verification of data authenticity (no signature / no MAC)
  CWE-472  externally-influenced input not validated (plaintext expiry date)

  License payload : <MachineCode> \t <ExpireDate> [\t <Email>]
  Cipher          : AES-128-CBC / PKCS7 / UTF8
  Key material    : fully derived from the LOCAL machine code (no server secret)
  Integrity       : none (no RSA/ECDSA signature, no MAC)
  Storage         : HKCU registry value + hidden file under %APPDATA%
  Decision point  : a single 'public static int Days' field

  => Forging the payload into BOTH storage locations yields a permanent license.

CLOUD CONTROL
  The vendor performs an online re-validation about 15s after startup. If the
  server rejects the machine, the client rewrites the local license to
  '<MachineCode> \t Invalid \t <Email>' and then terminates via Environment.Exit(0).
  A plain license forgery therefore only survives ~1-2 minutes.

  The bundled DLL defeats this with three redundant layers:
    1. license forgery (WMI machine code recompute + AES derivation + dual write)
    2. cloud-control removal (selective IWebProxy: only the vendor domain is
       routed to a dead port; all other traffic stays direct)
    3. memory lock (a watchdog pins App.Days to the permanent threshold every
       second, and restores the on-disk license within 5 seconds if rewritten)

  Measured: 8+ minutes of stable operation, zero outbound connections,
            zero license rollback events.

NOTE ON REDACTION
  The 19-character salt constant used by the target to derive the machine code has
  been redacted as <REDACTED_SALT> per the repository desensitization policy.
  The full value is retained only in the local private report. Substitute the real
  salt to make src/ProjectKUnlock.cs directly runnable.
  The vendor domain is likewise shown as <vendor-domain>.

BUILD
  csc -nologo -target:library -platform:anycpu -out:ProjectKUnlock.dll ^
      -r:System.Management.dll src/ProjectKUnlock.cs
  (C# 5 compiler from .NET Framework 4.x is sufficient)


[中文] 中文说明
-------------------------------------------------------------------------------
本归档是 项目K v7.19 的授权模型、本地许可存储与运行期授权决策的教育性逆向研究套件。

攻破的四层防护：
  1. Themida / WinLicense 原生壳      -> 进程内存 .NET PE 重建
  2. 方法体虚拟化                      -> 自建 JIT vtable Hook（截获 9632 个真实 IL）
  3. 字符串加密 + 委托跳板             -> 运行期解析 858 个委托
  4. Assembly.Load(byte[]) 内嵌核心    -> 进程内 dump + 完整反编译

漏洞摘要（CWE-602 / 321 / 327 / 345 / 472）：
  许可载荷 : <机器码> \t <到期日期> [\t <邮箱>]
  加密算法 : AES-128-CBC / PKCS7 / UTF8
  密钥来源 : 完全由本地机器码派生（无服务端秘密参与）
  完整性   : 无（无 RSA/ECDSA 签名、无 MAC）
  存储位置 : HKCU 注册表值 + %APPDATA% 下隐藏文件
  决策单点 : 单一 'public static int Days' 字段

  => 将伪造载荷同步写入两处存储，即可获得永久授权。

云控说明：
  原厂在启动约 15 秒后执行在线复核；服务端判定未注册时会把本地许可改写为
  '<机器码> \t Invalid \t <邮箱>'，随后 Environment.Exit(0) 退出。
  因此纯许可伪造仅能维持约 1~2 分钟。

  随包 DLL 以三重冗余对抗：
    1. 许可伪造（WMI 复算机器码 + AES 派生 + 双写）
    2. 云控剥离（自定义 IWebProxy，仅将厂商域名路由到死端口，其余直连）
    3. 内存锁（看门狗每秒钉死 App.Days，5 秒内复原被改写的磁盘许可）

  实测：稳定运行 8 分钟以上，零外部连接，零许可回滚事件。

脱敏说明：
  目标程序用于派生机器码的 19 字符盐值常量已按仓库脱敏规范屏蔽为
  <REDACTED_SALT>，完整值仅保留在本地私有报告。替换为真实盐值后
  src/ProjectKUnlock.cs 即可直接运行。厂商域名同样以 <vendor-domain> 表示。

编译：
  csc -nologo -target:library -platform:anycpu -out:ProjectKUnlock.dll ^
      -r:System.Management.dll src/ProjectKUnlock.cs
  （.NET Framework 4.x 自带的 C# 5 编译器即可）

===============================================================================
INT0 RESEARCH GROUP
===============================================================================
