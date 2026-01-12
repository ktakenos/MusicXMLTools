#!/usr/bin/env python3
# coding: utf-8
"""
apply_lyrics4.py

目的:
- スペース無し（または通常の文章スペース付き）ひらがな歌詞から、MusicXML の単音ボーカルパートに歌詞を割り当てる
- 自動分割結果を必ず「スペース入り中間ファイル」として出力
- 中間ファイルを編集して再投入した場合は、そのスペース区切りを優先採用

今回の修正点:
1) 入力テキストの改行を最初に除去して1行化（意図しない分割の減少を回避）
2) タイで繋がった後続音（tie 'continue'/'stop'）には歌詞を割り当てない

分割仕様（要件）:
- 拗音（小書きゃゅょぁぃぅぇぉゎゕゖ）は直前と結合（じゃ、きょ 等）
- 長音記号「ー」は直前と結合
- 次トークンが「ん」なら前と結合して1音（2音節目が「ん」でも1音）
- 次トークンが母音（あいうえお）なら前と結合し、母音が連続する限り全部結合（長母音解釈を含む）
  例: きょ/う→きょう、い/い→いい、え/い→えい、こ/う→こう

警告:
- ノート数（歌詞を付ける対象の音符数）と歌詞単位数が一致しなければ警告
- --strict で不一致時に中断

使い方:
  python3 apply_lyrics4.py in.musicxml lyrics.txt out.musicxml
  python3 apply_lyrics4.py in.musicxml lyrics.spaced.txt out.musicxml

オプション:
  [part_index]        対象パート番号（デフォルト 0）
  --no-overwrite      既存歌詞を消さずに追加
  --strict            ノート数不一致で中断
"""

import sys
from pathlib import Path
from typing import List, Optional
from music21 import converter

# 小書き（拗音・小母音など）：前の仮名に結合
SMALL_KANA = set("ゃゅょぁぃぅぇぉゎゕゖ")
# 促音（今回は単独のまま）
SMALL_TSU = "っ"
# 長音記号：直前に結合
CHOON = "ー"

# 母音（ひらがな）
VOWELS = set("あいうえお")


def preprocess_raw_text(raw: str) -> str:
    """
    入力テキストの前処理:
    - 改行を除去して1行化（重要）
    - 全角スペースは半角に寄せる
    """
    raw = raw.replace("\r\n", "\n").replace("\r", "\n")
    raw = raw.replace("\n", "")          # ←改行を除去して1行化
    raw = raw.replace("\u3000", " ")     # 全角スペース→半角
    return raw.strip()


def tokens_from_spaced_text_if_any(raw: str) -> Optional[List[str]]:
    """
    スペースが入っている入力を「中間ファイル形式（モーラ区切り）」として扱うか判定。
    - 中間ファイル: 短いトークンが大量に並ぶ（例: きょう は いい てんき）
    - 通常歌詞: フレーズ区切りのスペースがあっても、長い塊が多い

    判定:
    - 空白を含む → split() した後、1〜3文字トークン比率が高ければ中間ファイル形式とみなす
    """
    s = preprocess_raw_text(raw)
    if not s:
        return []

    if not any(ch.isspace() for ch in s):
        return None

    tokens = [t for t in s.split() if t]
    if not tokens:
        return []

    short = sum(1 for t in tokens if len(t) <= 3)
    ratio = short / len(tokens)

    # 条件は必要なら調整可
    if ratio >= 0.7 and len(tokens) >= 10:
        return tokens

    return None


def base_tokenize_no_space(raw: str) -> List[str]:
    """
    スペース無しモードの一次分割:
    - 空白は完全除去
    - 小書きゃゅょぁぃぅぇぉゎゕゖ は直前に結合（じゃ等）
    - ー は直前に結合
    - っ は単独
    """
    s = preprocess_raw_text(raw)
    s = "".join(ch for ch in s if not ch.isspace())
    if not s:
        return []

    tokens: List[str] = []
    for ch in s:
        if ch in SMALL_KANA:
            if not tokens:
                raise ValueError(f"先頭に小書き文字が来ています: {ch}")
            tokens[-1] += ch
        elif ch == CHOON:
            if not tokens:
                raise ValueError("先頭に長音記号(ー)が来ています")
            tokens[-1] += ch
        elif ch == SMALL_TSU:
            tokens.append(ch)
        else:
            tokens.append(ch)

    return tokens


def merge_rules(tokens: List[str]) -> List[str]:
    """
    結合ルール（長母音解釈含む）:
    - 次が「ん」なら前と結合
    - 次が母音（あいうえお）なら前と結合し、母音が続く限り全部結合
    """
    out: List[str] = []
    i = 0
    while i < len(tokens):
        cur = tokens[i]
        i += 1

        # 次が「ん」なら結合
        if i < len(tokens) and tokens[i] == "ん":
            cur += tokens[i]
            i += 1

        # 次が母音なら（母音が続く限り）全部結合
        while i < len(tokens) and tokens[i] in VOWELS:
            cur += tokens[i]
            i += 1

        out.append(cur)

    return out


def tokens_from_text_file(txt_path: Path) -> List[str]:
    raw = txt_path.read_text(encoding="utf-8")
    raw = preprocess_raw_text(raw)  # ←改行除去をここで確実に適用

    # 1) スペース入りを中間ファイル形式と判定できたら、その区切りを優先
    spaced = tokens_from_spaced_text_if_any(raw)
    if spaced is not None:
        return spaced

    # 2) 自動分割
    base = base_tokenize_no_space(raw)
    merged = merge_rules(base)
    return merged


def is_tied_continuation(el) -> bool:
    """
    タイで繋がった後続音（continue/stop）なら True。
    ＝歌詞を付けない対象
    """
    t = getattr(el, "tie", None)
    if t is None:
        return False
    # music21 tie.type は 'start'/'continue'/'stop' のいずれか
    return getattr(t, "type", "") in ("continue", "stop")


def count_lyric_target_notes(score, part_index: int = 0) -> int:
    """
    歌詞を付ける対象音符数を数える:
    - 休符は除外
    - タイ後続（continue/stop）は除外（start のみに歌詞を付ける）
    """
    part = score.parts[part_index]
    n = 0
    for el in part.recurse().notesAndRests:
        if el.isRest:
            continue
        if is_tied_continuation(el):
            continue
        n += 1
    return n


def write_spaced_intermediate(txt_in: Path, tokens: List[str]) -> Path:
    """
    中間ファイルを必ず出力:
      lyrics.txt -> lyrics.spaced.txt
    """
    base = txt_in.with_suffix("")  # 末尾拡張子を1つ落とす
    out_path = base.with_name(base.name + ".spaced").with_suffix(".txt")
    out_path.write_text(" ".join(tokens) + "\n", encoding="utf-8")
    return out_path


def apply_lyrics(
    xml_in: Path,
    txt_in: Path,
    xml_out: Path,
    part_index: int = 0,
    overwrite: bool = True,
    strict: bool = False,
) -> None:
    score = converter.parse(str(xml_in))
    tokens = tokens_from_text_file(txt_in)

    # 中間ファイル（スペース入り）を必ず出力
    spaced_path = write_spaced_intermediate(txt_in, tokens)
    print(f"中間ファイルを書き出しました: {spaced_path}", file=sys.stderr)

    note_count = count_lyric_target_notes(score, part_index=part_index)
    tok_count = len(tokens)

    if note_count != tok_count:
        msg = (
            f"警告: ノート数と歌詞単位数が一致しません（タイ後続はカウント除外）\n"
            f"  歌詞対象ノート数: {note_count}\n"
            f"  歌詞単位数      : {tok_count}\n"
            f"  先頭10単位      : {tokens[:10]}\n"
            f"  中間ファイル    : {spaced_path}（編集して再実行できます）\n"
        )
        print(msg, file=sys.stderr)
        if strict:
            raise SystemExit("strict=True のため中断しました。")

    # 実際の割り当て
    part = score.parts[part_index]
    i = 0
    for el in part.recurse().notesAndRests:
        if el.isRest:
            continue
        if is_tied_continuation(el):
            continue
        if i >= tok_count:
            break

        if overwrite:
            el.lyrics = []

        # verse番号は指定しない（デフォルト）
        el.addLyric(tokens[i])
        i += 1

    if i < tok_count:
        print(f"警告: 歌詞が余りました（未使用 {tok_count - i} 個）", file=sys.stderr)

    score.write("musicxml", fp=str(xml_out))


def main():
    if len(sys.argv) < 4:
        print(
            "使い方: apply_lyrics4.py input.musicxml lyrics.txt output.musicxml "
            "[part_index=0] [--no-overwrite] [--strict]",
            file=sys.stderr,
        )
        sys.exit(1)

    xml_in = Path(sys.argv[1])
    txt_in = Path(sys.argv[2])
    xml_out = Path(sys.argv[3])

    part_index = 0
    overwrite = True
    strict = False

    for a in sys.argv[4:]:
        if a == "--no-overwrite":
            overwrite = False
        elif a == "--strict":
            strict = True
        else:
            part_index = int(a)

    apply_lyrics(
        xml_in=xml_in,
        txt_in=txt_in,
        xml_out=xml_out,
        part_index=part_index,
        overwrite=overwrite,
        strict=strict,
    )


if __name__ == "__main__":
    main()
