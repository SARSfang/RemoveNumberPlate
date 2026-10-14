param()
$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Worker = Join-Path $ProjectRoot "dist\hd-component\hd-runtime\big-lama-worker\big-lama-worker.exe"
$Model = Join-Path $ProjectRoot "models\big-lama.pt"
$Evidence = Join-Path $ProjectRoot "output\hd-validation"
$Measurements = @()
foreach ($Side in @(1024, 1536, 2048)) {
    $InputPath = Join-Path $Evidence "stress-$Side.npz"
    $OutputPath = Join-Path $Evidence "stress-$Side.npy"
    $Arguments = @('"' + $Model + '"', '"' + $InputPath + '"', '"' + $OutputPath + '"', "$Side")
    $Started = [DateTime]::UtcNow
    $WorkerProcess = Start-Process -FilePath $Worker -ArgumentList $Arguments `
        -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $Evidence "stress-$Side.log") `
        -RedirectStandardError (Join-Path $Evidence "stress-$Side.error.log")
    $ObservedPeak = 0L
    while (-not $WorkerProcess.HasExited) {
        $WorkerProcess.Refresh()
        try { $ObservedPeak = [Math]::Max($ObservedPeak, $WorkerProcess.PeakWorkingSet64) } catch {}
        if (([DateTime]::UtcNow - $Started).TotalSeconds -gt 90) {
            $WorkerProcess.Kill()
            throw "Worker measurement timed out at $Side."
        }
        Start-Sleep -Milliseconds 100
    }
    $WorkerProcess.WaitForExit()
    if ($WorkerProcess.ExitCode -ne 0) { throw "Worker failed at $Side; see stress error log." }
    $Measurements += [pscustomobject]@{
        side = $Side
        device = (Get-Content -LiteralPath (Join-Path $Evidence "stress-$Side.log") -Raw).Trim()
        elapsed_seconds = [Math]::Round(([DateTime]::UtcNow - $Started).TotalSeconds, 3)
        observed_peak_working_set_bytes = $ObservedPeak
        evidence_scope = "resized real-photo crop input stress only; worker process memory only"
    }
    $Measurements | ConvertTo-Json -Depth 4 | Set-Content `
        -LiteralPath (Join-Path $Evidence "worker-memory.json") -Encoding UTF8
    Write-Output $Measurements[-1]
}
