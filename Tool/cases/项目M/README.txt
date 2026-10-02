===============================================================================
  INT0 REVERSE ENGINEERING RESEARCH SUITE
  Release: 项目M.v2026.8.AuthBypass-INT0
  Target : 项目M v2026.8  (Windows Web 安全审计套件 / Java + install4j / 混淆加固)
===============================================================================

[EN] English
-------------------------------------------------------------------------------
This release archive is an educational reverse engineering research suite
analyzing the licensing model, cryptographic verification, and runtime authorization
decisions of 项目M v2026.8 (build 53343).

Three protection and verification layers were analyzed and bypassed:
  1. install4j Native Launcher + JRE Bootstrapping
     -> DLL search-order hijacking (version.dll IAT hook on JNI_CreateJavaVM)
  2. Heavy ZKM-like Class/Method/String Obfuscation
     -> Reflective dispatch (burp.Zfqu -> burp.Zp74 / burp.Zwa8 / burp.Zyc7)
  3. Client-Side Privilege Gating & State Machine (CWE-602)
     -> Native JDK java.lang.classfile runtime bytecode transformation
        (burp.Zfqu / burp.Zwxg.Zu) + license & AI activation token seeding in Preferences

DISCLAIMER:
This project is strictly for academic research, security auditing, and
educational purposes. Commercial exploitation is strictly prohibited.
If this software is valuable to your workflow, please support the original
authors by purchasing a genuine commercial license.

PACKAGE CONTENTS:
  - README.txt                       (bilingual documentation)
  - build.ps1                        (packaging + SHA256SUMS generator)
  - docs/reverse-engineering.md      (full RE walkthrough, protection layers,
                                      licensing architecture, CWE-602 analysis,
                                      dynamic JavaAgent bytecode patching)
  - docs/dll-hijack-and-agent.md     (native DLL search-order hijacking mapping,
                                      IAT hook on GetProcAddress, JNI wrapper)
  - src/BurpLoaderAgent.java         (JDK 26 java.lang.classfile bytecode patcher)
  - src/BuildAgent.java              (in-process compiler using JRE JavacTool)
  - src/ClearPrefs.java              (registry state reset utility)
  - src/BurpLoaderAgent.jar          (compiled JavaAgent binary)
  - src/setup_poc.bat                (one-click deploy, 5-stage auto-detect)
  - src/clean_poc.bat                (one-click restore to original unpatched state)
  - src/hijack/version.rs            (native proxy DLL source in Rust)
  - src/hijack/version.dll           (compiled 64-bit hijack DLL with 17 exports)

VULNERABILITY SUMMARY
  CWE-602  client-side enforcement of server-side security (local boolean gates)
  CWE-321  use of hard-coded cryptographic key material (1024-bit RSA modulus)
  CWE-427  uncontrolled search path element (VERSION.dll not in KnownDLLs)
  CWE-345  insufficient verification of data authenticity (no JAR hash self-check)

  Decision gate   : burp.Zer4.lambda$new$3() -> this.Zh == null ? Community : Professional
  State machine   : burp.Zwxg.Zu() -> Zno0 forces Professional edition
  Trust anchor    : burp.Zeo9.ZO (1024-bit RSA modulus in constant pool)
  Injection vector: DLL search order hijack on jvm.dll -> version.dll -> IAT hook

-------------------------------------------------------------------------------
[ZH] 简体中文
-------------------------------------------------------------------------------
本案例是针对 项目M v2026.8 客户端授权机制、非对称加密验签链与
原生启动引导链路的教育型白盒安全审计研究归档。

突破的三大防护层：
  1. install4j 原生启动器与 JRE 引导层：
     利用 VERSION.dll 未受 KnownDLLs 保护的特性，在应用程序目录实施
     DLL 搜索顺序劫持（T1574.001），在 DllMain 中改写主模块 IAT 槽位 #27
     （kernel32!GetProcAddress），拦截 JNI_CreateJavaVM 调用，向 JavaVMInitArgs
     追加 -javaagent 参数（nOptions 18 -> 19），实现原生层无痕参数注入。
  2. 重度类名/方法名/字符串动态混淆：
     还原了基于反射的链式动态类加载验签结构（burp.Zfqu 反射调用 burp.Zp74.ZX、
     burp.Zwa8.Zp、burp.Zyc7.Zi），解密其核心模数与参数。
  3. 客户端本地特权决策分支走查（CWE-602）：
     利用 JDK 26 原生 java.lang.classfile API（零第三方依赖），在运行时
     对 burp.Zfqu 与许可准入状态机 burp.Zwxg.Zu 进行微创字节码改写，恒定
     返回已授权状态；同时在注册表 Preferences 中播种授权主体与 AI ActivationToken，
     全量解锁包括漏洞扫描器（Scanner）、全速 Intruder、项目持久化在内的本地专业版功能。

免责声明：
本项目仅供学术研究、授权安全走查及教育用途。严禁用于任何商业与非法侵权行为。
若该工具在您的商业工作流中有价值，请向原厂商购买正版商业许可。
