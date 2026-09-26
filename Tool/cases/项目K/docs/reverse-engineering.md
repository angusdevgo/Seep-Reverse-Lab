# 项目K 授权激活逆向与客户端鉴权旁路（CWE-602）

> 目标：`项目K` v7.19（Windows 桌面文件管理器，.NET Framework 4.7.2 / WPF / x64）
> 授权模型：30 天试用 → 会员（计时 / 永久）
> 结论：**存在可 100% 复现的客户端鉴权旁路 + 云控剥离漏洞**

---

## 一、防护与解包链路（四层对抗）

| # | 防护层 | 特征 | 处置手段 |
|---|---|---|---|
| 1 | **Themida / WinLicense 原生壳** | `.themida` + `.boot` 节；导入表仅剩 `kernel32!GetModuleHandleA`；`IMAGE_DIRECTORY_ENTRY_COM_DESCRIPTOR` 被清零 | 进程内存镜像重建，定位内嵌 .NET PE（COR20 @ RVA 0x2000），还原完整托管模块 |
| 2 | **方法体虚拟化（Method Body Stubbing）** | 13983 个 `MethodDef` 中 **7860 个**被替换为 4 字节桩（`nop;nop;ldnull;ret`），真实 IL 由原生 VM 在 JIT 期投递 | 发现 Themida 已挂钩 `clrjit!ICorJitCompiler::compileMethod` vtable（指针位于 `clrjit.dll` 之外），**在其之上安装自建 Hook**，截获 **9632 个方法**的真实 IL |
| 3 | **字符串加密 + 委托跳板** | 全部 `ldstr` 仅剩 35 条明文（均为壳自身字符串）；业务字符串经 `mnwyDnYKw2aElTavFm0f` 委托解密；方法调用经 `d4cYKEmBVf8` 代理转发 | 运行期反射枚举全部静态字段，解析 **858 个委托字段** → 还原真实目标方法 |
| 4 | **内嵌加密程序集** | 授权核心由 `SpeedImage..cctor` 经 `Assembly.Load(byte[])` 动态加载（程序集名 `1kznju2l`，类型 `XXX.XXX`） | 从进程内存 dump 出该内嵌程序集并完整反编译（728 行 C#） |

### 关键技术点：JIT Hook 截获真实 IL
```csharp
// Themida 通过改写 ICorJitCompiler vtable 劫持 JIT；在其之上再挂一层即可截获解密后的 IL
IntPtr h   = GetModuleHandleA("clrjit.dll");
IntPtr jit = ((GetJitDel)GetDelegateForFunctionPointer(GetProcAddress(h,"getJit"), ...))();
IntPtr vt  = Marshal.ReadIntPtr(jit);            // ICorJitCompiler vtable
IntPtr cm  = Marshal.ReadIntPtr(vt);             // compileMethod
// cm - clrjitBase 为负/超界 => Themida 已挂钩
VirtualProtect(vt, 8, PAGE_READWRITE, out _);
Marshal.WriteIntPtr(vt, Marshal.GetFunctionPointerForDelegate(ourHook));
```
Hook 内读取 `CORINFO_METHOD_INFO`：
- `+0` `ftn`（MethodDesc*，可与 `RuntimeMethodHandle.Value` 直接对应）
- `+16` `ILCode`，`+24` `ILCodeSize`，`+28` `maxStack`，`+30` `EHcount`

> 注意：Themida 投递给 JIT 的 `ILCode` 为**裸 IL 代码**（不含方法体头），且 `EHcount` 恒为 0；方法体的 `maxStack` / `localVarSigTok` / EH 子句仍保留在磁盘桩头中，可回填复用。

### 真实 IL 回填
```python
# 1) 从内存镜像解析 PE -> COR20 -> MetaData -> #~ 流 -> MethodDef 表（行大小 18，RVA 在行首 4 字节）
# 2) 用截获的 IL 重建 fat 头方法体，写入镜像空闲区（原 Themida 保留区 RVA 0xA00000+）
# 3) 回写 MethodDef.RVA 列，扩展 section 覆盖 scratch 区
# 4) ILSpy 反编译 => 1163 个文件的完整真实 C# 源码
```

---

## 二、授权架构

### 2.1 机器码（JQM）
```
JQM = MD5_HEX( 主板序列号 + <SALT> + CPU ProcessorID + 语言后缀 )  →  每 4 字符插入 '-'
```
| 数据源 | 取值 |
|---|---|
| 主板 | WMI `SELECT SerialNumber FROM Win32_BaseBoard` |
| CPU | WMI `SELECT ProcessorID FROM Win32_Processor` |
| 盐 | `<REDACTED_SALT>`（19 字符硬编码常量，已按脱敏规范屏蔽） |
| 语言后缀 | `zh` → 空串；其它 → `-<大写语言码>` |

> 该盐值不随机器变化，属商业授权机密；完整值仅保留在本地私有报告。

### 2.2 许可载荷
```
<JQM> \t <到期日期 yyyy-MM-dd> [\t <邮箱>]
```

### 2.3 加密方案（对称 · 密钥完全本地派生）
`RijndaelManaged` / **AES-128-CBC / PKCS7 / UTF8**

对 JQM 去横线后取 32 字符，按固定切片拼装 Key 与 IV：

| 切片 | 下标区间 | 长度 |
|---|---|---|
| a | `[0,1)` | 1 |
| b | `[1,7)` | 6 |
| c | `[7,14)` | 7 |
| d | `[14,16)` | 2 |
| e | `[16,20)` | 4 |
| f | `[20,23)` | 3 |
| g | `[23,27)` | 4 |
| h | `[27,32)` | 5 |

```
AES Key = f + g + h + e     // 16 字节
AES IV  = a + c + d + b     // 16 字节
```

**核心缺陷**：密钥材料 100% 来自客户端本地可推导信息，**无任何服务端秘密参与**，且载荷**无数字签名 / 无 MAC**。

### 2.4 双重本地存储（伪防篡改）
| 位置 | 路径 |
|---|---|
| 注册表 | `HKCU\SOFTWARE\Microsoft\<JQM去横线去数字后前3字母>`，值名 `Configuration` |
| 隐藏文件 | `%APPDATA%\Microsoft\Crypto\Keys\<JQM去横线小写>` |

- 文件被置 `Hidden`，创建/写入/访问时间被伪造为与 `%APPDATA%` 目录创建时间一致
- 读取时**仅比对"注册表密文 == 文件密文"**，两者一致即放行 → 同时写入两处即可绕过

### 2.5 授权状态机
`项目K.App` 中 `public static int Days;`（默认 `-36500`）为**唯一全局判据**：

| 条件 | 状态 | 界面表现 |
|---|---|---|
| `Days >= 29200` | **永久授权版** | `PermanentLabel = 永久授权版`，隐藏购买入口 |
| `0 < Days < 29200` | 计时授权 | `您还有 X 天授权使用期` |
| `Days <= 0` | 免费版 | `免费使用版（全功能）` + 催购弹窗 |

> `29200 天 = 80 年` 被用作"永久"阈值。

### 2.6 会员权益差异（荣誉制，非功能阉割）
过期后软件仍为 **「免费使用版（全功能）」**，功能不阉割；差异仅在授权状态与催购干扰：

| 项目 | 免费版 | 永久会员 |
|---|---|---|
| 全部文件管理功能 | ✅ | ✅ |
| 关于窗口状态 | 免费使用版（全功能） | **永久授权版** |
| 「购买会员」按钮 | 显示 | **Collapsed 隐藏** |
| 菜单栏购买/续费入口 | 显示 | 隐藏（`Days > 10`） |
| 启动到期提醒弹窗 | 弹出 | 不弹（`Days > 10`） |

会员体系入口：**联系我们 / 切换语言 / 购买（试用到期·会员到期）/ 注册（重装系统·更换电脑·离线注册）**。

### 2.7 激活协议
- 服务端：`https://<vendor-domain>`（经系统代理发起 HTTPS `CONNECT`）
- `Controller.CheckRegistration(email)` → HTTP POST（超时 10000ms）→ 响应按 `\t` 分割，`array.Length >= 7` 时取 `array[6]` 为注册码
- `Controller.FinishRegistration(window, 注册码)` → `App.SetGqm()` → 解密注册码（`<x>\t<JQM>\t<到期日期|Invalid>\t<邮箱>`）→ 落盘

---

## 三、漏洞定级

| CWE | 类型 | 描述 |
|---|---|---|
| **CWE-602** | 客户端强行实施服务端安全机制 | 授权有效性由客户端本地整型 `App.Days` 单点决策，核心权益无服务端权威闭环 |
| **CWE-321/327** | 硬编码 / 可推导密钥 + 弱对称加密 | 许可密文 Key/IV 完全由本地机器码推导，无服务端秘密参与 |
| **CWE-345** | 缺少真实性与完整性校验 | 载荷无数字签名、无 MAC；"双存储比对"可被同时写入绕过 |
| **CWE-472** | 外部可控数据未校验 | 到期日期为明文字段，客户端直接 `int.Parse` 后计算剩余天数 |

### 攻击链
1. 复算本机机器码（WMI 三项 + 盐）→ 推导 AES Key/IV
2. 构造 `<JQM>\t2199-12-31\t<任意邮箱>`
3. AES-128-CBC/PKCS7 加密 → Base64
4. **同步写入注册表与隐藏文件**（绕开一致性比对）
5. 启动应用 → 剩余天数 > 29200 → 永久授权版

---

## 四、DLL 化复现方案（含云控剥离）

原厂在启动约 15s 后会向 `<vendor-domain>` 发起在线复核；若服务端判定未注册，则通过 `App.SetGqm()` 将本地许可覆写为 `<JQM>\tInvalid\t<邮箱>`，随后 `XXX.XXX.yIGxD()` 落盘毒化并 `Environment.Exit(0)`。
因此**单纯伪造许可仅能维持约 1~2 分钟**。

### 三重冗余对抗
| # | 模块 | 机制 |
|---|---|---|
| 1 | **许可伪造** | 运行期 WMI 复算机器码 → 派生 AES Key/IV → 写入永久载荷（注册表 + 隐藏文件，含 Hidden 属性与时间戳伪装） |
| 2 | **云控剥离** | 自定义 `IWebProxy`，**精准拦截 `<vendor-domain>`**（路由至死端口 `127.0.0.1:9`），其余流量直连 —— 只斩云控，不误伤其他网络功能 |
| 3 | **内存锁看门狗** | 反射锁定 `App.Days = 63282`（每秒重写）+ 每 5 秒校验磁盘许可，被改写即复原 |

> 关键洞察：`App.Days` 为 `public static int` 单字段驱动全部权益分支 —— 只要在内存中钉死它，云控回写即失效。

### 实测效果
| 指标 | 纯许可伪造 | **DLL 方案** |
|---|---|---|
| 永久授权生效 | ✅ | ✅ |
| 云控复核 | ❌ 1~2 分钟后被毒化 + 退出 | ✅ **完全阻断** |
| 稳定运行 | ~2.5 分钟 | **8 分钟以上零异常、零改写记录** |
| 外联行为 | 连接 `<vendor-domain>:443` | **零外部连接** |

### 关于窗口取证
```
[verify] App.Days=63282
  DaysLabel='63282'(Visible)
  PermanentLabel='永久授权版'(Visible)
  FreeLabel='免费使用版（全功能）'(Visible)
  VIPButton='购买会员'(Collapsed)      <-- 催购入口消失
  DaysStackPanel=Collapsed
  FreeStackPanel=Collapsed
  PermanentStackPanel=Visible          <-- 永久授权版面板
```

---

## 五、修复建议（纵深防御）

### 客户端加固
1. 授权核心从"运行期 `Assembly.Load(byte[])` 明文程序集"改为 Native + 控制流平坦化，消除"内存 dump 即得算法"单点
2. 消除 `App.Days` 单字段驱动全部权益的写法，改为**不可逆令牌 + 多因子校验**
3. 本地许可被篡改时应触发**服务端黑名单上报 + 功能降级**，而非仅本地覆写（本地覆写可被看门狗秒还原）

### 密码学修复（最关键）
1. 许可载荷改由**服务端私钥 Ed25519 / ECDSA-P256 签名**，客户端仅内置公钥验签
2. **禁止用机器码派生密钥**；机器码仅作为绑定标识参与签名
3. 若保留 AES，须使用服务端下发的一次性密钥 + HMAC 完整性保护

### 服务端权威闭环
1. 核心权益以**服务端为唯一权威**，客户端仅缓存展示
2. 在线复核结果以**服务端签发短时效 token** 下发，离线宽限期显式限定，超期强制降级
3. 建立"设备指纹 + 邮箱 + 订单"三要素绑定的服务端风控

### 反回拨
- 时间源改为**服务端时间 + 单调计数器**，避免仅依赖本地 `DateTime.Now`
- 移除可被同时篡改的"双存储一致性比对"，改用**服务端签名校验**

---

## 六、方法论沉淀

1. **Themida .NET 的"方法体虚拟化"并非不可破**：壳只是把真实 IL 延后到 JIT 期投递，在它自己的 JIT vtable 钩子**之上**再挂一层即可完整截获
2. **优先 dump 而非硬啃**：`AppDomainManager` 注入是纯托管、无需原生编译的进程内立足点，可同时完成"提权观察 + 内存 dump + 运行期反射解析"
3. **委托跳板是纸老虎**：混淆器的 `delegate.Invoke` 代理链在运行期就是普通静态字段，一次反射枚举即可全量还原 858 条映射
4. **"内嵌加密程序集"是常见盲区**：核心逻辑若在运行期 `Assembly.Load(byte[])` 加载，则静态分析必然扑空；务必在进程内 dump 该程序集
5. **客户端单字段判据 = 一击必杀**：`public static int Days` 这类设计使一次反射写值即可永久解锁，且可对抗任何服务端回写
6. **云控复核必须实测时长**：仅伪造许可时漏洞"看起来成立"，实际会在 1~2 分钟后被服务端回写清除 —— 必须做**长时间稳定性验证**才能确认漏洞真实可利用性
