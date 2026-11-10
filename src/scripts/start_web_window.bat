@echo off
cd /d "%~dp0"
python -m mtg.mtg_web_window
if errorlevel 1 pause
