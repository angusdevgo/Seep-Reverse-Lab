@echo off
REM Patch-engine regression test builder. Run from anywhere; it cd's to repo root.
set "CSC=C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
set "WPF=C:\Windows\Microsoft.NET\Framework64\v4.0.30319\WPF"
cd /d "%~dp0.."
"%CSC%" /nologo /target:exe /platform:x64 /codepage:65001 /main:IDM_Toolkit_Wpf.TestHarness ^
  /lib:"%WPF%" ^
  /r:System.dll /r:System.Core.dll /r:Microsoft.CSharp.dll /r:System.Xaml.dll ^
  /r:WindowsBase.dll /r:PresentationCore.dll /r:PresentationFramework.dll ^
  /out:tests\PatchEngineTests.exe src\Program.cs tests\PatchEngineTests.cs
echo BUILD_EXIT=%ERRORLEVEL%
