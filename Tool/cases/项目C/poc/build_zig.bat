@echo off
setlocal
cd /d "%~dp0"

echo ============================================================
echo   Building version.dll (x64) - Zig / Clang Toolchain
echo ============================================================

python -m ziglang version >nul 2>nul
if %errorlevel% neq 0 (
    echo [-] "python -m ziglang" not available.
    echo [*] Install with:  pip install ziglang
    exit /b 1
)

python -m ziglang c++ -shared -O2 -o version.dll proxy_version.cpp version.def -luser32

if exist version.dll (
    echo.
    echo [+] Compilation SUCCESS!
    echo [+] Output: %~dp0version.dll
    echo [*] Exports: 17  ^(GetFileVersionInfo* / VerFindFile* / VerInstallFile* / VerLanguageName* / VerQueryValue*^)
) else (
    echo.
    echo [-] Compilation FAILED.
)
