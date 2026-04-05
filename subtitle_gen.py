"""Subtitle Generator — Create SRT subtitle files from scenes."""

from __future__ import annotations

from pathlib import Path
from scene_splitter import Scene


def format_srt_time(seconds: float) -> str:
    """Convert seconds to SRT time format: HH:MM:SS,mmm"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def generate_srt(scenes: list[Scene], output_path: str | Path) -> Path:
    """Generate an SRT subtitle file from scenes.

    Args:
        scenes: List of Scene objects with timing info
        output_path: Path to save the .srt file

    Returns:
        Path to the saved SRT file
    """
    output_path = Path(output_path)

    lines = []
    for i, scene in enumerate(scenes):
        lines.append(str(i + 1))
        lines.append(f"{format_srt_time(scene.start_time)} --> {format_srt_time(scene.end_time)}")
        lines.append(scene.text)
        lines.append("")  # blank line separator

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return output_path


def generate_word_level_srt(text: str, audio_path: str, output_path: str | Path) -> Path:
    """Generate word-level SRT using audio analysis (basic estimation).

    For precise word-level timing, use Whisper:
        whisper audio.wav --model base --output_format srt
    """
    from pydub import AudioSegment

    audio = AudioSegment.from_file(audio_path)
    total_duration = len(audio) / 1000.0

    words = text.split()
    total_chars = sum(len(w) for w in words)

    output_path = Path(output_path)
    lines = []
    current_time = 0.0

    # Group words into subtitle chunks (5-8 words each)
    chunk_size = 6
    for i in range(0, len(words), chunk_size):
        chunk_words = words[i:i + chunk_size]
        chunk_text = " ".join(chunk_words)
        chunk_chars = sum(len(w) for w in chunk_words)
        chunk_duration = (chunk_chars / total_chars) * total_duration

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
