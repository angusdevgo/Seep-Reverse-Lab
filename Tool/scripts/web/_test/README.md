# Web 取证脚本回归测试（_test/）

这里放 **离线可复现** 的测试夹具，用来验证 `hls-analyze.ps1` / `http-replay.ps1` /
`spider-extract.ps1` 的判定逻辑没有被后续改动破坏。

> 这些文件**不参与运行**，只在人工回归时使用。不需要联网，不需要真实样本。

---

## 一、`serve_gated.py` —— 模拟影视站防盗链的本地服务器

规则（刻意模拟真实站点行为，三类资源三种门槛）：

| 路径 | 门槛 |
| :--- | :--- |
| `*.m3u8` | 必须带 `Referer: https://site.example/`，否则 403 |
| `*.key` | 同上 |
| `*.ts` | 必须带 `Referer` **且** `User-Agent` 含 `Mozilla`，否则 403 |

### 造一个 AES-128 + 防盗链的 fixture

```bash
FIX="D:/Tool/Web/work/fixture-aes"
mkdir -p "$FIX" && cd "$FIX"

FF="D:/Tool/Web/ffmpeg/bin/ffmpeg.exe"

# 1) 生成 6 秒测试视频
"$FF" -y -f lavfi -i "testsrc=size=320x240:rate=10" \
      -f lavfi -i "sine=frequency=440:sample_rate=44100" \
      -t 6 -c:v libx264 -preset ultrafast -pix_fmt yuv420p -c:a aac -b:a 64k src.mp4

# 2) 生成 AES-128 key 与 keyinfo（第二行必须是 key 文件的本地绝对路径）
openssl rand 16 > enc.key
printf "http://127.0.0.1:18080/enc.key\n%s\n%s\n" "$FIX/enc.key" "000102030405060708090a0b0c0d0e0f" > key_info.txt

# 3) 切 HLS
"$FF" -y -i src.mp4 -c copy -f hls -hls_time 2 -hls_playlist_type vod \
      -hls_key_info_file key_info.txt -hls_segment_filename "seg%03d.ts" out.m3u8

# 4) 起带门槛的服务器
# 用你自己的 Python 解释器启动；脚本路径相对本目录
python "$(dirname "$0")/serve_gated.py" "$FIX" 18080 &
```

### 期望结果

| 调用 | 期望 |
| :--- | :--- |
| `hls-analyze.ps1 -Url http://127.0.0.1:18080/out.m3u8`（无头） | `⚪ 目标不是有效 m3u8`，诊断 `NOT_A_PLAYLIST`（HTTP 403） |
| `hls-analyze.ps1 -Url ... -Referer https://site.example/ -UserAgent "Mozilla/5.0 Chrome/131.0.0.0"` | `🟢 可取证闭环`，`加密: AES-128`，`KEY_OK`，`去头后 403`，`probe.ts` 产出 |
| `http-replay.ps1 -Url ... -Referer ... -UserAgent ...` | `🟢 定位到门槛头：no-headers, ua-only, minus-Referer`；`referer-only` 为 200 |

---

## 二、`fixtures/DemoSpider.java` —— 合成 CatVod spider 源码

用来验证 `spider-extract.ps1` 的入口定位与线索抽取。编译成 jar：

```bash
cd "D:/Tool/Web/work/fixture-spider"
"D:/Tool/JDK 17/bin/javac.exe" -d classes src/com/spider/demo/DemoSpider.java
cd classes && "D:/Tool/JDK 17/bin/jar.exe" cf ../spider.jar .
```

（源码需先放到 `src/com/spider/demo/DemoSpider.java`，可从本目录直接拷过去。）

### 期望结果

```
entries   : homeContent / categoryContent / detailContent / playerContent 全部 ✅
domains   : api.example-vod.com, mirror2.example-cdn.net, www.example-site.com
secrets   : 2 处（API_KEY / SECRET）
headers   : 2 处（Referer / User-Agent）
verdict   : 🟢 已定位取流链路
```

---

## 三、已知的"看似 bug 其实是正确行为"

| 现象 | 原因 |
| :--- | :--- |
| ffmpeg 实解失败但判定"可解" | 判定基于 key 可取 + 分片未加密；实解失败通常是分片级头/一次性 token，属 ①/② 复合，不是算法问题 |
| `referer-only` 200 但 `minus-Referer` 403 | 正确 —— 说明 Referer 是唯一门槛，UA 不参与判定 |
| spider 提取报 `FAIL` | 入口靠命名匹配；反射调用的 spider 会被诚实判为未命中，不猜 |
