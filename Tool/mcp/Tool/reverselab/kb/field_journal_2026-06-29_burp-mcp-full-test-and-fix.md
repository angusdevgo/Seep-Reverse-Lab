# 2026-06-29 burp-mcp-full 全量测试与修复

## 场景分类
BurpSuite 扩展开发/测试

## 目标概述
对 burp-mcp-full 扩展(Burp Suite Professional MCP Full Control, 63 个工具)做全量运行时可用性测试,发现并修复 3 个 bug + 1 个桥接层竞争条件。

## 完整执行链路

1. 静态验证:检查 Java dispatch 表 / getToolList() / bridge buildToolDefinitions 三处 63 工具一致性
2. 编译:build.bat 自动化 fat-jar 打包(JDK 21, montoya-api 2025.5, gson 2.11.0, nanohttpd 2.3.1)
3. 加载:在 Burp Suite Professional 2026.4.2 中加载扩展,确认 [MCP] Server started
4. 运行时测试:分 5 批通过 node http 客户端直接调用 127.0.0.1:9876:
   - 第一批:30 个只读/编解码/查询工具(零副作用)
   - 第二批:网络发送类(send_request / repeater / intruder, 目标 scanme.nmap.org)
   - 第三批:Intruder 7 变体(attack/async/wordlist/pitchfork/cluster_bomb/battering_ram/with_options, 小范围枚举)
   - 第四批:Scope/配置/规则/handler/add_issue/compare
   - 第五批:crawl + proxy_clear
5. 发现并修复 3 个 bug,回归验证通过

## 踩坑记录

| 问题 | 原因 | 解决方案 | 耗时 |
|------|------|---------|------|
| `scan()` request_count 恒为 0 | AuditConfiguration 不接受种子 URL,代码漏调 addRequest | 从 url 解析 host/port/路径,构造 GET HttpRequest 喂给 activeAudit.addRequest() | 2h(含验证) |
| `send_to_intruder()` 报 HttpRequest must have an HttpService | 用 HttpRequest.httpRequest(raw) 无 service 重载 | 新增 buildRequestWithService(): 从 Host 头正则解析 host/port/https → HttpService,用 httpRequest(HttpService, raw) 重载 | 20min |
| `set_upstream_proxy()` 缺参数时空指针 NPE | params.get("proxy_host") 返回 null → .getAsString() NPE | 加判空:if (!params.has("proxy_host")) 返回清晰错误 | 5min |
| mcp-bridge.js API 异步竞争条件:4 个快速请求第 4 个丢失响应 | stdin close 时 process.exit(0) 杀死未完成的 HTTP 请求 | pending 计数器+stdinClosed 标志 → 所有请求完成后才 exit | 1h(含 mock 测试) |
| curl HTTP_CODE=000 无法探测端口 | curl 在本机被沙箱禁止 | 改用 node http 模块做探测 | 5min |
| Montoya API Audit 包路径推测错误 | 基于在线 javadoc 推断 Audit 在 scanner 包下 | javap 反编译真实 montoya-api-2025.5.jar 确认在 scanner.audit 包下 | 30min |
| 文件编码问题导致 Edit 工具匹配失败 | UTF-8 with BOM 中文内容在终端显示编码错层 | 改用 Python 做替换,指定 utf-8-sig | 10min |

## 工具链发现

- montoya-api 2025.5 版 Audit 在 `burp.api.montoya.scanner.audit.Audit` (非 scanner.Audit)
- AuditConfiguration 工厂方法不接受种子 URL,种子必须通过 Audit.addRequest(HttpRequest) 喂入
- HttpRequest.httpRequest(raw) 无 service 重载对 Repeater 够用,但 Intruder 要求带 HttpService
- Intruder.sendToIntruder(HttpRequest) 要求 request 必须附加 service
- api.burpSuite().version() 的 major()/minor()/build() 已在 2025.5 中移除 deprecation→removal,需用 buildNumber()/edition()/toString() 替代
- send_request 走 http.sendRequest(),不进 proxy history
- 本机 curl 被沙箱屏蔽,需用 node http 做探测
- IDA MCP 端口非固定 13337(实例间递增),但 Burp MCP 端口通过系统属性/env 可配,端口固定

## 关键代码/命令

### 全量测试脚本模式
```javascript
const http = require('http');
function call(tool, params={}, timeoutMs=30000) {
  return new Promise((resolve) => {
    const body = JSON.stringify({tool, params});
    const req = http.request({hostname:'127.0.0.1',port:9876,path:'/',method:'POST',
      headers:{'Content-Type':'application/json','Content-Length':Buffer.byteLength(body)}}, (res)=>{
      let d=''; res.on('data',c=>d+=c); res.on('end',()=>{ try{resolve(JSON.parse(d));}catch(e){resolve({__raw:d.slice(0,200)});} });
    });
    req.on('error', e => resolve({__err: e.message}));
    req.on('timeout', () => { req.destroy(); resolve({__timeout:true}); });
    req.setTimeout(timeoutMs);
    req.write(body); req.end();
  });
}
```

### buildRequestWithService (核心修复)
```java
private HttpRequest buildRequestWithService(String rawRequest) {
    java.util.regex.Matcher m = java.util.regex.Pattern.compile(
            "(?im)^Host:\\s*([^:\r\n]+)(?::(\\d+))?\\s*$").matcher(rawRequest);
    if (!m.find()) return HttpRequest.httpRequest(rawRequest);
    String host = m.group(1).trim();
    boolean isHttps = rawRequest.contains("https://") || rawRequest.contains(":443");
    int port = m.group(2) != null ? Integer.parseInt(m.group(2))
              : (isHttps ? 443 : 80);
    HttpService svc = HttpService.httpService(host, port, isHttps);
    return HttpRequest.httpRequest(svc, rawRequest);
}
```

### 桥接层竞争条件修复 (mcp-bridge.js)
```javascript
let pending = 0;
let stdinClosed = false;
rl.on('line', async (line) => { ... pending++; ... finally { pending--; if (stdinClosed && pending === 0) process.exit(0); } });
rl.on('close', () => { stdinClosed = true; if (pending === 0) process.exit(0); });
```

### scan() 种子修复
```java
// 从 URL 构造 GET 种子请求后喂给 audit
java.net.URL u = new java.net.URL(url);
String host = u.getHost();
boolean isHttps = "https".equalsIgnoreCase(u.getProtocol());
int port = u.getPort() > 0 ? u.getPort() : (isHttps ? 443 : 80);
String path = (u.getPath() == null || u.getPath().isEmpty()) ? "/" : u.getPath();
String pathQuery = u.getQuery() != null ? path + "?" + u.getQuery() : path;
HttpService svc = HttpService.httpService(host, port, isHttps);
HttpRequest seedReq = HttpRequest.httpRequest(svc,
    "GET " + pathQuery + " HTTP/1.1\r\nHost: " + host + "\r\nConnection: close\r\n\r\n");
activeAudit.addRequest(seedReq);
```

## 对本包的改进建议

- 路由矩阵已覆盖 BurpSuite MCP,无需修改
- `burpsuite-mcp-guide.md` 已追加更新日志(3 个修复 + 桥接层 + 全量验证结果)
- 工具表已更新 Scanner(scan 新增 mode 参数)和 Intruder(send_to_intruder Host header 要求)
- 无需新增 bootstrap 条目(编译脚本 build.bat 已自包含)
- IDA MCP 端口非固定,建议在 MCP 服务管理表中注明

## 可复用的模式/脚本片段

- 63 工具全量可用性测试脚本模式(见上方关键代码)。适用于任何 HTTP-based MCP 扩展的回归测试。
- buildRequestWithService 模式:从 Host 头解析 HttpService。适用于所有 Montoya API 中需要从原始请求构造 HttpRequest + HttpService 的场景。

## 进化动作
- [x] 更新了路由矩阵(路由已覆盖,无需修改)
- [ ] 更新了 tool-index(使用 .template,无需修改)
- [ ] 更新了 bootstrap-manifest(无新工具)
- [x] 更新了子 skill 文档(burpsuite-mcp-guide.md 追加更新日志)
- [x] 新增了 pitfall 记录(本条目)
- [ ] 无需更新

## 环境信息
- OS: Windows 11 Pro for Workstations 10.0.26200
- 工具版本: JDK 21.0.11+10 / Burp Suite Professional 2026.4.2 (20260402000047704)
- 目标平台: montoya-api 2025.5 / gson 2.11.0 / nanohttpd 2.3.1
- 测试目标: scanme.nmap.org (授权测试站点)

## 脱敏要求
测试目标为公开测试站点 scanme.nmap.org,无需脱敏。不含真实域名/IP/Token/用户名。

## 索引同步（提交前最后一步）

写完本日志后，必须同步更新 `_index.md`：

1. 在「按场景分类」对应小节新增一行（含日期、关键词）
2. 更新「累计统计」的计数与"最近更新"日期

---
<!-- [社区贡献] 完成后询问用户是否 PR 到主仓库。流程见 CONTRIBUTE-BACK.md -->
