"""VideoForge Configuration — API keys and default settings."""

import os
from pathlib import Path

# ── Paths ───────────────────────────────────────────────────────────────
PROJECT_DIR = Path(__file__).parent.resolve()
ASSETS_DIR = PROJECT_DIR / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
MUSIC_DIR = ASSETS_DIR / "music"

# Output directory: use env var (set by .app launcher) or fallback to local
_output_override = os.getenv("VIDEOFORGE_OUTPUT_DIR", "")
OUTPUT_DIR = Path(_output_override) if _output_override else PROJECT_DIR / "output"

# Ensure directories exist
for d in (ASSETS_DIR, FONTS_DIR, MUSIC_DIR, OUTPUT_DIR):
    d.mkdir(parents=True, exist_ok=True)

# ── Load .env from config dir (portable) or project dir ────────────────
def _load_env():
    """Load .env file — check config dir first, then project dir."""
    config_dir = os.getenv("VIDEOFORGE_CONFIG_DIR", "")
    candidates = []
    if config_dir:
        candidates.append(Path(config_dir) / ".env")
    candidates.append(PROJECT_DIR / ".env")
    
    for env_file in candidates:
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    os.environ.setdefault(key.strip(), val.strip())
            break

_load_env()

# ── API Keys (set via environment or .env) ──────────────────────────────
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# ── Video Defaults ──────────────────────────────────────────────────────
VIDEO_WIDTH = 1920
VIDEO_HEIGHT = 1080
VIDEO_FPS = 30
VIDEO_CODEC = "libx264"
AUDIO_CODEC = "aac"

# ── Scene Defaults ──────────────────────────────────────────────────────
MIN_SCENE_DURATION = 3.0   # seconds
MAX_SCENE_DURATION = 8.0   # seconds
CROSSFADE_DURATION = 0.5   # seconds between scenes
KEN_BURNS_ZOOM = 1.15      # max zoom factor for Ken Burns effect

# ── Subtitle Defaults ──────────────────────────────────────────────────
SUBTITLE_FONT_SIZE = 48
SUBTITLE_FONT_COLOR = "white"
SUBTITLE_BG_COLOR = (0, 0, 0, 180)  # RGBA
SUBTITLE_POSITION = "bottom"  # "bottom", "center", "top"

# ── Visual Search ───────────────────────────────────────────────────────
PEXELS_RESULTS_PER_SCENE = 5
PREFER_VIDEO_OVER_IMAGE = True  # prefer video clips from Pexels
