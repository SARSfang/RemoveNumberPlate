param(
    [Parameter(Mandatory = $true)]
    [string]$Installer,
    [Parameter(Mandatory = $true)]
    [string]$ExpectedProductVersion
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Workspace = (Resolve-Path -LiteralPath $ProjectRoot).Path
$Target = Join-Path $Workspace ".tmp_installer_acceptance_$PID"
$ResolvedInstaller = (Resolve-Path -LiteralPath $Installer).Path

if (-not $Target.StartsWith($Workspace, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Unsafe installer acceptance target."
}
if (Test-Path -LiteralPath $Target) {
    throw "Installer acceptance target already exists: $Target"
}

try {
    $Install = Start-Process -FilePath $ResolvedInstaller `
        -ArgumentList @(
            "/VERYSILENT",
            "/SUPPRESSMSGBOXES",
            "/NORESTART",
            "/SP-",
            ("/DIR=" + $Target)
        ) `
        -Wait -PassThru -WindowStyle Hidden
    if ($Install.ExitCode -ne 0) {
        throw "Installer failed: $($Install.ExitCode)"
    }

    $Executables = @(
        Get-ChildItem -LiteralPath $Target -Filter "*.exe" -File |
            Where-Object BaseName -NotLike "unins*"
    )
    if ($Executables.Count -ne 1) {
        throw "Expected one installed application executable."
    }
    $Executable = $Executables[0].FullName
    $LicenseManifest = Join-Path `
        $Target "_internal\third_party_licenses\manifest.json"
    $UserGuide = Join-Path $Target "_internal\docs\user-guide.md"
    if (
        -not (Test-Path -LiteralPath $Executable) -or
        -not (Test-Path -LiteralPath $LicenseManifest) -or
        -not (Test-Path -LiteralPath $UserGuide)
    ) {
        throw "Installed release files are incomplete."
    }

    $ProductVersion = (Get-Item -LiteralPath $Executable).VersionInfo.ProductVersion
    if ($ProductVersion -ne $ExpectedProductVersion) {
        throw "Expected product version $ExpectedProductVersion, found $ProductVersion."
    }

    $Smoke = Start-Process -FilePath $Executable -ArgumentList "--smoke" `
        -Wait -PassThru -WindowStyle Hidden
    if ($Smoke.ExitCode -ne 0) {
        throw "Installed desktop smoke failed: $($Smoke.ExitCode)"
    }

    $Uninstaller = Join-Path $Target "unins000.exe"
    $Uninstall = Start-Process -FilePath $Uninstaller `
        -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART") `
        -Wait -PassThru -WindowStyle Hidden
    if ($Uninstall.ExitCode -ne 0) {
        throw "Uninstaller failed: $($Uninstall.ExitCode)"
    }
    if (Test-Path -LiteralPath $Target) {
        throw "Install directory remains after uninstall."
    }

    Write-Host "Installer acceptance passed: $ProductVersion"
}
finally {
    if (Test-Path -LiteralPath $Target) {
        $Uninstaller = Join-Path $Target "unins000.exe"
        if (Test-Path -LiteralPath $Uninstaller) {
            Start-Process -FilePath $Uninstaller `
                -ArgumentList @("/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART") `
                -Wait -WindowStyle Hidden
        }
    }
}
