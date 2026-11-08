# Seep Web / 流媒体取证工具箱（WEB-TOOLBOX.md）

> 补的是工作台在 Web 维度的**「手」**：能脱离浏览器发请求、改包、验流、拆 spider 的能力。
> 只读方法论不够用 —— 影视源逆向的结论必须落到物证。

---

## 一、这套工具箱解决什么

影视站「播放不出来」有 **6 种完全不同的根因**，靠肉眼看 playlist 分不清：

| # | 根因 | 现象 | 谁来判 |
| :-- | :--- | :--- | :--- |
| ① | **防盗链** | 直链 403，带 Referer 就 200 | `hls-analyze` / `http-replay` |
| ② | **key 鉴权** | playlist 能取，`EXT-X-KEY` 的 URI 需登录态 | `hls-analyze`（key 探测） |
| ③ | **AES-128 加密** | 分片是密文，key 可取 → 可解 | `hls-analyze`（ffmpeg 实解） |
| ④ | **SAMPLE-AES / fMP4** | 部分帧加密或 `EXT-X-MAP` 初始化段 | `hls-analyze`（不冒充能解） |
| ⑤ | **DRM** | Widevine / FairPlay / PlayReady | `hls-analyze`（直接判 STOP） |
| ⑥ | **源本身失效** | 站返回 HTML 错误页伪装成 m3u8 | `hls-analyze`（`NOT_A_PLAYLIST`） |

**判定不出来就别下结论** —— 这 6 种里，①③ 可以取证闭环，②需授权态，④需专用解封装，⑤必须终止。

---

## 二、安装（幂等）

```powershell
powershell -ExecutionPolicy Bypass -File Tool\scripts\web\install-web-toolbox.ps1
```

| 项 | 说明 |
| :--- | :--- |
| 装到哪 | 默认 `D:\Tool\Web`，可用 `-Root` 或环境变量 `SEEP_WEB_TOOLBOX` 覆盖 |
| 装什么 | ffmpeg + ffprobe（BtbN 官方 builds，GitHub 代理镜像回退） |
| 副作用 | 生成 `<root>\bin\{ffmpeg,ffprobe}.cmd` 垫片，并加入用户 PATH |
| 重复跑 | 只补缺失，不动已有；`-Force` 强制重装，`-CheckOnly` 只看状态 |

> **PATH 提示**：新开终端才带新 PATH；当前会话请用绝对路径或走脚本（脚本内部自动解析）。

---

## 三、四个脚本

### 1. `hls-analyze.ps1` —— HLS 取证器（P0 主力）

```powershell
# 最简
powershell -File Tool\scripts\web\hls-analyze.ps1 -Url "https://cdn.site.com/hls/index.m3u8"

# 带防盗链头（影视站最常见）
powershell -File Tool\scripts\web\hls-analyze.ps1 -Url "<m3u8>" `
  -Referer "https://site.com/" -UserAgent "Mozilla/5.0 ..."

# 从浏览器复制的 curl 直接喂
powershell -File Tool\scripts\web\hls-analyze.ps1 -Curl "curl 'https://...' -H 'Referer: ...'"
```

**它做什么**：拉 playlist → master 递归下钻选最高码率 → 解析 `EXT-X-KEY` / `EXT-X-MAP` /
`EXT-X-DISCONTINUITY` / 分片规律 / token 参数 → **key URI 双态探测**（带头 vs 去头）→
ffmpeg 实解前 N 秒 → ffprobe 验编码 → 出 `evidence.json` + `report.md` + `probe.ts`。

**关键实现细节（踩过的坑，别改回去）**：
- ffmpeg 的 `-headers` **不会稳定下传到 HLS 子资源**（分片/key），UA 必须用独立 `-user_agent`，
  Referer 用 `-referer`。只给 `-headers` 会在分片上 403。
- 必须调用**真实 `.exe`** 而不是 `.cmd` 垫片 —— `.cmd` 通过 `%*` 传参无法携带含 CRLF 的多行参数，
  会报 `Trailing option(s) found in the command`。`WebToolbox.ps1` 的解析顺序已保证 exe 优先。
- PowerShell 5.1 里 `Where-Object` 命中单个对象时 `.Count` 是 `$null`，必须 `@(...).Count`。

### 2. `http-replay.ps1` —— 防盗链 / 鉴权举证器（P0）

```powershell
powershell -File Tool\scripts\web\http-replay.ps1 -Url "https://api.site.com/vod?ac=detail&ids=1"
powershell -File Tool\scripts\web\http-replay.ps1 -Curl "<浏览器复制的 curl>"
powershell -File Tool\scripts\web\http-replay.ps1 -Url "<api>" -Method POST -Body '{"id":1}' -RateTest 10
```

生成**头变体矩阵**并逐条重放：

```
full              200   18234B   ← 基准
no-headers        403       0B
ua-only           403       0B
referer-only      200   18234B   ← 只要 Referer 就能过
minus-Referer     403       0B   ← 剔除它就挂
minus-User-Agent  200   18234B
mobile-ua         200   18234B
```

三条结论分支：
- 🟢 **定位到门槛头**：其他都 200，剔掉某个就 403
- 🟡 **头不是门槛**：全部都能过 → 鉴权在时间戳签名 / token 参数 / IP / 频率
- 🟠 **全头仍失败**：需要登录态 Cookie / 有效签名 / 设备指纹 / IP 白名单

`-RateTest N` 额外打点检测 429 频控；`-SaveBodies` 落盘正文便于 diff。

### 3. `spider-extract.ps1` —— TVBox / CatVod 三入口提取（P1）

```powershell
powershell -File Tool\scripts\web\spider-extract.ps1 -Path .\spider.jar
```

> jadx 原生支持 `.jar`（已在工作台内置），**不需要额外装 Java 反编译器**。

入口固定四个，找到 `detailContent` / `playerContent` 就等于拿到取流链路：

| 入口 | 作用 |
| :--- | :--- |
| `homeContent` | 首页分类与推荐 |
| `categoryContent` | 分类分页列表 |
| `detailContent` | 详情（真正下发播放地址） |
| `playerContent` | 播放解析（取流逻辑） |

同时抽取：硬编码域名、接口路径（含 `?ac=detail` 这类采集参数）、
**硬编码凭据（CWE-798）**、**代码内硬编码请求头（防盗链绕过点）**、混淆度、加密调用种类。

### 4. `install-web-toolbox.ps1` —— 安装器（见第二节）

### 5. `install-web-scanners.ps1` —— 渗透扫描器安装

```powershell
powershell -File Tool\scripts\web\install-web-scanners.ps1
powershell -File Tool\scripts\web\install-web-scanners.ps1 -CheckOnly
powershell -File Tool\scripts\web\install-web-scanners.ps1 -Only nuclei
```

| 工具 | 作用 | 实测版本 |
| :--- | :--- | :--- |
| **nuclei** | 模板化漏扫（CMS 配置错配 / 暴露备份 / Actuator / Swagger / 技术指纹） | v3.11.1，模板库 14,104 条 / 88 MB |
| **ffuf** | 目录与参数爆破 | v2.3.0 + 自带 21 条最小字典 |
| **whatweb** | CMS 指纹 | ⚠️ **Ruby 脚本，本机无 Ruby → 已用 `cms-fingerprint.ps1` 替代** |

> nuclei 模板落在 `C:\Users\<you>\nuclei-templates`（默认位置）。
> `-tl` 会卡住等更新，别在 Agent 里跑；要看模板量直接 `find` 计 yaml 数。

### 6. `cms-fingerprint.ps1` —— 影视站 CMS / 源站指纹（whatweb 的针对性替代）

```powershell
powershell -File Tool\scripts\web\cms-fingerprint.ps1 -Url https://site.com
powershell -File Tool\scripts\web\cms-fingerprint.ps1 -Url https://site.com -Deep
```

六个识别维度：

| # | 维度 | 判定方式 |
| :-- | :--- | :--- |
| ① | 服务栈 | `Server` / `X-Powered-By` / `Set-Cookie` 名 / CDN·WAF 特征（Cloudflare / 加速乐 / 阿里云 WAF） |
| ② | CMS 家族 | 苹果CMS(maccms10) / 海洋CMS(seacms) / 织梦 / WordPress / 自建（HTML 特征加权） |
| ③ | **采集接口** | `/api.php/provide/vod/?ac=list` 是否返回有效 JSON（影视站核心资产） |
| ④ | 播放器 | MacPlayer / DPlayer / video.js / hls.js / ckplayer / aliplayer / jwplayer |
| ⑤ | TVBox 源 | `/tvbox/config.json` 类 `sites` 聚合配置 |
| ⑥ | 暴露面 | 后台入口 / `.env` / `.git/config` / 备份 / `install/` / `phpinfo.php`（`-Deep`） |

**行为约束**：只发 GET、固定 ≤20 个路径、默认 400ms 间隔；不爆破、不提交表单、不尝试登录。

**结论分级**：🟢 识别（置信度 ≥60%）/ 🟡 疑似 / ⚪ 未识别（自建站或强 WAF）。

---

## 四、路径解析（换机器 / 换盘怎么让它认到）

`Tool/scripts/lib/WebToolbox.ps1` 统一解析，优先级**从上到下命中即止**：

| 顺序 | 探测点 | 说明 |
| :--- | :--- | :--- |
| 1 | `$env:SEEP_WEB_TOOLBOX` | **唯一搬家开关**，换盘只改这一个 |
| 2 | `<root>\ffmpeg\bin\ffmpeg.exe` | 标准安装位（真实 exe 优先） |
| 3 | `<root>\bin\ffmpeg.exe` | 平铺安装 |
| 4 | `<root>\bin\ffmpeg.cmd` | 垫片（交互用，脚本不依赖） |
| 5 | `<root>\ffmpeg.exe` | 单文件投放 |
| 6 | 系统 `PATH` | 你自己装的 / winget / scoop |

MCP 侧 `_resolve_web_tool()` 用同一套顺序，所以 **Agent 调 `seep_hls_analyze` 和你在终端跑脚本走的是同一判定**。

---

## 五、MCP 工具（Agent 可直接调）

| 工具 | 说明 |
| :--- | :--- |
| `seep_web_toolbox()` | 工具箱就绪度看板（ffmpeg / ffprobe / nuclei / ffuf / whatweb / node + 字典与模板目录） |
| `seep_hls_analyze(url, referer, user_agent, cookie, headers, variant, verify_seconds, no_verify)` | HLS 取证，返回 verdict / 加密方案 / DRM / key 探测 / ffprobe 结果 / 报告路径 |
| `seep_http_replay(url \| curl, referer, user_agent, headers, method, body, rate_test)` | 头变体矩阵重放，返回门槛头定位 + 矩阵表 |
| `seep_spider_extract(target_path, out_dir, skip_decompile)` | spider 三入口 + 域名 / 接口 / 凭据 / 硬编码头 / 混淆度 |
| `seep_cms_fingerprint(url, referer, user_agent, cookie, headers, deep)` | CMS 家族 / 采集接口 / 播放器 / TVBox 配置 / 暴露面 |

`seep_status()` 的 `components.web_toolbox` 会一起报告就绪情况。

---

## 六、产物结构

```
<root>\work\hls-<时间戳>\
├── evidence.json    机器可读（Schema: seep.hls.evidence/1）
├── report.md        人可读（结论 + 六类诊断 + 处置建议）
└── probe.ts         ffmpeg 实解物证（"能播"的证明）

<root>\work\replay-<时间戳>\
├── evidence.json    Schema: seep.http.replay/1
├── report.md
└── bodies\          -SaveBodies 时的正文快照

<root>\work\spider-<名称>-<时间戳>\
├── src\             jadx 反编译产物
├── evidence.json    Schema: seep.spider.extract/1
└── report.md
```

`evidence.json` 的字段是**为报告直接引用**设计的：写 CWE-602 审计报告时可直接把
`Verdict.Level` / `KeyProbes` / `Diagnosis` 摘进正文，不需要二次加工。

---

## 七、合规边界（硬规则）

| 情形 | 动作 |
| :--- | :--- |
| 检测到 **Widevine / FairPlay / PlayReady / pssh** | **立即终止**，写「受 DRM 保护、不可逆向、需版权方授权」，不再探测许可证服务器 |
| 目标是自己/已授权站点 | 正常取证 |
| 产出用于抓取他人版权内容 | 禁止 —— 合法产出是「我的源为什么不稳 / 为什么被绕过」 |

---

## 七、自动逆向流程（一条命令跑完整条链）

这是「是否有泄露源风险？若有就复现并写报告」这类问题的**标准入口**。

```powershell
powershell -File Tool\scripts\web\web-pipeline.ps1 `
    -Url https://site.com -Authorized -Scope "站长自有站点全量授权"
```

### 五段硬门（不可跳）

| 阶段 | 名称 | 门禁要求 | 不满足时 |
| ---: | :--- | :--- | :--- |
| 0 | AUTHORIZE | 显式传入 `-Authorized -Scope` | **exit 2**，直接停 |
| 1 | FINGERPRINT | stage 0 已登记 | BLOCK |
| 2 | PROOF | stage 1 已收录且非空 | BLOCK；空举证拒绝收录 |
| 3 | RETEST | stage 2 已收录 | BLOCK |
| 4 | REPORT | 有 high 就必须有举证；report.md 存在 | BLOCK |

> 每次 check 都写 `.gate-history.jsonl`，**防「事后回填」**。

### 流程实际做什

```
授权登记 → cms-fingerprint -Deep → 逐条验暴露面（真取内容判定）
        → （可选）nuclei / ffuf → 复测确认仍存在 → 生成专用报告
```

**举证不是「看到 200 就算漏洞」**，每条都有判定规则：

| 类型 | 判定为可利用的条件 |
| :--- | :--- |
| 配置泄露 | 响应内含 `KEY=value` 形式的键值对 |
| 源码仓库泄露 | `.git/config` 含 `[core]` 段 |
| 备份文件 | Content-Type 非 html 且体积 > 32 B |
| phpinfo | 含 `PHP Version` / `phpinfo()` |
| 目录 | 含 `Index of /` |
| 后台入口 | 仅暴露入口 → **不计为可利用**（不等于可越权） |
| 采集接口 | 无鉴权返回 `list`/`data` → 可被第三方聚合 |

### 四个脚本分工

| 脚本 | 职责 |
| :--- | :--- |
| `web-pipeline.ps1` | 编排器：串起全链，每步过门 |
| `web-gate.ps1` | 阶段门：`init` / `authorize` / `check` / `record` / `status` |
| `web-report.ps1` | 报告：只读案件产物，**不重发包**（保证报告与证据一一对应） |
| `cms-fingerprint.ps1` | 指纹（被 pipeline 调度） |

### 分次执行（手动推进）

```powershell
$g = 'Tool\scripts\web\web-gate.ps1'
& $g -Action init -Target https://site.com
& $g -Action authorize -Dir <case> -Scope "站长自有站点全量授权"
& $g -Action check  -Dir <case> -Stage 2          # 能不能进第 2 阶段
& $g -Action record -Dir <case> -Stage 1 -Source <cms-fingerprint evidence.json>
& $g -Action status -Dir <case>
```

### 报告为什么不用 `seep_gen_security_report`

| | `seep_gen_security_report` | `web-report.ps1` |
| :--- | :--- | :--- |
| 适用场景 | 客户端 CWE-602 判权 | 网站源与暴露面 |
| 参数 | `branch_location = "0x0"`（地址偏移） | 案件目录 |
| 修复建议 | `ProcessDynamicCodePolicy` / 非对称签名 / 代码段自校验 | deny 规则 / 密钥轮换 / 日志审计 / 备份外迁 |
| 证据链 | 无 | gate 历史 + 逐条请求-响应 |

---

## 八、体检

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup\verify.ps1 -Detailed
```

新增 9 项检查：ffmpeg / ffprobe / 3 个取证脚本 / WebToolbox.ps1 / 本文档 / nuclei / ffuf /
cms-fingerprint + sandbox-runner / **web-pipeline + web-gate + web-report**。

---

## 九、已知边界（不吹）

| 项 | 状态 |
| :--- | :--- |
| SAMPLE-AES / SAMPLE-AES-CTR | 只判定并给出处置建议，不做解封装（需 mp4decrypt / shaka-packager） |
| 纯 AES-128-CBC 手动解 key | 交给 ffmpeg，脚本不自实现密码学 |
| Live 流 | 能解析，但 `-VerifySeconds` 只验窗口内分片 |
| 需要登录态的 key | 判定为 `KEY_DENIED`，需你提供有效 Cookie 后重跑 |
| 非 CatVod 结构的 spider | 入口靠命名匹配，反射调用的会被判 `FAIL`（诚实报告，不猜） |
| **whatweb** | 本机无 Ruby，未安装；由 `cms-fingerprint.ps1` 覆盖（对国内影视站更准） |
| **nuclei 首次跑** | 需 `-update-templates`（已预拉 14,104 条）；`-tl` 会卡住等更新，别在 Agent 里跑 |
| **CMS 识别上限** | 强 WAF（加速乐 JS 挑战 / 阿里云滑块）会返回挑战页 → 判 `⚪ 未识别`，需先用 js-reverse 过挑战再重跑 |
| **导入的第三方文献** | 5 项来自 `hello_js_reverse_skill@ec3cc38`，上游**无 LICENSE**，仅限本机自用、不得再分发（见 `webseep/PROVENANCE.md`） |
