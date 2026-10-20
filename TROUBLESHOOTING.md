# Troubleshooting

## App won't start

- Confirm Python 3.11–3.13: `python --version`
- Reinstall deps: `pip install -r requirements.txt`
- Check `%LOCALAPPDATA%\VoiceForge\logs\errors.log` and `logs\app.log`

## No voices listed

Install a model in **Model Manager** (confirm download size first).  
Kokoro needs both `kokoro-v1.0.onnx` and `voices-v1.0.bin`.

## Generation fails

Typical causes:

- Model not installed / incomplete download
- Out of memory (try Piper, shorter chunks, close other apps)
- Corrupted ONNX file (Verify in Model Manager, re-download)
- Piper selected but `piper-tts` not installed

## CUDA / GPU issues

VoiceForge falls back to CPU if CUDA providers are missing.  
Set **Settings → TTS → Compute device → CPU** to force CPU.

## MP3/OGG export fails

Install FFmpeg and ensure `ffmpeg` is on PATH. WAV/FLAC can work without it (FLAC via soundfile).

## Offline Mode blocks downloads

Expected. Disable Offline Mode only for model downloads/updates.

## UI freezes

Generation runs on a worker thread. If the UI freezes, check `errors.log` and file an issue with the stack trace. Avoid synthesizing enormous unchunked strings outside Studio (Studio always chunks).

## Unfinished project prompt

Crash recovery detected incomplete generation. Choose Resume to restore text, then Generate again.
