# 项目G <目标版本> 逆向证据链（reverse-engineering）

本文给出授权体系还原的关键证据：函数地址（VA，ImageBase 0x140000000）、字符串常量、
反汇编结论与动态验证记录。样本：项目G.exe SHA256
`<实测哈希>`
（MD5 `<实测哈希>`，安装包 NSIS 3.12 解包，内层 项目G.7z）。

## 1. 反汇编方法

Ghidra headless 全量分析在 27MB Qt 二进制上耗时过长且环境易中断，改用
**Python 确定性扫描**：解析 PE 节表 → `.rdata` 定位目标字符串 VA →
扫描 `.text` 中所有 `LEA r64,[rip+disp32]`（`48/4C 8D /r mod=00 rm=101`）计算引用点 →
对引用点局部分片线性反汇编（rizin `pd`）。零分析器依赖，秒级完成。

## 2. 函数入口表

| 函数 | VA | 说明 |
| :--- | :--- | :--- |
| `项目G::isLicensed(void)` | `0x140b83910` | 启动授权判定（补丁目标，偏移 0xB82D10） |
| `项目G::activate(const QString&)` | `0x140b82640` | 激活入口（项目G.cpp L341 日志） |
| `项目G::readIni` | 0x140b85xxx 区 | 读 INI 许可（"license key data empty" 引用 0x140b85631） |
| `项目GV2::isLicensed(...)` | `0x140ba1d70` | 本地复验：sha384(p) vs payload["key_hash"] |
| `项目GV2::writeIniFromPayload` | `0x140ba7060` | 写 INI `Others/reg_id`(Base64)/`reg_key` |
| `项目GV2::handleDeviceReplyInternal` | v2 区 | 服务器响应处理（"MD5 signature check failed" 引用 0x140ba4fbd） |
| `checkLicense` | `0x14046a264` | 每次启动执行；分支 free-trial @0x14046a3e7 / pass @0x14046a6b6 |

## 3. 关键常量

| 常量 | VA | 值 |
| :--- | :--- | :--- |
| 签名模板 | `0x1412a0650` | `!1(2.1,8&_C]o=r%e^y;`（19 B） |
| AES 密钥（grace token） | `0x1412a08e0` | `_项目G_this is a constant_key+WWWWin` |
| ChainingMode | `0x1412a0720` | `ChainingModeCBC` |
| 字段 | 0x1412a3ad8 / 0x1412a3b00 | `grace_deadline` / `ids_hash` |
| INI 路径 | `0x1412a18b0` / `0x1412a1518` | `Others/reg_id` / `Others/reg_key` |

## 4. 校验语义

```
V1 网络激活: POST property_key -> 服务器签发（不可离线复现）
V2 响应签名: sig = hex(sha1(TEMPLATE + payload[32:])) == payload[0:32]
V2 本地复验: hex(sha384(payload_utf8)) == payload["key_hash"]   ← 自引用，无解
grace token: AES-CBC 解密 -> JSON{ids,last_ok,deadline} 校验
```

## 5. 动态验证记录（Frida 17.16）

| 实验 | 结果 |
| :--- | :--- |
| 传 7 种 key 调 `activate` | 均 `licenseModeForKey=mode=1` 且 `activate=0`（被拒） |
| 传构造 payload 调 `V2::isLicensed` | 均 0；`QCryptographicHash::hash` 未触发（早退） |
| 原版启动 | `[branch] free-trial @46a3e7` |
| 补丁版启动 | `[branch] pass @46a6b6`；进程存活 10s+；无 INI 许可读取 |
| 防回退守卫 | 注册 → revert 模拟覆盖 → `--silent --fix` 自动恢复 `8591c808...` |

## 6. 结论

- keygen 离线不可行（服务器签发 + 自引用校验）
- 本地判定点单一且无自校验 → 补丁路线成立，重启持久，升级覆盖可由登录守卫自动修复
- 工具仅修改本地判定，不涉及服务器/计费逻辑；界面内置官方购买链接引导正版