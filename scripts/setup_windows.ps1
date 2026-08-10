param(
    [switch]$CpuOnly
)

$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot

function Write-Step([string]$Message) {
    Write-Host "[PracticeLab setup] $Message" -ForegroundColor Cyan
}

function Require-Command([string]$Name, [string]$InstallHint) {
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "$Name が見つかりません。$InstallHint"
    }
}

Write-Step "必要なコマンドを確認しています"
Require-Command "py.exe" "Python 3.10を python.org または winget でインストールしてください。"
Require-Command "ffmpeg.exe" "winget install Gyan.FFmpeg を実行してください。"
Require-Command "ffprobe.exe" "ffmpegの完全版をインストールしてください。"
Require-Command "node.exe" "winget install OpenJS.NodeJS.LTS を実行してください。"
Require-Command "npm.cmd" "Node.js LTSをインストールしてください。"

$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$HasNvidia = (-not $CpuOnly) -and (Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue)

function Test-ExistingEnvironment {
    if (-not (Test-Path $Python)) { return $false }
    $PreviousExecutor = $env:ANALYZER_EXECUTOR
    $PreviousDevice = $env:ANALYZER_DEVICE
    try {
        $env:ANALYZER_EXECUTOR = if ($HasNvidia) { "wsl" } else { "native" }
        $env:ANALYZER_DEVICE = if ($HasNvidia) { "cuda" } else { "cpu" }
        & $Python scripts\check_env.py *> $null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    } finally {
        $env:ANALYZER_EXECUTOR = $PreviousExecutor
        $env:ANALYZER_DEVICE = $PreviousDevice
    }
}

if (-not (Test-Path .env.local)) {
    Copy-Item .env.example .env.local
}

if (-not (Test-Path public\app.js)) {
    Write-Step "ブラウザ用ファイルがないため構築しています"
    & npm.cmd install
    if ($LASTEXITCODE -ne 0) { throw "フロントエンド依存の準備に失敗しました。" }
    & npm.cmd run build
    if ($LASTEXITCODE -ne 0) { throw "フロントエンドの構築に失敗しました。" }
}

Write-Step "既存環境がそのまま使えるか確認しています"
if (Test-ExistingEnvironment) {
    Write-Host "既存環境は正常です。依存パッケージを変更せずに利用します。" -ForegroundColor Green
    exit 0
}

if (-not (Test-Path $Python)) {
    Write-Step "Windows用Python環境を作成しています"
    & py.exe -3.10 -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw "Python環境の作成に失敗しました。" }
} else {
    Write-Step "既存環境に不足している依存を修復しています"
}

Write-Step "アプリの依存パッケージをインストールしています"
& $Python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pipの更新に失敗しました。" }
& $Python -m pip install -r requirements\app-py310.txt
if ($LASTEXITCODE -ne 0) { throw "アプリ依存のインストールに失敗しました。" }

if ($HasNvidia) {
    Require-Command "wsl.exe" "管理者PowerShellで wsl --install を実行し、再起動してください。"
    Write-Step "NVIDIA CUDA用のWSL解析環境を作成しています"
    $DriveLetter = $RepoRoot.Path.Substring(0, 1).ToLowerInvariant()
    $PathTail = $RepoRoot.Path.Substring(3).Replace('\', '/')
    $WslRepoRoot = "/mnt/$DriveLetter/$PathTail"
    & wsl.exe bash -lc "cd '$WslRepoRoot' && bash scripts/setup_wsl.sh"
    if ($LASTEXITCODE -ne 0) { throw "WSL解析環境のセットアップに失敗しました。" }
} else {
    Write-Step "CPU解析環境をインストールしています"
    & $Python -m pip install --index-url https://download.pytorch.org/whl/cpu torch==2.6.0
    if ($LASTEXITCODE -ne 0) { throw "PyTorch CPU版のインストールに失敗しました。" }
    & $Python -m pip install "natten==0.17.5+torch260cpu" -f https://whl.natten.org
    if ($LASTEXITCODE -ne 0) {
        Write-Step "CPU wheelがないためNATTENをビルドします"
        & $Python -m pip install natten==0.17.5 --no-build-isolation
        if ($LASTEXITCODE -ne 0) { throw "NATTENのインストールに失敗しました。" }
    }
    & $Python -m pip install all-in-one-fix==2.0.4 --no-build-isolation
    if ($LASTEXITCODE -ne 0) { throw "解析器のインストールに失敗しました。" }
}

Write-Step "環境を確認しています"
$PreviousExecutor = $env:ANALYZER_EXECUTOR
$PreviousDevice = $env:ANALYZER_DEVICE
try {
    $env:ANALYZER_EXECUTOR = if ($HasNvidia) { "wsl" } else { "native" }
    $env:ANALYZER_DEVICE = if ($HasNvidia) { "cuda" } else { "cpu" }
    & $Python scripts\check_env.py
    if ($LASTEXITCODE -ne 0) { throw "環境確認に失敗しました。" }
} finally {
    $env:ANALYZER_EXECUTOR = $PreviousExecutor
    $env:ANALYZER_DEVICE = $PreviousDevice
}

Write-Host ""
Write-Host "セットアップが完了しました。start.bat をダブルクリックして起動できます。" -ForegroundColor Green
