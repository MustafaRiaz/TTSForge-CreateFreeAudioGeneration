"""CLI entrypoint sharing the same core TTS services as the GUI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.core.logging_setup import setup_logging
from app.core.paths import ensure_dirs
from app.services.app_context import AppContext
from app.services.generation_service import GenerationRequest
from app.tts.base import ComputeDevice, VoiceSettings


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="voiceforge", description="VoiceForge offline TTS")
    p.add_argument("input", nargs="?", help="Input text file")
    p.add_argument("--voice", help="Voice id (e.g. kokoro:af_heart or piper:en_US-lessac-medium)")
    p.add_argument("--output", "-o", help="Output audio path")
    p.add_argument("--speed", type=float, default=1.0)
    p.add_argument("--format", default="wav", choices=["wav", "mp3", "flac", "ogg"])
    p.add_argument("--list-voices", action="store_true")
    p.add_argument("--list-models", action="store_true")
    p.add_argument("--device", default="auto", choices=["auto", "cpu", "gpu"])
    p.add_argument(
        "--reference-audio",
        help="Reference WAV/audio path for Chatterbox cloning voices",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    paths = ensure_dirs()
    setup_logging(paths["logs"])
    ctx = AppContext()

    if args.list_voices:
        for v in ctx.registry.all_voices():
            flag = "installed" if v.installed else "missing"
            print(f"{v.id}\t{v.name}\t{v.language}\t{flag}")
        return 0

    if args.list_models:
        for m in ctx.models.list_catalog():
            flag = "installed" if m.installed else "missing"
            print(f"{m.id}\t{m.provider}\t{m.language}\t{m.size_mb}MB\t{flag}")
        return 0

    if not args.input:
        build_parser().print_help()
        return 2

    inp = Path(args.input)
    if not inp.is_file():
        print(f"Input not found: {inp}", file=sys.stderr)
        return 1

    voice = args.voice or ctx.settings.get("default_voice")
    if not voice:
        # pick first installed
        installed = [v for v in ctx.registry.all_voices() if v.installed]
        if not installed:
            print("No installed voices. Use the GUI Model Manager or install models first.", file=sys.stderr)
            return 1
        voice = installed[0].id

    text = inp.read_text(encoding="utf-8", errors="replace")
    out = Path(args.output) if args.output else inp.with_suffix(f".{args.format}")
    extra: dict = {}
    if args.reference_audio:
        ref = Path(args.reference_audio)
        if not ref.is_file():
            print(f"Reference audio not found: {ref}", file=sys.stderr)
            return 1
        extra["reference_audio"] = str(ref.resolve())
    req = GenerationRequest(
        text=text,
        voice_id=voice,
        output_path=out,
        title=inp.stem,
        settings=VoiceSettings(speed=args.speed, extra=extra),
        audio_format=args.format,
        device=ComputeDevice(args.device),
    )

    def progress(p: dict) -> None:
        if p.get("message"):
            print(p["message"])

    result = ctx.generation.generate(req, on_progress=progress)
    if result.cancelled:
        print("Cancelled")
        return 1
    print(f"Wrote {result.output_path} ({result.duration_sec:.1f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
