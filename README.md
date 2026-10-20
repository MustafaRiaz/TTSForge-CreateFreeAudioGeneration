# VoiceForge

**Professional offline Text-to-Speech desktop application.**

VoiceForge turns documents and scripts into natural speech **entirely on your computer**. After you install voice models, core features work **without internet**, and **without any paid API, subscription, or API key**.

## Features

- Local neural TTS (Kokoro recommended — full ~54-voice multilingual set; Piper optional)
- Optional CPU voice cloning via Chatterbox Nano (MIT; reference WAV)
- Modern Studio UI with live stats, progress, pause/resume/cancel
- Long-document chunking for books and articles
- Multi-voice narration with `[SPEAKER]` tags
- Application-level markup (`<break>`, `<speed>`, `<emphasis>`) — not native SSML
- Projects, history, autosave, crash recovery
- Real waveform player
- Audio tools (normalize, fade, silence removal, convert, merge)
- Batch folder processing
- Model Manager with download confirmation (no surprise multi-GB downloads)
- Offline Mode
- CPU / optional CUDA acceleration with graceful fallback (Chatterbox forced to CPU)
- CLI sharing the same engine as the GUI

## Supported platforms

- **Primary:** Windows 10 / 11
- Architecture prepared for later macOS / Linux packaging

## Requirements

- Python 3.11–3.13 (for source installs)
- ~2+ GB free disk for models
- 8 GB RAM recommended (4–6 GB possible with Piper)
- Optional: NVIDIA GPU + CUDA-capable ONNX Runtime
- Optional: [FFmpeg](https://ffmpeg.org/) on PATH for MP3/OGG export

## Quick start (development)

```bash
cd "My TTS Model"
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

On first launch:

1. Choose Kokoro (recommended) or Piper (lightweight)
2. Open **Model Manager**
3. Confirm a download (size/language/quality shown)
4. Return to **Studio** and generate

Optional voice cloning (CPU):

```bash
pip install chatterbox-tts
```

Then download **Chatterbox Nano** in Model Manager, save a clone on the Voices page (or pick Reference… in Studio), and generate.

## CLI

```bash
python main.py --list-voices
python main.py --list-models
python main.py input.txt --voice kokoro:af_heart --output out.wav
python main.py input.txt --voice chatterbox:custom --reference-audio ref.wav -o clone.wav
```

## Offline operation

| Needs internet | Works offline |
|----------------|---------------|
| Model downloads | Text processing |
| Optional metadata refresh | TTS generation |
| Optional updates | Audio tools / playback / projects |

Enable **Offline Mode** in Settings to block network use.

## Licensing

- Application code: MIT (see project license intent in docs)
- Kokoro: engine MIT, weights Apache-2.0 (~54 voices in one package)
- Piper package (optional): GPL-3.0 — see `THIRD_PARTY_LICENSES.md`
- Chatterbox Nano (optional): MIT — CPU cloning; Resemble PerTh watermark on output

## Documentation

- `ARCHITECTURE.md` — system design
- `IMPLEMENTATION_PLAN.md` — build phases
- `DEVELOPMENT.md` — contributor setup
- `BUILD.md` — Windows packaging
- `TROUBLESHOOTING.md` — common issues
- `THIRD_PARTY_LICENSES.md` — dependencies & models

## Hardware notes

VoiceForge detects CPU/RAM/GPU at startup and recommends an engine. Low-RAM systems are steered toward Piper; otherwise Kokoro is preferred for quality.
