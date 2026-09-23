# 企业级纵深防御加固体系（厂商修复标准指南）

> 来源：softseep 主控 §三 | 加载时机：输出修复建议 / 加固方案时


针对上述走查出的 CWE-602 与内存打桩脆弱性，厂商应当实施的四层纵深加固标准：

### 第一道防线：DLL 劫持免疫（加载期封锁）
在主程序入口函数（`WinMainCRTStartup`）第一行代码调用：
```c
SetDefaultDllDirectories(LOAD_LIBRARY_SEARCH_SYSTEM32 | LOAD_LIBRARY_SEARCH_USER_DIRS);
```
彻底将程序目录从默认搜索链中移除，使伪造的 `version.dll` 无法被加载器映射。

### 第二道防线：内核级动态代码抑制（运行时封锁）
```c
PROCESS_MITIGATION_DYNAMIC_CODE_POLICY policy = { 0 };
policy.ProhibitDynamicCode = 1;
SetProcessMitigationPolicy(ProcessDynamicCodePolicy, &policy, sizeof(policy));
```
在内核 VAD 树层面禁止将 `.text` 等只读节重新修改为可写，任何 `VirtualProtect` 均直接抛出错误码 487。

### 第三道防线：只读节完整性与 Inline Hook 巡检
通过独立守护线程随机巡检关键函数头：
- 检测页面属性是否偏离 `PAGE_EXECUTE_READ (0x20)`；
- 检测前导机器码是否出现 `0xE9`、`0xFF 0x25`、`0xCC` 等打桩跳板。

### 第四道防线：业务强绑定非对称数字签名（逻辑层根治）
彻底废除“根据明文标志位或单点布尔函数判断特权”的设计，引入 ECDSA / Ed25519 非对称加密数字签名。核心特权票据 `(UserID, Expiration, Features)` 由服务端私钥下发签名，客户端在业务干道上直接解密校验，杜绝内存改写绕过。

### 第五道防线：输出 API 动态取址 + IAT 完整性自检
针对显示层文案伪造与 IAT 类挂钩：
- 对易被用于文案伪造的 User32 输出 API（`SetDlgItemTextW` / `SetWindowTextW` 等）改为 `LoadLibrary` + `GetProcAddress` **动态取址**，绕过 IAT 槽位；
- 启动时对自身 IAT 做一次快照（记录每个 External 槽位的预期地址是否落在对应系统 DLL 的映像区间内），在敏感流程（关于对话框、鉴权判决）前做一次比对；
- 敏感对话框文案改由**自绘（Owner-Draw / Direct2D）**渲染而非依赖系统控件，并对内存中的授权状态与展示文案做**内部一致性互验**。

---
