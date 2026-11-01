#!/usr/bin/env python3
"""Build burned-in-ready ASS subtitles with active-word highlighting.

Input JSON must follow faster-whisper's common shape:
{"segments": [{"words": [{"start", "end", "word"}, ...]}]}.
Use --segment PATH@OFFSET multiple times when clips were concatenated.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from PIL import ImageFont

CLITIC_RE = re.compile(r"[dljnmstcD'LJNMSTCquQU]+")
SENTENCE_END_RE = re.compile(r'[.!?…][”»\"]?$')


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--segment",
        action="append",
        required=True,
        metavar="PATH[@OFFSET]",
        help="Word-timestamp JSON and optional master-timeline offset in seconds.",
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--font-file", required=True)
    parser.add_argument("--font-name", default="DejaVu Sans")
    parser.add_argument("--font-size", type=int, default=48)
    parser.add_argument("--play-res-x", type=int, default=720)
    parser.add_argument("--play-res-y", type=int, default=1280)
    parser.add_argument("--max-line-width", type=float, default=620)
    parser.add_argument("--max-words", type=int, default=5)
    parser.add_argument("--margin-v", type=int, default=170)
    parser.add_argument("--active-colour", default="&H004AD5FF&")
    parser.add_argument("--base-colour", default="&H00FFFFFF&")
    return parser.parse_args()


def parse_segment_spec(spec: str) -> tuple[Path, float]:
    if "@" not in spec:
        return Path(spec), 0.0
    path_text, offset_text = spec.rsplit("@", 1)
    try:
        return Path(path_text), float(offset_text)
    except ValueError as exc:
        raise SystemExit(f"Invalid segment offset in {spec!r}") from exc


def ass_time(seconds: float) -> str:
    total_cs = max(0, round(seconds * 100))
    hours, remainder = divmod(total_cs, 360000)
    minutes, remainder = divmod(remainder, 6000)
    whole_seconds, centiseconds = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{whole_seconds:02d}.{centiseconds:02d}"


def escape_ass(text: str) -> str:
    return text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}")


def load_words(path: Path, offset: float) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    words: list[dict[str, Any]] = []
    for segment in payload.get("segments", []):
        for item in segment.get("words", []):
            token = str(item.get("word", "")).strip()
            if token:
                words.append(
                    {
                        "text": token,
                        "start": float(item["start"]) + offset,
                        "end": float(item["end"]) + offset,
                    }
                )

    merged: list[dict[str, Any]] = []
    index = 0
    while index < len(words):
        current = words[index].copy()
        if (
            index + 1 < len(words)
            and words[index + 1]["text"].startswith("'")
            and CLITIC_RE.fullmatch(current["text"])
        ):
            current["text"] += words[index + 1]["text"]
            current["end"] = words[index + 1]["end"]
            index += 1
        merged.append(current)
        index += 1
    return merged


def split_sentences(words: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    sentences: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for word in words:
        current.append(word)
        if SENTENCE_END_RE.search(word["text"]):
            sentences.append(current)
            current = []
    if current:
        sentences.append(current)
    return sentences


def wrapped_line_count(
    candidate: list[dict[str, Any]],
    font: ImageFont.FreeTypeFont,
    max_width: float,
) -> int:
    count = 1
    line_words: list[str] = []
    for word in candidate:
        proposed = line_words + [word["text"]]
        if line_words and font.getlength(" ".join(proposed)) > max_width:
            count += 1
            line_words = [word["text"]]
        else:
            line_words = proposed
    return count


def pack_chunks(
    words: list[dict[str, Any]],
    font: ImageFont.FreeTypeFont,
    max_width: float,
    max_words: int,
) -> list[list[dict[str, Any]]]:
    chunks: list[list[dict[str, Any]]] = []
    offset = 0
    while offset < len(words):
        remaining = len(words) - offset
        size = min(max_words, remaining)
        while (
            size > 2
            and wrapped_line_count(words[offset : offset + size], font, max_width) > 2
        ):
            size -= 1
        if remaining - size == 1 and size > 2:
            size -= 1
        chunks.append(words[offset : offset + size])
        offset += size
    return chunks


def line_breaks(
    chunk: list[dict[str, Any]],
    font: ImageFont.FreeTypeFont,
    max_width: float,
) -> set[int]:
    breaks: set[int] = set()
    line_words: list[str] = []
    for index, word in enumerate(chunk):
        proposed = line_words + [word["text"]]
        if line_words and font.getlength(" ".join(proposed)) > max_width:
            breaks.add(index - 1)
            line_words = [word["text"]]
        else:
            line_words = proposed
    return breaks


def render_text(
    chunk: list[dict[str, Any]],
    active_index: int | None,
    font: ImageFont.FreeTypeFont,
    max_width: float,
    active_colour: str,
    base_colour: str,
) -> str:
    parts: list[str] = []
    breaks = line_breaks(chunk, font, max_width)
    for index, word in enumerate(chunk):
        token = escape_ass(word["text"])
        if index == active_index:
            parts.append(r"{\1c" + active_colour + "}" + token + r"{\1c" + base_colour + "}")
        else:
            parts.append(token)
        if index < len(chunk) - 1:
            parts.append(r"\N" if index in breaks else " ")
    return "".join(parts)


def main() -> None:
    args = parse_args()
    font = ImageFont.truetype(args.font_file, args.font_size)
    words: list[dict[str, Any]] = []
    for spec in args.segment:
        path, offset = parse_segment_spec(spec)
        words.extend(load_words(path, offset))

    chunks: list[list[dict[str, Any]]] = []
    for sentence in split_sentences(words):
        chunks.extend(
            pack_chunks(sentence, font, args.max_line_width, args.max_words)
        )

    header = f"""[Script Info]
Title: Word-synchronised highlight subtitles
ScriptType: v4.00+
WrapStyle: 2
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709
PlayResX: {args.play_res_x}
PlayResY: {args.play_res_y}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Karaoke,{args.font_name},{args.font_size},{args.base_colour},{args.active_colour},&H00000000,&H70000000,-1,0,0,0,100,100,0,0,1,4,1,2,45,45,{args.margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events: list[str] = []
    for chunk in chunks:
        for index, word in enumerate(chunk):
            start = float(word["start"])
            end = max(float(word["end"]), start + 0.04)
            text = render_text(
                chunk,
                index,
                font,
                args.max_line_width,
                args.active_colour,
                args.base_colour,
            )
            events.append(
                f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Karaoke,,0,0,0,,{text}"
            )
            if index + 1 < len(chunk):
                gap_end = float(chunk[index + 1]["start"])
                if gap_end - end >= 0.04:
                    plain = render_text(
                        chunk,
                        None,
                        font,
                        args.max_line_width,
                        args.active_colour,
                        args.base_colour,
                    )
                    events.append(
                        f"Dialogue: 0,{ass_time(end)},{ass_time(gap_end)},Karaoke,,0,0,0,,{plain}"
                    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "output": str(args.output),
                "events": len(events),
                "chunks": len(chunks),
                "words": len(words),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
