# VoiceForge Implementation Plan

## Status: Core application implemented

Greenfield build completed in this workspace. Phases below reflect delivered scope.

## Phase 1 — Foundation ✅
Architecture, stack choice, scaffold, paths, logging, requirements

## Phase 2 — TTS Abstraction ✅
`TTSProvider`, KokoroProvider, PiperProvider, registry, catalog

## Phase 3 — Studio UI ✅
Main window, sidebar, Studio editor, themes

## Phase 4 — Text Processing ✅
Normalization, chunking, markup, importers, pronunciation rules

## Phase 5 — Background Generation ✅
QThread workers, pause/resume/cancel, progress, crash state

## Phase 6 — Audio Player + Waveform ✅
QMediaPlayer controls + real peak waveform

## Phase 7 — Projects + SQLite ✅
App DB, project folders, autosave

## Phase 8 — Voice / Model Manager ✅
Search/favorites/preview/download/import/verify

## Phase 9 — Long-Form TTS ✅
Chunk pipeline with cache + merge

## Phase 10 — Multi-Speaker ✅
Speaker tags + dialogue voice assignment

## Phase 11 — Audio Tools ✅
Normalize, silence, fade, convert, merge, volume

## Phase 12 — Batch Processing ✅
Folder batch page

## Phase 13 — CLI ✅
`python main.py --list-voices` / synthesize

## Phase 14 — Settings + First Run ✅
Settings tabs, offline mode, hardware, welcome wizard

## Phase 15 — Tests ✅
Unit + mocked integration (`pytest` — 20 passed)

## Phase 16 — Packaging ✅
PyInstaller spec + BUILD.md

## Phase 17 — Docs ✅
README, ARCHITECTURE, DEVELOPMENT, BUILD, TROUBLESHOOTING, THIRD_PARTY_LICENSES

## Follow-ups (optional polish)
- Deeper resume-from-chunk UX automation
- Installer scripting (Inno Setup) beyond the documented outline
- Additional Piper catalog voices
- Job-queue visual panel wired to `JobQueue` for multi-studio jobs
