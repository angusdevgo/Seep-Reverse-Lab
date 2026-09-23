# 项目A 软件安全防护与加固设计规范 (Software Defense & Anti-Tamper Specification)

## 1. 背景与安全风险分析

在此前的安全分析与逆向验证中，目标软件（`项目A.exe` <目标版本>）暴露了以下几项典型的安全脆弱面：
1. **DLL 劫持风险 (DLL Search-Order Hijacking)**：
   - 程序直接静态链接微软基础库（如 `version.dll`），但未通过 `SetDefaultDllDirectories` 约束加载路径。在标准 Windows 搜索顺序下，程序根目录具备最高优先加载权，导致任意无签名的本地伪装 DLL 可劫持程序入口并抢先执行恶意载荷。
2. **代码段内存可变风险 (In-Memory Patching via VirtualProtect)**：
   - 进程未启用 Windows 原生安全缓解策略（`ProcessDynamicCodePolicy`），导致同进程注入代码或第三方模块可通过 `VirtualProtect` 任意将 `.text` 节的保护属性由 `PAGE_EXECUTE_READ` 更改为 `PAGE_EXECUTE_READWRITE`，无阻碍地实施热补丁覆写。
3. **函数入口易挂钩性 (Inline Trampoline / Hook Vulnerability)**：
   - 核心鉴权与许可范围构建函数（如 `0x8E6D83`、`0x8E75ED`）头部缺乏代码完整性校验与控制流防护（Control Flow Guard / CFG），易被 14 字节跳转跳板（`FF 25`）劫持，直接替换返回的 BSTR 字符串对象。
4. **单点返回值判定 (Single Point of Failure / Check Bypass)**：
   - 授权有效性过度依赖局部函数的返回值（如 `0x66DB7B` 返回 `0xFFFF` 即代表授权有效），未在核心功能流中嵌入非对称数字签名深度关联或基于密钥派生的加解密验证。

---

## 2. 纵深防御架构设计 (Defense-in-Depth Architecture)

针对上述攻击面，设计并实施三层防御加固体系：

```
                    ┌──────────────────────────────────────────────┐
                    │            Level 1: 启动与加载时防护        │
                    │  - 强制限定加载目录 (LOAD_LIBRARY_SEARCH_SYSTEM32)│
                    │  - 启用 Authenticode 签名与强完整性检查 (CI) │
                    └──────────────────────┬───────────────────────┘
                                           │
                                           ▼
                    ┌──────────────────────────────────────────────┐
                    │            Level 2: 运行时内核缓解策略       │
                    │  - 启用 ProcessDynamicCodePolicy (禁止改写可执行页)│
                    │  - 阻止未签名二进制注入 (SignaturePolicy)     │
                    └──────────────────────┬───────────────────────┘
                                           │
                                           ▼
                    ┌──────────────────────────────────────────────┐
                    │            Level 3: 内存完整性主动巡检       │
                    │  - 核心鉴权函数 Hash / 前导字节 (JMP/CALL) 巡检 │
                    │  - 内存页 VAD 保护属性动态监控 (PAGE_EXECUTE_READ)│
                    │  - 授权 Token 非对称数字签名与业务流强绑定    │
                    └──────────────────────────────────────────────┘
```

---

## 3. 防护技术细节与实现规范

### 3.1 目录白名单与 DLL 劫持免疫 (Anti-DLL-Hijacking)
- **API 规约**：在程序入口函数（`main` / `WinMain` / `DllMain`）的最起始位置调用：
  ```c
  SetDefaultDllDirectories(LOAD_LIBRARY_SEARCH_SYSTEM32 | LOAD_LIBRARY_SEARCH_USER_DIRS);
  ```
- **机制原理**：
  移除当前工作目录和应用程序根目录在未加限定 LoadLibrary 调用中的默认搜索权，所有系统 API 依赖均强制定向至受 Windows TrustedInstaller 保护的 `C:\Windows\System32`，使得同级目录下存放的伪造 `version.dll` 无法被主程序加载。

### 3.2 动态代码与内存保护缓解策略 (Dynamic Code Mitigation)
- **API 规约**：调用 Windows 8/10/11 原生内核缓解策略接口：
  ```c
  PROCESS_MITIGATION_DYNAMIC_CODE_POLICY policy = { 0 };
  policy.ProhibitDynamicCode = 1;
  SetProcessMitigationPolicy(ProcessDynamicCodePolicy, &policy, sizeof(policy));
  ```
- **机制原理**：
  在 Windows 内核层面锁定进程地址空间的 VAD 树（Virtual Address Descriptor）。一旦启用该策略，内核的内存管理器将拒绝任何将已有不可写代码页更改为可写（`PAGE_EXECUTE_READWRITE`）的 `VirtualProtect` 请求，也拒绝分配全新的 `PAGE_EXECUTE_READWRITE` 页面，从而彻底摧毁任何基于内存覆写的补丁技术。

### 3.3 核心敏感函数特征与完整性巡检 (Integrity Watchdog)
- **自检规则**：
  1. **前导机器码探测**：检查关键函数入口（前 16 字节）是否出现常见 Inline Hook 跳板机器码：
     - `0xE9` (JMP rel32)
     - `0xFF 0x25` (JMP [rip + disp32] / 绝对间接跳转)
     - `0xCC` (INT 3 软件断点)
     - `0xEB` (JMP rel8)
  2. **内存保护状态校验**：通过 `VirtualQuery` 确保函数所在页面的当前保护属性严格保持为 `PAGE_EXECUTE_READ`（`0x20`）。若发现属性异常（如变为 `0x40` PAGE_EXECUTE_READWRITE），即表明页面曾被修改。
  3. **哈希校验**：对静态编译后各敏感函数的核心代码块计算散列并与只读常量对比。

### 3.4 鉴权令牌与数字签名深度耦合 (Cryptographic Licensing Coupling)
- **改进设计**：
  1. 废除以明文 BSTR 直接拼接许可人、密钥和有效期限的松散结构。
  2. 采用 ECDSA / Ed25519 或 RSA-PSS 对授权结构体 `(LicenseeName, Key, Scope, Expiration)` 进行集中数字签名。
  3. 关于对话框在渲染时，仅接受验签通过的证书数据；若签名不匹配，界面强制显示未激活状态，杜绝单点改写内存全局指针即可伪造界面的风险。

---

## 4. 落地与自测验证场景 (Verification Matrix)

| 编号 | 测试场景 | 预期防御反应 | 验证指标 |
| :--- | :--- | :--- | :--- |
| **V-01** | 在主程序目录投递 `version.dll` 尝试劫持 | 系统忽略本地伪装 DLL，直接载入 System32 对应模块 | `GetModuleFileName(hModule)` 恒为系统路径 |
| **V-02** | 注入代码尝试对代码段调用 `VirtualProtect(..., PAGE_EXECUTE_READWRITE)` | 内核拒绝修改保护属性，API 返回 `FALSE` 并置 `GetLastError() = ERROR_DYNAMIC_CODE_BLOCKED` | 内存修改失败，触发违规异常 |
| **V-03** | 模拟外部注入工具在核心鉴权函数写入 `FF 25` 跳板 | 内存完整性自检模块检测到入口指令被篡改 | 自检函数返回 `TAMPER_DETECTED`，主程序采取安全退出策略 |
