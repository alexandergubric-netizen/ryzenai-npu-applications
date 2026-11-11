"""Native file and folder pickers, so the Library and Code mode get real paths (a browser page cannot)."""
import subprocess

from core.platform import NO_WINDOW, WINDOWS

PS = r"C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe"
SCRIPT = {
    "folder": r"""Add-Type -AssemblyName System.Windows.Forms
$o = New-Object System.Windows.Forms.Form -Property @{TopMost=$true}
$d = New-Object System.Windows.Forms.FolderBrowserDialog -Property @{Description='__TITLE__'; ShowNewFolderButton=$true; SelectedPath=$HOME}
if ($d.ShowDialog($o) -eq 'OK') { [Console]::OutputEncoding=[Text.UTF8Encoding]::new($false); [Console]::Write($d.SelectedPath) }""",
    "file": r"""Add-Type -AssemblyName System.Windows.Forms
$o = New-Object System.Windows.Forms.Form -Property @{TopMost=$true}
$d = New-Object System.Windows.Forms.OpenFileDialog -Property @{Title='__TITLE__'; InitialDirectory="$HOME\Documents"; Filter='Documents and code|*.txt;*.md;*.pdf;*.csv;*.json;*.py;*.js;*.ts;*.ps1;*.html;*.css;*.sql;*.c;*.cpp;*.cs;*.java|All files|*.*'}
if ($d.ShowDialog($o) -eq 'OK') { [Console]::OutputEncoding=[Text.UTF8Encoding]::new($false); [Console]::Write($d.FileName) }""",
}
# macOS: AppleScript's own chooser; the title contains only letters, digits and " .,:-()" (filtered below).
OSA = {"folder": 'POSIX path of (choose folder with prompt "__TITLE__")',
       "file": 'POSIX path of (choose file with prompt "__TITLE__")'}


def pick(kind, title):
    if kind not in SCRIPT:
        raise ValueError("Choose a file or a folder.")
    title = "".join(ch for ch in str(title or "")[:80] if ch.isalnum() or ch in " .,:-()")
    if WINDOWS:
        command = [PS, "-NoProfile", "-NonInteractive", "-STA", "-Command", SCRIPT[kind].replace("__TITLE__", title)]
    else:
        command = ["/usr/bin/osascript", "-e", OSA[kind].replace("__TITLE__", title or "Choose")]
    p = subprocess.run(command, capture_output=True, timeout=600, creationflags=NO_WINDOW)
    path = p.stdout.decode("utf-8", "replace").strip()
    if path and not WINDOWS and len(path) > 1:
        path = path.rstrip("/")
    return {"path": path} if path else {"cancelled": True}
