#!/usr/bin/env python3
"""Turn the essay markdown into paste-ready plain text for a TTS engine.

Removes the markup a speech engine would either read aloud or stumble over,
verbalizes code identifiers, and unwraps the hard line breaks so each
paragraph is a single line.

    python3 make_tts_text.py              # write docs/essays/tts/*.txt
    python3 make_tts_text.py --chunk 4500 # also split into paste-sized parts
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "tts"

# Identifiers a speech engine mangles, and how they should sound.
SPOKEN = {
    "llm": "L L M",
    "cmms": "C M M S",
    "ood": "O O D",
    "ece": "E C E",
    "api": "A P I",
    "csv": "C S V",
    "json": "JSON",
    "sql": "S Q L",
    "http": "H T T P",
    "url": "U R L",
    "ui": "U I",
    "db": "database",
    "id": "id",
}


def verbalize_code(text: str) -> str:
    """`backend/app/detector.py` -> backend app detector dot p y."""
    text = text.replace("{", "").replace("}", "")
    text = re.sub(r"[/_\-.]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    words = []
    for word in text.split(" "):
        key = word.lower()
        words.append(SPOKEN.get(key, word))
    return " ".join(words)


def clean(md: str) -> str:
    blocks = re.split(r"\n\s*\n", md)
    out: list[str] = []

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        heading = bool(re.match(r"^#+\s", block))
        block = re.sub(r"^#+\s*", "", block)

        # `code` -> spoken form
        block = re.sub(r"`([^`]+)`", lambda m: verbalize_code(m.group(1)), block)
        # **bold** and *italic* markers carry no sound
        block = re.sub(r"\*{1,2}([^*]+)\*{1,2}", r"\1", block)

        # en dash ranges read better as "to"; em dashes as a comma pause
        block = re.sub(r"(?<=[\w%])\s*–\s*(?=[\w$])", " to ", block)
        block = block.replace("—", ",")

        # unwrap the hard line breaks inside the paragraph
        block = re.sub(r"\s*\n\s*", " ", block)
        block = re.sub(r"\s+", " ", block).strip()

        # tidy punctuation the substitutions may have doubled up
        block = re.sub(r",\s*,", ",", block)
        block = re.sub(r"\s+([,.;:?!])", r"\1", block)
        block = re.sub(r",\s*\.", ".", block)

        # a heading with no terminal punctuation gets one, so the voice pauses
        if heading and not block.endswith((".", "!", "?", ":")):
            block += "."

        out.append(block)

    return "\n\n".join(out) + "\n"


def split_chunks(text: str, limit: int) -> list[str]:
    """Split on paragraph boundaries, never mid-sentence."""
    chunks: list[str] = []
    current = ""
    for para in text.split("\n\n"):
        candidate = para if not current else current + "\n\n" + para
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            chunks.append(current)
        while len(para) > limit:
            # oversized paragraph: break at the last sentence end that fits
            cut = para.rfind(". ", 0, limit)
            cut = cut + 1 if cut > limit // 2 else limit
            chunks.append(para[:cut].strip())
            para = para[cut:].strip()
        current = para
    if current:
        chunks.append(current)
    return chunks


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunk", type=int, default=0,
                    help="max characters per part; 0 writes whole files only")
    args = ap.parse_args()

    OUT.mkdir(exist_ok=True)
    total = 0

    for md_path in sorted(HERE.glob("*.md")):
        text = clean(md_path.read_text(encoding="utf-8"))
        total += len(text.encode("utf-8"))
        stem = md_path.stem

        (OUT / f"{stem}.txt").write_text(text, encoding="utf-8")

        if args.chunk:
            parts = split_chunks(text, args.chunk)
            for i, part in enumerate(parts, 1):
                name = f"{stem}.part{i:02d}.txt" if len(parts) > 1 else f"{stem}.txt"
                if len(parts) > 1:
                    (OUT / name).write_text(part + "\n", encoding="utf-8")
            print(f"{stem:42s} {len(text):7,d} chars  {len(parts):3d} part(s)")
        else:
            print(f"{stem:42s} {len(text):7,d} chars")

    print(f"\ntotal {total:,} bytes -> ${total / 1_000_000 * 15:.2f} at $15 per million bytes")


if __name__ == "__main__":
    main()
