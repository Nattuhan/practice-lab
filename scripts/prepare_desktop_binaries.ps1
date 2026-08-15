$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$BinDir = Join-Path $RepoRoot "desktop\bin"
New-Item -ItemType Directory -Force -Path $BinDir | Out-Null

foreach ($Name in @("node.exe", "ffmpeg.exe", "ffprobe.exe")) {
    $Command = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $Command) { throw "$Name was not found. Install it before building the desktop app." }
    Copy-Item -Force -LiteralPath $Command.Source -Destination (Join-Path $BinDir $Name)
}

Write-Host "Prepared Node.js and FFmpeg for the desktop bundle." -ForegroundColor Green
