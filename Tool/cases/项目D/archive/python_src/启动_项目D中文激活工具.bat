@echo off
chcp 65001 >nul
title 项目D 激活与优化管理工具 (中文版)
cd /d "%~dp0"

:: 检查管理员权限，若无则自动请求 UAC
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo 正在获取管理员权限...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

:: 优先使用 pythonw 无控制台启动，若无则使用 python
start "" pythonw "%~dp0IDM_Activator_CN.pyw"
if %errorlevel% neq 0 (
    python "%~dp0IDM_Activator_CN.pyw"
)
exit
