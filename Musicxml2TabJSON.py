#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
MusicXML（Dorico等）の <technical><string><fret> をTAB用JSONへ変換。
複数 <part> がある場合、TAB情報(string+fret)を最も多く含む part を自動選択。

使い方:
  python3 musicxml2tabjson.py input.musicxml
  python3 musicxml2tabjson.py input.musicxml --verbose
  python3 musicxml2tabjson.py input.musicxml --list-parts
  python3 musicxml2tabjson.py input.musicxml --part 2

出力:
  input.json （拡張子を .json に置換）

デバッグ表示はstderr。stdoutは出力ファイル名のみ。
"""

import json
import sys
import os
import xml.etree.ElementTree as ET


def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


def localname(tag: str) -> str:
    return tag.split("}")[-1] if "}" in tag else tag


def find_child_local(el, name: str):
    for ch in list(el):
        if localname(ch.tag) == name:
            return ch
    return None


def find_children_local(el, name: str):
    return [ch for ch in list(el) if localname(ch.tag) == name]


def find_desc_local(el, name: str):
    for sub in el.iter():
        if localname(sub.tag) == name:
            return sub
    return None


def find_desc_text(el, name: str):
    n = find_desc_local(el, name)
    if n is None or n.text is None:
        return None
    return n.text.strip()


def count_tab_notes_in_part(part) -> int:
    """part内で、noteの中に technical(string+fret) があるものを数える"""
    c = 0
    for note in part.iter():
        if localname(note.tag) != "note":
            continue
        tech = find_desc_local(note, "technical")
        if tech is None:
            continue
        st = find_desc_text(tech, "string")
        fr = find_desc_text(tech, "fret")
        if st is not None and fr is not None and st != "" and fr != "":
            c += 1
    return c


def list_parts(root):
    parts = [ch for ch in list(root) if localname(ch.tag) == "part"]
    out = []
    for i, p in enumerate(parts, start=1):
        pid = p.get("id", f"(no-id:{i})")
        meas = sum(1 for ch in list(p) if localname(ch.tag) == "measure")
        tabn = count_tab_notes_in_part(p)
        out.append((i, pid, meas, tabn))
    return out


def choose_best_part(root, forced_index: int | None = None):
    parts = [ch for ch in list(root) if localname(ch.tag) == "part"]
    if not parts:
        raise ValueError("No <part> found in MusicXML.")

    if forced_index is not None:
        if not (1 <= forced_index <= len(parts)):
            raise ValueError(f"--part out of range (1..{len(parts)}): {forced_index}")
        return parts[forced_index - 1], forced_index

    # TAB情報が最大のpartを選ぶ
    best_i = 1
    best_c = -1
    for i, p in enumerate(parts, start=1):
        c = count_tab_notes_in_part(p)
        if c > best_c:
            best_c = c
            best_i = i
    return parts[best_i - 1], best_i


def musicxml_tab_to_json_dict(xml_path: str, verbose: bool = False, part_index: int | None = None) -> dict:
    eprint(f"[INFO] Parsing: {xml_path}")
    tree = ET.parse(xml_path)
    root = tree.getroot()
    eprint(f"[INFO] Root tag: {root.tag}")

    tech_total = sum(1 for x in root.iter() if localname(x.tag) == "technical")
    eprint(f"[INFO] Total <technical> tags in file: {tech_total}")

    parts_info = list_parts(root)
    eprint("[INFO] Parts summary: index, id, measures, TAB-notes")
    for i, pid, meas, tabn in parts_info:
        eprint(f"        {i}: {pid}, measures={meas}, TAB-notes={tabn}")

    part, chosen_i = choose_best_part(root, forced_index=part_index)
    chosen_id = part.get("id", f"(no-id:{chosen_i})")
    eprint(f"[INFO] Using part #{chosen_i} id={chosen_id}")

    measures = [m for m in list(part) if localname(m.tag) == "measure"]
    eprint(f"[INFO] Measures in chosen part: {len(measures)}")

    measures_out = []

    for meas_idx, meas in enumerate(measures, start=1):
        # defaults
        divisions = 12
        beats = 4
        beat_type = 4

        attr = find_child_local(meas, "attributes")
        if attr is not None:
            div_el = find_child_local(attr, "divisions")
            if div_el is not None and div_el.text:
                divisions = int(div_el.text)

            time_el = find_child_local(attr, "time")
            if time_el is not None:
                b = find_child_local(time_el, "beats")
                bt = find_child_local(time_el, "beat-type")
                if b is not None and bt is not None and b.text and bt.text:
                    beats = int(b.text)
                    beat_type = int(bt.text)

        measure_len_div = int(round(divisions * beats * (4 / beat_type)))
        if measure_len_div <= 0:
            measure_len_div = divisions * 4

        if verbose:
            eprint(f"\n[MEAS {meas_idx}] divisions={divisions} time={beats}/{beat_type} measure_len_div={measure_len_div}")

        # ----- 1st pass: 16/48 判定 -----
        cursor = 0
        starts = []
        durs = []
        tab_note_count = 0

        for el in list(meas):
            tag = localname(el.tag)

            if tag == "backup":
                dur_text = find_desc_text(el, "duration")
                if dur_text:
                    d = int(dur_text)
                    cursor -= d
                    if verbose:
                        eprint(f"  backup -{d} -> cursor={cursor}")
                continue

            if tag == "forward":
                dur_text = find_desc_text(el, "duration")
                if dur_text:
                    d = int(dur_text)
                    cursor += d
                    if verbose:
                        eprint(f"  forward +{d} -> cursor={cursor}")
                continue

            if tag != "note":
                continue

            is_chord = (find_child_local(el, "chord") is not None)
            dur_text = find_desc_text(el, "duration")
            dur = int(dur_text) if dur_text else 0

            tech = find_desc_local(el, "technical")
            if tech is not None:
                st = find_desc_text(tech, "string")
                fr = find_desc_text(tech, "fret")
                if st is not None and fr is not None and st != "" and fr != "":
                    starts.append(cursor)
                    durs.append(dur)
                    tab_note_count += 1

            if verbose:
                tech_flag = "TAB" if tech is not None else "   "
                chord_flag = "CH" if is_chord else "  "
                eprint(f"  note {tech_flag} {chord_flag} start={cursor} dur={dur}")

            if not is_chord:
                cursor += dur

        need48 = any((x % 3) != 0 for x in (starts + durs))
        steps_per_bar = 48 if need48 else 16
        step_div = measure_len_div / steps_per_bar
        eprint(f"[MEAS {meas_idx}] TAB-notes={tab_note_count} -> steps_per_bar={steps_per_bar} (step_div={step_div})")

        # ----- grid -----
        grid = [[{"kind": "empty", "fret": None} for _ in range(steps_per_bar)] for _ in range(6)]

        def place(string_1to6: int, fret: int, start_div: int, dur_div: int, is_tie: bool):
            s = string_1to6 - 1  # 1弦->0
            if not (0 <= s < 6) or dur_div <= 0:
                return

            start_step = int(round(start_div / step_div))
            dur_steps = max(1, int(round(dur_div / step_div)))
            if not (0 <= start_step < steps_per_bar):
                return

            kind = "tie" if is_tie else "note"
            grid[s][start_step] = {"kind": kind, "fret": int(fret)}

            for k in range(1, dur_steps):
                t = start_step + k
                if t >= steps_per_bar:
                    break
                if grid[s][t]["kind"] == "empty":
                    grid[s][t] = {"kind": "hold", "fret": None}

            if verbose:
                eprint(f"    [PLACE] string={string_1to6} fret={fret} {kind} start_div={start_div} dur_div={dur_div} -> step={start_step} dur_steps={dur_steps}")

        # ----- 2nd pass: 実配置 -----
        cursor = 0
        placed = 0

        for el in list(meas):
            tag = localname(el.tag)

            if tag == "backup":
                dur_text = find_desc_text(el, "duration")
                if dur_text:
                    cursor -= int(dur_text)
                continue

            if tag == "forward":
                dur_text = find_desc_text(el, "duration")
                if dur_text:
                    cursor += int(dur_text)
                continue

            if tag != "note":
                continue

            is_chord = (find_child_local(el, "chord") is not None)
            dur_text = find_desc_text(el, "duration")
            dur = int(dur_text) if dur_text else 0

            tech = find_desc_local(el, "technical")
            if tech is not None:
                st = find_desc_text(tech, "string")
                fr = find_desc_text(tech, "fret")
                if st is not None and fr is not None and st != "" and fr != "":
                    string_no = int(st)
                    fret = int(fr)

                    tie_stop = False
                    for tie in find_children_local(el, "tie"):
                        if tie.get("type") == "stop":
                            tie_stop = True
                    for tied in el.iter():
                        if localname(tied.tag) == "tied" and tied.get("type") == "stop":
                            tie_stop = True

                    place(string_no, fret, cursor, dur, is_tie=tie_stop)
                    placed += 1

            if not is_chord:
                cursor += dur

        eprint(f"[MEAS {meas_idx}] placed={placed}")
        measures_out.append({"steps_per_bar": steps_per_bar, "grid": grid})

    return {"version": 1, "measures": measures_out}


def default_output_path(input_path: str) -> str:
    base, _ext = os.path.splitext(input_path)
    return base + ".json"


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        eprint("Usage: python3 musicxml2tabjson.py <input.musicxml|input.xml> [--verbose] [--list-parts] [--part N]")
        return 2

    in_path = argv[1]
    verbose = ("--verbose" in argv[2:])
    list_only = ("--list-parts" in argv[2:])

    part_index = None
    if "--part" in argv[2:]:
        i = argv.index("--part")
        if i + 1 >= len(argv):
            eprint("ERROR: --part requires an integer argument")
            return 2
        part_index = int(argv[i + 1])

    try:
        # list-only: パート情報だけ表示して終了
        if list_only:
            root = ET.parse(in_path).getroot()
            parts_info = list_parts(root)
            eprint("[INFO] Parts summary: index, id, measures, TAB-notes")
            for i, pid, meas, tabn in parts_info:
                eprint(f"        {i}: {pid}, measures={meas}, TAB-notes={tabn}")
            return 0

        out_path = default_output_path(in_path)
        data = musicxml_tab_to_json_dict(in_path, verbose=verbose, part_index=part_index)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    except Exception as e:
        eprint(f"ERROR: {e}")
        return 1

    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
