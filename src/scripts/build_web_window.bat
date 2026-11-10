@echo off
cd /d "%~dp0"
python -m PyInstaller --noconfirm --onefile --windowed --name MTGDeckViewerHTML --distpath "..\dist" --workpath "..\build\web_window" --specpath "..\build" --add-data "..\mtg_deck_viewer.html;." run_web_window.py
if errorlevel 1 pause
