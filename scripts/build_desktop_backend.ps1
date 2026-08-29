$ErrorActionPreference = "Stop"
$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) { throw "Python environment is missing. Run setup.bat first." }

& $Python -m pip install -r (Join-Path $RepoRoot "requirements\desktop-build.txt")
if ($LASTEXITCODE -ne 0) { throw "Failed to install PyInstaller." }

& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --onedir `
    --name practice-lab-backend `
    --paths $RepoRoot `
    --collect-all yt_dlp `
    --hidden-import practice_lab.score_extractor `
    --exclude-module cv2 `
    --exclude-module rapidocr_onnxruntime `
    --exclude-module onnxruntime `
    --exclude-module pyclipper `
    --exclude-module shapely `
    --exclude-module torch `
    --exclude-module torchvision `
    --exclude-module torchaudio `
    --exclude-module allin1fix `
    --exclude-module demucs_infer `
    --distpath (Join-Path $RepoRoot "desktop\dist\backend") `
    --workpath (Join-Path $RepoRoot "desktop\build\backend") `
    --specpath (Join-Path $RepoRoot "desktop\build") `
    (Join-Path $RepoRoot "desktop\backend_entry.py")
if ($LASTEXITCODE -ne 0) { throw "Failed to build the desktop backend." }
