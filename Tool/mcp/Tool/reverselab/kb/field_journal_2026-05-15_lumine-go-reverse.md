---
name: lumine-reverse-2026-05-15
description: Go 1.24.5 TLS 分片代理 lumine v0.9.1 全量逆向恢复，含 7 个包源码重建
metadata:
  type: project
---

# lumine v0.9.1 — Go TLS 分片代理逆向

**日期**: 2026-05-15
**目标**: `lumine_v0.9.1_windows_amd64.exe` (PE32+, Go 1.24.5, 11.6 MB)
**原文**: `REVERSE_REPORT.md`

## 背景

用户要求将二进制还原为可读 Go 源码。目标是一个 TLS 反 DPI 代理工具，技术源自 Python [TlsFragment](https://github.com/maoist2009/TlsFragment)。

## 过程

1. **工具链搭建**: Python + capstone 反汇编, GoReSym 恢复符号表 (1944 个 Go 函数, 269 个来自项目)
2. **包结构识别**: 从 GoReSym 的 `package.function` 命名推断出 12 个包
3. **类型恢复**: 通过 `config.json` 反推 JSON 反序列化类型，结合函数引用恢复字段
4. **源码重建**: 按包逐个编写可读 Go 代码，保留逻辑而非逐行还原
5. **子包补全**: dial (出站绑定), errors (错误类型), format (字符串工具)

## 关键发现

- 核心反 DPI 机制: TLS 记录分段 + 噪声注入 + 等待 ACK + OOB + Fake TTL
- 策略引擎: 域名 Trie + IP Trie → Policy 匹配
- 依赖 `go-freelru` (LRU 缓存) 做 DNS/TTL 缓存
- 源仓库 `github.com/moi-si/lumine` 返回 404，只能完全靠二进制恢复

## 工具

| 工具 | 用途 | 版本 |
|---|---|---|
| GoReSym | Go 符号恢复 | v1.7.1 (Mandiant) |
| Capstone | 反汇编引擎 | latest |
| pefile | PE 结构解析 | latest |

## 踩坑记录

1. **Python3 路径问题**: WindowsApps 的 stub python3 不支持 pip install capstone，需用完整 CPython 路径
2. **GoReSym 子进程路径**: `~` 不会自动展开，需 `os.path.expanduser()`
3. **tab/space 混用**: 自动生成的 Python 反编译脚本中存在 tab/space 混合，导致 Go 源码格式错误；v3 版全部用空格解决
4. **vendor-less GoReSym**: Go 1.24.5 的 binary 不带 vendor 符号时，GoReSym 仍能提取函数名但参数和局部变量不可恢复
5. **字符串噪声**: Go 标准库字符串常量大量混入，需要仔细从包级别过滤

## 产物

- `REVERSE_REPORT.md` — 完整逆向分析报告
- `reconstructed_src_v3/` — 7 个 Go 源文件，core engine + 3 个子包
