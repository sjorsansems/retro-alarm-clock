@echo off
setlocal

python "%~dp0tools\convert_upload.py" %*
set EXIT_CODE=%ERRORLEVEL%

if %EXIT_CODE%==9009 (
    echo Python niet gevonden in PATH. Activeer je venv of installeer Python.
)

endlocal & exit /b %EXIT_CODE%
