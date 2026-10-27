@echo off
rem Kaizen 5S - starts the local server (no console window) and opens the app window.
cd /d "%~dp0"
where pythonw >nul 2>nul
if %errorlevel%==0 (
  start "" pythonw "%~dp0app.py"
) else (
  start "" /min python "%~dp0app.py"
)
