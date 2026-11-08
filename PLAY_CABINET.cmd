@echo off
cd /d "%~dp0"
REM Mode 3: movable fixed-size moon backdrop + slim bezel + classic colour strip.
REM Native 224x256 game uses integer pixels; F11 cycles modes, F10 toggles strip.
REM Normal play: recording is OFF unless you press F8.
python play.py --artwork cabinet --overlay classic
if errorlevel 1 pause
