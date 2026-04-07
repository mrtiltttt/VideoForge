# 🎬 VideoForge

Automated YouTube/TikTok video creation from script + voiceover.

**Text → Voice (ChatterVox) → Scenes → Visuals → Video**

## ✨ Features

- 🖥 **macOS GUI** — Full desktop app with CustomTkinter dark UI
- 📝 **Auto Scene Splitting** — Splits script into timed scenes synced with audio
- 🎨 **Visual Search** — Pexels stock photos/videos or AI-generated images (DALL-E)
- 🎥 **Ken Burns Effect** — Smooth zoom/pan animations on still images
- 💬 **Whisper Subtitles** — Word-level synced subtitles via faster-whisper
- 🎵 **Background Music** — Optional ambient music with fade in/out controls
- 📱 **TikTok / YouTube** — 9:16 and 16:9 format support
- ⚡ **One Command** — Full pipeline in ~5 minutes

## 🚀 Quick Start

### GUI (recommended)
```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Add your Pexels API key
python gui.py
```

### CLI
```bash
python videoforge.py --audio voiceover.wav --script script.txt
```

## 📦 Build Portable macOS App

Build a standalone `.app` bundle that runs on any Mac:

```bash
bash build_app.sh
open dist/VideoForge.app
```

### What the build does

1. Copies all Python source → `VideoForge.app/Contents/Resources/app/`
2. Copies entire `venv/site-packages` (~280 MB) → `Resources/site-packages/`
3. Compiles a native **C launcher** (Mach-O arm64) → `Contents/MacOS/VideoForge`
4. Creates `Info.plist` for macOS
5. Strips `com.apple.quarantine` extended attributes

### Architecture

```
VideoForge.app/
└── Contents/
    ├── Info.plist
    ├── MacOS/
    │   └── VideoForge          ← Native C binary (arm64)
    └── Resources/
        ├── app/                ← Python source code
        └── site-packages/      ← All pip dependencies + bundled FFmpeg
```

**The C launcher:**
- Finds system `python3` (Homebrew → python.org → Xcode CLT)
- Sets `PYTHONPATH` to bundled `site-packages/`
- Handles quarantine removal on first run
- Creates `ffmpeg` symlink for pydub compatibility
- Stores output in `~/Desktop/VideoForge_Output/`
- Stores config in `~/Library/Application Support/VideoForge/`

### Transfer to another Mac

When transferring the `.app` to another Mac, macOS Gatekeeper will block it ("app is damaged"). Fix:

```bash
xattr -cr /path/to/VideoForge.app
```

Or use the included `Зняти_карантин.command` — double-click it next to the `.app`.

### Requirements on target Mac

| Requirement | Details |
|-------------|---------|
| macOS | 12.0+ (Monterey or newer) |
| Architecture | Apple Silicon (M1/M2/M3/M4) |
| Python 3 | Any — Homebrew, Xcode CLT, or python.org |

### ⚠️ Build Notes: What doesn't work

- **Bundling Homebrew Python binary** — Has framework respawn mechanism (`python3.14` → `Python.app` → framework dylib chain). `install_name_tool` path rewriting breaks code signature (SIGKILL exit 137). Not portable.
- **Bash script as CFBundleExecutable** — macOS `open` requires Mach-O binary, bash gives error -10669.
- **PyInstaller** — Breaks `ctranslate2`, `onnxruntime`, `faster-whisper` model loading, and `customtkinter` asset paths.

## 📖 CLI Usage

### Basic
```bash
python videoforge.py --audio output.wav --script script.txt
```

### With AI-generated images
```bash
python videoforge.py --audio output.wav --script script.txt --ai
```

### Inline text
```bash
python videoforge.py --audio output.wav --text "Your text here"
```

### With background music
```bash
python videoforge.py --audio output.wav --script script.txt --music assets/music/lofi.mp3
```

### Photos only (no video clips)
```bash
python videoforge.py --audio output.wav --script script.txt --prefer-photos
```

### Generate SRT subtitles
```bash
python videoforge.py --audio output.wav --script script.txt --srt
```

## 🔑 API Keys

| Service | Purpose | Cost | Link |
|---------|---------|------|------|
| **Pexels** | Stock photos & videos | Free | [pexels.com/api](https://www.pexels.com/api/) |
| **OpenAI** | AI image generation | ~$0.04/image | [platform.openai.com](https://platform.openai.com) |

## 📁 Project Structure

```
VideoForge/
├── gui.py                 # macOS desktop GUI (CustomTkinter)
├── videoforge.py          # CLI entry point
├── scene_splitter.py      # Split text → timed scenes
├── visual_finder.py       # Pexels/AI visual search
├── video_assembler.py     # moviepy video assembly
├── subtitle_gen.py        # Whisper word-level subtitles + SRT
├── config.py              # Settings & portable paths
├── build_app.sh           # macOS .app bundle builder
├── requirements.txt
├── .env.example
└── assets/
    ├── fonts/
    └── music/
```

## 🎬 Pipeline

```
1. Script text + Audio file
       ↓
2. Scene Splitter → timed scenes with search queries
       ↓
3. Visual Finder → download Pexels clips/photos or AI images
       ↓
4. Whisper → word-level timestamps for subtitles
       ↓
5. Video Assembler → Ken Burns + subtitles + music + transitions
       ↓
6. Final MP4 (1080x1920 or 1920x1080) + optional SRT
```

## 🔗 Integration with ChatterVox

```bash
# 1. Generate voiceover in ChatterVox → save as output.wav
# 2. Save your script as script.txt
# 3. Create video:
python videoforge.py --audio ~/path/to/output.wav --script script.txt --srt
```

---

Made with ❤️ for content creators
