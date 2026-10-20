# Bundled FFmpeg (optional)

Place a Windows LGPL build of `ffmpeg.exe` in this folder before running the installer build script.

```
packaging/ffmpeg/ffmpeg.exe
```

The build script copies it into `dist/VoiceForge/ffmpeg/` so MP3/OGG export works without a system install.

Download: https://www.gyan.dev/ffmpeg/builds/ (choose `ffmpeg-release-essentials.zip`, extract `bin/ffmpeg.exe`).

You can also set a custom path in **Settings → Audio → FFmpeg path**.
