@echo off
setlocal
cd /d "%~dp0"
title GPT Image Studio
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" app.py %*
  goto done
)
py -3 -c "import sys; assert sys.version_info >= (3,10)" >nul 2>&1
if not errorlevel 1 (
  py -3 app.py %*
  goto done
)
python -c "import sys; assert sys.version_info >= (3,10)" >nul 2>&1
if not errorlevel 1 (
  python app.py %*
  goto done
)
rem Optional fallback for computers that already have the Codex Python runtime.
if exist "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" (
  "%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe" app.py %*
  goto done
)
echo Python 3.10 or newer is required.
echo Install it from https://www.python.org/downloads/ and enable Add Python to PATH.
:done
pause
