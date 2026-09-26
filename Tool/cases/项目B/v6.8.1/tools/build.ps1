# ============================================================================
#  项目B 本地化守护 —— 代理 DLL 一键编译
#  用法： powershell -NoProfile -ExecutionPolicy Bypass -File .\build.ps1
#  依赖： python (PATH) + rustc (PATH)
# ============================================================================
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host "[1/4] 从点位表生成 Rust 源码与 .def 转发表 ..." -ForegroundColor Cyan
python work/gen_proxy.py
if ($LASTEXITCODE -ne 0) { throw "gen_proxy.py 失败" }

New-Item -ItemType Directory -Force -Path dist | Out-Null

$rustcArgs = @('--crate-type','cdylib','-C','opt-level=z','-C','panic=abort',
               '-C','strip=symbols','-C','lto')

Write-Host "[2/4] 编译 dist\sentry.dll  (覆盖 项目BNxMain.exe / 项目BNxService.exe) ..." -ForegroundColor Cyan
& rustc @rustcArgs -o dist\sentry.dll src\sentry_proxy.rs -C link-arg=src/sentry.def
if ($LASTEXITCODE -ne 0) { throw "sentry.dll 编译失败" }

Write-Host "[3/4] 编译 dist\version.dll (覆盖 项目BRemoteService.exe) ..." -ForegroundColor Cyan
& rustc @rustcArgs -o dist\version.dll src\version_proxy.rs -C link-arg=src/version.def
if ($LASTEXITCODE -ne 0) { throw "version.dll 编译失败" }

Write-Host "[4/4] 校验导出转发完整性 ..." -ForegroundColor Cyan
python -c @"
import sys; sys.path.insert(0,'work')
from pe_exports import PEFile
import subprocess, os
def need(exe, dll):
    out = subprocess.run(['D:/Tool/Radare2/bin/rabin2.exe','-i',exe],
                         capture_output=True, text=True).stdout
    s=set()
    for line in out.splitlines():
        p=line.split()
        if len(p)>=6 and p[4].lower()==dll: s.add(p[5])
    return s
def fwd(dll):
    r=PEFile(dll).exports()
    return set(r['forwarders'].keys())
cases=[(r'<安装目录>\nx_main\项目BNxMain.exe','sentry.dll','dist/sentry.dll'),
       (r'<安装目录>\nx_main\项目BNxService.exe','sentry.dll','dist/sentry.dll'),
       (r'<安装目录>\nx_main\项目BRemoteService.exe','version.dll','dist/version.dll')]
ok=True
for exe,dll,proxy in cases:
    n=need(exe,dll); f=fwd(proxy); miss=n-f
    print('  %-26s need=%-3d forward=%-3d missing=%d' % (os.path.basename(exe), len(n), len(f), len(miss)))
    if miss: print('    !! 缺失:', sorted(miss)); ok=False
print('EXPORT CHECK:', 'PASS' if ok else 'FAIL')
sys.exit(0 if ok else 1)
"@
if ($LASTEXITCODE -ne 0) { throw "导出校验失败" }

Get-ChildItem dist\*.dll | ForEach-Object {
    $h = (Get-FileHash $_.FullName -Algorithm SHA256).Hash
    Write-Host ("  {0,-14} {1,8} bytes  SHA256={2}" -f $_.Name, $_.Length, $h)
}
Write-Host "`n完成：dist\sentry.dll, dist\version.dll" -ForegroundColor Green
Write-Host "部署：powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy\Deploy-ProxyDll.ps1" -ForegroundColor Green
