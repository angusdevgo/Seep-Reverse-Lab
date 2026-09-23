@echo off
title ���� 项目D Pro Tool (WPF UI ��)

set "CSC=C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
set "FW=C:\Windows\Microsoft.NET\Framework64\v4.0.30319"
set "WPF=%FW%\WPF"

echo ========================================================
echo        ���ڱ��� 项目D Pro Tool (WPF UI ������)
echo ========================================================
echo.

if not exist "%CSC%" (
    echo [����] δ�ҵ� .NET Framework 64 λ������: %CSC%
    pause
    exit /b 1
)

echo [1/3] ���� WPF Դ�� src\Program.cs ...
"%CSC%" /nologo /target:winexe /optimize+ /platform:x64 /codepage:65001 ^
    /lib:"%WPF%" ^
    /r:System.dll /r:System.Core.dll /r:Microsoft.CSharp.dll /r:System.Xaml.dll ^
    /r:WindowsBase.dll /r:PresentationCore.dll /r:PresentationFramework.dll ^
    /win32icon:src\app.ico ^
    /win32manifest:src\app.manifest ^
    /out:IDM_Pro_Tool.exe src\Program.cs

if not %ERRORLEVEL% equ 0 (
    echo.
    echo [����] ����ʧ�ܣ������Ϸ�������Ϣ��
    pause
    exit /b 1
)

echo [2/3] ���ƴ���ͼ�� app_icon.png ...
copy /y "src\app_icon.png" "app_icon.png" >nul

echo [3/3] �������: IDM_Pro_Tool.exe
echo.
echo ע��: ������ҪͬĿ¼�µ� app_icon.png������ͼ�꣩��
echo.
pause
