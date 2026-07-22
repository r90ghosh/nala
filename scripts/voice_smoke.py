#!/usr/bin/env python3
"""Live smoke test for the voice pipeline: generates a WAV via macOS `say`,
POSTs it to /api/voice/turn on a running `nala.serve` instance with a
harmless status question, and prints transcript + reply + timing.

Requires: `nala.serve` already running (see CLAUDE.md's Commands section),
and macOS `say` (used only to generate test input audio — unrelated to
nala's own Kokoro TTS).

Usage: .venv/bin/python scripts/voice_smoke.py [--url http://127.0.0.1:8642]
"""

import argparse
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

DEFAULT_URL = "http://127.0.0.1:8642"
SMOKE_TEXT = "what's my status"


def _make_wav(path: Path, text: str) -> None:
    subprocess.run(
        ["say", "-o", str(path), "--data-format=LEI16@16000", "--file-format=WAVE", text],
        check=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default=DEFAULT_URL, help=f"nala.serve base URL (default: {DEFAULT_URL})")
    parser.add_argument("--text", default=SMOKE_TEXT, help=f"text to speak as input (default: {SMOKE_TEXT!r})")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        wav_path = Path(tmp) / "smoke.wav"
        print(f"Generating input audio via `say`: {args.text!r}")
        _make_wav(wav_path, args.text)

        print(f"POSTing to {args.url}/api/voice/turn ...")
        start = time.monotonic()
        with open(wav_path, "rb") as f:
            resp = httpx.post(
                f"{args.url}/api/voice/turn",
                files={"audio": ("smoke.wav", f, "audio/wav")},
                # serve.py's CSRF gate requires Origin on every state-changing
                # request now — --url IS an origin (scheme://host[:port]), so
                # this satisfies both the local-dev allow-list and the
                # tunnel's dynamic Host-derived rule.
                headers={"Origin": args.url},
                timeout=60.0,
            )
        elapsed_ms = int((time.monotonic() - start) * 1000)

    if resp.status_code != 200:
        print(f"FAILED: HTTP {resp.status_code} — {resp.text}", file=sys.stderr)
        return 1

    data = resp.json()
    print(f"Round-trip time: {elapsed_ms}ms")

    if data.get("ask_repeat"):
        print(f"ask_repeat: True — reason: {data.get('reason')}")
        print(f"(heard: {data.get('transcript')!r})")
        return 0

    print(f"Transcript:  {data.get('transcript')!r}")
    print(f"Reply text:  {data.get('reply_text')!r}")
    print(f"Status:      {data.get('status')}")
    audio_b64 = data.get("audio_b64") or ""
    print(f"Reply audio: {len(audio_b64)} base64 chars ({len(audio_b64) * 3 // 4} bytes approx)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
