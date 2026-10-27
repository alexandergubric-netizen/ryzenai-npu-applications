# Builds Postura.exe with the C# compiler that ships with Windows (.NET Framework 4.x, C# 5) — no SDK needed.
# Usage:  pwsh -File postura\build.ps1 [-Release] [-Dev]
#   -Release  also copies the installer to Documents\Apps by Alex (Postura-Setup.exe)
#   -Dev      developer build (--web, --serve, --break-test work) into build\dev-<edition>; never for release
#   APPS_OUTPUT_SUBFOLDER (env) changes where -Release copies to (default "Apps by Alex")
param([ValidateSet('public')][string]$Edition = 'public', [switch]$Release, [switch]$Dev)
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$fw = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319'
if (-not (Test-Path "$fw\csc.exe")) { $fw = Join-Path $env:WINDIR 'Microsoft.NET\Framework\v4.0.30319' }
$wm = Join-Path $env:WINDIR 'System32\WinMetadata'

if (-not (Test-Path (Join-Path $root 'build\public\postura.ico'))) { python (Join-Path $root 'make_icon.py') }

$src = Get-ChildItem (Join-Path $root 'src') -Filter *.cs | ForEach-Object { $_.FullName }
# web\org.js holds the public edition's wording (a company edition would put editions\<id>\org.js in its place)
$webFiles = Get-ChildItem (Join-Path $root 'web') -File
$refs = @('System.dll', 'System.Core.dll', 'System.Drawing.dll', 'System.Windows.Forms.dll', 'System.Web.Extensions.dll',
    'Microsoft.CSharp.dll', "$fw\System.Runtime.dll", "$fw\System.Runtime.WindowsRuntime.dll",
    "$fw\System.Runtime.InteropServices.WindowsRuntime.dll", "$wm\Windows.Foundation.winmd", "$wm\Windows.Data.winmd",
    "$wm\Windows.UI.winmd") | ForEach-Object { "/r:$_" }

$docs = [Environment]::GetFolderPath('MyDocuments')
$editions = @('public')
foreach ($ed in $editions) {
    $art = Join-Path $root "build\$ed"
    $outDir = if ($Dev) { Join-Path $root "build\dev-$ed" } else { $art }
    New-Item -ItemType Directory -Force $outDir | Out-Null
    $out = Join-Path $outDir 'Postura.exe'
    $cargs = @('/nologo', '/optimize+', '/codepage:65001', '/target:winexe', '/platform:anycpu', "/out:$out",
        "/win32manifest:$(Join-Path $root 'src\app.manifest')", "/win32icon:$art\postura.ico",
        "/resource:$art\icon.png,web/icon.png", "/resource:$art\tray.ico,tray.ico")
    if ($Dev) { $cargs += '/define:DEV' }
    $web = $webFiles | ForEach-Object {
        $f = if ($_.Name -eq 'org.js' -and $ed -ne 'public') { Join-Path $root "editions\$ed\org.js" } else { $_.FullName }
        "/resource:$f,web/$($_.Name)"
    }
    # a response file sidesteps PowerShell's quoting of paths with spaces
    $rsp = Join-Path $outDir 'csc.rsp'
    ($cargs + $refs + $web + $src | ForEach-Object { '"' + $_ + '"' }) | Set-Content $rsp -Encoding utf8
    & "$fw\csc.exe" "@$rsp"
    if ($LASTEXITCODE -ne 0) { throw "csc failed for $ed ($LASTEXITCODE)" }
    Write-Host "Built $out ($([math]::Round((Get-Item $out).Length / 1KB)) KB)"
    if ($Release -and -not $Dev) {
        $sub = if ($env:APPS_OUTPUT_SUBFOLDER) { $env:APPS_OUTPUT_SUBFOLDER } else { 'Apps by Alex' }
        $dir = Join-Path $docs $sub
        New-Item -ItemType Directory -Force $dir | Out-Null
        $name = 'Postura-Setup.exe'
        Copy-Item $out (Join-Path $dir $name) -Force
        Write-Host "  -> $(Join-Path $dir $name)"
    }
}
