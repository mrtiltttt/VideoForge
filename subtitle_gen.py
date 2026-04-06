"""Subtitle Generator — Whisper-based word-level SRT with precise timestamps."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class WordTiming:
    """A single word with precise start/end timestamps."""
    word: str
    start: float   # seconds
    end: float     # seconds


@dataclass
class SubtitleSegment:
    """A group of words forming one subtitle display."""
    text: str
    start: float
    end: float


def format_srt_time(seconds: float) -> str:
    """Convert seconds to SRT time format: HH:MM:SS,mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


# ── Whisper transcription cache ────────────────────────────────────────
_whisper_cache: dict[str, list[WordTiming]] = {}
_whisper_model = None


def _get_whisper_model():
    """Lazy-load Whisper model (cached singleton)."""
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        logger.info("Loading Whisper model (base)...")
        # Use 'base' for speed on CPU; 'small' for better accuracy
        _whisper_model = WhisperModel(
            "base",
            device="cpu",
            compute_type="int8",
        )
        logger.info("Whisper model loaded.")
    return _whisper_model


def transcribe_with_timestamps(audio_path: str | Path) -> list[WordTiming]:
    """Transcribe audio and return word-level timestamps using Whisper.

    Results are cached per audio file path.

    Args:
        audio_path: Path to audio file (WAV/MP3/M4A/etc.)

    Returns:
        List of WordTiming objects with precise start/end times for each word
    """
    audio_key = str(Path(audio_path).resolve())

    if audio_key in _whisper_cache:
        logger.info("Using cached Whisper transcription for %s", Path(audio_path).name)
        return _whisper_cache[audio_key]

    model = _get_whisper_model()

    logger.info("Transcribing %s with Whisper (word-level)...", Path(audio_path).name)

    segments, info = model.transcribe(
        str(audio_path),
        word_timestamps=True,
        vad_filter=True,
    )

    words: list[WordTiming] = []
    for segment in segments:
        if segment.words:
            for w in segment.words:
                clean_word = w.word.strip()
                if clean_word:
                    words.append(WordTiming(
                        word=clean_word,
                        start=w.start,
                        end=w.end,
                    ))

    logger.info("Whisper transcribed %d words (%.1fs audio, lang=%s, prob=%.2f)",
                len(words), info.duration, info.language, info.language_probability)

    _whisper_cache[audio_key] = words
    return words


def group_words_into_subtitles(
    words: list[WordTiming],
    words_per_group: int = 4,
    max_chars: int = 45,
) -> list[SubtitleSegment]:
    """Group words into subtitle segments for display.

    Creates short, frequent subtitle groups (3-5 words) that change
    in sync with the spoken audio — TikTok/Reels style.

    Args:
        words: List of WordTiming from Whisper
        words_per_group: Target number of words per subtitle (default 4)
        max_chars: Maximum characters per subtitle line

    Returns:
        List of SubtitleSegment objects
    """
    if not words:
        return []

    segments: list[SubtitleSegment] = []
    i = 0

    while i < len(words):
        # Take up to words_per_group words
        group: list[WordTiming] = []
        chars = 0

        while i < len(words) and len(group) < words_per_group:
            w = words[i]
            new_chars = chars + len(w.word) + (1 if group else 0)

            # Don't exceed max chars (but always take at least 1 word)
            if group and new_chars > max_chars:
                break

            group.append(w)
            chars = new_chars
            i += 1

            # Break on sentence-ending punctuation for natural pauses
            if w.word and w.word[-1] in '.!?':
                break

        if group:
            text = " ".join(w.word for w in group)
            segments.append(SubtitleSegment(
                text=text,
                start=group[0].start,
                end=group[-1].end,
            ))

    # Fill gaps: ensure no overlap and minimal gaps
    for j in range(len(segments) - 1):
        # If there's a gap between this segment and the next, extend this one
        gap = segments[j + 1].start - segments[j].end
        if 0 < gap < 0.3:
            segments[j].end = segments[j + 1].start

    return segments


def get_subtitle_segments_for_scene(
    all_segments: list[SubtitleSegment],
    scene_start: float,
    scene_end: float,
) -> list[SubtitleSegment]:
    """Get subtitle segments that fall within a scene's time range.

    Args:
        all_segments: All subtitle segments from Whisper
        scene_start: Scene start time (seconds)
        scene_end: Scene end time (seconds)

    Returns:
        List of SubtitleSegments clipped to scene boundaries
    """
    result = []
    for seg in all_segments:
        # Segment overlaps with scene
        if seg.end > scene_start and seg.start < scene_end:
            clipped = SubtitleSegment(
                text=seg.text,
                start=max(seg.start, scene_start),
                end=min(seg.end, scene_end),
            )
            # Only include if duration is meaningful
            if clipped.end - clipped.start >= 0.1:
                result.append(clipped)
    return result


def generate_word_level_srt(
    text: str,
    audio_path: str,
    output_path: str | Path,
    words_per_group: int = 4,
) -> Path:
    """Generate word-level SRT using Whisper for precise timestamps.

    Args:
        text: Original script text (used as fallback reference)
        audio_path: Path to audio file
        output_path: Path to save the .srt file
        words_per_group: Words per subtitle group (default 4)

    Returns:
        Path to the saved SRT file
    """
    output_path = Path(output_path)

    # Get precise word timestamps from Whisper
    words = transcribe_with_timestamps(audio_path)

    if not words:
        logger.warning("Whisper returned no words, falling back to basic estimation")
        return _generate_basic_srt(text, audio_path, output_path)

    # Group into subtitle segments
    segments = group_words_into_subtitles(words, words_per_group=words_per_group)

    # Write SRT
    lines = []
    for i, seg in enumerate(segments):
        lines.append(str(i + 1))
        lines.append(f"{format_srt_time(seg.start)} --> {format_srt_time(seg.end)}")
        lines.append(seg.text)
        lines.append("")  # blank line separator

    output_path.write_text("\n".join(lines), encoding="utf-8")
    logger.info("SRT saved: %s (%d subtitle groups)", output_path, len(segments))
    return output_path


def generate_srt(scenes, output_path: str | Path) -> Path:
    """Generate a scene-level SRT subtitle file (legacy, for basic use)."""
    output_path = Path(output_path)

    lines = []
    for i, scene in enumerate(scenes):
        lines.append(str(i + 1))
        lines.append(f"{format_srt_time(scene.start_time)} --> {format_srt_time(scene.end_time)}")
        lines.append(scene.text)
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def _generate_basic_srt(text: str, audio_path: str, output_path: Path) -> Path:
    """Fallback: basic character-proportion SRT (used if Whisper fails)."""
    from pydub import AudioSegment

    audio = AudioSegment.from_file(audio_path)
    total_duration = len(audio) / 1000.0

    words = text.split()
    total_chars = sum(len(w) for w in words)

    lines = []
    current_time = 0.0
    chunk_size = 4

    for i in range(0, len(words), chunk_size):
        chunk_words = words[i:i + chunk_size]
        chunk_text = " ".join(chunk_words)
        chunk_chars = sum(len(w) for w in chunk_words)
        chunk_duration = (chunk_chars / max(total_chars, 1)) * total_duration

        sub_index = i // chunk_size + 1
        start = current_time
        end = current_time + chunk_duration

        lines.append(str(sub_index))
        lines.append(f"{format_srt_time(start)} --> {format_srt_time(end)}")
        lines.append(chunk_text)
        lines.append("")

        current_time = end

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path
