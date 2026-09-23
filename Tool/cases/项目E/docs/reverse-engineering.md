# 逆向方法论：从 EXECryptor 混合授权体系到激活补丁

本文记录 项目E 注册校验机制从三态体系到可交付补丁的完整逆向路径。

## 1. 样本概况

- 分发形式：Inno Setup 安装（`<本地路径> 安装目录，含 `unins000.exe`）
- 主程序：`项目E.exe`，PE32+ x64，原生 C++，MSVC 19.50.35227
  （VS2026 工具链），6,451,848 字节，Authenticode 签名
- 配套组件：`项目EHelper.exe`（授权运行时，474,720 字节）、
  `项目E.cpl`、`PinToTaskbar.exe`、`languages\*.xml`
- 版本：<目标版本>；SHA256 `<实测哈希>`
- PDB：`<本地路径>
  本地不可得，Ghidra 以 FUN_xxxx 命名）

## 2. 保护机制（EXECryptor 混合授权）

| 层 | 载体 | 机制 | 判定 |
|---|---|---|---|
| 授权 SDK | Helper | EXECryptor 授权运行时：序列号绑定机器码（RSD），验签实现被 VM 虚拟化（`FUN_0046ef97` VM stub，反编译为不可执行伪码） | 无 keygen 路径 |
| 在线核验 | Helper | `verify.php` @ `项目E.license-manage.com`（`verify_php_sender.h` 源码路径泄露） | 激活必须联网 |
| IPC | 主程序↔Helper | 共享内存 `Global\项目EHelper_Memory`(0x200B) + 事件 `EventSent/EventComplete` + 互斥体 `Local\UTOOL`；XML 明文请求，JSON 响应 | 可观测协议 |
| 注册表存储 | 主程序 | `HKCU\Software\项目E Software\项目E`，值名 RN/RC（许可证）、VH/VL（版本戳）、RF/RL（试用时间戳，XOR 编码） | 可读写 |
| 时间防护 | 主程序 | 试用 30 天（`0x1e`）、时钟回拨检测（`CLCK MVD BCK`/`CLCK DS LT {}`）、首次运行戳（`FirstRun`/`SetFirstRunTime`） | 可绕过（注册后不生效） |

未加壳：DiE 无 packer、各节 entropy 正常（overlay 高熵为签名数据）——
**保护重点不在代码加密而在授权体系设计**。

## 3. 静态还原步骤

1. **triage**：`triage_pe`（hash/DiE/entropy/节表/导入）+ `rz-bin -zz` 字符串全量落盘
   （102,259 行）。命中 `license.dat`、`RegName`/`SerialNum`、`Software\项目E
   Software\项目E`、`msgRegFailed`、`项目E.license-manage.com`、
   `VerifySerialNumberW`、`CLicenseManager::*`——一次锁定全部线索。
2. **导入面**：Reg* 全套（ADVAPI32）+ WININET/WS2_32 网络面 + CRYPT32 Cert*
   （仅 HTTPS 链验证）+ CryptGenRandom；**无 MD5/SHA/对称加密 API** →
   排除本地密码学校验假设。
3. **Ghidra headless**（6.4MB / 15,366 函数，300s+ 分析）：
   - 字符串 xref 反查函数（自制 `scripts/misc/ghidra_summary_query.py --by-string`）
   - `VerifySerialNumberW` 封装（FUN_140009e60）：构造 XML 请求 → 共享内存 →
     解析 JSON `result/ExpiryMonth/ExpiryYear/LicType/UserParam`
   - `CLicenseManager::Activate`（FUN_1400320d4）：result!=3 → "key was not
     accepted"；成功 → 写 RN/RC + 内存状态 + LicType 归一
   - `CLicenseManager::CheckRegistration`（FUN_1400329c4，完整反编译 40,130 字符）：
     启动判定 + 试用期 + 时钟防护
   - 完整反编译导出：`scripts/_shared/ghidra/DumpFunctionsDecompile.java`
     （summary 内置 preview 仅 5,000 字符，大函数需二次导出）
4. **字节级定位**：rizin 反汇编 `FUN_140009db0`，确认 `mov eax,edi` 返回路径与
   `call atoi` 位置（0x140009E0F）；Python 扫 .text 找 CC 填充区（0x140001622）。
5. **动态验证**：patch 副本 → 与 Helper 同目录运行（Helper 是必需组件，主程序启动
   失败会 TerminateProcess）→ 主窗口 `项目E <目标版本>` 正常（hwnd 枚举）；
   注册表写入 RN/RC 后被读取。

## 4. 补丁交付

见 `docs/algorithm.md` §3。工具链三层复用：

```
python scripts/windows/uninstall_tool_patch.py        # 独立复现（含 --verify）
src/Patcher.cs（C# 镜像实现，纯字节数组，可单测）      # 工具内嵌
tests/test_tool.cs（模拟 PE + 真实样本断言）           # 构建自检 ALL PASS
```

## 5. Open Questions

- Helper 的 `FUN_0046ef97`（VM stub）背后是纯本地验签还是先本地后在线——
  动态抓包可进一步确认 verify.php 调用频度（激活时 vs 每次启动）。
- 便携版激活通道（license.dat + LicType 998/999）未覆盖。

## 6. 环境备注

- bash 作业对象会在命令结束时终止其启动的 GUI 进程：动态观察须在**单次命令内**
  完成"启动→检查→枚举"。
- 本机系统事件流量过大，Procmon PML 大窗口导出 CSV 受限（见
  `exports\windows\procmon\README.md`），已用静态反编译 + 注册表实测等价取证。