@echo off
chcp 65001 >nul
title Seep Reverse Lab - 部署完备性体检 (Verifier)
echo.
echo 正在启动 Seep 工作台健康检查...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup\verify.ps1"
echo.
echo ================================================================================
echo 按任意键关闭窗口...
pause >nul
