@echo off
setlocal
set "APP="
if exist "%~dp0dist\preview\CURRENT.txt" (
  set /p APP_VERSION=<"%~dp0dist\preview\CURRENT.txt"
)
if defined APP_VERSION if exist "%~dp0dist\preview\%APP_VERSION%\消除车牌\消除车牌.exe" (
  set "APP=%~dp0dist\preview\%APP_VERSION%\消除车牌\消除车牌.exe"
)
for /r "%~dp0dist\preview" %%F in (*.exe) do if not defined APP set "APP=%%~fF"
if not defined APP (
  echo 请先运行 packaging\build_preview.ps1 生成测试版。
  pause
  exit /b 1
)
start "" "%APP%"
endlocal
