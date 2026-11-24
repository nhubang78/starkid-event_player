@echo off
REM Dong goi EventPlayer thanh file chay .exe (thu muc dist\EventPlayer)
cd /d "%~dp0"
python -m pip install --user pyinstaller PySide6 mutagen
python -m PyInstaller --noconfirm --windowed --name EventPlayer --distpath release ^
  --exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.QtWebEngineWidgets ^
  --exclude-module PySide6.QtQuick --exclude-module PySide6.QtQml --exclude-module PySide6.QtPdf ^
  main.py
echo.
echo Xong! File chay: %~dp0release\EventPlayer\EventPlayer.exe
pause
