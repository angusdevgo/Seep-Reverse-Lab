# [种子] PCAP 自定义二进制协议逆向

## 场景分类
抓包分析 / 协议逆向

## 目标概述
某 IoT 设备/桌面客户端走 TCP 自定义二进制协议（非 HTTP），抓到一段 PCAP，需要还原帧结构、字段含义、加密层（如有），并写一个本地 client/server 复现。

## 完整执行链路

1. Wireshark 打开 PCAP，先做基础统计
   - `Statistics → Conversations` 看 IP/端口对
   - `Statistics → I/O Graphs` 看数据节奏
2. 找出真正的应用层流（剥掉 TLS 之类标准层）
3. 在某条 TCP 流上 → `Follow → TCP Stream` → 切到 RAW 模式 → 导出
4. 二进制级观察：每帧前几字节是不是固定 magic / 长度字段？
   ```bash
   xxd dump.bin | head -20
   ```
5. 用 hex 模式找规律：固定头、长度、TLV、CRC
6. 写 Python 解析器（struct + scapy）一帧一帧解
7. 同步从二进制反编译反查协议字段（IDA / Ghidra 看 send/recv 周围 struct）
8. 验证：自己起 client 发一帧 → 服务端响应一致

## 踩坑记录

| 问题 | 原因 | 解决方案 | 耗时 |
|------|------|---------|------|
| Wireshark 不识别协议，只显示 "Data" | 是私有协议，没有解析器 | 写 Wireshark Lua dissector 或 直接 Python 离线分析 | 30min |
| 看起来无规律，每帧都不同 | 有压缩或加密层 | 用熵分析（`ent dump.bin`）判断是否加密；找 nonce/IV 字段 | 1h |
| 长度字段算不对 | 长度可能是 little-endian / big-endian / 含/不含自身 | 找几条不同长度的帧，列方程组解出来 | 40min |
| TLS 抓到但解不了 | 客户端不留 SSLKEYLOGFILE | 在客户端进程层 hook（Frida 抓 ssl_read/ssl_write）抓明文 | 1.5h |
| 数据正确但服务端不响应 | 协议带递增的 seq / nonce，重放被拒 | 搞清楚 seq 计算方式（通常前一帧的 hash 或递增计数器） | 50min |

## 工具链发现

- **Wireshark Lua Dissector** 用 < 100 行就能把私有协议变成 Wireshark 可视化
- **scapy** 写 Python parser 时定义 `Packet` 子类即可
- **Kaitai Struct** 用 YAML 描述协议结构，能生成多语言 parser（Python/Java/C++/JS），适合长期复用
- **NetworkMiner** 比 Wireshark 更适合"事后取证"（自动重组文件、识别凭证）
- **ent / binwalk -E** 看熵，>7.5 几乎肯定加密

## 关键代码/命令

scapy 自定义协议示例（TLV）：

```python
from scapy.all import *

class MyMsg(Packet):
    name = "MyProto"
    fields_desc = [
        StrFixedLenField("magic", b"\xab\xcd", 2),
        ByteField("version", 1),
        ByteField("type", 0),
        LenField("length", None, fmt="H"),     # H = uint16 BE
        XIntField("seq", 0),
        StrLenField("payload", "", length_from=lambda p: p.length - 8),
        XShortField("crc", 0),
    ]

# 解析 PCAP
pkts = rdpcap('dump.pcap')
for p in pkts:
    if TCP in p and p[TCP].dport == 9527 and p.payload:
        msg = MyMsg(bytes(p[TCP].payload))
        msg.show()
```

Kaitai Struct YAML（长期项目首选）：

```yaml
# myproto.ksy
meta:
  id: myproto
  endian: be
seq:
  - id: magic
    contents: [0xab, 0xcd]
  - id: version
    type: u1
  - id: type
    type: u1
  - id: length
    type: u2
  - id: seq_no
    type: u4
  - id: payload
    size: length - 8
  - id: crc
    type: u2
```

熵分析：

```bash
binwalk -E dump.bin             # 熵图
ent dump.bin                    # 数值
```

## 对本包的改进建议

- `reverse-engineering/platforms.md` 增加"自定义协议逆向 4 步法"章节
- 新增 `reverse-engineering/references/kaitai-cheatsheet.md` 速查
- bootstrap manifest 增加 scapy（pip）和 binwalk

## 可复用的模式/脚本片段

**自定义协议逆向 4 步法**：

```text
1. 看节奏（I/O 图 + Conversations 找出会话边界）
2. 找帧界（magic / length / 终止符）
3. 拆字段（固定头、长度、payload、校验）
4. 验加密（熵 + 找 nonce + 二进制反查 send 函数）
```

**找帧长度的小技巧**：

把同流的所有 PSH 包导出 → 看每个 TCP segment 的总长度，看长度字段（位置 i, i+1, i+2 都试）是否能推出 segment 长度。

## 进化动作
- [ ] reverse-engineering/platforms.md 增加协议逆向章节
- [ ] bootstrap-manifest 加 scapy / binwalk
- [ ] 增加 Kaitai Struct 速查

## 环境信息
- Kali / Ubuntu，Wireshark 4.x, Python 3.10+, scapy 2.5
- 目标协议: 自定义 TCP 二进制（含 TLV / 长度前缀）
- 加密层: 视情况而定（常见 AES-CTR / ChaCha20）

## 脱敏要求
本条目为种子数据，基于公开协议逆向方法编写，不涉及真实产品。
