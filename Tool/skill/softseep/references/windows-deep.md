# Windows 深水区 —— exe-reverse 中文桥接层

> **本文件是 Seep 本地新增**。上游 `exe-reverse` 全部为英文且保持原样，
> 这里只做**中文意图 → 上游参考文件**的映射，不复制、不改写上游内容。
> 上游同步（`setup/sync-upstream.py`）不会触碰本文件。

---

## 0. 什么时候加载本文件

`softseep` 判型为 **平台=Windows**，且任务属于以下任一类时：

- 需要**改字节/打补丁**并证明补丁真的生效；
- 需要**跨版本**维持补丁（特征码/AOB）；
- 目标**有壳/被保护/虚拟化**，读不出代码；
- 目标是 **.NET / Unity IL2CPP / 打包 Python**（不是纯 C++）；
- 目标是**驱动/内核组件**；
- **所有 hook 都被检测**，需要硬件层观测；
- 需要**还原算法**（不只是定位分支）。

纯"会员怎么破/卡密怎么算"的**权威定性**仍先走 `softseep` 的 `AUTH-G0…G4` 前置门控；
本文件负责的是**机制层执行**。

---

## 1. 与 `windows-sop.md` 的分工（避免重复劳动）

| 文件 | 定位 | 语言 | 回答的问题 |
| :--- | :--- | :--- | :--- |
| `references/windows-sop.md` | **交付流水线**（6 步） | 中文 | 这个任务怎么从头做到尾、怎么验收 |
| **`exe-reverse/references/*`**（本文件桥接） | **机制字典 + 可执行引擎** | 英文 | 这一步底层到底在发生什么、凭什么判定 |

**执行顺序**：`windows-sop.md` 定流程 → 遇到机制疑问 → 按本文件第 2 节落到具体上游参考文件。

---

## 2. 中文意图 → 上游参考文件（唯一权威映射）

| 用户大白话 / 症状 | 上游文件（`Tool/skill/exe-reverse/`） | 配套脚本 |
| :--- | :--- | :--- |
| 改字节 / 补丁 / 校验和不匹配 / 补丁写了但没生效 | `references/patching.md` | `scripts/pepatch.py` |
| 特征码 / AOB / 这版能用下版还能用吗 | `references/aob-and-signatures.md` | `scripts/aob_scan.py` |
| 有壳 / 节区熵异常 / 导入表空 / 字符串消失 | `references/protectors-and-packers.md` | `scripts/pe_triage.py` |
| 程序自校验 / 改完就退出 / 签名校验 | `references/integrity-checks.md` | — |
| 一个几千行 switch / 控制流平坦化 / VMP / dex2c 类比 | `references/virtualization-and-flattening.md` | `scripts/trace_reduce.py` |
| 算法形状清楚但常数看不到 / 需要解方程 | `references/algorithm-recovery.md`、`references/symbolic-execution.md` | `scripts/trace_reduce.py --prove` |
| .NET / C# / 混淆 / 反编译名字全丢 | `references/managed-dotnet.md`、`references/dotnet-decompilation.md` | — |
| Unity 游戏 / IL2CPP / `global-metadata.dat` / `GameAssembly.dll` | `references/unity-il2cpp.md` | — |
| Flutter 桌面端 / `data/app.so` | `references/flutter-and-dart-aot.md` | `scripts/dart_snapshot_strings.py` |
| PyInstaller / Nuitka / pyarmor / `python3xx.dll` / `_internal` | `references/python-runtime-bundles.md` | — |
| 驱动 / `.sys` / 内核组件 / 用户态工具够不着 | `references/kernel-and-drivers.md` | — |
| 反调试 / 附加就崩 / 延迟自毁 / 时间到就退出 | `references/anti-analysis.md` | — |
| 所有 hook 都被检测 / 要无侵入观测 | `references/hardware-tracing.md` | `scripts/gate_probe.js` |
| 虚拟机里调试不了 / VBS/HVCI 占着调试寄存器 | `references/hypervisor-observation.md` | `scripts/hwprobe.py` |
| 会员/授权到底谁说了算 | `references/license-mechanisms.md`、`references/network-activated-licensing.md` | — |
| 两个版本行为不一样 / 补丁迁移 | `references/pe-diff-and-versions.md` | `scripts/pe_diff.py` |
| 同一份 exe 在另一台机器上结果不同 | `references/cpu-vendor-divergence.md` | — |
| 函数序言不像 C/C++ / 调用约定对不上 / 跳板崩 | `references/assembly-idioms.md`、`references/compiler-fingerprints.md` | — |
| 工具输出太长读不完 | `references/toolchain.md` | `scripts/fold.py` |
| 不知道这技能覆盖到哪 / 能不能承诺 | `references/coverage-and-limits.md` | — |
| 准备发布成果 / 写报告 / 截图 | `references/desensitization.md` | `scripts/scan_leaks.py` |
| 任务跑长了，不确定已经证明了什么 | `references/long-task-discipline.md` | — |
| 结果很怪 / 修好了但现象还在 | `references/pitfalls.md` | — |
| 需要总索引 | `references/routing.md` | — |

---

## 3. 三条强制纪律（Windows 侧）

### 3.1 先探主机（`EXE-G2`）
```
python Tool/skill/exe-reverse/scripts/doctor.py
```
- 未探主机就假设"有 IDA / 能提权 / 不是虚拟机"，会把**宿主问题误判成目标行为**；
- 缺工具是**结论**（"本机没有这条路线"），不是可以绕过的许可。

### 3.2 等长补丁 + 校验和 + 回读（`O3`）
```
# 先 dry-run 看落点
python scripts/pepatch.py target.exe --at-rva 0x1010 --expect "48 8B 05" --bytes "90 90 90" --out out.exe --dry-run
# 再落盘；脚本自动重算校验和并逐字节回读
python scripts/pepatch.py target.exe --at-rva 0x1010 --expect "48 8B 05" --bytes "90 90 90" --out out.exe
```
- 改变长度 = 结构性编辑（会移动后续所有偏移），默认拒绝；
- **输入只读**，永远输出到新文件。

### 3.3 未验证不得声称完成（`done` 六条）
"能启动" ≠ "功能变了"；"日志干净"不是证据。
见 `references/verification.md`。

---

## 4. 与 Seep 现有能力的协同

| 场景 | 组合 |
| :--- | :--- |
| 静态读代码 | `exe-reverse` 定路线 → `ida-reverse` / `seep_r2_*` MCP 执行 |
| 动态定位 | `exe-reverse/references/dynamic-debugging.md` → x64dbg / Frida |
| 知识库检索 | `seep_kb_search`（reverselab 294 篇）先查方法论 |
| 授权定性 | 先 `softseep` 的 `AUTH-G0…G4`，再进本技能 |
| 补丁交付验收 | `MANUAL/POC-VALIDATION.md` 三阶段闭环 |

---

## 5. 上游不覆盖（不要过度承诺）

`references/coverage-and-limits.md` 摘要：
- **服务器权威**决策 —— 客户端改不动，属路线判定；
- 通用全自动**脱虚拟化器** —— 不提供；
- 具名**商业壳的产品级破解**承诺 —— 不提供；
- 本仓库**未实测**的 Windows 构建上的保证 —— 不承诺。

> `unknown` ≠ `不存在`；"我没找到" ≠ "它不在"。
