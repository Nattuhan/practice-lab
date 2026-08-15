param(
    [Parameter(Mandatory = $true)][string]$AppHome,
    [Parameter(Mandatory = $true)][string]$ResourceDir
)

$ErrorActionPreference = "Stop"
$Host.UI.RawUI.WindowTitle = "PracticeLab NVIDIA Setup"

function Step([string]$Message) {
    Write-Host ""
    Write-Host "[PracticeLab] $Message" -ForegroundColor Cyan
}

try {
    Step "Checking the NVIDIA GPU"
    if (-not (Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue)) {
        throw "The NVIDIA driver was not found. Install the latest NVIDIA driver and try again."
    }
    & nvidia-smi.exe --query-gpu=name --format=csv,noheader
    if ($LASTEXITCODE -ne 0) { throw "The NVIDIA GPU is unavailable." }

    if (-not (Get-Command wsl.exe -ErrorAction SilentlyContinue)) {
        Step "Installing WSL2. Approve the Windows administrator prompt"
        Start-Process powershell.exe -Verb RunAs -Wait -ArgumentList @(
            "-NoProfile", "-Command", "wsl.exe --install -d Ubuntu"
        )
        Write-Host "Restart Windows, then run NVIDIA Setup again from PracticeLab." -ForegroundColor Yellow
        Read-Host "Press Enter to close"
        exit 2
    }

    Step "Checking WSL2 and Ubuntu"
    & wsl.exe bash -lc "true"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Complete the Ubuntu first-run setup, then run NVIDIA Setup again." -ForegroundColor Yellow
        & wsl.exe -d Ubuntu
        exit 2
    }

    & wsl.exe bash -lc "nvidia-smi -L"
    if ($LASTEXITCODE -ne 0) {
        throw "The NVIDIA GPU is not visible inside WSL2. Update Windows and the NVIDIA driver, then restart."
    }

    Step "Preparing Python inside WSL2"
    & wsl.exe -u root -- bash -lc "apt-get update && DEBIAN_FRONTEND=noninteractive apt-get install -y python3 python3-venv python3-pip git"
    if ($LASTEXITCODE -ne 0) { throw "Failed to prepare Python inside WSL2." }

    $RuntimeWindows = Join-Path $AppHome "runtime\wsl"
    New-Item -ItemType Directory -Force -Path $RuntimeWindows | Out-Null
    $RuntimeWsl = (& wsl.exe wslpath -a ($RuntimeWindows -replace '\\','/')).Trim()
    $ResourceWsl = (& wsl.exe wslpath -a ($ResourceDir -replace '\\','/')).Trim()

    Step "Installing CUDA analysis libraries. This can take a while"
    & wsl.exe bash -lc "bash '$ResourceWsl/scripts/setup_wsl_runtime.sh' '$RuntimeWsl'"
    if ($LASTEXITCODE -ne 0) { throw "Failed to install the CUDA analysis runtime." }

    Step "Running the final GPU check"
    & wsl.exe bash -lc "'$RuntimeWsl/.venv/bin/python' -c 'import allin1fix, demucs_infer, torch; print(torch.cuda.get_device_name(0)); assert torch.cuda.is_available()'"
    if ($LASTEXITCODE -ne 0) { throw "The analysis runtime cannot use CUDA." }

    Write-Host ""
    Write-Host "NVIDIA setup is complete. Restart PracticeLab." -ForegroundColor Green
} catch {
    Write-Host ""
    Write-Host $_.Exception.Message -ForegroundColor Red
    Write-Host "Setup did not complete. Review the message above." -ForegroundColor Red
    $global:LASTEXITCODE = 1
}

Read-Host "Press Enter to close"
exit $global:LASTEXITCODE
