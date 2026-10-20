# Development Guide

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install -e ".[dev]"
```

Optional Piper engine (GPL):

```bash
pip install piper-tts
```

Optional Chatterbox Nano cloning (MIT, pulls PyTorch — CPU only in VoiceForge):

```bash
pip install chatterbox-tts
```

Then download **Chatterbox Nano** from Model Manager (~2 GB) and save a reference clone on the Voices page.

## Run GUI

```bash
python main.py
```

## Run CLI

```bash
python main.py --list-voices
python -m app.cli input.txt --voice kokoro:af_heart -o out.wav
```

## Tests

```bash
pytest -q
```

Heavy model inference is mocked in unit/integration tests. Real synthesis requires installed models.

## Layout

```text
app/
  core/         paths, logging, hardware
  tts/          provider abstraction + Kokoro/Piper/Chatterbox
  text/         normalization, chunking, importers
  audio/        processing, cache, export
  services/     generation, models, settings
  workers/      Qt background threads
  ui/           PySide6 pages/widgets
  cli/          shared CLI
  database/     SQLite
  projects/     project folders
tests/
assets/styles/  QSS themes
```

## Coding rules

- Keep TTS logic in providers/services — UI must not synthesize directly
- Never add paid/cloud TTS dependencies to the core path
- Disable UI controls the engine cannot support; explain why
- Do not auto-download large models without confirmation

## Data locations (Windows)

`%LOCALAPPDATA%\VoiceForge\` — database, models, cache, projects, logs
