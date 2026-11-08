@echo off
cd /d "%~dp0"
REM Space Invaders Python v1.0 - normal play, no AVI recording.
REM Normal play: recording is OFF unless you press F8.
python play.py
if errorlevel 1 pause
