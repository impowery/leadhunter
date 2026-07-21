@echo off
setlocal
cd /d "%~dp0"

REM === НАСТРОЙКА (скопируй и заполни .env) ===
set TG_API_ID=
set TG_API_HASH=
set GROQ_API_KEY=
set OPENROUTER_API_KEY=

REM === ЗАПУСК ===
echo Starting Lead Hunter Pro...
python lead_hunter_pro.py %*
pause
