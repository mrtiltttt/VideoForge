# 🎬 VideoForge

Automated YouTube video creation from script + voiceover.

**Text → Voice (ChatterVox) → Scenes → Visuals → Video**

## ✨ Features

- 📝 **Auto Scene Splitting** — Splits script into timed scenes synced with audio
- 🎨 **Visual Search** — Pexels stock photos/videos or AI-generated images (DALL-E)
- 🎥 **Ken Burns Effect** — Smooth zoom/pan animations on still images
- 💬 **Auto Subtitles** — Built-in subtitle overlay + SRT export
- 🎵 **Background Music** — Optional ambient music mixing
- ⚡ **One Command** — Full pipeline in ~5 minutes

## 🚀 Quick Start

```bash
# 1. Setup
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 2. Configure API keys
cp .env.example .env
# Edit .env and add your Pexels API key (free: https://www.pexels.com/api/)

# 3. Run!
python videoforge.py --audio voiceover.wav --script script.txt
```

## 📖 Usage

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

### Without Pexels (placeholders only)
```bash
python videoforge.py --audio output.wav --script script.txt --no-pexels
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
├── videoforge.py          # Main CLI entry point
├── scene_splitter.py      # Split text → timed scenes
├── visual_finder.py       # Pexels/AI visual search
├── video_assembler.py     # moviepy video assembly
├── subtitle_gen.py        # SRT subtitle generation
├── config.py              # Settings & defaults
├── requirements.txt
├── .env.example
└── assets/
    ├── fonts/             # Custom fonts (optional)
    └── music/             # Background music files
```

## 🎬 Pipeline

```
1. Script text + Audio file
       ↓
2. Scene Splitter → timed scenes with search queries
       ↓
3. Visual Finder → download Pexels clips/photos or AI images
       ↓
4. Video Assembler → Ken Burns + subtitles + transitions
       ↓
5. Final MP4 (1920x1080, 30fps) + optional SRT
```

## ⚙️ Configuration

Edit `config.py` to customize:
- Video resolution (default: 1920x1080)
- FPS (default: 30)
- Scene duration range (3-8 seconds)
- Ken Burns zoom factor
- Subtitle styling
- Crossfade duration

## 🔗 Integration with ChatterVox

```bash
# 1. Generate voiceover in ChatterVox → save as output.wav
# 2. Save your script as script.txt
# 3. Create video:
python videoforge.py --audio ~/path/to/output.wav --script script.txt --srt
```

---

Made with ❤️ for content creators
