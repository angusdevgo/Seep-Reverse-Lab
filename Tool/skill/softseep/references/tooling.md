# 常用工具脚本与参考工程

> 来源：softseep 主控 §七 | 加载时机：需要找现成脚本 / 工程模板时


1. **多进程代理 DLL 完整工程模板**：`项目B/localize/src/version_proxy.c` 与 `version.def`
2. **单进程代理 DLL + 显示层伪造完整工程**：`项目C/poc/proxy_version.cpp`、`version.def`、`build_zig.bat`
3. **逆向测绘报告范例（鉴权全貌 + 补丁清单 + 防御整改）**：`项目C/poc/RE_FINDINGS.md`
4. **全流程复盘模板（时间线/攻克点/踩坑/证据链）**：`项目C/poc/TASK_RETRO.md`
5. **自动化任务沙盒建档**：`Tool/scripts/case-init.ps1`
6. **工具链健康自检**：`Tool/scripts/refresh-tool-index.ps1`
7. **IDA Pro 自动化 MCP 链路**：`Tool/scripts/trigger_ida_mcp.ps1`
8. **跨进程 UI 工装集（可判定验收）**：
   - `tools/ui/abdump.ps1` —— 全量控件布局 + 文本字节 + 样式 dump
   - `tools/ui/linetest.ps1` —— `EM_GETLINECOUNT` 行数判定（LF vs CRLF 探针）
   - `tools/ui/crtest.ps1` —— CR 存活探针（判定控件是否吞 CR）
   - `tools/ui/openabout.ps1` —— `WM_COMMAND` 自动触发对话框
   - `tools/ui/menumap.ps1` —— 菜单命令 ID 递归枚举
9. **经典载荷构建器与加固源码**：`项目A/` 目录
10. **许可/激活/卡密校验模型全量手册**：`references/license-validation.md`
    - §1 运行时×模型×协议×平台四维分类（含 Win/mac/Linux 能力对照）
    - §2 静态解剖（PE 壳 · .NET 四堆手解 · Electron/JVM/Py 速解 · **商用保护壳/License SDK 指纹表**）
    - §5 端点接管（等长合法值规则 · **副本角色表与 2~3 处上限** · `netsh` 提权回环接管）
    - §6 握手与响应判定（字段角色拆法 · **会话绑定三判据**）
    - §7.1 **公钥替换重签五步法**
    - §8 金样回放 / §8.5 透明中继（五要点）
    - §9 **取载荷 Payload Carving**
    - §10 厂商侧防护清单（8 条，可直接交甲方）
    - §12 陷阱日志（15 条，单条即坑）
    - §13 交付模板 + **环境清理总清单**（删接管地址 / 还原 hosts / 撤 DNAT / 清自签 CA）

11. **四型项目实例证据归档**（个人经验沉淀，脱敏版）：
    - **项目 A**（单进程离线）：补丁点源码（2 处补丁字节）· 加固设计规范（4 类脆弱面 + 3 层防御）
    - **项目 B**（多进程混合）：会员状态链路分析摘要 · 代理 DLL 开发总结（12 点热补丁表 + 169 符号转发）· 手动点位表（53 点手动方案）
    - **项目 C**（资源模板）：完整 CWE-602 走查报告（258 行）· 全流程复盘（7 阶段时间线 + 5 攻克点 + 踩坑清单）
    - **项目 D**（壳保护 + 多策略）：激活注册原理参考源码（548 行 · 18 点补丁表 + 三策略联动）· 壳/导入/语义分析报告
    - **项目 E**（VM + 在线 → patch）：algorithm.md（EXECryptor 混合授权机理 + 补丁原理）· reverse-engineering.md（三态体系到补丁的完整逆向路径）· src/Patcher.cs（2 点补丁镜像实现）
    - **项目 F**（.NET 混淆 → Keygen）：algorithm.md（校验算法 + 19×5bit 构造 + 完整演算示例）· reverse-engineering.md（动态解壳三步 + IL 还原）· src/LicenseAlgo.cs（Generate/Verify/Checksum）
    - **项目 G**（自引用 → 补判定点）：algorithm.md（V1/V2 双层 + grace token 机理）· reverse-engineering.md（Python 确定性扫描法）· src/激活脚本（1 处 5 字节补丁 + 防回退守卫）
    - **项目 H**（公钥替换 Keygen）：algorithm.md（Ed25519 公钥密文内嵌 + 9 偏移回写 + 设备码自洽）· reverse-engineering.md（Qt 容器内存布局 + 反调试 XOR 路径）· src/（algo/cli/gui 三件套）
    - **项目 I**（RSA 弱模 + 验签入口补丁）：algorithm.md（RSA-1016 + CONST 异或 + 滑窗验证 + 机器绑定）· reverse-engineering.md（CNG blob 布局 + Ghidra 切分陷阱）· src/（SabLicenseAlgo/SabPatchEngine/SabMachineCode/SabRollbackGuard）
    > 实际目录名分享时一律改为 `项目A/B/C/D`，文件名同步重命名，防止据路径名反查目标
