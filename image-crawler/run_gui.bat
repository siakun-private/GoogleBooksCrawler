@echo off
setlocal
REM Keep settings and downloads relative to this crawler after relocation.
pushd "%~dp0"
echo Starting Google Books Crawler GUI...
echo.

if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" gui_app.py
) else (
    python gui_app.py
)

set "crawler_exit_code=%ERRORLEVEL%"
popd
pause
exit /b %crawler_exit_code%
