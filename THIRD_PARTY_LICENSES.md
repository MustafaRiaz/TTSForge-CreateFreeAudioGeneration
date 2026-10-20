# Third-Party Licenses

VoiceForge aims for offline, free-to-use TTS. **Open source does not always mean unrestricted commercial redistribution.** Review each license before shipping a commercial build.

## Application

| Component | License |
|-----------|---------|
| VoiceForge application code | MIT (intended) |

## Core libraries

| Library | License | Role |
|---------|---------|------|
| PySide6 / Qt | LGPL-3.0 | GUI |
| NumPy | BSD | Audio buffers |
| soundfile / libsndfile | BSD-like | Audio I/O |
| ONNX Runtime | MIT | Inference |
| BeautifulSoup4 | MIT | HTML import |
| python-docx | MIT | DOCX import |
| pypdf | BSD-3-Clause | PDF text import |
| psutil | BSD | Hardware stats |
| pytest | MIT | Tests |

## TTS engines & models

| Component | License | Notes |
|-----------|---------|-------|
| kokoro-onnx | MIT | Recommended engine wrapper |
| Kokoro model weights | Apache-2.0 | Permissive; full ~54-voice set in voices-v1.0.bin |
| piper-tts (current OHF packages) | GPL-3.0 | Optional; bundling may require GPL compliance for the distributed work |
| Piper voice models (rhasspy/piper-voices) | Often MIT per voice — verify each | Downloaded on demand |
| espeak-ng (used by Piper) | GPL-3.0 | Via Piper stack |
| chatterbox-tts / Chatterbox Nano | MIT | Optional CPU cloning; Resemble PerTh watermark applied to synthesized audio |

**Recommendation:** Default product builds use **Kokoro only**. Treat Piper and Chatterbox as optional plugins the user installs themselves (Piper for GPL reasons; Chatterbox because it pulls PyTorch).

## FFmpeg

FFmpeg may be LGPL or GPL depending on build configuration. Bundle an LGPL build or require a system install and document it.

## Network endpoints used for optional downloads

- Kokoro models: GitHub releases (`thewh1teagle/kokoro-onnx`)
- Piper voices: Hugging Face (`rhasspy/piper-voices`)
- Chatterbox Nano: Hugging Face (`ResembleAI/chatterbox-nano`)

No telemetry or analytics SDKs are included.

## No hidden paid dependencies

This repository must not require:

- ElevenLabs / Google / Azure / OpenAI / Polly / Play.ht / Murf APIs
- API keys for core TTS
- Mandatory cloud processing
