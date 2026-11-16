@echo off
cd /d "%~dp0"
python -m PyInstaller --noconfirm --onefile --windowed --name MTGDeckViewerHTML --paths "%~dp0.." --distpath "..\..\release" --workpath "..\..\build\web_window" --specpath "..\..\build" --add-data "%~dp0..\..\mtg_deck_viewer.html;." --add-data "%~dp0..\..\card_preview.html;." "%~dp0run_web_window.py"
if errorlevel 1 pause
