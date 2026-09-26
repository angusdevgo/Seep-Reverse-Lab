@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title 项目J 卡密授权旁路 - 一键复现

echo ============================================================
echo    项目J  卡密授权旁路  --  一键复现
echo ============================================================
echo.
echo [1/3] 启动目标并写入补丁 ...
echo.

where python >nul 2>nul
if errorlevel 1 goto :PS

python "%~dp0apply_patch.py"
if errorlevel 1 goto :FAIL
goto :NEXT

:PS
echo [i] 未检测到 Python，改用 PowerShell 补丁器 ...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0apply_patch.ps1"
if errorlevel 1 goto :FAIL

:NEXT
echo.
echo [2/3] 请在登录框输入【任意】卡密（例如 123456），然后点击「登陆」。
echo.
echo [3/3] 验证要点：
echo        - 主窗口尺寸变为 948 x 727（登录窗为 415 x 214）
echo        - 主窗口含：信息编辑 / 文本参数编辑 / 图形参数编辑
echo        - 点击「生成图片」应渲染出完整《商标注册证》
echo        - 停留 3 分钟不自动退出
echo.
echo    对照实验：不运行本脚本时，同样卡密会提示「卡号不存在」。
echo.
pause
exit /b 0

:FAIL
echo.
echo [!] 补丁失败。请右键本文件 -^> 以管理员身份运行；
echo     或先执行「手动复现步骤.md」第 0.2 节把清单降权为 asInvoker。
echo.
pause
exit /b 1
