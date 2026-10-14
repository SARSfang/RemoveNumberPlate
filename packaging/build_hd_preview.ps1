param()
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$AppPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
Push-Location $ProjectRoot
try {
    & (Join-Path $PSScriptRoot "build_hd_component.ps1")
    & $AppPython -m PyInstaller --noconfirm --distpath dist\hd-preview-final `
        --workpath build\hd-preview-final packaging\plate_clear.spec
    if ($LASTEXITCODE -ne 0) { throw "Main HD preview build failed." }
    $Target = Join-Path $ProjectRoot "dist\hd-preview-final\消除车牌"
    Copy-Item -LiteralPath (Join-Path $ProjectRoot "dist\hd-component\hd-runtime") `
        -Destination $Target -Recurse -Force
    Copy-Item -LiteralPath (Join-Path $ProjectRoot "dist\hd-component\_internal\models\big-lama.pt") `
        -Destination (Join-Path $Target "_internal\models") -Force
    Copy-Item -LiteralPath (Join-Path $ProjectRoot "dist\hd-component\third_party_licenses_hd") `
        -Destination $Target -Recurse -Force
    Copy-Item -LiteralPath (Join-Path $ProjectRoot "docs\hd-validation-2026-10-14.md") `
        -Destination $Target -Force
    Write-Host "HD preview ready: $Target"
}
finally { Pop-Location }
