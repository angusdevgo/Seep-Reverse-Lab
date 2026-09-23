# [种子] iOS 越狱检测绕过 + 抓包

## 场景分类
iOS 逆向 / 移动安全测试

## 目标概述
某 iOS 应用在越狱设备上启动即闪退或显示"环境异常"，需要绕过越狱检测才能进一步分析其 HTTP 请求。

## 完整执行链路

1. 越狱机准备（Dopamine / palera1n / unc0ver）→ 装 frida-server（Cydia 源 `build.frida.re`）
2. 把 IPA 拖到机器，AppSync Unified 装签名 → 启动确认能 `frida-ps -U`
3. 启动 App → 闪退或弹"环境异常"
4. 用 `frida-trace -U -i 'open' -i 'stat' -i 'access' -i 'fork' com.target.app` 看检测调用
5. 常见命中：探测 `/Applications/Cydia.app`、`/private/var/lib/apt`、`/usr/sbin/sshd`、`fork()` 是否成功、`/etc/apt`
6. 用 objection 一键绕过：`objection --gadget com.target.app explore -s "ios jailbreak disable"`
7. 启动成功后用 frida hook NSURLSession 抓包，或配 mitmproxy 装系统证书

## 踩坑记录

| 问题 | 原因 | 解决方案 | 耗时 |
|------|------|---------|------|
| objection 绕过后还是闪退 | App 用了 SSL Pinning + 越狱检测双重 | 同时启用 `ios sslpinning disable` 与 `ios jailbreak disable` | 15min |
| App 在启动前就检测，hook 来不及 | 越狱检测在 `+load` 或 `__attribute__((constructor))` 里 | 用 `-f` spawn 模式 + `frida-trace --aux 'spawn=1'` | 20min |
| Hook stat 之后 App 卡住 | stat 被 hook 后部分系统调用也被影响 | 只 hook 应用 bundle 内代码触发的 stat（按 caller 过滤） | 30min |
| Frida-server 启动后 App 仍能检测到 | App 检测了 27042 端口与 frida 字符串 | 用 `frida-server` 改名 + 改默认端口（`-l 0.0.0.0:1234`），客户端用 `-H ip:1234` | 25min |
| mitmproxy 装证书后仍 SSL 错误 | iOS 14+ 系统证书需要在"通用 → 关于本机 → 证书信任设置"再开一道开关 | 装完证书去信任设置勾选 | 10min |

## 工具链发现

- **objection** 是 iOS 安全测试的瑞士军刀，自带 jailbreak / sslpin / clipboard / keychain dump 等模块
- **r2frida** 把 radare2 接到 frida 上，能在运行时反汇编 + 修改寄存器，比纯 frida 强得多
- **Hopper / IDA** 反编译 iOS 二进制（iOS Mach-O 用 IDA 7+ 或 Ghidra 都行）
- **dumpdecrypted** 已经过时，现在用 **frida-ios-dump** 脱壳

## 关键代码/命令

通用越狱检测 hook 模板：

```javascript
// 拦截 NSFileManager fileExistsAtPath 检测越狱目录
var NSFileManager = ObjC.classes.NSFileManager;
Interceptor.attach(NSFileManager['- fileExistsAtPath:'].implementation, {
    onEnter: function (args) {
        var path = ObjC.Object(args[2]).toString();
        var jbPaths = [
            '/Applications/Cydia.app',
            '/Library/MobileSubstrate/MobileSubstrate.dylib',
            '/bin/bash', '/usr/sbin/sshd',
            '/etc/apt', '/private/var/lib/apt/'
        ];
        if (jbPaths.indexOf(path) !== -1) {
            this.shouldFake = true;
            console.log('[+] Hide JB path: ' + path);
        }
    },
    onLeave: function (retval) {
        if (this.shouldFake) retval.replace(0);
    }
});

// 拦截 fork() —— 越狱机能 fork，非越狱机返回 -1
var fork = Module.findExportByName(null, 'fork');
Interceptor.replace(fork, new NativeCallback(function () {
    return -1;
}, 'int', []));
```

一键脱壳（用于上传 jadx 等的反编译）：

```bash
frida-ios-dump -l com.target.app
# 输出 Payload/TargetApp.app + 已脱壳 Mach-O
```

## 对本包的改进建议

- 新增子 skill `ios-reverse/`（与 `apk-reverse/` 平行），覆盖：脱壳、越狱检测绕过、SSL Pin、Keychain dump、frida-ios-dump、`+load` 时机
- 现有 `apk-reverse/` 不应承担 iOS 内容，避免混淆

## 可复用的模式/脚本片段

**iOS 安全测试速查**：

```text
1. 越狱环境准备（Dopamine 16.x / palera1n 旧版）
2. frida-ios-dump 脱壳
3. otool / class-dump 看类层级
4. objection 起 console
5. ios jailbreak disable
6. ios sslpinning disable
7. mitmproxy 抓包（系统证书 + 信任设置双开）
8. 关键逻辑找完后用 IDA / Hopper 静态深挖
```

## 进化动作
- [ ] **建议新增 ios-reverse skill**（当前路由矩阵 iOS 走 reverse-engineering/platforms.md，不够细）
- [ ] bootstrap manifest 增加 frida-ios-dump
- [ ] 增加"iOS 安全测试 Checklist"到 references/

## 环境信息
- 越狱设备: iPhone X（iOS 16.5）+ Dopamine 1.1.7
- 主机: macOS 13+ / Kali（mitmproxy + frida-tools）
- frida-server-ios: 16.x

## 脱敏要求
本条目为种子数据，基于公开技术模式编写，不涉及真实目标。Bundle ID `com.target.app` 为占位符。
