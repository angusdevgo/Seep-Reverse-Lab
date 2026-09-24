#Requires -Version 5.1
<#
  Seep Reverse Lab - 根目录快捷健康体检入口
  用法: powershell -ExecutionPolicy Bypass -File .\check.ps1
#>
& (Join-Path $PSScriptRoot 'setup\verify.ps1') @args
exit $LASTEXITCODE
