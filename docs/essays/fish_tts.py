#!/usr/bin/env python3
"""Send the essay text to the Fish Audio API and save one MP3 per essay.

Dry run first (spends nothing, prints the bill):

    python3 fish_tts.py --voice <reference_id>

Then generate for real:

    export FISH_API_KEY=your_key_here
    python3 fish_tts.py --voice <reference_id> --go

Safety: --go refuses to start if the estimated cost exceeds --max-usd
(default $4.00), and it stops mid-run if the running total reaches that cap.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

TTS_DIR = Path(__file__).resolve().parent / "tts"
AUDIO_DIR = Path(__file__).resolve().parent / "audio"
ENDPOINT = "https://api.fish.audio/v1/tts"
USD_PER_MILLION_BYTES = 15.0


def chunks(text: str, limit: int) -> list[str]:
    """Split on blank lines so a request never ends mid-sentence."""
    out: list[str] = []
    current = ""
    for para in text.split("\n\n"):
        candidate = para if not current else current + "\n\n" + para
        if len(candidate) <= limit:
            current = candidate
        else:
            if current:
                out.append(current)
            current = para
    if current:
        out.append(current)
    return out


def synthesize(chunk: str, key: str, voice: str, model: str, fmt: str) -> bytes:
    body = json.dumps({
        "text": chunk,
        "reference_id": voice,
        "format": fmt,
        "mp3_bitrate": 128,
        "normalize": True,
    }).encode("utf-8")

    request = urllib.request.Request(
        ENDPOINT,
        data=body,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "model": model,
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        return response.read()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--voice", required=True,
                    help="reference_id of the voice, from its fish.audio URL")
    ap.add_argument("--model", default="s1",
                    help="model header: s1, s2-pro, s2.1-pro-free ...")
    ap.add_argument("--chunk", type=int, default=4000,
                    help="characters per request")
    ap.add_argument("--format", default="mp3", choices=["mp3", "wav", "opus"])
    ap.add_argument("--max-usd", type=float, default=4.00,
                    help="hard spending ceiling for this run")
    ap.add_argument("--only", default="",
                    help="substring filter, e.g. --only DEFENSE")
    ap.add_argument("--go", action="store_true",
                    help="actually call the API; without this it is a dry run")
    args = ap.parse_args()

    files = sorted(TTS_DIR.glob("*.txt"))
    if args.only:
        # An exact stem wins, so --only ARCHITECTURE cannot also pull in
        # ARCHITECTURE_AND_INTERVIEW_GUIDE. Otherwise fall back to substring.
        exact = [p for p in files if p.stem == args.only]
        files = exact or [p for p in files if args.only in p.name]
    if not files:
        print(f"no .txt files in {TTS_DIR}", file=sys.stderr)
        return 1

    plan = [(p, chunks(p.read_text(encoding="utf-8"), args.chunk)) for p in files]
    total_bytes = sum(len(c.encode("utf-8")) for _, cs in plan for c in cs)
    estimate = total_bytes / 1_000_000 * USD_PER_MILLION_BYTES

    for path, cs in plan:
        size = sum(len(c.encode("utf-8")) for c in cs)
        print(f"{path.stem:42s} {size:7,d} bytes  {len(cs):3d} request(s)")
    print(f"\n{len(files)} file(s), {total_bytes:,} bytes, "
          f"{sum(len(cs) for _, cs in plan)} requests")
    print(f"estimated cost at ${USD_PER_MILLION_BYTES:g}/M bytes: ${estimate:.2f}")

    if not args.go:
        print("\nDry run. Nothing was sent and nothing was charged.")
        print("Re-run with --go once the voice and model look right.")
        return 0

    if estimate > args.max_usd:
        print(f"\nRefusing to start: estimate ${estimate:.2f} exceeds "
              f"--max-usd ${args.max_usd:.2f}.", file=sys.stderr)
        return 1

    key = os.environ.get("FISH_API_KEY", "").strip()
    if not key:
        print("\nFISH_API_KEY is not set.", file=sys.stderr)
        return 1

    AUDIO_DIR.mkdir(exist_ok=True)
    spent = 0.0

    for path, cs in plan:
        target = AUDIO_DIR / f"{path.stem}.{args.format}"
        if target.exists():
            print(f"skip {path.stem} (already generated)")
            continue

        audio = bytearray()
        for i, chunk in enumerate(cs, 1):
            cost = len(chunk.encode("utf-8")) / 1_000_000 * USD_PER_MILLION_BYTES
            if spent + cost > args.max_usd:
                print(f"\nStopping: ${args.max_usd:.2f} ceiling reached.",
                      file=sys.stderr)
                return 1

            print(f"  {path.stem} part {i}/{len(cs)} ...", end="", flush=True)
            try:
                audio += synthesize(chunk, key, args.voice, args.model, args.format)
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")[:300]
                print(f" HTTP {exc.code}: {detail}", file=sys.stderr)
                return 1
            except urllib.error.URLError as exc:
                print(f" network error: {exc.reason}", file=sys.stderr)
                return 1

            spent += cost
            print(f" ok (${spent:.3f} so far)")
            time.sleep(0.5)

        target.write_bytes(bytes(audio))
        print(f"wrote {target}  ({len(audio) / 1_048_576:.1f} MB)")

    print(f"\nDone. Approximate spend this run: ${spent:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
