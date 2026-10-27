# Builds Sensei's command catalog: every cmdlet/function on this PC with its parameters and aliases.
# The checker reads it instead of calling Get-Command, which would load a module (1-4 s each) the first time.
# Runs in the background on first start and again when PowerShell or the installed modules change.
param([Parameter(Mandatory)][string]$Out)
$ErrorActionPreference = 'SilentlyContinue'
$ProgressPreference = 'SilentlyContinue'
$WarningPreference = 'SilentlyContinue'
Import-Module (Join-Path $PSScriptRoot 'SenseiTools.psm1') -DisableNameChecking

$commands = @{}
# parameters are only known once a module is loaded, so load every installed module once (here, not in Sensei)
foreach ($m in Get-Module -ListAvailable | Sort-Object Name -Unique) {
    if (-not (Get-Module -Name $m.Name)) { try { Import-Module -Name $m.Name -ErrorAction Stop -WarningAction SilentlyContinue 3>$null } catch {} }
}
foreach ($c in Get-Command -CommandType Cmdlet, Function, Filter) {
    if ($commands.ContainsKey($c.Name)) { continue }
    $p = $null
    try { $p = $c.Parameters } catch {}
    $names = [Collections.Generic.List[string]]::new()
    if ($p) { foreach ($v in $p.Values) { $names.Add($v.Name); foreach ($a in $v.Aliases) { $names.Add($a) } } }
    $commands[$c.Name] = @{ m = "$($c.Source)"; t = "$($c.CommandType)"; p = $names }
}
$aliases = @{}
foreach ($a in Get-Alias) { $aliases[$a.Name] = "$($a.Definition)" }

$data = [ordered]@{
    version     = 1
    built       = (Get-Date).ToString('o')
    ps          = "$($PSVersionTable.PSVersion)"
    fingerprint = $env:SENSEI_CATALOG_FP
    commands    = $commands
    aliases     = $aliases
}
$tmp = "$Out.tmp"
$data | ConvertTo-Json -Depth 4 -Compress | Set-Content -LiteralPath $tmp -Encoding utf8
Move-Item -LiteralPath $tmp -Destination $Out -Force
"catalog: $($commands.Count) commands, $($aliases.Count) aliases"
