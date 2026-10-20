# Build self-contained VoiceForge Setup.exe from the portable ZIP
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$Zip = Join-Path $Root "dist\VoiceForge-Portable.zip"
$PyInstaller = Join-Path $Root ".venv\Scripts\pyinstaller.exe"
if (-not (Test-Path $Zip)) { throw "Missing portable ZIP. Run scripts\build_installer.ps1 first." }
if (-not (Test-Path $PyInstaller)) { throw "Missing PyInstaller in .venv" }

Write-Host "==> Building VoiceForge Setup.exe (embeds portable ZIP)..."
$OutDir = Join-Path $Root "dist\installer"
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

& $PyInstaller --noconfirm --clean --distpath $OutDir --workpath (Join-Path $Root "build\setup") `
    (Join-Path $Root "packaging\setup_bootstrap.spec")
if ($LASTEXITCODE -ne 0) { throw "Setup build failed" }

$Setup = Join-Path $OutDir "VoiceForge Setup.exe"
if (-not (Test-Path $Setup)) { throw "Setup exe not created" }

Write-Host ""
Write-Host "SUCCESS:"
Get-Item $Setup | Format-List FullName, @{N='SizeMB';E={[math]::Round($_.Length/1MB,1)}}, LastWriteTime
