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

# Config loads .env and sets up paths
from config import OUTPUT_DIR, PEXELS_API_KEY
from scene_splitter import split_script, get_audio_duration, Scene
from visual_finder import fetch_visuals_for_scenes
from video_assembler import assemble_video
from subtitle_gen import generate_srt, generate_word_level_srt

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
        self._cancel_flag = False

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
        api_status = "🟢 Pexels OK" if PEXELS_API_KEY else "🔴 No Pexels Key"
        ctk.CTkLabel(header, text=api_status,
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

        # Default script
        _default_script = (
            "Hey, lighten up!\n\n"
            "What's the one thing women crave most in a relationship? Sex? Money? Nope! "
            "It's all about the game! Seriously, that's what makes her tick, makes her feel "
            "secure, wanted, and loved.\n"
            "Why's that? Women are like kids. Playing is how she gauges your dominance, "
            "figures out how awesome you are. It's like a mating dance for birds. No game, no gain!\n"
            "Remember this:\n"
            "You have the ultimate power over a woman when you're playing with her.\n"
            "Don't spoil the game! Don't say \"I love you\" until she asks. Let her figure it out.\n"
            "Make her feel good. Your mission is to get her hooked on the drug that is you. "
            "But! Only when you're in a good mood – that's what she'll be working towards.\n"
            "Bottom line: Want a woman to be obsessed with you? Turn her life into a game "
            "where she can influence the outcome. Show her that how good things are for both "
            "of you depends on her actions."
        )
        self.script_input.insert("1.0", _default_script)
        self._update_chars()

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

        # Format selector (YouTube / TikTok)
        fmt_row = ctk.CTkFrame(settings, fg_color="transparent")
        fmt_row.pack(fill="x", pady=(0, 6))

        self.format_var = ctk.StringVar(value="📱 TikTok (9:16)")
        ctk.CTkSegmentedButton(
            fmt_row,
            values=["🖥 YouTube (16:9)", "📱 TikTok (9:16)"],
            variable=self.format_var,
            font=ctk.CTkFont(size=10, weight="bold"),
            selected_color=ACCENT,
            selected_hover_color=ACCENT_HOVER,
            unselected_color=BG_INPUT,
            text_color=TEXT_PRIMARY,
        ).pack(fill="x")

        # Subtitles toggle
        self.subtitles_var = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(settings, text="💬 Subtitles",
                      font=ctk.CTkFont(size=11),
                      variable=self.subtitles_var,
                      progress_color=PURPLE,
                      text_color=TEXT_PRIMARY).pack(anchor="w", pady=2)

        # Subtitle controls frame
        sub_frame = ctk.CTkFrame(settings, fg_color="transparent")
        sub_frame.pack(fill="x", pady=(2, 4))

        # Font selector
        self._font_options = {
            "Impact": "/System/Library/Fonts/Supplemental/Impact.ttf",
            "Arial Black": "/System/Library/Fonts/Supplemental/Arial Black.ttf",
            "Futura Bold": "/System/Library/Fonts/Supplemental/Futura.ttc",
            "Helvetica Bold": "/System/Library/Fonts/Helvetica.ttc",
            "Avenir Black": "/System/Library/Fonts/Avenir.ttc",
            "Avenir Next Bold": "/System/Library/Fonts/Avenir Next.ttc",
            "Avenir Condensed": "/System/Library/Fonts/Avenir Next Condensed.ttc",
            "Chalkboard": "/System/Library/Fonts/Supplemental/Chalkboard.ttc",
            "Comic Sans": "/System/Library/Fonts/Supplemental/Comic Sans MS Bold.ttf",
            "Arial Rounded": "/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf",
            "Menlo": "/System/Library/Fonts/Menlo.ttc",
        }
        self.sub_font_var = ctk.StringVar(value="Impact")
        font_row = ctk.CTkFrame(sub_frame, fg_color="transparent")
        font_row.pack(fill="x", pady=1)
        ctk.CTkLabel(font_row, text="Font:",
                     font=ctk.CTkFont(size=9),
                     text_color=TEXT_SECONDARY).pack(side="left")
        ctk.CTkOptionMenu(font_row,
                          values=list(self._font_options.keys()),
                          variable=self.sub_font_var,
                          font=ctk.CTkFont(size=9),
                          dropdown_font=ctk.CTkFont(size=10),
                          width=120, height=22,
                          fg_color=BG_INPUT,
                          button_color=BORDER,
                          dropdown_fg_color=BG_CARD,
                          ).pack(side="left", padx=4)

        # Font size slider
        size_row = ctk.CTkFrame(sub_frame, fg_color="transparent")
        size_row.pack(fill="x", pady=1)
        ctk.CTkLabel(size_row, text="Size:",
                     font=ctk.CTkFont(size=9),
                     text_color=TEXT_SECONDARY).pack(side="left")
        self.sub_size_var = ctk.IntVar(value=42)
        ctk.CTkSlider(size_row, from_=24, to=96,
                      variable=self.sub_size_var,
                      width=100, height=14,
                      fg_color=BORDER,
                      command=lambda v: self.sub_size_label.configure(
                          text=f"{int(v)}px")).pack(side="left", padx=4)
        self.sub_size_label = ctk.CTkLabel(size_row, text="42px",
                                            font=ctk.CTkFont(size=10, weight="bold"),
                                            text_color=GOLD)
        self.sub_size_label.pack(side="left")

        # Position slider (vertical %)
        pos_row = ctk.CTkFrame(sub_frame, fg_color="transparent")
        pos_row.pack(fill="x", pady=1)
        ctk.CTkLabel(pos_row, text="Y pos:",
                     font=ctk.CTkFont(size=9),
                     text_color=TEXT_SECONDARY).pack(side="left")
        self.sub_pos_var = ctk.IntVar(value=75)
        ctk.CTkSlider(pos_row, from_=10, to=95,
                      variable=self.sub_pos_var,
                      width=100, height=14,
                      fg_color=BORDER,
                      command=lambda v: self.sub_pos_label.configure(
                          text=f"{int(v)}%")).pack(side="left", padx=4)
        self.sub_pos_label = ctk.CTkLabel(pos_row, text="75%",
                                           font=ctk.CTkFont(size=10, weight="bold"),
                                           text_color=GOLD)
        self.sub_pos_label.pack(side="left")

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

        self.min_scene_var = ctk.DoubleVar(value=2.0)
        ctk.CTkEntry(dur_row, width=40, height=24,
                     font=ctk.CTkFont(size=10),
                     fg_color=BG_INPUT, text_color=TEXT_PRIMARY,
                     textvariable=self.min_scene_var,
                     border_width=0).pack(side="left", padx=3)

        ctk.CTkLabel(dur_row, text="–",
                     font=ctk.CTkFont(size=10),
                     text_color=TEXT_SECONDARY).pack(side="left")

        self.max_scene_var = ctk.DoubleVar(value=3.0)
        ctk.CTkEntry(dur_row, width=40, height=24,
                     font=ctk.CTkFont(size=10),
                     fg_color=BG_INPUT, text_color=TEXT_PRIMARY,
                     textvariable=self.max_scene_var,
                     border_width=0).pack(side="left", padx=3)

        ctk.CTkLabel(dur_row, text="sec",
                     font=ctk.CTkFont(size=10),
                     text_color=TEXT_SECONDARY).pack(side="left")

        # Music
        music_header = ctk.CTkFrame(settings, fg_color="transparent")
        music_header.pack(fill="x", pady=(8, 0))

        ctk.CTkLabel(music_header, text="🎵 MUSIC",
                     font=ctk.CTkFont(size=10, weight="bold"),
                     text_color=GOLD).pack(side="left")

        ctk.CTkButton(music_header, text="📂 Browse", width=65, height=20,
                      font=ctk.CTkFont(size=9),
                      fg_color="transparent", hover_color=BG_INPUT,
                      text_color=TEXT_SECONDARY,
                      command=self._browse_music).pack(side="right")

        self.music_label = ctk.CTkLabel(music_header, text="None",
                                        font=ctk.CTkFont(size=9),
                                        text_color=TEXT_SECONDARY)
        self.music_label.pack(side="right", padx=5)

        self.music_path = ""

        # Volume with % display
        vol_row = ctk.CTkFrame(settings, fg_color="transparent")
        vol_row.pack(fill="x", pady=(4, 0))

        ctk.CTkLabel(vol_row, text="Vol:",
                     font=ctk.CTkFont(size=9),
                     text_color=TEXT_SECONDARY).pack(side="left")

        self.music_vol_var = ctk.DoubleVar(value=0.05)
        ctk.CTkSlider(vol_row, from_=0, to=0.5,
                      variable=self.music_vol_var,
                      width=120, height=14,
                      progress_color=GOLD,
                      fg_color=BORDER,
                      command=self._update_vol_label).pack(side="left", padx=4)

        self.vol_pct_label = ctk.CTkLabel(vol_row, text="5%",
                                           font=ctk.CTkFont(size=10, weight="bold"),
                                           text_color=GOLD)
        self.vol_pct_label.pack(side="left")

        # Fade In
        fade_row = ctk.CTkFrame(settings, fg_color="transparent")
        fade_row.pack(fill="x", pady=(3, 0))

        ctk.CTkLabel(fade_row, text="Fade In:",
                     font=ctk.CTkFont(size=9),
                     text_color=TEXT_SECONDARY).pack(side="left")

        self.fade_in_var = ctk.DoubleVar(value=3.0)
        ctk.CTkSlider(fade_row, from_=0, to=10.0,
                      variable=self.fade_in_var,
                      width=90, height=14,
                      progress_color=GOLD,
                      fg_color=BORDER,
                      command=lambda v: self.fade_in_lbl.configure(text=f"{float(v):.1f}s")).pack(side="left", padx=4)

        self.fade_in_lbl = ctk.CTkLabel(fade_row, text="3.0s",
                                         font=ctk.CTkFont(size=9),
                                         text_color=TEXT_SECONDARY)
        self.fade_in_lbl.pack(side="left")

        # Fade Out
        fade_row2 = ctk.CTkFrame(settings, fg_color="transparent")
        fade_row2.pack(fill="x", pady=(2, 0))

        ctk.CTkLabel(fade_row2, text="Fade Out:",
                     font=ctk.CTkFont(size=9),
                     text_color=TEXT_SECONDARY).pack(side="left")

        self.fade_out_var = ctk.DoubleVar(value=3.0)
        ctk.CTkSlider(fade_row2, from_=0, to=10.0,
                      variable=self.fade_out_var,
                      width=90, height=14,
                      progress_color=GOLD,
                      fg_color=BORDER,
                      command=lambda v: self.fade_out_lbl.configure(text=f"{float(v):.1f}s")).pack(side="left", padx=4)

        self.fade_out_lbl = ctk.CTkLabel(fade_row2, text="3.0s",
                                          font=ctk.CTkFont(size=9),
                                          text_color=TEXT_SECONDARY)
        self.fade_out_lbl.pack(side="left")

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

    def _update_vol_label(self, value):
        pct = int(float(value) * 100)
        self.vol_pct_label.configure(text=f"{pct}%")

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
        # If already running, cancel immediately
        if self.is_running:
            self._cancel_flag = True
            self.is_running = False
            self._set_status("⛔ Cancelled", ACCENT)
            self.progress_bar.set(0)
            self.gen_btn.configure(
                text="⚡ Generate Video", fg_color=ACCENT, hover_color=ACCENT_HOVER)
            return

        text = self.script_input.get("1.0", "end-1c").strip()
        if not text:
            messagebox.showwarning("Warning", "Enter script text")
            return
        if not self.audio_path:
            messagebox.showwarning("Warning", "Select audio file")
            return

        self.is_running = True
        self._cancel_flag = False
        self.gen_btn.configure(text="⏹ Stop", fg_color="#cc3333", hover_color="#ff4444")

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

            if self._cancel_flag:
                raise InterruptedError("Cancelled")

            # Update scenes preview
            self.after(0, lambda: self._update_scenes_display())

            # Step 2: Fetch visuals
            self.after(0, lambda: self._set_status(f"🎨 Fetching visuals for {len(self.scenes)} scenes...", GOLD))
            self.after(0, lambda: self.progress_bar.set(0.3))

            # Determine format
            is_tiktok = "TikTok" in self.format_var.get()
            video_size = (1080, 1920) if is_tiktok else (1920, 1080)
            orientation = "portrait" if is_tiktok else "landscape"

            self.scenes = fetch_visuals_for_scenes(
                self.scenes,
                work_dir=work_dir / "visuals",
                use_ai=self.ai_var.get(),
                prefer_video=self.prefer_video_var.get(),
                orientation=orientation,
            )

            if self._cancel_flag:
                raise InterruptedError("Cancelled")

            # Step 3: Whisper transcription (if subtitles enabled)
            if self.subtitles_var.get():
                self.after(0, lambda: self._set_status("🎤 Transcribing with Whisper...", PURPLE))
                self.after(0, lambda: self.progress_bar.set(0.5))

                # Pre-warm whisper cache so assembler uses cached result
                from subtitle_gen import transcribe_with_timestamps
                transcribe_with_timestamps(self.audio_path)

                if self._cancel_flag:
                    raise InterruptedError("Cancelled")

            # Step 4: Assemble video
            self.after(0, lambda: self._set_status("🎬 Assembling video...", PURPLE))
            self.after(0, lambda: self.progress_bar.set(0.6))

            result = assemble_video(
                scenes=self.scenes,
                audio_path=self.audio_path,
                output_path=output_path,
                add_subtitles=self.subtitles_var.get(),
                add_music=self.music_path or None,
                music_volume=self.music_vol_var.get(),
                music_fade_in=self.fade_in_var.get(),
                music_fade_out=self.fade_out_var.get(),
                video_size=video_size,
                sub_font_path=self._font_options.get(self.sub_font_var.get()),
                sub_font_size=self.sub_size_var.get(),
                sub_y_percent=self.sub_pos_var.get(),
            )

            # Step 4: SRT
            if self.srt_var.get():
                srt_path = Path(output_path).with_suffix(".srt")
                generate_word_level_srt(text, self.audio_path, srt_path)

            self.after(0, lambda: self.progress_bar.set(1.0))
            self.after(0, lambda: self._set_status(f"✅ Done! Saved: {Path(output_path).name}", GREEN))
            self.after(0, lambda: messagebox.showinfo("Done!", f"Video saved:\n{output_path}"))

        except Exception as e:
            if self._cancel_flag:
                self.after(0, lambda: self._set_status("⛔ Cancelled", ACCENT))
            else:
                logger.error("Pipeline error: %s", e, exc_info=True)
                self.after(0, lambda: self._set_status(f"❌ Error: {e}", ACCENT))
                self.after(0, lambda: messagebox.showerror("Error", str(e)))

        finally:
            self.is_running = False
            self._cancel_flag = False
            self.after(0, lambda: self.gen_btn.configure(
                text="⚡ Generate Video", fg_color=ACCENT, hover_color=ACCENT_HOVER))

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
