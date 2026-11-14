@echo off
chcp 65001 >nul
cd /d "%~dp0"
set MODE=%~1
set ARG2=%~2
set ARG3=%~3
set PY=python
where python >nul 2>&1
if errorlevel 1 set PY=py -3

echo ==========================================
if /i "%MODE%"=="next" (
  echo  LeadHunter: filling the NEXT job from the queue
) else (
  echo  LeadHunter: filling ONE job from the clipboard
  echo  Copy a job link first, then run this.
)
echo ==========================================
echo.

if /i "%MODE%"=="next" (
  %PY% next.py %ARG2% %ARG3%
) else (
  %PY% autofill.py %ARG2% %ARG3%
)
set RC=%ERRORLEVEL%
echo.
echo [%DATE% %TIME%] mode=%MODE% exit=%RC% >> "%~dp0run.log"
if not "%RC%"=="0" echo Something went wrong, exit code %RC%. Messages above.
echo.
pause
