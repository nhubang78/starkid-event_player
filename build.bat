@echo off
REM Dong goi Starkid Event Player thanh file chay .exe
REM Dong goi vao thu muc "stage" truoc, roi moi chep sang "release" (khong dung vao ban dang mo)
cd /d "%~dp0"
python -m pip install --user pyinstaller PySide6 mutagen av pillow
python -m PyInstaller --noconfirm --windowed --name StarkidEventPlayer --icon assets\app.ico ^
  --add-data "assets;assets" --collect-binaries av --distpath stage ^
  --exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.QtWebEngineWidgets ^
  --exclude-module PySide6.QtQuick --exclude-module PySide6.QtQml --exclude-module PySide6.QtPdf ^
  main.py
if errorlevel 1 goto :eof
tasklist /FI "IMAGENAME eq StarkidEventPlayer.exe" | find /I "StarkidEventPlayer.exe" >nul && (
  echo.
  echo Starkid Event Player dang mo - hay tat roi chay lai build.bat de cap nhat thu muc release.
  echo Ban moi da nam o: %~dp0stage\StarkidEventPlayer
  pause
  goto :eof
)
robocopy stage\StarkidEventPlayer release\StarkidEventPlayer /MIR /NFL /NDL /NJH /NJS /NP >nul
powershell -NoProfile -Command "Compress-Archive -Path 'release\StarkidEventPlayer' -DestinationPath 'release\StarkidEventPlayer-win64.zip' -Force"
echo.
echo Xong! File chay: %~dp0release\StarkidEventPlayer\StarkidEventPlayer.exe
echo File zip:       %~dp0release\StarkidEventPlayer-win64.zip
pause