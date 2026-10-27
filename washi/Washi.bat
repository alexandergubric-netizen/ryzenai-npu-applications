@echo off
rem Starts Washi from this folder (the desktop shortcut runs pythonw app.py directly, without a console window).
start "" pythonw "%~dp0app.py" %*
