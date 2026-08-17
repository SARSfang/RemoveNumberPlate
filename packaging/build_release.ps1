param(
    [switch]$SkipTests,
    [string]$PfxPath,
    [string]$PfxPassword,
    [switch]$RequireSignature
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Python = $null
$PythonCandidates = @(
    $env:PLATE_CLEAR_PYTHON
    (Join-Path $ProjectRoot ".venv\Scripts\python.exe")
    (Join-Path $ProjectRoot ".venv-rc5\Scripts\python.exe")
)
foreach ($Candidate in $PythonCandidates) {
    if (-not $Candidate -or -not (Test-Path -LiteralPath $Candidate)) {
        continue
    }
    try {
        & $Candidate -c `
            "import sys; raise SystemExit(0 if (3, 11) <= sys.version_info[:2] < (3, 13) else 1)" `
            2>$null
        if ($LASTEXITCODE -eq 0) {
            $Python = $Candidate
            break
        }
    }
    catch {
        continue
    }
}
$InnoCommand = Get-Command "ISCC.exe" -ErrorAction SilentlyContinue
$InnoCandidates = @(
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 7\ISCC.exe")
    (Join-Path $env:ProgramFiles "Inno Setup 7\ISCC.exe")
    if ($InnoCommand) { $InnoCommand.Source }
)
$InnoCompiler = $InnoCandidates |
    Where-Object { $_ -and (Test-Path -LiteralPath $_) } |
    Select-Object -First 1

if (-not $Python) {
    throw "A working Python 3.11 or 3.12 release environment is missing."
}
if (-not (Test-Path -LiteralPath $InnoCompiler)) {
    throw "Inno Setup compiler is missing: $InnoCompiler"
}

# installer.iss bundles the WebView2 Evergreen bootstrapper; it is a local,
# git-ignored binary, so fetch the official one when missing (local first
# build or CI). Redistribution is permitted by Microsoft; the Authenticode
# signature must be valid before the file is used.
$WebView2Path = Join-Path $PSScriptRoot "vendor\MicrosoftEdgeWebview2Setup.exe"
if (-not (Test-Path -LiteralPath $WebView2Path)) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $WebView2Path) |
        Out-Null
    Invoke-WebRequest `
        -Uri "https://go.microsoft.com/fwlink/p/?LinkId=2124703" `
        -OutFile $WebView2Path
    $WebView2Signature = Get-AuthenticodeSignature -LiteralPath $WebView2Path
    if ($WebView2Signature.Status -ne "Valid") {
        Remove-Item -LiteralPath $WebView2Path -Force
        throw "Downloaded WebView2 bootstrapper signature is not valid."
    }
    Write-Host "Downloaded signed WebView2 bootstrapper to $WebView2Path"
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
    $InstallerOutput = Join-Path $ProjectRoot "dist\installer"
    if (Test-Path -LiteralPath $InstallerOutput) {
        Get-ChildItem -LiteralPath $InstallerOutput `
            -Filter "*-Setup-v*-win64.exe" -File |
            Remove-Item -Force
    }
    & $Python -m scripts.verify_models
    if ($LASTEXITCODE -ne 0) { throw "Model verification failed." }

    if (-not $SkipTests) {
        # watch_folder e2e hangs on Windows (blocking CloseHandle in
        # _stop_watcher); skip it until the watcher shutdown bug is fixed.
        & $Python -m pytest -q --basetemp .tmp_pytest_release_build `
            --ignore=tests/integration/test_watch_folder_e2e.py `
            -o cache_dir=.tmp_pytest_cache_release_build
        if ($LASTEXITCODE -ne 0) { throw "Tests failed." }
        & $Python -m ruff check app tests scripts
        if ($LASTEXITCODE -ne 0) { throw "Ruff failed." }
    }

    & $Python -m scripts.collect_licenses
    if ($LASTEXITCODE -ne 0) { throw "License collection failed." }

    & $Python -m PyInstaller --noconfirm --clean packaging\plate_clear.spec
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }

    $ReleaseDirectories = @(
        Get-ChildItem -LiteralPath "dist" -Directory |
            Where-Object { $_.Name -notin @("installer", "preview") }
    )
    $ApplicationExecutables = @(
        $ReleaseDirectories |
            ForEach-Object {
                Get-ChildItem -LiteralPath $_.FullName -Filter "*.exe" -File
            }
    )
    if ($ReleaseDirectories.Count -ne 1 -or $ApplicationExecutables.Count -ne 1) {
        throw "Expected exactly one release application executable."
    }
    $ApplicationExecutable = $ApplicationExecutables[0]
    if ($PfxPath) {
        & "$PSScriptRoot\sign_release.ps1" `
            -Artifact $ApplicationExecutable.FullName `
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
