"""Visual Finder — Fetch images/videos from Pexels or generate via AI."""

from __future__ import annotations

import logging
import random
import time
from pathlib import Path

import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import (
    PEXELS_API_KEY, OPENAI_API_KEY,
    PEXELS_RESULTS_PER_SCENE, PREFER_VIDEO_OVER_IMAGE,
    OUTPUT_DIR,
)
from scene_splitter import Scene

logger = logging.getLogger(__name__)

PEXELS_PHOTO_URL = "https://api.pexels.com/v1/search"
PEXELS_VIDEO_URL = "https://api.pexels.com/videos/search"


def _download_file(url: str, dest: Path, headers: dict = None) -> bool:
    """Download a file from URL to destination."""
    try:
        resp = requests.get(url, headers=headers or {}, stream=True, timeout=30)
        resp.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in resp.iter_content(chunk_size=8192):
                f.write(chunk)
        logger.info("Downloaded: %s", dest.name)
        return True
    except Exception as e:
        logger.error("Download failed for %s: %s", url, e)
        return False


def search_pexels_photos(query: str, per_page: int = 5, orientation: str = "landscape") -> list[dict]:
    """Search Pexels for photos."""
    if not PEXELS_API_KEY:
        logger.warning("No PEXELS_API_KEY set — skipping photo search")
        return []

    try:
        resp = requests.get(
            PEXELS_PHOTO_URL,
            headers={"Authorization": PEXELS_API_KEY},
            params={"query": query, "per_page": per_page, "orientation": orientation},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("photos", [])
    except Exception as e:
        logger.error("Pexels photo search failed: %s", e)
        return []


def search_pexels_videos(query: str, per_page: int = 5, orientation: str = "landscape") -> list[dict]:
    """Search Pexels for video clips."""
    if not PEXELS_API_KEY:
        logger.warning("No PEXELS_API_KEY set — skipping video search")
        return []

    try:
        resp = requests.get(
            PEXELS_VIDEO_URL,
            headers={"Authorization": PEXELS_API_KEY},
            params={"query": query, "per_page": per_page, "orientation": orientation},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("videos", [])
    except Exception as e:
        logger.error("Pexels video search failed: %s", e)
        return []


def generate_ai_image(prompt: str, dest: Path) -> bool:
    """Generate an image using OpenAI DALL-E."""
    if not OPENAI_API_KEY:
        logger.warning("No OPENAI_API_KEY set — skipping AI generation")
        return False

    try:
        from openai import OpenAI
        client = OpenAI(api_key=OPENAI_API_KEY)

        response = client.images.generate(
            model="dall-e-3",
            prompt=f"Cinematic YouTube thumbnail style, dark moody lighting: {prompt}",
            size="1792x1024",
            quality="standard",
            n=1,
        )

        image_url = response.data[0].url
        return _download_file(image_url, dest)
    except Exception as e:
        logger.error("AI image generation failed: %s", e)
        return False


def _get_best_video_file(video_data: dict, max_width: int = 1920) -> str | None:
    """Get the best quality video file URL from Pexels video data."""
    files = video_data.get("video_files", [])
    suitable = [f for f in files if f.get("width", 0) <= max_width and f.get("file_type") == "video/mp4"]
    if not suitable:
        suitable = [f for f in files if f.get("file_type") == "video/mp4"]
    if not suitable:
        return None
    suitable.sort(key=lambda x: x.get("width", 0), reverse=True)
    return suitable[0].get("link")


def fetch_visuals_for_scenes(
    scenes: list[Scene],
    work_dir: Path | None = None,
    use_ai: bool = False,
    prefer_video: bool = True,
    orientation: str = "landscape",
) -> list[Scene]:
    """Fetch visuals for all scenes.

    Strategy:
    1. Try Pexels video clips first (if prefer_video) — portrait first for TikTok
    2. Fallback to Pexels photos
    3. Fallback to AI generation (if use_ai)
    4. Fallback to solid color placeholder

    Args:
        scenes: List of Scene objects with search_query filled
        work_dir: Directory to save downloaded visuals
        use_ai: Whether to use AI image generation as fallback
        prefer_video: Prefer video clips over photos
        orientation: 'landscape' for YouTube, 'portrait' for TikTok

    Returns:
        Updated list of Scene objects with visual_path filled
    """
    if work_dir is None:
        work_dir = OUTPUT_DIR / "visuals"
    work_dir.mkdir(parents=True, exist_ok=True)

    used_ids = set()  # avoid duplicate visuals

    def _fetch_one_scene(scene):
        query = scene.search_query
        logger.info("Scene %d: searching for '%s'...", scene.index, query)
        found = False

        # 1. Try Pexels videos (portrait first for TikTok, then fallback to landscape)
        if prefer_video and PEXELS_API_KEY:
            videos = search_pexels_videos(query, PEXELS_RESULTS_PER_SCENE, orientation)
            # If portrait and no results, fallback to landscape
            if not videos and orientation == "portrait":
                videos = search_pexels_videos(query, PEXELS_RESULTS_PER_SCENE, "landscape")
            random.shuffle(videos)
            for v in videos:
                vid = v.get("id")
                if vid in used_ids:
                    continue
                url = _get_best_video_file(v)
                if url:
                    dest = work_dir / f"scene_{scene.index:03d}.mp4"
                    if _download_file(url, dest):
                        scene.visual_path = str(dest)
                        scene.is_video = True
                        used_ids.add(vid)
                        found = True
                        break
            if found:
                return scene

        # 2. Try Pexels photos
        if PEXELS_API_KEY:
            photos = search_pexels_photos(query, PEXELS_RESULTS_PER_SCENE, orientation)
            if not photos and orientation == "portrait":
                photos = search_pexels_photos(query, PEXELS_RESULTS_PER_SCENE, "landscape")
            random.shuffle(photos)
            for p in photos:
                pid = p.get("id")
                if pid in used_ids:
                    continue
                src = p.get("src", {})
                url = src.get("landscape") or src.get("large") or src.get("original")
                if url:
                    dest = work_dir / f"scene_{scene.index:03d}.jpg"
                    if _download_file(url, dest):
                        scene.visual_path = str(dest)
                        scene.is_video = False
                        used_ids.add(pid)
                        found = True
                        break
            if found:
                return scene

        # 3. Try AI generation
        if use_ai and not found:
            dest = work_dir / f"scene_{scene.index:03d}_ai.png"
            if generate_ai_image(scene.text, dest):
                scene.visual_path = str(dest)
                scene.is_video = False
                found = True

        # 4. Placeholder
        if not found:
            logger.warning("Scene %d: no visual found, creating placeholder", scene.index)
            dest = work_dir / f"scene_{scene.index:03d}_placeholder.png"
            _create_placeholder(dest, scene.overlay_text)
            scene.visual_path = str(dest)
            scene.is_video = False

        return scene

    # Fetch all scenes in parallel (3 concurrent downloads)
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(_fetch_one_scene, s): s for s in scenes}
        for future in as_completed(futures):
            future.result()  # re-raise any exceptions

    return scenes


def _create_placeholder(dest: Path, text: str):
    """Create a dark gradient placeholder image with text."""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (1920, 1080), (20, 20, 35))
    draw = ImageDraw.Draw(img)

    # Gradient overlay
    for y in range(1080):
        alpha = int(20 + (y / 1080) * 30)
        draw.line([(0, y), (1920, y)], fill=(alpha, alpha, alpha + 15))

    # Text
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 42)
    except Exception:
        font = ImageFont.load_default()

    # Word wrap
    words = text.split()
    lines = []
    current_line = ""
    for word in words:
        test = f"{current_line} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] > 1600:
            lines.append(current_line)
            current_line = word
        else:
            current_line = test
    if current_line:
        lines.append(current_line)

    total_height = len(lines) * 55
    y_start = (1080 - total_height) // 2
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        x = (1920 - (bbox[2] - bbox[0])) // 2
        # Shadow
        draw.text((x + 2, y_start + i * 55 + 2), line, fill=(0, 0, 0), font=font)
        draw.text((x, y_start + i * 55), line, fill=(230, 230, 255), font=font)

    img.save(str(dest))
    logger.info("Created placeholder: %s", dest.name)
