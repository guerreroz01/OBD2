@echo off
setlocal
cd /d "%~dp0"
echo OBD Desk 0.2 - Entorno virtual local de Windows
if exist ".venv\Scripts\python.exe" goto install
set "BASEPY="
py -3.13 --version >nul 2>&1
if not errorlevel 1 set "BASEPY=py -3.13"
if defined BASEPY goto create
py -3.12 --version >nul 2>&1
if not errorlevel 1 set "BASEPY=py -3.12"
if defined BASEPY goto create
py -3 -c "import sys; sys.exit(sys.version_info < (3,10))" >nul 2>&1
if not errorlevel 1 set "BASEPY=py -3"
if defined BASEPY goto create
python -c "import sys; sys.exit(sys.version_info < (3,10))" >nul 2>&1
if not errorlevel 1 set "BASEPY=python"
if defined BASEPY goto create
echo Instala Python con Tcl/Tk. Para esta base, usa Python 3.12 o 3.13.
goto fail
:create
%BASEPY% -m venv ".venv"
if errorlevel 1 goto fail
:install
".venv\Scripts\python.exe" -c "from runtime import require_venv; require_venv(); import sys; print(sys.executable)"
if errorlevel 1 goto fail
".venv\Scripts\python.exe" -m pip --require-virtualenv install -r requirements.txt
if errorlevel 1 goto fail
".venv\Scripts\python.exe" -m pip check
if errorlevel 1 goto fail
".venv\Scripts\python.exe" -c "import tkinter, obd, serial; print('Dependencias importadas correctamente.')"
if errorlevel 1 goto fail
echo.
echo Preparado. Abre demo_windows.bat o iniciar_windows.bat.
echo Las dependencias se han instalado solo en .venv.
pause
exit /b 0
:fail
echo.
echo No se completo la instalacion. Conserva el error anterior.
echo No se han solicitado instalaciones globales de paquetes.
pause
exit /b 1
