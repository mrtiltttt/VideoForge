#!/usr/bin/env python3
"""VideoForge — Automated YouTube video creation from script + voiceover.

Usage:
    python videoforge.py --audio voice.wav --script script.txt
    python videoforge.py --audio voice.wav --script script.txt --style cinematic
    python videoforge.py --audio voice.wav --text "Hello world" --ai
"""

from __future__ import annotations

import argparse
import logging
import sys
import os
from pathlib import Path
from datetime import datetime

# Load .env if present
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())

from config import OUTPUT_DIR
from scene_splitter import split_script, get_audio_duration
from visual_finder import fetch_visuals_for_scenes
from video_assembler import assemble_video
from subtitle_gen import generate_srt, generate_word_level_srt

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(
        description="VideoForge — Create YouTube videos from script + voiceover",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic: script file + audio
  python videoforge.py --audio output.wav --script script.txt

  # With AI-generated images
  python videoforge.py --audio output.wav --script script.txt --ai

  # Inline text instead of file
  python videoforge.py --audio output.wav --text "Your text here"

  # With background music
  python videoforge.py --audio output.wav --script script.txt --music assets/music/lofi.mp3

  # Custom output path
  python videoforge.py --audio output.wav --script script.txt -o my_video.mp4
        """,
    )

    parser.add_argument("--audio", "-a", required=True, help="Path to voiceover audio file (WAV/MP3)")
    parser.add_argument("--script", "-s", help="Path to script text file")
    parser.add_argument("--text", "-t", help="Inline script text (alternative to --script)")
    parser.add_argument("--output", "-o", help="Output video file path")
    parser.add_argument("--ai", action="store_true", help="Use AI (DALL-E) for image generation")
    parser.add_argument("--no-subtitles", action="store_true", help="Disable subtitle overlays")
    parser.add_argument("--music", "-m", help="Path to background music file")
    parser.add_argument("--music-volume", type=float, default=0.15, help="Background music volume (0.0-1.0)")
    parser.add_argument("--srt", action="store_true", help="Also generate SRT subtitle file")
    parser.add_argument("--no-pexels", action="store_true", help="Skip Pexels search (use placeholders only)")
    parser.add_argument("--prefer-photos", action="store_true", help="Prefer photos over video clips from Pexels")
    parser.add_argument("--min-scene", type=float, default=3.0, help="Minimum scene duration (seconds)")
    parser.add_argument("--max-scene", type=float, default=8.0, help="Maximum scene duration (seconds)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Validate inputs
    audio_path = Path(args.audio)
    if not audio_path.exists():
        logger.error("Audio file not found: %s", audio_path)
        sys.exit(1)

    # Get script text
    if args.script:
        script_path = Path(args.script)
        if not script_path.exists():
            logger.error("Script file not found: %s", script_path)
            sys.exit(1)
        text = script_path.read_text(encoding="utf-8")
    elif args.text:
        text = args.text
    else:
        logger.error("Provide either --script or --text")
        sys.exit(1)

    # Output path
    if args.output:
        output_path = Path(args.output)
    else:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = OUTPUT_DIR / f"video_{timestamp}.mp4"

    # Create work directory for this run
    work_dir = OUTPUT_DIR / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    work_dir.mkdir(parents=True, exist_ok=True)

    # ── Pipeline ────────────────────────────────────────────────────────

    duration = get_audio_duration(audio_path)
    logger.info("=" * 60)
    logger.info("🎬 VideoForge — Starting pipeline")
    logger.info("  Audio: %s (%.1f seconds)", audio_path.name, duration)
    logger.info("  Text: %d characters", len(text))
    logger.info("  Output: %s", output_path)
    logger.info("=" * 60)

    # Step 1: Split into scenes
    logger.info("\n📝 Step 1: Splitting script into scenes...")
    scenes = split_script(text, audio_path, args.min_scene, args.max_scene)
    logger.info("  → %d scenes created", len(scenes))
    for s in scenes:
        logger.info("  [%d] %.1f-%.1fs | Query: '%s' | Overlay: '%s'",
                    s.index, s.start_time, s.end_time, s.search_query, s.overlay_text[:40])

    # Step 2: Fetch visuals
    logger.info("\n🎨 Step 2: Fetching visuals...")
    if args.no_pexels:
        logger.info("  Pexels disabled, using placeholders")
        from visual_finder import _create_placeholder
        for scene in scenes:
            dest = work_dir / f"scene_{scene.index:03d}_placeholder.png"
            _create_placeholder(dest, scene.overlay_text)
            scene.visual_path = str(dest)
    else:
        scenes = fetch_visuals_for_scenes(
            scenes,
            work_dir=work_dir / "visuals",
            use_ai=args.ai,
            prefer_video=not args.prefer_photos,
        )

    # Step 3: Assemble video
    logger.info("\n🎬 Step 3: Assembling video...")
    result = assemble_video(
        scenes=scenes,
        audio_path=audio_path,
        output_path=output_path,
        add_subtitles=not args.no_subtitles,
        add_music=args.music,
        music_volume=args.music_volume,
    )

    # Step 4: Generate SRT if requested
    if args.srt:
        srt_path = output_path.with_suffix(".srt")
        logger.info("\n📄 Step 4: Generating subtitles...")
        generate_word_level_srt(text, str(audio_path), srt_path)
        logger.info("  → Subtitles: %s", srt_path)

    # Done
    logger.info("\n" + "=" * 60)
    logger.info("✅ Done! Video saved to: %s", result)
    logger.info("  Duration: %.1f seconds", duration)
    logger.info("  Scenes: %d", len(scenes))
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
