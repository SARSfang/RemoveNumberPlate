@echo off
chcp 65001 >nul
setlocal
set "HdApplication=%~dp0dist\hd-preview-final\消除车牌\消除车牌.exe"
if not exist "%HdApplication%" (
  echo 高清测试版尚未构建。
  pause
  exit /b 1
)
if not "%~1"=="" (
  "%HdApplication%" %*
  exit /b
)
start "" "%HdApplication%"
if errorlevel 1 (
  echo 启动失败，请直接运行 dist\hd-preview-final\消除车牌\消除车牌.exe。
  pause
  exit /b 1
)
