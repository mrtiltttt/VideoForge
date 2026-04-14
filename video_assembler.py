"""Video Assembler — Combine visuals + audio into final YouTube/TikTok video."""

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

# ── Supported media extensions ───────────────────────────────────────
VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".webp"}
MEDIA_EXTS = VIDEO_EXTS | IMAGE_EXTS


def assign_local_videos_to_scenes(
    scenes: list[Scene],
    video_dir: str | Path,
) -> list[Scene]:
    """Assign local media files (videos + images) to scenes in alphabetical order.

    Files are used sequentially. If all files are exhausted before
    all scenes are filled, the cycle restarts from the beginning.

    Videos are trimmed to scene duration by the assembler.
    Images get Ken Burns (slow zoom) effect.
    Widescreen content is auto-cropped for TikTok mode.

    Args:
        scenes: List of Scene objects with timing info
        video_dir: Path to folder containing video/image files

    Returns:
        Updated scenes with visual_path and is_video set
    """
    video_dir = Path(video_dir)
    media_files = sorted(
        [f for f in video_dir.iterdir() if f.suffix.lower() in MEDIA_EXTS],
        key=lambda f: f.name,
    )

    if not media_files:
        logger.warning("No media files found in %s", video_dir)
        return scenes

    logger.info("Found %d local media files in %s", len(media_files), video_dir.name)

    for i, scene in enumerate(scenes):
        # Cycle through files: when all are used, start from beginning
        media_path = media_files[i % len(media_files)]
        scene.visual_path = str(media_path)
        scene.is_video = media_path.suffix.lower() in VIDEO_EXTS
        kind = "video" if scene.is_video else "image"
        logger.info("Scene %d (%.1fs) → %s [%s]", scene.index, scene.duration, media_path.name, kind)

    return scenes


def _load_image_as_array(path: str, size: tuple = (VIDEO_WIDTH, VIDEO_HEIGHT)) -> np.ndarray:
    """Load image, resize to target size, return numpy array."""
    img = Image.open(path).convert("RGB")
    img = img.resize(size, Image.LANCZOS)
    return np.array(img)


def _smart_resize(img: Image.Image, target_w: int, target_h: int) -> Image.Image:
    """Smart resize: crop to target aspect ratio then resize.
    
    For TikTok (portrait): crops center of landscape image.
    For YouTube (landscape): standard resize.
    """
    src_w, src_h = img.size
    target_ratio = target_w / target_h
    src_ratio = src_w / src_h

    if abs(src_ratio - target_ratio) < 0.05:
        # Already close to target ratio
        return img.resize((target_w, target_h), Image.LANCZOS)

    if src_ratio > target_ratio:
        # Source is wider — crop sides
        new_w = int(src_h * target_ratio)
        offset = (src_w - new_w) // 2
        img = img.crop((offset, 0, offset + new_w, src_h))
    else:
        # Source is taller — crop top/bottom
        new_h = int(src_w / target_ratio)
        offset = (src_h - new_h) // 2
        img = img.crop((0, offset, src_w, offset + new_h))

    return img.resize((target_w, target_h), Image.LANCZOS)


def _create_ken_burns_clip(image_path: str, duration: float, zoom: float = 1.15,
                            video_size: tuple = None):
    """Create a Ken Burns (slow zoom + pan) clip from a still image."""
    from moviepy import ImageClip

    vw, vh = video_size or (VIDEO_WIDTH, VIDEO_HEIGHT)

    # Load at higher resolution for zoom headroom
    img = Image.open(image_path).convert("RGB")
    # Smart crop to target aspect ratio first
    img = _smart_resize(img, int(vw * zoom), int(vh * zoom))
    zoom_w, zoom_h = img.size
    img_array = np.array(img)

    # Random direction: zoom in or zoom out
    zoom_in = random.choice([True, False])
    # Random start position offset
    max_offset_x = zoom_w - vw
    max_offset_y = zoom_h - vh

    def make_frame(t):
        progress = t / max(duration, 0.01)
        if zoom_in:
            scale = 1.0 - progress * (1.0 - 1.0 / zoom)
        else:
            scale = 1.0 / zoom + progress * (1.0 - 1.0 / zoom)

        cw = int(vw / scale)
        ch = int(vh / scale)
        cw = min(cw, zoom_w)
        ch = min(ch, zoom_h)

        cx = (zoom_w - cw) // 2 + int(progress * max_offset_x * 0.3)
        cy = (zoom_h - ch) // 2 + int(progress * max_offset_y * 0.2)
        cx = max(0, min(cx, zoom_w - cw))
        cy = max(0, min(cy, zoom_h - ch))

        crop = img_array[cy:cy + ch, cx:cx + cw]
        pil_crop = Image.fromarray(crop).resize((vw, vh), Image.LANCZOS)
        return np.array(pil_crop)

    from moviepy import VideoClip
    clip = VideoClip(make_frame, duration=duration).with_fps(VIDEO_FPS)
    return clip


def _create_video_scene_clip(video_path: str, duration: float,
                              video_size: tuple = None):
    """Create a clip from a video file, looped if needed.
    Smart-crops to target aspect ratio."""
    from moviepy import VideoFileClip, VideoClip

    vw, vh = video_size or (VIDEO_WIDTH, VIDEO_HEIGHT)
    clip = VideoFileClip(video_path)

    # Smart crop: if aspect ratios differ (e.g. landscape source → portrait target)
    src_w, src_h = clip.size
    target_ratio = vw / vh
    src_ratio = src_w / src_h

    if abs(src_ratio - target_ratio) > 0.1:
        # Need to crop frames
        def crop_frame(get_frame, t):
            frame = get_frame(t)
            fh, fw = frame.shape[:2]
            if src_ratio > target_ratio:
                new_w = int(fh * target_ratio)
                offset = (fw - new_w) // 2
                frame = frame[:, offset:offset + new_w]
            else:
                new_h = int(fw / target_ratio)
                offset = (fh - new_h) // 2
                frame = frame[offset:offset + new_h, :]
            pil = Image.fromarray(frame).resize((vw, vh), Image.LANCZOS)
            return np.array(pil)

        clip = clip.transform(crop_frame)

    clip = clip.resized((vw, vh))

    # Loop if needed
    if clip.duration < duration:
        from moviepy import concatenate_videoclips
        loops_needed = int(duration / clip.duration) + 1
        clip = concatenate_videoclips([clip] * loops_needed)

    clip = clip.subclipped(0, min(duration, clip.duration))
    clip = clip.without_audio()
    return clip


def _create_subtitle_overlay(text: str, duration: float, position: str = "bottom",
                              video_size: tuple = None,
                              font_path: str = None,
                              font_size: int = None,
                              y_percent: int = None):
    """Create a text overlay clip for subtitles."""
    from moviepy import VideoClip

    vw, vh = video_size or (VIDEO_WIDTH, VIDEO_HEIGHT)
    fs = font_size or (SUBTITLE_FONT_SIZE if vw >= 1080 else max(28, SUBTITLE_FONT_SIZE - 12))
    _font_path = font_path or "/System/Library/Fonts/Helvetica.ttc"

    try:
        font = ImageFont.truetype(_font_path, fs)
    except Exception:
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", fs)
        except Exception:
            font = ImageFont.load_default()

    # Word wrap
    max_width = vw - (200 if vw >= 1080 else 80)
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

    line_height = fs + 10
    block_height = len(lines) * line_height + 30
    block_width = vw

    txt_img = Image.new("RGBA", (block_width, block_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(txt_img)

    # Draw text with shadow outline (no background bar)
    shadow_offsets = [(-2, -2), (-2, 2), (2, -2), (2, 2), (-2, 0), (2, 0), (0, -2), (0, 2)]
    y = 15
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        x = (block_width - (bbox[2] - bbox[0])) // 2
        # Shadow/outline
        for ox, oy in shadow_offsets:
            draw.text((x + ox, y + oy), line, fill=(0, 0, 0, 220), font=font)
        # Main text
        draw.text((x, y), line, fill="white", font=font)
        y += line_height

    txt_array = np.array(txt_img)

    # Vertical position
    if y_percent is not None:
        y_pos = int(vh * y_percent / 100) - block_height // 2
        y_pos = max(0, min(y_pos, vh - block_height))
    elif position == "bottom":
        y_pos = vh - block_height - 60
    elif position == "top":
        y_pos = 60
    else:
        y_pos = (vh - block_height) // 2

    def make_frame(t):
        frame = np.zeros((vh, vw, 4), dtype=np.uint8)
        frame[y_pos:y_pos + block_height, 0:block_width] = txt_array
        return frame[:, :, :3]

    def make_mask(t):
        mask = np.zeros((vh, vw), dtype=np.float64)
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
    music_fade_in: float = 3.0,
    music_fade_out: float = 3.0,
    video_size: tuple = None,
    sub_font_path: str = None,
    sub_font_size: int = None,
    sub_y_percent: int = None,
    on_progress=None,
    ending_duration: float = 0.0,
) -> Path:
    """Assemble all scenes with visuals + audio into final video.

    Uses Whisper word-level timestamps for precise subtitle sync.
    Every spoken word appears on screen, grouped into short 3-5 word
    phrases that change in sync with the voice (TikTok/Reels style).

    Args:
        scenes: List of Scene objects with visual_path filled
        audio_path: Path to voiceover audio file
        output_path: Output video file path
        add_subtitles: Whether to add subtitle overlays
        add_music: Optional path to background music file
        music_volume: Volume of background music (0.0-1.0)
        music_fade_in: Fade-in duration for music (seconds)
        music_fade_out: Fade-out duration for music (seconds)
        video_size: (width, height) tuple, defaults to (VIDEO_WIDTH, VIDEO_HEIGHT)
        sub_font_path: Path to subtitle font file
        sub_font_size: Subtitle font size in pixels
        sub_y_percent: Vertical position of subtitles (0-100%)
        on_progress: Callback(current, total) for progress
        ending_duration: Extra seconds to add after voice ends (tail/outro)

    Returns:
        Path to the rendered video file
    """
    from moviepy import (
        AudioFileClip, CompositeVideoClip, CompositeAudioClip,
        concatenate_videoclips,
    )

    vw, vh = video_size or (VIDEO_WIDTH, VIDEO_HEIGHT)

    if output_path is None:
        output_path = OUTPUT_DIR / "output.mp4"
    output_path = Path(output_path)

    # ── Step 0: Get Whisper subtitles upfront (once for entire audio) ──
    all_subtitle_segments = []
    if add_subtitles:
        from subtitle_gen import (
            transcribe_with_timestamps,
            group_words_into_subtitles,
            get_subtitle_segments_for_scene,
        )
        logger.info("Getting Whisper word-level timestamps...")
        words = transcribe_with_timestamps(audio_path)
        if words:
            all_subtitle_segments = group_words_into_subtitles(
                words, words_per_group=4, max_chars=45,
            )
            logger.info("Created %d subtitle segments from %d words",
                        len(all_subtitle_segments), len(words))
        else:
            logger.warning("Whisper returned no words — subtitles will be empty")

    total = len(scenes)
    clips = []

    # ── Ending duration: extend last scene so its video keeps playing ──
    if ending_duration > 0 and scenes:
        scenes[-1].duration += ending_duration
        scenes[-1].end_time += ending_duration
        logger.info("Extended last scene by %.1fs (now %.1fs)", ending_duration, scenes[-1].duration)

    for i, scene in enumerate(scenes):
        if on_progress:
            on_progress(i, total)
        logger.info("Building scene %d/%d (%.1fs)...", i + 1, total, scene.duration)

        # Create visual clip
        if scene.is_video and scene.visual_path:
            try:
                visual = _create_video_scene_clip(scene.visual_path, scene.duration,
                                                   video_size=(vw, vh))
            except Exception as e:
                logger.warning("Video clip failed for scene %d: %s, using Ken Burns", i, e)
                visual = _create_ken_burns_clip(scene.visual_path, scene.duration,
                                                video_size=(vw, vh))
        elif scene.visual_path:
            visual = _create_ken_burns_clip(scene.visual_path, scene.duration, KEN_BURNS_ZOOM,
                                            video_size=(vw, vh))
        else:
            from moviepy import ColorClip
            visual = ColorClip((vw, vh), color=(20, 20, 35), duration=scene.duration)

        # ── Whisper-synced subtitle overlays ──
        if add_subtitles and all_subtitle_segments:
            scene_subs = get_subtitle_segments_for_scene(
                all_subtitle_segments,
                scene.start_time,
                scene.end_time,
            )

            if scene_subs:
                sub_layers = []
                for seg in scene_subs:
                    # Time relative to scene start
                    rel_start = seg.start - scene.start_time
                    rel_end = seg.end - scene.start_time
                    seg_dur = rel_end - rel_start

                    if seg_dur < 0.05:
                        continue

                    sub_clip = _create_subtitle_overlay(
                        seg.text, seg_dur, SUBTITLE_POSITION,
                        video_size=(vw, vh),
                        font_path=sub_font_path,
                        font_size=sub_font_size,
                        y_percent=sub_y_percent,
                    ).with_start(rel_start)
                    sub_layers.append(sub_clip)

                if sub_layers:
                    visual = CompositeVideoClip([visual] + sub_layers)
                    logger.info("  Scene %d: %d subtitle groups", i + 1, len(sub_layers))

        clips.append(visual)

    # Concatenate
    if len(clips) > 1 and CROSSFADE_DURATION > 0:
        final_video = concatenate_videoclips(clips, method="compose")
    else:
        final_video = clips[0] if len(clips) == 1 else concatenate_videoclips(clips)

    # Audio
    voiceover = AudioFileClip(str(audio_path))

    # ── Pad voice with silence for ending duration ──
    if ending_duration > 0:
        from moviepy import AudioClip
        silence = AudioClip(lambda t: [0, 0], duration=ending_duration, fps=44100)
        from moviepy import concatenate_audioclips
        voiceover = concatenate_audioclips([voiceover, silence])
        logger.info("Added %.1fs ending duration (voice padded to %.1fs)", ending_duration, voiceover.duration)

    if add_music and Path(add_music).exists():
        from moviepy import AudioFileClip as AFC
        music = AFC(add_music)
        if music.duration < final_video.duration:
            from moviepy import concatenate_audioclips
            loops = int(final_video.duration / music.duration) + 1
            music = concatenate_audioclips([music] * loops)
        music = music.subclipped(0, final_video.duration)
        music = music.with_volume_scaled(music_volume)
        if music_fade_in > 0 or music_fade_out > 0:
            from moviepy.audio.fx import AudioFadeIn, AudioFadeOut
            effects = []
            if music_fade_in > 0:
                effects.append(AudioFadeIn(music_fade_in))
            if music_fade_out > 0:
                effects.append(AudioFadeOut(music_fade_out))
            music = music.with_effects(effects)
        combined_audio = CompositeAudioClip([voiceover, music])
        final_video = final_video.with_audio(combined_audio)
    else:
        final_video = final_video.with_audio(voiceover)

    # Render
    logger.info("Rendering %dx%d video to %s...", vw, vh, output_path)
    if on_progress:
        on_progress(total, total)

    final_video.write_videofile(
        str(output_path),
        fps=VIDEO_FPS,
        codec="libx264",
        audio_codec="aac",
        preset="ultrafast",
        threads=8,
        logger=None,
    )

    logger.info("✅ Video saved: %s (%.1fs)", output_path, final_video.duration)
    return output_path
