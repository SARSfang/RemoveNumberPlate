@echo off
setlocal
set "APP="
for /r "%~dp0dist\preview" %%F in (*.exe) do if not defined APP set "APP=%%~fF"
if not defined APP (
  echo 请先运行 packaging\build_preview.ps1 生成测试版。
  pause
  exit /b 1
)
start "" "%APP%"
endlocal
