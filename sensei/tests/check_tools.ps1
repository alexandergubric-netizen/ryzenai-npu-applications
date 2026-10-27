# Tests SenseiTools on this PC without changing anything for good:
# settings are set to their current value, files are made in a throwaway folder.
# Usage: pwsh -NoProfile -File tests\check_tools.ps1 [-Shutdown]  (-Shutdown schedules a 10 h shutdown and cancels it)
param([switch]$Shutdown)
$ErrorActionPreference = 'Stop'
Import-Module (Join-Path $PSScriptRoot '..\core\SenseiTools.psm1') -Force
$pass = 0; $fail = 0
function Check([string]$name, [scriptblock]$test) {
    try { $r = & $test; Write-Host "PASS  $name  $(($r | Out-String).Trim() -replace '\s+', ' ')"; $script:pass++ }
    catch { Write-Host "FAIL  $name  $($_.Exception.Message)" -ForegroundColor Red; $script:fail++ }
}
$box = Join-Path $env:TEMP "sensei-test-$(Get-Random)"
New-Item -ItemType Directory $box | Out-Null
Add-Type -AssemblyName System.Drawing

Check 'audio volume read+set same' {
    $v = Get-AudioVolume
    $r = Set-AudioVolume -Percent $v.VolumePercent
    if ($v.Muted) { Set-AudioVolume -Mute | Out-Null }
    if ([math]::Abs($r.VolumePercent - $v.VolumePercent) -gt 1) { throw "volume changed $($v.VolumePercent) -> $($r.VolumePercent)" }
    "volume $($v.VolumePercent)% muted=$($v.Muted)"
}
Check 'mute toggle restores' {
    $v = Get-AudioVolume
    Set-AudioVolume -Mute | Out-Null; $m = (Get-AudioVolume).Muted
    if (-not $v.Muted) { Set-AudioVolume -Unmute | Out-Null }
    if (-not $m) { throw 'mute did not apply' }
    "mute works, restored to muted=$((Get-AudioVolume).Muted)"
}
Check 'brightness read+set same' { $b = Get-ScreenBrightness; Set-ScreenBrightness -Percent $b.BrightnessPercent }
Check 'dark mode set to current' {
    $cur = (Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize').AppsUseLightTheme
    if ($cur -eq 1) { Set-DarkMode -Off } else { Set-DarkMode }
}
Check 'wallpaper set to current' {
    $wp = (Get-ItemProperty 'HKCU:\Control Panel\Desktop').WallPaper
    if ($wp -and (Test-Path $wp)) { Set-Wallpaper -Path $wp } else { 'skipped (no wallpaper file)' }
}
Check 'speech engine available' { $v = New-Object -ComObject SAPI.SpVoice; "voice: $($v.Voice.GetDescription())" }
Check 'screenshot' { $r = Save-Screenshot -Path (Join-Path $box 'shot.png'); if (-not (Test-Path "$box\shot.png")) { throw 'no file' }; $r }
Check 'image convert png->jpg keeps original' {
    $r = Convert-Image -Path "$box\shot.png" -Format jpg -Quality 80
    if (-not (Test-Path "$box\shot.png") -or -not (Test-Path "$box\shot.jpg")) { throw 'missing file' }; $r
}
Check 'image convert via pipeline to folder' { Get-ChildItem $box -Filter *.jpg | Convert-Image -Format bmp -Destination "$box\out" }
Check 'resize 50%' {
    $i = Get-ImageInfo "$box\shot.png"; $r = Resize-Image "$box\shot.png" -Percent 50
    if ([math]::Abs($r.Width - [int]($i.Width / 2)) -gt 1) { throw "width $($r.Width)" }; $r
}
Check 'resize width' { Resize-Image "$box\shot.jpg" -Width 640 }
Check 'folder size' { Get-FolderSize $box }
Check 'subfolder sizes' { Get-FolderSize $box -Subfolders }
Check 'duplicates' {
    Copy-Item "$box\shot.png" "$box\out\copy.png"
    $d = @(Find-DuplicateFiles $box); if ($d.Count -lt 2) { throw 'duplicate not found' }; "$($d.Count) files in duplicate groups"
}
Check 'recycle bin delete' {
    Set-Content "$box\trash1.txt" 'x'; Set-Content "$box\trash2.txt" 'y'
    $r = Get-ChildItem $box -Filter 'trash*.txt' | Remove-ToRecycleBin
    if (Test-Path "$box\trash1.txt") { throw 'still there' }; $r
}
Check 'close app' {
    $p = Start-Process charmap -PassThru; Start-Sleep 2
    $r = Close-App charmap -Force; Start-Sleep 1
    if (Get-Process -Id $p.Id -ErrorAction SilentlyContinue) { Stop-Process -Id $p.Id -Force; throw 'still running' }; $r
}
Check 'timer script parses' {
    # do not pop up a real timer: build the same script and parse it
    $script = "Start-Sleep -Seconds 1; Add-Type -AssemblyName PresentationFramework; [void][System.Windows.MessageBox]::Show('it''s time', 'Sensei timer')"
    [void][scriptblock]::Create($script); 'ok'
}
Check 'eject missing drive gives clear error' { try { Dismount-Drive Q; throw 'no error' } catch { if ($_.Exception.Message -notmatch 'no drive') { throw } ; 'clear error' } }
Check 'public ip' { $r = Get-PublicIP; if ($r.PublicIP -notmatch '^[\d\.:a-f]+$') { throw $r.PublicIP }; 'got an address' }
Check 'wifi password (current network)' { $r = Get-WifiPassword; "network '$($r.Network)', password length $($r.Password.Length)" }
Check 'internet speed' { Test-InternetSpeed -MB 5 }
Check 'wifi adapter detection' {
    $a = Get-NetAdapter -Physical | Where-Object { $_.PhysicalMediaType -match '802\.11|Wireless' -or $_.Name -match 'Wi-?Fi|WLAN' } | Select-Object -First 1
    if (-not $a) { throw 'no wifi adapter' }; "adapter '$($a.Name)'"
}
if ($Shutdown) {
    Check 'shutdown schedule + cancel' {
        $r = Start-Shutdown -InMinutes 600; $c = Stop-Shutdown
        if ($c -notmatch 'cancelled') { shutdown.exe /a; throw "cancel said: $c" }; "$r / $c"
    }
    Check 'shutdown At parses' { $r = Start-Shutdown -At '23:59' -Restart; $c = Stop-Shutdown; if ($c -notmatch 'cancelled') { shutdown.exe /a; throw $c }; $r }
}
Remove-Item $box -Recurse -Force
Write-Host "`n$pass passed, $fail failed"
