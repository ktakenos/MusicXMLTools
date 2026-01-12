#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MusicXML (lyrics included) -> MP4 (image switching lipsync style)
Works on Raspberry Pi 5 (Python3 + OpenCV).
"""

import argparse
import os
import re
import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np
import xml.etree.ElementTree as ET


# ---------------------------
# Utilities: lyric -> vowel group
# ---------------------------

# Basic hiragana/katakana vowel detection for Japanese-ish lyrics.
# If your lyrics are romaji, we also handle [aiueo].
VOWEL_GROUPS = {
    "A": set(list("あかさたなはまやらわがざだばぱぁゃゎアカサタナハマヤラワガザダバパァャヮ"
                  "ぁゃゎ")),
    "I": set(list("いきしちにひみりぎじぢびぴぃイキシチニヒミリギジヂビピィ")),
    "U": set(list("うくすつぬふむゆるぐずづぶぷぅゅウクスツヌフムユルグズヅブプゥュ")),
    "E": set(list("えけせてねへめれげぜでべぺぇエケセテネヘメレゲゼデベペェ")),
    "O": set(list("おこそとのほもよろをごぞどぼぽぉょオコソトノホモヨロゴゾドボポォョ")),
}

SMALL_KANA = set(list("ゃゅょぁぃぅぇぉャュョァィゥェォ"))
LONG_MARK = "ー"

def normalize_lyric(s: str) -> str:
    """Normalize lyric text for parsing."""
    if s is None:
        return ""
    s = s.strip()
    # Remove punctuation/spaces
    s = re.sub(r"[ \t\r\n]+", "", s)
    s = re.sub(r"[、。・,.\-!！?？「」『』（）()\[\]{}]", "", s)
    return s

def pick_vowel_group_from_japanese(text: str) -> Optional[str]:
    """
    Return one of 'A','I','U','E','O' if we can infer.
    Strategy:
      - Scan from end for a kana that maps to vowel group.
      - Ignore small kana, prolonged sound mark 'ー' (it elongates previous vowel).
      - Handle ん/ン as None (keep previous / closed).
    """
    if not text:
        return None

    # Common nasal
    if text in ("ん", "ン"):
        return None

    # Scan from end
    chars = list(text)
    for i in range(len(chars) - 1, -1, -1):
        c = chars[i]
        if c == LONG_MARK:
            # elongation: look left
            continue
        if c in SMALL_KANA:
            continue
        for vg, charset in VOWEL_GROUPS.items():
            if c in charset:
                return vg
    return None

def pick_vowel_group_from_romaji(text: str) -> Optional[str]:
    """
    For romaji lyrics: pick last vowel in [aiueo].
    """
    if not text:
        return None
    m = re.findall(r"[aiueoAIUEO]", text)
    if not m:
        return None
    v = m[-1].lower()
    return {"a":"A", "i":"I", "u":"U", "e":"E", "o":"O"}.get(v)

def lyric_to_state(text: str, map_ie_to: str = "A") -> str:
    """
    Map lyric text -> one of: A, O, U, CLOSED.
    - A: A-group
    - O: O-group
    - U: U-group
    - I/E are mapped to map_ie_to (default 'A'), because we only have 4 images.
    """
    t = normalize_lyric(text)
    if not t:
        return "CLOSED"

    vg = pick_vowel_group_from_japanese(t)
    if vg is None:
        vg = pick_vowel_group_from_romaji(t)

    if vg == "A":
        return "A"
    if vg == "O":
        return "O"
    if vg == "U":
        return "U"
    if vg in ("I", "E"):
        if map_ie_to.upper() in ("A", "O", "U", "CLOSED"):
            return map_ie_to.upper()
        return "A"

    # unknown
    return "CLOSED"


# ---------------------------
# MusicXML parsing
# ---------------------------

@dataclass
class Segment:
    t0: float
    t1: float
    state: str  # A/O/U/CLOSED

def find_first(elem: ET.Element, path: str) -> Optional[ET.Element]:
    x = elem.find(path)
    return x

def text_of(elem: Optional[ET.Element]) -> Optional[str]:
    if elem is None:
        return None
    return elem.text

def parse_tempo_bpm(root: ET.Element, default_bpm: float = 120.0) -> float:
    """
    Try (1) <sound tempo="...">, (2) <per-minute>, else default.
    """
    # (1) sound tempo attribute
    for snd in root.iter():
        if snd.tag.endswith("sound"):
            tempo = snd.attrib.get("tempo")
            if tempo:
                try:
                    return float(tempo)
                except ValueError:
                    pass

    # (2) per-minute in metronome
    for pm in root.iter():
        if pm.tag.endswith("per-minute"):
            try:
                return float(pm.text.strip())
            except Exception:
                pass

    return default_bpm

def iter_notes_in_order(root: ET.Element) -> List[ET.Element]:
    """
    Collect <note> in document order across parts/measures.
    This is simplistic but works for single-part lyric lines.
    """
    notes = []
    # Prefer first part
    parts = [e for e in root.findall(".//part")]
    if not parts:
        return notes
    part = parts[0]
    for meas in part.findall("./measure"):
        for note in meas.findall("./note"):
            notes.append(note)
    return notes

def parse_segments_from_musicxml(xml_path: str,
                                fps: float,
                                default_bpm: float = 120.0,
                                map_ie_to: str = "A",
                                rest_state: str = "CLOSED") -> Tuple[List[Segment], float, int, str]:
    """
    Returns:
      (segments, total_duration_seconds, measure_count, lyrics_hiragana_concat)

    Adds padding for:
      1) measures with no <note> : pad by inferred measure length (time sig)
      2) measures whose summed duration is shorter than a full measure : pad remainder
         (skips padding if measure has implicit="yes")
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()

    bpm = parse_tempo_bpm(root, default_bpm=default_bpm)
    sec_per_quarter = 60.0 / bpm  # quarter note seconds

    segments: List[Segment] = []
    t = 0.0

    current_lyric_state = rest_state

    parts = [e for e in root.findall(".//part")]
    if not parts:
        return [], 0.0, 0, ""
    part = parts[0]

    divisions: Optional[int] = None

    # 現在の拍子（デフォルト 4/4）
    time_beats = 4
    time_beat_type = 4

    def measure_quarter_len() -> float:
        # 小節長を「四分音符何個分か」で返す。4/4なら4.0、3/8なら1.5 等
        return float(time_beats) * (4.0 / float(time_beat_type))

    measure_count = 0
    lyrics_chars: List[str] = []

    for measure in part.findall("./measure"):
        measure_count += 1

        # --- attributes update (divisions / time signature) ---
        attrs = measure.find("./attributes")
        if attrs is not None:
            div = attrs.find("./divisions")
            if div is not None and div.text:
                try:
                    divisions = int(div.text.strip())
                except Exception:
                    pass

            tm = attrs.find("./time")
            if tm is not None:
                b = tm.find("./beats")
                bt = tm.find("./beat-type")
                if b is not None and b.text and bt is not None and bt.text:
                    try:
                        time_beats = int(b.text.strip())
                        time_beat_type = int(bt.text.strip())
                    except Exception:
                        pass

        if divisions is None:
            divisions = 1  # fallback

        meas_no = measure.attrib.get("number", "?")
        implicit = (measure.attrib.get("implicit", "no").lower() == "yes")

        measure_sec_before = t
        measure_lyrics: List[str] = []

        notes = measure.findall("./note")

        # ==========================
        # (1) <note> が無い小節を補完
        # ==========================
        if not notes:
            qlen = measure_quarter_len()
            dt = qlen * sec_per_quarter

            # 全区間 CLOSED で埋める
            segments.append(Segment(t, t + dt, rest_state))
            t += dt

            print(f"[measure {meas_no}] PAD(no-notes) +{dt:.3f}s  time={time_beats}/{time_beat_type}  lyrics=(no-lyric)")
            continue

        # 小節内の合計（四分音符単位）を数えて、小節末の余りを埋める
        sum_quarters = 0.0

        for note in notes:
            is_rest = (note.find("./rest") is not None)

            dur_elem = note.find("./duration")
            if dur_elem is None or dur_elem.text is None:
                # grace等（時間に寄与しない）
                print(f"[measure {meas_no}] WARNING: <note> without <duration> skipped")
                continue
            try:
                dur_div = int(dur_elem.text.strip())
            except Exception:
                print(f"[measure {meas_no}] WARNING: invalid <duration> skipped")
                continue

            # duration/divisions = 四分音符何個分か
            q = dur_div / float(divisions)
            dt = q * sec_per_quarter
            sum_quarters += q

            tie_elems = note.findall("./tie")
            tie_types = {te.attrib.get("type") for te in tie_elems if te is not None}
            has_tie_start = "start" in tie_types
            has_tie_stop = "stop" in tie_types

            lyric_text = None
            lyr = note.find("./lyric")
            if lyr is not None:
                tx = lyr.find("./text")
                if tx is not None and tx.text:
                    lyric_text = tx.text

            if is_rest:
                state = rest_state
            else:
                if lyric_text:
                    norm = normalize_lyric(lyric_text)
                    if norm:
                        measure_lyrics.append(norm)
                        lyrics_chars.append(norm)
                    state = lyric_to_state(lyric_text, map_ie_to=map_ie_to)
                    current_lyric_state = state
                else:
                    # 歌詞がない場合：タイ継続なら前の母音を維持、そうでなければ閉
                    if has_tie_stop and not has_tie_start:
                        state = current_lyric_state
                    else:
                        state = rest_state

            # CLOSED 1フレ挿入（子音っぽさ）
            if segments:
                prev = segments[-1]
                if prev.state == "CLOSED" and state in ("A", "O", "U"):
                    gap = 1.0 / fps
                    if dt > gap * 1.5:
                        segments.append(Segment(t, t + gap, "CLOSED"))
                        t += gap
                        dt -= gap

            segments.append(Segment(t, t + dt, state))
            t += dt

        # =======================================
        # (2) 小節末尾の余りを CLOSED で補完（任意）
        #    ※ implicit="yes" は補完しない
        # =======================================
        qlen = measure_quarter_len()
        remainder_q = qlen - sum_quarters
        # ほんの誤差は無視
        if (not implicit) and remainder_q > 1e-6:
            dt_pad = remainder_q * sec_per_quarter
            segments.append(Segment(t, t + dt_pad, rest_state))
            t += dt_pad
            pad_msg = f" PAD(remainder) +{dt_pad:.3f}s"
        else:
            pad_msg = ""

        measure_sec = t - measure_sec_before
        lyric_join = "".join(measure_lyrics) if measure_lyrics else "(no-lyric)"
        print(f"[measure {meas_no}] +{measure_sec:.3f}s  time={time_beats}/{time_beat_type}  lyrics={lyric_join}{pad_msg}")

    total = t
    lyrics_concat = "".join(lyrics_chars)
    return segments, total, measure_count, lyrics_concat


# ---------------------------
# Video rendering
# ---------------------------

def load_images(img_dir: str, paths: Dict[str, str]) -> Dict[str, np.ndarray]:
    imgs = {}
    base_w = base_h = None
    for k, rel in paths.items():
        p = rel if os.path.isabs(rel) else os.path.join(img_dir, rel)
        if not os.path.exists(p):
            raise FileNotFoundError(f"Image not found: {p}")
        im = cv2.imread(p, cv2.IMREAD_COLOR)
        if im is None:
            raise RuntimeError(f"Failed to load image: {p}")
        if base_w is None:
            base_h, base_w = im.shape[:2]
        else:
            h, w = im.shape[:2]
            if (w, h) != (base_w, base_h):
                raise ValueError(f"Image size mismatch: {p} is {w}x{h}, expected {base_w}x{base_h}")
        imgs[k] = im
    return imgs

def state_at_time(segments: List[Segment], t: float) -> str:
    # linear scan is OK for short songs; for long, you can binary search.
    for seg in segments:
        if seg.t0 <= t < seg.t1:
            return seg.state
    return "CLOSED"

def render_mp4(out_mp4: str,
               segments: List[Segment],
               total_sec: float,
               fps: float,
               imgs: Dict[str, np.ndarray],
               crf_hint: Optional[int] = None) -> None:
    h, w = next(iter(imgs.values())).shape[:2]

    # OpenCV mp4 encoding depends on ffmpeg build; 'mp4v' is widely available on Pi.
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(out_mp4, fourcc, fps, (w, h))
    if not writer.isOpened():
        raise RuntimeError("Failed to open VideoWriter. Is ffmpeg/gstreamer available for OpenCV?")

    nframes = int(math.ceil(total_sec * fps))
    for i in range(nframes):
        t = i / fps
        st = state_at_time(segments, t)
        frame = imgs.get(st, imgs["CLOSED"])
        writer.write(frame)

    writer.release()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("musicxml", help="Input MusicXML (.musicxml/.xml)")
    ap.add_argument("--img-dir", default=".", help="Directory containing images")
    ap.add_argument("--img-a", default="mouth_A.png")
    ap.add_argument("--img-o", default="mouth_O.png")
    ap.add_argument("--img-u", default="mouth_U.png")
    ap.add_argument("--img-closed", default="mouth_closed.png")
    ap.add_argument("--out", default="out.mp4")
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--bpm", type=float, default=120.0, help="Default BPM if not in MusicXML")
    ap.add_argument("--map-ie-to", default="A", choices=["A","O","U","CLOSED"],
                    help="We only have 4 images; map I/E vowels to one of them.")
    args = ap.parse_args()

    paths = {
        "A": args.img_a,
        "O": args.img_o,
        "U": args.img_u,
        "CLOSED": args.img_closed,
    }

    imgs = load_images(args.img_dir, paths)

    segments, total_sec, measure_count, lyrics_concat = parse_segments_from_musicxml(
        args.musicxml,
        fps=args.fps,
        default_bpm=args.bpm,
        map_ie_to=args.map_ie_to,
        rest_state="CLOSED",
    )

    print("---- SUMMARY ----")
    print(f"Measures parsed: {measure_count}")
    print(f"Total seconds : {total_sec:.3f}")
    print(f"Lyrics(hira)  : {lyrics_concat if lyrics_concat else '(none)'}")
    print("-----------------")

    if not segments:
        raise RuntimeError("No segments parsed. Is the MusicXML valid and containing notes?")

    render_mp4(args.out, segments, total_sec, args.fps, imgs)
    print(f"OK: wrote {args.out}  duration={total_sec:.2f}s  fps={args.fps}")

if __name__ == "__main__":
    main()
