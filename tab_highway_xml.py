#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TABハイウェイ動画生成（6弦レーン水平 / 左1/4プレイヘッド / 右→左スクロール）
- 入力: (A) スクリプト内に直書きノートデータ  または (B) MusicXML（TAB: string/fret）
- 出力: MP4（ffmpeg）
"""

from __future__ import annotations

import math
import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict

from PIL import Image, ImageDraw, ImageFont
import xml.etree.ElementTree as ET
import argparse
import shutil
import subprocess
from pathlib import Path
from dataclasses import dataclass

@dataclass
class MeasureSeg:
    meas_no: str
    start_q: float        # クリップ先頭からの開始（四分=1）
    beats: int
    beat_type: int
    dur_q: float          # ★追加：その小節の実長（四分単位）

# =========================
# 調整パラメータ（ここだけ触ればOK）
# =========================

# 出力
WIDTH = 1280
HEIGHT = 720
FPS = 30
OUT_MP4 = "tab_highway.mp4"

# テンポ指定
BPM_OVERRIDE: Optional[float] = 120.0  # None にするとXMLから拾う
BPM_DEFAULT = 120.0

# 見た目
FONT_SIZE = 30            # フレット番号フォント
NOTE_BAR_HEIGHT = 28      # 音バーの太さ（縦）
PRE_ROLL_SECONDS = 1.2    # 最初の音の前の助走（秒）
LOOKAHEAD_SECONDS = 2.5   # 右端→プレイヘッド到達までの秒（大きいほどゆっくり）
DURATION_SCALE = 1.0      # 音価の“見た目だけ”誇張（1.0で実時間通り）

# 余白・位置
MARGIN_LEFT = 70
MARGIN_RIGHT = 30
MARGIN_TOP = 90
MARGIN_BOTTOM = 90
PLAYHEAD_X = int(WIDTH * 0.25)

# 色
BG_COLOR = (12, 12, 16)
LANE_COLOR = (70, 70, 80)
BEAT_LINE_COLOR = (40, 40, 55)
BAR_LINE_COLOR = (90, 90, 110)
PLAYHEAD_COLOR = (220, 220, 240)
NOTE_FILL = (230, 230, 240)
NOTE_TEXT = (20, 20, 28)

# --- Theme ---
THEME = "auto"  # "auto" | "light" | "dark"
THEME_LUMA_THRESHOLD = 160.0  # auto判定の閾値

# 前景（テーマで上書きされる）
LANE_COLOR = (70, 70, 80)
BEAT_LINE_COLOR = (40, 40, 55)
BAR_LINE_COLOR = (90, 90, 110)
PLAYHEAD_COLOR = (220, 220, 240)
STRING_LABEL_COLOR = (180, 180, 200)
BAR_LABEL_COLOR = (160, 160, 185)
ATTACK_MIN_DIGITS = 2  # 2にすると1桁でも2桁と同じ円サイズ

# --- Outline (縁取り) ---
NOTE_OUTLINE_PX = 2
NOTE_OUTLINE_RGB = (0, 0, 0)

LINE_OUTLINE_PX = 2
LINE_OUTLINE_RGB = (0, 0, 0)

# --- Audio ---
ENABLE_AUDIO = False
ENABLE_METRONOME = True

SOUNDFONT_PATH = "/usr/share/sounds/sf2/FluidR3_GM.sf2"  # 環境により違う。CLIで上書き推奨
AUDIO_SAMPLE_RATE = 44100
AUDIO_GAIN = 0.6

# GM program (0-based): 24=nylon, 25=steel
GUITAR_PROGRAM_0BASED = 25  # steel guitar

CLICK_VELOCITY = 70
ACCENT_VELOCITY = 110
CLICK_NOTE = 42     # closed hi-hat
ACCENT_NOTE = 37    # side stick
CLICK_LEN_BEATS = 0.08  # クリックの長さ（拍）

# --- Strings / Tuning ---
STRINGS = 6  # 4ならベース4弦など
OPEN_MIDI: Dict[int, int] = {}  # string_index -> midi (string=1が最も細い弦)

# 入力切替
USE_MUSICXML = True

# MusicXML: ファイルパス指定（推奨）
MUSICXML_PATH = "input.musicxml"

# MusicXML: ここに貼り付けた断片を置いてもOK（ファイルが無いとき用）
MUSICXML_SNIPPET = r"""
  </part>
  <part id="P2">
  <measure number="1">
    <attributes>
      <divisions>12</divisions>
      <key><fifths>0</fifths></key>
      <time><beats>4</beats><beat-type>4</beat-type></time>
      <clef><sign>TAB</sign><line>5</line></clef>
    </attributes>
    <forward>
      <duration>24</duration>
    </forward>
    <note>
      <pitch>
        <step>B</step>
        <octave>2</octave>
      </pitch>
      <duration>6</duration>
      <voice>1</voice>
      <staff>1</staff>
      <type>eighth</type>
      <notations>
        <technical>
          <string>5</string>
          <fret>2</fret>
        </technical>
      </notations>
    </note>
    <note>
      <chord/>
      <pitch>
        <step>E</step>
        <octave>2</octave>
      </pitch>
      <duration>6</duration>
      <voice>1</voice>
      <staff>1</staff>
      <type>eighth</type>
      <notations>
        <technical>
          <string>6</string>
          <fret>0</fret>
        </technical>
      </notations>
    </note>
    <note>
      <pitch>
        <step>B</step>
        <octave>2</octave>
      </pitch>
      <duration>12</duration>
      <voice>1</voice>
      <staff>1</staff>
      <type>quarter</type>
      <notations>
        <technical>
          <string>5</string>
          <fret>2</fret>
        </technical>
      </notations>
    </note>
    <note>
      <chord/>
      <pitch>
        <step>E</step>
        <octave>2</octave>
      </pitch>
      <duration>12</duration>
      <voice>1</voice>
      <staff>1</staff>
      <type>quarter</type>
      <notations>
        <technical>
          <string>6</string>
          <fret>0</fret>
        </technical>
      </notations>
    </note>
    <note>
      <pitch>
        <step>D</step>
        <alter>1</alter>
        <octave>3</octave>
      </pitch>
      <duration>6</duration>
      <voice>1</voice>
      <staff>1</staff>
      <type>eighth</type>
      <tie type="start"/>
      <notations>
        <tied type="start"/>
        <technical>
          <string>4</string>
          <fret>1</fret>
        </technical>
      </notations>
    </note>
    <note>
      <chord/>
      <pitch>
        <step>B</step>
        <octave>2</octave>
      </pitch>
      <duration>6</duration>
      <voice>1</voice>
      <staff>1</staff>
      <type>eighth</type>
      <tie type="start"/>
      <notations>
        <tied type="start"/>
        <technical>
          <string>5</string>
          <fret>2</fret>
        </technical>
      </notations>
    </note>
  </measure>
"""


# =========================
# データ構造
# =========================

@dataclass(frozen=True)
class NoteEvent:
    start_beats: float     # 開始（拍）
    dur_beats: float       # 長さ（拍）
    string_1_to_6: int     # 1..6（上=1弦, 下=6弦）
    fret: int


# =========================
# 基本ユーティリティ
# =========================

def seconds_per_beat(bpm: float) -> float:
    return 60.0 / bpm

def beats_to_seconds(beats: float, bpm: float) -> float:
    return beats * seconds_per_beat(bpm)

def clamp(a: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, a))

def load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            return ImageFont.truetype(p, size=size)
    return ImageFont.load_default()

def run_ffmpeg_encode(frames_dir: str, fps: int, out_mp4: str) -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg が見つかりません。sudo apt-get install ffmpeg を実行してください。")
    pattern = os.path.join(frames_dir, "frame_%06d.png")
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(fps),
        "-i", pattern,
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        out_mp4
    ]
    subprocess.run(cmd, check=True)

def make_lane_centers() -> List[int]:
    usable_h = HEIGHT - MARGIN_TOP - MARGIN_BOTTOM
    step = usable_h / 5.0
    return [int(MARGIN_TOP + i * step) for i in range(6)]  # index0=1弦

def string_to_y(string_1_to_n: int, lane_centers: List[int]) -> int:
    s = int(string_1_to_n)
    if s < 1:
        s = 1
    if s > len(lane_centers):
        s = len(lane_centers)
    return lane_centers[s - 1]  # 1弦が上、n弦が下

def x_for_time(event_time_sec: float, now_sec: float, speed_px_per_sec: float) -> float:
    return PLAYHEAD_X + (event_time_sec - now_sec) * speed_px_per_sec

def wavelength_to_rgb(wavelength_nm: float) -> Tuple[int, int, int]:
    """
    波長(nm) -> RGB (0-255)
    近似式（可視域 380-780nm を想定）。範囲外はクランプ。
    """
    w = float(wavelength_nm)
    w = max(380.0, min(780.0, w))

    if 380 <= w < 440:
        r, g, b = -(w - 440) / (440 - 380), 0.0, 1.0
    elif 440 <= w < 490:
        r, g, b = 0.0, (w - 440) / (490 - 440), 1.0
    elif 490 <= w < 510:
        r, g, b = 0.0, 1.0, -(w - 510) / (510 - 490)
    elif 510 <= w < 580:
        r, g, b = (w - 510) / (580 - 510), 1.0, 0.0
    elif 580 <= w < 645:
        r, g, b = 1.0, -(w - 645) / (645 - 580), 0.0
    else:  # 645-780
        r, g, b = 1.0, 0.0, 0.0

    # 端の視感度補正（それっぽく）
    if 380 <= w < 420:
        factor = 0.3 + 0.7 * (w - 380) / (420 - 380)
    elif 420 <= w <= 700:
        factor = 1.0
    else:  # 700-780
        factor = 0.3 + 0.7 * (780 - w) / (780 - 700)

    gamma = 0.8
    def to_int(c: float) -> int:
        c = max(0.0, min(1.0, c))
        return int(round((c * factor) ** gamma * 255))

    return to_int(r), to_int(g), to_int(b)


def fret_to_color(fret: int, fret_min: int = 0, fret_max: int = 24) -> Tuple[int, int, int]:
    """
    fret_min -> 青、fret_max -> 赤。間は可視光スペクトルで補間。
    ユーザー要望に合わせて、青側 ~450nm、赤側 ~650nm を線形で割り当て。
    """
    if fret_max <= fret_min:
        return (255, 255, 255)

    t = (fret - fret_min) / (fret_max - fret_min)
    t = max(0.0, min(1.0, t))

    blue_nm = 450.0
    red_nm = 650.0
    wl = blue_nm + t * (red_nm - blue_nm)  # 0->450(青), 1->650(赤)

    return wavelength_to_rgb(wl)


def best_text_color(fill_rgb: Tuple[int, int, int]) -> Tuple[int, int, int]:
    """
    背景/塗りの明るさで文字色を自動選択（黒 or 白）
    """
    r, g, b = fill_rgb
    # 相対輝度っぽいもの
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return (20, 20, 28) if y > 160 else (245, 245, 250)

def parse_hex_rgb(s: str) -> Tuple[int, int, int]:
    """
    'FFFFFF' / '#FFFFFF' / 'fff' / '#fff' を (255,255,255) に変換
    """
    t = s.strip()
    if t.startswith("#"):
        t = t[1:]
    if len(t) == 3:
        t = "".join([c * 2 for c in t])
    if len(t) != 6 or any(c not in "0123456789abcdefABCDEF" for c in t):
        raise ValueError(f"invalid hex color: {s} (use RRGGBB like FFFFFF)")
    r = int(t[0:2], 16)
    g = int(t[2:4], 16)
    b = int(t[4:6], 16)
    return (r, g, b)

def relative_luma(rgb: Tuple[int, int, int]) -> float:
    r, g, b = rgb
    return 0.2126 * r + 0.7152 * g + 0.0722 * b  # 0-255

def resolve_theme(theme: str, bg_rgb: Tuple[int, int, int]) -> str:
    t = (theme or "auto").lower()
    if t in ("light", "dark"):
        return t
    # auto
    return "light" if relative_luma(bg_rgb) >= THEME_LUMA_THRESHOLD else "dark"

def apply_theme(theme: str, bg_rgb: Tuple[int, int, int]) -> None:
    """
    背景色(bg)に対して、線/文字などの前景色を light/dark で切替。
    背景色そのものは変更しない（キー用途の予測ができるように）。
    """
    global LANE_COLOR, BEAT_LINE_COLOR, BAR_LINE_COLOR, PLAYHEAD_COLOR
    global STRING_LABEL_COLOR, BAR_LABEL_COLOR

    t = resolve_theme(theme, bg_rgb)

    if t == "light":
        # 明るい背景（白など）用：前景を濃色に
        LANE_COLOR = (60, 60, 70)
        BEAT_LINE_COLOR = (150, 150, 165)
        BAR_LINE_COLOR = (90, 90, 110)
        PLAYHEAD_COLOR = (10, 10, 14)
        STRING_LABEL_COLOR = (30, 30, 40)
        BAR_LABEL_COLOR = (30, 30, 40)
    else:
        # 暗い背景用：前景を淡色に（今までのデフォルトに近い）
        LANE_COLOR = (70, 70, 80)
        BEAT_LINE_COLOR = (40, 40, 55)
        BAR_LINE_COLOR = (90, 90, 110)
        PLAYHEAD_COLOR = (220, 220, 240)
        STRING_LABEL_COLOR = (180, 180, 200)
        BAR_LABEL_COLOR = (160, 160, 185)

def theme_default_outline_rgb(theme: str, bg_rgb: Tuple[int, int, int]) -> Tuple[int, int, int]:
    """
    テーマに合わせた縁取り色の既定値：
    light -> 黒、dark -> 白
    """
    t = resolve_theme(theme, bg_rgb)
    return (0, 0, 0) if t == "light" else (255, 255, 255)

def draw_line_with_outline(draw: ImageDraw.ImageDraw,
                           p0: Tuple[float, float],
                           p1: Tuple[float, float],
                           fill: Tuple[int, int, int],
                           width: int,
                           outline_px: int,
                           outline_rgb: Tuple[int, int, int]) -> None:
    """
    線を「アウトライン→本線」の2回描画で縁取りする。
    outline_px=0 なら通常描画。
    """
    w = int(width)
    if outline_px > 0:
        ow = w + 2 * int(outline_px)
        draw.line([p0, p1], fill=outline_rgb, width=ow)
    draw.line([p0, p1], fill=fill, width=w)

def default_open_midi_for_strings(n: int) -> Dict[int, int]:
    """
    string番号は MusicXML準拠で 1=最も細い(高い), n=最も太い(低い)。
    """
    n = int(n)
    if n == 4:
        # Bass 4: G2 D2 A1 E1（1弦がG2）
        return {1: 43, 2: 38, 3: 33, 4: 28}
    if n == 5:
        # Bass 5: G2 D2 A1 E1 B0（5弦がB0）
        return {1: 43, 2: 38, 3: 33, 4: 28, 5: 23}
    if n == 6:
        # Guitar 6: E4 B3 G3 D3 A2 E2
        return {1: 64, 2: 59, 3: 55, 4: 50, 5: 45, 6: 40}
    if n == 7:
        # 7-string guitar (一般的): E4 B3 G3 D3 A2 E2 B1
        return {1: 64, 2: 59, 3: 55, 4: 50, 5: 45, 6: 40, 7: 35}

    # その他は「とりあえず6弦ギターを縮める」フォールバック
    base6 = {1: 64, 2: 59, 3: 55, 4: 50, 5: 45, 6: 40}
    return {s: base6.get(s, 40) for s in range(1, n + 1)}

# --- Audio ---
def string_fret_to_midi(string_1_to_n: int, fret: int) -> int:
    base = OPEN_MIDI.get(int(string_1_to_n))
    if base is None:
        # 範囲外が来ても落ちないように
        base = OPEN_MIDI.get(STRINGS, 40)  # 一番太い弦の値か 40
    return int(base + int(fret))

def write_midi(notes, out_mid, bpm, measure_segs: List[MeasureSeg], program_0based, ppq=480, include_metronome=True):
    import mido
    from mido import Message, MidiFile, MidiTrack, MetaMessage

    mid = MidiFile(ticks_per_beat=ppq)
    meta = MidiTrack()
    meta_events: List[Tuple[int, int, mido.MetaMessage]] = []
    
    # tempo は先頭（tick=0）
    meta_events.append((0, 0, MetaMessage('set_tempo', tempo=mido.bpm2tempo(float(bpm)), time=0)))
    
    # PRE_ROLL でノート/クリックを後ろへずらしているなら、拍子変化点も同じだけずらす
    offset_beats = float(PRE_ROLL_SECONDS) / seconds_per_beat(bpm)
    offset_tick = int(round(offset_beats * ppq))
    
    # 拍子（最初は tick=0 に必ず入れる）
    if measure_segs:
        first = measure_segs[0]
        meta_events.append((0, 1, MetaMessage('time_signature',
                                              numerator=int(first.beats),
                                              denominator=int(first.beat_type),
                                              time=0)))
        last_ts = (int(first.beats), int(first.beat_type))
    
        # 以後、拍子が変わったところだけ追加
        for seg in measure_segs[1:]:
            ts = (int(seg.beats), int(seg.beat_type))
            if ts != last_ts:
                tick = offset_tick + int(round(float(seg.start_q) * ppq))  # ★ここが変化点
                meta_events.append((tick, 1, MetaMessage('time_signature',
                                                        numerator=ts[0],
                                                        denominator=ts[1],
                                                        time=0)))
                last_ts = ts
    else:
        # measure_segsが作れない場合の保険（従来互換）
        meta_events.append((0, 1, MetaMessage('time_signature', numerator=4, denominator=4, time=0)))
    
    # meta_events をデルタにして track に書き込む
    meta_events.sort(key=lambda x: (x[0], x[1]))
    last = 0
    for tick, _order, msg in meta_events:
        msg.time = int(tick - last)
        last = tick
        meta.append(msg)
    
    mid.tracks.append(meta)

    meta.append(MetaMessage('set_tempo', tempo=mido.bpm2tempo(float(bpm)), time=0))

    # --- Guitar track ---
    tr_g = MidiTrack()
    mid.tracks.append(tr_g)
    tr_g.append(Message('program_change', program=int(program_0based), channel=0, time=0))

    # --- Metronome track (drums) ---
    tr_m = None
    if include_metronome:
        tr_m = MidiTrack()
        mid.tracks.append(tr_m)

    # 音声は「視覚用DURATION_SCALE」の影響を受けないよう、元に戻す
    dur_scale = float(DURATION_SCALE) if float(DURATION_SCALE) != 0.0 else 1.0

    # 絶対tickのイベントにして後でデルタ化
    g_events: List[Tuple[int, int, Message]] = []
    m_events: List[Tuple[int, int, Message]] = []

    # 映像はPRE_ROLLで先頭に余白があるので、音も同じだけ前に無音を置く（＝ノートを後ろにずらす）
    # ※これで「映像上でプレイヘッドに来た瞬間に鳴る」に一致
    offset_beats = float(PRE_ROLL_SECONDS) / seconds_per_beat(bpm)

    for n in notes:
        start_beats = float(n.start_beats) + offset_beats
        dur_beats_raw = float(n.dur_beats) / dur_scale

        start_tick = int(round(start_beats * ppq))
        end_tick = int(round((start_beats + max(0.02, dur_beats_raw)) * ppq))
        end_tick = max(end_tick, start_tick + 1)

        midi_note = string_fret_to_midi(n.string_1_to_6, n.fret)

        # 同tickでの並び：off(0)を先に、on(1)を後に
        g_events.append((start_tick, 1, Message('note_on', note=midi_note, velocity=90, channel=0, time=0)))
        g_events.append((end_tick,   0, Message('note_off', note=midi_note, velocity=0, channel=0, time=0)))

    if include_metronome and tr_m is not None:
        click_len_ticks = max(1, int(round(float(CLICK_LEN_BEATS) * ppq)))

        if include_metronome and tr_m is not None:
            click_len_ticks = max(1, int(round(float(CLICK_LEN_BEATS) * ppq)))
            offset_beats = float(PRE_ROLL_SECONDS) / seconds_per_beat(bpm)
            
            for seg in measure_segs:
                beat_unit_q = 4.0 / float(seg.beat_type)
                for i in range(int(seg.beats)):
                    q = seg.start_q + i * beat_unit_q
                    t = int(round((offset_beats + q) * ppq))
            
                    is_accent = (i == 0)
                    note = ACCENT_NOTE if is_accent else CLICK_NOTE
                    vel = ACCENT_VELOCITY if is_accent else CLICK_VELOCITY
            
                    m_events.append((t, 1, Message('note_on', note=note, velocity=int(vel), channel=9, time=0)))
                    m_events.append((t + click_len_ticks, 0, Message('note_off', note=note, velocity=0, channel=9, time=0)))

    def write_track(track: MidiTrack, events: List[Tuple[int, int, Message]]) -> None:
        events.sort(key=lambda x: (x[0], x[1]))
        last = 0
        for tick, _order, msg in events:
            delta = tick - last
            last = tick
            msg.time = int(delta)
            track.append(msg)

    write_track(tr_g, g_events)
    if tr_m is not None:
        write_track(tr_m, m_events)

    mid.save(out_mid)

def ensure_tool(name: str) -> None:
    if shutil.which(name) is None:
        raise RuntimeError(f"required tool not found: {name}")

def midi_to_wav(mid_path: str, wav_path: str, soundfont: str, samplerate: int = 44100, gain: float = 0.6) -> None:
    ensure_tool("fluidsynth")
    cmd = [
        "fluidsynth",
        "-ni",
        "-g", str(gain),
        soundfont,
        mid_path,
        "-F", wav_path,
        "-r", str(int(samplerate)),
    ]
    subprocess.run(cmd, check=True)

def mux_audio(video_path: str, wav_path: str, out_path: str) -> None:
    ensure_tool("ffmpeg")
    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-i", wav_path,
        "-c:v", "copy",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        out_path
    ]
    subprocess.run(cmd, check=True)


# =========================
# 描画
# =========================

def draw_lanes(draw: ImageDraw.ImageDraw, lane_centers: List[int]) -> None:
    for y in lane_centers:
        draw_line_with_outline(
            draw,
            (MARGIN_LEFT, y), (WIDTH - MARGIN_RIGHT, y),
            fill=LANE_COLOR,
            width=2,
            outline_px=LINE_OUTLINE_PX,
            outline_rgb=LINE_OUTLINE_RGB
        )

    font = load_font(18)
    for s in range(1, STRINGS + 1):
        y = string_to_y(s, lane_centers)
        label = f"{s}"
        bbox = draw.textbbox((0, 0), label, font=font)
        th = bbox[3] - bbox[1]
        draw.text((10, y - th // 2), label, fill=(180, 180, 200), font=font)

def draw_playhead(draw: ImageDraw.ImageDraw) -> None:
    draw_line_with_outline(
        draw,
        (PLAYHEAD_X, MARGIN_TOP - 40),
        (PLAYHEAD_X, HEIGHT - MARGIN_BOTTOM + 40),
        fill=PLAYHEAD_COLOR,
        width=3,
        outline_px=LINE_OUTLINE_PX,
        outline_rgb=LINE_OUTLINE_RGB
    )

def draw_grid(draw: ImageDraw.ImageDraw, now_sec: float, speed: float,
              bpm: float, measure_segs2: List[MeasureSeg]) -> None:
    font = load_font(18)

    sec_per_q = seconds_per_beat(bpm)  # 四分音符1つの秒

    for seg in measure_segs2:
        # 小節頭（Bar line）
        bar_t = seg.start_q * sec_per_q
        x_bar = PLAYHEAD_X + (bar_t - now_sec) * speed
        if x_bar < MARGIN_LEFT - 200 or x_bar > WIDTH - MARGIN_RIGHT + 200:
            continue

        # 小節線
        draw_line_with_outline(
            draw,
            (x_bar, MARGIN_TOP - 25), (x_bar, HEIGHT - MARGIN_BOTTOM + 25),
            fill=BAR_LINE_COLOR, width=3,
            outline_px=LINE_OUTLINE_PX, outline_rgb=LINE_OUTLINE_RGB
        )

        # 小節番号
        draw.text((x_bar + 4, MARGIN_TOP - 55), f"Bar {seg.meas_no}",
                  fill=BAR_LABEL_COLOR, font=font)

        # 拍線（beat-typeに従う）
        beat_unit_q = 4.0 / float(seg.beat_type)  # 1拍の長さ（四分音符単位）
        for i in range(1, int(seg.beats)):  # 小節頭は既に引いたので1..beats-1
            q = seg.start_q + i * beat_unit_q
            t = q * sec_per_q
            x = PLAYHEAD_X + (t - now_sec) * speed
            if x < MARGIN_LEFT - 50 or x > WIDTH - MARGIN_RIGHT + 50:
                continue
            draw_line_with_outline(
                draw,
                (x, MARGIN_TOP - 25), (x, HEIGHT - MARGIN_BOTTOM + 25),
                fill=BEAT_LINE_COLOR, width=1,
                outline_px=LINE_OUTLINE_PX, outline_rgb=LINE_OUTLINE_RGB
            )

def draw_note(draw: ImageDraw.ImageDraw, lane_y: int,
              x0: float, x1: float, fret: int,
              font: ImageFont.ImageFont, bar_height: int,
              fill_rgb: Tuple[int, int, int]) -> None:
    """
    アタック：フレット数字入りの円
    サステイン：円の右端から x1 までのバー（太さ=bar_height）
    ※右→左に流れるので、尾は右側（後ろ）に伸びるのが自然
    """
    if x1 < x0:
        x0, x1 = x1, x0

    # 画面外は早めに捨てる
    if x1 < MARGIN_LEFT - 80 or x0 > WIDTH + 80:
        return

    # テキストサイズから円サイズを決める（フォントに追従）
    label = str(fret)
    tb = draw.textbbox((0, 0), label, font=font)
    tw = tb[2] - tb[0]
    th = tb[3] - tb[1]
    
    # --- 追加：最低でも2桁ぶんの幅を確保（1桁でも円を小さくしない） ---
    sample = "8" * int(ATTACK_MIN_DIGITS)   # "88"
    tb2 = draw.textbbox((0, 0), sample, font=font)
    tw2 = tb2[2] - tb2[0]
    th2 = tb2[3] - tb2[1]
    tw = max(tw, tw2)
    th = max(th, th2)

    pad = max(6, int(FONT_SIZE * 0.25))            # 文字の周囲余白
    diameter = max(int(bar_height * 1.2), tw + pad * 2, th + pad * 2)
    radius = diameter / 2.0

    # 円（中心は x0）
    cx = x0
    cy = lane_y
    c_left = cx - radius
    c_right = cx + radius
    c_top = cy - radius
    c_bottom = cy + radius

    # サステインバー：円の右端→x1
    bar_h = int(bar_height)
    y0 = lane_y - bar_h // 2
    y1 = lane_y + bar_h // 2

    bar_start = c_right
    bar_end = x1

    # バー描画（画面内にある範囲だけ）
    bx0 = clamp(bar_start, MARGIN_LEFT, WIDTH - MARGIN_RIGHT)
    bx1 = clamp(bar_end,   MARGIN_LEFT, WIDTH - MARGIN_RIGHT)

    if bx1 > bx0 + 1:
        r = max(4, min(10, bar_h // 3))
        if NOTE_OUTLINE_PX > 0:
            draw.rounded_rectangle([bx0, y0, bx1, y1], radius=r,
                                   fill=fill_rgb, outline=NOTE_OUTLINE_RGB, width=NOTE_OUTLINE_PX)
        else:
            draw.rounded_rectangle([bx0, y0, bx1, y1], radius=r, fill=fill_rgb)

    # 円描画（画面内なら）
    ex0 = clamp(c_left,  MARGIN_LEFT, WIDTH - MARGIN_RIGHT)
    ex1 = clamp(c_right, MARGIN_LEFT, WIDTH - MARGIN_RIGHT)
    # 円がほぼ画面外なら捨てる
    if ex1 > MARGIN_LEFT + 1 and ex0 < WIDTH - MARGIN_RIGHT - 1:
        if NOTE_OUTLINE_PX > 0:
            draw.ellipse([c_left, c_top, c_right, c_bottom],
                         fill=fill_rgb, outline=NOTE_OUTLINE_RGB, width=NOTE_OUTLINE_PX)
        else:
            draw.ellipse([c_left, c_top, c_right, c_bottom], fill=fill_rgb)

        # 文字色（背景や塗りに応じて黒/白を選ぶ）
        txt = best_text_color(fill_rgb)
        
        label = str(fret)
        tb_label = draw.textbbox((0, 0), label, font=font)  # (x0,y0,x1,y1)
        
        # bboxの中心を円の中心(cx,cy)に一致させる
        tx = cx - (tb_label[0] + tb_label[2]) / 2.0
        ty = cy - (tb_label[1] + tb_label[3]) / 2.0
        
        draw.text((tx, ty), label, fill=txt, font=font)



# =========================
# MusicXML パース
# =========================

def _strip_ns(tag: str) -> str:
    # "{namespace}tag" -> "tag"
    return tag.split("}", 1)[-1] if "}" in tag else tag

def normalize_musicxml_snippet(snippet: str) -> str:
    """
    貼り付け断片を最小限のMusicXML構造に包んでET.parseできるようにする。
    - <measure>から始まってもOK（自動で <part id="P2"> で包む）
    - 先頭のゴミ（</part>等）を落とす
    """
    s = snippet.strip()

    # 先頭の余計な閉じタグなどを落として、<score-partwise> / <part> / <measure> のどれかから始める
    m = re.search(r"<(score-partwise\b|part\b|measure\b)", s)
    if not m:
        raise ValueError("snippet内に <score-partwise> / <part> / <measure> が見つかりません。")
    s = s[m.start():]

    # すでにscore-partwiseならそのまま（閉じが無ければ補う）
    if "<score-partwise" in s:
        if "</score-partwise>" not in s:
            s += "\n</score-partwise>\n"
        return s

    # <part>が無いなら、<measure>断片だとみなして part で包む
    if "<part" not in s:
        if "<measure" in s:
            s = f'<part id="P2">\n{s}\n</part>\n'
        else:
            raise ValueError("snippetが <part> も <measure> も含みません。")

    # </part> が無ければ足す
    if "</part>" not in s:
        s += "\n</part>\n"

    # ルートで包む（part-list は不要。ETで読めればOK）
    s = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<score-partwise version="3.1">\n'
        f'{s}\n'
        '</score-partwise>\n'
    )
    return s

def extract_tempo_from_musicxml(root: ET.Element) -> Optional[float]:
    """
    よくあるMusicXMLのテンポ表現から bpm を拾う。
    - <sound tempo="120"/>
    - <direction><sound tempo="..."/>
    - 稀に <per-minute> など（簡易対応）
    """
    # 1) <sound tempo="..."> を総当り
    for el in root.iter():
        if _strip_ns(el.tag) == "sound":
            tempo = el.attrib.get("tempo")
            if tempo:
                try:
                    return float(tempo)
                except ValueError:
                    pass

    # 2) <per-minute> を探す（metronome表記）
    for el in root.iter():
        if _strip_ns(el.tag) == "per-minute" and el.text:
            try:
                return float(el.text.strip())
            except ValueError:
                pass

    return None

def choose_tab_part_id(root: ET.Element, fallback: str = "P2") -> str:
    """
    part-listのpart-nameに 'TAB' が含まれるパートを優先して選ぶ。
    見つからなければ fallback。
    """
    # part-listから探す
    part_list = None
    for el in root.iter():
        if _strip_ns(el.tag) == "part-list":
            part_list = el
            break

    if part_list is not None:
        for sp in part_list:
            if _strip_ns(sp.tag) != "score-part":
                continue
            pid = sp.attrib.get("id")
            pname = sp.findtext("part-name") or ""
            if pid and ("tab" in pname.lower()):
                return pid

    return fallback

def parse_musicxml_notes(xml_text: str,
                         target_part_id: str = "P2",
                         target_voice: Optional[str] = "1",
                         target_staff: Optional[str] = "1",
                         bpm_fallback: float = BPM_DEFAULT,
                         start_measure: Optional[int] = None,
                         end_measure: Optional[int] = None
                         ) -> Tuple[List[NoteEvent], float, int, int]:

    root = ET.fromstring(xml_text)

    measure_segs: List[MeasureSeg] = []
    time_sig_den = 4  # 追加：beat-type

    # part選択
    part = None
    for p in root.iter():
        if _strip_ns(p.tag) == "part" and p.attrib.get("id") == target_part_id:
            part = p
            break
    if part is None:
        raise ValueError(f'part id="{target_part_id}" が見つかりません。')

    divisions = 12
    time_sig_num = 4

    cursor = 0          # divisions単位の時間カーソル
    last_onset = 0      # chord用

    events: List[NoteEvent] = []

    # クリップ基準
    clip_offset_div: Optional[int] = None
    bar_number_base = start_measure if (start_measure is not None) else 1

    # tie追跡：key=(voice, staff, string, fret) -> (start_onset_div, total_dur_div)
    open_ties: Dict[Tuple[str, str, int, int], Tuple[int, int]] = {}

    def tie_types_of(note_el: ET.Element) -> set[str]:
        types: set[str] = set()
        for t in note_el.findall("tie"):
            tp = t.attrib.get("type")
            if tp:
                types.add(tp)
        for el2 in note_el.iter():
            if _strip_ns(el2.tag) == "tied":
                tp = el2.attrib.get("type")
                if tp:
                    types.add(tp)
        return types

    def in_measure_range(meas_no: Optional[int]) -> bool:
        if meas_no is None:
            # 変則番号はとりあえず範囲内扱い（必要なら強化）
            return True
        if start_measure is not None and meas_no < start_measure:
            return False
        if end_measure is not None and meas_no > end_measure:
            return False
        return True

    for meas in list(part):
        if _strip_ns(meas.tag) != "measure":
            continue

        meas_no_text = meas.attrib.get("number", "")
        try:
            meas_no = int(meas_no_text)
        except ValueError:
            meas_no = None

        in_range = in_measure_range(meas_no)
        meas_start_cursor = cursor  # 小節開始div
        
        # ... この小節の中身を処理して cursor を進める ...
        
        meas_end_cursor = cursor
        meas_dur_q = (meas_end_cursor - meas_start_cursor) / divisions

        
        # clip_offset_div が確定した瞬間（最初の範囲内小節）に start を0基準にする
        if clip_offset_div is None and in_range:
            clip_offset_div = cursor
            bar_number_base = start_measure if (start_measure is not None) else 1
            open_ties.clear()

        if in_range and clip_offset_div is not None:
            start_q = (meas_start_cursor - clip_offset_div) / divisions
            measure_segs.append(MeasureSeg(
                meas_no=meas_no_text if meas_no_text else str(meas_no) if meas_no is not None else "?",
                start_q=float(start_q),
                beats=int(time_sig_num),
                beat_type=int(time_sig_den),
                dur_q=float(meas_dur_q),
            ))

        # クリップ開始位置を「最初に範囲内に入った瞬間」の cursor で確定
        if clip_offset_div is None and in_range:
            clip_offset_div = cursor
            bar_number_base = start_measure if (start_measure is not None) else 1
            # クリップ前から持ち越した tie は見た目を崩すので破棄（跨ぎ対応したくなったら拡張）
            open_ties.clear()

        # 範囲外でも attributes/forward/backup/note を処理して cursor は正しく進める
        for el in list(meas):
            tag = _strip_ns(el.tag)

            if tag == "attributes":
                beats_el = el.find(".//time/beats")
                if beats_el is not None and beats_el.text and beats_el.text.isdigit():
                    time_sig_num = int(beats_el.text)
                
                beat_type_el = el.find(".//time/beat-type")
                if beat_type_el is not None and beat_type_el.text and beat_type_el.text.isdigit():
                    time_sig_den = int(beat_type_el.text)

                div_el = el.find(".//divisions")
                if div_el is not None and div_el.text and div_el.text.isdigit():
                    divisions = int(div_el.text)

                beats_el = el.find(".//time/beats")
                if beats_el is not None and beats_el.text and beats_el.text.isdigit():
                    time_sig_num = int(beats_el.text)

            elif tag == "forward":
                dur_el = el.find(".//duration")
                if dur_el is not None and dur_el.text:
                    cursor += int(dur_el.text)

            elif tag == "backup":
                dur_el = el.find(".//duration")
                if dur_el is not None and dur_el.text:
                    cursor -= int(dur_el.text)

            elif tag == "note":
                v = (el.findtext("voice") or "1").strip()
                st = (el.findtext("staff") or "1").strip()
                if target_voice is not None and v != target_voice:
                    continue
                if target_staff is not None and st != target_staff:
                    continue

                is_rest = el.find("rest") is not None
                dur_text = el.findtext("duration")
                if dur_text is None:
                    continue
                dur_div = int(dur_text)

                is_chord = el.find("chord") is not None
                onset = last_onset if is_chord else cursor
                if not is_chord:
                    last_onset = onset

                advance_time = (not is_chord)

                if is_rest:
                    if advance_time:
                        cursor += dur_div
                    continue

                # string/fret取得
                string_text = None
                fret_text = None
                for tech in el.iter():
                    if _strip_ns(tech.tag) == "technical":
                        st_el = tech.find("./string")
                        fr_el = tech.find("./fret")
                        if st_el is not None and st_el.text:
                            string_text = st_el.text.strip()
                        if fr_el is not None and fr_el.text:
                            fret_text = fr_el.text.strip()
                        break

                if string_text is None or fret_text is None:
                    if advance_time:
                        cursor += dur_div
                    continue

                string_1_to_6 = int(string_text)
                fret = int(fret_text)

                ttypes = tie_types_of(el)
                key = (v, st, string_1_to_6, fret)

                off = clip_offset_div or 0

                def emit_note(start_div: int, total_div: int) -> None:
                    if not in_range or clip_offset_div is None:
                        return
                    events.append(NoteEvent(
                        start_beats=(start_div - off) / divisions,
                        dur_beats=(total_div / divisions) * float(DURATION_SCALE),
                        string_1_to_6=string_1_to_6,
                        fret=fret
                    ))

                if "start" in ttypes or "stop" in ttypes:
                    if "stop" in ttypes and key in open_ties:
                        start_onset_div, total_dur_div = open_ties[key]
                        total_dur_div += dur_div

                        if "start" in ttypes:
                            # stop+start（中継）
                            open_ties[key] = (start_onset_div, total_dur_div)
                        else:
                            # stopのみ（終端）
                            emit_note(start_onset_div, total_dur_div)
                            del open_ties[key]

                    elif "start" in ttypes and "stop" not in ttypes:
                        # startのみ（開始）
                        open_ties[key] = (onset, dur_div)

                    else:
                        # stopのみだが開始が無い等：壊れないよう単発として扱う
                        print(f"[warn] tie stop without open tie: measure {meas_no_text}, voice {v}, staff {st}, string {string_1_to_6}, fret {fret}")
                        # 単発ノートとして描く
                        if in_range and clip_offset_div is not None:
                            events.append(NoteEvent(
                                start_beats=(onset - off) / divisions,
                                dur_beats=(dur_div / divisions) * float(DURATION_SCALE),
                                string_1_to_6=string_1_to_6,
                                fret=fret
                            ))
                        # もし stop+start だったら「ここから開始」扱いにする
                        if "start" in ttypes:
                            open_ties[key] = (onset, dur_div)

                else:
                    # 通常ノート
                    if in_range and clip_offset_div is not None:
                        events.append(NoteEvent(
                            start_beats=(onset - off) / divisions,
                            dur_beats=(dur_div / divisions) * float(DURATION_SCALE),
                            string_1_to_6=string_1_to_6,
                            fret=fret
                        ))

                if advance_time:
                    cursor += dur_div

        # end_measure を超えたらここで打ち切りたい場合（measure番号が整数の時のみ）
        if end_measure is not None and meas_no is not None and meas_no >= end_measure:
            # ただし、end_measure内は処理したので break
            break

    # 未クローズ tie が残ったら末尾で閉じる（範囲内なら）
    for (v, st, s, f), (onset_div, total_div) in list(open_ties.items()):
        print(f"[warn] unterminated tie closed at end: voice {v}, staff {st}, string {s}, fret {f}")
        if clip_offset_div is not None:
            off = clip_offset_div
            events.append(NoteEvent(
                start_beats=(onset_div - off) / divisions,
                dur_beats=(total_div / divisions) * float(DURATION_SCALE),
                string_1_to_6=s,
                fret=f
            ))

    # クリップ範囲が一度も開始しなかった場合の保険
    if clip_offset_div is None:
        clip_offset_div = 0
        bar_number_base = start_measure if (start_measure is not None) else 1

    # bpm 決定：override > xml > fallback
    if BPM_OVERRIDE is not None:
        bpm = float(BPM_OVERRIDE)
    else:
        bpm_xml = extract_tempo_from_musicxml(root)
        bpm = float(bpm_xml) if bpm_xml is not None else float(bpm_fallback)

    time_sig_num0 = measure_segs[0].beats if measure_segs else time_sig_num
    return events, bpm, time_sig_num0, measure_segs, bar_number_base

def append_tail_measures(measure_segs: List[MeasureSeg], tail_measures: int) -> List[MeasureSeg]:
    if tail_measures <= 0 or not measure_segs:
        return measure_segs

    out = list(measure_segs)
    last = out[-1]

    # ダミー小節の長さは「拍子通りの名目長」を採用
    nominal_q = float(last.beats) * (4.0 / float(last.beat_type))

    # 次の小節番号（数値なら +1、無理なら "+")
    try:
        base_no = int(str(last.meas_no))
        next_no = base_no + 1
        fmt = "int"
    except Exception:
        next_no = None
        fmt = "str"

    start_q = float(last.start_q + last.dur_q)

    for i in range(tail_measures):
        meas_no = str(next_no + i) if fmt == "int" else f"{last.meas_no}+{i+1}"
        out.append(MeasureSeg(
            meas_no=meas_no,
            start_q=float(start_q),
            beats=int(last.beats),
            beat_type=int(last.beat_type),
            dur_q=float(nominal_q),
        ))
        start_q += nominal_q

    return out


# =========================
# レンダリング
# =========================
def compute_lane_centers(n_strings: int) -> List[int]:
    n = int(n_strings)
    top = MARGIN_TOP
    bottom = HEIGHT - MARGIN_BOTTOM
    usable = max(1, bottom - top)

    # n本の中心位置を等間隔に配置
    step = usable / (n - 1) if n > 1 else 0
    return [int(round(top + i * step)) for i in range(n)]

def render_video(notes: List[NoteEvent], out_mp4: str,
                 bpm: float, measure_segs: int, bar_number_base: int, tail_measures: int = 1,
                 bar_width_px: Optional[float] = None) -> None:
    lane_centers = compute_lane_centers(STRINGS)
    font = load_font(FONT_SIZE)

    sec_per_q = seconds_per_beat(bpm)  # 四分=1 の秒
    
    # ノートの“見た目”終端（すでに dur_beats は DURATION_SCALE を含んだ見た目長のはず）
    last_note_end_q = 0.0
    if notes:
        last_note_end_q = max(float(n.start_beats + n.dur_beats) for n in notes)
    
    measure_segs2 = append_tail_measures(measure_segs, tail_measures)

    # グリッドの終端（最後のsegの start + dur）
    last_grid_end_q = 0.0
    if measure_segs2:
        last = measure_segs2[-1]
        last_grid_end_q = float(last.start_q + last.dur_q)
    
    # どちらか長い方に合わせる（最後のバーがプレイヘッド通過まで出る）
    total_q = max(last_note_end_q, last_grid_end_q)
    
    # ここに PRE_ROLL を足して総秒数
    total_sec = float(PRE_ROLL_SECONDS) + total_q * sec_per_q

        # スクロール速度（px/sec）
    # 優先: bar_width_px（1小節=何と思うpx）
    # フォールバック: lookahead（右端→プレイヘッド到達秒）
    if bar_width_px is not None:
        # 1拍あたりのpx = (1小節px) / (拍子分子)
        # bar_width_px は「4/4（四分×4）の1小節分の幅」と定義する
        px_per_quarter = float(bar_width_px) / 4.0
        
        # seconds_per_beat(bpm) は四分音符1つの秒（=sec_per_quarter）
        sec_per_quarter = seconds_per_beat(bpm)
        
        speed = px_per_quarter / sec_per_quarter  # px/sec
    else:
        speed = (WIDTH - MARGIN_RIGHT - PLAYHEAD_X) / float(LOOKAHEAD_SECONDS)

    # 尺（最後のノート終端 + 余韻）
    last_end_beats = 0.0
    for n in notes:
        last_end_beats = max(last_end_beats, n.start_beats + n.dur_beats)

    start_sec = -float(PRE_ROLL_SECONDS)
    end_sec = beats_to_seconds(last_end_beats, bpm) + 2.0
    total_sec = end_sec - start_sec
    total_frames = int(math.ceil(total_sec * FPS))

    with tempfile.TemporaryDirectory(prefix="tab_highway_frames_") as td:
        for frame_idx in range(total_frames):
            now_sec = start_sec + frame_idx / FPS

            im = Image.new("RGB", (WIDTH, HEIGHT), BG_COLOR)
            draw = ImageDraw.Draw(im)

            draw_lanes(draw, lane_centers)
            draw_grid(draw, now_sec, speed, bpm, measure_segs2)
            draw_playhead(draw)

            for n in notes:
                t0 = beats_to_seconds(n.start_beats, bpm)
                t1 = beats_to_seconds(n.start_beats + n.dur_beats, bpm)

                x0 = x_for_time(t0, now_sec, speed)
                x1 = x_for_time(t1, now_sec, speed)

                # 画面外はスキップ
                if x1 < MARGIN_LEFT - 50 or x0 > WIDTH + 50:
                    continue

                y = string_to_y(n.string_1_to_6, lane_centers)
                fill = fret_to_color(n.fret, fret_min=0, fret_max=24)
                draw_note(draw, y, x0, x1, n.fret, font, NOTE_BAR_HEIGHT, fill)

            frame_path = os.path.join(td, f"frame_{frame_idx+1:06d}.png")
            im.save(frame_path)

        run_ffmpeg_encode(td, FPS, out_mp4)

    print(f"OK: {out_mp4}")


# =========================
# 直書きデータ（テスト用）
# =========================

def demo_notes() -> List[NoteEvent]:
    # 例：同時和音（開始拍が同じ）を複数弦に置くだけ
    return [
        # 1拍目に 6弦0 と 5弦2（あなたの断片に合わせた感じ）
        NoteEvent( start_beats=0.0, dur_beats=0.5, string_1_to_6=6, fret=0 ),
        NoteEvent( start_beats=0.0, dur_beats=0.5, string_1_to_6=5, fret=2 ),

        # 2拍目に同様（長め）
        NoteEvent( start_beats=1.0, dur_beats=1.0, string_1_to_6=6, fret=0 ),
        NoteEvent( start_beats=1.0, dur_beats=1.0, string_1_to_6=5, fret=2 ),

        # 3拍目に 4弦1 + 5弦2
        NoteEvent( start_beats=2.0, dur_beats=0.5, string_1_to_6=4, fret=1 ),
        NoteEvent( start_beats=2.0, dur_beats=0.5, string_1_to_6=5, fret=2 ),
    ]

def main() -> None:
    # グローバル設定をCLIで上書きする
    global OUT_MP4, MUSICXML_PATH, USE_MUSICXML
    global BPM_OVERRIDE, BPM_DEFAULT
    global WIDTH, HEIGHT, FPS
    global FONT_SIZE, NOTE_BAR_HEIGHT, PRE_ROLL_SECONDS, LOOKAHEAD_SECONDS, DURATION_SCALE
    global MARGIN_LEFT, MARGIN_RIGHT, MARGIN_TOP, MARGIN_BOTTOM
    global PLAYHEAD_X
    global BG_COLOR
    global THEME
    global NOTE_OUTLINE_PX, NOTE_OUTLINE_RGB
    global LINE_OUTLINE_PX, LINE_OUTLINE_RGB
    global LANE_COLOR, BEAT_LINE_COLOR, BAR_LINE_COLOR, PLAYHEAD_COLOR
    global STRING_LABEL_COLOR, BAR_LABEL_COLOR
    global STRINGS, OPEN_MIDI




    ap = argparse.ArgumentParser(description="TAB highway renderer (MusicXML -> MP4)")

    # 入出力
    ap.add_argument("--xml", dest="xml_path", default=None, help="Input MusicXML path")
    ap.add_argument("--out", dest="out_mp4", default=OUT_MP4, help="Output MP4 path")

    # 楽譜選択
    ap.add_argument("--part", dest="part_id", default=None, help="Target part id (e.g. P2). Omit to auto-detect TAB part.")
    ap.add_argument("--voice", dest="voice", default="1", help="Target voice (default: 1)")
    ap.add_argument("--staff", dest="staff", default="1", help="Target staff (default: 1)")

    # テンポ
    ap.add_argument("--bpm", dest="bpm", default=None, type=float,
                    help="Override tempo (e.g. 140). If omitted, uses BPM_OVERRIDE / XML / default.")
    ap.add_argument("--bpm-default", dest="bpm_default", default=BPM_DEFAULT, type=float,
                    help="Fallback tempo if neither --bpm nor XML tempo exists.")

    # 映像
    ap.add_argument("--width", dest="width", type=int, default=WIDTH, help="Video width")
    ap.add_argument("--height", dest="height", type=int, default=HEIGHT, help="Video height")
    ap.add_argument("--fps", dest="fps", type=int, default=FPS, help="Frames per second")

    # 見た目
    ap.add_argument("--font", dest="font_size", type=int, default=FONT_SIZE, help="Fret number font size")
    ap.add_argument("--barh", dest="bar_height", type=int, default=NOTE_BAR_HEIGHT, help="Note bar height (thickness)")
    ap.add_argument("--preroll", dest="preroll", type=float, default=PRE_ROLL_SECONDS, help="Pre-roll seconds before first note")
    ap.add_argument("--lookahead", dest="lookahead", type=float, default=LOOKAHEAD_SECONDS,
                    help="Seconds for notes to travel from right edge to playhead (bigger=slower)")
    ap.add_argument("--dur-scale", dest="dur_scale", type=float, default=DURATION_SCALE,
                    help="Visual duration scale (1.0=real time).")
    ap.add_argument("--playhead", dest="playhead_ratio", type=float, default=(PLAYHEAD_X / WIDTH if WIDTH else 0.25),
                    help="Playhead X position as ratio of width (default ~0.25).")

    # マージン
    ap.add_argument("--margin-left", dest="m_left", type=int, default=MARGIN_LEFT)
    ap.add_argument("--margin-right", dest="m_right", type=int, default=MARGIN_RIGHT)
    ap.add_argument("--margin-top", dest="m_top", type=int, default=MARGIN_TOP)
    ap.add_argument("--margin-bottom", dest="m_bottom", type=int, default=MARGIN_BOTTOM)

    # Start/End Measure
    ap.add_argument("--start-measure", dest="start_measure", type=int, default=None,
                    help="Start measure number (inclusive)")
    ap.add_argument("--end-measure", dest="end_measure", type=int, default=None,
                    help="End measure number (inclusive)")
    
    ap.add_argument("--bar-width", dest="bar_width", type=float, default=None,
                help="Measure width in pixels (overrides --lookahead). e.g. 900 means 1 bar = 900px.")

    ap.add_argument("--fret-min", dest="fret_min", type=int, default=0)
    ap.add_argument("--fret-max", dest="fret_max", type=int, default=24)
    
    ap.add_argument("--bg", dest="bg", default=None,
                help="Background color as hex RRGGBB (e.g. FFFFFF or #FFFFFF)")
    
    ap.add_argument("--theme", dest="theme", default="auto",
                choices=["auto", "light", "dark"],
                help="Foreground theme. Does not change background color.")

    ap.add_argument("--outline", dest="outline", type=int, default=2,
                    help="Note outline width in pixels (0 disables)")
    ap.add_argument("--outline-color", dest="outline_color", default="auto",
                    help="Note outline color hex RRGGBB, or 'auto' to follow theme")
    
    ap.add_argument("--line-outline", dest="line_outline", type=int, default=2,
                    help="Outline width for lanes/grid/playhead (0 disables)")
    ap.add_argument("--line-outline-color", dest="line_outline_color", default="auto",
                    help="Line outline color hex RRGGBB, or 'auto' to follow theme")
    
    ap.add_argument("--audio", action="store_true", help="Generate guitar+metronome audio and mux into mp4")
    ap.add_argument("--no-metronome", action="store_true", help="Disable metronome track")
    ap.add_argument("--soundfont", default=None, help="Path to .sf2 SoundFont")
    ap.add_argument("--gm", type=int, default=26, help="GM program number (1-based). 25=nylon, 26=steel (default 26)")
    ap.add_argument("--gain", type=float, default=AUDIO_GAIN, help="FluidSynth gain")
    ap.add_argument("--sr", type=int, default=AUDIO_SAMPLE_RATE, help="Audio sample rate")
    ap.add_argument("--strings", type=int, default=6, help="Number of strings (e.g. 4 for bass)")
    ap.add_argument("--tail-measures", type=int, default=1,
                    help="Append N dummy measures after end so last note passes playhead (default 1)")


    args = ap.parse_args()

    # --- CLI値を反映 ---
    OUT_MP4 = args.out_mp4

    WIDTH = int(args.width)
    HEIGHT = int(args.height)
    FPS = int(args.fps)

    FONT_SIZE = int(args.font_size)
    NOTE_BAR_HEIGHT = int(args.bar_height)
    PRE_ROLL_SECONDS = float(args.preroll)
    LOOKAHEAD_SECONDS = float(args.lookahead)
    DURATION_SCALE = float(args.dur_scale)

    MARGIN_LEFT = int(args.m_left)
    MARGIN_RIGHT = int(args.m_right)
    MARGIN_TOP = int(args.m_top)
    MARGIN_BOTTOM = int(args.m_bottom)
    
    STRINGS = max(1, int(args.strings))
    OPEN_MIDI = default_open_midi_for_strings(STRINGS)


    # playhead_ratio を clamp
    r = float(args.playhead_ratio)
    if not (0.05 <= r <= 0.95):
        raise ValueError("--playhead は 0.05〜0.95 の範囲で指定してください（例: 0.25）")
    PLAYHEAD_X = int(WIDTH * r)

    BPM_DEFAULT = float(args.bpm_default)

    # --bpm が指定されていれば最優先
    if args.bpm is not None:
        BPM_OVERRIDE = float(args.bpm)
    # 指定が無いなら、スクリプト内の BPM_OVERRIDE（設定値）をそのまま使う
    # （BPM_OVERRIDE=None にしておけば XML→default の順になる）

    # 入力ファイル指定
    if args.xml_path is not None:
        USE_MUSICXML = True
        MUSICXML_PATH = args.xml_path
        
    if args.bg is not None:
        BG_COLOR = parse_hex_rgb(args.bg)
    # テーマ適用（前景のみ。背景は変えない）
    THEME = args.theme
    apply_theme(THEME, BG_COLOR)
    
    # アウトライン設定（色が "auto" ならテーマに追随）
    NOTE_OUTLINE_PX = max(0, int(args.outline))
    LINE_OUTLINE_PX = max(0, int(args.line_outline))
    
    if (args.outline_color or "").lower() == "auto":
        NOTE_OUTLINE_RGB = theme_default_outline_rgb(THEME, BG_COLOR)
    else:
        NOTE_OUTLINE_RGB = parse_hex_rgb(args.outline_color)
    
    if (args.line_outline_color or "").lower() == "auto":
        LINE_OUTLINE_RGB = theme_default_outline_rgb(THEME, BG_COLOR)
    else:
        LINE_OUTLINE_RGB = parse_hex_rgb(args.line_outline_color)
    

    # --- 実行 ---
    if USE_MUSICXML:
        if os.path.exists(MUSICXML_PATH):
            with open(MUSICXML_PATH, "r", encoding="utf-8") as f:
                xml_text = f.read()
        else:
            # ファイルが無い場合はスニペットから（デバッグ用）
            xml_text = normalize_musicxml_snippet(MUSICXML_SNIPPET)

        root = ET.fromstring(xml_text)

        # part id 決定（指定 > 自動 > P2）
        part_id = args.part_id if args.part_id else choose_tab_part_id(root, fallback="P2")

        notes, bpm, time_sig_num, measure_segs, bar_base = parse_musicxml_notes(
            xml_text,
            target_part_id=part_id,
            bpm_fallback=args.bpm,
            start_measure=args.start_measure,
            end_measure=args.end_measure,
        )

        if not notes:
            raise RuntimeError(
                f"MusicXMLからノートが取れませんでした。"
                f" part={part_id} voice={args.voice} staff={args.staff} の指定と"
                f" technical(string/fret) の有無を確認してください。"
            )

        print(f"Parsed notes: {len(notes)}, part={part_id}, bpm={bpm}, "
              f"time_sig_num0={time_sig_num}, measure_segs={len(measure_segs)}")
        render_video(notes, OUT_MP4,
                     bpm=bpm,
                     measure_segs=measure_segs,
                     bar_number_base=bar_base,
                     bar_width_px=args.bar_width,
                     tail_measures=args.tail_measures)
    else:
        notes = demo_notes()
        bpm = BPM_DEFAULT if (BPM_OVERRIDE is None) else float(BPM_OVERRIDE)
        render_video(notes, OUT_MP4, bpm=bpm, time_sig_num=4)
    
    # --- Audio pipeline (optional) ---
    if args.audio:
        # パス決定
        out_video = OUT_MP4
        base = str(Path(out_video).with_suffix(""))
        mid_path = base + ".mid"
        wav_path = base + ".wav"
        muxed_path = base + "_audio.mp4"
    
        sf2 = args.soundfont if args.soundfont else SOUNDFONT_PATH
        program_0based = max(0, int(args.gm) - 1)

        write_midi(
            notes=notes,
            out_mid=mid_path,
            bpm=bpm,
            measure_segs=measure_segs,
            program_0based=program_0based,
            include_metronome=(not args.no_metronome)
        )
        midi_to_wav(mid_path, wav_path, soundfont=sf2, samplerate=int(args.sr), gain=float(args.gain))
        mux_audio(out_video, wav_path, muxed_path)
        print(f"[audio] wrote: {muxed_path}")


if __name__ == "__main__":
    main()
