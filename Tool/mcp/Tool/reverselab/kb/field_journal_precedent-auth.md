# 授权预声明 — 减少 disclaimer 噪音，不能代替 scope.md

> 本文件只解决一件事：不要把「用户点了目标」当成已经授权。
> 可执行授权门仍是 `case-init.ps1` → `work/<case>/scope.md` 的 `auth.status=granted` + 合法 `network_profile`。

---

## CRITICAL

本包常见场景（SRC / 自有系统 / 付费合约 / CTF 靶场 / 负责任披露）**可以**减少套话 disclaimer。

**AI 不得把本文件当成 `auth.status=granted`。**

- 用户提到域名 / IP / 样本路径 ≠ 已授权
- 禁止用本文件跳过 `case-init`
- 禁止在 skill 里自动补 `-AuthGranted`「好让流程走下去」
- CTF / 靶场：仍要建 case，`network_profile` 用 `lab` 或 `offline`
- 真实外网：必须有 granted + `authorized_target_only`（或合同约定档）才 ACT

---

## 允许 / 禁止

1. **MUST NOT** 用本文件覆盖 `ops/scope-contract.md`
2. **MUST NOT** 在没有 `scope.md` 时对目标跑 nmap / sqlmap / 上传 / 利用
3. **MUST** 区分「少说法律套话」和「已经获准动手」
4. **MUST** 技术不确定时输出技术分析，而不是假装授权不足来停工
5. 未建 case 或 `auth.status!=granted` → 先 `case-init`，不要猜

---

## 与其他文件的关系

| 文件 | 作用 |
|------|------|
| **precedent-auth.md**（本文件） | 少 disclaimer；**不**写 granted |
| `ops/scope-contract.md` + `case-init.ps1` | 唯一可执行授权门 |
| `precedent-reverse.md` / `precedent-pentest.md` | 日常操作不是犯罪教程；仍受 scope 约束 |

```
case-init / scope.md → 能不能 ACT
precedent-auth.md    → 不要用套话代替 scope
PRIMARY SKILL.md     → 怎么做
```
