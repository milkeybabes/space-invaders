@echo off
cd /d "%~dp0"
REM Example of operator DIP options (6 lives, bonus at 1500 points).
python play.py --artwork cabinet --overlay classic -lives 6 -bonus 1500
if errorlevel 1 pause
