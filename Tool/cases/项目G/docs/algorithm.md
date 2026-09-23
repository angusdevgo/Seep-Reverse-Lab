# 项目G <目标版本> 激活补丁方案（algorithm）

> 目标函数：`项目G::isLicensed(void)` @0x140b83910（文件偏移 0xB82D10）

## 1. 常量

| 名称 | 值 |
| :--- | :--- |
| 补丁偏移 | `0xB82D10`（文件偏移） |
| 原始字节 | `48 89 4c 24 08`（`mov qword [rsp+8], rcx`） |
| 补丁字节 | `b0 01 c3 90 90`（`mov al,1; ret; nop; nop`） |
| 原始 SHA256 | `<实测哈希>` |
| 补丁 SHA256 | `<实测哈希>` |

## 2. 工作原理

```
checkLicense() @启动
  ├─ isLicensed(void)   ← 项目G 基类, 每次启动调 2 次
  │    原版: 读 INI 许可 -> false      → 分支 "checkLicense free trial"
  │    补丁: mov al,1; ret (恒 true)   → 分支 "checkLicense pass"
```

补丁把函数入口改为 `mov al,1; ret`：不执行原函数体（读 INI、校验 payload），
调用方（checkLicense 等）统一收到"已授权"。函数帧未分配即返回，无栈平衡问题。

## 3. 兼容性

- 字节级检测三分支：已补丁 / 原版 / 未知（非标准构建跳过，避免破坏）
- 已知版本做强哈希校验；未知小版本字节匹配则继续（`[!]` 提示）
- Windows 大写不敏感路径自动去重（<本地路径> 与 <本地路径> 视为同一目录）

## 4. 防回退

- `--guard`：`HKCU\Software\Microsoft\Windows\CurrentVersion\Run\项目GActivateGuard`
  → `项目GActivate.exe --silent --fix`
- 登录时静默执行：定位全部 项目G 目录 → 检查偏移字节 → 原版则重新补丁 → 幂等退出
- `--unguard` 移除；`--revert` 由 `.bak` 还原正版

## 5. 验证

```
python -m pytest tests -q
# 5 passed：常量自洽 / 补丁往返 / 版本识别 / 样本哈希 / 购买链接

项目GActivate.exe --check
# [i] <本地路径> patched (已激活)
```