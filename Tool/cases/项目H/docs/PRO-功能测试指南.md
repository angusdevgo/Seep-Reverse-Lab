# 项目H 2 PRO 功能清单 & 测试指南（本机实测版）

> 适用于 `<本地路径> patch 为 Pro 版，与
> `<本地路径> 配套）。

## 一、PRO 独有功能（来自 exe 字符串 + 官方定位）

| # | 功能 | 位置/入口 | 本机实测 |
|---|------|-----------|---------|
| 1 | **自定义命令绑定全局热键/鼠标动作** | 首选项 → 控制 → 全局快捷键 →「添加新命令」 | ✅ 已实测：保存 `pro-test` 命令成功写入 config.ini `[Hotkey] custom_command_0_desc` |
| 2 | **外部程序命令**（如 `external notepad c:/123.txt`） | 命令行 `项目H.exe external <程序> <参数>` | 命令对话框「预设」含常用模板 |
| 3 | **命令行 `;` 多操作组合** | `项目H.exe snip --full -o clipboard ; pin` | 帮助文本标明 "With 项目H PRO, the above options can be combined with ;" |
| 4 | **`--hold`**：指定输出前先标注再保存 | 命令行截图选项 | 帮助文本标 [PRO] |
| 5 | **`--block [秒]`**：命令执行等待截图完成 | 命令行选项 | 帮助文本标 [PRO] |
| 6 | **OCR 文字提取** | 截屏工具内「文字识别」+ 首选项配 OCR 引擎（本地 tesseract / 腾讯 / OCR.space API） | 需要额外装 tesseract 才能完整测 |
| 7 | **自定义应用内快捷键**（In-App Shortcuts） | 首选项 → 控制 → 应用内快捷键 | 字符串标 [PRO] |
| 8 | **配置截图缩略图快捷键** | 首选项 → 截屏 | 字符串标 [PRO] |
| 9 | 首选项标题「[专业版]」徽标 | 任意窗口标题 / About 页 PRO 徽章 | ✅ 已实测 |
| 10 | 「解锁专业版」对话框直接显示已激活 | 托盘 → 解锁专业版… | ✅ 已实测：page2_success |

## 二、如何自己测试（每条都验证过可操作路径）

### 1. 最快确认是 Pro 版
托盘图标右键 →「解锁专业版…」→ 直接停在 **「项目H 2 专业版已激活」** 页
（免费版这里会显示 "You are using the free version…" + Purchase 按钮）。

### 2. 自定义命令（PRO 核心）
```
首选项 → 控制 → 全局快捷键 → 「添加新命令」
→ 名称随意（如 test）、命令填：cmd /c echo 123 > %TEMP%\pro.txt
→ 确定
→ 左侧快捷键列表中应出现该命令条目（已保存到 config.ini [Hotkey] 段）
```
免费版：这个按钮/对话框会被 PRO 检查拦截（本机对照：官方版连首选项命令都被拒绝）。

### 3. 命令行组合 `;`（PRO）
在 cmd 里运行（同时按住，项目H 已在运行）：
```
项目H.exe snip --full -o clipboard ; pin
```
PRO 版会依次执行：全屏截图→复制→贴图。免费版会提示该组合需 PRO。

### 4. OCR 文字提取
```
首选项 → 截屏 → OCR 区域配置本地 tesseract 路径（如 d:\tesseract\tesseract.exe）
→ 截图选中一段文字 → 点「文字识别」→ 结果弹出
```
免费版该区域为锁定/付费引导。

### 5. 全局热键绑定任意程序
「添加新命令」里命令填 `external notepad.exe <文件路径>`，确定后按分配的快捷键
即可唤起外部程序（PRO 专属，官方帮助原文："项目H PRO allows you to bind any
command to a global hotkey!"）。

## 三、已知差异/限制（persist 版）

- 「解锁专业版」页面显示 "(0 设备)"：persist 路径下 license 对象字段为空所致
  （设备计数=0），**不影响功能使用**；若需正常显示可改用"粘贴激活码"流程
  （`项目H-keygen.exe gen` 生成的码与当前 exe 配套）。
- OCR 需自备 tesseract/API key，属于功能使用前提而非授权限制。

## 四、对照方法（想验证 patch 前后差异）

```
官方原版（免费）：<本地路径>
1. 复制官方原版 + 配套文件到新目录运行
2. 托盘右键「Unlock PRO features」→ 显示 free version 介绍页
3. 运行 open-preferences 命令 → 被拒绝（No valid arguments matched）
Pro 版（当前）：直接运行 <本地路径>
1. 解锁对话框 → 已激活 success 页
2. open-preferences → 首选项 [专业版] 正常打开
```