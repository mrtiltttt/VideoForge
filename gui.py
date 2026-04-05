#!/usr/bin/env python3
"""VideoForge GUI — macOS desktop app for automated YouTube video creation."""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

# Load .env
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())

from config import OUTPUT_DIR, PEXELS_API_KEY
from scene_splitter import split_script, get_audio_duration, Scene
from visual_finder import fetch_visuals_for_scenes
from video_assembler import assemble_video
from subtitle_gen import generate_srt, generate_word_level_srt
from music_finder import find_music_for_text, list_available_moods, FREESOUND_API_KEY

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ── Theme ──────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

BG_DARK = "#0f0f1a"
BG_CARD = "#1a1a2e"
BG_INPUT = "#16213e"
BORDER = "#2a2a4a"
ACCENT = "#e94560"
ACCENT_HOVER = "#ff6b81"
CYAN = "#00d2ff"
GOLD = "#ffd700"
GREEN = "#00e676"
TEXT_PRIMARY = "#e8e8f0"
TEXT_SECONDARY = "#8888aa"
PURPLE = "#a855f7"


class VideoForgeApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("🎬 VideoForge")
        self.geometry("900x700")
        self.configure(fg_color=BG_DARK)
        self.minsize(800, 600)

        self.audio_path: str = ""
        self.scenes: list[Scene] = []
        self.is_running = False

        self._build_ui()

    def _build_ui(self):
        # ── Header ──
        header = ctk.CTkFrame(self, fg_color=BG_CARD, corner_radius=0, height=50)
        header.pack(fill="x")
        header.pack_propagate(False)

        ctk.CTkLabel(header, text="🎬 VideoForge",
                     font=ctk.CTkFont(size=18, weight="bold"),
                     text_color=ACCENT).pack(side="left", padx=15)
        ctk.CTkLabel(header, text="Script → Voice → Visuals → Video",
                     font=ctk.CTkFont(size=11),
                     text_color=TEXT_SECONDARY).pack(side="left", padx=5)

        # API status
        api_status = "🟢 Pexels" if PEXELS_API_KEY else "🔴 Pexels"
        fs_status = " + 🟢 Freesound" if FREESOUND_API_KEY else " + 🔴 Freesound"
        ctk.CTkLabel(header, text=api_status + fs_status,
                     font=ctk.CTkFont(size=10),
                     text_color=GREEN if PEXELS_API_KEY else ACCENT).pack(side="right", padx=15)

        # ── Main content ──
        main = ctk.CTkFrame(self, fg_color="transparent")
        main.pack(fill="both", expand=True, padx=15, pady=10)

        # Left column: inputs
        left = ctk.CTkFrame(main, fg_color="transparent")
        left.pack(side="left", fill="both", expand=True, padx=(0, 8))

        # Right column: settings + scenes
        right = ctk.CTkFrame(main, fg_color="transparent", width=280)
        right.pack(side="right", fill="y", padx=(8, 0))
        right.pack_propagate(False)

        self._build_audio_section(left)
        self._build_script_section(left)
        self._build_output_section(left)
        self._build_settings(right)
        self._build_scenes_preview(right)

        # ── Bottom: actions + progress ──
        self._build_actions()

    # ── Audio Section ──────────────────────────────────────────────────

    def _build_audio_section(self, parent):
        frame = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=10,
                             border_width=1, border_color=BORDER)
        frame.pack(fill="x", pady=(0, 8))

        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=8)

        ctk.CTkLabel(row, text="🎙️ AUDIO",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=CYAN).pack(side="left")

        self.audio_label = ctk.CTkLabel(row, text="No file selected",
                                        font=ctk.CTkFont(size=11),
                                        text_color=TEXT_SECONDARY)
        self.audio_label.pack(side="left", padx=10)

        ctk.CTkButton(row, text="📂 Browse", width=90, height=28,
                      font=ctk.CTkFont(size=11),
                      fg_color=CYAN, hover_color="#33ddff",
                      text_color=BG_DARK,
                      command=self._browse_audio).pack(side="right")

    # ── Script Section ─────────────────────────────────────────────────

    def _build_script_section(self, parent):
        frame = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=10,
                             border_width=1, border_color=BORDER)
        frame.pack(fill="both", expand=True, pady=(0, 8))

        # Header row
        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(8, 2))

        ctk.CTkLabel(row, text="📝 SCRIPT",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=GOLD).pack(side="left")

        self.char_label = ctk.CTkLabel(row, text="0 chars",
                                       font=ctk.CTkFont(size=9),
                                       text_color=TEXT_SECONDARY)
        self.char_label.pack(side="right")

        ctk.CTkButton(row, text="📂 Load .txt", width=80, height=24,
                      font=ctk.CTkFont(size=10),
                      fg_color="transparent", hover_color=BG_INPUT,
                      text_color=TEXT_SECONDARY,
                      command=self._load_script).pack(side="right", padx=5)

        # Text action buttons
        btn_row = ctk.CTkFrame(frame, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=(2, 2))

        for text_lbl, cmd in [
            ("Select All", self._select_all_script),
            ("Delete All", lambda: (self.script_input.delete("1.0", "end"), self._update_chars())),
            ("📋 Copy",    self._copy_script),
            ("📌 Paste",   self._paste_script),
        ]:
            ctk.CTkButton(btn_row, text=text_lbl, width=75, height=24,
                          font=ctk.CTkFont(size=10),
                          fg_color=BG_INPUT, hover_color=BORDER,
                          text_color=TEXT_SECONDARY,
                          command=cmd).pack(side="left", padx=2)

        # Text input
        self.script_input = ctk.CTkTextbox(
            frame, font=ctk.CTkFont(family="SF Mono", size=12),
            fg_color=BG_INPUT, text_color=TEXT_PRIMARY,
            border_width=0, corner_radius=8, wrap="word",
        )
        self.script_input.pack(fill="both", expand=True, padx=10, pady=(2, 8))
        self.script_input.bind("<KeyRelease>", lambda e: self._update_chars())

    # ── Output Section ─────────────────────────────────────────────────

    def _build_output_section(self, parent):
        frame = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=10,
                             border_width=1, border_color=BORDER)
        frame.pack(fill="x", pady=(0, 0))

        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=8)

        ctk.CTkLabel(row, text="📁 OUTPUT",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=GREEN).pack(side="left")

        self.output_entry = ctk.CTkEntry(
            row, font=ctk.CTkFont(size=11),
            fg_color=BG_INPUT, text_color=TEXT_PRIMARY,
            border_width=0, corner_radius=6, width=400,
        )
        self.output_entry.pack(side="left", padx=10, fill="x", expand=True)
        # Default output path
        default_out = str(OUTPUT_DIR / f"video_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4")
        self.output_entry.insert(0, default_out)

        ctk.CTkButton(row, text="📂", width=35, height=28,
                      font=ctk.CTkFont(size=13),
                      fg_color="transparent", hover_color=BG_INPUT,
                      text_color=TEXT_SECONDARY,
                      command=self._browse_output).pack(side="right")

    # ── Settings ───────────────────────────────────────────────────────

    def _build_settings(self, parent):
        frame = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=10,
                             border_width=1, border_color=BORDER)
        frame.pack(fill="x", pady=(0, 8))

        ctk.CTkLabel(frame, text="⚙️ SETTINGS",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=PURPLE).pack(anchor="w", padx=12, pady=(8, 4))

        settings = ctk.CTkFrame(frame, fg_color="transparent")
        settings.pack(fill="x", padx=12, pady=(0, 8))

        # Subtitles toggle
        self.subtitles_var = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(settings, text="💬 Subtitles",
                      font=ctk.CTkFont(size=11),
                      variable=self.subtitles_var,
                      progress_color=PURPLE,
                      text_color=TEXT_PRIMARY).pack(anchor="w", pady=2)

        # SRT export
        self.srt_var = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(settings, text="📄 Export SRT",
                      font=ctk.CTkFont(size=11),
                      variable=self.srt_var,
                      progress_color=PURPLE,
                      text_color=TEXT_PRIMARY).pack(anchor="w", pady=2)

        # Prefer video clips
        self.prefer_video_var = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(settings, text="🎥 Prefer video clips",
                      font=ctk.CTkFont(size=11),
                      variable=self.prefer_video_var,
                      progress_color=PURPLE,
                      text_color=TEXT_PRIMARY).pack(anchor="w", pady=2)

        # Use AI images
        self.ai_var = ctk.BooleanVar(value=False)
        ctk.CTkSwitch(settings, text="🤖 AI images (DALL-E)",
                      font=ctk.CTkFont(size=11),
                      variable=self.ai_var,
                      progress_color=PURPLE,
                      text_color=TEXT_PRIMARY).pack(anchor="w", pady=2)

        # Scene duration
        dur_row = ctk.CTkFrame(settings, fg_color="transparent")
        dur_row.pack(fill="x", pady=(6, 0))

        ctk.CTkLabel(dur_row, text="Scene duration:",
                     font=ctk.CTkFont(size=10),
                     text_color=TEXT_SECONDARY).pack(side="left")

        self.min_scene_var = ctk.DoubleVar(value=3.0)
        ctk.CTkEntry(dur_row, width=40, height=24,
                     font=ctk.CTkFont(size=10),
                     fg_color=BG_INPUT, text_color=TEXT_PRIMARY,
                     textvariable=self.min_scene_var,
                     border_width=0).pack(side="left", padx=3)

        ctk.CTkLabel(dur_row, text="–",
                     font=ctk.CTkFont(size=10),
                     text_color=TEXT_SECONDARY).pack(side="left")

        self.max_scene_var = ctk.DoubleVar(value=8.0)
        ctk.CTkEntry(dur_row, width=40, height=24,
                     font=ctk.CTkFont(size=10),
                     fg_color=BG_INPUT, text_color=TEXT_PRIMARY,
                     textvariable=self.max_scene_var,
                     border_width=0).pack(side="left", padx=3)

        ctk.CTkLabel(dur_row, text="sec",
                     font=ctk.CTkFont(size=10),
                     text_color=TEXT_SECONDARY).pack(side="left")

        # Music — auto or manual
        music_header = ctk.CTkFrame(settings, fg_color="transparent")
        music_header.pack(fill="x", pady=(8, 0))

        ctk.CTkLabel(music_header, text="🎵 MUSIC",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=GOLD).pack(side="left")

        self.auto_music_var = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(music_header, text="Auto",
                      font=ctk.CTkFont(size=10),
                      variable=self.auto_music_var,
                      progress_color=GOLD,
                      width=40,
                      text_color=TEXT_PRIMARY).pack(side="right")

        # Mood selector
        mood_row = ctk.CTkFrame(settings, fg_color="transparent")
        mood_row.pack(fill="x", pady=(3, 0))

        ctk.CTkLabel(mood_row, text="Mood:",
                     font=ctk.CTkFont(size=9),
                     text_color=TEXT_SECONDARY).pack(side="left")

        moods = ["auto"] + list_available_moods()
        self.mood_var = ctk.StringVar(value="auto")
        ctk.CTkOptionMenu(mood_row, variable=self.mood_var,
                          values=moods, width=120, height=22,
                          font=ctk.CTkFont(size=10),
                          fg_color=BG_INPUT,
                          button_color=BORDER,
                          dropdown_fg_color=BG_CARD).pack(side="left", padx=5)

        # Manual browse
        music_row = ctk.CTkFrame(settings, fg_color="transparent")
        music_row.pack(fill="x", pady=(3, 0))

        self.music_label = ctk.CTkLabel(music_row, text="Auto-detect",
                                        font=ctk.CTkFont(size=9),
                                        text_color=TEXT_SECONDARY)
        self.music_label.pack(side="left")

        ctk.CTkButton(music_row, text="📂 Browse", width=65, height=20,
                      font=ctk.CTkFont(size=9),
                      fg_color="transparent", hover_color=BG_INPUT,
                      text_color=TEXT_SECONDARY,
                      command=self._browse_music).pack(side="right")

        self.music_path = ""

        # Music volume
        vol_row = ctk.CTkFrame(settings, fg_color="transparent")
        vol_row.pack(fill="x", pady=(3, 0))

        ctk.CTkLabel(vol_row, text="Volume:",
                     font=ctk.CTkFont(size=9),
                     text_color=TEXT_SECONDARY).pack(side="left")

        self.music_vol_var = ctk.DoubleVar(value=0.15)
        ctk.CTkSlider(vol_row, from_=0, to=0.5,
                      variable=self.music_vol_var,
                      width=130, height=14,
                      progress_color=GOLD,
                      fg_color=BORDER).pack(side="left", padx=5)

    # ── Scenes Preview ─────────────────────────────────────────────────

    def _build_scenes_preview(self, parent):
        frame = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=10,
                             border_width=1, border_color=BORDER)
        frame.pack(fill="both", expand=True, pady=(0, 0))

        row = ctk.CTkFrame(frame, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(8, 2))

        ctk.CTkLabel(row, text="🎬 SCENES",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=ACCENT).pack(side="left")

        self.scene_count_label = ctk.CTkLabel(row, text="",
                                              font=ctk.CTkFont(size=9),
                                              text_color=TEXT_SECONDARY)
        self.scene_count_label.pack(side="right")

        ctk.CTkButton(row, text="⟳ Preview", width=70, height=22,
                      font=ctk.CTkFont(size=10),
                      fg_color="transparent", hover_color=BG_INPUT,
                      text_color=CYAN,
                      command=self._preview_scenes).pack(side="right", padx=5)

        self.scenes_list = ctk.CTkTextbox(
            frame, font=ctk.CTkFont(family="SF Mono", size=10),
            fg_color=BG_INPUT, text_color=TEXT_SECONDARY,
            border_width=0, corner_radius=6, wrap="word",
            state="disabled",
        )
        self.scenes_list.pack(fill="both", expand=True, padx=10, pady=(2, 8))

    # ── Actions ────────────────────────────────────────────────────────

    def _build_actions(self):
        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.pack(fill="x", padx=15, pady=(8, 10))

        # Progress
        self.progress_bar = ctk.CTkProgressBar(bottom, height=6,
                                                progress_color=ACCENT,
                                                fg_color=BORDER)
        self.progress_bar.pack(fill="x", pady=(0, 6))
        self.progress_bar.set(0)

        # Status + buttons row
        row = ctk.CTkFrame(bottom, fg_color="transparent")
        row.pack(fill="x")

        self.status_label = ctk.CTkLabel(row, text="Ready",
                                         font=ctk.CTkFont(size=11),
                                         text_color=TEXT_SECONDARY)
        self.status_label.pack(side="left")

        # Generate button
        self.gen_btn = ctk.CTkButton(
            row, text="⚡ Generate Video", width=180, height=40,
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color=ACCENT, hover_color=ACCENT_HOVER,
            text_color="white",
            command=self._start_generation,
        )
        self.gen_btn.pack(side="right")

        # Open output folder
        ctk.CTkButton(row, text="📂 Output", width=80, height=40,
                      font=ctk.CTkFont(size=12),
                      fg_color=BG_CARD, hover_color=BORDER,
                      text_color=TEXT_SECONDARY,
                      command=lambda: os.system(f'open "{OUTPUT_DIR}"')).pack(side="right", padx=8)

        # Preview scenes
        ctk.CTkButton(row, text="👁 Preview", width=80, height=40,
                      font=ctk.CTkFont(size=12),
                      fg_color=BG_CARD, hover_color=BORDER,
                      text_color=CYAN,
                      command=self._preview_scenes).pack(side="right", padx=4)

    # ── Callbacks ──────────────────────────────────────────────────────

    def _browse_audio(self):
        path = filedialog.askopenfilename(
            filetypes=[("Audio", "*.wav *.mp3 *.m4a *.flac *.ogg *.aac")]
        )
        if path:
            self.audio_path = path
            name = Path(path).name
            try:
                dur = get_audio_duration(path)
                self.audio_label.configure(text=f"✅ {name} ({dur:.1f}s)", text_color=GREEN)
            except Exception:
                self.audio_label.configure(text=f"✅ {name}", text_color=GREEN)

    def _load_script(self):
        path = filedialog.askopenfilename(filetypes=[("Text", "*.txt")])
        if path:
            text = Path(path).read_text(encoding="utf-8")
            self.script_input.delete("1.0", "end")
            self.script_input.insert("1.0", text)
            self._update_chars()

    def _browse_output(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".mp4",
            filetypes=[("MP4", "*.mp4")],
            initialdir=str(OUTPUT_DIR),
        )
        if path:
            self.output_entry.delete(0, "end")
            self.output_entry.insert(0, path)

    def _browse_music(self):
        path = filedialog.askopenfilename(
            filetypes=[("Audio", "*.mp3 *.wav *.m4a *.ogg")]
        )
        if path:
            self.music_path = path
            self.music_label.configure(text=Path(path).name, text_color=GOLD)

    def _select_all_script(self):
        self.script_input.tag_add("sel", "1.0", "end-1c")
        self.script_input.focus_set()

    def _copy_script(self):
        text = self.script_input.get("1.0", "end-1c")
        self.clipboard_clear()
        self.clipboard_append(text)
        self._set_status("📋 Copied to clipboard", CYAN)

    def _paste_script(self):
        try:
            text = self.clipboard_get()
            self.script_input.insert("insert", text)
            self._update_chars()
        except Exception:
            pass

    def _update_chars(self):
        text = self.script_input.get("1.0", "end-1c")
        self.char_label.configure(text=f"{len(text):,} chars")

    def _set_status(self, text: str, color: str = TEXT_SECONDARY):
        self.status_label.configure(text=text, text_color=color)

    def _preview_scenes(self):
        text = self.script_input.get("1.0", "end-1c").strip()
        if not text:
            messagebox.showwarning("Warning", "Enter script text first")
            return
        if not self.audio_path:
            messagebox.showwarning("Warning", "Select audio file first")
            return

        try:
            self.scenes = split_script(
                text, self.audio_path,
                self.min_scene_var.get(), self.max_scene_var.get(),
            )

            self.scenes_list.configure(state="normal")
            self.scenes_list.delete("1.0", "end")

            for s in self.scenes:
                self.scenes_list.insert("end",
                    f"[{s.index+1}] {s.start_time:.1f}-{s.end_time:.1f}s\n"
                    f"  🔍 {s.search_query}\n"
                    f"  💬 {s.overlay_text}\n\n"
                )

            self.scenes_list.configure(state="disabled")
            self.scene_count_label.configure(text=f"{len(self.scenes)} scenes")
            self._set_status(f"✅ {len(self.scenes)} scenes created", GREEN)

        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _start_generation(self):
        if self.is_running:
            return

        text = self.script_input.get("1.0", "end-1c").strip()
        if not text:
            messagebox.showwarning("Warning", "Enter script text")
            return
        if not self.audio_path:
            messagebox.showwarning("Warning", "Select audio file")
            return

        self.is_running = True
        self.gen_btn.configure(state="disabled", text="⏳ Generating...")

        thread = threading.Thread(target=self._run_pipeline, args=(text,), daemon=True)
        thread.start()

    def _run_pipeline(self, text: str):
        try:
            output_path = self.output_entry.get().strip()
            if not output_path:
                output_path = str(OUTPUT_DIR / f"video_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp4")

            work_dir = OUTPUT_DIR / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            work_dir.mkdir(parents=True, exist_ok=True)

            # Step 1: Split scenes
            self.after(0, lambda: self._set_status("📝 Splitting into scenes...", CYAN))
            self.after(0, lambda: self.progress_bar.set(0.1))

            self.scenes = split_script(
                text, self.audio_path,
                self.min_scene_var.get(), self.max_scene_var.get(),
            )

            # Update scenes preview
            self.after(0, lambda: self._update_scenes_display())

            # Step 2: Fetch visuals
            self.after(0, lambda: self._set_status(f"🎨 Fetching visuals for {len(self.scenes)} scenes...", GOLD))
            self.after(0, lambda: self.progress_bar.set(0.3))

            self.scenes = fetch_visuals_for_scenes(
                self.scenes,
                work_dir=work_dir / "visuals",
                use_ai=self.ai_var.get(),
                prefer_video=self.prefer_video_var.get(),
            )

            # Step 2.5: Auto-find music
            music_to_use = self.music_path or None
            if self.auto_music_var.get() and not music_to_use:
                self.after(0, lambda: self._set_status("🎵 Finding background music...", GOLD))
                self.after(0, lambda: self.progress_bar.set(0.5))
                mood_override = None if self.mood_var.get() == "auto" else self.mood_var.get()
                audio_dur = get_audio_duration(self.audio_path)
                music_path, detected_mood = find_music_for_text(
                    text, duration_hint=audio_dur, mood_override=mood_override
                )
                if music_path:
                    music_to_use = music_path
                    self.after(0, lambda m=detected_mood: self.music_label.configure(
                        text=f"🎵 {m}", text_color=GOLD))
                    self.after(0, lambda m=detected_mood: self._set_status(
                        f"🎵 Found music: {m}", GOLD))

            # Step 3: Assemble video
            self.after(0, lambda: self._set_status("🎬 Assembling video...", PURPLE))
            self.after(0, lambda: self.progress_bar.set(0.6))

            result = assemble_video(
                scenes=self.scenes,
                audio_path=self.audio_path,
                output_path=output_path,
                add_subtitles=self.subtitles_var.get(),
                add_music=music_to_use,
                music_volume=self.music_vol_var.get(),
            )

            # Step 4: SRT
            if self.srt_var.get():
                srt_path = Path(output_path).with_suffix(".srt")
                generate_word_level_srt(text, self.audio_path, srt_path)

            self.after(0, lambda: self.progress_bar.set(1.0))
            self.after(0, lambda: self._set_status(f"✅ Done! Saved: {Path(output_path).name}", GREEN))
            self.after(0, lambda: messagebox.showinfo("Done!", f"Video saved:\n{output_path}"))

        except Exception as e:
            logger.error("Pipeline error: %s", e, exc_info=True)
            self.after(0, lambda: self._set_status(f"❌ Error: {e}", ACCENT))
            self.after(0, lambda: messagebox.showerror("Error", str(e)))

        finally:
            self.is_running = False
            self.after(0, lambda: self.gen_btn.configure(state="normal", text="⚡ Generate Video"))

    def _update_scenes_display(self):
        self.scenes_list.configure(state="normal")
        self.scenes_list.delete("1.0", "end")
        for s in self.scenes:
            self.scenes_list.insert("end",
                f"[{s.index+1}] {s.start_time:.1f}-{s.end_time:.1f}s\n"
                f"  🔍 {s.search_query}\n"
                f"  💬 {s.overlay_text}\n\n"
            )
        self.scenes_list.configure(state="disabled")
        self.scene_count_label.configure(text=f"{len(self.scenes)} scenes")


def main():
    app = VideoForgeApp()
    app.mainloop()


if __name__ == "__main__":
    main()
