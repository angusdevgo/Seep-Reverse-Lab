---
id: "pe-reverse/10-license-keygen/08-cross-version-aob-migration"
title: "跨版本 AOB 特征码迁移与双态修补"
title_en: "Cross-Version AOB Signature Migration & Dual-State Patching"
summary: >
  针对软件小版本更新导致代码段非均匀位移、硬编码偏移全部失效的场景，给出从单版本偏移表
  迁移到跨版本 AOB 特征码表的完整方法：滑动汉明距离定位位点、多版本共同稳定区生成特征码、
  双态（原始态/已补丁态）唯一性校验、相邻位点合并、COMDAT 折叠陷阱规避，以及 PE 结构门禁、
  版本感知备份、差异字节白名单等防写坏工程保障。
summary_en: >
  A complete workflow for migrating hardcoded-offset patch tables to cross-version AOB signature
  tables when minor releases shift code unevenly: sliding Hamming-distance site location, common
  stable-region signature generation across multiple versions, dual-state (original/patched)
  uniqueness validation, adjacent-site merging, COMDAT-folding pitfalls, plus PE-structure gating,
  version-aware backup and changed-byte whitelisting to guarantee the target is never bricked.
board: "pe-reverse"
category: "10-license-keygen"
signals:
  - "硬编码偏移失效"
  - "跨版本补丁"
  - "代码位移"
  - "非均匀位移"
  - "重编译"
  - "特征码迁移"
  - "多版本特征码"
  - "重定位指针"
  - "COMDAT 折叠"
  - "无条件截断"
  - "ERROR_BAD_EXE_FORMAT"
  - "不是有效的 Win32 应用程序"
  - "回滚点错版"
  - "陈旧备份"
mcp_tools:
  - triage_pe
  - ghidra_headless_analyze
  - ghidra_summary_functions
keywords:
  - "AOB migration"
  - "cross-version patch"
  - "Hamming distance"
  - "dual-state signature"
  - "relocation pointer"
  - "COMDAT folding"
  - "PE checksum"
  - "version-aware backup"
  - "特征码迁移"
  - "汉明距离"
difficulty: "advanced"
tags:
  - "license-patching"
  - "signature-scanning"
  - "version-migration"
  - "binary-patching"
  - "safety-gating"
language: "zh-CN"
last_updated: "2026-09-26"
related_articles:
  - "pe-reverse/01-triage/01-aob-signature-scan"
  - "pe-reverse/10-license-keygen/02-validation-function-location"
  - "pe-reverse/08-patch/01-code-patching"
---
# 跨版本 AOB 特征码迁移与双态修补

## 场景

已有一套**基于硬编码绝对偏移**的补丁表（例如「18 个位点 / 31 字节」），在目标软件的小版本更新后：

- 补丁位点全部错位 → 部分命中、部分失配
- 若补丁工具还带**无条件截断**逻辑，则直接把 PE 映像写坏
- 用户侧表现为：`Win32Exception 0x80004005 指定的可执行文件不是此操作系统平台的有效应用程序`（Win32 错误 193 / `ERROR_BAD_EXE_FORMAT`）

此时需要把偏移表**迁移为跨版本鲁棒的 AOB 特征码表**。

## 输入信号

- 已有旧版本的完整补丁位点清单（偏移 + 期望字节 + 补丁字节）
- 拿到新版本的同一目标二进制
- 现象：模式一/三失败，模式二（不碰二进制）正常 → **强烈指向二进制被写坏**

---

## 一、 先判性质：重编译 vs 重写

**不要**直接开始迁移，先判定版本差异性质。按节区做「相同偏移逐字节一致率」统计：

| 节区 | 典型观测 | 含义 |
|---|---|---|
| `.rsrc` | 100% 相同 | 资源未变 |
| `.data` | 95%+ 相同 | 数据段未变 |
| `.rdata` | 30–40% 相同 | 常量/导入表局部变动 |
| `.text` | **5–10% 相同** | 看似重写，实为位移 |

`.text` 一致率极低**不等于**重写。验证手段：对比节区**起始 128 字节**：

```
旧版 @0x400: 8B 44 24 04 83 F8 50 77 13 ... E9 F3 F9 20 00 E9 26 FA 20 00 C3
新版 @0x400: 8B 44 24 04 83 F8 50 77 13 ... E9 03 FC 20 00 E9 36 FC 20 00 C3
                                            └─ 仅 E9 rel32 目标不同 ─┘
```

跳转目标差值 = `.text` 的 VSize 增长量 ⇒ **代码整体位移**。

### 位移曲线绘制

以 64 字节窗口、4KB 步长，在 `±0x8000` 范围内搜索最佳匹配：

```python
for off in range(text_start, text_end, 0x1000):
    win = old[off:off+64]
    pred = off + prev_shift
    pos, dist = best_in_range(new, pred-0x8000, pred+0x8000)
    shift = pos - off
```

**关键结论**：小版本更新的位移**非均匀**（实测在 `−896 ~ +64` 之间跳变）。

> ⚠️ **架构推论**：固定偏移迁移方案在跨版本时**必然失效**，必须改用特征码扫描。

---

## 二、 位点迁移：滑动汉明距离

### 2.1 方法

以旧版本位点为中心取 **64 字节窗口**，在新版本上做**滑动汉明距离**，取距离最小者：

```python
idx  = np.arange(lo, hi)[:, None] + np.arange(WIN)[None, :]
dist = (A11[idx] != win[None, :]).sum(axis=1)
best = lo + int(dist.argmin())
```

**判据**：64 字节窗口下随机匹配的期望汉明距离 ≈ **62**；实测命中距离 **1–6** ⇒ 置信度极高。

### 2.2 反例警示：不要用分块哈希建全局偏移映射

用「分块哈希 + 唯一性 + 单调性」建 b10→b11 全局映射，实测产出 `+1,755,424` 这种**荒谬位移** —— 大二进制中重复块导致误锚定，单调性过滤也拦不住。

> **滑动汉明距离直接逐点定位更可靠**，且天然给出置信度（距离值）。

### 2.3 位点字节校验

迁移后必须校验位点处字节仍等于期望值：

```
旧 0x2D7BD  新 0x2D45D  位移 −864  汉明 2  字节 85 == 85  ✓
```

---

## 三、 特征码生成：多版本共同稳定区

### 3.1 生成规则

1. 以位点为中心，**向左右扩展**，只保留**所有已采集版本中完全一致**的字节；
2. 生成**双态特征码**：
   - **原始态**：含期望字节
   - **已补丁态**：含补丁字节
3. **双态唯一性**校验：两份特征码在所有版本的「原始态 / 已补丁态」中均须**唯一命中**。

### 3.2 陷阱一：单版本特征码会混入重定位指针

用 **单版本** 生成特征码，在第三版本上 **13/14 命中**，失败的那条：

```
版本 A 特征码右扩展 4 字节: 38 83 69 00
版本 B 同位置:              30 83 69 00     ← 重定位指针，差 8
```

**修正**：改用**三版本**共同稳定区 → 该点右扩展自动归零。

> **规则**：特征码扩展必须要求该字节在**所有已采集版本**中一致，否则会把版本相关的重定位指针、地址常量纳入特征码。

### 3.3 陷阱二：相邻位点必须合并

数据段两个位点相距仅 **4 字节**：

```
0x378CDC  01 00 00 00        ← 试用状态标志
0x378CE0          1E 00 00 00 ← 试用天数常量（30 天）
```

拆成两条时**特征码互相包含** → 唯一性校验必然失败。
**修正**：合并为单条 8 字节条目：

```
01 00 00 00 1E 00 00 00   →   00 00 00 00 FF FF FF 7F
```

### 3.4 陷阱三：COMDAT 折叠导致函数序言不可用作锚点

MSVC 链接器会把**相同模板实例**的 SEH 作用域表折叠，导致两个不同函数的**函数序言逐字节相同**：

```
守护线程 D      @0x7CA50: 6A FF 68 9C 8D 66 00 64 A1 00 00 00 00 50 81 EC C4 01 00 00 ...
看门狗关联函数   @0x834E0: 6A FF 68 9C 8D 66 00 64 A1 00 00 00 00 50 81 EC C4 01 00 00 ...
                          └──────────── 完全相同 ────────────┘
```

**后果**：这两个位点**无法依赖函数序言**定位（序言相同会双命中），只能靠**左侧前一个函数的尾部字节**锚定 —— 其中一条特征码仅 **14 字节**。

> **规避**：对这类位点，向左（前一个函数尾部）或向右（函数体内非重定位区）扩展足够长度，并**在回归测试中固化该特征码**，一旦未来版本失效会立即暴露。

### 3.5 统计参考

- 总字节数 **755**，平均 **53.9 字节/位点**
- 最短 14 字节，最长 118 字节

---

## 四、 语义验证：反汇编交叉印证

用 capstone 对每个位点做**多版本指令序列比对**（归一化掉地址与跳转目标）：

```python
md = Cs(CS_ARCH_X86, CS_MODE_32); md.syntax = CS_OPT_SYNTAX_INTEL
insns = [i.mnemonic + " " + i.op_str for i in md.disasm(data[foff:foff+24], va)]
```

### 最有价值的印证：全局地址咬合

```
授权分支:
  call dword ptr [0x694004]
  85 C0  test eax, eax        ← 补丁点
  0F 85  jne 0x2E180
  mov byte ptr [ebp-0xAB1], 1

试用期计算:
  mov eax, dword ptr [0x779CDC]   ; RVA 0x379CDC → 文件偏移 0x378CDC
  and eax, 0xF                    ; ← 补丁点
  add eax, 0xF                    ; ← 补丁点
  mov dword ptr [0x779CE0], eax   ; RVA 0x379CE0 → 文件偏移 0x378CE0
```

**代码段指令引用的两个全局地址，恰好落在数据段两个补丁点的文件偏移上** —— 三点语义完全咬合，证明分析无误。

> 换算公式：`文件偏移 = 节区 RawPtr + (VA − ImageBase − 节区 VA)`

**多版本结论**：若三版本的指令序列（归一化后）完全一致，说明**授权校验逻辑零变更**，差异仅为代码位置平移与重定位地址。

---

## 五、 防写坏工程保障

### 5.1 PE 结构门禁（必须前置）

解析 PE 头，**动态**求出一切关键偏移，替代硬编码：

```
e_lfanew   = DWORD @ 0x3C
Optional   = e_lfanew + 24
CheckSum   = Optional + 0x40
DataDir[4] = Optional + 0x60 (PE32) / 0x70 (PE32+)
ImageEnd   = max(节区 RawPtr + RawSize)
```

**校验**：MZ / PE 签名 / 节区边界 / `RawPtr + RawSize ≤ 文件长度`。
**任一不合法 → 立即拒绝**（这正是 `ERROR_BAD_EXE_FORMAT` 的判据）。

### 5.2 安全截断（替代硬编码目标大小）

**错误做法**：

```csharp
const int TARGET_FILE_SIZE = 6189056;   // 单版本专属常量
if (data.Length > TARGET_FILE_SIZE)
    Array.Resize(ref data, TARGET_FILE_SIZE);   // 其它版本必被写坏
```

**正确做法**：只剥离「**超出 `ImageEnd` 且长度 == `SecuritySize`**」的 Authenticode 尾部。

### 5.3 PE 校验和标准化

补丁与截断**完成后**，用微软标准算法重算：

```python
def pe_checksum(data, off):
    t = 0
    for i in range(0, len(data)-1, 2):
        w = 0 if (off <= i < off+4) else (data[i] | (data[i+1] << 8))
        t += w; t = (t & 0xFFFF) + (t >> 16)
    while t > 0xFFFF: t = (t & 0xFFFF) + (t >> 16)
    return (t + len(data)) & 0xFFFFFFFF
```

> **反直觉发现**：流传的原版 Crack 写入的校验和 `0x005F0BEA`，经穷举（4 种输入状态 × 16 种算法变体）**无法被任何标准算法复现** —— 是无效值。
> 而官方原版的校验和与标准算法 **100% 吻合**。
> 它能工作 ⇒ 目标程序与 Windows **均不校验该字段**。仍应写入**正确值**。

### 5.4 版本感知备份（升级后回滚点错版）

**缺陷**：仅在备份不存在时创建 → 用户升级后，遗留备份属**上一版本**：

- 回滚点指向错误版本
- 「一键还原」把**旧版主程序盖到新版安装上**（主程序与依赖库版本错配）

**策略**：

| 情形 | 处理 |
|---|---|
| 备份不存在 | 直接备份 |
| 备份版本 == 当前版本 | 保持不变 |
| 备份版本 ≠ 当前版本，当前为纯净原版 | 旧备份归档为 `<exe>.BAK.<旧版本>`，写入新备份 |
| 备份版本 ≠ 当前版本，当前已含补丁 | **拒绝继续** |

并为「一键还原」加入**版本一致性守卫**。

> 💥 **实测价值**：该守卫在回归测试中当场拦下一次真实事故 —— 测试误触真实安装目录时，正是它阻止了旧版本主程序覆盖新版本安装。

### 5.5 原子写入 + 三级回滚

```
写前建 .rollback.tmp
  → 写入前 PE 终检
    → 写临时文件
      → 落盘后复读并重新解析 PE
        → 失败自动回滚
```

### 5.6 差异字节白名单（回归测试核心断言）

产物相对原版的**每一个差异字节**，必须落在「补丁位点 ∪ PE 校验和 ∪ 签名目录」内：

```csharp
HashSet<int> expected = ...;   // 全部预期改动偏移
foreach (int o in diffs)
    if (!expected.Contains(o)) → 判定「意外改动」，测试失败
```

---

## 攻击链

```
1. 判性质      节区一致率矩阵 + 起始 128 字节 → 重编译 vs 重写
2. 绘位移曲线   4KB 步长 + ±0x8000 搜索 → 确认非均匀位移
3. 迁位点      64B 窗口滑动汉明距离（距离 ≤8）→ 新偏移 + 置信度
4. 校字节      位点处字节 == 期望值
5. 生特征码    N 版本共同稳定区 → 双态（原始/已补丁）特征码
6. 验唯一      双态在所有版本 × 两状态中均唯一命中
7. 反汇编印证  capstone 多版本指令序列比对 + 全局地址咬合
8. 加固         PE 门禁 + 安全截断 + 校验和重算 + 版本感知备份 + 原子回滚
9. 回归         端到端 × 全版本 + 幂等 + 差异白名单 + 负向用例
```

## MCP 工具映射

| 攻击链步骤 | MCP 工具 | 说明 |
|---|---|---|
| 版本差异初筛 | `triage_pe` | hash / 节区 / 导入 / 字符串，判断是否加壳与节区布局 |
| 位点语义确认 | `ghidra_headless_analyze` | 反编译定位授权校验函数，确认位点语义 |
| 多版本函数对齐 | `ghidra_summary_functions` | 按名/地址定位函数，交叉核对位点归属 |

## 证据与验证闭环

- 记录**全部**目标版本的 SHA256、体积、官方 PE 校验和、节区 RawPtr/VSize。
- 位点迁移必须给出**汉明距离**作为置信度证据（≤8 可用，>12 需重新逆向）。
- 特征码必须给出**双态唯一性命中数**（必须恒为 1）。
- 产物必须通过：PE 结构合法 + 校验和自洽 + AOB 复扫全表已补丁态 + 差异字节 ⊆ 白名单。
- 负向用例必须验证**零写入**：节区截断 / 特征码不符 / 空文件 / 非 PE → 全部拒绝且文件字节不变。
- 回归测试须验证**对真实系统零副作用**（注册表与进程快照前后一致）。
