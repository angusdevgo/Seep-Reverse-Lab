===============================================================================
  INT0 REVERSE ENGINEERING RESEARCH SUITE
  Release: 项目N.v2.2.4.3.AuthBypass-INT0
  Target : 项目N v2.2.4.3  (Windows .NET 系统优化工具 / WPF / Eazfuscator.NET 全保护)
===============================================================================

[EN] English
-------------------------------------------------------------------------------
This case study analyzes the licensing architecture, protection stack and
runtime authorization decisions of 项目N v2.2.4.3 (build 2.2.4.3), a Windows
desktop system-optimization client built on .NET Framework / WPF.

Four independent authorization defects were identified and reproduced offline:

  1. Client-Side Entitlement Decision (CWE-602)
     -> Premium (PRO) entitlement is decided entirely by local boolean state.
        Of 26 feature flags, 4 are marked "PRO-only" at construction time, and
        a single global entitlement query entry point is referenced by 8 managed
        call sites (activation UI, task pipeline, editability gates, page gates).

  2. Fail-Open License Short-Circuit (CWE-287)
     -> The only decision point in the startup license-loading state machine
        treats a null / empty / "null" credential as "no verification required"
        and jumps straight into the success branch without issuing any request.

  3. Privileged State in User-Writable Storage (CWE-863)
     -> 71 feature switches (including all PRO-related ones) are stored as
        plaintext booleans under HKCU\Software\BoosterX with no integrity check.

  4. Cleartext Transport + Hard-Coded Key Material (CWE-319 / CWE-798)
     -> The license endpoint is plain HTTP and the request/response body is
        encrypted with a globally hard-coded AES-128 key shipped to every client.

The protection stack (Eazfuscator.NET full mode) was fully reversed:

  L1  Symbol renaming            -> 3,364 types decompiled
  L2  String encryption          -> 7,806 / 7,806 strings dumped at runtime
  L3  Assembly code encryption   -> algorithm fully recovered; 15,380 method
                                    bodies decrypted (keystream derived from the
                                    content hash of sibling sections = anti-tamper)
  L4  Code virtualization (VM)   -> ALL THREE sub-layers broken:
                                    (a) RSA-2048 / PKCS#1 v1.5 envelope
                                    (b) position-dependent stream XOR
                                    (c) self-describing Ascii85 method tokens
                                    => 722,260 bytes of VM bytecode recovered as
                                       readable plaintext (3,917 member records)
  L5  Custom symmetric cipher    -> TEA variant (32-bit block / 80-bit key /
                                    12 rounds / S-box round function) plus a
                                    5-stage cascade with a DeriveBytes KDF

KEY TAKEAWAY
  Protection strength and security architecture are ORTHOGONAL dimensions.
  项目N ships one of the strongest obfuscation stacks seen in this case library,
  yet the architectural defect ("the client decides") remains fully present.
  Obfuscation raises analysis cost; it cannot substitute for architectural fixes.

DISCLAIMER:
This project is strictly for academic research, security auditing, and
educational purposes. Commercial exploitation is strictly prohibited.
If this software is valuable to your workflow, please support the original
authors by purchasing a genuine commercial license.

PACKAGE CONTENTS:
  - README.txt                      (bilingual documentation, this file)
  - build.ps1                       (packaging + redaction scan + SHA256SUMS)
  - docs/reverse-engineering.md     (full RE walkthrough: protection layers,
                                     licensing architecture, CWE-602/287/863
                                     analysis, R1-R5 verification, hardening)
  - docs/protection-layers.md       (protection stack internals: code-encryption
                                     keystream derivation, VM three-layer recovery
                                     algorithms, custom cipher specification)
  - tools/bx_patch.py               (minimal binary patch tool, three profiles,
                                     with per-patch original-byte verification)

VERIFICATION GATE (R1-R5):
  R1 reproducibility   PASS  (script produces identical results across runs)
  R2 observability     PASS  (reflection probe: original False -> patched True)
  R3 idempotency       PASS  (always regenerated from the pristine original)
  R4 revertibility     PASS  (registry restore + regenerate from original)
  R5 version binding   PASS  (v2.2.4.3, SHA-256 pinned)

  Target SHA-256:
    d21ff11ac4f9077b53a22545a510d302ca371f12bc5ff8dd85c8e7d8198d6dc4


[中文] 简体中文
-------------------------------------------------------------------------------
本案例对 项目N v2.2.4.3（Windows .NET 桌面系统优化客户端）的授权架构、
保护栈与运行时授权决策进行完整走查。

共识别并离线复现 4 类独立授权缺陷：

  1. PRO 权益本地化裁决（CWE-602）
     付费权益完全由本地布尔量决定。26 个功能设置项中 4 项在构造时被标记为
     "PRO 专属"，且存在一个全局授权态查询入口，被 8 处托管调用点引用
     （激活页状态、任务执行流程、可编辑性门控、页面级门控）。

  2. 授权校验 Fail-Open 短路（CWE-287）
     启动期授权装载状态机中的唯一判定点，把 null / 空串 / "null" 凭据
     解释为"无需校验"，直接跳入成功分支，整个过程不发出任何请求。

  3. 特权状态存放于用户可写位置（CWE-863）
     71 个功能开关（含全部 PRO 相关开关）以明文布尔值存放于
     HKCU\Software\BoosterX，读取时未做任何完整性校验。

  4. 明文传输 + 硬编码密钥材料（CWE-319 / CWE-798）
     授权接口走明文 HTTP，请求/响应体仅用全局硬编码 AES-128 密钥加密，
     该密钥随客户端分发。

保护栈（Eazfuscator.NET 全保护模式）已被完整还原：

  L1  符号重命名            -> 3,364 个类型全量反编译
  L2  字符串加密            -> 运行时转储 7,806 / 7,806 条
  L3  程序集代码加密        -> 算法完整还原，15,380 个方法体解密
                               （keystream 由兄弟节区内容哈希派生 = 反篡改）
  L4  代码虚拟化（VM）      -> 三层全部击穿：
                               (a) RSA-2048 / PKCS#1 v1.5 封装层
                               (b) 位置相关流 XOR
                               (c) 自描述 Ascii85 方法令牌
                               => 722,260 字节 VM 字节码还原为可读明文
                                  （3,917 个成员记录）
  L5  自定义对称密码        -> TEA 变体（32-bit 分组 / 80-bit 密钥 / 12 轮 /
                               S-box 轮函数）+ 5 级级联 + DeriveBytes KDF

关键教训
  保护层强度与安全架构是两个正交维度。项目N 的保护强度在本案例库中最高，
  但架构层"裁决权在客户端"的缺陷依然完整存在。
  混淆只能提高分析成本，无法替代架构修正。

免责声明：
本项目仅供学术研究、安全审计与教学使用。严禁商业利用。
若该软件对您的工作产生了实际价值，请通过官方渠道购买正版许可。

包内文件：
  - README.txt                      双语文档（本文件）
  - build.ps1                       打包 + 脱敏扫描 + SHA256SUMS 生成
  - docs/reverse-engineering.md     完整逆向走查（保护层 / 授权架构 /
                                    CWE-602/287/863 分析 / R1-R5 验证 / 加固建议）
  - docs/protection-layers.md       保护栈技术细节（代码加密 keystream 派生、
                                    VM 三层还原算法、自定义密码规范）
  - tools/bx_patch.py               微创补丁工具（三档 profile，含逐点字节校验）

验证门禁（R1-R5）：全部 PASS（详见 docs/reverse-engineering.md §4）


===============================================================================
  脱敏策略说明 (Redaction Policy)
===============================================================================

本案例遵循工作台《脱敏分层原则》。下表明示哪些是占位符、哪些是实测原文：

| 层级 | 内容 | 处理 | 说明 |
|:---|:---|:---|:---|
| 散文 / 注释 / 文档文案 | 产品名 | **替换为 `项目N`** | 全部叙述性文字 |
| 产品名 / 可执行文件名 | `项目N.exe` | **替换** | 命令示例中的文件名 |
| 用户绝对路径 | `C:\Users\<user>\...` | **替换为相对路径** | 避免泄露本地目录结构 |
| 注册表路径 | `HKCU\Software\BoosterX` | **保留原文** | 删除后无法复现，属功能性必需 |
| 导入通道路径 | `HKCU\SOFTWARE\trampios\KEY` | **保留原文** | 同上 |
| 官方域名 | `reserve.boosterx.org` / `api.boosterx.org` | **保留原文** | 协议分析必需 |
| 资源键 / 方法名 | `ShowExperimentalTweaks` 等 | **保留原文** | 代码标识符，替换即失效 |
| 哈希 / 常量 | SHA-256、算法常量 | **保留原文** | 可复现性必需 |

> **判据**：删掉后**无法复现**的 → 保留；只是"读起来像产品名"的 → 替换。

===============================================================================
  INT0 RESEARCH GROUP // 项目N.v2.2.4.3.AuthBypass-INT0 // 2026
===============================================================================
