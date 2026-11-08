@echo off
cd /d "%~dp0"
REM Original verified monochrome display; F10 switches colour effect on/off.
REM Normal play: recording is OFF unless you press F8.
python play.py --overlay none
if errorlevel 1 pause
