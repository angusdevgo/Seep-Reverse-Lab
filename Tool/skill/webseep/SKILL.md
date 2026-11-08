---
name: webseep
description: 【Web / 流媒体逆向与取证】当目标是一条 m3u8/HLS 播放链路、一个影视采集接口（苹果CMS/海洋CMS/自建 API）、一个 TVBox/CatVod spider（jar/dex），或任何"接口能抓但播不出来 / 改个头就能过"的 Web 侧问题时使用。核心能力：HLS 六类根因判定（防盗链 / key 鉴权 / AES-128 / SAMPLE-AES / DRM / 源失效）、头变体矩阵重放定位门槛、spider 三入口与硬编码凭据提取。与 apkseep（客户端判权）、mcp-js-reverse-playbook（JS 签名链路）互补，不重复。
---

# webseep —— Web / 流媒体取证

> 这个 Skill 只回答一件事：**「抓到了，但播放不出来 / 访问不了」到底为什么。**
> 判不出来就别写结论 —— 影视源逆向的 6 类根因结论完全不同，猜错等于交废报告。

---

## 一、适用 / 不适用

| 适用 | 不适用（转到哪） |
| :--- | :--- |
| m3u8 / HLS 播不出、加密、防盗链 | 需要定位 JS 签名函数 → `mcp-js-reverse-playbook` |
| 影视采集接口（`/api.php/provide/vod/`）通路与越权 | 目标在 APK 内、要动客户端判权 → `apkseep` |
| TVBox / CatVod spider（jar / dex） | 二进制（PE/ELF/SO）→ `radare2` / `ida-reverse` |
| "抓包看到了请求，但不知道哪个头是关键" | 纯爬虫分页采集 → KB `ctf-website` + 通用模板 |
| 判定是否需要终止（DRM） | 大厂风控 JSVMP → 见第六节合规红线 |

---

## 二、四步法（不跳步）

> **已代码化**：`web-gate.ps1` + `web-pipeline.ps1` 把下面的四步变成硬阶段门，
> 前置产物缺失即 BLOCK。一键入口：
> ```powershell
> powershell -File Tool\scripts\web\web-pipeline.ps1 -Url <target> -Authorized -Scope "<授权依据>"
> ```

```
① 定性：这条链路的"失败点"在哪一层
    └─ 数据获取失败 → http-replay（头/凭据/频控）
    └─ 数据拿到了但解不开 → hls-analyze（加密/DRM/key）
    └─ 逻辑在客户端 jar 里 → spider-extract（三入口）

② 取证：用对应脚本产出 evidence.json + report.md（**必须有物证**）

③ 判定：6 类根因里属于哪一类（见第三节）

④ 交付：结论 + 物证 + 处置建议；DRM 一律 STOP
```

**阶段门（硬阻断，五段）**

| 阶段 | 名称 | 内容 |
| ---: | :--- | :--- |
| 0 | AUTHORIZE | 授权登记（G-Auth） |
| 1 | FINGERPRINT | CMS / 采集接口 / 暴露面 / 播放链路 |
| 2 | PROOF | 逐条可利用性举证（不是看到 200 就算） |
| 3 | RETEST | 复测确认仍存在 |
| 4 | REPORT | 专用报告（有 high 必先有举证） |

**纪律**：不允许"看 playlist 里有 `EXT-X-KEY` 就写加密"、不允许"403 就写有防护"。
`EXT-X-KEY:METHOD=NONE`、key 是否可取、分片是否真能解，是三个独立事实，必须分别验证。

---

## 三、HLS 六类根因（判定表）

| # | 根因 | 判定依据 | 能否取证闭环 |
| :-- | :--- | :--- | :--- |
| ① | 防盗链 | `http-replay` 定位到门槛头；全头 200 / 剔头 403 | ✅ 补齐头即可 |
| ② | key 鉴权 | `hls-analyze` 的 `KeyProbes` = `KEY_DENIED`（带头仍 401/403） | ⚠️ 需授权态 Cookie |
| ③ | AES-128 | `Decrypt.Scheme=AES-128` 且 `Possible=true`，ffmpeg 实解出 `probe.ts` | ✅ 可解 |
| ④ | SAMPLE-AES / fMP4 | `Decrypt.Scheme=SAMPLE-AES`，或 `Fmp4=true` | ⚠️ 需 mp4decrypt / shaka |
| ⑤ | DRM | `Drm` 字段命中 Widevine / FairPlay / PlayReady | ⛔ **STOP** |
| ⑥ | 源失效 | `Fetch.IsPlaylist=false`（返回 HTML/404/登录页） | ⛔ 无取证价值 |

关键区分点：`Decrypt.Possible=true` 但 `Verify.Ok=false` → 属 **①/② 的复合**（token 有效期、
分片级头不同域），不是"算法问题"。**不要**据此写成"加密强度高"。

---

## 四、工具与命令

| 目的 | 命令 |
| :--- | :--- |
| 首跑：确认工具箱就绪 | `powershell -File Tool\scripts\web\install-web-toolbox.ps1 -CheckOnly` |
| HLS 取证 | `powershell -File Tool\scripts\web\hls-analyze.ps1 -Url <m3u8> -Referer <r> -UserAgent <ua>` |
| 门槛定位 | `powershell -File Tool\scripts\web\http-replay.ps1 -Url <api>` 或 `-Curl "<浏览器复制>"` |
| spider 提取 | `powershell -File Tool\scripts\web\spider-extract.ps1 -Path .\spider.jar` |
| 站点指纹（CMS/影视源） | `powershell -File Tool\scripts\web\cms-fingerprint.ps1 -Url <站点>` |
| 模板化漏扫 / 目录爆破 | `nuclei -u <url> -tags cms,exposure` · `ffuf -u <url>/FUZZ -w <字典>` |
| 频控探测 | `http-replay.ps1 -Url <api> -RateTest 10` |
| **JS 沙盒执行** | `node Tool\skill\webseep\scripts\sandbox-runner.js <target.js> --extract-cookie --verbose` |

Agent 侧等价工具：`seep_hls_analyze` / `seep_http_replay` / `seep_spider_extract` / `seep_cms_fingerprint` / `seep_web_toolbox`。
完整手册见 `Tool/docs/WEB-TOOLBOX.md`。

## 四之二、按需加载的深度资料（本地文献，不是自动加载）

| 文件 | 何时读 |
| :--- | :--- |
| `references/crypto-patterns.md` | 认出密文形态后（32 位 hex → MD5？），要双语言复现时 |
| `references/protocol-analysis.md` | 头补全了还被拒 → TLS 指纹 / HTTP2 / 频控层 |
| `references/common-pitfalls.md` | 开始前先看反模式（observer effect / 误报归类） |
| `templates/python-request/` | 要交付一个可复跑的采集/巡检程序时（自带分页、断点、去重） |
| `scripts/sandbox-runner.js` | 要在 node vm 里跑目标脚本、抽 cookie / 全局变量时 |

> 来源与许可：这 5 项导自 `WhiteNightShadow/hello_js_reverse_skill@ec3cc38`，**上游无 LICENSE（保留所有权利）**，
> 仅限本机自用，**不得再分发**。详见 `PROVENANCE.md`。

---

## 五、跨 Skill 组合（真实工作流）

**A. 影视源"能播但卡/断"**
`http-replay`（确认头与频控）→ `hls-analyze`（分片数/时长/断点/token 有效期）→ 结论写"源侧 token 生命周期短"。

**B. 采集接口数据是错的/不完整**
`mcp-js-reverse-playbook`（拿 `sign` 生成逻辑）→ `http-replay`（验证签名参数是唯一门槛）→ 复现。

**C. spider 换了源站就失效**
`spider-extract`（定位 `detailContent`/`playerContent` + 硬编码域名）→ `http-replay`（新域名门槛是否变化）→ 给"改哪个常量"的结论。

**D. 站长的 App 有 VIP 判权**
转 `apkseep` + `client-license-validation-bypass`（CWE-602 客户端判权），本 Skill 只负责服务端的流链路。

---

## 六、合规红线（硬）

- 命中 **DRM / pssh / 许可证服务器** → 立即 STOP，写「不可逆向，需版权方授权」。不探测、不绕、不记录密钥。
- 产出必须是**站点自身健康度**结论（"为什么我的源不稳定 / 为什么能被绕过"），
  不得用于抓取他人版权内容。
- 涉及登录态的源：只使用站长本人提供且已授权的账号。

---

## 七、常见坑（踩过的，别重犯）

1. **ffmpeg 只给 `-headers` 不带 `-user_agent`** → 分片 403。UA/Referer 要用独立选项。
2. **用 `.cmd` 垫片调 ffmpeg** → 含 CRLF 的多行 `-headers` 被 `%*` 拆散。必须走真实 `.exe`。
3. **`EXT-X-KEY` 存在 ≠ 加密** → `METHOD=NONE` 是明文声明。
4. **key 返回非 16 字节就当成功** → 可能是 DRM 许可证响应或错误页，脚本判 `KEY_SUSPECT`。
5. **master playlist 直接分析分片** → 必须下钻到 variant，否则分片数为 0。
6. **把 `-VerifySeconds` 设太大** → 每个分片都要下载，单次验证 >60s 时容易触发 CDN 频控，反被 403。
