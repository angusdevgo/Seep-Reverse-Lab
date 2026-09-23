# 项目E 注册校验机理与补丁原理

> 目标组件：`项目E.exe`（主程序，x64 原生 C++，MSVC 19.50）+
> `项目EHelper.exe`（EXECryptor 授权运行时，共享内存 IPC 服务）
> 版本：项目E <目标版本>（2026-08 构建，SHA256 `93cfbeaa...d48229`）

## 1. 结论先行

项目E 的注册校验是 **EXECryptor 授权运行时验签 + 激活时在线核验** 的
混合体系，**不存在可从本地还原的纯算号器路径**：

- 序列号（SerialNum）由 EXECryptor SDK 生成，**绑定机器码签名**，验签私钥在
  项目E 侧；验签逻辑位于 `项目EHelper.exe` 内且被 **EXECryptor VM
  虚拟化**（`FUN_0046ef97` 为 VM stub，静态不可还原）。
- 激活时主程序经 Helper 向 `项目E.license-manage.com/verify.php` 做在线核验
  （源码路径 `<本地路径> 泄露组件名），
  服务器返回 `result` / `ExpiryMonth` / `ExpiryYear` / `LicType` / `UserParam`。

因此本仓库交付 **patch 版一键激活工具**（主程序判定改写 + 注册表写入），而非算号器。

## 2. 校验流程（主程序侧判定链）

```
注册对话框(FUN_14002da88)
  → CLicenseManager::Activate(FUN_1400320d4)        0x1400320D4
      → VerifySerialNumberW 封装(FUN_140009e60)     0x140009E60
          → ExecuteXMLRequest(FUN_140009290)        0x140009290
              共享内存 Global\项目EHelper_Memory
              → Helper 分发循环(Helper FUN_00405f7d)
                  → VerifySerialNumber 实现（EXECryptor VM + verify.php）
              ← JSON { "result": 0|2|3, "ExpiryMonth":.., "ExpiryYear":..,
                       "LicType":.., "UserParam":.. }
      → IsRegistered 查询封装(FUN_140009db0)         0x140009DB0
          （同样走共享内存，返回 json["result"]）
  [result == 3] → 成功分支：
      写注册表 HKCU\Software\项目E Software\项目E
        RN = 注册名（值名 0x14039bc1c，L"RN"）
        RC = 注册码（值名 0x14039bc24，L"RC"）
      内存状态 param_1+0x170/0x178= 注册名/码，param_1+0x188 = LicType（0→归一为 1）
  [else] → "activation: the key was not accepted" → 失败提示（msgRegFailed）

启动检查 CLicenseManager::CheckRegistration(FUN_1400329c4)
  注册表 RN/RC 非空 → 同上 VerifySerialNumberW + IsRegistered → result==3 → 已注册
  RN/RC 为空 → SecureReadW（EXECryptor 加密存储，键名 RegName/SerialNum，legacy 通道）
  均无 → 试用期：RF/RL（0x14039bb30/38，XOR 编码时间戳）→ 30 天倒计时（0x1e 天）
        + 时钟回拨检测（"CLCK MVD BCK" / "CLCK DS LT {}" / _atoi64）
  末尾 FUN_140009270 启动 Helper，失败 → TerminateProcess（Helper 是必需组件）
```

## 3. 补丁原理（IsRegistered 恒 3）

`FUN_140009db0` 是**唯一**的注册状态判定源，被 CheckRegistration（2 处）与
Activate（2 处）复用。函数尾 `mov eax, edi` 返回 `json["result"]`。
把其中 `atoi(json["result"])` 的调用点重定向到 stub 即可令 result 恒为 3：

```
0x140009E0F  E8 B4 4A 2D 00   call 0x1402DE8C8      ; atoi(json["result"])
0x140009E0F  E8 0E 78 F9 FF   call 0x140001622      ; -> stub
0x140001622  B8 03 00 00 00   mov eax, 3
0x140001627  C3               ret
```

副作用分析：

| 调用方 | 原行为 | patch 后 | 风险 |
|---|---|---|---|
| Activate（对话框提交） | result!=3 → 拒绝 | 恒成功，写 RN/RC + LicType=1 | 无 |
| CheckRegistration（启动） | 未注册 → 试用期逻辑 | 恒已注册；RN/RC 为空时注册名显示空 | 需先用工具写 RN/RC |
| 便携版检查（FUN_1400347f4） | 需 LicType 998/999 | 安装版路径不受影响 | 便携版不适用（见 README） |
| Helper 在线核验 | 激活时联网 | 主程序不再依赖其返回值 | Helper 仍可联网（可选 hosts 屏蔽） |

## 4. 弱点分析

1. **判定集中**：result==3 的最终仲裁全部在主程序侧完成，Helper 只提供"服务"，没有
   独立推送注册状态的能力（或至少主程序不信任它的主动状态）——单点改写即可覆盖
   对话框与启动两条路径。
2. **局部变量先清零后归一**：`local_478`（LicType 输出）在调用验证前被
   `memset(0, 0x16)` 清零，验证"失败"时 LicType=0 → 自动归一为 1（单机授权），
   因此 patch 后无需额外修补 LicType。
3. **值名混淆但可枚举**：注册表值名使用短混淆名（RN/RC/VH/VL/RF/RL），由 .rdata
   常量直接引用，可被静态枚举。
4. **Helper 共享内存协议**：`Global\项目EHelper_Memory` + 命名事件 +
   `Local\UTOOL` 互斥体，明文 XML 请求（方法名 `VerifySerialNumberW`/`IsRegistered`、
   字段 `Name`/`Serial`/`result`）——无认证/签名保护，可伪造请求（但 Helper 的
   验签实现被 VM 保护，伪造请求无助生成有效序列号）。

## 5. 覆盖范围与限制

- 仅覆盖安装版（Single Computer License 语义，LicType→1）。便携版需要独立的
  Portable license 与 license.dat 通道，本补丁不适用于便携版（README 已注明）。
- 补丁作用于 项目E.exe **副本**；Helper、语言包、其它组件不修改。
- 已知样本指纹：输入 `93cfbeaa...d48229` → 输出 `721bdb0b...`；其它版本
  需重新定位常量（脚本已按结构校验，非指纹匹配亦可应用）。

## 6. 复现

```bash
python scripts/windows/uninstall_tool_patch.py samples/windows/项目E.exe out\项目E-patched.exe
python scripts/windows/uninstall_tool_patch.py --verify out\项目E-patched.exe   # is_patched=True
```

C# 复现（零依赖）：

```powershell
powershell -ExecutionPolicy Bypass -File <本地路径>   # ALL PASS
.\tools\test_tool.exe  'E:\...\samples\windows\项目E.exe'            # 含真实样本断言
```