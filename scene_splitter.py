"""Scene Splitter — Break script into timed scenes synced with audio."""

from __future__ import annotations

import re
import logging
from dataclasses import dataclass, field
from pathlib import Path

from pydub import AudioSegment

logger = logging.getLogger(__name__)


@dataclass
class Scene:
    """A single scene with text, timing, and visual metadata."""
    index: int
    text: str
    start_time: float    # seconds
    end_time: float      # seconds
    duration: float      # seconds
    search_query: str = ""     # for Pexels/AI image search
    visual_path: str = ""      # path to downloaded/generated visual
    overlay_text: str = ""     # key phrase for text overlay
    is_video: bool = False     # True if visual is a video clip

    def __repr__(self):
        return f"Scene({self.index}, {self.duration:.1f}s, '{self.text[:40]}...')"


def get_audio_duration(audio_path: str | Path) -> float:
    """Get audio duration in seconds."""
    audio = AudioSegment.from_file(str(audio_path))
    return len(audio) / 1000.0


def split_into_sentences(text: str) -> list[str]:
    """Split text into sentences, preserving bullet points."""
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text.strip())

    # Split on sentence endings
    parts = re.split(r'(?<=[.!?])\s+', text)

    # Merge very short fragments
    sentences = []
    buffer = ""
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if len(buffer) + len(part) < 40 and buffer:
            buffer += " " + part
        else:
            if buffer:
                sentences.append(buffer)
            buffer = part
    if buffer:
        sentences.append(buffer)

    return sentences


def extract_key_phrase(text: str) -> str:
    """Extract the most important phrase for overlay text."""
    # Remove bullet markers
    clean = re.sub(r'^[\*\-•]\s*', '', text.strip())

    # Use full text for short scenes
    if len(clean) <= 100:
        return clean

    # Take first sentence or phrase
    match = re.match(r'^(.{20,80})[.!?,]', clean)
    if match:
        return match.group(1).strip()

    # Fallback: first sentence boundary
    first_sent = re.split(r'[.!?]', clean)[0].strip()
    if first_sent:
        return first_sent

    return clean[:80].rsplit(' ', 1)[0]


def generate_search_query(text: str) -> str:
    """Generate a Pexels/image search query from scene text."""
    # Remove common filler words
    stop_words = {
        'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been',
        'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
        'could', 'should', 'may', 'might', 'shall', 'can', 'that',
        'this', 'these', 'those', 'it', 'its', 'you', 'your', 'her',
        'his', 'their', 'our', 'my', 'me', 'him', 'them', 'us', 'we',
        'she', 'he', 'they', 'i', 'and', 'or', 'but', 'not', 'no',
        'so', 'if', 'when', 'what', 'how', 'why', 'who', 'which',
        'just', 'don', 't', 's', 're', 've', 'll', 'to', 'of', 'in',
        'on', 'at', 'for', 'with', 'about', 'into', 'from', 'up',
        'out', 'like', 'all', 'only', 'than', 'then', 'too', 'very',
        'really', 'seriously', 'remember', 'nope', 'hey',
    }

    # Clean text
    clean = re.sub(r'[^\w\s]', '', text.lower())
    words = [w for w in clean.split() if w not in stop_words and len(w) > 2]

    # Take top 3-4 meaningful words
    keywords = words[:4]
    if not keywords:
        keywords = ["people", "lifestyle"]

    return " ".join(keywords)


def split_script(
    text: str,
    audio_path: str | Path,
    min_duration: float = 3.0,
    max_duration: float = 8.0,
) -> list[Scene]:
    """Split script into timed scenes synced with audio duration.

    Args:
        text: Full script text
        audio_path: Path to the voiceover audio file
        min_duration: Minimum scene duration in seconds
        max_duration: Maximum scene duration in seconds

    Returns:
        List of Scene objects with timing information
    """
    total_duration = get_audio_duration(audio_path)
    sentences = split_into_sentences(text)

    if not sentences:
        return []

    # Calculate total character count for proportional timing
    total_chars = sum(len(s) for s in sentences)
    if total_chars == 0:
        return []

    # Group sentences into scenes based on timing
    scenes: list[Scene] = []
    current_time = 0.0
    current_group: list[str] = []
    current_chars = 0

    for sent in sentences:
        sent_duration = (len(sent) / total_chars) * total_duration

        if current_group and (current_chars / total_chars) * total_duration >= min_duration:
            # Current group is long enough, check if adding this sentence
            # would make it too long
            potential_duration = ((current_chars + len(sent)) / total_chars) * total_duration
            if potential_duration > max_duration:
                # Finalize current group
                group_duration = (current_chars / total_chars) * total_duration
                group_text = " ".join(current_group)
                scenes.append(Scene(
                    index=len(scenes),
                    text=group_text,
                    start_time=current_time,
                    end_time=current_time + group_duration,
                    duration=group_duration,
                    search_query=generate_search_query(group_text),
                    overlay_text=extract_key_phrase(group_text),
                ))
                current_time += group_duration
                current_group = []
                current_chars = 0

        current_group.append(sent)
        current_chars += len(sent)

    # Final group
    if current_group:
        group_duration = total_duration - current_time
        group_text = " ".join(current_group)
        scenes.append(Scene(
            index=len(scenes),
            text=group_text,
            start_time=current_time,
            end_time=total_duration,
            duration=group_duration,
            search_query=generate_search_query(group_text),
            overlay_text=extract_key_phrase(group_text),
        ))

    logger.info("Split into %d scenes for %.1fs audio", len(scenes), total_duration)
    for s in scenes:
        logger.debug("  Scene %d: %.1f-%.1fs [%s] → '%s'",
                     s.index, s.start_time, s.end_time, s.search_query, s.overlay_text)

    return scenes
