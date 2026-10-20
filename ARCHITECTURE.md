# VoiceForge Architecture

## Product Overview

**VoiceForge** is a professional offline Text-to-Speech desktop application. All speech generation runs locally on the user's machine. No paid APIs, API keys, cloud TTS services, or subscriptions are required for core functionality.

## Technology Stack

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Language | Python 3.11–3.13 | Best ecosystem for local ML/TTS; strong Windows support |
| GUI | PySide6 (Qt 6) | Mature, accessible, themable, commercial-friendly LGPL |
| Primary TTS | Kokoro via `kokoro-onnx` | High quality, ~82M params, CPU-friendly, MIT + Apache-2.0 (~54 voices) |
| Secondary TTS | Piper via `piper-tts` / ONNX | Lightweight, many languages, fast on CPU |
| Optional cloning | Chatterbox Nano via `chatterbox-tts` | MIT, CPU-only zero-shot cloning from ~10s reference WAV |
| Inference | ONNX Runtime (+ optional PyTorch for Chatterbox) | Cross-platform CPU/CUDA without heavy PyTorch for core path |
| Audio I/O | soundfile, numpy, FFmpeg | Reliable WAV/FLAC + export to MP3/OGG |
| Database | SQLite | Zero-config local storage for settings, history, projects |
| Packaging | PyInstaller | Single-folder / installer build for Windows |

### Why not Electron / C++ / Coqui?

- **Electron**: Heavier runtime; weaker native audio/ML integration.
- **C++**: Better performance ceiling, far slower to ship a full product UI.
- **Coqui / XTTS**: Strong quality but heavier (PyTorch), larger models, more fragile Windows installs, and non-commercial weight licenses — not a core dependency. Voice cloning is covered by optional **Chatterbox Nano** (MIT, CPU).

## Offline / Online Boundary

| Requires Internet | Offline (always) |
|-------------------|------------------|
| Model downloads (user-confirmed) | Text preprocessing |
| Optional model metadata refresh | TTS generation |
| Optional app update checks | Audio processing / playback |
| | Project / history / settings |

**Offline Mode** disables all network calls.

## TTS Provider Abstraction

```text
TTSProvider (ABC)
 ├── KokoroProvider      # Recommended — quality + permissive licenses (~54 voices)
 ├── PiperProvider       # Lightweight — many languages (optional GPL package)
 └── ChatterboxProvider  # Optional — CPU voice cloning (MIT)
```

Contract (`app/tts/base.py`):

- `is_available()` / `get_voices()` / `load_voice()` / `unload()`
- `synthesize(text, settings) -> AudioResult`
- `supported_settings` — UI disables unsupported controls honestly
- `capabilities` — speed, pitch, multi-speaker, etc.

Providers load models **once** and reuse them across chunks.

## Application Layers

```text
┌─────────────────────────────────────────────┐
│  UI (PySide6) — Studio, Voices, Settings…   │
├─────────────────────────────────────────────┤
│  Services — generation, queue, projects…    │
├─────────────────────────────────────────────┤
│  Workers (QThread) — TTS, download, audio   │
├─────────────────────────────────────────────┤
│  Domain — text, audio, cache, models        │
├─────────────────────────────────────────────┤
│  Providers — Kokoro / Piper / Chatterbox Nano          │
├─────────────────────────────────────────────┤
│  Persistence — SQLite + project folders     │
└─────────────────────────────────────────────┘
```

CLI (`voiceforge` / `python -m app.cli`) calls the **same** services and providers as the GUI.

## Long-Form Pipeline

```text
Document → preprocess → segment → chunk → synthesize
        → normalize → merge → export
```

- Chunks are bounded (configurable) so huge books never load into the engine at once.
- Progress, pause, resume, cancel, and per-chunk retry are first-class.
- Deterministic cache keys: `hash(text + voice + model + settings)`.

## Multi-Voice Narration

Scripts use speaker tags (`[NARRATOR]`, `[JOHN]`). The dialogue editor maps speakers → voices. Sections are synthesized in order with configurable inter-speaker pauses, then merged.

## Project Layout (on disk)

```text
data/projects/<ProjectName>/
  project.db
  source/
  audio/
  chunks/
  exports/
```

App-wide SQLite lives under `data/voiceforge.db` (settings, history, voice favorites, queue).

## Hardware Strategy

At startup VoiceForge detects CPU, RAM, GPU (NVIDIA CUDA via ONNX Runtime when present), disk space. Recommendations:

- Low RAM / no GPU → Piper medium/low
- Adequate RAM → Kokoro (recommended)
- CUDA available → enable GPU EP when the selected engine supports it

Failures fall back to CPU without crashing.

## Security Notes

- No arbitrary code execution from imported documents or models
- Path validation / traversal prevention for projects and model imports
- Model downloads only from configured legitimate repositories with user confirmation
- Optional SHA verification where checksums are published

## Licensing Summary

| Component | License | Notes |
|-----------|---------|-------|
| VoiceForge application code | MIT | Product code |
| PySide6 | LGPL-3.0 | Dynamic linking; compliant packaging |
| kokoro-onnx | MIT | Engine wrapper |
| Kokoro model weights | Apache-2.0 | Permissive (~54 voices) |
| piper-tts (current) | GPL-3.0 | Optional; see THIRD_PARTY_LICENSES.md |
| Piper voice models | Per-voice (often MIT) | Check each voice |
| chatterbox-tts / Chatterbox Nano | MIT | Optional CPU cloning; PerTh watermark on output |
| ONNX Runtime | MIT | Inference |
| FFmpeg | LGPL/GPL | Bundle LGPL build or require system FFmpeg |

**Commercial distribution note:** Bundling GPL Piper into a closed-source binary may force GPL obligations. VoiceForge treats Piper as an **optional** provider and documents this clearly. Kokoro is the recommended default for permissive redistribution. Chatterbox Nano is also optional (MIT) but pulls PyTorch.

## Extensibility

Adding an engine:

1. Implement `TTSProvider` in `app/tts/`
2. Register in `app/tts/registry.py`
3. Add catalog entries in Model Manager metadata
4. No UI rewrite required beyond capability flags
