param(
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 8000,
    [switch]$NoBrowser,
    [switch]$CheckOnly
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot

function Write-Step($Message) {
    Write-Host "[practice-lab] $Message"
}

function Test-PortOpen($HostAddress, $Port) {
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $async = $client.BeginConnect($HostAddress, $Port, $null, $null)
        if (-not $async.AsyncWaitHandle.WaitOne(250)) {
            return $false
        }
        $client.EndConnect($async)
        return $true
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

function Test-PracticeLab($Url) {
    try {
        $response = Invoke-RestMethod -Uri "$Url/healthz" -TimeoutSec 1
        return $response.ok -eq $true
    } catch {
        return $false
    }
}

function Get-FreePort($HostAddress, $PreferredPort) {
    if (-not (Test-PortOpen $HostAddress $PreferredPort)) {
        return $PreferredPort
    }

    for ($candidate = $PreferredPort + 1; $candidate -le $PreferredPort + 20; $candidate++) {
        if (-not (Test-PortOpen $HostAddress $candidate)) {
            return $candidate
        }
    }

    throw "No free port found between $PreferredPort and $($PreferredPort + 20)."
}

$PythonExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    $PythonExe = "python"
}

Write-Step "cwd=$RepoRoot"
Write-Step "python=$PythonExe"

try {
    & $PythonExe -c "import uvicorn, fastapi, yt_dlp" 2>$null
} catch {
    Write-Host ""
    Write-Host "Required Python packages are not available."
    Write-Host "Run these once, then start again:"
    Write-Host "  py -3.10 -m venv .venv"
    Write-Host "  .\.venv\Scripts\Activate.ps1"
    Write-Host "  pip install -r requirements\app-py310.txt"
    exit 1
}

$ExistingUrl = "http://${HostAddress}:$Port"
if (Test-PortOpen $HostAddress $Port) {
    if (Test-PracticeLab $ExistingUrl) {
        Write-Step "already running at $ExistingUrl"
        if (-not $NoBrowser) {
            Start-Process $ExistingUrl
        }
        exit 0
    }

    $Port = Get-FreePort $HostAddress $Port
    Write-Step "port $($Port - 1) is busy; using $Port"
}

$Url = "http://${HostAddress}:$Port"
if (-not $env:ANALYZER_DEVICE) {
    $env:ANALYZER_DEVICE = "auto"
}
Write-Step "analyzer_device=$env:ANALYZER_DEVICE"
Write-Step "url=$Url"

if ($CheckOnly) {
    Write-Step "check complete"
    exit 0
}

$BrowserJob = $null
if (-not $NoBrowser) {
    $BrowserJob = Start-Job -ScriptBlock {
        param($TargetUrl)
        for ($i = 0; $i -lt 60; $i++) {
            try {
                $response = Invoke-RestMethod -Uri "$TargetUrl/healthz" -TimeoutSec 1
                if ($response.ok -eq $true) {
                    Start-Process $TargetUrl
                    return
                }
            } catch {
                Start-Sleep -Milliseconds 500
            }
        }
    } -ArgumentList $Url
}

Write-Step "starting uvicorn; press Ctrl+C to stop"
Write-Host ""

try {
    & $PythonExe -m uvicorn main:app --host $HostAddress --port $Port --log-level info --no-access-log
    $ExitCode = $LASTEXITCODE
} finally {
    if ($BrowserJob) {
        Receive-Job $BrowserJob -ErrorAction SilentlyContinue | Out-Null
        Remove-Job $BrowserJob -Force -ErrorAction SilentlyContinue
    }
}

Write-Host ""
Write-Host "Exit code: $ExitCode"
exit $ExitCode
