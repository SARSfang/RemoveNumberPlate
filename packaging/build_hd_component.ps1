param()
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$HdPython = Join-Path $ProjectRoot ".venv-hd\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $HdPython)) { throw "Independent .venv-hd is missing." }
$ModelPath = Join-Path $ProjectRoot "models\big-lama.pt"
$ExpectedHash = "344c77bbcb158f17dd143070d1e789f38a66c04202311ae3a258ef66667a9ea9"
if ((Get-FileHash -LiteralPath $ModelPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $ExpectedHash) {
    throw "Big-LaMa checksum failed."
}
Push-Location $ProjectRoot
try {
    & $HdPython -m PyInstaller --noconfirm --onedir --console `
        --name big-lama-worker --hidden-import torch `
        --distpath dist\hd-component\hd-runtime --workpath build\hd-worker `
        --specpath build\hd-worker app\infrastructure\big_lama_worker.py
    if ($LASTEXITCODE -ne 0) { throw "HD worker build failed." }
    & $HdPython -m scripts.collect_hd_licenses
    if ($LASTEXITCODE -ne 0) { throw "HD license collection failed." }
    $HdModels = Join-Path $ProjectRoot "dist\hd-component\_internal\models"
    New-Item -ItemType Directory -Path $HdModels -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $ProjectRoot "models\big-lama.pt") -Destination $HdModels
    Copy-Item -LiteralPath (Join-Path $ProjectRoot "docs\hd-repair.md") `
        -Destination (Join-Path $ProjectRoot "dist\hd-component\高清组件说明.md")
    Write-Host "Optional offline component: dist\hd-component"
}
finally { Pop-Location }
