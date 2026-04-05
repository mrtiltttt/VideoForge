"""Video Assembler — Combine visuals + audio into final YouTube video."""

from __future__ import annotations

import logging
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from config import (
    VIDEO_WIDTH, VIDEO_HEIGHT, VIDEO_FPS,
    CROSSFADE_DURATION, KEN_BURNS_ZOOM,
    SUBTITLE_FONT_SIZE, SUBTITLE_BG_COLOR, SUBTITLE_POSITION,
    OUTPUT_DIR,
)
from scene_splitter import Scene

logger = logging.getLogger(__name__)


def _load_image_as_array(path: str, size: tuple = (VIDEO_WIDTH, VIDEO_HEIGHT)) -> np.ndarray:
    """Load image, resize to target size, return numpy array."""
    img = Image.open(path).convert("RGB")
    img = img.resize(size, Image.LANCZOS)
    return np.array(img)


def _create_ken_burns_clip(image_path: str, duration: float, zoom: float = 1.15):
    """Create a Ken Burns (slow zoom + pan) clip from a still image."""
    from moviepy import ImageClip

    # Load at higher resolution for zoom headroom
    img = Image.open(image_path).convert("RGB")
    zoom_w = int(VIDEO_WIDTH * zoom)
    zoom_h = int(VIDEO_HEIGHT * zoom)
    img = img.resize((zoom_w, zoom_h), Image.LANCZOS)
    img_array = np.array(img)

    # Random direction: zoom in or zoom out
    zoom_in = random.choice([True, False])
    # Random start position offset
    max_offset_x = zoom_w - VIDEO_WIDTH
    max_offset_y = zoom_h - VIDEO_HEIGHT

    def make_frame(t):
        progress = t / max(duration, 0.01)
        if zoom_in:
            # Zoom in: start wide, end tight
            scale = 1.0 - progress * (1.0 - 1.0 / zoom)
        else:
            # Zoom out: start tight, end wide
            scale = 1.0 / zoom + progress * (1.0 - 1.0 / zoom)

        # Current crop size
        cw = int(VIDEO_WIDTH / scale)
        ch = int(VIDEO_HEIGHT / scale)
        cw = min(cw, zoom_w)
        ch = min(ch, zoom_h)

        # Center with slight drift
        cx = (zoom_w - cw) // 2 + int(progress * max_offset_x * 0.3)
        cy = (zoom_h - ch) // 2 + int(progress * max_offset_y * 0.2)
        cx = max(0, min(cx, zoom_w - cw))
        cy = max(0, min(cy, zoom_h - ch))

        crop = img_array[cy:cy + ch, cx:cx + cw]
        # Resize to output resolution
        pil_crop = Image.fromarray(crop).resize((VIDEO_WIDTH, VIDEO_HEIGHT), Image.LANCZOS)
        return np.array(pil_crop)

    from moviepy import VideoClip
    clip = VideoClip(make_frame, duration=duration).with_fps(VIDEO_FPS)
    return clip


def _create_video_scene_clip(video_path: str, duration: float):
    """Create a clip from a video file, looped if needed."""
    from moviepy import VideoFileClip

    clip = VideoFileClip(video_path)

    # Resize to target resolution
    clip = clip.resized((VIDEO_WIDTH, VIDEO_HEIGHT))

    # If video is shorter than scene, loop it
    if clip.duration < duration:
        from moviepy import concatenate_videoclips
        loops_needed = int(duration / clip.duration) + 1
        clip = concatenate_videoclips([clip] * loops_needed)

    # Trim to exact duration
    clip = clip.subclipped(0, min(duration, clip.duration))

    # Remove original audio (we'll use our voiceover)
    clip = clip.without_audio()

    return clip


def _create_subtitle_overlay(text: str, duration: float, position: str = "bottom"):
    """Create a text overlay clip for subtitles."""
    from moviepy import VideoClip

    # Pre-render the text image
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", SUBTITLE_FONT_SIZE)
    except Exception:
        font = ImageFont.load_default()

    # Word wrap
    max_width = VIDEO_WIDTH - 200
    words = text.split()
    lines = []
    current_line = ""
    test_img = Image.new("RGBA", (1, 1))
    test_draw = ImageDraw.Draw(test_img)

    for word in words:
        test = f"{current_line} {word}".strip()
        bbox = test_draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] > max_width:
            if current_line:
                lines.append(current_line)
            current_line = word
        else:
            current_line = test
    if current_line:
        lines.append(current_line)

    # Calculate text block size
    line_height = SUBTITLE_FONT_SIZE + 10
    block_height = len(lines) * line_height + 30
    block_width = VIDEO_WIDTH

    # Create text image
    txt_img = Image.new("RGBA", (block_width, block_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(txt_img)

    # Background bar
    bg_color = SUBTITLE_BG_COLOR
    draw.rectangle([(0, 0), (block_width, block_height)], fill=bg_color)

    # Draw text
    y = 15
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        x = (block_width - (bbox[2] - bbox[0])) // 2
        draw.text((x, y), line, fill="white", font=font)
        y += line_height

    txt_array = np.array(txt_img)

    # Position
    if position == "bottom":
        y_pos = VIDEO_HEIGHT - block_height - 60
    elif position == "top":
        y_pos = 60
    else:
        y_pos = (VIDEO_HEIGHT - block_height) // 2

    def make_frame(t):
        frame = np.zeros((VIDEO_HEIGHT, VIDEO_WIDTH, 4), dtype=np.uint8)
        frame[y_pos:y_pos + block_height, 0:block_width] = txt_array
        return frame[:, :, :3]  # Return RGB only

    def make_mask(t):
        mask = np.zeros((VIDEO_HEIGHT, VIDEO_WIDTH), dtype=np.float64)
        alpha = txt_array[:, :, 3].astype(np.float64) / 255.0
        mask[y_pos:y_pos + block_height, 0:block_width] = alpha
        return mask

    clip = VideoClip(make_frame, duration=duration).with_fps(VIDEO_FPS)
    mask_clip = VideoClip(make_mask, duration=duration, is_mask=True).with_fps(VIDEO_FPS)
    clip = clip.with_mask(mask_clip)

    return clip


def assemble_video(
    scenes: list[Scene],
    audio_path: str | Path,
    output_path: str | Path | None = None,
    add_subtitles: bool = True,
    add_music: str | None = None,
    music_volume: float = 0.15,
    on_progress=None,
) -> Path:
    """Assemble all scenes with visuals + audio into final video.

    Args:
        scenes: List of Scene objects with visual_path filled
        audio_path: Path to voiceover audio file
        output_path: Output video file path
        add_subtitles: Whether to add subtitle overlays
        add_music: Optional path to background music file
        music_volume: Volume of background music (0.0-1.0)
        on_progress: Callback(current, total) for progress

    Returns:
        Path to the rendered video file
    """
    from moviepy import (
        AudioFileClip, CompositeVideoClip, CompositeAudioClip,
        concatenate_videoclips,
    )

    if output_path is None:
        output_path = OUTPUT_DIR / "output.mp4"
    output_path = Path(output_path)

    total = len(scenes)
    clips = []

    for i, scene in enumerate(scenes):
        if on_progress:
            on_progress(i, total)
        logger.info("Building scene %d/%d (%.1fs)...", i + 1, total, scene.duration)

        # Create visual clip
        if scene.is_video and scene.visual_path:
            try:
                visual = _create_video_scene_clip(scene.visual_path, scene.duration)
            except Exception as e:
                logger.warning("Video clip failed for scene %d: %s, using Ken Burns", i, e)
                visual = _create_ken_burns_clip(scene.visual_path, scene.duration)
        elif scene.visual_path:
            visual = _create_ken_burns_clip(scene.visual_path, scene.duration, KEN_BURNS_ZOOM)
        else:
            # Black frame fallback
            from moviepy import ColorClip
            visual = ColorClip((VIDEO_WIDTH, VIDEO_HEIGHT), color=(20, 20, 35), duration=scene.duration)

        # Add subtitle overlay
        if add_subtitles and scene.overlay_text:
            subtitle = _create_subtitle_overlay(
                scene.overlay_text, scene.duration, SUBTITLE_POSITION
            )
            visual = CompositeVideoClip([visual, subtitle])

        clips.append(visual)

    # Concatenate all scenes with crossfade
    if len(clips) > 1 and CROSSFADE_DURATION > 0:
        # Simple concatenation (crossfade requires more complex setup)
        final_video = concatenate_videoclips(clips, method="compose")
    else:
        final_video = clips[0] if len(clips) == 1 else concatenate_videoclips(clips)

    # Add voiceover audio
    voiceover = AudioFileClip(str(audio_path))

    # Add background music if provided
    if add_music and Path(add_music).exists():
        from moviepy import AudioFileClip as AFC
        music = AFC(add_music)
        # Loop music if shorter than video
        if music.duration < final_video.duration:
            from moviepy import concatenate_audioclips
            loops = int(final_video.duration / music.duration) + 1
            music = concatenate_audioclips([music] * loops)
        music = music.subclipped(0, final_video.duration)
        music = music.with_volume_scaled(music_volume)
        combined_audio = CompositeAudioClip([voiceover, music])
        final_video = final_video.with_audio(combined_audio)
    else:
        final_video = final_video.with_audio(voiceover)

    # Render
    logger.info("Rendering video to %s...", output_path)
    if on_progress:
        on_progress(total, total)

    final_video.write_videofile(
        str(output_path),
        fps=VIDEO_FPS,
        codec="libx264",
        audio_codec="aac",
        preset="medium",
        threads=4,
        logger=None,
    )

    logger.info("✅ Video saved: %s (%.1fs)", output_path, final_video.duration)
    return output_path
