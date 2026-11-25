@echo off
REM Tao file cai dat Starkid Event Player: release\StarkidEventPlayer-Setup-<phien ban>.exe
REM Can: Python + thu vien (tu cai), Inno Setup 6 (winget install JRSoftware.InnoSetup)
cd /d "%~dp0"
setlocal
for /f "tokens=2 delims==" %%v in ('findstr /b /c:"VERSION = " main.py') do set VER=%%~v
set VER=%VER: =%
set VER=%VER:"=%
echo Phien ban: %VER%

set ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe
if not exist "%ISCC%" set ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe
if not exist "%ISCC%" set ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe
if not exist "%ISCC%" (
  echo Chua co Inno Setup. Cai bang lenh:  winget install JRSoftware.InnoSetup
  pause
  goto :eof
)

python -m pip install --user pyinstaller PySide6 mutagen av pillow numpy
python -m PyInstaller --noconfirm --windowed --name StarkidEventPlayer --icon assets\app.ico ^
  --add-data "assets;assets" --collect-binaries av --distpath stage ^
  --exclude-module PySide6.QtWebEngineCore --exclude-module PySide6.QtWebEngineWidgets ^
  --exclude-module PySide6.QtQuick --exclude-module PySide6.QtQml --exclude-module PySide6.QtPdf ^
  main.py
if errorlevel 1 (
  echo Dong goi that bai.
  pause
  goto :eof
)
"%ISCC%" /Q /DAppVer=%VER% installer.iss
if errorlevel 1 (
  echo Tao file cai dat that bai.
  pause
  goto :eof
)
echo.
echo Xong! File cai dat: %~dp0release\StarkidEventPlayer-Setup-%VER%.exe
pause