#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import struct
import time
import tkinter as tk
import tkinter.font as tkfont
from dataclasses import dataclass
from tkinter import filedialog, messagebox, simpledialog
from typing import Optional, List, Tuple, Dict, Any


# =========================
# Config / Constants
# =========================
STRINGS = ["e", "B", "G", "D", "A", "E"]            # 1st -> 6th
TUNING_MIDI = [64, 59, 55, 50, 45, 40]             # E4,B3,G3,D3,A2,E2

PREFIX_W_CH = 4
GAP_BETWEEN_BARS_CH = 2

# UI duration in "16th-units" (1=1/16, 2=1/8, 4=1/4, 8=1/2, 16=1)
DUR_16TH_UNITS = [1, 2, 4, 8, 16]
DUR_LABELS = {1: "1/16", 2: "1/8", 4: "1/4", 8: "1/2", 16: "1"}

TIE_GRAY = "#888888"


# =========================
# Model
# =========================
@dataclass
class Cell:
    kind: str = "empty"  # "empty" | "hold" | "note" | "tie"
    fret: Optional[int] = None


class Measure:
    def __init__(self, steps_per_bar: int = 16):
        self.steps_per_bar = steps_per_bar
        self.grid: List[List[Cell]] = [[Cell() for _ in range(steps_per_bar)] for _ in range(6)]

    def resize(self, new_steps: int):
        old_steps = self.steps_per_bar
        if new_steps == old_steps:
            return

        heads: List[Tuple[int, int, str, Optional[int]]] = []
        for s in range(6):
            for t in range(old_steps):
                c = self.grid[s][t]
                if c.kind in ("note", "tie"):
                    heads.append((s, t, c.kind, c.fret))

        self.steps_per_bar = new_steps
        self.grid = [[Cell() for _ in range(new_steps)] for _ in range(6)]

        for s, t, kind, fret in heads:
            nt = int(round(t * (new_steps / old_steps)))
            nt = max(0, min(new_steps - 1, nt))
            self.grid[s][nt] = Cell(kind=kind, fret=fret)


class TabModel:
    def __init__(self, initial_measures: int = 1):
        self.measures: List[Measure] = [Measure(16) for _ in range(max(1, initial_measures))]

    def ensure_at_least_one(self):
        if not self.measures:
            self.measures.append(Measure(16))


# =========================
# MIDI minimal writer
# =========================
GM_PRESETS = {
    "Guitar (Steel) 26": 25,   # 1-based 26 -> 0-based 25
    "Guitar (Nylon) 25": 24,
    "Guitar (Overdriven) 30": 29,   # GM 1-based 30 -> program 29
    "Guitar (Distortion) 31": 30,   # GM 1-based 31 -> program 30
    "Bass (Finger) 34": 33,
    "Bass (Pick) 35": 34,
    "Synth Bass 1 39": 38,
    "Synth Bass 2 40": 39,
}

def clamp(v, lo, hi):
    return lo if v < lo else hi if v > hi else v

def _varlen(n: int) -> bytes:
    buf = [n & 0x7F]
    n >>= 7
    while n:
        buf.append((n & 0x7F) | 0x80)
        n >>= 7
    return bytes(reversed(buf))


def write_midi_file(path: str, events: List[Tuple[int, bytes]], ppq: int = 480):
    events = sorted(events, key=lambda x: x[0])
    track = bytearray()
    last = 0
    for tick, ev in events:
        dt = tick - last
        last = tick
        track += _varlen(dt) + ev
    track += _varlen(0) + bytes([0xFF, 0x2F, 0x00])  # End of Track

    header = struct.pack(">4sIHHH", b"MThd", 6, 0, 1, ppq)  # format0, 1 track
    track_chunk = struct.pack(">4sI", b"MTrk", len(track)) + track
    with open(path, "wb") as f:
        f.write(header)
        f.write(track_chunk)


# =========================
# MusicXML helpers
# =========================
STEP_NAMES = ["C", "C", "D", "D", "E", "F", "F", "G", "G", "A", "A", "B"]
ALTERS =     [0,  1,  0,  1,  0,  0,  1,  0,  1,  0,  1,  0]


def midi_to_pitch_xml(midi_note: int) -> Tuple[str, Optional[int], int]:
    pc = midi_note % 12
    step = STEP_NAMES[pc]
    alter = ALTERS[pc]
    octave = (midi_note // 12) - 1
    return step, (alter if alter != 0 else None), octave


def xml_escape(s: str) -> str:
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace('"', "&quot;")
             .replace("'", "&apos;"))


# =========================
# App
# =========================
class TabCanvasApp(tk.Tk):
    UNDO_LIMIT = 300
    UNDO_BURST_SEC = 0.75

    def __init__(self):
        super().__init__()

        self.app_base_title = "TAB Canvas — JSON + MIDI + MusicXML"
        self.current_json_path: Optional[str] = None  # ★上書き保存／タイトル用
        self._update_title()
        
        # MIDI instrument / transpose
        self.midi_prog = tk.IntVar(value=25)   # GM Program (0-127). 25=Acoustic Guitar (steel)
        self.transpose_str = tk.StringVar(value="0")  # semitone transpose for export

        self.model = TabModel(initial_measures=1)

        # cursor
        self.cur_measure = 0
        self.cur_string = 0   # 0..5 (1st..6th)
        self.cur_step = 0

        # duration
        self.dur16_var = tk.IntVar(value=1)
        self.dotted_var = tk.BooleanVar(value=False)

        # BPM text-entry
        self.bpm_str = tk.StringVar(value="120")

        # view
        self.compact48_var = tk.BooleanVar(value=True)

        # digit buffer (10+ frets)
        self.digit_buf = ""
        self.digit_after_id = None
        self.digit_timeout_ms = 600

        # selection / multi-measure clipboard
        self.sel_start: Optional[int] = None
        self.sel_end: Optional[int] = None
        self.measures_clip: Optional[Dict[str, Any]] = None
        self.beat_clip: Optional[Dict[str, Any]] = None

        # undo
        self.undo_stack: List[Dict[str, Any]] = []
        self._undoing = False
        self._undo_last_time = 0.0
        self._undo_last_tag: Optional[str] = None

        # fixed-width font + measured positioning
        self.font = tkfont.nametofont("TkFixedFont").copy()
        self.font.configure(size=14)
        self.char_h = self.font.metrics("linespace")

        self._build_menubar()
        self._build_toolbar()

        self.canvas = tk.Canvas(self, background="white", highlightthickness=0)
        self.hsb = tk.Scrollbar(self, orient="horizontal", command=self.canvas.xview)
        self.vsb = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=self.hsb.set, yscrollcommand=self.vsb.set)

        self.canvas.grid(row=2, column=0, sticky="nsew")
        self.vsb.grid(row=2, column=1, sticky="ns")
        self.hsb.grid(row=3, column=0, sticky="ew")

        self.status = tk.Label(self, anchor="w")
        self.status.grid(row=4, column=0, columnspan=2, sticky="ew")

        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.base_items: Dict[str, int] = {}
        self.overlay_items: List[int] = []
        self.rect_items: List[int] = []

        self._bind_keys()
        self.render()

    # -------------------------
    # Title
    # -------------------------
    def _update_title(self):
        if self.current_json_path:
            name = os.path.basename(self.current_json_path)
            self.title(f"{name} — {self.app_base_title}")
        else:
            self.title(self.app_base_title)

    # -------------------------
    # Utility: focus guard (avoid stealing typing from Entry)
    # -------------------------
    def _focus_is_text_input(self) -> bool:
        w = self.focus_get()
        if w is None:
            return False
        return isinstance(w, (tk.Entry, tk.Spinbox, tk.Text))

    # -------------------------
    # BPM parsing
    # -------------------------
    def get_bpm(self) -> int:
        s = self.bpm_str.get().strip()
        try:
            bpm = int(s)
        except Exception:
            bpm = 120
        bpm = max(30, min(300, bpm))
        if str(bpm) != s:
            # normalize display silently
            self.bpm_str.set(str(bpm))
        return bpm

    # -------------------------
    # Undo
    # -------------------------
    def _snapshot(self) -> Dict[str, Any]:
        return {
            "model": self.model_to_dict(),
            "cur_measure": self.cur_measure,
            "cur_string": self.cur_string,
            "cur_step": self.cur_step,
            "sel_start": self.sel_start,
            "sel_end": self.sel_end,
            "dur16": int(self.dur16_var.get()),
            "dotted": bool(self.dotted_var.get()),
            "bpm": self.get_bpm(),
            "compact48": bool(self.compact48_var.get()),
            "current_json_path": self.current_json_path,  # ★追加
        }

    def push_undo(self, tag: str = "edit", burst: bool = False):
        if self._undoing:
            return

        now = time.monotonic()
        if burst and self.undo_stack:
            if self._undo_last_tag == tag and (now - self._undo_last_time) <= self.UNDO_BURST_SEC:
                self._undo_last_time = now
                return

        self.undo_stack.append(self._snapshot())
        if len(self.undo_stack) > self.UNDO_LIMIT:
            self.undo_stack = self.undo_stack[-self.UNDO_LIMIT:]
        self._undo_last_time = now
        self._undo_last_tag = tag

    def undo(self):
        self.commit_digit_buf()
        if not self.undo_stack:
            return
        snap = self.undo_stack.pop()
        self._undoing = True
        try:
            self.dict_to_model(snap["model"], clear_selection=False)
            self.cur_measure = max(0, min(int(snap["cur_measure"]), len(self.model.measures) - 1))
            self.cur_string = max(0, min(int(snap["cur_string"]), 5))
            self.cur_step = max(0, min(int(snap["cur_step"]), self.model.measures[self.cur_measure].steps_per_bar - 1))
            self.sel_start = snap.get("sel_start")
            self.sel_end = snap.get("sel_end")
            self.dur16_var.set(int(snap.get("dur16", 1)))
            self.dotted_var.set(bool(snap.get("dotted", False)))
            self.bpm_str.set(str(int(snap.get("bpm", 120))))
            self.compact48_var.set(bool(snap.get("compact48", True)))
            self.current_json_path = snap.get("current_json_path", None)
            self._update_title()
            self._clear_digit_buf()
        finally:
            self._undoing = False
        self.render()

    # -------------------------
    # Menus / Toolbar
    # -------------------------
    def _build_menubar(self):
        menubar = tk.Menu(self)

        filem = tk.Menu(menubar, tearoff=False)
        filem.add_command(label="New", command=self.new_score, accelerator="Ctrl+Shift+N")
        filem.add_command(label="Open JSON…", command=self.open_json, accelerator="Ctrl+O")
        filem.add_command(label="Save JSON", command=self.save_json, accelerator="Ctrl+S")              # ★上書き可
        filem.add_command(label="Save JSON As…", command=self.save_json_as, accelerator="Ctrl+Shift+S") # ★追加
        filem.add_separator()
        filem.add_command(label="Export MIDI…", command=self.export_midi, accelerator="Ctrl+E")
        filem.add_command(label="Export MusicXML…", command=self.export_musicxml, accelerator="Ctrl+M")
        filem.add_separator()
        filem.add_command(label="Quit", command=self.destroy, accelerator="Ctrl+Q")
        menubar.add_cascade(label="File", menu=filem)

        editm = tk.Menu(menubar, tearoff=False)
        editm.add_command(label="Undo", command=self.undo, accelerator="Ctrl+Z")
        editm.add_separator()
        editm.add_command(label="Mark Selection Start (F7)", command=self.mark_selection_start)
        editm.add_command(label="Mark Selection End (F8)", command=self.mark_selection_end)
        editm.add_command(label="Clear Selection (Esc)", command=self.clear_selection)
        editm.add_command(label="Delete Selected Range", command=self.delete_selected_range, accelerator="Ctrl+Shift+Delete")
        editm.add_separator()
        editm.add_command(label="Copy (Selection or Measure)", command=self.copy_measures, accelerator="Ctrl+C")
        editm.add_command(label="Paste Overwrite", command=self.paste_measures_overwrite, accelerator="Ctrl+V")
        editm.add_command(label="Paste Insert", command=self.paste_measures_insert, accelerator="Ctrl+Shift+V")
        editm.add_separator()
        editm.add_command(label="Copy Beat", command=self.copy_beat, accelerator="Ctrl+Alt+C")
        editm.add_command(label="Paste Beat (Overwrite)", command=self.paste_beat_overwrite, accelerator="Ctrl+Alt+V")
        editm.add_separator()
        editm.add_command(label="Tie Back (current -> previous)", command=self.tie_back, accelerator="Ctrl+Shift+T")
        editm.add_separator()
        editm.add_command(label="Duplicate (Insert at cursor)", command=self.duplicate_here, accelerator="Ctrl+D")
        editm.add_command(label="Repeat… (Insert at cursor)", command=self.repeat_dialog_here, accelerator="Ctrl+Shift+D")
        editm.add_separator()
        editm.add_command(label="Insert Blank Measure (before)", command=self.insert_blank_measure, accelerator="Ctrl+I")
        editm.add_command(label="Append Blank Measure (end)", command=self.append_blank_measure, accelerator="Ctrl+Shift+I")
        editm.add_command(label="Delete Measure", command=self.delete_current_measure, accelerator="Ctrl+Delete")
        menubar.add_cascade(label="Edit", menu=editm)

        resm = tk.Menu(menubar, tearoff=False)
        resm.add_command(label="Set current measure = 16 steps", command=lambda: self.set_measure_resolution(16))
        resm.add_command(label="Set current measure = 48 steps", command=lambda: self.set_measure_resolution(48))
        menubar.add_cascade(label="Resolution", menu=resm)

        viewm = tk.Menu(menubar, tearoff=False)
        viewm.add_checkbutton(label="Compact 48 (subslot)", variable=self.compact48_var, command=self.render)
        menubar.add_cascade(label="View", menu=viewm)

        self.config(menu=menubar)

        # global accelerators
        self.bind_all("<Control-q>", lambda e: self.destroy())
        self.bind_all("<Control-Shift-N>", lambda e: self.new_score())
        self.bind_all("<Control-o>", lambda e: self.open_json())
        self.bind_all("<Control-s>", lambda e: self.save_json())
        self.bind_all("<Control-Shift-S>", lambda e: self.save_json_as())
        self.bind_all("<Control-e>", lambda e: self.export_midi())
        self.bind_all("<Control-m>", lambda e: self.export_musicxml())

        self.bind_all("<Control-z>", lambda e: self.undo())

        self.bind_all("<Control-c>", lambda e: self.copy_measures())
        self.bind_all("<Control-v>", lambda e: self.paste_measures_overwrite())
        self.bind_all("<Control-Shift-V>", lambda e: self.paste_measures_insert())
        self.bind_all("<Control-Alt-c>", lambda e: self.copy_beat())
        self.bind_all("<Control-Alt-v>", lambda e: self.paste_beat_overwrite())
        self.bind_all("<Control-Shift-t>", lambda e: self.tie_back())

        self.bind_all("<Control-d>", lambda e: self.duplicate_here())
        self.bind_all("<Control-Shift-D>", lambda e: self.repeat_dialog_here())

        self.bind_all("<F7>", lambda e: self.mark_selection_start())
        self.bind_all("<F8>", lambda e: self.mark_selection_end())
        self.bind_all("<Escape>", lambda e: self.clear_selection())
        self.bind_all("<Control-Shift-Delete>", lambda e: self.delete_selected_range())

        self.bind_all("<Control-i>", lambda e: self.insert_blank_measure())
        self.bind_all("<Control-Shift-I>", lambda e: self.append_blank_measure())
        self.bind_all("<Control-Delete>", lambda e: self.delete_current_measure())

    def _build_toolbar(self):
        tb = tk.Frame(self)
        tb.grid(row=0, column=0, columnspan=2, sticky="ew")

        tk.Label(tb, text="Len:").pack(side="left", padx=(6, 2), pady=4)
        for d in DUR_16TH_UNITS:
            tk.Radiobutton(
                tb, text=DUR_LABELS.get(d, str(d)),
                value=d, variable=self.dur16_var,
                indicatoron=0, padx=10, pady=2,
                command=self.render
            ).pack(side="left", padx=2, pady=4)

        tk.Checkbutton(
            tb, text=" . ", variable=self.dotted_var,
            indicatoron=0, padx=8, pady=2, command=self.render
        ).pack(side="left", padx=(8, 2), pady=4)

        tk.Label(tb, text="BPM:").pack(side="left", padx=(14, 2), pady=4)
        bpm_entry = tk.Entry(tb, textvariable=self.bpm_str, width=6)
        bpm_entry.pack(side="left", padx=2, pady=4)
        bpm_entry.bind("<FocusOut>", lambda e: self.render())
        bpm_entry.bind("<Return>", lambda e: (self.focus_set(), self.render()))

        tk.Checkbutton(
            tb, text="Compact48", variable=self.compact48_var,
            indicatoron=0, padx=8, pady=2, command=self.render
        ).pack(side="left", padx=(16, 2), pady=4)

        # --- MIDI Inst preset ---
        tk.Label(tb, text="MIDI:").pack(side="left", padx=(14, 2), pady=4)

        tk.Button(tb, text="+Bar(end)", command=self.append_blank_measure).pack(side="left", padx=(16, 2), pady=4)
        tk.Button(tb, text="Undo", command=self.undo).pack(side="left", padx=2, pady=4)

        tk.Label(tb, text="  (Ctrl+Shift+T: tie-back, Ctrl+Shift+Del: delete range)").pack(side="left", padx=8, pady=4)

        
        self.midi_preset_str = tk.StringVar(value="Guitar (Steel) 26")
        def apply_preset(_=None):
            name = self.midi_preset_str.get()
            prog = GM_PRESETS.get(name, 25)
            self.midi_prog.set(int(prog))
            # ついでにベース時は -12 をセット、ギター時は 0 に（好みで）
            if "Bass" in name:
                self.transpose_str.set("-12")
            else:
                self.transpose_str.set("0")
        
        preset_menu = tk.OptionMenu(tb, self.midi_preset_str, *GM_PRESETS.keys(), command=apply_preset)
        preset_menu.pack(side="left", padx=2, pady=4)
        
        # manual program number
        tk.Label(tb, text="Prog").pack(side="left", padx=(8, 2), pady=4)
        prog_entry = tk.Entry(tb, width=4)
        prog_entry.insert(0, str(self.midi_prog.get()))
        prog_entry.pack(side="left", padx=2, pady=4)
        
        def sync_prog_from_entry(_=None):
            try:
                v = int(prog_entry.get().strip())
            except Exception:
                v = self.midi_prog.get()
            v = clamp(v, 0, 127)
            self.midi_prog.set(v)
            prog_entry.delete(0, "end")
            prog_entry.insert(0, str(v))
        
        prog_entry.bind("<FocusOut>", sync_prog_from_entry)
        prog_entry.bind("<Return>", lambda e: (sync_prog_from_entry(), self.focus_set(), self.render()))
        
        # transpose
        tk.Label(tb, text="Tr").pack(side="left", padx=(8, 2), pady=4)
        tr_entry = tk.Entry(tb, textvariable=self.transpose_str, width=4)
        tr_entry.pack(side="left", padx=2, pady=4)
        tr_entry.bind("<FocusOut>", lambda e: self.render())
        tr_entry.bind("<Return>", lambda e: (self.focus_set(), self.render()))
        
        # preset buttons（クリック一発で“確認モード”切替）
        tk.Button(tb, text="GTR", command=lambda: (self.midi_preset_str.set("Guitar (Steel) 26"), apply_preset())).pack(side="left", padx=(10, 2), pady=4)
        tk.Button(tb, text="BASS", command=lambda: (self.midi_preset_str.set("Bass (Finger) 34"), apply_preset())).pack(side="left", padx=2, pady=4)
        
        # 初期反映
        apply_preset()
        



    def _bind_keys(self):
        # navigation
        self.bind("<Left>", lambda e: self.move_step(-1))
        self.bind("<Right>", lambda e: self.move_step(+1))
        self.bind("<Up>", lambda e: self.move_string(-1))
        self.bind("<Down>", lambda e: self.move_string(+1))

        self.bind("<Prior>", lambda e: self.move_measure(-1))  # PageUp
        self.bind("<Next>", lambda e: self.move_measure(+1))   # PageDown
        self.bind("<Home>", lambda e: self.jump_to_step(0))
        self.bind("<End>", lambda e: self.jump_to_step(self.model.measures[self.cur_measure].steps_per_bar - 1))

        # digits (fret input)
        for d in "0123456789":
            self.bind(f"<KP_{d}>", self.on_digit)   # numpad support

        self.bind("<space>", lambda e: self.on_space())
        self.bind("<Return>", lambda e: self.commit_digit_buf())

        # toggles
        self.bind("d", lambda e: self.toggle_dotted())
        self.bind("t", lambda e: self.toggle_compact48())

    def toggle_compact48(self):
        self.commit_digit_buf()
        self.compact48_var.set(not self.compact48_var.get())
        self.render()

    # -------------------------
    # Selection helpers
    # -------------------------
    def _selection_norm(self) -> Optional[Tuple[int, int]]:
        if self.sel_start is None or self.sel_end is None:
            return None
        a = max(0, min(self.sel_start, self.sel_end))
        b = min(len(self.model.measures) - 1, max(self.sel_start, self.sel_end))
        if a > b:
            return None
        return (a, b)

    def mark_selection_start(self):
        self.commit_digit_buf()
        self.sel_start = self.cur_measure
        if self.sel_end is None:
            self.sel_end = self.cur_measure
        self.render()

    def mark_selection_end(self):
        self.commit_digit_buf()
        self.sel_end = self.cur_measure
        if self.sel_start is None:
            self.sel_start = self.cur_measure
        self.render()

    def clear_selection(self):
        self.commit_digit_buf()
        self.sel_start = None
        self.sel_end = None
        self.render()

    def delete_selected_range(self):
        """選択範囲があればその小節範囲を削除。なければ何もしない"""
        self.commit_digit_buf()
        sel = self._selection_norm()
        if sel is None:
            return

        a, b = sel
        self.push_undo(tag="range", burst=False)

        del self.model.measures[a:b+1]
        self.model.ensure_at_least_one()

        self.cur_measure = min(a, len(self.model.measures) - 1)
        self.cur_step = min(self.cur_step, self.model.measures[self.cur_measure].steps_per_bar - 1)

        self.sel_start = None
        self.sel_end = None
        self.render()

    # -------------------------
    # Measure insert/delete/append
    # -------------------------
    def insert_blank_measure(self):
        self.commit_digit_buf()
        self.push_undo(tag="range", burst=False)

        idx = max(0, min(self.cur_measure, len(self.model.measures)))
        spb = self.model.measures[self.cur_measure].steps_per_bar if self.model.measures else 16
        self.model.measures.insert(idx, Measure(spb))
        self.cur_measure = idx
        self.cur_step = min(self.cur_step, self.model.measures[self.cur_measure].steps_per_bar - 1)

        if self.sel_start is not None and self.sel_start >= idx:
            self.sel_start += 1
        if self.sel_end is not None and self.sel_end >= idx:
            self.sel_end += 1

        self.render()

    def append_blank_measure(self):
        self.commit_digit_buf()
        self.push_undo(tag="range", burst=False)

        spb = self.model.measures[-1].steps_per_bar if self.model.measures else 16
        self.model.measures.append(Measure(spb))
        self.cur_measure = max(0, min(self.cur_measure, len(self.model.measures) - 1))
        self.cur_step = min(self.cur_step, self.model.measures[self.cur_measure].steps_per_bar - 1)
        self.render()

    def delete_current_measure(self):
        self.commit_digit_buf()
        self.push_undo(tag="range", burst=False)

        if len(self.model.measures) <= 1:
            spb = self.model.measures[0].steps_per_bar
            self.model.measures[0] = Measure(spb)
            self.cur_measure = 0
            self.cur_step = 0
            self.sel_start = None
            self.sel_end = None
            self.render()
            return

        idx = self.cur_measure
        del self.model.measures[idx]
        self.cur_measure = max(0, min(idx, len(self.model.measures) - 1))
        self.cur_step = min(self.cur_step, self.model.measures[self.cur_measure].steps_per_bar - 1)

        if self.sel_start is not None:
            if self.sel_start == idx:
                self.sel_start = None
            elif self.sel_start > idx:
                self.sel_start -= 1
        if self.sel_end is not None:
            if self.sel_end == idx:
                self.sel_end = None
            elif self.sel_end > idx:
                self.sel_end -= 1
        if self.sel_start is None or self.sel_end is None:
            self.sel_start = None
            self.sel_end = None

        self.render()

    # -------------------------
    # Clipboard helpers (multi measure)
    # -------------------------
    def _measure_to_dict(self, m: Measure) -> dict:
        return {
            "steps_per_bar": m.steps_per_bar,
            "grid": [[{"kind": c.kind, "fret": c.fret} for c in row] for row in m.grid],
        }

    def _dict_to_measure(self, d: dict) -> Measure:
        spb = int(d.get("steps_per_bar", 16))
        m = Measure(spb)
        grid = d.get("grid", [])
        for s in range(min(6, len(grid))):
            row = grid[s]
            for t in range(min(spb, len(row))):
                c = row[t]
                m.grid[s][t] = Cell(kind=c.get("kind", "empty"), fret=c.get("fret", None))
        return m

    def _get_clip_payload(self) -> Optional[dict]:
        if self.measures_clip is not None:
            return self.measures_clip
        try:
            s = self.clipboard_get()
            d = json.loads(s)
            if isinstance(d, dict) and "measures" in d:
                self.measures_clip = d
                return d
            if isinstance(d, dict) and "grid" in d and "steps_per_bar" in d:
                payload = {"version": 1, "measures": [d]}
                self.measures_clip = payload
                return payload
        except Exception:
            return None
        return None

    def copy_measures(self):
        self.commit_digit_buf()
        sel = self._selection_norm()
        if sel is None:
            a = b = self.cur_measure
        else:
            a, b = sel

        measures = [self._measure_to_dict(self.model.measures[i]) for i in range(a, b + 1)]
        payload = {"version": 1, "measures": measures}
        self.measures_clip = payload
        try:
            self.clipboard_clear()
            self.clipboard_append(json.dumps(payload, ensure_ascii=False))
        except Exception:
            pass
        self.render()

    def paste_measures_overwrite(self):
        self.commit_digit_buf()
        payload = self._get_clip_payload()
        if payload is None:
            messagebox.showinfo("Paste", "No copied measures found.")
            return
        measures_data = payload.get("measures", [])
        if not measures_data:
            messagebox.showinfo("Paste", "Clipboard has no measures.")
            return

        self.push_undo(tag="range", burst=False)

        idx = max(0, min(self.cur_measure, len(self.model.measures)))
        new_measures = [self._dict_to_measure(md) for md in measures_data]

        for k, nm in enumerate(new_measures):
            pos = idx + k
            if pos < len(self.model.measures):
                self.model.measures[pos] = nm
            else:
                self.model.measures.append(nm)

        self.cur_measure = min(idx, len(self.model.measures) - 1)
        self.cur_step = min(self.cur_step, self.model.measures[self.cur_measure].steps_per_bar - 1)
        self.render()

    def paste_measures_insert(self):
        self.commit_digit_buf()
        payload = self._get_clip_payload()
        if payload is None:
            messagebox.showinfo("Insert", "No copied measures found.")
            return
        measures_data = payload.get("measures", [])
        if not measures_data:
            messagebox.showinfo("Insert", "Clipboard has no measures.")
            return

        self.push_undo(tag="range", burst=False)

        idx = max(0, min(self.cur_measure, len(self.model.measures)))
        new_measures = [self._dict_to_measure(md) for md in measures_data]
        for k, nm in enumerate(new_measures):
            self.model.measures.insert(idx + k, nm)

        self.cur_measure = idx
        self.cur_step = min(self.cur_step, self.model.measures[self.cur_measure].steps_per_bar - 1)

        # selectionは自動でずらさない（混乱防止）
        self.render()

    # -------------------------
    # Beat copy/paste
    # -------------------------
    def _beat_steps(self, spb: int) -> int:
        if spb == 16:
            return 4
        if spb == 48:
            return 12
        return max(1, spb // 4)

    def _beat_bounds(self, mi: int, step: int) -> Tuple[int, int, int]:
        m = self.model.measures[mi]
        spb = m.steps_per_bar
        bs = self._beat_steps(spb)
        bi = max(0, min((spb - 1) // bs, step // bs))
        st = bi * bs
        ed = min(spb, st + bs)
        return bi, st, ed

    def copy_beat(self):
        self.commit_digit_buf()
        mi = self.cur_measure
        m = self.model.measures[mi]
        _bi, st, ed = self._beat_bounds(mi, self.cur_step)
        bs = ed - st

        grid = []
        for s in range(6):
            row = []
            for t in range(st, ed):
                c = m.grid[s][t]
                row.append({"kind": c.kind, "fret": c.fret})
            grid.append(row)

        payload = {"version": 1, "spb": m.steps_per_bar, "beat_steps": bs, "grid": grid}
        self.beat_clip = payload

        try:
            self.clipboard_clear()
            self.clipboard_append(json.dumps({"type": "beat", **payload}, ensure_ascii=False))
        except Exception:
            pass

        self.render()

    def _get_beat_clip(self) -> Optional[dict]:
        if self.beat_clip is not None:
            return self.beat_clip
        try:
            s = self.clipboard_get()
            d = json.loads(s)
            if isinstance(d, dict) and d.get("type") == "beat" and "grid" in d:
                d.pop("type", None)
                self.beat_clip = d
                return d
        except Exception:
            return None
        return None

    def paste_beat_overwrite(self):
        self.commit_digit_buf()
        clip = self._get_beat_clip()
        if clip is None:
            messagebox.showinfo("Paste Beat", "No copied beat found.")
            return

        self.push_undo(tag="edit", burst=False)

        mi = self.cur_measure
        m = self.model.measures[mi]
        _bi, st, ed = self._beat_bounds(mi, self.cur_step)
        bs_dst = ed - st

        grid = clip.get("grid", [])
        if not grid or len(grid) != 6:
            messagebox.showinfo("Paste Beat", "Clipboard beat data is invalid.")
            return

        bs_src = int(clip.get("beat_steps", len(grid[0]) if grid and grid[0] else 0))
        bs = min(bs_dst, bs_src)

        for s in range(6):
            for t in range(st, ed):
                m.grid[s][t] = Cell()

            prev_ok = False
            if st > 0:
                prev_ok = (m.grid[s][st - 1].kind in ("note", "tie", "hold"))

            row = grid[s]
            for i in range(bs):
                src = row[i] if i < len(row) else {"kind": "empty", "fret": None}
                kind = src.get("kind", "empty")
                fret = src.get("fret", None)

                if kind == "tie" and (st + i) != 0:
                    kind = "note"

                if not prev_ok and kind == "hold":
                    kind = "empty"
                    fret = None

                m.grid[s][st + i] = Cell(kind=kind, fret=fret)

        self.render()

    # -------------------------
    # Tie back (make current note a "tie" to previous note)
    # -------------------------
    def _pos_prev(self, mi: int, step: int) -> Optional[Tuple[int, int]]:
        if mi < 0 or mi >= len(self.model.measures):
            return None
        if step > 0:
            return (mi, step - 1)
        if mi == 0:
            return None
        pm = self.model.measures[mi - 1]
        return (mi - 1, pm.steps_per_bar - 1)

    def _pos_next(self, mi: int, step: int) -> Optional[Tuple[int, int]]:
        if mi < 0 or mi >= len(self.model.measures):
            return None
        m = self.model.measures[mi]
        if step + 1 < m.steps_per_bar:
            return (mi, step + 1)
        if mi + 1 >= len(self.model.measures):
            return None
        return (mi + 1, 0)

    def _note_end_pos(self, mi: int, s: int, head_step: int) -> Optional[Tuple[int, int]]:
        """Return (mi_end, step_end) where the note ends (first position after the note)."""
        if not (0 <= mi < len(self.model.measures)):
            return None
        m = self.model.measures[mi]
        c = m.grid[s][head_step]
        if c.kind not in ("note", "tie") or c.fret is None:
            return None
        fret = c.fret

        # consume holds in same measure
        cur_mi, cur_step = mi, head_step
        nxt = self._pos_next(cur_mi, cur_step)
        while nxt is not None:
            nmi, ns = nxt
            nm = self.model.measures[nmi]
            if nmi == cur_mi and nm.grid[s][ns].kind == "hold":
                cur_step = ns
                nxt = self._pos_next(cur_mi, cur_step)
                continue
            break

        end_pos = self._pos_next(cur_mi, cur_step)
        if end_pos is None:
            return None

        # follow tie chain forward if the next position is exactly a tie head of same fret at step 0
        while True:
            nmi, ns = end_pos
            if not (0 <= nmi < len(self.model.measures)):
                return end_pos
            nm = self.model.measures[nmi]
            if ns == 0:
                head = nm.grid[s][0]
                if head.kind == "tie" and head.fret == fret:
                    # consume holds after tie head
                    cur_mi, cur_step = nmi, 0
                    nxt2 = self._pos_next(cur_mi, cur_step)
                    while nxt2 is not None:
                        nmi2, ns2 = nxt2
                        if nmi2 == cur_mi and self.model.measures[nmi2].grid[s][ns2].kind == "hold":
                            cur_step = ns2
                            nxt2 = self._pos_next(cur_mi, cur_step)
                            continue
                        break
                    end_pos = self._pos_next(cur_mi, cur_step)
                    if end_pos is None:
                        return None
                    continue
            return end_pos

    def tie_back(self):
        """
        カーソル位置の note を tie に変換して、直前の同フレット音とタイ接続させる。
        """
        self.commit_digit_buf()

        mi = self.cur_measure
        s = self.cur_string
        t = self.cur_step
        m = self.model.measures[mi]
        cur = m.grid[s][t]
        if cur.kind not in ("note", "tie") or cur.fret is None:
            return

        # current is already tie -> toggle back to note (undoable)
        if cur.kind == "tie":
            self.push_undo(tag="edit", burst=False)
            m.grid[s][t] = Cell(kind="note", fret=cur.fret)
            self.render()
            return

        fret = cur.fret

        # search previous head of same fret on same string
        p = self._pos_prev(mi, t)
        prev_head = None
        while p is not None:
            pmi, ps = p
            pm = self.model.measures[pmi]
            c = pm.grid[s][ps]
            if c.kind in ("note", "tie") and c.fret == fret:
                prev_head = (pmi, ps)
                break
            p = self._pos_prev(pmi, ps)

        if prev_head is None:
            return

        # check previous ends exactly at current position
        endp = self._note_end_pos(prev_head[0], s, prev_head[1])
        if endp != (mi, t):
            return

        # ok: convert current head to tie
        self.push_undo(tag="edit", burst=False)
        m.grid[s][t] = Cell(kind="tie", fret=fret)
        self.render()

    # -------------------------
    # Duplicate / Repeat (destination = cursor)
    # -------------------------
    def _source_range_for_block(self) -> Tuple[int, int]:
        sel = self._selection_norm()
        if sel is None:
            return (self.cur_measure, self.cur_measure)
        return sel

    def duplicate_here(self):
        self.commit_digit_buf()
        a, b = self._source_range_for_block()
        block = [self._measure_to_dict(self.model.measures[i]) for i in range(a, b + 1)]

        self.push_undo(tag="range", burst=False)

        idx = max(0, min(self.cur_measure, len(self.model.measures)))
        clones = [self._dict_to_measure(md) for md in block]
        for k, mm in enumerate(clones):
            self.model.measures.insert(idx + k, mm)

        self.cur_measure = idx
        self.cur_step = min(self.cur_step, self.model.measures[self.cur_measure].steps_per_bar - 1)
        self.sel_start = idx
        self.sel_end = idx + len(clones) - 1
        self.render()

    def repeat_dialog_here(self):
        self.commit_digit_buf()
        n = simpledialog.askinteger("Repeat", "How many times to repeat?", minvalue=1, maxvalue=999)
        if not n:
            return
        self.repeat_here(n)

    def repeat_here(self, times: int):
        a, b = self._source_range_for_block()
        block = [self._measure_to_dict(self.model.measures[i]) for i in range(a, b + 1)]
        block_len = len(block)

        self.push_undo(tag="range", burst=False)

        idx = max(0, min(self.cur_measure, len(self.model.measures)))
        for rep in range(times):
            clones = [self._dict_to_measure(md) for md in block]
            for k, mm in enumerate(clones):
                self.model.measures.insert(idx + rep * block_len + k, mm)

        self.cur_measure = idx
        self.cur_step = min(self.cur_step, self.model.measures[self.cur_measure].steps_per_bar - 1)
        self.sel_start = idx
        self.sel_end = idx + times * block_len - 1
        self.render()

    # -------------------------
    # JSON
    # -------------------------
    def model_to_dict(self) -> dict:
        measures = []
        for m in self.model.measures:
            measures.append({
                "steps_per_bar": m.steps_per_bar,
                "grid": [[{"kind": c.kind, "fret": c.fret} for c in row] for row in m.grid]
            })
    
        return {
            "version": 1,
            "tuning_midi": TUNING_MIDI,
            "measures": measures,
            "meta": {
                "bpm": self.get_bpm(),
                "midi_prog": int(self.midi_prog.get()),
                "transpose": self.transpose_str.get().strip(),
                "midi_preset": getattr(self, "midi_preset_str", tk.StringVar(value="")).get(),
            }
        }

    def dict_to_model(self, d: dict, clear_selection: bool = True):
        measures_data = d.get("measures", [])
        self.model = TabModel(initial_measures=0)
        self.model.measures = []
        for md in measures_data:
            spb = int(md.get("steps_per_bar", 16))
            m = Measure(spb)
            grid = md.get("grid", [])
            for s in range(min(6, len(grid))):
                row = grid[s]
                for t in range(min(spb, len(row))):
                    c = row[t]
                    m.grid[s][t] = Cell(kind=c.get("kind", "empty"), fret=c.get("fret", None))
            self.model.measures.append(m)
        self.model.ensure_at_least_one()
        self.cur_measure = max(0, min(self.cur_measure, len(self.model.measures) - 1))
        self.cur_string = max(0, min(self.cur_string, 5))
        self.cur_step = max(0, min(self.cur_step, self.model.measures[self.cur_measure].steps_per_bar - 1))
        if clear_selection:
            self.sel_start = None
            self.sel_end = None
        meta = d.get("meta", {}) if isinstance(d, dict) else {}
        if isinstance(meta, dict):
            if "bpm" in meta:
                try:
                    self.bpm_str.set(str(int(meta["bpm"])))
                except Exception:
                    self.bpm_str.set("120")
        
            if "midi_prog" in meta:
                try:
                    self.midi_prog.set(max(0, min(127, int(meta["midi_prog"]))))
                except Exception:
                    pass
        
            if "transpose" in meta:
                self.transpose_str.set(str(meta["transpose"]))


        # meta = d.get("meta", {}) if isinstance(d, dict) else {}
        # if "midi_prog" in meta:
        #     self.midi_prog.set(clamp(int(meta.get("midi_prog", 25)), 0, 127))
        # if "transpose" in meta:
        #     self.transpose_str.set(str(meta.get("transpose", "0")))
        # if hasattr(self, "midi_preset_str") and "midi_preset" in meta:
        #     name = meta.get("midi_preset")
        #     if name in GM_PRESETS:
        #         self.midi_preset_str.set(name)
        #         # apply_preset がスコープ問題になるなら、復元後に手動で prog/transpose を優先でOK

    def save_json_as(self):
        self.commit_digit_buf()
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.model_to_dict(), f, ensure_ascii=False, indent=2)
            self.current_json_path = path
            self._update_title()
        except Exception as e:
            messagebox.showerror("Save failed", str(e))

    def save_json(self):
        """上書き保存：既存パスが無ければ Save As"""
        self.commit_digit_buf()
        if not self.current_json_path:
            self.save_json_as()
            return
        try:
            with open(self.current_json_path, "w", encoding="utf-8") as f:
                json.dump(self.model_to_dict(), f, ensure_ascii=False, indent=2)
            self._update_title()
        except Exception as e:
            messagebox.showerror("Save failed", str(e))

    def open_json(self):
        self.commit_digit_buf()
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                d = json.load(f)
            self.push_undo(tag="range", burst=False)
            self.dict_to_model(d)

            # ★要望：開いたら最後の小節へ移動
            self.cur_measure = len(self.model.measures) - 1
            self.cur_step = 0
            self.cur_string = 0

            self.current_json_path = path
            self._update_title()

            self.render()
        except Exception as e:
            messagebox.showerror("Open failed", str(e))

    # -------------------------
    # MIDI export
    # -------------------------
    def export_midi(self):
        self.commit_digit_buf()
        path = filedialog.asksaveasfilename(defaultextension=".mid", filetypes=[("MIDI", "*.mid")])
        if not path:
            return

        bpm = self.get_bpm()
        mpqn = int(60_000_000 / max(1, bpm))
        ppq = 480
        ticks_per_measure = ppq * 4

        events: List[Tuple[int, bytes]] = []
        events.append((0, bytes([0xFF, 0x51, 0x03]) + mpqn.to_bytes(3, "big")))
        # events.append((0, bytes([0xC0, 25])))  # steel guitar-ish
        # Program change
        prog = clamp(int(self.midi_prog.get()), 0, 127)
        events.append((0, bytes([0xC0, prog])))

        for mi, m in enumerate(self.model.measures):
            step_tick = ticks_per_measure / m.steps_per_bar
            for s in range(6):
                for st in range(m.steps_per_bar):
                    c = m.grid[s][st]
                    if c.kind != "note" or c.fret is None:
                        continue
                    pitch = TUNING_MIDI[s] + int(c.fret)
                    start_tick = int(round(mi * ticks_per_measure + st * step_tick))
                    dur_steps = self._calc_note_total_steps(mi, s, st)
                    end_tick = self._calc_end_tick(mi, st, dur_steps, ticks_per_measure)
                    events.append((start_tick, bytes([0x90, pitch & 0x7F, 100])))
                    events.append((end_tick, bytes([0x80, pitch & 0x7F, 0])))

        try:
            write_midi_file(path, events, ppq=ppq)
        except Exception as e:
            messagebox.showerror("MIDI export failed", str(e))

    def _calc_note_total_steps(self, mi: int, s: int, st: int) -> int:
        m = self.model.measures[mi]
        fret = m.grid[s][st].fret
        steps = 1
        t = st + 1
        while t < m.steps_per_bar and m.grid[s][t].kind == "hold":
            steps += 1
            t += 1

        nmi = mi + 1
        while nmi < len(self.model.measures):
            nm = self.model.measures[nmi]
            head = nm.grid[s][0]
            if head.kind == "tie" and head.fret == fret:
                steps += 1
                t2 = 1
                while t2 < nm.steps_per_bar and nm.grid[s][t2].kind == "hold":
                    steps += 1
                    t2 += 1
                nmi += 1
                continue
            break
        return steps

    def _calc_end_tick(self, start_mi: int, start_step: int, dur_steps: int, ticks_per_measure: int) -> int:
        mi = start_mi
        step = start_step
        remaining = dur_steps  # ★ここを dur_steps-1 から変更
    
        while remaining > 0 and mi < len(self.model.measures):
            m = self.model.measures[mi]
            step += 1
            if step >= m.steps_per_bar:
                mi += 1
                step = 0
                continue
            remaining -= 1
    
        if mi >= len(self.model.measures):
            return len(self.model.measures) * ticks_per_measure
    
        m = self.model.measures[mi]
        step_tick = ticks_per_measure / m.steps_per_bar
        return int(round(mi * ticks_per_measure + step * step_tick))


    # def _calc_end_tick(self, start_mi: int, start_step: int, dur_steps: int, ticks_per_measure: int) -> int:
    #     mi = start_mi
    #     step = start_step
    #     remaining = dur_steps - 1
    #     while remaining > 0 and mi < len(self.model.measures):
    #         m = self.model.measures[mi]
    #         step += 1
    #         if step >= m.steps_per_bar:
    #             mi += 1
    #             step = 0
    #             continue
    #         remaining -= 1
    #     if mi >= len(self.model.measures):
    #         return len(self.model.measures) * ticks_per_measure
    #     m = self.model.measures[mi]
    #     step_tick = ticks_per_measure / m.steps_per_bar
    #     return int(round(mi * ticks_per_measure + step * step_tick))

    # -------------------------
    # MusicXML export (dur split for MuseScore3)
    # -------------------------
    def export_musicxml(self):
        self.commit_digit_buf()
        path = filedialog.asksaveasfilename(
            defaultextension=".musicxml",
            filetypes=[("MusicXML", "*.musicxml"), ("XML", "*.xml")]
        )
        if not path:
            return
    
        # Keep your current convention
        divisions = 12                  # quarter = 12
        measure_div_len = divisions * 4 # 4/4 => 48
    
        title = "TAB Export"
        xml: List[str] = []
        xml.append('<?xml version="1.0" encoding="UTF-8" standalone="no"?>')
        xml.append('<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 3.1 Partwise//EN" '
                   '"http://www.musicxml.org/dtds/partwise.dtd">')
        xml.append('<score-partwise version="3.1">')
        xml.append(f'  <work><work-title>{xml_escape(title)}</work-title></work>')
    
        # 2 parts
        xml.append('  <part-list>')
        xml.append('    <score-part id="P1"><part-name>Guitar</part-name></score-part>')
        xml.append('    <score-part id="P2"><part-name>Guitar TAB</part-name></score-part>')
        xml.append('  </part-list>')
    
        # MuseScore3-friendly "simple" durations.  (We also allow fallback for dur<3)
        CAND = [
            (48, "whole", 0),
            (36, "half", 1),
            (24, "half", 0),
            (18, "quarter", 1),
            (12, "quarter", 0),
            (9,  "eighth", 1),
            (6,  "eighth", 0),
            (3,  "16th", 0),
        ]
    
        def split_duration_div(dur_div: int) -> List[Tuple[int, Optional[str], int]]:
            """
            Return list of (duration, type_or_None, dots).
            If dur_div is not representable by CAND (e.g., 1 or 2), we emit a single chunk with type=None.
            """
            out: List[Tuple[int, Optional[str], int]] = []
            remain = int(dur_div)
            while remain > 0:
                found = False
                for d, typ, dots in CAND:
                    if d <= remain:
                        out.append((d, typ, dots))
                        remain -= d
                        found = True
                        break
                if not found:
                    # Unrepresentable with our candidates (typically 1 or 2)
                    out.append((remain, None, 0))
                    break
            return out
    
        def emit_forward(dur_div: int):
            """Advance time without creating visible rests."""
            dur_div = int(dur_div)
            if dur_div <= 0:
                return
            xml.append('    <forward>')
            xml.append(f'      <duration>{dur_div}</duration>')
            xml.append('    </forward>')
    
        def emit_note(pitch_midi: int, dur_div: int, voice: int,
                      tie_stop: bool, tie_start: bool,
                      add_technical: bool, string_no: int, fret: int,
                      is_chord: bool = False):
            """
            add_technical=True => add <technical><string><fret> (TAB part)
            is_chord=True      => emit <chord/> (2nd note+ at same onset)
            """
            parts = split_duration_div(dur_div)
            n = len(parts)
    
            for i, (d, typ, dots) in enumerate(parts):
                internal_start = (i < n - 1)
                internal_stop = (i > 0)
    
                ts = tie_stop or internal_stop
                te = tie_start or internal_start
    
                step, alter, octave = midi_to_pitch_xml(pitch_midi)
    
                xml.append('    <note>')
                if is_chord:
                    xml.append('      <chord/>')
                xml.append('      <pitch>')
                xml.append(f'        <step>{step}</step>')
                if alter is not None:
                    xml.append(f'        <alter>{alter}</alter>')
                xml.append(f'        <octave>{octave}</octave>')
                xml.append('      </pitch>')
                xml.append(f'      <duration>{int(d)}</duration>')
                xml.append(f'      <voice>{voice}</voice>')
                xml.append('      <staff>1</staff>')
                if typ is not None:
                    xml.append(f'      <type>{typ}</type>')
                    for _ in range(dots):
                        xml.append('      <dot/>')
    
                if ts:
                    xml.append('      <tie type="stop"/>')
                if te:
                    xml.append('      <tie type="start"/>')
    
                if ts or te or add_technical:
                    xml.append('      <notations>')
                    if te:
                        xml.append('        <tied type="start"/>')
                    if ts:
                        xml.append('        <tied type="stop"/>')
                    if add_technical:
                        xml.append('        <technical>')
                        xml.append(f'          <string>{string_no}</string>')
                        xml.append(f'          <fret>{fret}</fret>')
                        xml.append('        </technical>')
                    xml.append('      </notations>')
    
                xml.append('    </note>')
    
        def emit_part_single_voice(part_id: str, is_tab: bool):
            """
            Single voice (voice=1) for both P1 and P2.
            No rests spam: gaps are emitted via <forward>.
            Notes at same onset are emitted as chords (<chord/>).
            """
            xml.append(f'  <part id="{part_id}">')
    
            for mi, m in enumerate(self.model.measures):
                spb = m.steps_per_bar if m.steps_per_bar > 0 else 16
                voice = 1
    
                xml.append(f'  <measure number="{mi+1}">')
    
                # Attributes on first measure
                if mi == 0:
                    xml.append('    <attributes>')
                    xml.append(f'      <divisions>{divisions}</divisions>')
                    xml.append('      <key><fifths>0</fifths></key>')
                    xml.append('      <time><beats>4</beats><beat-type>4</beat-type></time>')
                    if is_tab:
                        xml.append('      <clef><sign>TAB</sign><line>5</line></clef>')
                    else:
                        xml.append('      <clef><sign>G</sign><line>2</line><clef-octave-change>-1</clef-octave-change></clef>')
                    xml.append('    </attributes>')
    
                # Map step boundary -> divisions (sum always == 48)
                step_pos = [int(round(i * measure_div_len / spb)) for i in range(spb + 1)]
                step_pos[0] = 0
                step_pos[-1] = measure_div_len
    
                # Collect onsets where ANY string has note/tie head
                onsets: List[int] = []
                for t0 in range(spb):
                    for s in range(6):
                        c0 = m.grid[s][t0]
                        if c0.kind in ("note", "tie") and c0.fret is not None:
                            onsets.append(t0)
                            break
                onsets = sorted(set(onsets))
    
                # If no notes in this measure: advance silently (no visible rest)
                if not onsets:
                    emit_forward(measure_div_len)
                    xml.append('  </measure>')
                    continue
    
                cursor_step = 0
    
                for idx, t0 in enumerate(onsets):
                    # gap -> forward
                    if t0 > cursor_step:
                        emit_forward(step_pos[t0] - step_pos[cursor_step])
    
                    # single-voice time progression uses "until next onset"
                    t1 = onsets[idx + 1] if (idx + 1) < len(onsets) else spb
                    if t1 <= t0:
                        t1 = min(spb, t0 + 1)
    
                    dur_div_common = step_pos[t1] - step_pos[t0]
                    if dur_div_common <= 0:
                        cursor_step = max(cursor_step, t1)
                        continue
    
                    first = True
                    any_note = False
    
                    # Emit all notes at this onset as a chord
                    for s in range(6):
                        c = m.grid[s][t0]
                        if c.kind not in ("note", "tie") or c.fret is None:
                            continue
    
                        fret = int(c.fret)
                        pitch = TUNING_MIDI[s] + fret
    
                        # Tie judgement uses actual hold-run length
                        dur_steps = 1
                        tt = t0 + 1
                        while tt < spb and m.grid[s][tt].kind == "hold":
                            dur_steps += 1
                            tt += 1
                        end_step = min(spb, t0 + dur_steps)
    
                        tie_stop = (c.kind == "tie")
                        tie_start = False
                        if c.kind == "note":
                            # within measure
                            if end_step < spb:
                                nxt = m.grid[s][end_step]
                                if nxt.kind == "tie" and nxt.fret == fret:
                                    tie_start = True
                            # cross measure
                            elif (mi + 1) < len(self.model.measures):
                                nm = self.model.measures[mi + 1]
                                head = nm.grid[s][0]
                                if head.kind == "tie" and head.fret == fret:
                                    tie_start = True
    
                        emit_note(
                            pitch_midi=pitch,
                            dur_div=dur_div_common,
                            voice=voice,
                            tie_stop=tie_stop,
                            tie_start=tie_start,
                            add_technical=is_tab,
                            string_no=(s + 1),
                            fret=fret,
                            is_chord=(not first)
                        )
                        first = False
                        any_note = True
    
                    # If onset list was weird (shouldn't), still advance time
                    if not any_note:
                        emit_forward(dur_div_common)
    
                    cursor_step = max(cursor_step, t1)
    
                # trailing gap -> forward
                if cursor_step < spb:
                    emit_forward(step_pos[spb] - step_pos[cursor_step])
    
                xml.append('  </measure>')
    
            xml.append('  </part>')
    
        # Emit both parts (both single-voice)
        emit_part_single_voice("P1", is_tab=False)
        emit_part_single_voice("P2", is_tab=True)
    
        xml.append('</score-partwise>')
    
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(xml))
        except Exception as e:
            messagebox.showerror("MusicXML export failed", str(e))

    # -------------------------
    # Basic ops
    # -------------------------
    def new_score(self):
        self.commit_digit_buf()
        self.push_undo(tag="range", burst=False)
        self.model = TabModel(initial_measures=1)
        self.cur_measure = 0
        self.cur_string = 0
        self.cur_step = 0
        self.sel_start = None
        self.sel_end = None

        # ★新規は未保存扱い
        self.current_json_path = None
        self._update_title()

        self.render()

    def set_measure_resolution(self, steps_per_bar: int):
        self.commit_digit_buf()
        self.push_undo(tag="range", burst=False)
        m = self.model.measures[self.cur_measure]
        m.resize(steps_per_bar)
        self.cur_step = min(self.cur_step, m.steps_per_bar - 1)
        self.render()

    # -------------------------
    # Navigation (auto-append on forward beyond end)
    # -------------------------
    def move_string(self, delta: int):
        if self._focus_is_text_input():
            return
        self.commit_digit_buf()
        self.cur_string = max(0, min(5, self.cur_string + delta))
        self.render()

    def move_measure(self, delta: int):
        if self._focus_is_text_input():
            return
        self.commit_digit_buf()
        if delta > 0 and self.cur_measure == len(self.model.measures) - 1:
            self.push_undo(tag="range", burst=False)
            spb = self.model.measures[-1].steps_per_bar
            self.model.measures.append(Measure(spb))
            self.cur_measure += 1
        else:
            self.cur_measure = max(0, min(len(self.model.measures) - 1, self.cur_measure + delta))

        self.cur_step = min(self.cur_step, self.model.measures[self.cur_measure].steps_per_bar - 1)
        self.render()

    def jump_to_step(self, step: int):
        if self._focus_is_text_input():
            return
        self.commit_digit_buf()
        m = self.model.measures[self.cur_measure]
        self.cur_step = max(0, min(m.steps_per_bar - 1, step))
        self.render()

    def move_step(self, delta: int):
        if self._focus_is_text_input():
            return
        self.commit_digit_buf()
        mi = self.cur_measure
        step = self.cur_step + delta

        if delta > 0:
            while True:
                m = self.model.measures[mi]
                if step < m.steps_per_bar:
                    break
                if mi >= len(self.model.measures) - 1:
                    self.push_undo(tag="range", burst=False)
                    spb = m.steps_per_bar
                    self.model.measures.append(Measure(spb))
                step -= m.steps_per_bar
                mi += 1
        else:
            while step < 0:
                if mi == 0:
                    step = 0
                    break
                mi -= 1
                pm = self.model.measures[mi]
                step += pm.steps_per_bar

        self.cur_measure = max(0, min(mi, len(self.model.measures) - 1))
        self.cur_step = max(0, min(self.model.measures[self.cur_measure].steps_per_bar - 1, step))
        self.render()

    # -------------------------
    # Duration
    # -------------------------
    def toggle_dotted(self):
        self.commit_digit_buf()
        self.dotted_var.set(not self.dotted_var.get())
        self.render()

    def effective_steps_for_current_measure(self) -> Tuple[int, Optional[str]]:
        m = self.model.measures[self.cur_measure]
        base16 = int(self.dur16_var.get())
        dotted = bool(self.dotted_var.get())
        factor = m.steps_per_bar / 16.0
        steps = base16 * factor
        if dotted:
            steps *= 1.5
        rounded = int(round(steps))
        warn = None
        if abs(rounded - steps) > 1e-6:
            warn = f"Duration rounded {steps:.2f} -> {rounded} at res={m.steps_per_bar}"
        return max(1, rounded), warn

    # -------------------------
    # Editing (digits/space)
    # -------------------------
    def on_digit(self, event):
        if self._focus_is_text_input():
            return
        d = event.char
        if not d and event.keysym.startswith("KP_"):
            k = event.keysym[3:]
            if k.isdigit():
                d = k

        if d not in "0123456789":
            return

        if self.digit_after_id is not None:
            self.after_cancel(self.digit_after_id)
            self.digit_after_id = None

        if len(self.digit_buf) == 0:
            self.digit_buf = d
            self.digit_after_id = self.after(self.digit_timeout_ms, self.commit_digit_buf)
        else:
            self.digit_buf += d
            self.commit_digit_buf()

    def on_space(self):
        if self._focus_is_text_input():
            return
        if self.digit_buf:
            self._clear_digit_buf()
            self.render()
            return
        self.push_undo(tag="edit", burst=True)
        self.delete_at_cursor()
        self.render()

    def _clear_digit_buf(self):
        if self.digit_after_id is not None:
            self.after_cancel(self.digit_after_id)
            self.digit_after_id = None
        self.digit_buf = ""

    def commit_digit_buf(self):
        if self._focus_is_text_input():
            return
        if not self.digit_buf:
            return
        try:
            fret = int(self.digit_buf)
        except ValueError:
            self._clear_digit_buf()
            return
        self._clear_digit_buf()
        dur_steps, _ = self.effective_steps_for_current_measure()
        self.push_undo(tag="edit", burst=True)
        self.place_note(fret=fret, dur_steps=dur_steps)
        self.render()

    def place_note(self, fret: int, dur_steps: int):
        """
        ★改善：最終小節末をまたぐ入力でも自動で小節を追加して継続できる
        """
        m = self.model.measures[self.cur_measure]
        s = self.cur_string
        t = self.cur_step

        if m.grid[s][t].kind == "hold":
            self._shorten_from_hold(self.cur_measure, s, t)
        if m.grid[s][t].kind in ("note", "tie"):
            self._delete_head_and_holds(self.cur_measure, s, t)

        m.grid[s][t] = Cell(kind="note", fret=fret)

        remaining = dur_steps - 1
        mi = self.cur_measure
        step = t
        while remaining > 0:
            cm = self.model.measures[mi]
            step += 1

            if step >= cm.steps_per_bar:
                mi += 1
                step = 0

                # ★末尾なら自動追加
                if mi >= len(self.model.measures):
                    self.model.measures.append(Measure(cm.steps_per_bar))

                nm = self.model.measures[mi]
                if nm.grid[s][0].kind in ("note", "tie"):
                    self._delete_head_and_holds(mi, s, 0)
                nm.grid[s][0] = Cell(kind="tie", fret=fret)
                remaining -= 1
                continue

            cm.grid[s][step] = Cell(kind="hold")
            remaining -= 1

    def delete_at_cursor(self):
        mi = self.cur_measure
        m = self.model.measures[mi]
        s = self.cur_string
        t = self.cur_step
        c = m.grid[s][t]

        if c.kind == "hold":
            self._shorten_from_hold(mi, s, t)
            return

        if c.kind in ("note", "tie"):
            fret = c.fret
            self._delete_head_and_holds(mi, s, t)
            if fret is not None:
                self._delete_tie_chain_forward(mi + 1, s, fret)

    def _delete_head_and_holds(self, mi: int, s: int, t: int):
        m = self.model.measures[mi]
        m.grid[s][t] = Cell()
        tt = t + 1
        while tt < m.steps_per_bar and m.grid[s][tt].kind == "hold":
            m.grid[s][tt] = Cell()
            tt += 1

    def _shorten_from_hold(self, mi: int, s: int, t: int):
        m = self.model.measures[mi]
        tt = t
        while tt < m.steps_per_bar and m.grid[s][tt].kind == "hold":
            m.grid[s][tt] = Cell()
            tt += 1

    def _delete_tie_chain_forward(self, start_mi: int, s: int, fret: int):
        mi = start_mi
        while mi < len(self.model.measures):
            m = self.model.measures[mi]
            head = m.grid[s][0]
            if head.kind == "tie" and head.fret == fret:
                self._delete_head_and_holds(mi, s, 0)
                mi += 1
                continue
            break

    # -------------------------
    # Rendering
    # -------------------------
    def render(self):
        for item in self.overlay_items:
            self.canvas.delete(item)
        for item in self.rect_items:
            self.canvas.delete(item)
        self.overlay_items.clear()
        self.rect_items.clear()

        window = [self.cur_measure - 1, self.cur_measure, self.cur_measure + 1]
        header, marker, ruler, lines, map_cell, map_ruler, bar_spans = self._build_display(window)

        y = 0
        self._set_base_text("header", 0, y, header, fill="black"); y += self.char_h
        self._set_base_text("marker", 0, y, marker, fill="red");  y += self.char_h
        self._set_base_text("ruler",  0, y, ruler,  fill="black"); y += self.char_h
        for s in range(6):
            self._set_base_text(f"line{s}", 0, y, lines[s], fill="black")
            y += self.char_h
        total_height = y

        max_len = max(len(header), len(marker), len(ruler), *(len(x) for x in lines))
        width_px = self.font.measure(" " * max_len) + 20

        # selection highlight
        sel = self._selection_norm()
        if sel is not None:
            a, b = sel
            for (mi, ch0, ch1) in bar_spans:
                if mi is None or mi < 0 or mi >= len(self.model.measures):
                    continue
                if a <= mi <= b:
                    x0 = self.font.measure(ruler[:ch0])
                    x1 = self.font.measure(ruler[:ch1])
                    r = self.canvas.create_rectangle(
                        x0, 0, x1, total_height,
                        outline="", fill="#fff4c2"
                    )
                    self.rect_items.append(r)

        # ★追加：現在弦の水平網掛け（拍の縦と併用）
        row_y0 = (3 + self.cur_string) * self.char_h
        row_rect = self.canvas.create_rectangle(
            0, row_y0, width_px, row_y0 + self.char_h,
            outline="", fill="#f3f8ff"
        )
        self.rect_items.append(row_rect)

        # overlays: note red, tie gray
        for wi, mi in enumerate(window):
            if not (0 <= mi < len(self.model.measures)):
                continue
            m = self.model.measures[mi]
            for s in range(6):
                for t in range(m.steps_per_bar):
                    c = m.grid[s][t]
                    if c.kind not in ("note", "tie") or c.fret is None:
                        continue
                    if (wi, s, t) not in map_cell:
                        continue
                    chpos = map_cell[(wi, s, t)]
                    x = self.font.measure(lines[s][:chpos])
                    y0 = (3 + s) * self.char_h
                    color = "red" if c.kind == "note" else TIE_GRAY
                    self.overlay_items.append(
                        self.canvas.create_text(
                            x, y0, text=self._cell_text(c),
                            anchor="nw", font=self.font, fill=color
                        )
                    )

        # current string label red
        cur_line_y = (3 + self.cur_string) * self.char_h
        self.overlay_items.append(
            self.canvas.create_text(0, cur_line_y, text=STRINGS[self.cur_string],
                                    anchor="nw", font=self.font, fill="red")
        )

        # blue focus rect (beat/column + cell)
        if (1, self.cur_step) in map_ruler:
            chpos = map_ruler[(1, self.cur_step)]
            x0 = self.font.measure(ruler[:chpos])
            w = self.font.measure("--")

            y_top = 2 * self.char_h
            y_bot = total_height
            col_rect = self.canvas.create_rectangle(x0, y_top, x0 + w, y_bot, outline="", fill="#eef6ff")
            self.rect_items.append(col_rect)

            y1 = (3 + self.cur_string) * self.char_h
            cell_rect = self.canvas.create_rectangle(x0, y1, x0 + w, y1 + self.char_h, outline="", fill="#d0e7ff")
            self.rect_items.append(cell_rect)

        # layer order
        for r in self.rect_items:
            self.canvas.tag_lower(r)
        for item_id in self.base_items.values():
            self.canvas.tag_raise(item_id)
        for item in self.overlay_items:
            self.canvas.tag_raise(item)

        self.canvas.configure(scrollregion=(0, 0, width_px, total_height))

        eff, warn = self.effective_steps_for_current_measure()
        m = self.model.measures[self.cur_measure]
        warn_txt = f"  ⚠ {warn}" if warn else ""
        sel_txt = f"  SEL={sel[0]+1}-{sel[1]+1}" if sel else "  SEL=none"
        self.status.configure(
            text=f"bars={len(self.model.measures)}  bar {self.cur_measure+1} res={m.steps_per_bar} "
                 f"step={self.cur_step+1}/{m.steps_per_bar} string={STRINGS[self.cur_string]} "
                 f"len={DUR_LABELS.get(self.dur16_var.get(), str(self.dur16_var.get()))} dotted={self.dotted_var.get()} "
                 f"=> {eff} steps BPM={self.get_bpm()} buf='{self.digit_buf}'{warn_txt}{sel_txt}"
        )

    def _set_base_text(self, key: str, x: int, y: int, text: str, fill: str = "black"):
        if key not in self.base_items:
            self.base_items[key] = self.canvas.create_text(x, y, text=text, anchor="nw", font=self.font, fill=fill)
        else:
            self.canvas.itemconfigure(self.base_items[key], text=text, fill=fill)
            self.canvas.coords(self.base_items[key], x, y)

    def _build_display(
        self, window: List[int]
    ) -> Tuple[str, str, str, List[str],
               Dict[Tuple[int, int, int], int], Dict[Tuple[int, int], int],
               List[Tuple[int, int, int]]]:
        """
        Returns:
          header, marker, ruler, lines[6],
          map_cell[(wi, s, step)] = char_index_for_cell_start,
          map_ruler[(wi, step)] = char_index_for_step_on_ruler,
          bar_spans[(measure_index, start_char, end_char)] on ruler line
        """
        header = " " * PREFIX_W_CH
        marker = " " * PREFIX_W_CH
        ruler = " " * PREFIX_W_CH
        lines = [(f"{STRINGS[i]:<1}" + " " * (PREFIX_W_CH - 1)) for i in range(6)]

        map_cell: Dict[Tuple[int, int, int], int] = {}
        map_ruler: Dict[Tuple[int, int], int] = {}
        bar_spans: List[Tuple[int, int, int]] = []

        for wi, mi in enumerate(window):
            if wi != 0:
                gap = " " * GAP_BETWEEN_BARS_CH
                header += gap
                marker += gap
                ruler += gap
                for s in range(6):
                    lines[s] += gap

            if 0 <= mi < len(self.model.measures):
                m = self.model.measures[mi]
                spb = m.steps_per_bar
                label = f"[bar {mi+1:03d} {spb:02d}]"
            else:
                m = None
                spb = 16
                label = "[bar --- --]"

            compact48 = (spb == 48 and self.compact48_var.get())

            if compact48:
                # 48 steps mapped into 16 slots, each slot 4 chars, each step -> 1 char
                slots = 16
                slot_w = 4
                interior_len = slots * slot_w
                bar_text_len = 1 + interior_len + 1

                header += label.ljust(bar_text_len)

                marker_inside = [" "] * interior_len
                if wi == 1 and self.cur_step < 48:
                    slot = self.cur_step // 3
                    sub = self.cur_step % 3
                    marker_inside[slot * slot_w + sub] = "^"
                marker += "|" + "".join(marker_inside) + "|"

                ruler_inside = [" "] * interior_len
                for beat_idx, t0 in enumerate([0, 12, 24, 36], start=1):
                    slot = t0 // 3
                    sub = t0 % 3
                    ruler_inside[slot * slot_w + sub] = str(beat_idx)

                bar_start = len(ruler)
                ruler += "|" + "".join(ruler_inside) + "|"
                bar_end = len(ruler)
                bar_spans.append((mi, bar_start, bar_end))

                for step in range(48):
                    slot = step // 3
                    sub = step % 3
                    pos = slot * slot_w + sub
                    map_ruler[(wi, step)] = bar_start + 1 + pos

                for s in range(6):
                    start_char_line = len(lines[s])
                    if m is not None:
                        interior = list("".join(["--  "] * slots))
                        # holds -> blank 2 chars at mapped position
                        for step in range(48):
                            c = m.grid[s][step]
                            if c.kind == "hold":
                                slot = step // 3
                                sub = step % 3
                                pos = slot * slot_w + sub
                                if pos + 1 < interior_len:
                                    interior[pos] = " "
                                    interior[pos + 1] = " "
                        block = "|" + "".join(interior) + "|"
                    else:
                        block = "|" + "".join(["--  "] * slots) + "|"
                    lines[s] += block

                    for step in range(48):
                        slot = step // 3
                        sub = step % 3
                        pos = slot * slot_w + sub
                        map_cell[(wi, s, step)] = start_char_line + 1 + pos

            else:
                # normal view: each step = 2 chars
                cell_w = 2
                interior_len = spb * cell_w
                bar_text_len = 1 + interior_len + 1

                header += label.ljust(bar_text_len)

                marker_inside = [" "] * interior_len
                if wi == 1 and self.cur_step < spb:
                    marker_inside[self.cur_step * cell_w] = "^"
                marker += "|" + "".join(marker_inside) + "|"

                ruler_inside = [" "] * interior_len
                q = spb // 4
                if q > 0:
                    for beat_idx, step0 in enumerate([0, q, 2*q, 3*q], start=1):
                        ruler_inside[step0 * cell_w] = str(beat_idx)

                bar_start = len(ruler)
                ruler += "|" + "".join(ruler_inside) + "|"
                bar_end = len(ruler)
                bar_spans.append((mi, bar_start, bar_end))

                for step in range(spb):
                    map_ruler[(wi, step)] = bar_start + 1 + step * cell_w

                for s in range(6):
                    start_char_line = len(lines[s])
                    if m is not None:
                        base_cells = [self._cell_text(m.grid[s][t]) for t in range(spb)]
                        block = "|" + "".join(base_cells) + "|"
                    else:
                        block = "|" + "".join(["--"] * spb) + "|"
                    lines[s] += block

                    for t in range(spb):
                        map_cell[(wi, s, t)] = start_char_line + 1 + t * cell_w

        return header, marker, ruler, lines, map_cell, map_ruler, bar_spans

    def _cell_text(self, cell: Cell) -> str:
        if cell.kind == "empty":
            return "--"
        if cell.kind == "hold":
            return "  "
        fret = cell.fret if cell.fret is not None else 0
        if fret < 10:
            return f"{fret}-"
        return f"{fret:02d}"


if __name__ == "__main__":
    TabCanvasApp().mainloop()
