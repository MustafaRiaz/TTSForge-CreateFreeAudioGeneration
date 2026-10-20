# Build VoiceForge Windows package + installer
#
# Usage (from repo root, venv activated):
#   powershell -ExecutionPolicy Bypass -File scripts\build_installer.ps1
#
# Produces:
#   dist\VoiceForge\VoiceForge.exe          (portable app folder)
#   dist\installer\VoiceForge Setup.exe     (when Inno Setup is available)
#   dist\VoiceForge-Portable.zip            (always)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
$PyInstaller = Join-Path $Root ".venv\Scripts\pyinstaller.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Error "Virtualenv not found. Run: python -m venv .venv && .\.venv\Scripts\pip install -r requirements.txt"
}

if (-not (Test-Path $PyInstaller)) {
    Write-Host "Installing PyInstaller..."
    & $VenvPython -m pip install pyinstaller
}

Write-Host "==> Cleaning previous build..."
Remove-Item -Recurse -Force (Join-Path $Root "build") -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force (Join-Path $Root "dist\VoiceForge") -ErrorAction SilentlyContinue

Write-Host "==> Running PyInstaller (this can take several minutes)..."
& $PyInstaller --noconfirm --clean (Join-Path $Root "packaging\voiceforge.spec")
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE" }

$AppDir = Join-Path $Root "dist\VoiceForge"
if (-not (Test-Path (Join-Path $AppDir "VoiceForge.exe"))) {
    throw "Build output missing: dist\VoiceForge\VoiceForge.exe"
}

# Ensure styles exist beside / inside bundle
$StyleCandidates = @(
    (Join-Path $AppDir "assets\styles\dark.qss"),
    (Join-Path $AppDir "_internal\assets\styles\dark.qss")
)
if (-not ($StyleCandidates | Where-Object { Test-Path $_ })) {
    Write-Host "Copying styles into bundle..."
    $Dest = Join-Path $AppDir "_internal\assets\styles"
    New-Item -ItemType Directory -Force -Path $Dest | Out-Null
    Copy-Item (Join-Path $Root "assets\styles\*") $Dest -Force
}

Write-Host "==> Bundling FFmpeg (if present)..."
$FfmpegSrc = Join-Path $Root "packaging\ffmpeg\ffmpeg.exe"
if (Test-Path $FfmpegSrc) {
    $FfmpegDest = Join-Path $AppDir "ffmpeg"
    New-Item -ItemType Directory -Force -Path $FfmpegDest | Out-Null
    Copy-Item $FfmpegSrc $FfmpegDest -Force
    Write-Host "FFmpeg bundled at $FfmpegDest\ffmpeg.exe"
} else {
    Write-Host "No bundled FFmpeg found (optional). See packaging\ffmpeg\README.md"
}

Write-Host "==> Creating portable ZIP..."
$ZipPath = Join-Path $Root "dist\VoiceForge-Portable.zip"
if (Test-Path $ZipPath) { Remove-Item $ZipPath -Force }
Compress-Archive -Path (Join-Path $AppDir "*") -DestinationPath $ZipPath -CompressionLevel Optimal
Write-Host "Portable package: $ZipPath"

function Find-ISCC {
    $candidates = @(
        "${env:LocalAppData}\Programs\Inno Setup 6\ISCC.exe",
        "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        "C:\Program Files\Inno Setup 6\ISCC.exe"
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) { return $c }
    }
    $cmd = Get-Command iscc -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

$Iscc = Find-ISCC
if (-not $Iscc) {
    Write-Host "==> Inno Setup not found. Attempting winget install..."
    try {
        winget install --id JRSoftware.InnoSetup -e --accept-package-agreements --accept-source-agreements
        $Iscc = Find-ISCC
    } catch {
        Write-Warning "winget install failed: $_"
    }
}

$InstallerOut = Join-Path $Root "dist\installer"
New-Item -ItemType Directory -Force -Path $InstallerOut | Out-Null

if ($Iscc) {
    Write-Host "==> Compiling installer with Inno Setup: $Iscc"
    & $Iscc (Join-Path $Root "packaging\voiceforge.iss")
    if ($LASTEXITCODE -ne 0) { throw "Inno Setup compilation failed" }
    $Setup = Join-Path $InstallerOut "VoiceForge Setup.exe"
    if (Test-Path $Setup) {
        Write-Host ""
        Write-Host "SUCCESS (Inno): $Setup"
        Get-Item $Setup | Format-List FullName, Length, LastWriteTime
    }
} else {
    Write-Host "==> Building self-contained VoiceForge Setup.exe bootstrapper..."
    & powershell -ExecutionPolicy Bypass -File (Join-Path $Root "scripts\build_setup_exe.ps1")
}

Write-Host "Done."
