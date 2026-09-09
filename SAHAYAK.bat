@echo off
setlocal EnableExtensions EnableDelayedExpansion
title SAHAYAK v6
cd /d "%~dp0"

rem =====================================================================
rem  SAHAYAK v6 - single launcher
rem
rem    SAHAYAK.bat            first run: full setup, then start (default)
rem    SAHAYAK.bat setup      force re-install of Python + Node packages
rem    SAHAYAK.bat test       run the backend test-suite (pytest)
rem    SAHAYAK.bat stop       close the backend / frontend windows
rem
rem  Needs: Windows 10/11, Anaconda or Miniconda, Chrome or Edge,
rem         internet the first time (packages + AI models).
rem =====================================================================

set "ROOT=%~dp0"
set "APP=%ROOT%SAHAYAK-main"
set "BACKEND=%APP%\backend"
set "FRONTEND=%APP%\frontend"
set "RUNDIR=%ROOT%.sahayak"
set "LOG=%ROOT%sahayak.log"
set "ENV_NAME=sahayak"
set "MODE=%~1"
if "%MODE%"=="" set "MODE=run"
if not exist "%RUNDIR%" mkdir "%RUNDIR%"

echo.
echo  =====================================================================
echo   SAHAYAK v6  -  AI-assisted stress ^& vulnerability triage   [%MODE%]
echo  =====================================================================
echo.
echo ==== SAHAYAK v6 [%MODE%] %DATE% %TIME% ==== >> "%LOG%"

if /i "%MODE%"=="stop" goto :stop

rem ---------------------------------------------------------------------
rem  0. Project folder (extract the zip if it is next to this file)
rem ---------------------------------------------------------------------
if not exist "%BACKEND%\services\tone_engine.py" (
  if exist "%ROOT%SAHAYAK-multimodal-v6.zip" (
    echo [0/4] Extracting SAHAYAK-multimodal-v6.zip ...
    if exist "%BACKEND%\data\cases.json" copy /y "%BACKEND%\data\cases.json" "%ROOT%cases.backup.json" >nul
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Expand-Archive -Force -LiteralPath '%ROOT%SAHAYAK-multimodal-v6.zip' -DestinationPath '%ROOT%.'"
    if exist "%ROOT%cases.backup.json" (
      copy /y "%ROOT%cases.backup.json" "%BACKEND%\data\cases.json" >nul
      del "%ROOT%cases.backup.json"
    )
  )
)
if not exist "%BACKEND%\main.py" (
  echo   The project folder "SAHAYAK-main" was not found next to this file.
  echo   Put SAHAYAK.bat inside the extracted SAHAYAK folder and run it again.
  pause
  exit /b 1
)

rem ---------------------------------------------------------------------
rem  1. Anaconda / Miniconda
rem ---------------------------------------------------------------------
set "CONDA_BAT="
for %%D in ("%USERPROFILE%\anaconda3" "%USERPROFILE%\miniconda3" "%ProgramData%\anaconda3" "%ProgramData%\miniconda3" "%LOCALAPPDATA%\anaconda3" "%LOCALAPPDATA%\miniconda3" "C:\anaconda3" "C:\miniconda3") do (
  if not defined CONDA_BAT if exist "%%~D\condabin\conda.bat" set "CONDA_BAT=%%~D\condabin\conda.bat"
)
if not defined CONDA_BAT (
  echo   Anaconda / Miniconda was not found.
  echo   Install Miniconda from https://docs.conda.io/en/latest/miniconda.html and run this file again.
  pause
  exit /b 1
)

call "%CONDA_BAT%" activate %ENV_NAME% >nul 2>&1
python -c "import sys; sys.exit(0 if '%ENV_NAME%' in sys.prefix.lower() else 1)" >nul 2>&1
if errorlevel 1 (
  echo [1/4] Creating the "%ENV_NAME%" environment ^(Python 3.11, ffmpeg, Node 22^) ...
  echo       first time only - this takes a few minutes.
  call "%CONDA_BAT%" create -y -n %ENV_NAME% -c conda-forge python=3.11 ffmpeg nodejs=22 --quiet >> "%LOG%" 2>&1
  if errorlevel 1 (
    echo   Environment creation failed - see sahayak.log
    pause
    exit /b 1
  )
  call "%CONDA_BAT%" activate %ENV_NAME%
) else (
  echo [1/4] Environment "%ENV_NAME%" ready.
)
python --version
node --version
ffmpeg -version 2>nul | findstr /i "ffmpeg version"

rem ---------------------------------------------------------------------
rem  2. Python packages (only when requirements.txt changed, or "setup")
rem ---------------------------------------------------------------------
set "NEED_PIP=0"
if /i "%MODE%"=="setup" set "NEED_PIP=1"
if not exist "%BACKEND%\.deps_installed" set "NEED_PIP=1"
if "%NEED_PIP%"=="0" fc /b "%BACKEND%\requirements.txt" "%BACKEND%\.deps_installed" >nul 2>&1 || set "NEED_PIP=1"
if "%NEED_PIP%"=="1" (
  echo [2/4] Installing Python packages ^(PyTorch, Whisper, librosa, MediaPipe, OpenCV ...^)
  echo       several minutes on the first run.
  python -m pip install --upgrade pip --quiet >> "%LOG%" 2>&1
  python -m pip install -r "%BACKEND%\requirements.txt" --progress-bar off
  if errorlevel 1 (
    echo.
    echo   Package installation failed. Trying again without the optional video-footage packages ...
    findstr /v /i "mediapipe opencv" "%BACKEND%\requirements.txt" > "%RUNDIR%\requirements-core.txt"
    python -m pip install -r "%RUNDIR%\requirements-core.txt" --progress-bar off
    if errorlevel 1 (
      echo   Python package installation failed - see the messages above.
      pause
      exit /b 1
    )
    echo   Core packages installed. Uploaded VIDEO FILES will be analysed for audio only
    echo   ^(live camera tracking in the browser still works^).
  )
  copy /y "%BACKEND%\requirements.txt" "%BACKEND%\.deps_installed" >nul
) else (
  echo [2/4] Python packages up to date.
)
if not exist "%BACKEND%\.env" copy "%BACKEND%\.env.example" "%BACKEND%\.env" >nul

rem ---------------------------------------------------------------------
rem  3. Frontend packages (only when package.json changed, or "setup")
rem ---------------------------------------------------------------------
set "NEED_NPM=0"
if /i "%MODE%"=="setup" set "NEED_NPM=1"
if not exist "%FRONTEND%\node_modules\.package-lock.json" set "NEED_NPM=1"
if not exist "%FRONTEND%\.deps_installed" set "NEED_NPM=1"
if "%NEED_NPM%"=="0" fc /b "%FRONTEND%\package.json" "%FRONTEND%\.deps_installed" >nul 2>&1 || set "NEED_NPM=1"
if "%NEED_NPM%"=="1" (
  echo [3/4] Installing frontend packages ...
  pushd "%FRONTEND%"
  call npm install --no-audit --no-fund
  if errorlevel 1 (
    popd
    echo   npm install failed - see the messages above.
    pause
    exit /b 1
  )
  popd
  copy /y "%FRONTEND%\package.json" "%FRONTEND%\.deps_installed" >nul
) else (
  echo [3/4] Frontend packages up to date.
)
if not exist "%FRONTEND%\.env" copy "%FRONTEND%\.env.example" "%FRONTEND%\.env" >nul

if /i "%MODE%"=="test" goto :test
if /i "%MODE%"=="setup" (
  echo.
  echo   Setup complete. Double-click SAHAYAK.bat to start.
  pause
  exit /b 0
)

rem ---------------------------------------------------------------------
rem  4. Start backend + frontend in their own windows, then open the app
rem ---------------------------------------------------------------------
if not exist "%RUNDIR%" mkdir "%RUNDIR%"

> "%RUNDIR%\backend.cmd" (
  echo @echo off
  echo title SAHAYAK backend ^(FastAPI^)
  echo call "%CONDA_BAT%" activate %ENV_NAME%
  echo cd /d "%BACKEND%"
  echo echo Backend starting on http://127.0.0.1:8000  ^(API docs: /docs^)
  echo echo First request downloads the NLP model; first video file downloads the MediaPipe models.
  echo uvicorn main:app --host 127.0.0.1 --port 8000
  echo echo.
  echo echo Backend stopped. Press any key to close.
  echo pause ^>nul
)
> "%RUNDIR%\frontend.cmd" (
  echo @echo off
  echo title SAHAYAK frontend ^(Vite^)
  echo call "%CONDA_BAT%" activate %ENV_NAME%
  echo cd /d "%FRONTEND%"
  echo call npm run dev -- --port 5173 --strictPort
  echo echo.
  echo echo Frontend stopped. Press any key to close.
  echo pause ^>nul
)

echo [4/4] Starting servers ...
netstat -ano | findstr /r /c:":8000 .*LISTENING" >nul 2>&1
if not errorlevel 1 (
  echo       something already listens on port 8000 - reusing the running backend.
) else (
  start "SAHAYAK backend" "%RUNDIR%\backend.cmd"
)
netstat -ano | findstr /r /c:":5173 .*LISTENING" >nul 2>&1
if not errorlevel 1 (
  echo       something already listens on port 5173 - reusing the running frontend.
) else (
  start "SAHAYAK frontend" "%RUNDIR%\frontend.cmd"
)

echo       waiting for the backend ^(up to 90 s - the first start loads Whisper^) ...
set "READY=0"
for /l %%I in (1,1,45) do (
  if "!READY!"=="0" (
    powershell -NoProfile -Command "try { $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 http://127.0.0.1:8000/api/health; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
    if not errorlevel 1 set "READY=1"
    if "!READY!"=="0" timeout /t 2 /nobreak >nul
  )
)
if "!READY!"=="1" (echo       backend is up.) else (echo       backend not answering yet - it may still be loading; the page will retry.)
timeout /t 3 /nobreak >nul
start "" http://localhost:5173

echo.
echo  =====================================================================
echo   SAHAYAK v6 is running.  Keep the two server windows open.
echo.
echo   App      : http://localhost:5173        ^(use Chrome or Edge^)
echo   API docs : http://127.0.0.1:8000/docs
echo.
echo   Sign in  : admin@sahayak.local / Admin@123          ^(full responder view^)
echo              authority@sahayak.local / Authority@123  ^(full responder view^)
echo              "Create account" as a User to see the participant view
echo.
echo   Stop     : SAHAYAK.bat stop   ^(or close the two server windows^)
echo   Tests    : SAHAYAK.bat test
echo  =====================================================================
pause
exit /b 0

rem ---------------------------------------------------------------------
:test
echo.
echo  Running backend tests ...
pushd "%BACKEND%"
python -m pytest -q
set "RC=%errorlevel%"
popd
echo.
if "%RC%"=="0" (echo  All tests passed.) else (echo  Some tests failed - see above.)
pause
exit /b %RC%

rem ---------------------------------------------------------------------
:stop
echo  Stopping SAHAYAK servers ...
taskkill /fi "WINDOWTITLE eq SAHAYAK backend*" /t /f >nul 2>&1
taskkill /fi "WINDOWTITLE eq SAHAYAK frontend*" /t /f >nul 2>&1
rem also free the ports in case a window was renamed
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /r /c:":8000 .*LISTENING" /c:":5173 .*LISTENING"') do taskkill /pid %%P /t /f >nul 2>&1
echo  Done.
timeout /t 2 /nobreak >nul
exit /b 0
