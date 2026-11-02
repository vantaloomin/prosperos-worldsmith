@echo off
rem Stops a running Worldsmith: the Python process listening on its port (8795, or the one given: stop.bat 8800).
setlocal
set "port=%~1"
if "%port%"=="" set "port=8795"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -Command ^
  "$found = Get-NetTCPConnection -LocalAddress 127.0.0.1 -LocalPort %port% -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Get-Process -Id $_.OwningProcess -ErrorAction SilentlyContinue } | Where-Object { $_.ProcessName -like 'python*' } | Sort-Object Id -Unique;" ^
  "if (-not $found) { Write-Host 'Worldsmith is not running on port %port%.'; exit 0 }" ^
  "$found | ForEach-Object { Stop-Process -Id $_.Id -Force; Write-Host ('Stopped Worldsmith (process ' + $_.Id + ').') }"
exit /b %ERRORLEVEL%
