# 软件安全评估与鉴权脆弱性走查报告

- **目标资产**: `示例`
- **评估类型**: 白盒代码走查 / 客户端决策逻辑安全性验证
- **缺陷分类**: `CWE-602`
- **评估时间**: 鍛ㄤ竴 2026/11/09 
- **报告归属**: `probe/reports/`

---

## 1. 风险概述与脆弱性成因 (Vulnerability Summary)
client-side check

---

## 2. 关键判定决策位点 (Decision Branch Location)
- **判定函数 / 偏移位点**: `lib/x.so`
- **汇编指令与分支模式**:
```text
; 典型本地鉴权判断分支
TEST EAX, EAX
JZ   loc_restricted_feature  ; 本地跳转决定受限功能
```

---

## 3. 验证 PoC 与复现过程 (Proof of Concept)
n/a

---

## 4. 纵深防护与企业级加固修复建议 (Remediation)
server-side enforcement
