# 项目I 授权校验算法

> 来源：`项目IX64.dll`（X64）/ `项目IA64.dll`（ARM64），<目标版本>
> 证据：Ghidra headless 反编译（`cases/20260901-项目I-keygen/exports/`，迁移版以
> 本仓库 docs 描述为准；地址均指 <目标版本> 样本）。

## 1. 常量

| 常量 | 值 | 位置 |
|---|---|---|
| RSA modulus n | `c3a6cca1…63ce79`（1016 bit！） | X64 file 0xA3160 / A64 0xB1FB0，CNG `RSAPUBLICBLOB` |
| RSA e | `0x10001` | 同上（cbPublicExp=3） |
| CONST | `4e9934f69c3fd8c3e8502a2fd1ab89c2e78671d38a9b97ba313f5eaba6fd420f` | .rdata VA 0x1800A3E90（64 hex） |
| MAGIC | `SABALL` | 验证函数立即数（0x41424153/0x4C4C 小端） |
| 默认机器码 A/B | `xxxx xxxx` / `yyyy yyyy` | FUN_180001a90/FUN_180001b9c 失败回退 |

## 2. 本地要素

```
md5hex(x)            = MD5(x) 的 32 字符小写 hex      （FUN_180001a20: BCryptHash MD5 → %02x×16）
LicenseHash          = md5hex(key)                    （key = License 键默认值，长度 > 0x1E 才迁移）
A（磁盘序列号）      = PhysicalDrive0 IDENTIFY/SMART 序列号（word-swap），失败保持 "xxxx xxxx"
B（SMBIOS UUID）     = GetSystemFirmwareTable('RSMB') Type1 UUID，失败保持 "yyyy yyyy"
R（请求串）          = LicenseHash + md5hex(A) + md5hex(B)   （96 hex，Ordinal_103）
```

## 3. 签发（服务器侧，需私钥 d）

```
P = R[:32] + ( CONST | R[32:96] ) + "SABALL" + pad(0x00)   # 128 字节
sig = P^d mod n
ActivationData = base64(sig)   → HKCU|HKLM\Software\项目I\License\ActivationData (REG_BINARY)
```

## 4. 验证（FUN_180001e8c，本地）

```
P' = base64decode(ActivationData)^e mod n        # BCryptImportKeyPair + BCryptEncrypt
for o in 0..0x1b:                                 # 滑动窗口，步长 1
    P'[o:o+32]   == LicenseHash
    and ( P'[o+32:o+96] == CONST                      # 通用要素
          or (P'[o+32:o+64]==md5hex(A) and P'[o+64:o+96]==md5hex(B)) )  # 机器绑定
    and P'[o+96:o+102] == "SABALL"
→ 任一窗口命中即"已激活"（Ordinal_102 返回 1 且 out[0]='1'）
```

## 5. 试用判定（Ordinal_100/101）

- 首装时间戳 = `HKCU\...\Explorer\CLSID\{md5hex("项目I"+PINGROUP)-1-31-9}` 键的
  最后写入时间（PINGROUP 为 CPU 拓扑派生组串）
- 试用 100 天；系统时间早于键时间戳或年 ≥ 2028 时跳过过期判定（容忍时钟回拨）

## 6. keygen 可行性

- key 不含可本地自洽校验的校验段（对比 项目F 的 19 字符校验串）——**算号器路线不成立**
- 最终要素需 `d`；n=1016bit（弱，最低质因子 2663）但 q1(1005bit) 未分解——现实中不可伪造
- 因此本工具走：本地要素复现 + `Ordinal_102` 验签入口补丁（激活态注入）+ 防回退
