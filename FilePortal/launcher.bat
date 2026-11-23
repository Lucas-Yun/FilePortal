@echo off
setlocal
title File Service Platform - Launcher
cd /d "%~dp0"

rem Locate the program folder by its entry files, so the launcher does not
rem depend on a hard-coded folder name.
set "APP_DIR="
for /d %%D in ("%~dp0*") do (
  if exist "%%~fD\app.py" if exist "%%~fD\console.py" set "APP_DIR=%%~fD"
)
if not defined APP_DIR (
  if exist "%~dp0app.py" if exist "%~dp0console.py" set "APP_DIR=%~dp0"
)
if not defined APP_DIR (
  echo.
  echo   [ERROR] Program folder was not found next to this launcher.
  echo           Expected a subfolder containing app.py and console.py.
  echo.
  pause
  exit /b 1
)
cd /d "%APP_DIR%"

set "PY="
if exist "%LOCALAPPDATA%\Programs\Python\Python314\python.exe" set "PY=%LOCALAPPDATA%\Programs\Python\Python314\python.exe"
if not defined PY (
  where py >nul 2>nul && set "PY=py -3"
)
if not defined PY (
  where python >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo.
  echo   [ERROR] Python 3 runtime was not detected on this host.
  echo           Please install Python 3 and ensure it is added to PATH,
  echo           then run this launcher again.
  echo.
  pause
  exit /b 1
)

set "PYW="
if exist "%LOCALAPPDATA%\Programs\Python\Python314\pythonw.exe" set "PYW=%LOCALAPPDATA%\Programs\Python\Python314\pythonw.exe"
if not defined PYW (
  where pythonw >nul 2>nul && set "PYW=pythonw"
)
if not defined PYW (
  where pyw >nul 2>nul && set "PYW=pyw -3"
)

echo.
echo   [INFO] Ensuring File Service Platform is running...
%PY% tray.py --ensure
if errorlevel 1 (
  echo   [ERROR] The service failed to start. See the runtime log folder for details.
  pause
  exit /b 1
)

if defined PYW (
  if exist "tray.py" (
    start "" %PYW% tray.py
    echo   [INFO] System tray manager enabled.
    echo          Right-click the tray icon to open the console, restart or stop the service.
  ) else (
    echo   [WARN] tray.py was not found; the tray manager was not started.
  )
) else (
  echo   [WARN] pythonw.exe was not found; the tray manager was not started.
)

ping -n 2 127.0.0.1 >nul 2>nul
exit /b 0
