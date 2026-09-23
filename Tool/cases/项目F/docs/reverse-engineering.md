# 逆向方法论：从混淆二进制到 Keygen

本文记录该算法从加壳二进制到可运行 Keygen 的完整逆向路径，供研究参考。

## 1. 样本概况

- 分发形式：Inno Setup 6.1 安装器（`项目F.exe`，约 12 MB），内含主程序
  `app\项目F.exe`（.NET Framework 4.8，32 位，约 2.5 MB）
- 版本覆盖：项目F 6.3 正式版与 7.0 Beta（v7.0.0.9）
- 解包方式：`innoextract` 直接解出 `app\` 目录（含 `项目F.pdb` 符号文件，为静态分析提供 TypeRef 线索）

## 2. 保护机制（定制 .NET 混淆器）

主程序使用**自家定制混淆器**（非 ConfuserEx/Reactor 等已知产品），三层保护：

| 层 | 机制 |
|---|---|
| 方法体加密 | 关键方法 IL 从元数据剥离，存放于嵌入资源加密流；运行时解密后用 `DynamicILInfo.SetCode` 注入 `DynamicMethod` 执行 |
| 字符串加密 | 所有字符串以 token 索引存放，运行时经 `Reflection.Emit` 动态方法 XOR 链解密 |
| 控制流混淆 | 状态机式 `while(true) + switch` 循环 + 常量表达式垃圾指令（v6 全量；v7 业务代码已无状态机） |

v7 与 v6 同构但**加密面大幅缩小**：v7 全程序集仅 5 个方法被 token 化加密
（`CheckLicense` + 4 个哈希函数），其余约 7000 个方法可直接反编译。

## 3. 动态解壳（关键步骤）

静态反编译只能看到瘦身后的 stub（方法体被剥离），必须**动态解壳**：

1. **定位执行器**：通过单例字段特征在混淆类中定位方法体解密执行器
   （v6：`\ue1cd.\ue00f`；v7：`\ue215.\ue00f`），它负责把加密方法体解码为标准 IL
2. **Hook token 分配**：用 Harmony 对 `DynamicILInfo.GetTokenFor` 打补丁，
   记录"动态 token → 成员引用"映射——解密后的 IL 里复杂成员引用是运行时分配的
   动态 token，不打补丁无法对照出成员名
3. **Dump IL**：触发目标方法执行（或直接调用执行器的解码入口），把解密后的
   `DynamicMethod` IL 字节 dump 出来，配合 token 映射反汇编成可读 IL
4. **字符串表**：调用字符串解密器批量还原全部字符串 token（v7 共 3,148 个）

## 4. 算法还原

从解密后的 `CheckLicense` IL（约 226 字节）还原出：

```
常量：CHARSET / SALT / LICENSE_LEN(192) / CHECK_POS(160) / CHECK_LEN(19)
流程：3×uint32 哈希 → 96bit 拼接 → 19×5bit 字符映射 → 与 license[160:179] 比对
      + MD5(email+SALT) 黑名单
```

还原后用**独立实现交叉验证**（见 `docs/algorithm.md` §7），再在真实程序上验收：
反射调用安装版 `CheckLicense`，构造密钥使其返回 `True`。

## 5. 激活路径分析

激活流程（`ProService.ActivateNewLicense`）：

```
1. LicenseChecker.CheckLicense(email, key)   ← 本地校验（离线）
2. HTTP POST account.项目F.com             ← 远程激活（非必需）
3. 写 项目F5License 设置
```

选项页提供**离线激活**：本地 `CheckLicense` 通过即写入设置并置 `IsPro=true`，全程无网络。
设置持久化于 `%APPDATA%\项目F\UserProfile\Settings\Preferences.json` 的
`Settings` 对象（点分键）：

```json
"项目F5.ProLicense.Name":  "用户名",
"项目F5.ProLicense.Email": "邮箱",
"项目F5.ProLicense.Key":   "192 字符密钥"
```

> 注意：写入前必须退出 项目F——程序退出时会用内存中的设置覆盖配置文件，
> 运行中写入会被回滚。因此激活工具在写入前检测进程并警告。

## 6. 工具链构成

| 阶段 | 工具 |
|---|---|
| 安装包解包 | innoextract |
| 静态反编译 | ilspycmd（v7 可直接反编译业务代码） |
| 动态解壳/DUMP | 自研 .NET loader（net48）+ Harmony 2.3.5（本仓库未收录，属分析期工具） |
| IL 反汇编 | dnlib 自研 ildump（token 映射对照） |
| 算法复现 | C# `LicenseAlgo.cs` + Python 独立实现交叉验证 |
| 验收 | 反射调用安装版 `CheckLicense` 返回 True |

## 7. 经验总结

1. **静态分析要配合动态验证**：方法体加密导致静态反编译只有 stub，必须跑起来解壳
2. **Token 映射是动态解密的关键**：不打 `GetTokenFor` 补丁，解密 IL 里全是数字 token
3. **自洽测试会掩盖移植错误**：同源 Generate/Verify 互验全过 ≠ 与参考实现一致——
   用 Python 独立实现逐字符对照，立刻暴露了 C# 96 位整数拼接错误
4. **版本间保护差异巨大**：v7 把加密面从"全量"缩到"5 个方法"，
   检验算法却一字未改——分析结论可跨版本复用（v6 keygen 在 v7 零适配通过）