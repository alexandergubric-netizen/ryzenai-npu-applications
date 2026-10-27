# SenseiTools: helper commands for tasks Windows has no simple cmdlet for.
# Loaded into Sensei's PowerShell session and checker, so the AI and the library can call them by name.
# Every function keeps originals (images are written as new files, deletes go to the Recycle Bin).

Set-StrictMode -Off

# ------------------------------------------------------------------ native helpers (compiled on first use)
function Initialize-SenseiNative {
    if ('SenseiNative.Audio' -as [type]) { return }
    Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
namespace SenseiNative {
  [Guid("5CDF2C82-841E-4546-9722-0CF74078229A"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IAudioEndpointVolume {
    int f(); int g(); int h(); int i();
    int SetMasterVolumeLevelScalar(float fLevel, Guid pguidEventContext);
    int j();
    int GetMasterVolumeLevelScalar(out float pfLevel);
    int k(); int l(); int m(); int n();
    int SetMute([MarshalAs(UnmanagedType.Bool)] bool bMute, Guid pguidEventContext);
    int GetMute(out bool pbMute);
  }
  [Guid("D666063F-1587-4E43-81F1-B948E807363F"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IMMDevice { int Activate(ref Guid id, int clsCtx, IntPtr activationParams, out IAudioEndpointVolume aev); }
  [Guid("A95664D2-9614-4F35-A746-DE8DB63617E6"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
  interface IMMDeviceEnumerator { int f(); int GetDefaultAudioEndpoint(int dataFlow, int role, out IMMDevice endpoint); }
  [ComImport, Guid("BCDE0395-E52F-467C-8E3D-C4579291692E")] class MMDeviceEnumeratorComObject { }

  public static class Audio {
    static IAudioEndpointVolume Endpoint() {
      var en = (IMMDeviceEnumerator)(new MMDeviceEnumeratorComObject());
      IMMDevice dev;
      Marshal.ThrowExceptionForHR(en.GetDefaultAudioEndpoint(0, 1, out dev));
      IAudioEndpointVolume epv;
      Guid id = typeof(IAudioEndpointVolume).GUID;
      Marshal.ThrowExceptionForHR(dev.Activate(ref id, 23, IntPtr.Zero, out epv));
      return epv;
    }
    public static float Volume {
      get { float v; Marshal.ThrowExceptionForHR(Endpoint().GetMasterVolumeLevelScalar(out v)); return v; }
      set { Marshal.ThrowExceptionForHR(Endpoint().SetMasterVolumeLevelScalar(value, Guid.Empty)); }
    }
    public static bool Mute {
      get { bool m; Marshal.ThrowExceptionForHR(Endpoint().GetMute(out m)); return m; }
      set { Marshal.ThrowExceptionForHR(Endpoint().SetMute(value, Guid.Empty)); }
    }
  }

  public static class Win {
    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern bool SystemParametersInfo(int action, int param, string vparam, int winIni);
    [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
    [DllImport("user32.dll")] public static extern int GetSystemMetrics(int index);
    [DllImport("user32.dll")] public static extern bool PostMessage(IntPtr hWnd, int msg, IntPtr wParam, IntPtr lParam);
    [DllImport("user32.dll", CharSet = CharSet.Auto)]
    public static extern IntPtr SendMessageTimeout(IntPtr hWnd, int msg, IntPtr wParam, string lParam, int flags, int timeout, out IntPtr result);
  }

  [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
  struct SHFILEOPSTRUCT {
    public IntPtr hwnd; public uint wFunc;
    [MarshalAs(UnmanagedType.LPWStr)] public string pFrom;
    [MarshalAs(UnmanagedType.LPWStr)] public string pTo;
    public ushort fFlags; public bool fAnyOperationsAborted; public IntPtr hNameMappings;
    [MarshalAs(UnmanagedType.LPWStr)] public string lpszProgressTitle;
  }
  public static class Recycle {
    [DllImport("shell32.dll", CharSet = CharSet.Unicode)] static extern int SHFileOperation(ref SHFILEOPSTRUCT op);
    // FO_DELETE with FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_NOERRORUI | FOF_SILENT: no dialogs, goes to the Recycle Bin
    public static int Send(string[] paths) {
      var op = new SHFILEOPSTRUCT();
      op.wFunc = 3;
      op.pFrom = string.Join("\0", paths) + "\0\0";
      op.fFlags = 0x40 | 0x10 | 0x400 | 0x4;
      return SHFileOperation(ref op);
    }
  }
}
'@
}

# ------------------------------------------------------------------ sound
function Get-AudioVolume {
    <# Current speaker volume in percent and whether it is muted. #>
    [CmdletBinding()] param()
    Initialize-SenseiNative
    [pscustomobject]@{ VolumePercent = [math]::Round([SenseiNative.Audio]::Volume * 100); Muted = [SenseiNative.Audio]::Mute }
}

function Set-AudioVolume {
    <# Set-AudioVolume -Percent 50 | -Up 10 | -Down 10 | -Mute | -Unmute #>
    [CmdletBinding(DefaultParameterSetName = 'Percent')]
    param(
        [Parameter(ParameterSetName = 'Percent', Position = 0)][ValidateRange(0, 100)][int]$Percent,
        [Parameter(ParameterSetName = 'Up')][ValidateRange(1, 100)][int]$Up,
        [Parameter(ParameterSetName = 'Down')][ValidateRange(1, 100)][int]$Down,
        [Parameter(ParameterSetName = 'Mute')][switch]$Mute,
        [Parameter(ParameterSetName = 'Unmute')][switch]$Unmute
    )
    Initialize-SenseiNative
    switch ($PSCmdlet.ParameterSetName) {
        'Mute' { [SenseiNative.Audio]::Mute = $true }
        'Unmute' { [SenseiNative.Audio]::Mute = $false }
        'Up' { [SenseiNative.Audio]::Volume = [math]::Min(1, [SenseiNative.Audio]::Volume + $Up / 100); [SenseiNative.Audio]::Mute = $false }
        'Down' { [SenseiNative.Audio]::Volume = [math]::Max(0, [SenseiNative.Audio]::Volume - $Down / 100) }
        default { [SenseiNative.Audio]::Volume = $Percent / 100; if ($Percent -gt 0) { [SenseiNative.Audio]::Mute = $false } }
    }
    Get-AudioVolume
}

function Out-Speech {
    <# Reads the text aloud with the Windows voice. #>
    [CmdletBinding()] param([Parameter(Mandatory, Position = 0, ValueFromPipeline)][string]$Text, [ValidateRange(-10, 10)][int]$Rate = 0)
    process {
        $voice = New-Object -ComObject SAPI.SpVoice
        $voice.Rate = $Rate
        [void]$voice.Speak($Text)
    }
}

# ------------------------------------------------------------------ display
function Get-ScreenBrightness {
    [CmdletBinding()] param()
    $b = Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $b) { throw 'This display does not let Windows control its brightness (external monitors usually do not).' }
    [pscustomobject]@{ BrightnessPercent = $b.CurrentBrightness }
}

function Set-ScreenBrightness {
    <# Set-ScreenBrightness -Percent 40 (built-in laptop screens) #>
    [CmdletBinding()] param([Parameter(Mandatory, Position = 0)][ValidateRange(0, 100)][int]$Percent)
    $m = Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $m) { throw 'This display does not let Windows control its brightness (external monitors usually do not).' }
    Invoke-CimMethod -InputObject $m -MethodName WmiSetBrightness -Arguments @{ Timeout = [uint32]0; Brightness = [byte]$Percent } | Out-Null
    Get-ScreenBrightness
}

function Set-ScreenOff {
    <# Turns the display off now (move the mouse or press a key to wake it). #>
    [CmdletBinding()] param()
    Initialize-SenseiNative
    Start-Sleep -Milliseconds 500   # so the click that ran this does not wake the screen at once
    [void][SenseiNative.Win]::PostMessage([IntPtr]0xffff, 0x0112, [IntPtr]0xF170, [IntPtr]2)
    'Screen turned off. Move the mouse to wake it.'
}

function Set-DarkMode {
    <# Set-DarkMode (dark) | Set-DarkMode -Off (light) #>
    [CmdletBinding()] param([switch]$Off)
    $key = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Themes\Personalize'
    $light = [int][bool]$Off
    Set-ItemProperty -Path $key -Name AppsUseLightTheme -Value $light -Type DWord
    Set-ItemProperty -Path $key -Name SystemUsesLightTheme -Value $light -Type DWord
    Initialize-SenseiNative
    $r = [IntPtr]::Zero
    [void][SenseiNative.Win]::SendMessageTimeout([IntPtr]0xffff, 0x1A, [IntPtr]::Zero, 'ImmersiveColorSet', 2, 2000, [ref]$r)
    if ($Off) { 'Light mode is on.' } else { 'Dark mode is on.' }
}

function Set-Wallpaper {
    <# Set-Wallpaper -Path C:\pics\sky.jpg #>
    [CmdletBinding()] param([Parameter(Mandatory, Position = 0)][string]$Path)
    $full = (Resolve-Path -LiteralPath $Path -ErrorAction Stop).Path
    Initialize-SenseiNative
    if (-not [SenseiNative.Win]::SystemParametersInfo(20, 0, $full, 3)) { throw "Windows refused the wallpaper $full" }
    "Wallpaper set to $full"
}

function Save-Screenshot {
    <# Saves the whole screen as PNG (default: Pictures\Screenshots). Save-Screenshot -Delay 5 waits first. #>
    [CmdletBinding()] param([string]$Path, [ValidateRange(0, 600)][int]$Delay = 0)
    if ($Delay) { Start-Sleep -Seconds $Delay }
    Add-Type -AssemblyName System.Windows.Forms, System.Drawing
    Initialize-SenseiNative
    [void][SenseiNative.Win]::SetProcessDPIAware()
    $x = [SenseiNative.Win]::GetSystemMetrics(76); $y = [SenseiNative.Win]::GetSystemMetrics(77)
    $w = [SenseiNative.Win]::GetSystemMetrics(78); $h = [SenseiNative.Win]::GetSystemMetrics(79)
    if (-not $Path) {
        $dir = Join-Path ([Environment]::GetFolderPath('MyPictures')) 'Screenshots'
        New-Item -ItemType Directory -Path $dir -Force | Out-Null
        $Path = Join-Path $dir ("Screenshot {0:yyyy-MM-dd HHmmss}.png" -f (Get-Date))
    }
    $bmp = [System.Drawing.Bitmap]::new($w, $h)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    try { $g.CopyFromScreen($x, $y, 0, 0, $bmp.Size); $bmp.Save($Path, [System.Drawing.Imaging.ImageFormat]::Png) }
    finally { $g.Dispose(); $bmp.Dispose() }
    Get-Item -LiteralPath $Path | Select-Object FullName, @{n = 'Size'; e = { "$w x $h" } }
}

# ------------------------------------------------------------------ images (originals are kept)
function Get-ImageInfo {
    [CmdletBinding()] param([Parameter(Mandatory, Position = 0, ValueFromPipeline, ValueFromPipelineByPropertyName)][Alias('FullName')][string]$Path)
    begin { Add-Type -AssemblyName System.Drawing }
    process {
        $img = [System.Drawing.Image]::FromFile((Resolve-Path -LiteralPath $Path).Path)
        try { [pscustomobject]@{ Name = Split-Path $Path -Leaf; Width = $img.Width; Height = $img.Height; SizeKB = [math]::Round((Get-Item -LiteralPath $Path).Length / 1KB) } }
        finally { $img.Dispose() }
    }
}

function Convert-Image {
    <# Get-ChildItem *.png | Convert-Image -Format jpg   (writes new files next to the originals) #>
    [CmdletBinding()]
    param(
        [Parameter(Mandatory, Position = 0, ValueFromPipeline, ValueFromPipelineByPropertyName)][Alias('FullName')][string]$Path,
        [Parameter(Mandatory)][ValidateSet('jpg', 'jpeg', 'png', 'bmp', 'gif', 'tiff', 'ico')][string]$Format,
        [ValidateRange(1, 100)][int]$Quality = 90,
        [string]$Destination
    )
    begin {
        Add-Type -AssemblyName System.Drawing
        $fmt = @{ jpg = 'Jpeg'; jpeg = 'Jpeg'; png = 'Png'; bmp = 'Bmp'; gif = 'Gif'; tiff = 'Tiff'; ico = 'Icon' }[$Format]
    }
    process {
        $src = (Resolve-Path -LiteralPath $Path).Path
        $dir = if ($Destination) { New-Item -ItemType Directory -Path $Destination -Force | Select-Object -ExpandProperty FullName } else { Split-Path $src }
        $out = Join-Path $dir ([IO.Path]::GetFileNameWithoutExtension($src) + '.' + $Format)
        if ($out -eq $src) { Write-Warning "$src is already $Format"; return }
        $img = [System.Drawing.Image]::FromFile($src)
        try {
            if ($fmt -eq 'Jpeg') {
                $codec = [System.Drawing.Imaging.ImageCodecInfo]::GetImageEncoders() | Where-Object MimeType -eq 'image/jpeg'
                $ep = [System.Drawing.Imaging.EncoderParameters]::new(1)
                $ep.Param[0] = [System.Drawing.Imaging.EncoderParameter]::new([System.Drawing.Imaging.Encoder]::Quality, [long]$Quality)
                # JPEG has no transparency: paint on white first
                $bmp = [System.Drawing.Bitmap]::new($img.Width, $img.Height)
                $g = [System.Drawing.Graphics]::FromImage($bmp); $g.Clear([System.Drawing.Color]::White); $g.DrawImage($img, 0, 0, $img.Width, $img.Height); $g.Dispose()
                $bmp.Save($out, $codec, $ep); $bmp.Dispose()
            } else {
                $img.Save($out, [System.Drawing.Imaging.ImageFormat]::$fmt)
            }
        } finally { $img.Dispose() }
        Get-Item -LiteralPath $out | Select-Object FullName, @{n = 'SizeKB'; e = { [math]::Round($_.Length / 1KB) } }
    }
}

function Resize-Image {
    <# Resize-Image photo.jpg -Percent 50 | -Width 1920   (writes photo-resized.jpg, keeps the original) #>
    [CmdletBinding(DefaultParameterSetName = 'Percent')]
    param(
        [Parameter(Mandatory, Position = 0, ValueFromPipeline, ValueFromPipelineByPropertyName)][Alias('FullName')][string]$Path,
        [Parameter(ParameterSetName = 'Percent', Mandatory)][ValidateRange(1, 1000)][int]$Percent,
        [Parameter(ParameterSetName = 'Width', Mandatory)][int]$Width,
        [switch]$Overwrite
    )
    begin { Add-Type -AssemblyName System.Drawing }
    process {
        $src = (Resolve-Path -LiteralPath $Path).Path
        $img = [System.Drawing.Image]::FromFile($src)
        try {
            if ($PSCmdlet.ParameterSetName -eq 'Width') { $w = $Width; $h = [int]($img.Height * $Width / $img.Width) }
            else { $w = [int]($img.Width * $Percent / 100); $h = [int]($img.Height * $Percent / 100) }
            $bmp = [System.Drawing.Bitmap]::new([math]::Max(1, $w), [math]::Max(1, $h))
            $g = [System.Drawing.Graphics]::FromImage($bmp)
            $g.InterpolationMode = 'HighQualityBicubic'; $g.SmoothingMode = 'HighQuality'; $g.PixelOffsetMode = 'HighQuality'
            $g.DrawImage($img, 0, 0, $bmp.Width, $bmp.Height); $g.Dispose()
            $format = $img.RawFormat
        } finally { $img.Dispose() }
        $out = if ($Overwrite) { $src } else { Join-Path (Split-Path $src) ([IO.Path]::GetFileNameWithoutExtension($src) + '-resized' + [IO.Path]::GetExtension($src)) }
        $bmp.Save($out, $format); $bmp.Dispose()
        Get-ImageInfo -Path $out
    }
}

# ------------------------------------------------------------------ files
function Remove-ToRecycleBin {
    <# Moves files or folders to the Recycle Bin (can be restored). Works with the pipeline. #>
    [CmdletBinding()]
    param([Parameter(Mandatory, Position = 0, ValueFromPipeline, ValueFromPipelineByPropertyName)][Alias('FullName')][string[]]$Path)
    begin { Initialize-SenseiNative; $all = [Collections.Generic.List[string]]::new() }
    process { foreach ($p in $Path) { foreach ($r in (Resolve-Path -Path $p -ErrorAction Continue)) { $all.Add($r.ProviderPath) } } }
    end {
        if (-not $all.Count) { 'Nothing to delete.'; return }
        for ($i = 0; $i -lt $all.Count; $i += 200) {
            $chunk = $all.GetRange($i, [math]::Min(200, $all.Count - $i)).ToArray()
            $rc = [SenseiNative.Recycle]::Send($chunk)
            if ($rc -ne 0) { Write-Error "Windows could not recycle some items (code $rc)." }
        }
        "$($all.Count) item(s) moved to the Recycle Bin."
    }
}

function Get-FolderSize {
    <# Get-FolderSize C:\Users\me\Downloads   |   Get-FolderSize $HOME -Subfolders (each subfolder, biggest first) #>
    [CmdletBinding()] param([Parameter(Position = 0)][string]$Path = '.', [switch]$Subfolders, [int]$Top = 20)
    $root = (Resolve-Path -LiteralPath $Path -ErrorAction Stop).Path
    $measure = {
        param($p)
        $m = Get-ChildItem -LiteralPath $p -File -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object Length -Sum
        [pscustomobject]@{ Folder = $p; SizeGB = [math]::Round($m.Sum / 1GB, 2); SizeMB = [math]::Round($m.Sum / 1MB); Files = $m.Count }
    }
    if (-not $Subfolders) { return & $measure $root }
    $dirs = Get-ChildItem -LiteralPath $root -Directory -Force -ErrorAction SilentlyContinue
    $dirs | ForEach-Object { & $measure $_.FullName } | Sort-Object SizeMB -Descending | Select-Object -First $Top
}

function Find-DuplicateFiles {
    <# Lists files with identical content (same size, then same hash), grouped. #>
    [CmdletBinding()] param([Parameter(Position = 0)][string]$Path = '.', [string[]]$Include = '*')
    Get-ChildItem -LiteralPath (Resolve-Path -LiteralPath $Path).Path -File -Recurse -Include $Include -ErrorAction SilentlyContinue |
        Group-Object Length | Where-Object Count -gt 1 | ForEach-Object { $_.Group } |
        Get-FileHash -Algorithm MD5 | Group-Object Hash | Where-Object Count -gt 1 |
        ForEach-Object { $i = $_; $i.Group | Select-Object @{n = 'Group'; e = { $i.Name.Substring(0, 8) } }, Path }
}

# ------------------------------------------------------------------ apps, timers, power
function Close-App {
    <# Asks the app to close normally (it may ask to save). -Force kills it if it is still open after 5 s. #>
    [CmdletBinding()] param([Parameter(Mandatory, Position = 0)][string]$Name, [switch]$Force)
    $procs = @(Get-Process -Name $Name -ErrorAction SilentlyContinue)
    if (-not $procs) { "$Name is not running."; return }
    foreach ($p in $procs) { if ($p.MainWindowHandle -ne 0) { [void]$p.CloseMainWindow() } }
    $deadline = (Get-Date).AddSeconds(5)
    while ((Get-Date) -lt $deadline -and (Get-Process -Name $Name -ErrorAction SilentlyContinue | Where-Object MainWindowHandle -ne 0)) { Start-Sleep -Milliseconds 300 }
    $left = @(Get-Process -Name $Name -ErrorAction SilentlyContinue)
    if ($left -and $Force) { $left | Stop-Process -Force; "$Name was force-closed." }
    elseif ($left | Where-Object MainWindowHandle -ne 0) { "$Name is still open (it may be asking to save). Use Close-App $Name -Force to kill it." }
    else { "$Name closed." }
}

function Start-Timer {
    <# Start-Timer -Minutes 5 -Message 'Tea'   (pops up and beeps; keeps running in the background) #>
    [CmdletBinding()] param([double]$Minutes = 0, [int]$Seconds = 0, [string]$Message = 'Time is up!')
    $total = [int]($Minutes * 60) + $Seconds
    if ($total -le 0) { throw 'Give -Minutes or -Seconds.' }
    $msg = $Message.Replace("'", "''")
    $script = "Start-Sleep -Seconds $total; 1..3 | ForEach-Object { [console]::Beep(880, 300); Start-Sleep -Milliseconds 150 }; " +
        "Add-Type -AssemblyName PresentationFramework; [void][System.Windows.MessageBox]::Show('$msg', 'Sensei timer')"
    $enc = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($script))
    $exe = (Get-Process -Id $PID).Path
    Start-Process -FilePath $exe -WindowStyle Hidden -ArgumentList '-NoProfile', '-EncodedCommand', $enc | Out-Null
    "Timer set for {0:hh\:mm\:ss} - it will pop up at {1:HH:mm:ss}." -f [timespan]::FromSeconds($total), (Get-Date).AddSeconds($total)
}

function Start-Shutdown {
    <# Start-Shutdown -At 23:00 | -InMinutes 10, add -Restart to restart instead. Cancel with Stop-Shutdown. #>
    [CmdletBinding(DefaultParameterSetName = 'In')]
    param([Parameter(ParameterSetName = 'At', Mandatory)][string]$At,
        [Parameter(ParameterSetName = 'In', Mandatory)][double]$InMinutes,
        [switch]$Restart)
    if ($PSCmdlet.ParameterSetName -eq 'At') {
        $when = Get-Date $At
        if ($when -le (Get-Date)) { $when = $when.AddDays(1) }
    } else { $when = (Get-Date).AddMinutes($InMinutes) }
    $secs = [int][math]::Max(0, ($when - (Get-Date)).TotalSeconds)
    $mode = if ($Restart) { '/r' } else { '/s' }
    shutdown.exe $mode /t $secs /c "Scheduled by Sensei" | Out-Null
    if ($LASTEXITCODE) { throw "shutdown.exe failed (exit $LASTEXITCODE). Is another shutdown already scheduled? Cancel it with Stop-Shutdown." }
    "{0} at {1:HH:mm:ss} (in {2} min). Cancel with Stop-Shutdown." -f $(if ($Restart) { 'Restart' } else { 'Shutdown' }), $when, [math]::Round($secs / 60)
}

function Start-SleepTimer {
    <# Start-SleepTimer -Minutes 30   puts the PC to sleep later (cancel with Stop-Shutdown) #>
    [CmdletBinding()] param([Parameter(Mandatory, Position = 0)][double]$Minutes)
    $secs = [int]($Minutes * 60)
    $script = "Start-Sleep -Seconds $secs; Add-Type -AssemblyName System.Windows.Forms; [void][System.Windows.Forms.Application]::SetSuspendState('Suspend', `$false, `$false) # SenseiSleepTimer"
    Start-Process -FilePath (Get-Process -Id $PID).Path -WindowStyle Hidden -ArgumentList '-NoProfile', '-Command', $script | Out-Null
    "The PC will sleep at {0:HH:mm} (in {1} min). Cancel with Stop-Shutdown." -f (Get-Date).AddSeconds($secs), [math]::Round($secs / 60)
}

function Stop-Shutdown {
    <# Cancels a scheduled shutdown/restart and any Sensei sleep timer. #>
    [CmdletBinding()] param()
    shutdown.exe /a 2>$null | Out-Null
    $aborted = -not $LASTEXITCODE
    $timers = @(Get-CimInstance Win32_Process -Filter "Name='pwsh.exe' OR Name='powershell.exe'" | Where-Object { $_.CommandLine -like '*SenseiSleepTimer*' -and $_.ProcessId -ne $PID -and $_.CommandLine -like '*Start-Sleep -Seconds*SetSuspendState*' })
    $timers | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    if ($aborted -and $timers) { 'Scheduled shutdown/restart and sleep timer cancelled.' }
    elseif ($aborted) { 'Scheduled shutdown/restart cancelled.' }
    elseif ($timers) { 'Sleep timer cancelled.' }
    else { 'No shutdown, restart or sleep timer was scheduled.' }
}

function Dismount-Drive {
    <# Safely ejects a USB drive: Dismount-Drive E #>
    [CmdletBinding()] param([Parameter(Mandatory, Position = 0)][ValidatePattern('^[A-Za-z]:?$')][string]$Letter)
    $l = $Letter.TrimEnd(':').ToUpper() + ':'
    $item = (New-Object -ComObject Shell.Application).Namespace(17).ParseName($l)
    if (-not $item) { throw "There is no drive $l" }
    $item.InvokeVerb('Eject')
    Start-Sleep -Seconds 2
    if (Test-Path "$l\") { "$l is still there (a program may be using it)." } else { "$l ejected - you can unplug it." }
}

# ------------------------------------------------------------------ network
function Get-PublicIP {
    [CmdletBinding()] param()
    [pscustomobject]@{ PublicIP = (Invoke-RestMethod -Uri 'https://api.ipify.org' -TimeoutSec 10) }
}

function Get-WifiPassword {
    <# Password of a saved Wi-Fi network; without -Name the one you are connected to. #>
    [CmdletBinding()] param([Parameter(Position = 0)][string]$Name)
    if (-not $Name) {
        $line = netsh wlan show interfaces | Where-Object { $_ -match '^\s*SSID\s*:' } | Select-Object -First 1
        if (-not $line) { throw 'Not connected to Wi-Fi. Give -Name (see: netsh wlan show profiles).' }
        $Name = ($line -split ':', 2)[1].Trim()
    }
    $out = netsh wlan show profile name="$Name" key=clear
    if ($LASTEXITCODE) { throw "No saved Wi-Fi network called '$Name'." }
    $key = $out | Where-Object { $_ -match 'Key Content' } | ForEach-Object { ($_ -split ':', 2)[1].Trim() }
    [pscustomobject]@{ Network = $Name; Password = $(if ($key) { $key } else { '(open network or password not stored)' }) }
}

function Test-InternetSpeed {
    <# Downloads 25 MB from Cloudflare and reports Mbps and ping. #>
    [CmdletBinding()] param([ValidateRange(1, 200)][int]$MB = 25)
    $ping = (Test-Connection -TargetName 1.1.1.1 -Count 3 -ErrorAction SilentlyContinue | Measure-Object Latency -Average).Average
    $client = [System.Net.Http.HttpClient]::new()
    $client.Timeout = [timespan]::FromSeconds(120)
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $bytes = $client.GetByteArrayAsync("https://speed.cloudflare.com/__down?bytes=$($MB * 1000000)").GetAwaiter().GetResult()
    $sw.Stop(); $client.Dispose()
    [pscustomobject]@{
        DownloadMbps = [math]::Round($bytes.Length * 8 / $sw.Elapsed.TotalSeconds / 1e6, 1)
        PingMs       = [math]::Round($ping)
        TestedMB     = [math]::Round($bytes.Length / 1e6)
    }
}

function Set-WifiState {
    <# Set-WifiState -On | -Off   (needs admin) #>
    [CmdletBinding()] param([switch]$On, [switch]$Off)
    $a = Get-NetAdapter -Physical | Where-Object { $_.PhysicalMediaType -match '802\.11|Wireless' -or $_.Name -match 'Wi-?Fi|WLAN' } | Select-Object -First 1
    if (-not $a) { throw 'No Wi-Fi adapter found.' }
    if ($Off) { Disable-NetAdapter -Name $a.Name -Confirm:$false -ErrorAction Stop; "Wi-Fi ($($a.Name)) turned off." }
    else { Enable-NetAdapter -Name $a.Name -Confirm:$false -ErrorAction Stop; "Wi-Fi ($($a.Name)) turned on." }
}

# ------------------------------------------------------------------ cleanup
function Clear-TempFiles {
    <# Deletes what can be deleted in your temp folder and reports the space freed. #>
    [CmdletBinding()] param()
    $size = { (Get-ChildItem $env:TEMP -File -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum }
    $before = & $size
    Get-ChildItem $env:TEMP -Force -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    $after = & $size
    "Freed {0:N0} MB ({1:N0} MB left in use by running programs)." -f (($before - $after) / 1MB), ($after / 1MB)
}

Export-ModuleMember -Function Get-AudioVolume, Set-AudioVolume, Out-Speech, Get-ScreenBrightness, Set-ScreenBrightness,
Set-DarkMode, Set-Wallpaper, Save-Screenshot, Get-ImageInfo, Convert-Image, Resize-Image, Remove-ToRecycleBin, Get-FolderSize,
Find-DuplicateFiles, Close-App, Start-Timer, Start-Shutdown, Stop-Shutdown, Start-SleepTimer, Set-ScreenOff, Dismount-Drive, Get-PublicIP, Get-WifiPassword,
Test-InternetSpeed, Set-WifiState, Clear-TempFiles
