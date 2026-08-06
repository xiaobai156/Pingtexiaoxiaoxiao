@echo off
setlocal
set "ISSUE=%~1"
if "%ISSUE%"=="" (
  set /p ISSUE=Input issue number, for example 164: 
)
if "%ISSUE%"=="" (
  echo No issue number entered.
  pause
  exit /b 1
)
pushd "%~dp0"
python "run_single.py" "%ISSUE%"
set "PYTHON_EXIT=%ERRORLEVEL%"
popd
pause
exit /b %PYTHON_EXIT%
