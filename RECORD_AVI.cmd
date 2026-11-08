@echo off
cd /d "%~dp0"
REM OPTIONAL ONLY: this launcher starts AVI recording immediately.
REM Normal PLAY and PLAY_CABINET launchers do NOT record automatically.
REM F8 stops/starts recording; ESC exits and finalises the AVI.
REM Output goes to recordings\ as AVI plus per-frame CSV.
python play.py --record-avi
if errorlevel 1 pause
