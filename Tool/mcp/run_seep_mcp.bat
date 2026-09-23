@echo off
setlocal

rem Resolve seep root directory
set "SEEP_ROOT=%~dp0"
set "PYTHONIOENCODING=utf-8"

rem Check python
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Python not found in PATH. Please install Python 3.10+ >&2
    exit /b 1
)

python "%SEEP_ROOT%seep_mcp_server.py" %*
