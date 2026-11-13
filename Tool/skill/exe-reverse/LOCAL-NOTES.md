# exe-reverse × Seep Lab —— 本地接入说明（LOCAL-NOTES）

> 本文件是 **Seep Lab本地新增**，不属于上游仓库。
> 上游 `SKILL.md` / `references/` / `scripts/` **保持原样不修改**，因此
> `setup/sync-upstream.py` 对 `Tool/upstream/exe-reverse` 的同步始终是纯拷贝、零漂移。

---

## 1. 它是什么，与 softseep / apkseep 的分工

| 层 | 技能 | 职责 |
| :--- | :--- | :--- |
| **总控 / 判型** | `softseep` | G-Auth 授权门、平台判型、类型判型、路由分发、Windows 6 步交付流水线、九型项目范式 |
| **平台执行层（Windows）** | **`exe-reverse`（本技能）** | PE 机制字典 + 可执行引擎：PE 结构、等长补丁、AOB 签名、完整性校验、壳/保护、虚拟化、.NET、IL2CPP、Python 打包、内核驱动、硬件追踪、符号执行 |
| **平台执行层（Android）** | `apkseep` | APK/DEX/SO 全链路、脱壳、重打包、Frida |

一句话：**`softseep` 决定"打不打、往哪打"，`exe-reverse` 决定"具体怎么打、怎么证明打对了"。**

`softseep/references/windows-sop.md` 是**交付流水线**（6 步，中文，面向业务落地）；
本技能的 `references/` 是**机制字典**（英文，面向底层判定）。两者互补，不重复。

---

## 2. 门禁命名空间交叉映射（★ 必读，防止用错门）

三层各自有 G 开头的门禁，**同名不同义**。引用门禁时必须带层前缀。

| 统一前缀 | 所属层 | 门禁序列 | 语义 |
| :--- | :--- | :--- | :--- |
| **`AUTH-G0…G4`** | `softseep` 前置门控 | G0 权威定性 / G1 样本定性 / G2 写入判死归因 / G3 端点发现 / G4 响应判定 | **许可/激活类目标的权威归属判定** |
| **`APK-G1…G4`** | `apkseep` | G1 交付物形态 / G2 环境真实性 / G3 代码定位 / G4 基线对照 | Android 交付纪律 |
| **`EXE-G1…G5`** | **`exe-reverse`** | G1 交付物形态 / G2 **主机真实性与能力清单** / G3 代码定位 / G4 基线对照 / G5 **首次执行前隔离** | Windows 交付纪律（多一道隔离门） |

**硬规则**：
1. 说 `G2` 必须说清是哪一层的 `G2`；
2. `AUTH-G*` 先过（决定"能不能测、权威在不在本地"），再进 `EXE-G*` / `APK-G*`；
3. 本技能的操作纪律 `O1–O5`、症状索引、两击熔断、done 六条，**与 softseep 的调度纪律同等强制**。

---

## 3. 三条铁律（来自本技能，Windows 侧必须执行）

| 铁律 | 含义 | 落地命令 |
| :--- | :--- | :--- |
| **先探主机** | `EXE-G2`：不探测就假设"有 IDA / 能提权 / 不是虚拟机"，会把宿主问题误判成目标行为 | `python scripts/doctor.py` / `python scripts/hwprobe.py` |
| **等长补丁 + 回读** | 改字节必须等长；校验和重算；**写盘后逐字节回读**证明补丁真的落在文件里 | `python scripts/pepatch.py` |
| **未验证不得声称完成** | "能启动"≠"功能变了"；`done` 需满足六条，日志干净不算证据 | `references/verification.md` |

---

## 4. 中文意图 → 参考文件快速索引

| 用户大白话 | 直接加载 |
| :--- | :--- |
| 打补丁 / 改字节 / 校验和 / 补丁不生效 | `references/patching.md` |
| 特征码 / AOB / 跨版本还能用吗 | `references/aob-and-signatures.md` |
| 有壳 / 节区乱码 / 导入表空 / 自校验 | `references/protectors-and-packers.md`、`references/integrity-checks.md` |
| 一个几千行 switch / 控制流平坦化 / VMP | `references/virtualization-and-flattening.md` |
| 算法知道形状但常数看不到 | `references/algorithm-recovery.md`、`references/symbolic-execution.md` |
| .NET / C# / 混淆 / 名字没了 | `references/managed-dotnet.md`、`references/dotnet-decompilation.md` |
| Unity 游戏 / IL2CPP / global-metadata.dat | `references/unity-il2cpp.md` |
| PyInstaller / pyarmor / python3xx.dll | `references/python-runtime-bundles.md` |
| 驱动 / .sys / 内核 | `references/kernel-and-drivers.md` |
| 所有 hook 都被检测 / 硬件断点 / ETW | `references/hardware-tracing.md`、`references/hypervisor-observation.md` |
| 会员/授权到底谁说了算 | `references/license-mechanisms.md`、`references/network-activated-licensing.md` |
| 反调试 / 自毁 / 附加就崩 | `references/anti-analysis.md` |
| 两个版本行为不同 | `references/pe-diff-and-versions.md`、`references/cpu-vendor-divergence.md` |
| 工具输出爆上下文 | `scripts/fold.py` |
| 不知道这技能覆盖到哪 | `references/coverage-and-limits.md` |
| 准备发布成果前 | `references/desensitization.md` |

---

## 5. 可执行引擎（16 个脚本，纯标准库）

> **优先走 MCP 收口**：工作台的 `seep` MCP 已把四个最常用的 PE 操作包装成工具，
> 无需拼路径、无需走终端：
>
> | MCP 工具 | 对应脚本 | 读/写 |
> | :--- | :--- | :--- |
> | `seep_pe_triage` | `pe_triage.py` | 只读 |
> | `seep_pe_aob_scan` | `aob_scan.py` | 只读 |
> | `seep_pe_diff` | `pe_diff.py` | 只读 |
> | `seep_pe_patch` | `pepatch.py`（强制显式 out，拒绝原地覆盖） | **写** |
>
> 其余脚本（`doctor.py` / `hwprobe.py` / `plan.py` / `preflight.py` / `fold.py` /
> `trace_reduce.py` / `scan_leaks.py` / `make_fixture_pe.py` / `dart_snapshot_strings.py` /
> `capabilities.py` / `gate_probe.js`）仍直接命令行调用。

| 脚本 | 用途 | 写盘 |
| :--- | :--- | :--- |
| `peutil.py` | 零依赖 PE 解析库（RVA↔偏移、导入导出、资源、TLS、重定位、微软校验和、逐节熵） | 否 |
| `pe_triage.py` | 未知样本一次过体检（身份、构建证据、保护信号、攻击面、下一步） | 否 |
| `pepatch.py` | 等长补丁（只读输入、歧义守卫、校验和重算、逐字节回读） | **是** |
| `aob_scan.py` | 特征码定位 + 命中数 + unique/ambiguous/pervasive/no-match 裁决 | 否 |
| `pe_diff.py` | 归一化易变头字段的内容差分，差异映射回 RVA | 否 |
| `hwprobe.py` | 探测本机真实支持的路线（CPUID/提权/测试签名/Hypervisor/工具清单） | 否 |
| `doctor.py` | 能力裁决 + 逐脚本可运行性 + 会污染实验的宿主事实 | 否 |
| `capabilities.py` | 能力注册表：缺什么、怎么补、成本多少 | 否 |
| `plan.py` | 意图 → 能力 → 本机解析 → 缺口补齐命令 | 否 |
| `preflight.py` | 会话前置：样本哈希、工作副本、目标盘空间、残留追踪会话 | 否 |
| `fold.py` | 大输出有界摘要（一次扫描、上限明示） | 否 |
| `trace_reduce.py` | 混淆位向量化简 + 可选 SMT 证明 | 否 |
| `scan_leaks.py` | 发布前目标身份泄露扫描（可作 commit 门禁） | 否 |
| `make_fixture_pe.py` | 离线合成测试用 PE（五节区、完整目录、故意植入重复字节） | 是 |
| `dart_snapshot_strings.py` | 从 Dart AOT 快照（Flutter `app.so`）恢复字符串字面量 | 否 |
| `gate_probe.js` | Frida 探针：区分"门触发了/门放行了/什么都没发生" | 否 |

---

## 6. 许可证与溯源

- 上游：`https://codeberg.org/dabao1955/exe-reverse`（MIT，Copyright (c) 2026 exe-reverse contributors）
- 本工作台整体：**GPL-3.0**。MIT 与 GPL-3.0 兼容，本技能保留原始 MIT `LICENSE` 与署名。
- 上游镜像：`Tool/upstream/exe-reverse/`（含 `docs/tool-verification/` 证据记录与 `tests/` 回归套件）
- 同步：`setup/upstream-rules.json` 第 4 条，`python setup/sync-upstream.py -Target exe-reverse`

---

## 7. 上游不覆盖的内容（不要过度承诺）

见 `references/coverage-and-limits.md`。摘要：
- 击败**服务器权威**决策 —— 不可能，属于路线判定而非技术缺口；
- 通用全自动**脱虚拟化器** —— 不提供；
- 对某个**具名商业壳**的"产品级破解"承诺 —— 不提供；
- 本仓库**未实测**的 Windows 构建上的任何保证 —— 不承诺。

`unknown` ≠ `不存在`；"我没找到" ≠ "它不在"。
