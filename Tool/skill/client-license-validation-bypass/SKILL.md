---
name: client-license-validation-bypass
description: >-
  Authorized-testing playbook for defeating client-side license / activation / card-key validation across runtimes (native PE, .NET/Mono, Electron, JVM, Python/Go/Rust) and models (offline license & signature, online activation, card-key/subscription/trial, Token/JWT, hardware-bound). Use to locate validation logic and endpoints, decide server-side vs client-side authority, judge forge-vs-relay, and test backdoors, endpoint takeover, memory patching, protocol/injection flaws, key extraction, and payload carving. Authorized samples only; ships a vendor-side hardening checklist.
---

# SKILL: Client License / Activation / Card-Key Validation — Expert Attack Playbook

> **LOAD**: 桌面/原生客户端许可校验实战手册。覆盖多运行时(原生 PE / .NET·Mono / Electron·Node / JVM / Python·Go·Rust 冻结 / 加载器+密文载荷)与多校验模型(离线许可文件·签名、在线激活、卡密·订阅·试用、Token·JWT、硬件绑定)。
> **四问**(开测即答,任何客户端通用):
> ① **权威在哪** — 校验是服务器审核,还是纯本地判定(离线许可/签名验证)?
> ② **本地能否完成握手** — 能**伪造成立**,还是**只能中继**上游?
> ③ **有无捷径** — 后门/调试开关/环境变量/隐藏参数?
> ④ **功能是否与校验分离** — 真功能能否脱离校验单取即用(载荷/DLL/脚本/资源)?
> **边界**: 仅已授权样本;与 scope、影响闸、证据门槛冲突时以后者为准。禁 DoS 扩大化、禁真实凭据外泄。

---

## 【G-Auth】授权门(先于 §0 的唯一起始门)

> **本手册仅用于已授权的白盒安全测试实验室环境。**

**规则**: 每接**新目标**,第一件事是**询问用户是否已获得该目标的测试授权**。

| 答复 | 动作 |
|---|---|
| **无授权 / 不确定 / 未回答** | **立即停止**。不分析、不下载、不运行、不试探。说明需要什么, 等待。 |
| **已授权** | 进入 §0 执行顺序门, 此后**全速工作**。 |

**双向约束(两个“最大”)**:
- **防误用(硬闸)**: 授权**逐目标**确认, 换目标重新确认; 不得以“之前说过”跳过; 确认前不做任何实质分析。
- **保效率(零摩擦)**: **一次确认即放行**, 不反复询问; **不缩减输出**、不堆免责声明、不降低交付标准。**闸门只放在门口, 不放在路上**。

**边界**: 授权覆盖“能不能测”; **下载/安装/写文件/改环境变量**仍需单独确认。

---

## 0. 执行顺序门(先读本节,按门推进)

先定权威归属,再选打法。门是通用骨架,案例仅示范一条路径。

| 门 | 判据 | 命中则 | 未命中 |
|---|---|---|---|
| **G0 权威定性** | 断网/改系统时钟/改本地许可文件,功能是否仍可用? | 纯本地校验 ⇒ 走**离线路线**(§2.4、§7.1) | 需联网 ⇒ 服务器权威,转 G1 |
| **G1 样本定性** | 静态 10 分钟能否判出运行时/壳/子系统/依赖指纹? | 见 §1–§2 | 情报不足转动态 §3 |
| **G2 写入判死归因** | 改它自己内存里 1 个无害字符,4s 后仍存活? | 存活 ⇒ **无自保护**,可继续改内存 | 崩溃 ⇒ 疑有自保护,先按"值非法"排除再定论,转网络层接管 |
| **G3 端点发现** | 盘上/静态有明文 URL/IP 吗? | 直接读 | **内存取证**(§4.1) |
| **G4 响应判定** | 多次会话令牌是否变化?时间戳是否回填?体长是否恒定而内容随会话变? | 命中 ⇒ **会话绑定** ⇒ 只走中继/DoS(§8.5) | 未绑定 ⇒ 金样回放(§8) |
| **G5 载荷判定** | 服务器下发载荷:导出表为空?仅导入基础运行库?无自校验/不联网? | 成立 ⇒ **取载荷即用**(§9),性价比最高 | 载荷有校验 ⇒ 转 §7·6 密钥提取 / §8.5 中继 |
| **G6 交付** | — | 结论分级(确认/现象/N-A)+证据路径+载荷指纹+§10 防护清单 | — |

**通用禁令(踩过坑)**: ① 未过 G2 不得批量改内存;② G4 判绑定后别再试字段二分;③ 不轮询抢补丁竞速(见 §4.3);④ 等长替换禁前导零/NUL/空格填充;⑤ 结论必须区分"伪造成立"与"仅能中继"。

**门 → 决策树 → 章节映射**(消 §0 与 §7 的重叠):

| 门结论 | 决策树路径(§7) | 主章节 |
|---|---|---|
| G0 纯本地 | 1. 离线判定直接改 | §7.1 |
| 任意阶段发现捷径 | 2. 后门/调试开关 | §7 |
| G4 未绑定 | 4. 密文回放(金样) | §8 |
| G4 绑定 + 上游可达 | 5a. 透明中继 | §8.5 |
| G4 绑定 + 上游不可达 | 5b. 拒绝服务 | §5.3 |
| G5 成立 | 7. 取载荷 | §9 |
| 上述皆不通 | 3/6. 协议注入 / 密钥提取 | §7·3、§7·6 |

**退出/升级判据(防死磕)**: 单条路径 ≤3 轮无进展即挂起转下一路(呼应禁令③,竞速类"必输"路径直接放弃);内存补丁累计崩 2 次 ⇒ 停改内存转网络层;金样回放连续静默退出 ⇒ 判会话绑定转中继;三大路径(离线改/回放/中继+取载荷)全不通 ⇒ 记为"现象级/需人工深逆",附已排除项与证据,勿无限重试。

---

## 1. 目标画像与分类(先分型,再选工具)

优化点:先按维度归类,后续各节据类分流,避免只会打一种客户端。

**运行时维度**
- **原生 PE(C/C++/加载器)**: PE 头+节表解析;密文段+运行期自解密常见;§2.1。
- **.NET / Mono**: 托管元数据可倾出;IL 可反编;ReadyToRun/AOT 例外;§2.2。
- **Electron / Node**: `asar` 包、`app.asar` 内 JS;`process.env`、V8 快照;许可逻辑常在明文 JS 或 native addon(`.node`)。
- **JVM(Java/Kotlin)**: jar/class 可反编(CFR/Procyon);混淆(ProGuard)靠字符串/调用图定位;许可常在 `verify*/License*` 类。
- **Python/Go/Rust 冻结**: PyInstaller/py2exe 可解包取 `.pyc`;Go 有符号表(`gopclntab`)可还原函数名;Rust 靠字符串+panic 路径。

**校验模型维度**
- **离线许可文件/签名**: 本地 `.lic/.key/注册表`,非对称签名验证;攻击面=签名验证逻辑本身(§7.1)。
- **在线激活/心跳**: 首次激活+周期心跳;攻击面=端点接管+响应伪造(§5–§8)。
- **卡密/订阅/试用**: 卡密上行、服务端返回剩余期;试用期常本地存时间戳(§2.4)。
- **Token/JWT**: 校验签名或调用校验端点;弱密钥/`alg:none`/本地不验签是经典缺陷。
- **硬件绑定**: 机器码=MAC/磁盘序列/CPUID 哈希;可 hook 采集函数伪造机器码。

**协议维度**: HTTP/HTTPS、WebSocket、gRPC、裸 TCP 自定义二进制。判协议决定"金样回放/中继/监听器"的实现(§8)。

**平台等价维度**(本手册命令多为 Windows,以下给 macOS/Linux 等价物,方法不变):

| 能力 | Windows | macOS | Linux |
|---|---|---|---|
| 可执行格式 | PE(§2.1) | Mach-O(`otool`/`nm`/`class-dump`) | ELF(`readelf`/`nm`) |
| 代码签名/公证 | Authenticode | `codesign -dvvv` + notarization | 无强制,GPG/自签常见 |
| 注入/hook | DLL 注入、Detours、Frida | `DYLD_INSERT_LIBRARIES`、Frida | `LD_PRELOAD`、`ptrace`、Frida |
| 端点接管 | `netsh add address`/hosts(§5.3) | `/etc/hosts`、`pf` RDR | `/etc/hosts`、`iptables/nft DNAT` |
| 内存读取 | `OpenProcess`+`ReadProcessMemory` | `task_for_pid`+`vm_read`(需 SIP 关/授权) | `/proc/<pid>/mem`、`process_vm_readv` |
| 许可存储 | 注册表/`%APPDATA%`/ADS | `~/Library`、plist、Keychain | `~/.config`、`~/.local`、`/etc` |
| 驱动/GUI 观测 | UIAutomation | AXUIElement/Accessibility | AT-SPI、`xdotool` |

---

## 2. 静态解剖(按运行时分流)

### 2.1 原生 PE 壳
PE 头+节表纯 struct 解析 → 熵剖面定密文段 → 明文导入名/字符串定角色 → 其余转动态。**不在壳上硬磕**。
- 节表真伪: `RawSize=0 而 VSize 巨大、节名自定义且重复 = 表被伪造`;仅 1~2 段有 raw 且熵≈7.8 = 全密文载荷。
- 入口点落在密文段内 ⇒ 运行期自解密,静态字符串必空(勿据此判死)。
- 无 `ws2_32/winhttp` 静态导入 = 动态加载;密文段内散落明文 DLL 名 = 运行期手工解析导入。
- 子系统: `Subsystem=3`⇒控制台⇒§3.1;`=2`⇒GUI⇒§3.2。

### 2.2 .NET / Mono 手解(无 SDK/ILSpy 也能倾)
元数据根 `BSJB`;流目录偏移相对根;`#~` 24 字节头+行数表;直倾 `#Strings`/`#US`(长度含尾标志字节)/`#Blob`/`#GUID`。表头版本被改或行无法对齐 = 定制布局,转动态。`ldstr(0x72)` 命中寥寥 = ReadyToRun/AOT,IL 不在盘上。COM 描述符(数据目录 14)非零=托管;含 CoreCLR 源码路径=自举宿主。运行时自解压盯 `%TEMP%\.net\<App>\<hash>\`,趁进程存活整树拷贝。

### 2.3 其它运行时速解
- **Electron**: `npx @electron/asar extract app.asar out/`;搜 `license/activate/verify/machineId`;native addon 转 §2.1 原生流程。
- **JVM**: 解 jar → CFR 反编 → 找 `License/Auth/verify/checkSignature`;混淆时靠常量字符串与网络调用点反推。
- **Python 冻结**: `pyinstxtractor` 解包 → `.pyc` 反编(decompyle3/pycdc);校验逻辑常明文可读。
- **Go/Rust**: 字符串扫端点/错误文案;Go 用 `gopclntab` 还原函数名定位 `verify`。

### 2.4 离线许可与本地状态
- 许可文件: exe 同目录/`%APPDATA%`/注册表下 `*.lic/*.key/license.dat`;判其是否被签名(尾部固定长 blob=签名)。
- 试用期存储: 注册表隐藏键、`%APPDATA%` 时间戳文件、备用 ADS 流;删/改后看是否重置=本地时间判定。
- 存卡: exe 同目录 `*_card_save.json` 或注册表键常明文存卡密。找不到不必纠缠——**卡密往往就在每条请求头里**(§6.1)。

- 通用线索词: 类型/函数名含 `Auth/Login/Heartbeat/Card/Key/License/Activate/Verify/Sign/Aes/Rsa/Jwt`、`*Embedded.config.json`、`IsDevMode`、`--dev`、`machineId`。

### 2.5 商用保护壳 / 许可 SDK 指纹(先辨型,定"绕逻辑 vs 提功能")
先认厂再决策:**壳**只保护/加密,目标是脱壳或运行期取内存;**许可 SDK**是可 hook 的鉴权层,目标是 hook 校验点或模拟。

| 目标 | 类别 | 静态指纹 | 首选打法 |
|---|---|---|---|
| VMProtect | 壳(虚拟化) | 节名 `.vmp0/.vmp1`、大量间接跳转 | 不硬逆 VM;运行期内存转储 OEP 后取明文(§4.1) |
| Themida/WinLicense | 壳(SecureEngine) | 节名 `.themida`、反调试重 | 先过反调试再内存转储;许可查询点 hook |
| Enigma Protector | 壳+许可 | `enigma` 字符串、虚拟文件系统 | 断激活 API,改返回;取内存资源 |
| Denuvo | 壳(游戏 DRM) | 触发式加密块、大 `.arch` 节 | 极高成本;仅内存态取功能,不逆 |
| FlexLM/FlexNet | 许可 SDK | 导入 `lc_checkout/lc_init`、`FLEXlm` 串、`@host` 许可格式 | hook `lc_checkout` 返回 0(成功);或伪造 license server |
| Sentinel HASP/LDK | 许可 SDK+dongle | `hasp_login/hasp_decrypt`、`haspvlib` | dongle 模拟(HASP emulator);hook `hasp_*` 返回 |
| Wibu CodeMeter | 许可 SDK+dongle | `CodeMeter` 服务、`wibu` 串 | hook `CmAccess/CmCrypt`;模拟 CmContainer |
| Cryptlex/LicenseSpring | 云许可 SDK | `LexActivator`、`IsLicenseGenuine` | 端点接管+响应伪造(§5–§8);hook 校验返回 |

判据: 有以上指纹先查厂商已知弱点(hook 点/模拟器可行性),再回主流程;强壳(VMProtect/Themida/Denuvo)一律走**运行期内存取功能/取载荷**(§4.1、§9),勿硬逆。

---

## 3. 动态观测

### 3.0 写入判死归因(任何内存改写之前,20 秒)
后果: 无此步会把"补丁值非法"误判为"有反内存自保护"(案例白烧 3 轮)。
做法: 定位它自己的一处无害串(已保存卡密/窗口标题),改 1 字符 → 等 4s → 存活则回改再等 4s。存活 ⇒ 无自保护,后续崩溃一律先归因"值非法/改坏相邻结构"。

### 3.1 控制台客户端(stdin 驱动 + stdout 预言机)
- 必须重定向输入,否则卡在交互提示(常弹 `请输入(Y/N)` 等 ~60s 超时——**这才是"启动后 ~60s 才联网"的真因**,勿误读为"自退"):
  `cmd /c ""sample.exe" < yes.txt > out.txt 2>&1"`(`Start-Process` 无 stdin 会停住)。
- **stdout 原文即阶段预言机**: 卡密回显 → `验证成功…` → `注入成功!` → `清理完成!`。
- **失败模式**: 未通过时"一字不出直接退出"——无输出本身即判据,别等错误文案。
- 实现陷阱: `StreamReader.EndOfStream` 同步读会**阻塞主循环**(轮询/转储全停摆);改文件重定向 + 轮询文件长度。

### 3.2 GUI 客户端
UI Automation 枚举 Edit/Button/CheckBox 的 Name/Value,`ValuePattern.SetValue` 填卡,`InvokePattern` 点击;窗口文本("响应解密失败"等)即错误预言机。Electron/CEF 界面可挂 DevTools/远程调试端口直接读渲染进程状态。

### 3.3 API/系统调用观测(定位校验点)
- 通用探针: API Monitor / Frida / ETW 挂 `getaddrinfo`、`connect`、`send/recv`、`CryptVerifySignature`、时间函数、文件/注册表读。
- 断在校验函数返回处改返回值(patch `AL=1`)是"是否纯本地判定"的最快验证。

---

## 4. 端点发现

### 4.1 硬编码 IP/URL 场景: 内存取证是主路径
盘上全空时直接扫运行中进程内存(同用户进程可 `OpenProcess`+`ReadProcessMemory`):
- ASCII: `\d+\.\d+\.\d+\.\d+`、`host:port`、`https?://…`、`wss?://…`;
- 二进制 `sockaddr_in`: `02 00 <port_netorder> <ip_4B>`(端口网络序,如 50731=`C6 2B`);
- 裸 `in_addr` dword(如 `101.35.222.163`⇒`65 23 DE A3`)。
命中即取 ±64B 上下文 → 读出完整请求模板与 URL。

### 4.2 连接与 DNS(别指望一定有痕迹)
客户端可能**直连硬编码 IP** ⇒ `displaydns`/`Resolve-DnsName` 全程无新记录,不代表没联网。轮询(`GetExtendedTcpTable`、netstat 重定向)**窗口 ≥120s**;单次连接只在某一刻出现,漏抓属常态。走系统代理时按"全进程"过滤,但先实测是否真用代理。

### 4.3 配置块解密时间线(决定一切时序)
配置(IP/URL/模板)常**在一个极短窗口内一次性成型**(案例 21 份副本落在同一 **13ms** 内)。⇒ "轮询→命中→补丁"几乎**必输**(materialize→connect 只隔微秒),冻结(`SuspendThread`)**也切不开**该窗口。要么放弃竞速(转 §5.3),要么在中继层做(§8.5)。

### 4.4 抓包与 TLS 剥离
明文 HTTP 直接监听;HTTPS 先试系统代理+自签 CA(mitmproxy);抓不到即转 §4.1 内存取证。
**证书固定绕过(按运行时选点)**:
- **原生/OpenSSL**: Frida hook `SSL_CTX_set_verify` 强制 `SSL_VERIFY_NONE`,或 hook `X509_verify_cert` 返回 1;BoringSSL 同理。
- **Schannel(Windows)**: hook `CertVerifyCertificateChainPolicy` 令 `dwError=0`。
- **.NET**: hook/patch `ServerCertificateValidationCallback`/`RemoteCertificateValidationCallback` 恒返 true;或环境层信任自签 CA。
- **JVM**: 替换 `X509TrustManager.checkServerTrusted` 为空实现(Frida `frida-java-bridge` 或字节码改写);处理 `TrustManagerFactory` 自定义 pinning。
- **Electron/Node**: `NODE_TLS_REJECT_UNAUTHORIZED=0` 或 hook `tls.checkServerIdentity`。
- 兜底: 无法 hook 时用 `SSLKEYLOGFILE` 导出会话密钥,Wireshark 解密仅供分析(不改流量)。

---

## 5. 端点接管

### 5.1 等长替换的合法值规则
等长只是必要条件;**值本身必须合法**: 数值形 IPv4 不得有前导零(`127.000.000.001` 被 `getaddrinfo/inet_pton` 拒收)、不得含 NUL/空格;域名不得以点/空格结尾。
位宽不足用**同长度回环地址**: `127/8` 全域回环,14 字符可用 `127.100.100.10`;主机名位宽不足优先同名解析(如 `x.localtest.me`=14)而非截断。
替换前 `ipaddress.ip_address()` 自检;替换后观察 4s 存活。端口亦可等长改(5 位)但须合法且未被占用。

### 5.2 内存补丁: 副本角色表与上限(实测)
| 副本角色 | 上下文特征 | 单独打 |
|---|---|---|
| 请求模板 | `GET /verify … Host: <ip>:<port>` | 无效(只改 Host) |
| host:port / URL 常量 / 裸字段 | `<ip>:<port>`、`http://…`、单独 `<ip>` | 无效 |
| 二进制 `sockaddr_in` | `02 00 <port> <ip>` | 无效 |
| **多副本组合 2~3 处** | 以上混打 | **有效**(案例两次成功) |
上限: 命中 **2~3 处** 安全;一次打 **13~24 处** 进程必崩(含已释放/复用堆块被写坏)。角色错打无效、全量打崩。

### 5.3 提权回环接管(零竞速,案例决定性一招)
```powershell
netsh interface ipv4 add address 1 <c2_ip> 255.255.255.255   # 管理员：C2 IP 抢到回环 → 流量直达本地
netsh interface ipv4 delete address 1 <c2_ip>                # 收尾必删
```
- **副作用(必须写明)**: 抢到本机后**你也够不到真服务器**(同机代理同样回环)⇒ 只能拒绝服务或纯中继,做不到"边转发边伪造"。只抢不通 ⇒ 客户端收到本地响应即静默退出,表现为"全体卡密突然失效",是有效 DoS(影响面大,慎用)。
- 提权子进程会被会话/作业回收: 用**一次性脚本 + 结果落盘**,别设计常驻控制器。
- 跨平台等价物: hosts 文件重定向(域名场景)、`iptables/pf` DNAT(Linux/mac)。

### 5.4 本地监听器陷阱
绑前查占用(`Get-NetTCPConnection -LocalPort <p> -State Listen`)。Windows `SO_REUSEADDR` **允许同端口双绑** ⇒ 旧实例不退会让请求落到旧实例/别的进程。旧进程持日志句柄会让 `Remove-Item` **静默失败**(会看到两条 start 混写同一日志)⇒ 每轮独立日志名。**绑 `0.0.0.0` 而非 `127.0.0.1`**,才能让任意 `127/8`(含被接管的 C2 IP)命中。每次请求落盘 JSONL(方法/路径/全部头/体 hex)。

---

## 6. 握手与响应判定

### 6.1 请求/响应样例(案例,示范如何拆解字段角色)
```
GET /verify HTTP/1.1   Host: <ip>:<port>   User-Agent: HTTP-Getter/1.0
Auth: <base64: 明文占位(如分号)+每请求变化的密文块>   uk: <卡密——常见明文>   xt: <客户端时间戳>

HTTP/1.1 200 OK
vt: <会话令牌,客户端会在下一跳回送>   vs: <每响应都变>   xt: <服务端回填>
content-length: <恒定>   content-type: application/json
{"o": true, "m": "验证成功，卡密类型：天卡，剩余时间：N分钟", "a": ["game.exe"], "d": "http://<ip>:<port>/api/dll"}
```
**通用拆法**: 逐字段标注角色——布尔通过位(`o`)/回显文案(`m`)/行为参数(`a`,如注入目标)/下一跳地址(`d`)/会话令牌(`vt/vs`)/时间戳(`xt`)。角色表决定回放能否成立。

### 6.2 会话绑定判据(G4,协议无关)
| 观察 | 结论 |
|---|---|
| 多次独立会话令牌都不同 | 响应与会话绑定 |
| 时间戳由服务端回填(≈请求时间戳) | 时间戳参与绑定 |
| 体长恒定而体内容随会话变 | 体被签名/封送 |
命中 ⇒ 本地无法复算 ⇒ 直接 §8.5 中继。均不命中 ⇒ §8 金样回放可破。

### 6.3 加密/签名分析(不破钥也能赢)
外层明文信封 `{"soft":..,"data":"<hex>","sign":"<md5>"}` 先看,再推内层。
- **模式判定**: CBC+固定 IV——自选 16×A / 16×B 各取一次密文比较逐块差异;块 0 不变=IV 固定;差异自块 k 起链式蔓延=CBC;仅局部差异=ECB/流式。
- **免 IV 筛钥**: 候选 K 验 `D_K(C_k) XOR C_(k-1)` 是否含自选明文片段。
- **签名**: `sign` 常为 `MD5(data+盐)`,两样本可排除简单组合;HMAC/RSA 则转密钥提取(§7·6)或中继(§8.5)。
- **JWT**: 先看 `alg`——`none`/弱 HS256 密钥/本地不验签均可直接伪造。

---

## 7. 绕过决策树(按易至难,先定权威再选路)

1. **离线判定直接改**(过 G0 为本地): patch 校验函数返回、改本地许可文件、伪造签名(若本地不验或验签逻辑可绕)。§7.1。
2. **后门/捷径**: `--dev` / `ASPNETCORE_ENVIRONMENT=Development` / 调试参数 / 隐藏环境变量 → 零登录零心跳。先试。
3. **协议/注入类**: 内层模板若 `String.Format` 风格且不转义 ⇒ 卡密字段即注入点;亦可注入补全 `code/o/msg/dll`;弱 Token/JWT 伪造。
4. **密文回放(金样)**: 仅当 G4 判定**未**会话绑定(§8)。
5. **会话绑定** ⇒ **透明中继**(上游可达,唯一能"本地完成握手"的正解)｜ **拒绝服务**(上游不可达,如 §5.3 抢 IP)。
6. **密钥提取**: 密钥常为 `.text` 内联字节,以块验证法暴力筛节区;或内存转储/调试器断解密函数;托管/JVM 直接读常量。
7. **取载荷**(§9): 功能若在服务器下发的载荷里且无自校验 ⇒ 脱加载器直接用。性价比最高,常被忽略。

### 7.1 离线签名/许可绕过要点
- 判验签是否真执行: patch 掉验签调用看是否仍可用(很多客户端"验了不看返回")。
- 非对称签名不可伪造时,改攻验签**逻辑**(返回值 patch、比较跳转反转)或替换内置公钥为自控密钥后重签许可。
- 时间试用: 冻结/回拨系统时钟、清本地时间戳存储、hook 时间 API。

**公钥替换重签(签名不可伪造时的正解,五步)**:
1. 定位内置公钥: 静态搜 PEM 头 `-----BEGIN PUBLIC KEY-----`、DER 序列 `30 82`、或 RSA 模数常量;托管/JVM/JS 常为明文资源。
2. 生成自控密钥对(同算法同位宽,如 RSA-2048/Ed25519)。
3. 就地等长替换公钥(DER/模数须**同长度**,遵 §5.1 合法值规则)或改资源文件;固定曲线的 Ed25519 直接替 32 字节公钥。
4. 用自控私钥对伪造许可/响应重签,喂给客户端。
5. 兜底: 公钥被哈希校验或多处冗余 ⇒ 回退到 patch 验签返回值/反转比较跳转(§7·6 定位校验点)。
- **验签点定位**: hook `CryptVerifySignature`(Win)、`RSA_verify/EVP_DigestVerify`(OpenSSL)、`Signature.verify`(JVM)、`RSACng.VerifyData`(.NET);断点看比较结果落点即 patch 目标。

---

## 8. 金样回放与透明中继

### 8.1 金样回放(仅未会话绑定适用)
1. 本地监听器捕获登录请求 → 记录 `data/sign`。
2. 注入捕获: 卡密填注入串(闭合卡密值+补全 code/msg/tok/expire)→ 此请求密文即金样。
3. 回放: 对任意登录/心跳一律应答金样。
4. 验证: 登录窗关闭 / 主面板端口监听 / 进程存活 > 两个心跳周期。
5. 失败判读: **静默退出** = 会话绑定或格式不符(转 §6.2→§8.5);**缺字段崩溃** = 可用"崩溃 vs 存活"逐字段二分。
6. 包装: `pythonw` 无窗口 + 一键启动 + 补丁持久化说明。

### 8.5 透明中继(端点已接管但无签名密钥)
监听 C2 端口(或接管后任意 `127/8`),把客户端请求 **verbatim** 转发真服务器、真响应 verbatim 回送。要点:
① 请求头一字节不改(保留 `Auth/uk/vt` 等会话字段);
② 按 `content-length`(或协议帧长)收满再回;
③ 支持 keep-alive/多帧多请求;
④ 上游不可达返回 502 而非静默断链;
⑤ 请求+响应落盘(二进制 blob 即载荷)。
WebSocket/裸 TCP 同理:按帧透传,勿改握手。
**结论措辞(必须区分)**: "端点可被本地接管并完成握手(中继)" ≠ "可本地伪造成立(会话绑定挡住了)"。

---

## 9. 取载荷 Payload Carving(性价比最高的一路)

- **适用**: 加载器只做校验、真功能由服务器下发 DLL/驱动/脚本/资源;或下载端点可被接管(§5/§8.5)。
- **判据**: 真响应 `content-length` 与实际 blob 比对;PE 场景 blob 头 `MZ` 且 `e_lfanew` 指向 `PE\0\0`;**导出表为空 + 仅导入基础运行库(如 kernel32)** ⇒ 无自校验、不联网 ⇒ "功能与校验分离"成立。其它格式同理判其是否自带校验/回连逻辑。
- **手法**: ① 内存定点扫 committed readable 区域找 `MZ`+PE(或对应魔数),命中即落盘(本体+0x60000 余量);② 对下载端点做 verbatim 中继(§8.5)直接抓响应体。
- **交付**: 载荷 SHA256/MD5、导入导出清单、字符串表、行为参数(如注入目标进程名,响应 `a` 字段)。
- **厂商利用点**: 逆向载荷得 hook 点/偏移 ⇒ 完整性与行为检测。行为特征比指纹稳(换载荷即换指纹): 进程内**无模块记录的私有可执行内存**、命名文件映射加载、`SetThreadContext` 改写线程上下文。

---

## 10. 厂商侧防护清单(交付客户)

1. **凭据禁止明文上行**(案例 `uk` 头就是卡密明文 ⇒ 任何 MITM/假服务器可采集有效卡密): 改整请求 HMAC/AEAD(机器码+时间戳+随机数)。
2. **响应必须带服务器侧签名且客户端真验证**: 会话绑定(令牌+回填时间戳+封送体)有效挡住本地伪造——这是正解,应保持。
3. **全链路 HTTPS + 证书固定**: 明文 HTTP 让端点、凭据、载荷 URL 与本体全程裸奔。
4. **权威在服务端,校验在载荷内,功能与校验不能分离**: 加载器只做校验、真功能在下发载荷里且该载荷无自校验 ⇒ 取载荷即白嫖。
5. **载荷下发必须验签**;**行为目标必须鉴权**(如注入:进程名+文件签名+模块特征——案例把 `ping.exe` 改名 `game.exe` 即被当作合法目标注入)。
6. **失败分支勿静默退出**: 挡不住攻击者,还让自己无法排障;但也勿泄露过细错误。
7. **离线许可用非对称签名 + 客户端真验签 + 内置公钥防替换**;时间判定勿仅依赖本地时钟。
8. 加**内存完整性自校验**;自保护(内存读取拦截/元数据定制/进程伪装)值得肯定,但救不了应用层疏漏。

---

## 11. 工具箱速查

| 需求 | 手段 |
|---|---|
| PE/熵/节表真伪 | 纯 Python struct 解析 |
| .NET 四堆倾出 | BSJB→流目录→#Strings/#US/#Blob |
| Electron/JVM/Py 解包 | `@electron/asar`、CFR/Procyon、pyinstxtractor+反编 |
| 校验点定位 | Frida/API Monitor/ETW hook `getaddrinfo/connect/Crypt*/时间API` |
| 端点内存取证 | `OpenProcess`+`VirtualQueryEx`+`ReadProcessMemory` 扫 ASCII/IP/`sockaddr_in` |
| 连接观测 | P/Invoke `GetExtendedTcpTable` 轮询(≥120s) 或 netstat 重定向 |
| 抓包/TLS | mitmproxy + 自签 CA;固定时 Frida/SSLKEYLOGFILE |
| 控制台驱动 | `cmd /c "x.exe" < yes.txt > out.txt 2>&1` |
| GUI 驱动 | PowerShell UIAutomation;Electron 用 DevTools/远程调试端口 |
| 端点接管 | 等长合法值替换 / `netsh … add address 1 <ip> 255.255.255.255` / hosts / DNAT |
| 本地握手 | python `http.server`/裸 socket + JSONL 落盘;或 verbatim 中继(§8.5) |
| 取载荷 | 内存定点扫魔数(`MZ`+`e_lfanew`)命中即落盘(§9) |
| 块差异分析 | cryptography ECB + XOR;JWT 用 `alg`/弱密钥爆破 |

---

## 12. 陷阱日志(单条即坑)

- 等长替换值非法(前导零/NUL/空格) ⇒ 目标静默退出;先做 §3.0 归因再改。
- 补丁数量阈值: 2~3 处安全、13~24 处必崩;副本有角色,错打无效。
- 配置块 13ms 一次性成型 ⇒ 轮询抢补丁必输,冻结切不开微秒窗口。
- `StreamReader.EndOfStream` 同步读 stdout 阻塞主循环。
- Windows `SO_REUSEADDR` 同端口双绑;旧监听器不退 ⇒ 请求落别处;旧日志句柄 ⇒ `Remove-Item` 静默失败。
- 提权子进程被回收 ⇒ 一次性脚本 + 结果落盘。
- 内存转储必须**同步记录 region 地址表**,否则拼接式转储无法定位数据。
- 沙箱 EPERM = 管道边界,勿重试,改重定向文件或纯 P/Invoke。
- `Get-NetTCPConnection`/WMI 在受限环境静默空返 ⇒ netstat 文件重定向或原生 API。
- PowerShell 中 `$pid` 为只读自动变量,勿作变量名。
- GBK 乱码是控制台显示问题,用 read 工具按 UTF-8 读文件。
- 响应填充无效 = 存活+"解密失败";有效填充+缺字段 = 崩溃退出——皆可作预言机;但**无输出即退出**时别死磕字段二分。
- 直连硬编码 IP ⇒ DNS 无痕不等于没联网;证书固定 ⇒ 代理抓不到不等于不用 HTTPS。
- "验了不看返回"常见 ⇒ 先 patch 验签调用看是否仍可用,再判是否需伪造签名。

---

## 13. 交付模板与环境清理

**报告结构(G6 落地)**——每个发现独立成条:
```
标题: <一句话缺陷,如"卡密明文上行,假服务器可批量采集">
分级: 确认利用 / 现象(疑似,未闭环) / N-A(不适用)
危害: <凭据泄露/校验绕过/功能白嫖/DoS…> + 影响面
前置: <权限/网络/权威定性 G0 结论>
复现: 1) … 2) … 3) …(命令/输入可粘贴)
证据: <抓包/内存转储/日志 JSONL 路径 + 关键截图>
根因: <本地判定 / 明文传输 / 会话未绑定 / 功能与校验分离 …>
修复映射: → §10 第 N 条
```
**指纹与产物清单**: 目标 SHA256/编译时间/签名状态;载荷 SHA256·MD5+导入导出表+字符串表+行为参数(如注入目标);端点(IP:port/URL/协议);捕获的金样/中继 blob 路径。

**环境清理总清单(收尾必做,防残留)**:
- 删接管地址: `netsh interface ipv4 delete address 1 <c2_ip>`;
- 还原 hosts / 撤 `iptables/pf` DNAT 规则;
- 结束本地监听器与提权子进程,释放端口;
- 移除注入/补丁 DLL,恢复被改的本地许可/注册表/时间戳;
- 撤销临时信任的自签 CA,清 `SSLKEYLOGFILE`;
- 归档证据后清理临时载荷副本与内存转储(按留存要求)。

---

## 14. 术语表(首现缩写)

- **权威(authority)**: 校验的最终裁决方在服务端还是本地。
- **金样(golden sample)**: 一次成功校验的完整请求/响应,未会话绑定时可无限回放。
- **会话绑定(session-bound)**: 响应含每会话变化的令牌/回填时间戳/封送体,致本地无法复算。
- **中继(relay)**: 逐字节转发客户端↔真服务器,不改内容;能"完成握手"但不能"伪造成立"。
- **取载荷(payload carving)**: 直接提取服务器下发的真功能模块(DLL/脚本/资源)脱离校验使用。
- **AEAD**: 带关联数据的认证加密(如 AES-GCM),同时保机密性与完整性。
- **DNAT**: 目的地址转换,Linux/mac 上把流量重定向到本地监听器。
- **ADS**: NTFS 备用数据流,常被藏试用期时间戳。
- **ReadyToRun/AOT**: .NET 预编译为原生码,IL 不在盘上,静态反编受限。
- **pinning**: 证书固定,客户端只信内置证书/公钥,普通代理抓包失效。
- **OEP**: 原始入口点,壳解密还原后跳转的真实入口,内存转储的定位锚。

## 附. 参考案例(单一样本,示范上述通用流程的一条完整路径)

> 用途: 以下为一个已授权的原生加载器样本,用来落地示范 §0–§12 的通用方法;数字/字段名皆该样本实测,勿当作所有目标的常量。

- **类型**: 无签名 >20MB 原生加载器,节表被伪造,全密文载荷运行期自解密,手工解析导入。控制台子系统,stdin 驱动。
- **权威**: 服务器审核;硬编码 IP 直连(DNS 无痕),配置块 13ms 内一次性成型。
- **握手**: 见 §6.1 样例;`uk` 头明文卡密,`vt/vs/xt` 构成会话绑定(G4 命中)。
- **结论**: 本地**无法伪造成立**(会话绑定),但端点**可被接管并中继**(§5.3 netsh 抢回环 + §8.5 verbatim 中继);真功能在服务器下发 DLL,该 DLL 导出为空、仅导入 kernel32 ⇒ **取载荷即用**(§9)为最高性价比路径。注入目标仅按进程名鉴权(`ping.exe` 改名 `game.exe` 即被注入)。
- **交付**: 结论分级 + 证据路径 + 载荷指纹 + §10 防护清单(明文卡密上行、注入目标弱鉴权、功能与校验分离为三大要害)。
