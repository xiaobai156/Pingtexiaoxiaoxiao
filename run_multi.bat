@echo off
setlocal DisableDelayedExpansion
set "ISSUES=%*"
if "%ISSUES%"=="" (
  set /p ISSUES=Input issue numbers, for example 187 188 189: 
)
if "%ISSUES%"=="" (
  echo No issue number entered.
  pause
  exit /b 1
)
pushd "%~dp0"
python "run_multi.py" "%ISSUES%"
set "PYTHON_EXIT=%ERRORLEVEL%"
popd
pause
exit /b %PYTHON_EXIT%
