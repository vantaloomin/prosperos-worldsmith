@echo off
rem Sets up Worldsmith: a Python environment in Program\.venv and the built screen in Program\dist.
rem Needs Python 3.12+ and Node 22+ on PATH. Run it again after updating.
setlocal
pushd "%~dp0..\Program" || exit /b 1
if not exist .venv (
  py -3.12 -m venv .venv 2>nul || python -m venv .venv || goto :failed
)
.venv\Scripts\python -m pip install --upgrade pip || goto :failed
.venv\Scripts\python -m pip install -e . || goto :failed
call npm ci --no-audit --no-fund || goto :failed
call npm run build || goto :failed
echo.
echo Worldsmith is installed. Start it with Windows\launch.bat.
popd
exit /b 0
:failed
echo.
echo Installing Worldsmith did not finish. Check the messages above.
popd
exit /b 1
