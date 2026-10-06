@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Ejecuta instalar_windows.bat antes de continuar.
  pause
  exit /b 1
)
".venv\Scripts\python.exe" app.py %*
set "RESULT=%ERRORLEVEL%"
if not "%RESULT%"=="0" pause
exit /b %RESULT%
