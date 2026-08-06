@echo off
setlocal DisableDelayedExpansion
set "ISSUES=%*"
if "%ISSUES%"=="" (
  set /p ISSUES=请输入期数，例如 187 188 189: 
)
if "%ISSUES%"=="" (
  echo 必须手动指定至少一个期数。
  pause
  exit /b 1
)
pushd "%~dp0"
python "run_multi.py" "%ISSUES%"
set "PYTHON_EXIT=%ERRORLEVEL%"
popd
pause
exit /b %PYTHON_EXIT%
