param(
    [string]$PythonExe = "python",
    [string]$NodeExe = "npm"
)

$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$frontendDir = Join-Path $projectRoot "frontend"
$releaseRoot = Join-Path $projectRoot "release"
$releaseDir = Join-Path $releaseRoot "windows-app"
$distRoot = Join-Path $projectRoot "dist"
$pyInstallerSpec = Join-Path $projectRoot "packaging\pyinstaller\translator.spec"
$pyInstallerOutputDir = Join-Path $distRoot "translator"
$modelsDir = Join-Path $projectRoot "models"
$workspaceDir = Join-Path $releaseDir "workspace"

Write-Host "Building frontend..."
Push-Location $frontendDir
try {
    & $NodeExe ci
    & $NodeExe run build
}
finally {
    Pop-Location
}

Write-Host "Installing packaging requirements..."
& $PythonExe -m pip install -r (Join-Path $projectRoot "backend\requirements-packaging.txt")

Write-Host "Running PyInstaller..."
& $PythonExe -m PyInstaller --noconfirm --clean $pyInstallerSpec

Write-Host "Preparing release layout..."
if (Test-Path $releaseDir) {
    Remove-Item -Recurse -Force $releaseDir
}
New-Item -ItemType Directory -Force -Path $releaseDir | Out-Null

Copy-Item -Recurse -Force (Join-Path $pyInstallerOutputDir "*") $releaseDir
Copy-Item -Force (Join-Path $projectRoot "packaging\windows\start.bat") (Join-Path $releaseDir "start.bat")
Copy-Item -Force (Join-Path $projectRoot "packaging\windows\README.txt") (Join-Path $releaseDir "README.txt")

if (Test-Path $modelsDir) {
    Copy-Item -Recurse -Force $modelsDir (Join-Path $releaseDir "models")
}
else {
    New-Item -ItemType Directory -Force -Path (Join-Path $releaseDir "models") | Out-Null
}

New-Item -ItemType Directory -Force -Path $workspaceDir | Out-Null

Write-Host "Release is ready at $releaseDir"
