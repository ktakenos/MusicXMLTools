#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import math
import re
import subprocess
import shutil
import time
import cv2
import numpy as np
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import List, Optional, Tuple

# =========================
# ユーザー設定
# =========================
PIVOT = (773, 721)     # 回転支点
TILT_MAX_DEG = 12.0    # 左右最大角度

WINK_DEFAULT_SEC = 0.15
MOVE_SEC_FAST = 0.20
MOVE_SEC_SLOW = 0.55
DWELL_SEC = 0.15
FPS_DEFAULT = 30.0

# ガンマ自動補正の制限
GAMMA_MIN = 0.70
GAMMA_MAX = 1.45

# =========================
# データ構造
# =========================
@dataclass
class CtrlEvent:
    t: float
    name: str
    sec: Optional[float] = None
    beats: Optional[float] = None
    
@dataclass
class NoteSeg:
    t0: float
    t1: float
    vowel: str  # A/I/U/E/O or N


# =========================
# ひらがな→母音
# =========================
VOWELS = {
    "A": set("あかさたなはまやらわがざだばぱぁゃ"),
    "I": set("いきしちにひみりぎじぢびぴぃ"),
    "U": set("うくすつぬふむゆるぐずづぶぷぅゅ"),
    "E": set("えけせてねへめれげぜでべぺぇ"),
    "O": set("おこそとのほもよろをごぞどぼぽぉょ"),
}
SMALL = set("ゃゅょぁぃぅぇぉ")
LONG = "ー"

def lyric_to_vowel(text: Optional[str]) -> str:
    t = (text or "").strip()
    if not t or t == "ん":
        return "N"
    for c in reversed(t):
        if c == LONG or c in SMALL:
            continue
        for k, s in VOWELS.items():
            if c in s:
                return k
    return "N"

# =========================
# 画像読み込み・合成
# =========================
def load_rgba(path: str) -> np.ndarray:
    im = cv2.imread(path, cv2.IMREAD_UNCHANGED)
    if im is None:
        raise FileNotFoundError(path)
    if im.ndim == 2:
        im = cv2.cvtColor(im, cv2.COLOR_GRAY2BGRA)
    elif im.shape[2] == 3:
        im = cv2.cvtColor(im, cv2.COLOR_BGR2BGRA)
    return im

def ensure_size(im: np.ndarray, w: int, h: int) -> np.ndarray:
    if im.shape[1] == w and im.shape[0] == h:
        return im
    return cv2.resize(im, (w, h), interpolation=cv2.INTER_LINEAR)

def alpha_blend(dst: np.ndarray, src: np.ndarray) -> np.ndarray:
    """dst, src: BGRA (dst is modified and returned)"""
    a = (src[..., 3:4].astype(np.float32) / 255.0)
    dst[..., :3] = (1.0 - a) * dst[..., :3] + a * src[..., :3]
    return dst

def rotate_rgba(img: np.ndarray, deg: float) -> np.ndarray:
    if abs(deg) < 1e-6:
        return img
    M = cv2.getRotationMatrix2D(PIVOT, deg, 1.0)
    return cv2.warpAffine(
        img, M, (img.shape[1], img.shape[0]),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0, 0),
    )

def rotate_rgba_roi(img_roi: np.ndarray, deg: float, pivot_roi) -> np.ndarray:
    if abs(deg) < 1e-6:
        return img_roi
    cx = float(pivot_roi[0])
    cy = float(pivot_roi[1])
    M = cv2.getRotationMatrix2D((cx, cy), float(deg), 1.0)
    return cv2.warpAffine(
        img_roi, M, (img_roi.shape[1], img_roi.shape[0]),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=(0, 0, 0, 0),
    )

def auto_roi_from_alpha(img_bgra: np.ndarray, pad: int = 80):
    a = img_bgra[..., 3]
    ys, xs = np.where(a > 0)
    if len(xs) == 0 or len(ys) == 0:
        return 0, 0, img_bgra.shape[1], img_bgra.shape[0]
    x0, x1 = xs.min(), xs.max() + 1
    y0, y1 = ys.min(), ys.max() + 1
    x0 = max(0, x0 - pad)
    y0 = max(0, y0 - pad)
    x1 = min(img_bgra.shape[1], x1 + pad)
    y1 = min(img_bgra.shape[0], y1 + pad)
    return x0, y0, x1, y1

def alpha_bbox(img_bgra: np.ndarray, thr: int = 1):
    a = img_bgra[..., 3]
    ys, xs = np.where(a >= thr)
    if xs.size == 0 or ys.size == 0:
        return None  # fully transparent
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    return (x0, y0, x1, y1)

def alpha_blend_bbox(dst: np.ndarray, src: np.ndarray, bbox):
    if bbox is None:
        return dst
    x0, y0, x1, y1 = bbox
    d = dst[y0:y1, x0:x1]
    s = src[y0:y1, x0:x1]

    a = (s[..., 3:4].astype(np.float32) / 255.0)
    d[..., :3] = (1.0 - a) * d[..., :3] + a * s[..., :3]
    dst[y0:y1, x0:x1] = d
    return dst

# =========================
# ガンマ補正（キャラ側）
# =========================
def mean_luma_bgr(bgr: np.ndarray, alpha: Optional[np.ndarray] = None) -> float:
    """bgr: uint8 BGR, alpha: uint8 (0-255) or None"""
    b = bgr[..., 0].astype(np.float32) / 255.0
    g = bgr[..., 1].astype(np.float32) / 255.0
    r = bgr[..., 2].astype(np.float32) / 255.0
    y = 0.114*b + 0.587*g + 0.299*r
    if alpha is None:
        return float(np.mean(y))
    m = (alpha.astype(np.float32) / 255.0)
    w = np.sum(m)
    if w <= 1e-6:
        return float(np.mean(y))
    return float(np.sum(y * m) / w)

def apply_gamma_rgba(img: np.ndarray, gamma: float) -> np.ndarray:
    """BGRA uint8 -> BGRA uint8 (RGBにのみ適用)"""
    out = img.copy()
    rgb = out[..., :3].astype(np.float32) / 255.0
    rgb = np.clip(rgb, 0.0, 1.0) ** gamma
    out[..., :3] = (rgb * 255.0 + 0.5).astype(np.uint8)
    return out

def auto_gamma_from_bg(bg_bgra: np.ndarray, char_rgba_list: List[np.ndarray]) -> float:
    """背景の平均輝度に、キャラの平均輝度を寄せるガンマを推定"""
    bg_bgr = bg_bgra[..., :3]
    bg_l = mean_luma_bgr(bg_bgr)  # 0..1

    # キャラ側は「非透明部分」だけで平均輝度
    char_ls = []
    for im in char_rgba_list:
        bgr = im[..., :3]
        a = im[..., 3]
        char_ls.append(mean_luma_bgr(bgr, a))
    char_l = float(np.mean(char_ls)) if char_ls else 0.5

    # 目標は背景の少し上（キャラが埋もれない）
    target = min(0.95, max(0.08, bg_l * 1.05))

    # gamma: char_l**gamma = target  => gamma = log(target)/log(char_l)
    eps = 1e-4
    cl = min(0.99, max(eps, char_l))
    tg = min(0.99, max(eps, target))
    gamma = math.log(tg) / math.log(cl)
    gamma = max(GAMMA_MIN, min(GAMMA_MAX, gamma))
    return gamma

# =========================
# CTRL words パース（CTRL:NAME[:seconds]）スペース許容
# =========================
VALID_NAMES = {
    "WINK",
    "EYE_AUTO",
    "CLOSE_EYES",
    "OPEN_EYES",
    "TILT_L",
    "TILT_R",
    "TILT_0",
    "TILT_C",
    "SPEED_SLOW",
    "SPEED_FAST",
}
_CTRL_RE = re.compile(r"^\s*CTRL:\s*([A-Za-z_]+)\s*(?::\s*([0-9]*\.?[0-9]+)\s*([bB])?\s*)?\s*$")

def parse_ctrl(words: str) -> Optional[Tuple[str, Optional[float], Optional[float]]]:
    m = _CTRL_RE.match(words or "")
    if not m:
        return None
    name = m.group(1).upper()
    if name not in VALID_NAMES:
        return None

    val = m.group(2)
    is_beat = m.group(3) is not None  # 'b' が付いていたら拍

    if val is None:
        return name, None, None

    v = float(val)
    if is_beat:
        return name, None, v   # sec=None, beats=v
    else:
        return name, v, None   # sec=v, beats=None

from typing import List, Optional, Tuple

def parse_musicxml(
    path: str,
    default_bpm: float = 120.0,
    start_measure: int = 1,
    end_measure: Optional[int] = None
) -> Tuple[float, List[NoteSeg], List[CtrlEvent], float, float]:
    """
    Returns:
      total_sec:          duration of selected range (seconds)
      notes:              NoteSeg list with times relative to range start (t=0 at start_measure head)
      events:             CtrlEvent list with times relative to range start
      bpm_at_start:       BPM effective at the head of start_measure
      start_offset_sec:   seconds from song start to start_measure head (for trimming WAV by -ss)
    """

    tree = ET.parse(path)
    root = tree.getroot()

    parts = root.findall(".//part")
    if not parts:
        raise RuntimeError("No <part> in MusicXML")
    part = parts[0]

    if start_measure < 1:
        start_measure = 1

    divisions = 1
    beats, beat_type = 4, 4

    def measure_quarters() -> float:
        # defensive fallback
        b = beats if isinstance(beats, (int, float)) and beats else 4
        bt = beat_type if isinstance(beat_type, (int, float)) and beat_type else 4
        return float(b) * (4.0 / float(bt))

    # current tempo (can change while scanning measures)
    bpm = float(default_bpm)
    bpm_at_start: Optional[float] = None

    # absolute time from song start (seconds)
    t = 0.0
    start_offset_sec: Optional[float] = None

    notes: List[NoteSeg] = []
    events: List[CtrlEvent] = []

    measures = part.findall("./measure")
    for idx, measure in enumerate(measures, start=1):

        # ----- Update tempo if this measure contains <sound tempo="..."> -----
        # (handles mid-song tempo changes and ensures start_measure picks correct BPM)
        for s in measure.iter():
            if s.tag.endswith("sound") and "tempo" in getattr(s, "attrib", {}):
                try:
                    bpm = float(s.attrib["tempo"])
                except Exception:
                    pass  # ignore malformed tempo

        # If we've reached the start measure, record both offset and bpm-at-start
        if idx == start_measure:
            start_offset_sec = t
            bpm_at_start = bpm

        # ----- Update attributes (divisions, time sig) if present -----
        attrs = measure.find("./attributes")
        if attrs is not None:
            d = attrs.find("./divisions")
            if d is not None and d.text:
                try:
                    divisions = int(d.text.strip())
                except Exception:
                    pass

            tm = attrs.find("./time")
            if tm is not None:
                b_txt = tm.findtext("beats")
                bt_txt = tm.findtext("beat-type")
                try:
                    if b_txt is not None and bt_txt is not None:
                        b_val = int(b_txt.strip())
                        bt_val = int(bt_txt.strip())
                        if b_val > 0 and bt_val > 0:
                            beats, beat_type = b_val, bt_val
                except Exception:
                    # keep previous beats/beat_type
                    pass

        sec_per_quarter = 60.0 / float(bpm)  # quarter-note seconds at *current* tempo

        # If we're past the selected range, stop (but only after offset captured)
        if end_measure is not None and idx > end_measure:
            break

        # If we're before the selected range, we still must advance time correctly.
        # Easiest & safest: process notes/rests durations if they exist; otherwise fall back to full-measure rest.
        if idx < start_measure:
            measure_q = 0.0
            had_duration_note = False

            for ch in list(measure):
                tag = ch.tag.split("}")[-1]
                if tag != "note":
                    continue
                dur = ch.findtext("./duration")
                if dur is None:
                    continue
                try:
                    q = int(dur.strip()) / float(divisions)
                except Exception:
                    continue
                had_duration_note = True
                measure_q += q
                t += (q * sec_per_quarter)

            if not had_duration_note:
                # whole-measure rest
                t += (measure_quarters() * sec_per_quarter)
            else:
                # pad remainder to measure length
                rem = measure_quarters() - measure_q
                if rem > 1e-6:
                    t += (rem * sec_per_quarter)

            continue  # do not record notes/events outside range

        # Now we are within the selected range (start_measure .. end_measure)
        if start_offset_sec is None:
            # should not happen, but keep safe
            start_offset_sec = 0.0
        t_rel = t - start_offset_sec

        qlen = measure_quarters()
        measure_q = 0.0
        had_duration_note = False

        for ch in list(measure):
            tag = ch.tag.split("}")[-1]

            if tag == "direction":
                words = ch.findtext("./direction-type/words") or ""
                parsed = parse_ctrl(words)
                if parsed:
                    name, sec, ctrl_beats = parsed
                    events.append(CtrlEvent(t=t_rel, name=name, sec=sec, beats=ctrl_beats))
                continue

            if tag != "note":
                continue

            dur = ch.findtext("./duration")
            if dur is None:
                continue

            try:
                q = int(dur.strip()) / float(divisions)
            except Exception:
                continue

            dt = q * sec_per_quarter
            had_duration_note = True
            measure_q += q

            is_rest = (ch.find("./rest") is not None)
            if is_rest:
                notes.append(NoteSeg(t0=t_rel, t1=t_rel + dt, vowel="N"))
                t += dt
                t_rel += dt
                continue

            lyric = ch.findtext("./lyric/text")
            v = lyric_to_vowel(lyric)
            notes.append(NoteSeg(t0=t_rel, t1=t_rel + dt, vowel=v))

            t += dt
            t_rel += dt

        # Fill measure if needed
        if not had_duration_note:
            dt = qlen * sec_per_quarter
            notes.append(NoteSeg(t0=t_rel, t1=t_rel + dt, vowel="N"))
            t += dt
            t_rel += dt
        else:
            rem = qlen - measure_q
            if rem > 1e-6:
                dt = rem * sec_per_quarter
                notes.append(NoteSeg(t0=t_rel, t1=t_rel + dt, vowel="N"))
                t += dt
                t_rel += dt

    if start_offset_sec is None:
        start_offset_sec = 0.0
    if bpm_at_start is None:
        bpm_at_start = float(default_bpm)

    total_sec = max(0.0, t - start_offset_sec)
    events.sort(key=lambda e: e.t)

    return total_sec, notes, events, float(bpm_at_start), float(start_offset_sec)

# =========================
# Tiltアニメ
# =========================
def smoothstep(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x*x*(3 - 2*x)

@dataclass
class TiltAnim:
    current: float = 0.0
    start: float = 0.0
    target: float = 0.0
    t0: float = 0.0
    move_sec: float = MOVE_SEC_SLOW
    dwell_sec: float = DWELL_SEC
    phase: str = "IDLE"  # MOVE / DWELL / IDLE

    def set_target(self, now: float, target: float, move_sec: float):
        self.current = self.value(now)
        self.start = self.current
        self.target = target
        self.t0 = now
        self.move_sec = max(1e-3, move_sec)
        self.phase = "MOVE"

    def value(self, now: float) -> float:
        if self.phase == "IDLE":
            return self.current

        dt = now - self.t0
        if self.phase == "MOVE":
            if dt >= self.move_sec:
                self.current = self.target
                self.t0 = self.t0 + self.move_sec
                self.phase = "DWELL" if self.dwell_sec > 1e-6 else "IDLE"
                return self.current
            u = dt / self.move_sec
            s = smoothstep(u)
            return self.start + (self.target - self.start) * s

        if self.phase == "DWELL":
            if dt >= self.dwell_sec:
                self.current = self.target
                self.phase = "IDLE"
            return self.target

        return self.current

# =========================
# ノート状態取得
# =========================
def vowel_at_time(notes: List[NoteSeg], t: float) -> str:
    for seg in notes:
        if seg.t0 <= t < seg.t1:
            return seg.vowel
    return "N"

# =========================
# WAVをMP4へmux
# =========================
def mux_wav_segment(video_mp4: str, wav_path: str, out_mp4: str, start_sec: float, dur_sec: float) -> None:
    cmd = [
        "ffmpeg", "-y",
        "-i", video_mp4,
        "-ss", f"{start_sec:.6f}",
        "-t",  f"{dur_sec:.6f}",
        "-i", wav_path,
        "-c:v", "copy",
        "-c:a", "aac",
        "-shortest",
        out_mp4,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{r.stderr}")

# =========================
# main
# =========================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("musicxml")
    ap.add_argument("--out", default="out.mp4", help="final output (with wav if specified)")
    ap.add_argument("--tmp-video", default="_tmp_silent.mp4", help="intermediate silent video")
    ap.add_argument("--fps", type=float, default=FPS_DEFAULT)
    ap.add_argument("--bpm", type=float, default=120.0, help="fallback tempo")
    ap.add_argument("--wav", default=None, help="wav file to mux (optional)")
    ap.add_argument("--bg", default=None, help="background image (png/jpg). optional")
    ap.add_argument("--tilt-lead-beats", type=float, default=None,
                help="If set, start tilts earlier by this many beats so peak hits the beat-head (move_sec fixed accordingly).")


    # ★追加：小節範囲
    ap.add_argument("--start-measure", type=int, default=1, help="1-based measure index to start")
    ap.add_argument("--end-measure", type=int, default=None, help="1-based measure index to end (inclusive)")

    # ★追加：進捗表示頻度（秒）
    ap.add_argument("--progress-sec", type=float, default=1.0, help="print progress every N seconds (approx)")

    # ★追加：ガンマ自動調整ON/OFF
    ap.add_argument("--auto-gamma", action="store_true", help="auto gamma to match background brightness")
    ap.add_argument("--pivot", default=None,
                    help="Rotation pivot as 'x,y' in pixels. Default: use built-in PIVOT constant.")
    ap.add_argument("--roi", default=None,
                    help="Head ROI as 'WxH' (e.g. 792x763). Default: use built-in ROI_W/ROI_H.")


    args = ap.parse_args()

    def parse_pivot(s: str) -> tuple[int, int]:
        x_str, y_str = s.split(",")
        return int(float(x_str.strip())), int(float(y_str.strip()))

    def parse_roi(s: str) -> tuple[int, int]:
        w_str, h_str = s.lower().split("x")
        return int(w_str.strip()), int(h_str.strip())

    # images
    body = load_rgba("body.png")
    head_base = load_rgba("head_base.png")
    mouth = {k: load_rgba(f"mouth_{k}.png") for k in ["A","I","U","E","O"]}
    eye_wink = load_rgba("eye_wink.png")
    eye_close = load_rgba("eye_close.png")

    H, W = body.shape[:2]
    
    
    # ---- ROI (pivot centered) ----
    ROI_W = 792
    ROI_H = 763
    
    # ---- pivot override ----
    pivot = PIVOT
    if args.pivot:
        pivot = parse_pivot(args.pivot)
    
    # ---- ROI override ----
    roi_w, roi_h = ROI_W, ROI_H
    if args.roi:
        roi_w, roi_h = parse_roi(args.roi)

    x0, y0, x1, y1 = auto_roi_from_alpha(head_base, pad=120)
    ROI_W = x1 - x0
    ROI_H = y1 - y0
    PIVOT_ROI = (int(pivot[0] - x0), int(pivot[1] - y0))
    print("PIVOT_ROI=", PIVOT_ROI, type(PIVOT_ROI[0]), type(PIVOT_ROI[1]))



    # background
    bg = None
    if args.bg:
        bg = load_rgba(args.bg)
        bg = ensure_size(bg, W, H)

    # resize overlays to body size
    head_base = ensure_size(head_base, W, H)
    eye_wink = ensure_size(eye_wink, W, H)
    eye_close = ensure_size(eye_close, W, H)
    for k in list(mouth.keys()):
        mouth[k] = ensure_size(mouth[k], W, H)

    # ---- Crop head-related layers to ROI (BGRA) ----
    head_base_roi = head_base[y0:y1, x0:x1].copy()
    eye_wink_roi  = eye_wink[y0:y1, x0:x1].copy()
    eye_close_roi = eye_close[y0:y1, x0:x1].copy()
    
    mouth_roi = {k: mouth[k][y0:y1, x0:x1].copy() for k in ["A","I","U","E","O"]}

    bbox_head = alpha_bbox(head_base_roi)  # 普通はROI全域のはずだが一応
    bbox_eye_wink  = alpha_bbox(eye_wink_roi)
    bbox_eye_close = alpha_bbox(eye_close_roi)
    bbox_mouth = {k: alpha_bbox(mouth_roi[k]) for k in mouth_roi.keys()}


    # ★ガンマ自動調整（背景がある場合のみ意味がある）
    if args.auto_gamma and bg is not None:
        gamma = auto_gamma_from_bg(bg, [body, head_base, eye_wink, eye_close, *mouth.values()])
        print(f"[auto-gamma] gamma={gamma:.3f} (clamped {GAMMA_MIN}-{GAMMA_MAX})")
        body = apply_gamma_rgba(body, gamma)
        head_base = apply_gamma_rgba(head_base, gamma)
        eye_wink = apply_gamma_rgba(eye_wink, gamma)
        eye_close = apply_gamma_rgba(eye_close, gamma)
        for k in list(mouth.keys()):
            mouth[k] = apply_gamma_rgba(mouth[k], gamma)

    total_sec, notes, events, bpm_at_start, start_offset_sec = parse_musicxml(
        args.musicxml,
        default_bpm=args.bpm,
        start_measure=args.start_measure,
        end_measure=args.end_measure
    )
    sec_per_beat = 60.0 / float(bpm_at_start)  # 四分=1拍

    if args.tilt_lead_beats is not None:
        if args.tilt_lead_beats <= 0:
            raise ValueError("--tilt-lead-beats must be > 0")
    
        lead_sec = None
        if args.tilt_lead_beats is not None:
            sec_per_beat = 60.0 / bpm_at_start
            lead_sec = sec_per_beat * args.tilt_lead_beats
            move_sec = max(1e-3, lead_sec)
            for e in events:
                if e.name in ("TILT_L","TILT_R","TILT_C","TILT_0"):
                    e.t = max(0.0, e.t - lead_sec)
            events.sort(key=lambda e: e.t)
    
        print(f"[tilt-lead] bpm={bpm_at_start:.3f} sec_per_beat={sec_per_beat:.4f} "
              f"lead_beats={args.tilt_lead_beats:.3f} => lead_sec={lead_sec:.4f}s (events shifted earlier, move_sec fixed)")

    tilt = TiltAnim(current=0.0)
    move_sec = MOVE_SEC_SLOW
    eye_auto_until = -1.0
    open_until = -1.0
    close_until = -1.0
    wink_until = -1.0

    writer = cv2.VideoWriter(args.tmp_video, cv2.VideoWriter_fourcc(*"mp4v"), args.fps, (W, H))
    if not writer.isOpened():
        raise RuntimeError("VideoWriter open failed")

    frames = int(math.ceil(total_sec * args.fps))
    ev_i = 0

    t_start = time.time()
    next_report = 0.0
    report_every_frames = max(1, int(args.progress_sec * args.fps))

    rot_cache = {}  # key: (vowel_key, eye_mode, angle_key) -> rotated ROI(BGRA)
    
    def angle_key(deg: float, step: float = 0.1) -> int:
        # 0.1度刻み（必要なら0.2等にするとさらに速い）
        return int(round(deg / step))

    seg_i = 0

    base_static = None
    if bg is not None:
        base_static = alpha_blend(bg.copy(), body.copy())
    else:
        base_static = body.copy()

    def event_duration_sec(e, default_sec: float) -> float:
        if e.beats is not None:
            return max(0.0, float(e.beats) * sec_per_beat)
        if e.sec is not None:
            return max(0.0, float(e.sec))
        return max(0.0, float(default_sec))

    for fi in range(frames):
        t = fi / args.fps

        # events
        while ev_i < len(events) and events[ev_i].t <= t + 1e-9:
            e = events[ev_i]
        
            # SPEED_* が来たら move_sec を変える（tilt_lead_beats の時は無視）
            if e.name == "SPEED_FAST":
                if args.tilt_lead_beats is None:
                    move_sec = MOVE_SEC_FAST
                ev_i += 1
                continue
            elif e.name == "SPEED_SLOW":
                if args.tilt_lead_beats is None:
                    move_sec = MOVE_SEC_SLOW
                ev_i += 1
                continue
        
            # ★ここで “今回のイベントに使う速度” を確定
            use_move = move_sec if lead_sec is None else max(1e-3, lead_sec)

            if e.name == "WINK":
                dur = event_duration_sec(e, WINK_DEFAULT_SEC)
                wink_until = max(wink_until, t + dur)

            elif e.name == "OPEN_EYES":
                dur = event_duration_sec(e, 999999.0)
                open_until = max(open_until, t + dur)
            
            elif e.name == "CLOSE_EYES":
                dur = event_duration_sec(e, 999999.0)
                close_until = max(close_until, t + dur)
            
            elif e.name == "EYE_AUTO":
                dur = event_duration_sec(e, 999999.0)
                eye_auto_until = max(eye_auto_until, t + dur)

            # 以降は use_move を使う
            elif e.name in ("TILT_0", "TILT_C"):
                tilt.set_target(t, 0.0, use_move)
            elif e.name == "TILT_L":
                tilt.set_target(t, -TILT_MAX_DEG, use_move)
            elif e.name == "TILT_R":
                tilt.set_target(t, +TILT_MAX_DEG, use_move)

            ev_i += 1

        # base layer
        if bg is not None:
            frame = base_static.copy()
            frame = alpha_blend(frame, body.copy())
        else:
            frame = body.copy()

        # advance segment pointer (O(1))
        while seg_i + 1 < len(notes) and t >= notes[seg_i].t1:
            seg_i += 1
        v = notes[seg_i].vowel if notes else "N"

        ang = tilt.value(t)
        
        # notes pointer (O(1))
        while seg_i + 1 < len(notes) and t >= notes[seg_i].t1:
            seg_i += 1
        v = notes[seg_i].vowel if notes else "N"
        
        # eye mode decision (あなたのWINK最優先ロジックを維持)
        # eye_mode: 0=none(open), 1=close, 2=wink
        eye_mode = 0
        is_long_rest = False  # 休符長閉眼まだ無し
        
        if t < wink_until:
            eye_mode = 2
        else:
            if t < eye_auto_until:
                if is_long_rest or abs(ang) > 0.2:
                    eye_mode = 1
            else:
                if t < close_until:
                    eye_mode = 1
                elif t < open_until:
                    eye_mode = 0
                else:
                    if is_long_rest or abs(ang) > 0.2:
                        eye_mode = 1
        
        # cache lookup
        vk = v if v in ("A","I","U","E","O") else "N"
        ak = angle_key(ang, step=0.1)
        ck = (vk, eye_mode, ak)
        
        rot = rot_cache.get(ck)
        if rot is None:
            # compose head ROI (BGRA) - small (792x763)
            hroi = head_base_roi.copy()
            
            if vk in mouth_roi:
                hroi = alpha_blend_bbox(hroi, mouth_roi[vk], bbox_mouth[vk])
            
            if eye_mode == 2:
                hroi = alpha_blend_bbox(hroi, eye_wink_roi, bbox_eye_wink)
            elif eye_mode == 1:
                hroi = alpha_blend_bbox(hroi, eye_close_roi, bbox_eye_close)
        
            rot = rotate_rgba_roi(hroi, ang, PIVOT_ROI)
            rot_cache[ck] = rot
        
        # blend ONLY ROI area onto frame
        frame_roi = frame[y0:y1, x0:x1].copy()
        frame_roi = alpha_blend(frame_roi, rot)
        frame[y0:y1, x0:x1] = frame_roi

        # # head
        # head = head_base.copy()

        # if v in mouth:
        #     head = alpha_blend(head, mouth[v])

        # ang = tilt.value(t)

        # is_long_rest = False  # 休符長閉眼はまだ無し
        
        # if t < wink_until:
        #     head = alpha_blend(head, eye_wink)
        # else:
        #     if t < eye_auto_until:
        #         if is_long_rest or abs(ang) > 0.2:
        #             head = alpha_blend(head, eye_close)
        #     else:
        #         if t < close_until:
        #             head = alpha_blend(head, eye_close)
        #         elif t < open_until:
        #             pass
        #         else:
        #             if is_long_rest or abs(ang) > 0.2:
        #                 head = alpha_blend(head, eye_close)

        # head = rotate_rgba(head, ang)
        # frame = alpha_blend(frame, head)

        writer.write(frame[..., :3])

        # ★進捗表示
        if fi % report_every_frames == 0 or fi == frames - 1:
            elapsed = time.time() - t_start
            pct = (fi + 1) * 100.0 / frames
            print(f"[render] {fi+1}/{frames} ({pct:5.1f}%)  elapsed={elapsed:6.1f}s")

    writer.release()

    if args.wav:
        mux_wav_segment(args.tmp_video, args.wav, args.out, start_offset_sec, total_sec)
        print("written:", args.out, "(muxed with wav)")
    else:
        shutil.copyfile(args.tmp_video, args.out)
        print("written:", args.out, "(silent)")

if __name__ == "__main__":
    main()
