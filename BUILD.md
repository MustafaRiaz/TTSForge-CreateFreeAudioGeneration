# Building VoiceForge for Windows

## Quick build

From the repo root (venv activated):

```powershell
powershell -ExecutionPolicy Bypass -File scripts\build_installer.ps1
powershell -ExecutionPolicy Bypass -File scripts\build_setup_exe.ps1
```

### Outputs

| Artifact | Path |
|----------|------|
| App folder | `dist\VoiceForge\VoiceForge.exe` |
| Portable ZIP | `dist\VoiceForge-Portable.zip` |
| **Installer** | `dist\installer\VoiceForge Setup.exe` |

## What the installer does

`VoiceForge Setup.exe` is a self-contained bootstrapper that:

1. Extracts VoiceForge into `%LOCALAPPDATA%\Programs\VoiceForge`
2. Creates a Start Menu shortcut
3. Optionally creates a Desktop shortcut
4. Can launch the app when finished

Users do **not** need Python installed.

TTS models are **not** bundled (keeps the installer smaller). The first-run Model Manager downloads them with confirmation.

## Optional: Inno Setup classic installer

If [Inno Setup 6](https://jrsoftware.org/isinfo.php) is installed:

```powershell
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" packaging\voiceforge.iss
```

That produces another `dist\installer\VoiceForge Setup.exe` using the Inno wizard UI.

## Notes

- WAV works without FFmpeg; MP3/OGG need FFmpeg on PATH (or bundled later).
- Piper is optional/GPL — default builds ship Kokoro-capable stacks only.
- Rebuild after UI/code changes before redistributing.
