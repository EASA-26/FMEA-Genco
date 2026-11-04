@echo off
REM ============================================================
REM  FMEA Report Generator - local launcher
REM  Double-click this file to (re)start the app and open it in
REM  your default browser. If the app is already running, it is
REM  stopped first, so this is also the way to restart it.
REM  This window is the server: leave it open while you use the
REM  app, and close it (or press Ctrl+C) to stop the app.
REM ============================================================
setlocal
title FMEA Report App
cd /d "%~dp0"

echo ============================================
echo   FMEA Report Generator - local app
echo ============================================
echo.

REM --- Python: the project's .venv if there is one, otherwise the installed Python.
set "PY=python"
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
%PY% --version >nul 2>&1
if errorlevel 1 (
  echo [error] Python was not found. Install Python 3.11 or later, then run this file again.
  goto :fail
)

REM --- Python packages: installed only when some are missing.
%PY% -c "import importlib.util, sys; sys.exit(any(importlib.util.find_spec(m) is None for m in ('fastapi', 'uvicorn', 'python_multipart', 'pydantic', 'openpyxl', 'reportlab', 'PIL')))" >nul 2>&1
if errorlevel 1 (
  echo [setup] Installing the Python packages ...
  %PY% -m pip install -r requirements.txt
  if errorlevel 1 goto :fail
)

REM --- Frontend: rebuilt only when frontend\dist\index.html is missing or older
REM     than any file in frontend\src, frontend\public or the frontend config.
set "NEED_BUILD="
%PY% -c "import pathlib, sys; f = pathlib.Path('frontend'); built = (f / 'dist' / 'index.html').stat().st_mtime; source = [p for d in ('src', 'public') for p in (f / d).rglob('*')] + [f / n for n in ('index.html', 'package.json', 'package-lock.json', 'vite.config.js')]; sys.exit(any(p.is_file() and p.stat().st_mtime > built for p in source))" >nul 2>&1 || set "NEED_BUILD=1"
if not defined NEED_BUILD goto :frontend_ready

where node >nul 2>&1 || goto :no_node
where npm >nul 2>&1 || goto :no_node
if not exist "frontend\node_modules\vite\package.json" (
  echo [setup] Installing the frontend packages ...
  call npm --prefix frontend ci --no-audit --no-fund || goto :build_failed
)
echo [setup] Building the frontend ...
REM Same as "npm run build", but through Vite's API so it exits as soon as the
REM build is written: on some PCs the "net use" lookup Vite starts in the
REM background keeps "npm run build" open for about five more minutes.
pushd frontend
node -e "import('vite').then((vite) => vite.build()).then(() => process.exit(0), (err) => { console.error(err); process.exit(1); })"
if errorlevel 1 (
  popd
  goto :build_failed
)
popd
echo.
goto :frontend_ready

:no_node
echo [warn] The frontend needs building, but Node.js / npm was not found.
goto :use_last_build

:build_failed
echo [warn] The frontend build failed - see the messages above.

:use_last_build
if not exist "frontend\dist\index.html" goto :fail
echo [warn] The app will run with the last frontend build.
echo.

:frontend_ready

REM --- Address and port: the same settings app.py uses (environment, then .env).
set "APP_HOST=127.0.0.1"
set "APP_PORT=8000"
for /f "tokens=1,2" %%A in ('%PY% -c "from backend.settings import get_settings; s = get_settings(); print(s.host, s.port)" 2^>nul') do (
  set "APP_HOST=%%A"
  set "APP_PORT=%%B"
)
if "%APP_HOST%"=="0.0.0.0" set "APP_HOST=127.0.0.1"
set "APP_URL=http://%APP_HOST%:%APP_PORT%"

REM --- Restart: if a program is listening on the port and it is this FMEA app,
REM     stop it, and close the window this file opened for it. Any other program
REM     using the port is left alone and named instead.
set "PORT_PID="
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%APP_PORT% .*:0 "') do set "PORT_PID=%%P"
if not defined PORT_PID goto :port_free
set "FMEA_LAUNCHER=%~f0"
powershell -NoProfile -Command ^
  "$listener = [int]$env:PORT_PID; $procs = @(Get-CimInstance Win32_Process);" ^
  "$self = ($procs | Where-Object ProcessId -eq $PID).ParentProcessId;" ^
  "$chain = @(); $id = $listener; $child = $null;" ^
  "while ($id -and $chain.Count -lt 6) {" ^
  "  $p = $procs | Where-Object ProcessId -eq $id | Select-Object -First 1;" ^
  "  if (-not $p -or ($child -and $p.CreationDate -gt $child.CreationDate)) { break };" ^
  "  $chain += $p; $child = $p; $id = $p.ParentProcessId };" ^
  "$isFmea = $false;" ^
  "try { $isFmea = (Invoke-WebRequest ($env:APP_URL + '/') -UseBasicParsing -TimeoutSec 5).Content -match '<title>[^<]*FMEA' } catch { };" ^
  "$launcher = $chain | Where-Object { $_.Name -eq 'cmd.exe' -and $_.ProcessId -ne $self -and $_.CommandLine -and $_.CommandLine.ToLower().Contains($env:FMEA_LAUNCHER.ToLower()) } | Select-Object -First 1;" ^
  "if (-not $isFmea -and -not $launcher) {" ^
  "  Write-Host ('[error] Port ' + $env:APP_PORT + ' is already used by another program: ' + $chain[0].Name + ' (PID ' + $listener + ').');" ^
  "  Write-Host '[error] Close that program, or the window running it, then run this file again.'; exit 2 };" ^
  "$target = $listener;" ^
  "foreach ($p in $chain) { if ($p.Name -in 'python.exe', 'pythonw.exe', 'py.exe') { $target = $p.ProcessId } else { break } };" ^
  "if ($launcher) { $target = $launcher.ProcessId };" ^
  "Write-Host ('[restart] Stopping the FMEA app that is already running (PID ' + $listener + ') ...');" ^
  "taskkill /PID $target /T /F | Out-Null;" ^
  "Wait-Process -Id $listener -Timeout 15 -ErrorAction SilentlyContinue;" ^
  "if (Get-Process -Id $listener -ErrorAction SilentlyContinue) { Write-Host ('[error] The app on port ' + $env:APP_PORT + ' did not stop.'); exit 3 }"
if errorlevel 1 goto :fail
:port_free

REM --- Run. A background helper opens the browser once the app answers.
echo [run] Starting the app on %APP_URL%
echo [run] Your browser opens when it is ready.
echo [run] Leave this window OPEN while you use the app. Close it, or press Ctrl+C, to stop.
echo.
start "" /b powershell -NoProfile -Command "for ($i = 0; $i -lt 120; $i++) { try { Invoke-WebRequest ($env:APP_URL + '/api/health') -UseBasicParsing -TimeoutSec 2 | Out-Null; Start-Process $env:APP_URL; exit } catch { Start-Sleep -Milliseconds 500 } }"
%PY% app.py

echo.
echo [stopped] The app has stopped. Press any key to close this window.
pause >nul
exit /b 0

:fail
echo.
echo [error] The app could not be started - see the messages above.
pause
exit /b 1
