@echo off
setlocal
cd /d "%~dp0"

if not exist ".\models" (
  echo Models folder is missing. Place model directories under "%~dp0models".
  pause
  exit /b 1
)

if not exist ".\workspace" (
  mkdir ".\workspace"
)

set "TRANSLATOR_OPEN_BROWSER=true"
start "" ".\translator.exe"
