param(
    [Parameter(Mandatory = $true)]
    [string]$Artifact,
    [Parameter(Mandatory = $true)]
    [string]$PfxPath,
    [Parameter(Mandatory = $true)]
    [string]$PfxPassword,
    [string]$TimestampUrl = "http://timestamp.digicert.com"
)

$ErrorActionPreference = "Stop"
$ResolvedArtifact = (Resolve-Path -LiteralPath $Artifact).Path
$ResolvedPfx = (Resolve-Path -LiteralPath $PfxPath).Path

$SignToolCommand = Get-Command "signtool.exe" -ErrorAction SilentlyContinue
$SignTool = if ($SignToolCommand) { $SignToolCommand.Source } else { $null }
if (-not $SignTool) {
    $WindowsKits = Join-Path ${env:ProgramFiles(x86)} "Windows Kits\10\bin"
    if (Test-Path -LiteralPath $WindowsKits) {
        $SignTool = Get-ChildItem -LiteralPath $WindowsKits -Recurse `
            -Filter "signtool.exe" -File -ErrorAction SilentlyContinue |
            Where-Object FullName -Match "\\x64\\signtool\.exe$" |
            Sort-Object FullName -Descending |
            Select-Object -First 1 -ExpandProperty FullName
    }
}
if (-not $SignTool) {
    throw "signtool.exe was not found. Install the Windows SDK signing tools."
}

& $SignTool sign /fd SHA256 /td SHA256 /tr $TimestampUrl `
    /f $ResolvedPfx /p $PfxPassword $ResolvedArtifact
if ($LASTEXITCODE -ne 0) {
    throw "Signing failed for $ResolvedArtifact"
}

$Signature = Get-AuthenticodeSignature -LiteralPath $ResolvedArtifact
if ($Signature.Status -ne "Valid") {
    throw "Signature verification failed: $($Signature.StatusMessage)"
}
Write-Host "Signed and verified: $ResolvedArtifact"

