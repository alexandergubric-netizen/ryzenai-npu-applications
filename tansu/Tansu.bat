@echo off
rem Tansu - starts the app without a console window, on its own bundled Python (runtime\).
rem Paths given here (or by Explorer "Send to") are archived.
cd /d "%~dp0"
if exist "%~dp0runtime\pythonw.exe" (start "" "%~dp0runtime\pythonw.exe" "%~dp0app.py" %*) else (start "" pythonw "%~dp0app.py" %*)
