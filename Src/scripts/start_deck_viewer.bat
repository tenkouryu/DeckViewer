@echo off
cd /d "%~dp0"
python -m mtg.mtg_deck_viewer
if errorlevel 1 pause
