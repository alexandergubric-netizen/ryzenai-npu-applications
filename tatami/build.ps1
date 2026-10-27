# Builds Tatami.exe with the C# compiler that ships with Windows (.NET Framework 4.x, C# 5).
# Usage:  powershell -File tatami\build.ps1 [-Console]
#   -Console  builds a console exe (handy for --bench output while developing)
param([switch]$Console)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$csc = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\csc.exe'
if (-not (Test-Path $csc)) { $csc = Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319\csc.exe' }

$src = Get-ChildItem (Join-Path $root 'src') -Filter *.cs | ForEach-Object { $_.FullName }
$res = @()
$web = Join-Path $root 'web'
if (Test-Path $web) {
    Get-ChildItem $web -File | ForEach-Object { $res += "/resource:$($_.FullName),web/$($_.Name)" }
}
$icon = Join-Path $root 'tatami.ico'
$iconArg = @(); if (Test-Path $icon) { $iconArg = @("/win32icon:$icon") }
$target = if ($Console) { 'exe' } else { 'winexe' }
$out = Join-Path $root 'Tatami.exe'

$manifest = Join-Path $root 'src\app.manifest'
& $csc /nologo /optimize+ /unsafe+ /codepage:65001 /target:$target /platform:anycpu "/out:$out" "/win32manifest:$manifest" `
    /r:System.dll /r:System.Core.dll /r:System.Web.Extensions.dll /r:Microsoft.CSharp.dll `
    @iconArg @res @src
if ($LASTEXITCODE -ne 0) { throw "csc failed ($LASTEXITCODE)" }
Write-Host "Built $out ($([math]::Round((Get-Item $out).Length/1KB)) KB)"
