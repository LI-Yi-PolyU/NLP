param(
    [int]$StartPort = 7860,
    [int]$EndPort = 7869,
    [string]$PythonExe = ".venv/Scripts/python.exe",
    [string]$AppFile = "app.py"
)

$ErrorActionPreference = "Stop"

function Get-ListeningPidsInRange {
    param([int]$From, [int]$To)

    $lines = netstat -ano | Select-String "LISTENING"
    $pids = @()

    foreach ($line in $lines) {
        $text = $line.ToString()
        if ($text -match "127\.0\.0\.1:(\d+)") {
            $port = [int]$Matches[1]
            if ($port -ge $From -and $port -le $To) {
                $parts = ($text -split "\s+") | Where-Object { $_ -ne "" }
                if ($parts.Length -gt 0) {
                    $pidText = $parts[$parts.Length - 1]
                    if ($pidText -match "^\d+$") {
                        $pids += [int]$pidText
                    }
                }
            }
        }
    }

    return $pids | Sort-Object -Unique
}

function Stop-PidSafe {
    param([int]$ProcessId)

    try {
        $proc = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
        if ($null -eq $proc) {
            return
        }

        # Use wmic termination to avoid policy differences around Stop-Process/taskkill.
        $result = wmic process where processid=$ProcessId call terminate 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Stopped PID $ProcessId"
        } else {
            Write-Host "Failed to stop PID $ProcessId (wmic exit code $LASTEXITCODE)"
        }
    } catch {
        Write-Host "Failed to stop PID ${ProcessId}: $($_.Exception.Message)"
    }
}

Write-Host "[1/3] Cleaning listeners from $StartPort to $EndPort..."
$pids = Get-ListeningPidsInRange -From $StartPort -To $EndPort
if ($pids.Count -eq 0) {
    Write-Host "No listeners found in range."
} else {
    foreach ($procId in $pids) {
        Stop-PidSafe -ProcessId $procId
    }
}

Write-Host "[2/3] Verifying cleanup..."
$remaining = Get-ListeningPidsInRange -From $StartPort -To $EndPort
if ($remaining.Count -gt 0) {
    Write-Host "Warning: still listening PIDs: $($remaining -join ', ')"
} else {
    Write-Host "All ports in range are clear."
}

if (-not (Test-Path $PythonExe)) {
    throw "Python executable not found: $PythonExe"
}
if (-not (Test-Path $AppFile)) {
    throw "App file not found: $AppFile"
}

Write-Host "[3/3] Starting app..."
Write-Host "Command: $PythonExe $AppFile"
& $PythonExe $AppFile
