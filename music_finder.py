"""Music Finder — Auto-search and download royalty-free background music.

Sources:
  - Freesound.org API (Creative Commons 0 — no attribution needed)
  - Local music library fallback
"""

from __future__ import annotations

import logging
import os
import random
from pathlib import Path

import requests

from config import ASSETS_DIR, OUTPUT_DIR

logger = logging.getLogger(__name__)

FREESOUND_API_KEY = os.getenv("FREESOUND_API_KEY", "")
FREESOUND_SEARCH_URL = "https://freesound.org/apiv2/search/text/"
FREESOUND_SOUND_URL = "https://freesound.org/apiv2/sounds/{sound_id}/"

# Music directory for cached/downloaded tracks
MUSIC_CACHE = ASSETS_DIR / "music"
MUSIC_CACHE.mkdir(parents=True, exist_ok=True)

# ── Mood keywords mapping ──────────────────────────────────────────────
MOOD_KEYWORDS = {
    "motivational": ["motivational", "inspiring", "uplifting", "energetic"],
    "dark":         ["dark", "cinematic dark", "tension", "dramatic"],
    "calm":         ["calm", "peaceful", "ambient", "relaxing"],
    "confident":    ["confident", "powerful", "bold", "strong beat"],
    "romantic":     ["romantic", "love", "emotional", "tender"],
    "happy":        ["happy", "cheerful", "fun", "upbeat"],
    "sad":          ["sad", "melancholy", "emotional piano", "nostalgic"],
    "cinematic":    ["cinematic", "epic", "film score", "orchestral"],
    "lofi":         ["lofi", "chill", "lo-fi beats", "study music"],
    "ambient":      ["ambient", "atmospheric", "background", "minimal"],
}

# Simple text → mood mapping
MOOD_TRIGGERS = {
    "motivational": ["power", "strong", "win", "success", "achieve", "best", "great", "awesome"],
    "dark":         ["dark", "danger", "warning", "fear", "death", "shadow", "night"],
    "confident":    ["confidence", "dominant", "alpha", "game", "control", "power", "dominance"],
    "romantic":     ["love", "heart", "romance", "kiss", "passion", "desire", "beautiful"],
    "happy":        ["happy", "joy", "fun", "laugh", "smile", "party", "celebrate"],
    "sad":          ["sad", "cry", "pain", "loss", "miss", "alone", "broken"],
    "calm":         ["calm", "peace", "relax", "gentle", "quiet", "meditation", "zen"],
    "cinematic":    ["epic", "story", "journey", "adventure", "hero", "battle", "destiny"],
}


def detect_mood(text: str) -> str:
    """Detect the mood of text content for music selection."""
    text_lower = text.lower()
    scores: dict[str, int] = {}

    for mood, triggers in MOOD_TRIGGERS.items():
        score = sum(1 for word in triggers if word in text_lower)
        if score > 0:
            scores[mood] = score

    if scores:
        best_mood = max(scores, key=scores.get)
        logger.info("Detected mood: %s (score: %d)", best_mood, scores[best_mood])
        return best_mood

    # Default mood for talking-head / advice content
    logger.info("No strong mood detected, defaulting to 'cinematic'")
    return "cinematic"


def _search_freesound(query: str, min_duration: float = 30.0,
                       max_duration: float = 300.0,
                       license_filter: str = "Creative Commons 0") -> list[dict]:
    """Search Freesound.org for music tracks."""
    if not FREESOUND_API_KEY:
        logger.warning("No FREESOUND_API_KEY set")
        return []

    try:
        params = {
            "query": query,
            "token": FREESOUND_API_KEY,
            "filter": f'license:"{license_filter}" duration:[{min_duration} TO {max_duration}]',
            "fields": "id,name,duration,previews,license,tags,avg_rating",
            "sort": "rating_desc",
            "page_size": 10,
        }

        resp = requests.get(FREESOUND_SEARCH_URL, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        results = data.get("results", [])
        logger.info("Freesound: found %d results for '%s'", len(results), query)
        return results

    except Exception as e:
        logger.error("Freesound search failed: %s", e)
        return []


def _download_freesound_preview(sound: dict, dest: Path) -> bool:
    """Download the HQ preview MP3 from Freesound."""
    previews = sound.get("previews", {})
    url = previews.get("preview-hq-mp3") or previews.get("preview-lq-mp3")

    if not url:
        logger.warning("No preview URL for sound %s", sound.get("id"))
        return False

    try:
        resp = requests.get(url, timeout=30, stream=True)
        resp.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(8192):
                f.write(chunk)
        logger.info("Downloaded music: %s (%.1fs)", dest.name, sound.get("duration", 0))
        return True
    except Exception as e:
        logger.error("Download failed: %s", e)
        return False


def find_music_for_text(
    text: str,
    duration_hint: float = 60.0,
    mood_override: str | None = None,
    cache_dir: Path | None = None,
) -> tuple[str | None, str]:
    """Find suitable background music for the given text.

    Args:
        text: The script text to analyze for mood
        duration_hint: Approximate video duration (for finding right-length tracks)
        mood_override: Override auto-detected mood
        cache_dir: Directory to cache downloaded music

    Returns:
        Tuple of (path_to_music_file_or_None, mood_description)
    """
    if cache_dir is None:
        cache_dir = MUSIC_CACHE

    # Step 1: Detect mood
    mood = mood_override or detect_mood(text)
    keywords = MOOD_KEYWORDS.get(mood, ["ambient", "background", "instrumental"])

    # Step 2: Check local cache first
    cached = list(cache_dir.glob("*.mp3")) + list(cache_dir.glob("*.wav"))
    for f in cached:
        # If filename contains mood keyword, use it
        fname = f.stem.lower()
        if any(kw in fname for kw in [mood, mood[:4]]):
            logger.info("Using cached music: %s", f.name)
            return str(f), mood

    # Step 3: Search Freesound
    if FREESOUND_API_KEY:
        # Try multiple search queries
        search_query = random.choice(keywords) + " instrumental music"

        min_dur = max(30.0, duration_hint * 0.5)
        max_dur = max(180.0, duration_hint * 2.0)

        results = _search_freesound(search_query, min_dur, max_dur)

        if not results:
            # Broader search
            results = _search_freesound("ambient background music", 30.0, 300.0)

        if results:
            # Pick a random top result
            sound = random.choice(results[:5])
            dest = cache_dir / f"{mood}_{sound['id']}.mp3"

            if dest.exists():
                logger.info("Using cached: %s", dest.name)
                return str(dest), mood

            if _download_freesound_preview(sound, dest):
                return str(dest), mood

    # Step 4: Fallback — check for any local music
    if cached:
        pick = random.choice(cached)
        logger.info("Fallback to local music: %s", pick.name)
        return str(pick), mood

    logger.warning("No music found for mood '%s'", mood)
    return None, mood


def list_available_moods() -> list[str]:
    """Return list of available mood categories."""
    return list(MOOD_KEYWORDS.keys())


def get_mood_keywords(mood: str) -> list[str]:
    """Get search keywords for a mood."""
    return MOOD_KEYWORDS.get(mood, ["ambient", "background"])
