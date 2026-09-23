# 逆向过程记录（项目I <目标版本>）

> 完整过程见工作区 case 目录（不随本仓库发布）；本文保留可复现的方法论与关键命令。

## 1. Triage → Unpack

```text
diec.exe setup.exe          → PE64 / Authenticode / SFX: 7-Zip
7z l  setup.exe             → 60 files（Cfg/shell DLL/Loader/DarkMagic/UpdateCheck）
7z x  -osamples/unpacked/…  → 全量载荷
```

setup.exe 是 7-Zip SFX（归档偏移 0x14000），导入表无网络/加密 API——授权逻辑全在组件内。

## 2. 字符串定位

```bash
strings -a -n 5 项目IX64.dll   # 'SIBActivation: mismatch; expected…'、CONST 64hex、
                                      # 'Software\项目I\License'、'LicenseHash'
strings -el -n 5 项目ICfg.exe  # activate.php / sibsab.php / SIBActivated / 试用文案 / sabtask.xml
rz-find -s "RSA1"                     # 公钥 blob（CNG RSAPUBLICBLOB 布局解析）
```

## 3. Ghidra headless

```bash
analyzeHeadless.bat <projdir> 项目ILab -import 项目IX64.dll -overwrite
analyzeHeadless.bat <projdir> 项目ILab -process 项目IX64.dll -noanalysis \
  -scriptPath scripts/_shared/ghidra -postScript SabFindActivation.java out.c
```

脚本思路（`SabFindActivation.java`）：枚举 DefinedData 命中关键字 → 收集引用函数 →
批量反编译落盘；`SabDecompileByAddress.java` 按地址补漏（Ordinal_100/101/103、机器码函数）。

## 4. 关键还原点

| 结论 | 依据 |
|---|---|
| LicenseHash = md5hex(key) | FUN_180001d24：默认值>0x1e → md5hex → 写 LicenseHash、删默认值 |
| 机器码 A/B | FUN_180001a90（0x2D1400 SMART + 0x560000 回退，word-swap）；FUN_180001b9c（'RSMB' Type1 UUID） |
| 请求串 96 hex | Ordinal_103：lstrcpy/lstrcat 三段拼接 |
| 验证滑窗 | FUN_180001e8c：栈变量 Ghidra 切分陷阱——local_b8/local_98/local_78/iStack_58/asStack_54 实为同一 128B 输出 P' |
| CNG blob 布局 | RSA1|BitLength|cbPublicExp=3|cbModulus=128|cbPrime1=0|cbPrime2=0（非 CryptoAPI RSA1） |
| 弱模数 | n bit_length=1016；pollard rho 命中 2663；sympy factorint q1 无 <1e6 因子 |

## 5. 动态验证

- ctypes `GetProcAddress(dll, ordinal 102)` 直接调 patched DLL：ret=1、out[0]='1'
- explorer 重启×2 后模块重载 + 状态保持；reg before/after diff 记录激活态键
- hosts/UAC 在实验沙箱受限，提供脚本与程序化两条路径

## 6. 防回退

见 README「防回退机制」与 `SabRollbackGuard.cs` 注释中的触发点→抑制映射表。
