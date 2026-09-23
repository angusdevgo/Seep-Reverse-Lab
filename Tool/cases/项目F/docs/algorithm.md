# 项目F Pro 许可证校验算法原理

> 目标函数：`项目F.Core.Pro.LicenseChecker.CheckLicense(string email, string license)`
> 版本覆盖：项目F 6.3 / V7 Beta（两版本算法逐字节一致，仅混淆类名/token 不同）

## 1. 常量

```csharp
const string CHARSET    = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"; // 32 字符，剔除 0/1/I/O
const string SALT       = "项目Fl047YpyZUU5M";
const int    LICENSE_LEN = 192;   // 密钥总长度
const int    CHECK_POS   = 160;   // 校验串起始位置
const int    CHECK_LEN   = 19;    // 校验串长度
```

- 密钥是 192 字符的 Base32 风格字符串（字符集 32 个，5 bit/字符）
- **只有 `license[160:179]` 这 19 个字符被校验**，其余 160 + 13 字符任意

## 2. 校验流程

```
bool CheckLicense(email, license):
  1. email/license 非空，且 license.Length == 192
  2. email = email.ToLowerInvariant()
  3. v = (H1(email) << 64) | (H2(email) << 32) | H3(email)   // 96 位校验值
  4. for i in 0..18:
       result += CHARSET[(v >> (96 - (i+1)*5)) & 31]        // 19 个 5-bit 组
  5. if license[160:179] != result: return false
  6. h = MD5Hex(email + SALT)
  7. if BLACKLIST.Contains(h): return false                  // 6 个硬编码哈希
  8. return true
```

## 3. 三个哈希函数（自定义、无标准库对应）

### H1（多项式滚动哈希）
```
h = 0
for c in email: h = (h * 43 + ord(c)) mod 2^32
```

### H2（ELF 风格）
```
h = 0
for c in email:
    h = ((h << 4) + ord(c)) mod 2^32
    g = h & 0xF0000000
    if g != 0:
        h ^= (g >> 24)
        h ^= g
```

### H3（4 轮移位异或）
```
h = 0
for r in 0..3:
    for j in range(r, len(email), 4):
        h ^= (ord(email[j]) << ((r*8) % 32)) mod 2^32
```

## 4. 黑名单

`MD5Hex(email + SALT)`（小写 hex）命中以下 6 个硬编码哈希即拒绝（用于封锁已知泄露/破解邮箱）：

```
710ab287938947d40d8d5857f663753c
c109e3ee2bd74d5b88de647eebc2fd0e
1229667d8ecc0616bffd7740c4323f9a
b05744004c455956e5408a9b1c95b047
57a39722f37db4727e0f425156f3b2d7
0c16a79693d8d58e1e5b81f48f9ba64b
```

## 5. 校验串构造（Keygen 核心）

第 3 步已经证明：**校验串完全由 email 决定**。因此构造密钥：

```
license = 随机160字符 + CHARSET[(v >> (96-(i+1)*5)) & 31]（i=0..18, 19字符） + 随机13字符
```

- 随机部分取 `CHARSET` 内任意字符即可（未被校验）
- 随机邮箱命中黑名单概率可忽略（黑名单仅 6 个具体哈希）

## 5.1 完整工作示例（可亲手验证）

以 `test@项目F.com` 为例，逐步演算完整校验串：

```
1. 邮箱小写: test@项目F.com（16 个字符）

2. 三个哈希（uint32 溢出）
   H1 = 0x9F55B47B  (多项式 x43 滚动)
   H2 = 0x00EEF05D  (ELF 风格)
   H3 = 0x13070B6E  (4 轮移位异或)

3. 拼接 96 位校验值（H1 占高位，H3 占低位）
   v = 0x9F55B47B00EEF05D13070B6E   （24 个十六进制字符 = 96 bit，逐位紧凑无空隙）

4. 96 位布局（从最高位 bit 95 开始）

   H1 32bit      H2 32bit      H3 32bit
   ┌────────────┬────────────┬────────────┐
   │ 9F55B47B    │ 00EEF05D    │ 13070B6E    │
   └────────────┴────────────┴────────────┘
   bit 95        63           31           0
   ↑ v >> (96-(i+1)*5) 从高位向低位切 5 bit

5. 19 组 5-bit 切片 → 查 32 字符表

   i  bits范围   idx  字符     i  bits范围   idx  字符
   1  [91,96)   19   M       11  [41,46)   24   S
   2  [86,91)   29   X       12  [36,41)    5   7
   3  [81,86)   10   C       13  [31,36)   26   U
   4  [76,81)   27   V       14  [26,31)    4   6
   5  [71,76)    8   A       15  [21,26)   24   S
   6  [66,71)   30   Y       16  [16,21)    7   9
   7  [61,66)   24   S       17  [11,16)    1   3
   8  [56,61)    0   2       18  [ 6,11)   13   F
   9  [51,56)   29   X       19  [ 1, 6)   23   R
   10 [46,51)   27   V

6. 校验串（19 字符）:
   MXCVAYS2XVS7U6S93FR

7. 构造完整密钥:
   [0:160] 160 个随机字符（取 CHARSET 任取）
   [160:179] 校验串 MXCVAYS2XVS7U6S93FR
   [179:192] 13 个随机字符（取 CHARSET 任取）
```

读者可用任意语言复算（Python 3 约 20 行）：哈希函数逐个字节模拟 ≡ 上表数值（另见 §7 交叉验证）。

## 6. 弱点分析（为什么可以 Keygen）

| 弱点 | 说明 |
|---|---|
| 校验信息仅 95 bit 且无签名 | 19×5 bit 校验串由 email 哈希推导，无 RSA/公钥签名，可离线构造 |
| 173/192 字符不校验 | 头部 160 与尾部 13 字符任意，只用于外观 |
| 校验与 email 单向绑定 | 换邮箱即换校验串，但 email 由用户自由选择 |
| 黑名单规模极小 | 仅 6 个哈希，任意自有邮箱即规避 |
| 离线激活路径 | 选项页本地 `CheckLicense` 通过即写设置并置 `IsPro=true`，无需联网 |

## 7. 参考实现

- C#：`src/LicenseAlgo.cs`（本仓库，`Generate`/`Verify`/`Checksum`）
- Python 参考实现：`项目F_keygen.py`（社区传播的独立实现，与本仓库逐字符交叉验证一致）

> 交叉验证方法：固定 email → C# 与 Python 分别输出校验串 `license[160:179]` → 逐字符比对。
> 注意 C# 移植陷阱：96 位值无法放入 `ulong`（移位量按 mod 64 处理，`<<64` 等于 `<<0`），
> 必须使用 `BigInteger` 拼接；批量生成需共享随机源（`new Random()` 同 tick 同种子）。