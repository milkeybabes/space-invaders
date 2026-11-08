@echo off
cd /d "%~dp0"
REM Classic Midway red/green cellophane overlay, display-only.
REM F10 toggles monochrome/colour; F9 toggles sound; Shift+F9 saves a RAM snapshot.
REM Normal play: recording is OFF unless you press F8.
python play.py --overlay classic
if errorlevel 1 pause
