param([Parameter(Mandatory)][string]$InputPath)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false)
$base=Join-Path $PSScriptRoot '../vendor/sensei'
$Mode='offline-catalog'
$Catalog=Join-Path $base 'catalog.json'
. (Join-Path $base 'checker.ps1')
$data=[IO.File]::ReadAllText($Catalog) | ConvertFrom-Json
foreach($entry in $data.commands.psobject.Properties) {
    $v=$entry.Value
    $__catCmds[$entry.Name]=@{name=$entry.Name;t=$v.t;m=$v.m;p=[string[]]$v.p}
}
foreach($entry in $data.aliases.psobject.Properties){$__catAliases[$entry.Name]=[string]$entry.Value}
$__cat=$true
$items=[IO.File]::ReadAllText($InputPath) | ConvertFrom-Json
$results=@(foreach($code in $items){__Verify $code})
ConvertTo-Json -InputObject $results -Depth 8 -Compress

