@echo off
setlocal DisableDelayedExpansion
set "ISSUE=%~1"
if "%ISSUE%"=="" (
  set /p ISSUE=Input issue number, for example 164: 
)
if "%ISSUE%"=="" (
  echo An issue number is required.
  pause
  exit /b 1
)
pushd "%~dp0"
python "run_single.py" "%ISSUE%"
set "PYTHON_EXIT=%ERRORLEVEL%"
popd
pause
exit /b %PYTHON_EXIT%
