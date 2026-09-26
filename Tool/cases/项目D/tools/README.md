# 版本扩展流水线 (Version Extension Pipeline)

当 项目D 发布新版本、需要把补丁支持扩展到该版本时，按以下 6 步执行。

## 前置：准备样本

```bash
# 官方安装包（如 idman644build1.exe）
samples/项目D_<ver>_original.exe      # 从安装包提取出的原始 项目D.exe
```

## 步骤

| 步骤 | 脚本 | 作用 | 输入 → 输出 |
|---|---|---|---|
| 0 | `00_scan_only.py` | **只读扫描**：打补丁前体检，确认特征码对目标是否全部唯一命中 | 目标 项目D.exe → 终端输出 |
| 1 | `01_extract_sfx.py` | 解出官方安装包内的全部文件 | `idman6xx.exe` → `samples/extracted/项目D.exe` |
| 2 | `02_locate_points.py` | 滑动汉明距离定位已知位点在新版中的偏移 | 两版 项目D.exe → `samples/hamming_result.json` |
| 3 | `03_gen_signatures.py` | 生成**全部已采集版本**共同稳定的 AOB 特征码表 | 多版 项目D.exe → `samples/final_table.json` |
| 4 | `04_emit_cs_table.py` | 输出可直接粘贴进 `Program.cs` 的 C# 表 | `final_table.json` → `samples/aob_table.cs` |
| 5 | `05_verify_disasm.py` | capstone 反汇编语义比对，确认位点语义一致 | 两版 项目D.exe → 终端输出 |
| 6 | `06_e2e_validate.py` | 端到端打补丁并校验产物合法性 | 新版 项目D.exe → `samples/项目D_<ver>_patched.exe` |
| 7 | `07_splice_into_cs.py` | 把 `aob_table.cs` 自动拼接进 `src/Program.cs` | → 更新后的 `Program.cs` |

## 步骤 2/3 的前置修改

这两个脚本内硬编码了**已确认的位点映射**（`MAPPING` 数组）。新增版本时：

1. 先跑 `02_locate_points.py`，它会用**上一版已验证的偏移**作为输入，输出新版偏移；
2. 人工核对汉明距离（应 ≤ 8，随机期望 ≈ 62）与位点字节；
3. 把新版偏移补进 `MAPPING`，再跑 `03_gen_signatures.py` 生成三版本稳定特征码。

## 关键判据

- **汉明距离**：64 字节窗口下应 ≤ 8。若某位点距离 > 12，说明该处代码已实质变更，需重新逆向。
- **双态唯一性**：特征码在「原始态」与「已补丁态」下均须**唯一命中**。若某点命中数 ≠ 1，通常是**相邻位点互相包含**，需合并为单一条目（参见 `0x378CDC` + `0x378CE0` 的合并案例）。
- **差异字节白名单**：产物相对原版的差异字节，必须全部落在「补丁位点 ∪ PE 校验和 ∪ 签名目录」内，否则说明发生了意外改动。

## ⚠️ 特征码必须基于多版本共同稳定区

**实战教训**：用 **6.43.11.2 单版本** 生成的特征码，在 **6.43.11.3** 上 13/14 命中，唯一失败的那条特征码其**右扩展 4 字节恰好是重定位指针**（11.2 = `38 83 69 00`，11.3 = `30 83 69 00`）。

> **规则**：向左右扩展特征码时，必须要求该字节在**所有已采集版本**中一致。否则会把版本相关的重定位指针、地址常量纳入特征码，导致跨版本失效。

新版本引入后，应把新样本加入 `03_gen_signatures.py` 的 `VERSIONS` 列表重新生成，特征码会自动收窄到真正的稳定区。

## 新版本必须新增位点的情况

现有 14 个特征码只能覆盖**已有语义**的补丁点。若 项目D 新增了反篡改校验，需：

1. 用 IDA 定位新校验逻辑；
2. 把新位点补进 `03_gen_signatures.py` 的 `POINTS` 数组（需给出全部已采集版本的对应偏移）；
3. 重新生成特征码表并重跑回归测试。

## 集成到工具

把 `04_emit_cs_table.py` 的输出替换 `src/Program.cs` 中 `NativeBinaryPatcher.POINTS` 数组，并同步更新：

```csharp
public const string SupportedVersions = "项目D 6.43 build 10 / 6.43 build 11 / <新版>";
```

然后运行回归测试：

```bat
tests\build_tests.bat
tests\PatchEngineTests.exe
```

## 依赖

```
pip install numpy capstone pefile
```
