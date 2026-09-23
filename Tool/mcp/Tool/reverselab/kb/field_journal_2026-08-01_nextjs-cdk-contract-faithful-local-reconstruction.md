# Next.js CDK 订单中心的契约保真本地重建

> 日期：2026-08-01
>
> 场景：Web / API / JS 逆向与本地重建
>
> 脱敏：目标域名与端口使用标准占位符；凭据、CDK、订单标识及私有路径仅保留类别，不记录原值

## 场景分类

Web / API / JS 逆向

## 目标概述

对一个 Next.js 单页订单中心建立“入口快照、静态 bundle、运行时页面、公开 OpenAPI”四源证据链，在不连接真实支付、worker 与检查服务的前提下，重建同信息架构、同浏览器请求形状、同响应投影、同订单状态语义的可运行本地项目。

## Scope 摘要（脱敏）

- auth_basis: 用户提供入口并要求分析与同款本地实现
- network_profile: 公开入口与公开 OpenAPI 只读复核；构建和验收均指向环回地址
- asset_types: [web, frontend_js, public_openapi, screenshot, local_source]
- fixture_profile: 合成 CDK、合成 credential、合成支付链接、确定性 worker/check/payment 适配器

## 角色

- lead_role: lead
- specialists: [cre, doc]

## 完整执行链路

1. 固化入口 HTML、响应头、公开 OpenAPI 与 SHA-256，并复用既有静态包和浏览器取证。
2. 从主页面 bundle 提取路由、请求体字段、header、Storage key、轮询周期、条件渲染与状态词汇表。
3. 将页面内部 legacy API 与公开 v1 API 分开建模，建立各自 serializer，避免共用 DTO 导致字段漂移。
4. 从运行时全页截图、DOM 与 CSS 计算桌面几何、移动断点、卡片层级、控件状态和文案基线。
5. 建立 canonical domain model、CDK 账本和确定性状态机；外部能力通过 `CHECK_FN`、`PAYMENT_PROVIDER`、`WORKER_GATEWAY` 夹具适配器承接。
6. 将 credential 和支付链接在请求期立即缩减为摘要、类型和安全提示；持久化模型不设置原文槽位。
7. 对单笔、批量、详情、取消、重提、分页、双鉴权和 OpenAPI 文档执行契约测试。
8. 用桌面与移动浏览器截图验证视觉；用生产构建、接口冒烟、秘密扫描和解压复验形成交付证据。

## Evidence 链摘要（脱敏）

| E-id | source_type | 可复用命令模式 | 关联结论 |
|------|-------------|----------------|----------|
| E-001 | network/file | `curl -D headers -o page https://{target_domain}/<entry>; shasum -a 256 page` | 框架入口与时间戳基线 |
| E-002 | frontend_js/openapi | `rg 'sessionStorage|/api/|productType|customerToken' {formatted_chunk}`；`jq '{info,paths,securitySchemes}' openapi.json` | legacy 请求、状态、浏览器存储与 v1 合同 |
| E-003 | runtime_visual/local_qa | `chromium --headless ...; screenshot + DOMRect`；`npm test && npm run build && BASE_URL=... npm run smoke` | 桌面/移动几何、条件渲染与本地合同闭环 |

## Finding / Path 摘要

- top_finding: 页面内部 legacy API 与公开 v1 API 共享业务语义，但请求字段、鉴权入口和响应投影不同，重建时需要“一个领域模型、两个边界 serializer”。
- path_type: callflow
- path_one_liner: 表单输入 -> 页面字段映射 -> legacy Route Handler -> canonical service -> 夹具适配器/账本 -> legacy serializer -> 轮询渲染。

## 踩坑记录

| 问题 | 原因 | 解决方案 | 耗时 |
|------|------|---------|------|
| 仅按路由名搭接口仍造成页面字段空白 | legacy 与 v1 的响应字段并非同一 DTO | 从 bundle 的属性读取点反推 serializer，并对两套边界分别做契约测试 | ~45 min |
| 页面初始形态与绑定后形态混在一起 | 多处卡片、提示、按钮和列表为条件渲染 | 先固化未绑定基线，再按 CDK/订单状态制作交互矩阵 | ~30 min |
| 批量接口需要同时表达部分成功与账本一致性 | 把单项错误提升成整批异常会丢失原页面的逐项结果语义 | 先逐项解析，再在一次 store mutation 内按顺序产出 created/duplicate/failed，末尾统一校验账本并原子落盘 | ~35 min |
| 文档 required 字段与 properties 名称存在歧义 | OpenAPI 与页面内部调用面独立演进 | 保留规范字段，同时在边界识别兼容 alias；报告单列裁决依据 | ~15 min |
| 视觉看似接近但纵向误差持续累积 | 卡片 padding、line-height、gap 的小偏差叠加 | 以完整页面高度、主列宽和关键 DOMRect 为约束，逐段回归截图 | ~40 min |
| 夹具提示文案破坏同款首屏 | 实现说明直接混入产品 UI | UI 保持取证基线，夹具说明放 README；输入仍使用确定性示例 | ~15 min |

## 工具链发现

- 静态 bundle 的属性读取点比接口路径本身更适合恢复响应 DTO。
- legacy/v1 serializer 分层可让页面兼容性与公开 API 稳定性同时成立。
- `fullPage` 截图要结合视口宽度、页面总高度与 DOMRect；单纯像素相似度会被字体抗锯齿放大。
- 批量订单应保留逐项 created/duplicate/failed；去重、容量扣减与账本校验放在同一 mutation 中，最终只做一次原子文件替换。
- 秘密扫描应覆盖源代码、运行时 store、测试日志和最终压缩包展开目录，而不只扫描 Git 工作树。

## 关键代码/命令

```bash
# 静态调用面与状态字段
rg -n 'customerToken|productType|upiExpiresAt|customerResubmitCount|sessionStorage' {formatted_chunk}

# 公开 API 结构
jq '{openapi,info,paths:(.paths|keys),security:.components.securitySchemes}' openapi.json

# 本地质量门
npm run lint
npm test
npx tsc --noEmit
npm run build
BASE_URL=http://127.0.0.1:{port} npm run smoke
```

## 对本包的改进建议

1. `js-reverse` 增加“legacy UI API 与 public API 双 serializer”检查表。
2. 报告模板增加“视觉基线几何表”和“初始/绑定/订单状态矩阵”。
3. QA 模板增加批量部分成功与原子落盘、双鉴权 OR、OpenAPI schema/实际响应一致性和交付包展开扫描。

## 可复用的模式/脚本片段

1. **四源交叉**：入口快照定位版本，静态 bundle 恢复调用面，运行时恢复条件渲染，OpenAPI 恢复公开合同。
2. **一核双投影**：canonical domain 保持状态与账本统一，legacy/public serializer 保持边界保真。
3. **先初始态、后状态矩阵**：先锁定未绑定首屏，再验证绑定、创建、进行中、完成、取消、重提。
4. **请求期缩减**：原始输入进入 service 后立刻转换成 SHA-256、类型和掩码，日志与 store 只接收缩减结果。
5. **交付包二次复验**：从压缩包解压到新目录，重新安装、测试和构建，避免工作目录残留掩盖问题。

## 进化动作

- [ ] 更新了路由矩阵
- [ ] 更新了 tool-index
- [ ] 更新了 bootstrap-manifest
- [ ] 更新了子 skill 文档
- [x] 新增了 pitfalls 记录
- [ ] 无需更新

## 环境信息

- OS: macOS
- 工具版本: Node.js 24、Next.js 16.2.12 App Router、React、TypeScript 5.9.3、Chrome/Playwright
- 目标平台/版本: Next.js App Router / React / OpenAPI 3.1

## 最终验收记录

- ESLint、TypeScript 5.9.3、Next.js 16.2.12 production build：通过。
- Node test：8/8 通过。
- HTTP smoke：15 个契约组通过。
- Playwright：11 张状态/视口截图、10 组断言通过，浏览器 console 与 page error 均为空。
- 1440 px 初始页与基线尺寸同为 1440×1294；RGB MAE 2.301148，5/通道阈值内像素占比 0.945085。

## 脱敏复核

- [x] 目标域名替换为 `{target_domain}`
- [x] CDK、订单号、Token、Cookie、JWT 与支付链接原文未写入
- [x] 真实 IP、端口与本地私有路径未写入
- [x] 运行命令使用 `{port}` 与占位符
- [x] 交付经验仅保留方法、结构与验证模式

---
<!-- [社区贡献] 完成后询问用户是否 PR 到主仓库。 -->
