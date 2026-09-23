# 项目H <目标版本> PRO 授权算法原理

> 目标函数：`项目H`（桌面版内置，RVA 约 `0x140240000`）；离线激活与在线激活
> 共用同一解析/验签链。

## 1. 常量

```python
CHARSET     - 无（激活码为 base64，字符集标准 64）
SIGN_ALGO   - Ed25519（CryptoPP ed25519Verifier）
SIG_LEN     - 64
JSON_GZIP   - gzip 压缩（wbits=31 兼容 Qt）
机器码哈希  - blake2s(digest_size=16)，输入 "项目H 2" + "1" + MachineGuid
```

- 官方 Ed25519 公钥（32 字节原始格式）：
  `<实测哈希>`
- 公钥**不是明文存储**，而是以 58 字节密文内嵌在 `FUN_140249fa0`
  （15 个立即数 mov），运行时代码（`FUN_24fe70`/`FUN_24f920`）解密还原。

## 2. 设备码（hwi.machineid）

客户端在每次校验时**重新现算**期望设备码并与 license 中的 `hwi.machineid` 比较；

```
hex   = blake2s("项目H 2", "1", MachineGuid)[-6:].hex().upper()   # 12 字符
s     = hex[:4] + '-' + hex[4:]                                       # '62D7-B6766225'
check = adjacent_char_diff_sum(hex)     # 相邻 ASCII 差绝对值和 % len 取字符
期望设备码 = s + check + '1'            # '62D7-B676622561'（15 字符）
```

- 自洽性：15 字符、1 个 '-' → `(15-1-2)/2 = 6`，即 hex 长度 12=2*6，与 `[-6:]` 一致。
- JSON 中 `hwi.machineid` 存**明文**即可：客户端解析时用 `encode_field` 编码存储，
  校验时 `decode_field` 还原为明文——encode/decode 是互逆变换（密钥随机）。

### encode_field / decode_field（FUN_26db40 / FUN_26dc80）

```
encode:
    rot = |int8(key) ^ L| % L           # L = 长度
    body = rotate_right(明文, rot)
    for i: body[i] ^= (key ^ i) & 0xFF
    输出 = key 字节 + body
decode:
    rot = |int8(key) ^ (L-1)| % (L-1)
    for i: body[i] ^= (key ^ i) & 0xFF
    body = rotate_left(body, rot)       # 与 encode 的右旋配对
    输出 = body
```

> 生成 keygen 时对 `hwi.machineid` 填明文即可（客户端内部自行编解码）。其余字符串字段
> （nam/eml/pln/dom…）同样由客户端 encode 存储、decode 读取，JSON 侧全部使用明文。

## 3. 激活码结构

```
code = code[0] code[1] '-' code[3:]
  code[0] = 版本字符（离线官方为数字，keygen 固定 '0'）
  code[1] = 校验字符 = adjacent_char_diff_sum(code[3:])   # 相邻 ASCII 差和 % len
  code[3:] = base64( payload )                            # 标准 base64（'+/'）

payload = sig(64) || body'
  sig   = Ed25519 签名（消息见下）
  body' = gzip(JSON) XOR sig           # 先生成 gzip，再按 64 字节周期异或 sig
```

## 4. 客户端校验链

```
1. 入口 FUN_14024c9c0：len>3 且 code[2]=='-'；核对 code[1]；base64 解码 payload
2. postProcess FUN_14024ab20（仅当 len(payload) >= 65，否则原样失败）：
     body = payload[64:]
     A: body ^= sig
     B: body = gunzip(body)          # 失败 → 原样透传（必失败）
     C: body ^= sig
     输出 = sig || body'（重新拼回 sig 头）
3. 验签 FUN_14024b1d0 / FUN_14024b630（CryptoPP ed25519Verifier）：
     sig' = left(64)
     body'' = mid(64)
     （无调试器时）body'' ^= sig        # 反调试：FUN_275930 为 CheckRemoteDebuggerPresent
     msg = body''
     verify(pub, msg, sig)
   ★ 实际验签消息 = body'' = gunzip(payload[64:] XOR sig) XOR sig XOR sig
                    = gunzip(payload[64:] XOR sig) = JSON 明文
4. 成功后返回 body''（= JSON 明文）→ 上层 JSON 解析（FUN_2442e0）→ LicenseInfo 对象
5. 状态检查 FUN_140245880：
     - pln（api==0x a0 校验）合法
     - dom（工作组）可选；非空时须匹配本机工作组或其 blake2s 短哈希
     - hwi.machineid == 现算期望设备码
     - iat + 有效期 > now 且 exp > now；过期/未生效给错误码 0x08 / 0x1f
   err=0 时主程序认为 Pro（UI 显示「专业版已激活」，本 keygen 已验证）
```

## 5. 公钥替换（Patch 原理）

官方公钥以密文内嵌，密文主体 33 字节 = 公钥 32 字节 + `0x00`（NUL 终止）。
运行时代码等价于 `cipher XOR keystream`，其中 keystream 为 **16 字节周期**：

```
KEYS   = CIPHER_BODY XOR PLAIN            # 33 字节；KEYS[:16]==KEYS[16:32]
cipher = new_pub XOR KEYS[:32] + KEYS[32] # 新公钥加密
```

- 将该 33 字节写回 `FUN_140249fa0` 的 **9 个文件偏移**（`0x2493C8..0x249400`，
  前 8 个 dword + 第 9 个 dword 首字节；第 9 个其余字节保持原样）。
- patch 后程序运行时解密出的公钥即我们的公钥 → 我们持有对应私钥可签发合法激活码。

### 持久化（可选 --persist）

`FUN_140245880` 的 4 个失败出口（RVA `0x245a14/0x245ada/0x245b12/0x245b22`，
指令 `C7 07 imm32`）把立即数改为 `0x00000000`，使状态检查总是返回成功（启动即 Pro）。
> 注：部分环境实测使对话框出现概率不稳定，默认不开启；开启后仍需公钥替换配套。

## 6. 弱点总结

| 弱点 | 说明 |
|---|---|
| 无 RSA、无服务器签名 | 只有 Ed25519 自签名，公钥内嵌可整体替换 |
| 公钥保护可逆 | keystream 由密文+明文直接推导，无密钥材料 |
| 消息=明文 JSON | 验签消息等于签名前的 JSON，无摘要/格式加固 |
| 设备绑定弱 | machineid 仅由 MachineGuid 可预测哈希派生 |
| 反调试 XOR | 只要无调试器，XOR 路径确定，可精确复现 |

## 7. 参考实现

- `keygen/algo.py`：core（本文件公式的直接实现，含自检向量）
- `keygen/cli.py`：命令行（gen/patch/verify/selftest）
- `keygen/gui.py`：tkinter 单窗界面
- `tests/test_keygen.py`：9 项自检（官方公钥还原、设备码、编解码回路、激活码验签、patch 往返）

## 8. 声明

仅供学习 / 授权逆向分析。支持正版，生产环境请购买授权。