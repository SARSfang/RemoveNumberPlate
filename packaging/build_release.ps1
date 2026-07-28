param(
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$InnoCompiler = Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python 3.11 virtual environment is missing: $Python"
}
if (-not (Test-Path -LiteralPath $InnoCompiler)) {
    throw "Inno Setup compiler is missing: $InnoCompiler"
}

Push-Location $ProjectRoot
try {
    & $Python -m scripts.verify_models
    if ($LASTEXITCODE -ne 0) { throw "Model verification failed." }

    if (-not $SkipTests) {
        & $Python -m pytest -q --basetemp .tmp_pytest_release_build `
            -o cache_dir=.tmp_pytest_cache_release_build
        if ($LASTEXITCODE -ne 0) { throw "Tests failed." }
        & $Python -m ruff check app tests scripts
        if ($LASTEXITCODE -ne 0) { throw "Ruff failed." }
    }

    & $Python -m scripts.collect_licenses
    if ($LASTEXITCODE -ne 0) { throw "License collection failed." }

    & $Python -m PyInstaller --noconfirm --clean packaging\plate_clear.spec
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

    & $InnoCompiler packaging\installer.iss
    if ($LASTEXITCODE -ne 0) { throw "Installer build failed." }

    $Installers = @(
        Get-ChildItem -LiteralPath "dist\installer" `
            -Filter "*-Setup-v0.2.0-rc.1-win64.exe" -File
    )
    if ($Installers.Count -ne 1) {
        throw "Expected exactly one release installer, found $($Installers.Count)."
    }
    $Installer = $Installers[0]
    & $Python -m scripts.release_acceptance
    if ($LASTEXITCODE -ne 0) { throw "Release acceptance failed." }
    $Hash = Get-FileHash -LiteralPath $Installer.FullName -Algorithm SHA256

    Write-Host ""
    Write-Host "Release candidate ready:"
    Write-Host $Installer.FullName
    Write-Host "SHA-256: $($Hash.Hash.ToLowerInvariant())"
}
finally {
    Pop-Location
}
