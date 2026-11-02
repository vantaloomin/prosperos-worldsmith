@echo off
rem For working on Worldsmith: the server on 8795 in its own window, and Vite with live reload on 5187.
setlocal
pushd "%~dp0..\Program" || exit /b 1
start "Worldsmith server" .venv\Scripts\python -m worldsmith --no-browser
call npm run dev
popd
