# 2026-08-06 Cortex-M 虚拟磁盘升级固件的自带掩码旋转/XOR 封装

## 场景分类

二进制 / 固件逆向

## 目标概述

分析一份 Cortex-M 调试工具升级包，识别其自定义封装算法，并区分升级包中的应用映像与设备内驻留的 USB Mass Storage bootloader。

## Scope 摘要（脱敏）

- auth_basis: own_system
- network_profile: authorized_target_only（实际为本地离线样本）
- asset_types: [firmware_container, cortex_m_application, usb_msc_updater]

## 角色

- lead_role: lead
- specialists: [cre, cce, doc]

## 完整执行链路

1. 对原包做长度、熵、尾部周期和分块统计，发现文件大小是 1 KiB 的整数倍，尾部具有 7 字节周期。
2. 从 Cortex-M 向量表约束出发，枚举单字节旋转/XOR 关系，先恢复第一个块。
3. 发现每个 1 KiB 块会重置旋转相位，并且块首密文字节可直接作为该块 XOR 掩码。
4. 用 `P[i] = ROR8(C[i], (3*i) mod 7) XOR C[0]` 解码每块，并用逆变换逐字节重建原包。
5. 用第二份同系列官方固件交叉验证：相同格式恢复出合法向量表、版本字符串和可读代码；所有块首明文字节均为零。
6. 通过向量目标地址与文件偏移反推出应用基址，确认升级包没有包含前置 bootloader。
7. 结合官方“进入 bootloader / 模拟 U 盘”说明，重建 MSC 文件复制到 Flash 写入的外部流程，并把 bootloader 内部细节标为推断。
8. 对尾部 32 位字段测试常见 CRC、STM32 硬件 CRC、Adler 与累加，未匹配，保留为未解决完整性字段。

## Evidence 链摘要（脱敏）

| E-id | source_type | 可复用命令模式 | 关联 Finding |
|---|---|---|---|
| E-001 | local_binary | 分块熵、周期尾、向量约束 | F-001 |
| E-002 | derived_algorithm | 块首掩码 + ROR/XOR + round-trip | F-001 |
| E-003 | static_analysis | 向量、字符串、Thumb 反汇编 | F-002 |

## Finding / Path 摘要

- top_finding: 部分高熵固件包只是按 1 KiB 重置的自带掩码 ROR/XOR 混淆，不应过早归类为标准加密。
- path_type: solve/callflow
- path_one_liner: 周期与分块结构 → 向量表 crib → 首块恢复 → 块边界重置 → 第二固件交叉验证 → 应用/bootloader 边界 → MSC 升级外部流程。

## 踩坑记录

| 问题 | 原因 | 解决方案 | 耗时 |
|---|---|---|---|
| 先用每块“解旋后众数字节”作为掩码，少数块仍有乱码 | 文本密集块的最常见明文字节不一定是零 | 比较块首字节模型；乱码消失并在第二固件复现 | 中 |
| 单一全文件 XOR/旋转只在开头有效 | 旋转相位和掩码每 1 KiB 重置 | 显式按 `0x400` 分块 | 低 |
| IDA 与 radare2 启动失败 | 本机无 IDA 路径，r2 bootstrap 安装器异常 | 使用 Python + Capstone 验证 Cortex-M 入口 | 中 |
| 看到 `firmware_crc32` 就假设末尾是标准 CRC32 | 字符串是元数据键，不能证明包尾参数与覆盖范围 | 系统排除常见族后保留未知，不强行命名 | 低 |

## 工具链发现

- Python 适合做按位变换枚举、round-trip 和跨样本不变量验证。
- Capstone 足以在缺少 IDA/Ghidra/radare2 时验证 Cortex-M 向量入口与局部控制流。
- 字符串恢复质量是比较候选掩码模型的强信号，但必须结合绝对指针和反汇编，避免只凭“看起来可读”。

## 关键算法

```text
block_size = 0x400
mask = packed_block[0]
rotation(i) = (3 * i) mod 7
plain[i] = ROR8(packed[i], rotation(i)) XOR mask
```

逆变换用 `ROL8`；验证标准是编码结果与原包逐字节相同。

## 对本包的改进建议

- 在 firmware-pentest 的容器识别阶段加入“分块边界是否重置周期”的检查。
- 当启发式零字节 crib 在少数块失败时，优先测试块首/块尾的自描述掩码。
- 对“升级包只含应用”的情况，报告必须把 bootloader 内部行为与协议层必然行为分开标注。

## 可复用的模式

1. 先按常见 Flash/传输块大小（256、512、1024、2048、4096）检查周期是否重置。
2. 用 Cortex-M 的 SRAM 栈指针和 Thumb Reset Vector 作为强 crib。
3. 对每个候选模型执行三个验证：全文件 round-trip、第二样本复现、绝对地址引用一致。
4. 尾部字段未匹配常见校验时，不要把变量名或字符串当作算法证据。

## 进化动作

- [x] 新增了 field-journal 记录
- [x] 更新了 field-journal 索引
- [ ] 更新了路由矩阵
- [ ] 更新了 tool-index
- [ ] 更新了 bootstrap-manifest
- [ ] 更新了子 skill 文档

## 环境信息

- OS: Windows
- 工具版本: Python 3.12, Capstone 5.0.6
- 目标平台/版本: Cortex-M3 / F1 兼容 MCU，应用区固件

## 脱敏检查

- [x] 无真实域名、IP、凭证、token、PII
- [x] 无本地绝对路径
- [x] 无样本文件本体和样本哈希
- [x] 厂商、产品与版本信息已泛化
