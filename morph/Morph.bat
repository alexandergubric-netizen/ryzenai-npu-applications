@echo off
rem Morph - starts the app without a console window.
cd /d "%~dp0"
where pythonw >nul 2>nul && (start "" pythonw "%~dp0app.py") || (start "" /min python "%~dp0app.py")
