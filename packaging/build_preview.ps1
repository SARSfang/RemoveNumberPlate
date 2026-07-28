param(
    [switch]$SkipTests
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
if (-not $Python) {
    throw "A working Python 3.11 or 3.12 preview environment is missing."
}

$RunningApplication = Get-Process -Name "消除车牌" -ErrorAction SilentlyContinue
if ($RunningApplication) {
    throw "Close the running application before rebuilding the preview."
}

Push-Location $ProjectRoot
try {
    & $Python -m scripts.verify_models
    if ($LASTEXITCODE -ne 0) { throw "Model verification failed." }

    if (-not $SkipTests) {
        & $Python -m pytest -q --basetemp .tmp_pytest_preview_build `
            -o cache_dir=.tmp_pytest_cache_preview_build
        if ($LASTEXITCODE -ne 0) { throw "Tests failed." }
        & $Python -m ruff check app tests scripts
        if ($LASTEXITCODE -ne 0) { throw "Ruff failed." }
        & $Python -m mypy app
        if ($LASTEXITCODE -ne 0) { throw "Mypy failed." }
        & node --test tests\frontend\*.test.cjs
        if ($LASTEXITCODE -ne 0) { throw "Frontend tests failed." }
    }

    & $Python -m scripts.collect_licenses
    if ($LASTEXITCODE -ne 0) { throw "License collection failed." }

    & $Python -m PyInstaller --noconfirm --clean `
        --distpath dist\preview `
        --workpath build\preview `
        packaging\plate_clear.spec
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller preview build failed." }

    $PreviewExecutables = @(
        Get-ChildItem -LiteralPath "dist\preview" -Filter "*.exe" -File -Recurse
    )
    if ($PreviewExecutables.Count -ne 1) {
        throw "Expected one preview executable, found $($PreviewExecutables.Count)."
    }
    $Executable = $PreviewExecutables[0].FullName
    $Smoke = Start-Process -FilePath $Executable -ArgumentList "--smoke" `
        -WindowStyle Hidden -Wait -PassThru
    if ($Smoke.ExitCode -ne 0) {
        throw "Preview desktop smoke failed: $($Smoke.ExitCode)"
    }

    $Version = & $Python -c "from app.version import __version__; print(__version__)"
    $Commit = (& git rev-parse HEAD).Trim()
    $BuildTime = [DateTime]::UtcNow.ToString("o")
    @(
        "version=$Version"
        "commit=$Commit"
        "built_at_utc=$BuildTime"
        "desktop_smoke=passed"
        "tests=$(if ($SkipTests) { 'skipped' } else { 'passed' })"
    ) | Set-Content -LiteralPath "dist\preview\BUILD.txt" -Encoding UTF8

    Write-Host ""
    Write-Host "Stable preview ready:"
    Write-Host $Executable
    Write-Host "Launch it with 启动测试版.cmd; installation is not required."
}
finally {
    Pop-Location
}
