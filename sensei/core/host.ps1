# Sensei PowerShell host.
# Connects back to the app over a local socket and executes requests one at a time.
#   -Mode run     a persistent session: variables and the current folder survive between commands
#   -Mode verify  checks AI-written commands against this PC (syntax, commands, parameters, risk)
param([int]$Port, [string]$Token, [string]$Mode = 'run', [int]$Width = 150, [string]$Catalog = '')

$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'
$ConfirmPreference = 'None'
if ($PSStyle) { $PSStyle.OutputRendering = 'PlainText' }
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$OutputEncoding = [Text.UTF8Encoding]::new($false)

Import-Module (Join-Path $PSScriptRoot 'SenseiTools.psm1') -DisableNameChecking
# there is no console to clear here (the app clears its own output)
function global:Clear-Host { }

$__client = [Net.Sockets.TcpClient]::new('127.0.0.1', $Port)
$__client.NoDelay = $true
$__stream = $__client.GetStream()
$__reader = [IO.StreamReader]::new($__stream, [Text.UTF8Encoding]::new($false))
$__writer = [IO.StreamWriter]::new($__stream, [Text.UTF8Encoding]::new($false))
$__writer.AutoFlush = $false
$__writer.WriteLine($Token); $__writer.Flush()

$__jsonOpts = [Text.Json.JsonSerializerOptions]::new()
function __Send([string]$type, $data) {
    $json = if ($data -is [string]) { [Text.Json.JsonSerializer]::Serialize($data, [string], $__jsonOpts) }
            elseif ($null -eq $data) { 'null' }
            else { ConvertTo-Json -InputObject $data -Compress -Depth 6 }
    $__writer.WriteLine('{"t":"' + $type + '","d":' + $json + '}')
}

# ------------------------------------------------------------------ verification
# Read-only means "only reads": anything that can run code, open files, load modules or call .NET methods by name is
# at least 'caution', because the UI runs read-only library commands without a click.
$__safeVerbs = 'Get', 'Test', 'Measure', 'Select', 'Sort', 'Where', 'Group', 'Compare', 'Find', 'Search',
'Resolve', 'Show', 'Read', 'Format', 'Out', 'ConvertTo', 'ConvertFrom', 'Join', 'Split', 'Trace', 'Write', 'Wait', 'Tee'
$__dangerVerbs = 'Remove', 'Clear', 'Uninstall', 'Disable', 'Reset', 'Unregister', 'Dismount', 'Revoke', 'Suspend', 'Block'
$__dangerCmds = 'Format-Volume', 'Stop-Computer', 'Restart-Computer', 'Initialize-Disk', 'Clear-Disk', 'Set-ExecutionPolicy',
'Stop-Process', 'Remove-Partition', 'Set-Partition', 'Resize-Partition', 'Invoke-Expression', 'Set-MpPreference',
'Remove-AppxPackage', 'Disable-NetAdapter', 'Set-NetFirewallProfile', 'Clear-RecycleBin', 'Remove-Item', 'Checkpoint-Computer'
$__safeNative = 'ipconfig', 'ping', 'tracert', 'pathping', 'nslookup', 'whoami', 'hostname', 'systeminfo', 'netstat',
'tasklist', 'where', 'driverquery', 'getmac', 'nvidia-smi', 'arp', 'route', 'ver', 'tree', 'fc', 'findstr', 'more',
'chcp', 'qwinsta', 'query', 'w32tm', 'powercfg', 'gpresult', 'flm'
# programs that can download, decode or run code from files or the internet (living-off-the-land binaries)
$__lolNative = 'curl', 'certutil', 'wmic', 'bitsadmin', 'mshta', 'rundll32', 'regsvr32', 'cscript', 'wscript', 'msiexec',
'installutil', 'regasm', 'regsvcs', 'msbuild', 'hh', 'forfiles', 'pcalua', 'cmstp', 'odbcconf', 'mavinject', 'esentutl', 'expand',
'extrac32', 'makecab', 'replace', 'xcopy', 'robocopy', 'scp', 'sftp', 'tftp'
$__dangerNative = 'format', 'diskpart', 'shutdown', 'bcdedit', 'del', 'erase', 'rd', 'rmdir', 'takeown', 'icacls', 'cipher',
'reg', 'vssadmin', 'wbadmin', 'net', 'sc', 'schtasks', 'fsutil', 'manage-bde', 'netsh'
$__openers = 'taskmgr', 'devmgmt', 'services', 'diskmgmt', 'eventvwr', 'compmgmt', 'control', 'explorer', 'notepad', 'calc',
'mspaint', 'msinfo32', 'resmon', 'perfmon', 'appwiz', 'ncpa', 'sysdm', 'mmsys', 'main', 'inetcpl', 'firewall', 'code', 'start'
$__safeCmds = 'Clear-Host', 'New-Guid', 'New-TimeSpan', 'Get-Random', 'Set-Location', 'Push-Location', 'Pop-Location',
'Start-Sleep', 'Set-Clipboard', 'Format-Table', 'Format-List', 'Format-Wide', 'Format-Custom', 'Format-Hex',
'Out-String', 'Out-Host', 'Out-Null', 'Get-Help', 'Import-Csv', 'Import-PowerShellDataFile', 'Import-LocalizedData'
# commands that look harmless by name but open, load or run something
$__codeCmds = @{
    'Invoke-Item'     = 'opens a file or program (it may run it)'
    'Import-Module'   = 'loads a PowerShell module (runs its code)'
    'Import-Clixml'   = 'loads saved objects from a file'
    'Update-TypeData' = 'changes how PowerShell treats objects'
    'Update-FormatData' = 'changes how PowerShell shows objects'
    'Invoke-Command'  = 'runs a script block'
    'New-Module'      = 'builds a module from code'
}
# .NET member names that delete, stop or change things, and names that run code
$__destructiveMembers = '^(Delete|Kill|Remove|Format|Shutdown|Terminate|Uninstall|Encrypt|Decrypt|SetAccessControl|Empty)$'
$__codeMembers = '^(Invoke|InvokeReturnAsIs|InvokeWithContext|Create|CreateInstance|Load|LoadFrom|LoadFile|UnsafeLoadFrom|Start|Run|Execute|ExecuteCommand|ShellExecute|InvokeVerb|InvokeVerbEx|SetSuspendState|ExitWindowsEx|SetValue|SetEnvironmentVariable|Exit|FailFast|MoveTo|CopyTo|Save|WriteAll\w*|AppendAll\w*|SetAttributes|SetLastWriteTime\w*|SetCreationTime\w*)$'
# property names ForEach-Object may read without any risk (anything else could be a method call)
$__readMembers = '^(Name|FullName|BaseName|Extension|Length|Id|Count|Value|Key|Path|DisplayName|ProcessName|ToString|Trim|ToUpper|ToLower|IPAddress|IPv4Address|Version|Status|Source|Definition|Directory|DirectoryName|Mode|LastWriteTime|CreationTime|Size|Message|Description|Title|Line|Matches|Groups)$'
# static methods that only compute or read (anything else on a static type is 'caution')
$__pureStatic = '^(new|Get\w*|To\w+|Parse\w*|TryParse\w*|Convert\w*|Hash\w*|Compute\w*|StartNew|Format|Join|Concat|Round|Floor|Ceiling|Truncate|Abs|Max|Min|Pow|Sqrt|Log\w*|Exp|Sign|Sin|Cos|Tan|Equals|Compare\w*|IsNullOr\w+|Escape\w*|Unescape\w*|Match|Matches|IsMatch|Split|From\w+|Exists|Combine|HasExtension|IsPathRooted|Sum|Average|Reverse|Sort|IndexOf|Contains|NewGuid|IsDefined|ReferenceEquals|Now|UtcNow|Today|Create\w*Comparer|Distinct|Where|Select|First\w*|Last\w*|Count|Any|All|Range|Repeat|Empty|Ordinal\w*|Invariant\w*)$'
# Sensei's own helpers (SenseiTools.psm1)
$__helperRisk = @{
    'Remove-ToRecycleBin' = 'caution', 'moves items to the Recycle Bin (you can restore them)'
    'Start-Shutdown'      = 'danger', 'shuts down or restarts the PC'
    'Stop-Shutdown'       = 'caution', 'cancels a scheduled shutdown'
    'Start-SleepTimer'    = 'caution', 'puts the PC to sleep later'
    'Set-ScreenOff'       = 'caution', 'turns the screen off until you move the mouse'
    'Set-AudioVolume'     = 'caution', 'changes the volume'
    'Set-ScreenBrightness' = 'caution', 'changes the screen brightness'
    'Set-DarkMode'        = 'caution', 'changes the Windows theme'
    'Set-Wallpaper'       = 'caution', 'changes the wallpaper'
    'Save-Screenshot'     = 'caution', 'saves a screenshot file'
    'Convert-Image'       = 'caution', 'writes converted copies (originals are kept)'
    'Resize-Image'        = 'caution', 'writes resized copies (originals are kept)'
    'Close-App'           = 'caution', 'closes an app (it may ask to save)'
    'Start-Timer'         = 'caution', 'starts a timer in the background'
    'Dismount-Drive'      = 'caution', 'ejects a drive'
    'Set-WifiState'       = 'caution', 'turns Wi-Fi on or off'
    'Clear-TempFiles'     = 'caution', 'deletes temporary files'
    'Out-Speech'          = 'safe', ''
    'Test-InternetSpeed'  = 'caution', 'downloads test data from the internet'
    'Get-PublicIP'        = 'caution', 'asks an internet service for your public IP'
}
# commands that wait for keyboard input or never finish: better in a real terminal window
$__interactive = 'Read-Host', 'Get-Credential', 'Enter-PSSession', 'ssh', 'diskpart', 'python', 'py', 'node', 'nano', 'vim',
'vi', 'edit', 'Out-GridView', 'pause', 'choice', 'telnet', 'ftp', 'wsl', 'bash', 'cmd', 'powershell', 'pwsh'
# parameters that only exist on some providers (FileSystem, Certificate, Registry, ...) and are not visible to Get-Command
$__providerParams = 'File', 'Directory', 'Hidden', 'ReadOnly', 'System', 'Attributes', 'FollowSymlink', 'Encoding', 'Delimiter',
'Wait', 'Raw', 'Stream', 'AsByteStream', 'NoNewline', 'CodeSigningCert', 'DocumentEncryptionCert', 'SSLServerAuthentication',
'DnsName', 'Eku', 'ExpiringInDays', 'Type', 'PropertyType', 'Value', 'ItemType', 'Tail', 'TotalCount', 'Head', 'First', 'Last',
'ReadCount', 'Depth'
$__common = 'Verbose', 'Debug', 'ErrorAction', 'WarningAction', 'InformationAction', 'ProgressAction', 'ErrorVariable',
'WarningVariable', 'InformationVariable', 'OutVariable', 'OutBuffer', 'PipelineVariable', 'WhatIf', 'Confirm', 'vb', 'db',
'ea', 'wa', 'infa', 'proga', 'ev', 'wv', 'iv', 'ov', 'ob', 'pv', 'wi', 'cf'

# ------------------------------------------------------------------ command catalog (built by build_catalog.ps1)
$__cat = $false
$__catCmds = [Collections.Generic.Dictionary[string, object]]::new([StringComparer]::OrdinalIgnoreCase)
$__catAliases = [Collections.Generic.Dictionary[string, string]]::new([StringComparer]::OrdinalIgnoreCase)
function __LoadCatalog {
    if (-not $Catalog -or -not (Test-Path -LiteralPath $Catalog)) { return $false }
    try {
        $j = [IO.File]::ReadAllText($Catalog) | ConvertFrom-Json -AsHashtable
        $script:__catCmds.Clear(); $script:__catAliases.Clear()
        foreach ($k in $j.commands.Keys) { $v = $j.commands[$k]; $script:__catCmds[$k] = @{ name = $k; t = $v.t; m = $v.m; p = [string[]]$v.p } }
        foreach ($k in $j.aliases.Keys) { $script:__catAliases[$k] = $j.aliases[$k] }
        # Sensei's helpers are always current (the file may be newer than the catalog)
        foreach ($c in Get-Command -Module SenseiTools) { $script:__catCmds[$c.Name] = @{ name = $c.Name; t = 'Function'; m = 'SenseiTools'; p = [string[]]$(foreach ($v in $c.Parameters.Values) { $v.Name; $v.Aliases }) } }
        $script:__cat = $true
    } catch { $script:__cat = $false }
    $script:__cat
}
if ($Mode -eq 'verify') { [void](__LoadCatalog) }

function __Rank([string]$r) { switch ($r) { 'danger' { 3 } 'caution' { 2 } default { 1 } } }

function __Verify([string]$code) {
    $res = [ordered]@{ syntax = @(); commands = @(); problems = @(); risk = 'safe'; reasons = @(); interactive = $false }
    $script:__risk = 'safe'
    function Raise([string]$level, [string]$why) {
        if ((__Rank $level) -gt (__Rank $script:__risk)) { $script:__risk = $level }
        if ($why -and $res.reasons -notcontains $why) { $res.reasons += $why }
    }

    # <placeholders> are for the user to fill in; replace them so the parser can still check the rest
    $placeholders = @([regex]::Matches($code, '<([A-Za-z][\w \-\.]{0,40})>') | ForEach-Object { $_.Value } | Select-Object -Unique)
    $res.placeholders = $placeholders
    $parseCode = [regex]::Replace($code, '<([A-Za-z][\w \-\.]{0,40})>', 'PLACEHOLDER')

    $tokens = $null; $errs = $null
    $ast = [Management.Automation.Language.Parser]::ParseInput($parseCode, [ref]$tokens, [ref]$errs)
    foreach ($e in $errs) { $res.syntax += "$($e.Message) (line $($e.Extent.StartLineNumber))" }

    $defined = @($ast.FindAll({ $args[0] -is [Management.Automation.Language.FunctionDefinitionAst] }, $true) | ForEach-Object Name)
    $cmds = $ast.FindAll({ $args[0] -is [Management.Automation.Language.CommandAst] }, $true)
    foreach ($c in $cmds) {
        $name = $c.GetCommandName()
        if (-not $name) { Raise 'caution' 'runs a dynamic command'; continue }
        if ($defined -contains $name -or $name -eq 'PLACEHOLDER') { continue }
        $leaf = [IO.Path]::GetFileNameWithoutExtension($name)
        $argText = ($c.CommandElements | Select-Object -Skip 1 | ForEach-Object { $_.Extent.Text }) -join ' '
        if ($__interactive -contains $leaf -and -not ($leaf -in 'wsl', 'cmd', 'powershell', 'pwsh', 'python', 'py', 'node' -and $argText)) { $res.interactive = $true }
        if ($name -eq 'Get-Content' -and $argText -match '-Wait\b') { $res.interactive = $true }
        if ($leaf -eq 'ping' -and $argText -match '(^|\s)[-/]t\b') { $res.interactive = $true }
        # --- look the command up: the catalog first (instant), Get-Command only for programs/scripts or without a catalog
        $real = $null; $ctype = $null; $source = ''; $plist = $null
        if ($__cat) {
            $n = $name
            if ($__catAliases.ContainsKey($n)) { $n = $__catAliases[$n] }
            if ($__catCmds.ContainsKey($n)) {
                $e = $__catCmds[$n]; $real = $e.name; $ctype = $e.t; $source = $e.m; $plist = $e.p
            }
        }
        if (-not $real) {
            $types = if ($__cat) { 'Application', 'ExternalScript' } else { 'All' }
            $info = Get-Command -Name $name -CommandType $types -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($info -and $info.CommandType -eq 'Alias' -and $info.ResolvedCommand) { $info = $info.ResolvedCommand }
            if ($info) {
                $real = $info.Name; $ctype = "$($info.CommandType)"; $source = "$($info.Source)"
                if ($ctype -in 'Cmdlet', 'Function', 'Filter', 'ExternalScript') {
                    try { $plist = foreach ($v in $info.Parameters.Values) { $v.Name; $v.Aliases } } catch {}
                }
            }
        }
        if (-not $real) {
            if ($name -match '[\\/]' -or $name -like '*.*') { Raise 'caution' "runs $name"; $res.commands += @{ name = $name; found = $false; type = 'path' }; continue }
            $res.commands += @{ name = $name; found = $false }
            $res.problems += "'$name' is not a command on this PC."
            Raise 'caution' "unknown command $name"
            continue
        }
        $res.commands += @{ name = $real; found = $true; type = $ctype; source = $source }

        # --- parameters
        if ($plist -and @($plist).Count) {
            $plist = @($plist)
            foreach ($el in $c.CommandElements) {
                if ($el -isnot [Management.Automation.Language.CommandParameterAst]) { continue }
                $pn = $el.ParameterName
                if ($__common -contains $pn) { continue }
                if ($plist -contains $pn) { continue }
                $hit = @($plist | Where-Object { $_ -like "$pn*" } | Select-Object -Unique)
                if (-not $hit -and $__providerParams -contains $pn) { continue }
                if ($hit.Count -eq 0) {
                    $valid = ($plist | Where-Object { $__common -notcontains $_ } | Select-Object -Unique -First 40) -join ', -'
                    $res.problems += "$real has no parameter -$pn. Its parameters are: -$valid"
                } elseif ($hit.Count -gt 1) {
                    $res.problems += "-$pn is ambiguous for $real (could be: $($hit -join ', '))."
                }
            }
        }

        # --- risk
        $verb = if ($real -match '^([A-Za-z]+)-') { $Matches[1] } else { '' }
        $base = [IO.Path]::GetFileNameWithoutExtension($real).ToLower()
        $hasWhatIf = @($c.CommandElements | Where-Object { $_ -is [Management.Automation.Language.CommandParameterAst] -and $_.ParameterName -eq 'WhatIf' }).Count -gt 0
        if ($ctype -eq 'Application') {
            $args1 = ($c.CommandElements | Select-Object -Skip 1 | ForEach-Object { $_.Extent.Text }) -join ' '
            if ($__dangerNative -contains $base) {
                if ($base -eq 'netsh' -and $args1 -match '\bshow\b') { continue }
                if ($base -in 'sc', 'schtasks', 'net' -and $args1 -match '^(query|/query|user$|view|share$|start$|localgroup$)') { continue }
                if ($base -eq 'reg' -and $args1 -match '^query') { continue }
                if ($base -in 'sfc', 'dism' -and $args1 -match 'verifyonly|checkhealth|scanhealth|get-') { continue }
                Raise 'danger' "$base can change or delete system data"
            } elseif ($base -eq 'winget') {
                if ($args1 -notmatch '^(list|search|show|--version|-v)\b') { Raise 'caution' 'installs or changes software' }
            } elseif ($base -eq 'flm') {
                if ($args1 -notmatch '^(list|version|port|help|-h|--help|-v)\b') { Raise 'caution' 'changes FastFlowLM models or servers' }
            } elseif ($base -eq 'powercfg') {
                if ($args1 -notmatch '^[-/](list|l|batteryreport|energy|a|availablesleepstates|query|q|getactivescheme|sleepstudy|requests|lastwake|devicequery)\b') { Raise 'caution' 'changes power settings' }
            } elseif ($base -in 'sfc', 'dism') {
                if ($args1 -notmatch 'verifyonly|checkhealth|scanhealth|/get-') { Raise 'caution' "$base repairs Windows system files" }
            } elseif ($__lolNative -contains $base) {
                if ($base -eq 'certutil' -and $args1 -match '^[-/]hashfile\b') { }
                elseif ($base -eq 'wmic' -and $args1 -match '\b(get|list)\b' -and $args1 -notmatch '\b(call|create|delete|set)\b') { }
                elseif ($base -eq 'mshta') { Raise 'danger' 'mshta runs scripts from files or web pages' }
                else { Raise 'caution' "$base can download, unpack or run code" }
            } elseif ($__openers -contains $base) {
            } elseif ($__safeNative -notcontains $base) { Raise 'caution' "runs the program $base" }
        } elseif ($__helperRisk.ContainsKey($real)) {
            $hr = $__helperRisk[$real]
            if ($hr[0] -ne 'safe') { Raise $hr[0] $hr[1] }
        } elseif ($__codeCmds.ContainsKey($real)) {
            Raise 'caution' "$real $($__codeCmds[$real])"
        } elseif ($real -eq 'Add-Type') {
            # loading a framework assembly by name is harmless; compiling or loading code is not
            $named = @($c.CommandElements | Where-Object { $_ -is [Management.Automation.Language.CommandParameterAst] } | ForEach-Object ParameterName)
            if (@($named | Where-Object { $_ -notlike 'Assembly*' -and $__common -notcontains $_ }).Count -or -not @($named | Where-Object { $_ -like 'Assembly*' }).Count) {
                Raise 'caution' 'Add-Type compiles or loads code'
            }
        } elseif ($real -eq 'ForEach-Object') {
            # ForEach-Object Delete / % Kill / -MemberName X call a method by name on every item
            $member = $null
            for ($k = 1; $k -lt $c.CommandElements.Count; $k++) {
                $el = $c.CommandElements[$k]
                if ($el -is [Management.Automation.Language.CommandParameterAst]) {
                    if ($el.ParameterName -like 'M*' -and 'MemberName' -like "$($el.ParameterName)*") {
                        $member = if ($el.Argument) { $el.Argument.Extent.Text } elseif ($k + 1 -lt $c.CommandElements.Count) { $c.CommandElements[$k + 1].Extent.Text }
                        break
                    }
                    if ($el.ParameterName -like 'A*' -or $el.ParameterName -like 'I*') { $k++ }   # -ArgumentList / -InputObject value
                    continue
                }
                if ($el -is [Management.Automation.Language.StringConstantExpressionAst] -or $el -is [Management.Automation.Language.ExpandableStringExpressionAst]) { $member = $el.Extent.Text; break }
            }
            if ($member) {
                $m = $member.Trim("'", '"')
                $withArgs = @($c.CommandElements | Where-Object { $_ -is [Management.Automation.Language.CommandParameterAst] -and $_.ParameterName -like 'A*' }).Count
                if ($m -match $__destructiveMembers) { Raise 'danger' "calls $m on every item" }
                elseif ($withArgs -or $m -match $__codeMembers -or $m -notmatch $__readMembers) { Raise 'caution' "calls the member $m on every item" }
            }
        } elseif ($__safeCmds -contains $real) {
        } elseif ($__dangerCmds -contains $real -or $__dangerVerbs -contains $verb) {
            if ($hasWhatIf) { Raise 'caution' "$real (preview only, -WhatIf)" } else { Raise 'danger' "$real changes or removes things" }
        } elseif ($real -eq 'Out-GridView') {
        } elseif ($verb -in 'Out', 'Export', 'Tee' -or $real -eq 'Set-Content' -or $real -eq 'Add-Content') {
            Raise 'caution' "$real writes to a file"
        } elseif ($__safeVerbs -notcontains $verb) {
            Raise 'caution' "$real changes something"
        }
        if ($real -in 'Invoke-WebRequest', 'Invoke-RestMethod', 'Start-BitsTransfer') { Raise 'caution' 'uses the internet' }
        if ($real -eq 'New-Object' -and @($c.CommandElements | Where-Object { $_ -is [Management.Automation.Language.CommandParameterAst] -and $_.ParameterName -like 'Com*' }).Count) {
            Raise 'caution' 'uses a COM object (it can open, run or change things)'
        }
    }
    if ($ast.FindAll({ $args[0] -is [Management.Automation.Language.FileRedirectionAst] }, $true).Count) { Raise 'caution' 'writes output to a file' }
    $calls = @($ast.FindAll({ $args[0] -is [Management.Automation.Language.InvokeMemberExpressionAst] }, $true))
    foreach ($call in $calls) {
        $mn = $call.Member.Extent.Text.Trim("'", '"')
        $target = $call.Expression.Extent.Text
        if ($mn -match $__destructiveMembers -and -not ($call.Static -and $mn -eq 'Format')) { Raise 'danger' "calls the .NET method $mn, which deletes or stops things"; continue }
        if ($mn -match $__codeMembers) { Raise 'caution' "calls the .NET method $mn, which runs or changes something"; continue }
        if ($call.Static) {
            if ($target -match '^\[(System\.)?(IO\.|Diagnostics\.Process|Environment\]|Microsoft\.Win32|Runtime\.InteropServices|Reflection\.|Activator|Management\.Automation)') {
                Raise 'caution' "calls .NET methods on $target"
            } elseif ($mn -notmatch $__pureStatic) {
                Raise 'caution' "calls the .NET method $target::$mn"
            }
        }
    }
    # script blocks built from text and then run escape the command check above
    if ($ast.FindAll({ $args[0] -is [Management.Automation.Language.TypeExpressionAst] -and $args[0].TypeName.FullName -match '^(System\.Management\.Automation\.)?ScriptBlock$' }, $true).Count) {
        Raise 'caution' 'builds code at run time'
    }
    $res.risk = $script:__risk
    $res
}

function __Env {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $os = Get-CimInstance Win32_OperatingSystem -Property Caption, BuildNumber -ErrorAction SilentlyContinue
    [ordered]@{
        user     = $env:USERNAME
        computer = $env:COMPUTERNAME
        home     = $HOME
        cwd      = $PWD.Path
        ps       = "$($PSVersionTable.PSVersion)"
        os       = "$($os.Caption) (build $($os.BuildNumber))"
        admin    = ([Security.Principal.WindowsPrincipal]$id).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
        onedrive = [bool]$env:OneDrive
        desktop  = [Environment]::GetFolderPath('Desktop')
        documents = [Environment]::GetFolderPath('MyDocuments')
    }
}

__Send 'ready' (__Env)
$__writer.Flush()

# ------------------------------------------------------------------ main loop
while ($true) {
    $__line = $null
    try { $__line = $__reader.ReadLine() } catch { break }
    if ($null -eq $__line) { break }
    try { $__msg = $__line | ConvertFrom-Json } catch { continue }

    if ($__msg.op -eq 'verify') {
        try {
            if ($__msg.cwd -and (Test-Path -LiteralPath $__msg.cwd)) { Set-Location -LiteralPath $__msg.cwd }
            __Send 'verify' (__Verify $__msg.code)
        } catch { __Send 'verify' @{ syntax = @(); commands = @(); problems = @(); risk = 'caution'; reasons = @("could not be checked: $_") } }
        $__writer.Flush(); continue
    }
    if ($__msg.op -eq 'env') { __Send 'env' (__Env); $__writer.Flush(); continue }
    if ($__msg.op -eq 'reload') { __Send 'reload' @{ catalog = (__LoadCatalog); commands = $__catCmds.Count }; $__writer.Flush(); continue }
    if ($__msg.op -eq 'warm') {
        # load a module ahead of time, so the first command that needs it does not wait
        $__t0 = [Diagnostics.Stopwatch]::StartNew()
        try { Import-Module $__msg.module -ErrorAction Stop -WarningAction SilentlyContinue 3>$null } catch {}
        __Send 'warm' @{ module = $__msg.module; ms = $__t0.ElapsedMilliseconds }; $__writer.Flush(); continue
    }
    if ($__msg.op -ne 'run') { continue }

    # ---- run user code at script scope, so variables and the location persist
    $__t0 = [Diagnostics.Stopwatch]::StartNew()
    $__errors = 0; $__lines = 0; $__dropped = 0; $__lastFlush = 0
    $global:LASTEXITCODE = 0
    $__sp = { Out-String -Stream -Width $Width }.GetSteppablePipeline()
    $__sp.Begin($true)
    $__emit = {
        param($t, $s)
        if ($__lines -ge 4000) { $script:__dropped++; return }
        $script:__lines++
        __Send $t $s
        if ($__t0.ElapsedMilliseconds - $script:__lastFlush -gt 60) { $__writer.Flush(); $script:__lastFlush = $__t0.ElapsedMilliseconds }
    }
    try {
        $__sb = [scriptblock]::Create($__msg.code)
        . $__sb 2>&1 3>&1 4>&1 6>&1 | ForEach-Object {
            $__o = $_
            if ($__o -is [Management.Automation.ErrorRecord]) {
                if ($__o.Exception -is [Management.Automation.RemoteException]) { & $__emit 'stderr' "$__o" }
                else { $__errors++; foreach ($__l in (($__o | Out-String -Width $Width).TrimEnd() -split "`r?`n")) { & $__emit 'err' $__l } }
            } elseif ($__o -is [Management.Automation.WarningRecord]) { & $__emit 'warn' "WARNING: $($__o.Message)" }
            elseif ($__o -is [Management.Automation.VerboseRecord]) { & $__emit 'info' "VERBOSE: $($__o.Message)" }
            elseif ($__o -is [Management.Automation.InformationRecord]) { & $__emit 'out' "$($__o.MessageData)" }
            else { foreach ($__l in $__sp.Process($__o)) { & $__emit 'out' $__l } }
        }
    } catch {
        $__errors++
        foreach ($__l in (($_ | Out-String -Width $Width).TrimEnd() -split "`r?`n")) { & $__emit 'err' $__l }
    }
    try { foreach ($__l in $__sp.End()) { & $__emit 'out' $__l } } catch {}
    $__code = $global:LASTEXITCODE
    __Send 'done' ([ordered]@{ ok = ($__errors -eq 0 -and -not $__code); errors = $__errors; exit = $__code; ms = $__t0.ElapsedMilliseconds; cwd = $PWD.Path; dropped = $__dropped })
    $__writer.Flush()
}

[Environment]::Exit(0)
