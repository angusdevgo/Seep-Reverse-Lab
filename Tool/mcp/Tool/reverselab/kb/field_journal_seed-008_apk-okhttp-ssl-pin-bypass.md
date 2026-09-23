# [种子] APK Frida 绕过 OkHttp SSL Pinning

## 场景分类
APK 逆向 / 移动安全测试

## 目标概述
对一个使用 OkHttp + 自定义 CertificatePinner 的 Android 应用，用 Frida 动态绕过证书校验，让 Burp 能拿到明文流量。

## 完整执行链路

1. 装 Frida + frida-server，启动目标 App，确认进程名
   ```bash
   adb shell "ps -A | grep com.target.app"
   frida-ps -U | grep target
   ```
2. 用 Burp 抓包尝试 → 拿到证书错误，说明启用了 Pinning
3. 用 jadx 打开 APK 反编译 → 搜 `CertificatePinner` 或 `checkServerTrusted`
4. 确认是 OkHttp 自带 `CertificatePinner` 还是自定义 `X509TrustManager`
5. 写 Frida 脚本 hook 关键校验点
6. 启动 Frida 注入：`frida -U -f com.target.app -l bypass.js --no-pause`
7. 重新抓包 → Burp 能看到明文 HTTPS

## 踩坑记录

| 问题 | 原因 | 解决方案 | 耗时 |
|------|------|---------|------|
| Frida 启动报错 `unable to connect to remote frida-server` | server 未启动或端口被占 | `adb forward tcp:27042 tcp:27042` + 启动 server | 10min |
| Hook 不生效 | App 启动太快，Frida 注入晚了 | 用 `-f` 参数 spawn 模式，配合 `--no-pause` | 15min |
| Hook 后部分请求仍 SSL 错误 | 应用同时用了 OkHttp 与原生 HttpsURLConnection | 增加 hook `X509TrustManager.checkServerTrusted` 与 `HostnameVerifier.verify` | 20min |
| 反检测：App 检测到 Frida 后退出 | App 自检 frida-server 端口 / `/data/local/tmp/re.frida.server` | 改用 frida-gadget（注入 .so 进 APK 内）或 magisk + zygisk-frida | 30min+ |
| ProGuard 混淆后类名找不到 | 类名变成 `a.b.c` 短名 | 在 jadx 里用 `Find Usages` 反查谁实例化 OkHttpClient.Builder | 25min |

## 工具链发现

- **objection** 内置 `android sslpinning disable` 一条命令搞定 80% 场景，不用自己写 Frida 脚本
- **frida-multiple-unpinning**（GitHub: WithSecureLabs）覆盖 OkHttp 3/4、Retrofit、HttpsURLConnection、Conscrypt、Cordova，万能脚本
- **MEDUSA** 框架自带各种安卓绕过模块，比裸 Frida 上手快

## 关键代码/命令

最小可用 OkHttp Pin 绕过脚本：

```javascript
Java.perform(function () {
    // 1. OkHttp 3/4 内置 CertificatePinner
    try {
        var CertificatePinner = Java.use('okhttp3.CertificatePinner');
        CertificatePinner.check.overload('java.lang.String', 'java.util.List').implementation = function (host, peers) {
            console.log('[+] OkHttp CertificatePinner.check bypassed: ' + host);
            return;
        };
    } catch (e) {}

    // 2. 自定义 X509TrustManager.checkServerTrusted
    try {
        var TrustManagerImpl = Java.use('com.android.org.conscrypt.TrustManagerImpl');
        TrustManagerImpl.verifyChain.implementation = function (untrusted, holdHost, host, clientAuth, ocspData, tlsSctData) {
            console.log('[+] TrustManagerImpl.verifyChain bypassed: ' + host);
            return untrusted;
        };
    } catch (e) {}

    // 3. HostnameVerifier 全过
    var HostnameVerifier = Java.use('javax.net.ssl.HostnameVerifier');
    // 用 objection 自带模板补完...
});
```

一键命令（推荐）：

```bash
objection --gadget com.target.app explore -s "android sslpinning disable"
```

## 对本包的改进建议

- `apk-reverse/references/` 应有专门的 `ssl-pinning-bypass.md`，把 OkHttp 3/4、Conscrypt、自定义 TrustManager、Flutter（boringssl）四种主流情况合并为速查
- bootstrap manifest 加入 `objection`（pip 包）

## 可复用的模式/脚本片段

**通用绕过流程**：

```text
1. 抓包 → 看是哪类错误（CertPin / Hostname / TrustManager）
2. jadx 搜关键类（CertificatePinner / X509TrustManager / HostnameVerifier）
3. 优先 objection 一键 → 不行再 frida-multiple-unpinning → 再不行手写
4. 若有反 Frida 检测 → 切 frida-gadget 或 zygisk
5. Flutter 应用单独处理（hook libflutter.so 的 ssl_verify_peer_cert）
```

## 进化动作
- [x] 路由矩阵已覆盖（apk-reverse + Frida）
- [x] tool-index 中 frida 状态已检查
- [ ] 建议增补 ssl-pinning-bypass.md 速查

## 环境信息
- Kali / Windows + adb + frida-tools 16.x
- 目标 Android: 8-14（不同版本 TrustManagerImpl 路径不同）
- 注入方式: USB 调试 + frida-server / 或 zygisk-frida 隐藏

## 脱敏要求
本条目为种子数据，基于公开技术模式编写，不涉及真实目标。包名 `com.target.app` 为占位符。
