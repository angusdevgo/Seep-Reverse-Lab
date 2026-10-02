# 项目N — 保护层技术细节与还原算法

> 本文记录 Eazfuscator.NET 全保护模式在 项目N 上的具体表现与完整还原方法。
> 目标版本：v2.2.4.3（.NET Framework 4.x）

---

## 0. 保护层清单

| 层 | 保护手段 | 作用 | 还原方式 |
|:--|:---|:---|:---|
| L1 | 符号重命名 | 类型/方法/字段名替换为不可读标识符 | ILSpy 直接反编译 |
| L2 | 字符串加密 | 字符串常量运行时解密 | 调用客户端自身解密器转储 |
| L3 | **程序集代码加密** | 目标节区整体 XOR，密钥由其它节区内容哈希派生 | 静态复现 keystream 派生算法 |
| L4 | **代码虚拟化** | 关键方法编译为自定义字节码，内置解释器执行 | 三层分离还原 |
| L5 | 自定义对称密码 | 业务数据通道加密 | 完整算法复刻 |
| L6 | 反调试 / 反 Dump | 运行时环境检测 | 未构成有效阻断 |

---

## 1. L2 — 字符串加密还原策略

**问题**：字符串解密器自身被控制流混淆（大量 `if (0 == 0) {}` 死代码、
`_ = N; if (M == 0) {}` 噪声），静态还原成本高。

**策略**：**不静态还原解密器，改为运行时反射调用客户端自身的解密方法。**

```
1. 反射加载原版程序集
2. 定位字符串解密入口（静态方法，签名：string Decrypt(int id)）
3. 遍历 id 空间 [0, N)，逐条调用并记录
4. 输出 id → 明文 的映射表（7,806 条）
```

**优势**：绕过全部控制流混淆，结果 100% 准确。

**注意**：所有变体程序集的**标识相同**（同名同版本），
因此**每个样本必须用独立进程验证** —— 同进程内 `Assembly.LoadFrom`
会返回已加载的实例，导致结果误判。

---

## 2. L3 — 程序集代码加密

### 2.1 加密流程（构建期）

```
1. 遍历 PE 节表，计算每节名前 8 字节（两个 uint32）之积
2. 选定一个节作为目标（本项目实测 product == 0x65452714）
3. 以「其它非空节区」的内容逐 dword 演化 4 个状态字（内容哈希）
4. 由状态字展开 16 项 keystream
5. 对目标节区逐 dword 做 XOR，并自反馈推进 keystream
```

### 2.2 关键常量

| 项 | 值 |
|:---|:---|
| 目标节区识别 | `0x65452714`（节名前 8 字节两 u32 之积） |
| 种子初值 | `1758353659, 186699061, 1283470176, 872273121` |
| keystream 反馈常数 | `1204611781` |

### 2.3 反篡改属性

keystream 由**其它节区的内容**决定 ⇒ 改动 `.text` / `.rsrc` 等节区会导致
目标节区**解不开**。这是 Eazfuscator 的完整性自校验机制。

**但实测未观察到"解不开即拒绝运行"的逻辑** —— 校验失败时程序仍会继续，
只是行为异常。**建议厂商将此处改为 Fail-Closed。**

### 2.4 微创补丁的关键性质

keystream 的推进使用**明文**：

```
plain      = cipher ^ ks[i & 15]
ks[i & 15] = (ks[i & 15] ^ plain) + FEEDBACK     ← 用 plain，不是 cipher
```

因此加密方向与解密方向可用**同一函数**（仅输出不同），
从而可以做到"**解密 → 改几个字节 → 加密回写**"，
产出的文件**除补丁点外与原文件逐字节一致**，最大程度降低被反篡改发现的概率。

---

## 3. L4 — 代码虚拟化（三层分离还原）★

### 3.1 架构总览

```
资源（754,692 B）
  │
  ├─ 第 1 层：RSA-2048 / PKCS#1 v1.5 逐块解密
  │      n = a1(128B) ‖ base64解码(128B)；e = 65537
  │      块 256 B，明文 245 B/块（PKCS#1 固定 8 字节填充）
  │
  ├─ 第 2 层：位置流 XOR
  │      plain[i] = cipher[i] ^ (byte)(seed ^ i)
  │      seed = seedArg ^ (-559030707)
  │
  └─ 第 3 层：方法寻址（名称 → 偏移）
```

### 3.2 第 1 层：RSA 封装

**构造**：

```
byte[] n = a1(128B) ‖ Convert.FromBase64String(内嵌字符串)(128B)
BigInteger modulus = new BigInteger(1, n)
RSAKeyParameters key = new RSAKeyParameters(false, modulus, 65537)
RSAEngine rsa = new RSAEngine(new PKCS1Encoding(key))
```

**验证**：2,948 个块**全部**通过 PKCS#1 v1.5 校验，且每块填充长度**恰好为 8**
（`00 02 ‖ 8×非零 ‖ 00 ‖ 245B`）—— 构建期固定分块策略的铁证。

> **注意**：由于只有公钥，无法自行**重加密**。
> 若要修改 VM 字节码，需替换公钥为自己的密钥对（见 §3.5）。

### 3.3 第 2 层：位置流 XOR

解密流类（继承自定义 Stream 基类）：

```csharp
// 构造
this.seed = seedArg ^ -559030707;

// 单字节解密
byte DecryptByte(byte b, uint pos)
{
    byte k = (byte)((uint)this.seed ^ pos);
    return (byte)(b ^ k);
}

// Read：pos 取自底层流的当前位置（绝对偏移）
int Read(byte[] buf, int off, int count)
{
    uint pos = (uint)this.Position;
    int got  = this.stream.Read(buf, off, count);
    for (int i = off; i < off + got; i++)
        buf[i] = DecryptByte(buf[i], pos + (uint)(i - off));
    return got;
}
```

**等价 Python**：

```python
seed = (1822868938 ^ (-559030707 & 0xFFFFFFFF)) & 0xFFFFFFFF   # 0xB20B1B87
plain[i] = cipher[i] ^ ((seed ^ i) & 0xFF)
```

**效果**：熵 `7.9997 → 6.7565`，可打印串 `6,161 → 7,107`。

### 3.4 第 3 层：方法寻址（名称即自描述令牌）

每个虚拟化方法在托管侧都有一个**存根**：

```csharp
public bool SomeProperty
{
    get {
        object[] a = new object[1] { this };
        return (bool)VM.Instance.Dispatch(VM.Stream, "<不可读令牌>", a);
    }
}
```

**令牌不是随机串，而是方法在 VM 流中偏移的编码。**

**完整链条**：

```
令牌字符串
  ├─(1) Ascii85 解码
  │      字母表 '!'(33)..'u'(117)，5 字符 → 4 字节大端，'z' 为全零组
  │      K = {52200625, 614125, 7225, 85, 1}   (= 85⁴ .. 85⁰)
  │
  ├─(2) 位置流 XOR 解密（seedArg = 1485391981）
  │
  ├─(3) 乱序 ReadInt64
  │      low  = (a7<<8) | (a2<<24) | a0 | (a1<<16)
  │      high = (a5<<24) | (a6<<16) | a4 | (a3<<8)
  │      value = (high << 32) | low
  │
  └─(4) → VM 流偏移 → 方法记录
```

**可逆性**：XOR 解密后的 8 字节恰为**偏移的小端字节的置换**：

```
a[0]=b0, a[7]=b1, a[1]=b2, a[2]=b3, a[4]=b4, a[3]=b5, a[6]=b6, a[5]=b7
（b = 偏移.to_bytes(8, 'little')）
```

⇒ 可对**任意偏移生成合法令牌**，且能**逐字节复现原始令牌**。

> **攻击含义**：虚拟化方法的调用目标由一个短字符串决定。
> 改写该字符串即可把调用**重定向到任意虚拟化方法** —— 不需要私钥，也不需要还原 ISA。

### 3.5 方法记录格式与 ISA

```
+0x00  18 字节记录头（签名 / 类型描述）
+0x12  [1 字节长度][方法名 ASCII]
+…     [u32 代码长度][代码区]
```

指令为 **4 字节定长 token**，操作码被随机化重排。已识别：

| token | 推断语义 | 证据 |
|:---|:---|:---|
| `0x42487a8f` | `ret` | 几乎所有方法的**最后一条** |
| `0x5d914689` | `ldarg.0` / `ldfld` | 12 字节方法的首条；也出现在属性 getter 第 2 条 |
| `0xb4f09a23` | `ldarg.0`（引用型 this） | 引用类型方法首条 |

**典型 12 字节「常量 getter」样例**（3 token = load; load; ret）：

```
89 46 91 5d | XX XX XX XX | 8f 7a 48 42
```

### 3.6 若需修改 VM 字节码：公钥替换路径

由于只有公钥（无法重加密），完整改写 VM 字节码需：

1. 自行生成 RSA-2048 密钥对 `(n_own, e=65537, d_own)`；
2. 替换 `a1`（128 B FieldRva，位于加密代码节区 → 可用 L3 补丁能力改写）；
3. 替换内嵌 base64 字符串（**长度恰好等长**，可等长替换）；
4. 用 `d_own` 重加密改写后的 VM 字节码（245 B 分块 + PKCS#1 v1.5）；
5. 原地覆写资源（**大小完全一致**）。

> 该路径所需的全部能力（代码节区补丁、等长字符串替换、资源覆写）均已具备。

---

## 4. L5 — 自定义对称密码

### 4.1 算法参数

| 项 | 值 |
|:---|:---|
| 分组 | 32-bit |
| 密钥 | **80-bit** |
| 模式 | ECB / 无填充 |
| 轮数 | **12** |

### 4.2 轮函数（S-box 混淆查表）

```
输入：key[10], sum, v(16-bit)
hi = v >> 8;  lo = v & 0xFF
b5 = S[lo ^ key[(4·sum + 0) % 10]] ^ hi
b7 = S[b5 ^ key[(4·sum + 1) % 10]] ^ lo
b8 = S[b7 ^ key[(4·sum + 2) % 10]] ^ b5
b9 = S[b8 ^ key[(4·sum + 3) % 10]] ^ b7
返回 (b8 << 8) | b9
```

其中 `S` 为 256 字节 S-box（由 FieldRva 初始化）。

### 4.3 轮调度

```
encrypt: delta = +1, sum = 0
decrypt: delta = -1, sum = 23

for i in 0..11:
    v1 ^= F(key, sum, v0) ^ sum;  sum += delta
    v0 ^= F(key, sum, v1) ^ sum;  sum += delta
```

### 4.4 5 级级联

```
SymmetricAlgorithm[5]
for i in 0..4:
    cipher = new CustomTEA()
    cipher.Key = deriveBytes.GetBytes(cipher.KeySize / 8)   // 10 B
    cipher.IV  = deriveBytes.GetBytes(cipher.BlockSize / 8) //  4 B
    cascade[i] = cipher

// KDF
new DeriveBytes(password, salt, iterationCount: 1)
```

---

## 5. 工具链索引

| 工具 | 作用 |
|:---|:---|
| `tools/bx_patch.py` | 微创补丁（三档 profile，含补丁点字节校验） |
| 代码节区解密器 | L3 keystream 派生 + 逐 dword 解密 |
| VM 位置流解密器 | L4 第 2 层还原 |
| VM 寻址复算器 | L4 第 3 层还原 + 可逆编码器 |
| 运行时探针 | 反射调用客户端自身 `HashName` / VM 派发器 |
| 字符串转储器 | L2 还原（7,806 条） |

---

*本文档仅供安全研究与防御架构教学使用。*
