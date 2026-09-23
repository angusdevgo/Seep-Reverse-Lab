---
name: dsl-vm-captcha-reverse-2026-07-05
description: 验证码系统完整逆向分析 — JS 前端模块 + DSL VM 风控引擎
metadata:
  type: project
  tags: [captcha, reverse, dsl-vm, wasm, frontend]
  date: 2026-07-05
  status: completed
---

# 验证码系统完整逆向分析

## 场景
目标：逆向某大型验证码系统，用于理解其完整的工作原理和验证流程。

## 目标实体
- **nc.js** (72KB) — Webpack 打包的滑块核心 (9 modules)
- **fireyejs.js** (583KB) — DSL VM 解释器 (26 opcode 自定义指令集)
- **awsc.js** (9KB) — 模块加载器
- **secaptcha.js** (72KB) — WASM C 编译产物 (emscripten)
- **et_f.js** (262KB) — 另一个 DSL VM 类型的文件

## 已验证的技术方案

### 方案 A：Selenium + CDP 拖拽（推荐）
通过 CDP `Input.dispatchMouseEvent` 发送原生鼠标事件，在真实浏览器中完成验证。
- 成功率：高
- 依赖：Chrome + Selenium/Playwright

### 方案 B：Playwright 无头浏览器 Runner
在 Playwright 中加载 DSL VM 和模块加载器，通过 HTTP API 暴露 token。
- 成功率：中（依赖 WASM 初始化环境）

### 方案 C：纯 requests 协议验证
直接通过 HTTP 请求调用 API 端点进行验证。
- 成功率：**极低**（token 与浏览器 TLS/IP/指纹强绑定）
- 不建议使用

## 关键发现

1. **token 无法脱离浏览器使用** — DSL VM 生成的 token 提交时服务端会校验上下文一致性（TLS JA3、IP、Cookie、Referer 等）

2. **fireyejs.js 不是 WASM 二进制而是 DSL VM** — 583KB 纯 JS 实现的自定义虚拟机，通过 26 个 opcode 的解释器循环执行编码后的指令

3. **nc.js 9 模块已 100% 逆向** — 包括 API 端点、滑块 UI、交互逻辑、ncSessionID 算法、多语言等

4. **真正的 WASM 编译产物是 secaptcha.js** — 72KB，使用 SharedArrayBuffer + Atomics，emscripten 编译 C 代码

## 踩坑记录

1. 测试 appkey 不会触发真实验证，必须用真实页面的 appkey
2. `initialize` 返回特定状态码才是滑块模式，返回 `success` 只是会话创建确认
3. performance log 中 JSONP 请求的 URL 事件可能因 script 标签注入方式而捕获不完整
4. 导出函数名在 DSL VM 文件中不存在（被 VM 编码了），真正的导出通过模块注册中心暴露

## 可复用模式

- **DSL VM 逆向模式**：`case 提取 → opcode 分类 → 常量表分析 → 函数追踪 → 导出提取`
- **验证码系统通用架构**：`入口JS → 模块加载器(WASM/DSL) → API通信层 → 前端UI → 服务端验证`
- **CDP 原生事件绕过**：`Input.dispatchMouseEvent` 绕过检测，与 WebDriver 无关

## 工具链

- Selenium + CDP: 浏览器自动化 + 原生鼠标事件
- Playwright: 无头浏览器 + route 拦截
- Python requests: 纯 API 调用（验证失败）
- Node.js + Playwright: Runner 服务

## 文件结构

```
项目根/
├── slider_v3.py                # 改进版 CDP 拖拽
├── protocol_v2.py               # 纯协议版本（验证失败）
├── phase3_final.py              # Playwright 完整捕获
├── monitor_inject.js            # 页面监控 Hook
├── runner/                      # Node.js Runner
├── captured_js/                 # 已捕获的 JS 文件
├── hook_data/                   # Hook 捕获的数据
├── wasm_output/                 # WASM 提取输出
└── COMPLETE_REVERSE_REPORT.md   # 完整逆向报告
```

## 参考链接

- [[dsl-vm-reverse]] — DSL VM 逆向 skill 文档