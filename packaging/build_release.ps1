param(
    [switch]$SkipTests,
    [string]$PfxPath,
    [string]$PfxPassword,
    [switch]$RequireSignature
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$InnoCommand = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
$InnoCandidates = @(
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 7\ISCC.exe")
    (Join-Path $env:ProgramFiles "Inno Setup 7\ISCC.exe")
    if ($InnoCommand) { $InnoCommand.Source }
)
$InnoCompiler = $InnoCandidates |
    Where-Object { $_ -and (Test-Path -LiteralPath $_) } |
    Select-Object -First 1

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python 3.11 virtual environment is missing: $Python"
}
if (-not (Test-Path -LiteralPath $InnoCompiler)) {
    throw "Inno Setup compiler is missing: $InnoCompiler"
}
if ($RequireSignature -and -not $PfxPath) {
    throw "A signing certificate is required for this build."
}
if ($PfxPath -and -not $PfxPassword) {
    throw "A PFX password is required when a signing certificate is supplied."
}

Push-Location $ProjectRoot
try {
    $ReleaseVersion = & $Python -c `
        "from app.version import __version__; print(__version__)"
    $ProductVersion = & $Python -c `
        "from app.version import __display_version__; print(__display_version__.removeprefix('v'))"
    if ($LASTEXITCODE -ne 0 -or -not $ReleaseVersion) {
        throw "Unable to read the release version."
    }
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

    $ApplicationExecutables = @(
        Get-ChildItem -LiteralPath "dist" -Directory |
            Where-Object Name -ne "installer" |
            ForEach-Object {
                Get-ChildItem -LiteralPath $_.FullName -Filter "*.exe" -File
            }
    )
    if ($ApplicationExecutables.Count -ne 1) {
        throw "Expected one application executable, found $($ApplicationExecutables.Count)."
    }
    if ($PfxPath) {
        & "$PSScriptRoot\sign_release.ps1" `
            -Artifact $ApplicationExecutables[0].FullName `
            -PfxPath $PfxPath `
            -PfxPassword $PfxPassword
    }

    & $InnoCompiler packaging\installer.iss
    if ($LASTEXITCODE -ne 0) { throw "Installer build failed." }

    $Installers = @(
        Get-ChildItem -LiteralPath "dist\installer" `
            -Filter "*-Setup-v$ReleaseVersion-win64.exe" -File
    )
    if ($Installers.Count -ne 1) {
        throw "Expected exactly one release installer, found $($Installers.Count)."
    }
    $Installer = $Installers[0]
    if ($PfxPath) {
        & "$PSScriptRoot\sign_release.ps1" `
            -Artifact $Installer.FullName `
            -PfxPath $PfxPath `
            -PfxPassword $PfxPassword
    }
    & $Python -m scripts.release_acceptance
    if ($LASTEXITCODE -ne 0) { throw "Release acceptance failed." }
    & "$PSScriptRoot\test_installer.ps1" `
        -Installer $Installer.FullName `
        -ExpectedProductVersion $ProductVersion
    if ($LASTEXITCODE -ne 0) { throw "Installer acceptance failed." }
    $Hash = Get-FileHash -LiteralPath $Installer.FullName -Algorithm SHA256

    Write-Host ""
    Write-Host "Release candidate ready:"
    Write-Host $Installer.FullName
    Write-Host "SHA-256: $($Hash.Hash.ToLowerInvariant())"
}
finally {
    Pop-Location
}
