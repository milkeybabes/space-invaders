@echo off
cd /d "%~dp0"
REM Moon backdrop with pixel-exact 3x Space Invaders and classic colour strip.
REM Normal play: recording is OFF unless you press F8.
python play.py --artwork backdrop --overlay classic
if errorlevel 1 pause
