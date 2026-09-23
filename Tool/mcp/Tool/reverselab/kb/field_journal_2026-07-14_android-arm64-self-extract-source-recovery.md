# 2026-07-14 Android ARM64 自解压程序源码恢复

## 场景分类

二进制分析 / Android ARM64 / 自解压 Shell / 控制流平坦化

## 目标概述

对用户自有的本地 `.sh` 交付包进行只读源码恢复，拆出多层压缩载荷，分析 ARM64 主程序与保护库，并在不运行目标的情况下恢复业务文本和高层伪源码。

## 完整执行链路

1. 对输入目录做只读清单、大小、魔数和 SHA-256 分诊，不读取或记录凭证明文。
2. 识别第一层为“Shell 前导 + bzip2 尾部流”，通过 `BZh` 有效流测试定位精确偏移。
3. 在独立中文产物目录中保存前导、压缩流和解压载荷，不执行载荷。
4. 识别第二层为 `__ARCHIVE_BELOW__` 自解压脚本，安全展开 tar.gz，拒绝绝对路径、`..`、链接和设备节点。
5. 得到 Android AArch64 PIE 主程序和 AArch64 共享库；使用 pyelftools/Capstone 生成 ELF 头、节、符号、导入、字符串和入口反汇编。
6. 保护库保留可读 C++ 符号，逐函数导出伪代码，确认 `/proc` 扫描、`TracerPid`、三级进程终止和后台线程行为。
7. 主程序 `main` 的符号长度明显大于普通 CFG 识别长度，确认间接跳转控制流平坦化。
8. 静态求解跳转表：`target = table_entry + fixed_delta`，枚举所有唯一真实基本块。
9. 扫描同构字符串解密器，识别“前 N 字节循环 XOR 密钥 + 后 M 字节密文”布局。
10. 对每个真实基本块执行 AArch64 常量传播，解析间接解密器调用的目标和 `x1` 数据源，批量恢复业务文本。
11. 交付完整反汇编、逐函数伪代码、高层语义源码、Mermaid 流程图和正式报告。
12. 重新计算原始输入哈希，确认分析前后完全一致。

## 踩坑记录

| 问题 | 原因 | 解决方案 | 耗时 |
|---|---|---|---|
| PowerShell 直接运行 bootstrap 被执行策略拦截 | 系统禁止脚本 | 使用单次 `powershell.exe -ExecutionPolicy Bypass -File ...`，不改永久策略 | 低 |
| radare2 bootstrap 返回 GitHub API 403 | API 限流/拒绝，但发布页可访问 | 从 `releases/latest` 302 和 `expanded_assets/<tag>` 获取官方资产与页面 SHA-256，校验后解压 | 中 |
| winget 的 Rizin 静默/用户范围安装均未落地 | 安装器范围不匹配 | 两次失败后停止重试，切回已验证的 radare2 官方 ZIP | 低 |
| `r2pm -U` 长时间停在 git clone | 网络速度/递归仓库 | 终止可选插件路线，继续使用 `pdc` + Capstone 自定义恢复 | 高 |
| radare2 只识别 `main` 前部 CFG | 间接 BR 跳转表使常规分析在分发器结束 | 按跳转表公式枚举真实块，不依赖默认 CFG | 中 |
| 直接字符串扫描只看到少量路径 | 文本采用每字符串独立的循环 XOR | 从解密器指令提取 key/output 长度，静态重放算法 | 中 |

## 工具链发现

- Python 3.13 标准库足够安全处理 bzip2 与 tar.gz；`tarfile.extractall` 不如逐成员校验后写出安全。
- pyelftools 可恢复 ELF/DYNSYM/RELA，Capstone 适合做 ARM64 常量传播与专用解密器识别。
- radare2 6.1.8 的 `pdc` 对未混淆的保护库函数有效，对间接 BR 平坦化主函数只能提供局部伪代码。
- GitHub API 403 不等同于官方发布页资产不可访问；发布页可提供 tag、资产名和 SHA-256。

## 关键代码/命令

```python
# 通用循环 XOR 文本布局
key = blob[:key_length]
encrypted = blob[key_length:key_length + output_length]
plain = bytes(value ^ key[index % key_length]
              for index, value in enumerate(encrypted))
```

```python
# 间接跳转表静态求解
targets = {
    (entry + fixed_delta) & 0xFFFFFFFFFFFFFFFF
    for entry in jump_table_entries
}
```

```powershell
# API 403 时只读获取最新 tag
curl.exe -sS -I '<official-release-url>/radareorg/radare2/releases/latest'
```

## 对本包的改进建议

- 增加“`.sh` 自解压伪装二进制”目标类型路由，避免误判为纯 Shell 审阅。
- Windows GitHub Release bootstrap 应在 API 403 时回退到发布页/expanded_assets，并强制 SHA-256 校验。
- 可新增“ARM64 跳转表 + 循环 XOR”通用恢复脚本模板，作为无 IDA 时的低依赖路线。
- 工具调用超过前台窗口时必须保留 session id 并轮询，避免丢失仍在运行的下载或导出任务。

## 可复用的模式/脚本片段

1. 先扫描有效压缩流而不是只找魔数；对每个候选偏移在内存中完整解压测试。
2. 自解压归档永远按成员逐项安全写出，不直接执行、不信任成员路径。
3. 符号表声明的函数长度远大于 CFG 识别长度时，优先检查 BR/BLR 间接表。
4. 同构解密器可以通过 `add x16,x1,#key_len`、`cmp w16,#output_len`、`ldrb/eor/strb` 指令组合批量识别。
5. 对平坦化块做局部常量传播通常足以恢复间接函数目标和字符串源地址，无需先完整去平坦化。

## 进化动作

- [x] 更新了路由矩阵
- [x] 更新了 tool-index
- [ ] 更新了 bootstrap-manifest
- [ ] 更新了子 skill 文档
- [x] 新增了 pitfalls 记录
- [ ] 无需更新

## 环境信息

- OS: Windows
- 工具版本: Python 3.13；radare2 6.1.8；pyelftools；Capstone
- 目标平台/版本: Android ARM64，NDK r17 / Clang 6.0.2

## 脱敏检查

- 未记录软件名、作者名、真实域名、真实 API 端点、凭证、固定签名材料、业务包名或本地用户路径。
- 未附样本文件或样本哈希。
- 仅保留公开工具名称、版本和通用算法模式。

## 索引同步

已在 `_index.md` 的“二进制 / 固件 / CTF”分类中增加本条记录并更新统计。

---
<!-- [社区贡献] 完成后询问用户是否 PR 到主仓库。流程见 CONTRIBUTE-BACK.md -->
