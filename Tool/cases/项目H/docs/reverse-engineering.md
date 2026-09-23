# 逆向方法论：项目H <目标版本> 离线授权

> 记录从二进制到可运行 Keygen 的完整路径，供研究参考。

## 1. 样本概况

- 分发包：`项目H-<目标版本>-x64.zip`，主程序 `项目H.exe`（x64，Qt 6.2.4，MSVC，无壳无签名）
- MD5：`<实测哈希>`（= 官方安装版同字节）
- 授权子系统：内置 `项目H` / `Licensing_desktop`（CryptoPP Ed25519 + Qt）

## 2. 静态定位（Ghidra 12）

分析入口：字符串交叉引用是最可靠锚点。

```
"pi/activation"      → 项目H 网络 API（RVA 0x140242e90 / 0x140243a80 / 0x140243eb0）
"requestOfflineActivation" → UnlockProDialog UI 逻辑（FUN_1401b3930）
"pty_offlineLicenseCode"   → 离线激活页控件
".?AV项目H@@"    → RTTI 类型名
```

关键函数链（RVA，image base 0x140000000）：

| 函数 | 作用 |
|---|---|
| `14024c9c0` | 格式校验入口：code[2]=='-'，校验字符，base64 解码 |
| `14024f160` | 主处理：postProcess + JSON 解析 + 应用 LicenseInfo |
| `14024ab20` | postProcess：XOR→gunzip→XOR + 重拼 sig |
| `14024e6d0` / `14024b900` / `14024b1d0` | 验签包装 → CryptoPP ed25519Verifier |
| `14024b630` | 真正验签调用（`FUN_250020`） |
| `140249fa0` | 恢复官方公钥（内嵌 58 字节密文；**keygen patch 目标**） |
| `140245880` | 状态检查：pln/dom/machineid/有效期，写出 errcode |
| `140245b50` / `140288f90` | 现算期望设备码（blake2s） |
| `14026db40` / `14026dc80` | 字段 encode / decode（XOR+旋转） |
| `140275930` | 反调试（CheckRemoteDebuggerPresent）——被调试时跳过 XOR |

## 3. 动态验证（frida 17）

Qt6 容器内存布局是最大的坑：**QByteArray/QString 对象不是简单指针**。

```
QByteArray*: +0=d(QArrayData*) +8=data指针 +16=size(+24=alloc)
data = 从 +8 指针读取（不是 d+16！）
QString 同理（UTF-16）
```

关键探针与结论：

| 探针 | 结论 |
|---|---|
| hook `249FA0` onLeave | 运行解密出的官方公钥 = `86a6...` |
| hook `250020`/`24b630` | 验签消息 = gzip 解压后的 JSON 明文 |
| hook `245b50`/`288d10`/`288c00` | 期望设备码 = `62D7-B676622561`；校验字符 = 相邻ASCII差和 |
| hook `26db40`/`26dc80` | encode/decode 互逆；JSON 里 machineid 填明文即可 |
| spawn 全程 hook | 启动时**不加载**任何已存 license（离线激活无持久化路径） |
| 强制 `245880` err=0 | UI 立即显示「专业版已激活」——主程序完全信任该返回值 |

## 4. 关键突破点

1. **公钥可整体替换**：官方公钥密文 `cipher = pub XOR keystream`，keystream 由
   明文/密文直接推导 → 任意新公钥都能加密回写，9 处文件偏移固定。
2. **验签消息=明文 JSON**：postProcess 的 A/C 两次 XOR 与验签前一次 XOR 完全抵消，
   消息就是签名时的 JSON 字节。
3. **machineid 自洽**：期望设备码格式使 `(len-dash-2)/2 = 6` 恒成立，生成端
   无需预知 len 即可构造。
4. **主程序信任 errcode**：即使 license 对象字段全空，只要 `FUN_245880` 返回 0
   UI 即显示已激活 → 持久化 patch 点。

## 5. 端到端验收（已完成）

```
1. keygen patch 出 patched 项目H.exe（公钥换成自持密钥对）
2. keygen gen 生成激活码（按本机 MachineGuid）
3. 项目H GUI：输入授权码 → 离线激活 → 粘贴激活码
4. 界面显示「项目H 2 专业版已激活」「个人版 (1 设备)」✅
5. frida 复核：运行中解密公钥 = keypair.bin 公钥 ✅
```

## 6. 已知限制

- **离线激活不落盘**：此版本离线激活成功状态仅在内存（多次 frida 全量 IO hook
  均未观察到 config/注册表写入），重启后回到免费版。官方在线激活才有持久化。
- 可选 `--persist` patch 可让启动即 Pro，但需配套公钥替换且对话框行为偶有回退。
- 在线激活响应与离线激活共用验签链，理论上也可伪造（同公钥机制），
  但服务端流程（email+序列号）非 keygen 当前覆盖范围。

## 7. 经验

1. 字符串 xref 定位比猜函数名高效得多；Qt moc 字符串是天然锚。
2. frida 读 Qt 容器务必先确认 +8/+16 布局，否则浪费时间。
3. 反调试分支（CheckRemoteDebuggerPresent）会在调试态改变 XOR 路径，务必无调试器复现。
4. 覆盖 4 个失败出口的持久化 patch 已用「逐项保留」方法验证因果（仅个别出口的改动
   不影响启动存活；全量在干净目录存在对话框回退，属可接受实验态）。