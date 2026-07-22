"""Fully local voice: Parakeet (parakeet-mlx) for STT, Kokoro (mlx-audio) for
TTS. Both models are lazy-loaded singletons — the first voice request pays
the (multi-second) model load, everything after is sub-second (measured on
this machine: ~80ms warm STT for a one-sentence utterance, ~150-300ms warm
TTS for a short reply). GET /api/voice/warmup forces both to load ahead of
time instead of on the first real request.

MLX ARRAYS ARE THREAD-AFFINE — a real gotcha found while wiring this up, not
in the original spec. mx.new_stream's own docstring: "The stream can only be
used on the thread where it was created on, using it in any other thread
would result in errors." A model loaded on one thread (e.g. inside
asyncio.to_thread, which can and does hand different calls to different
worker threads from Python's default pool) breaks with
`RuntimeError: There is no Stream(cpu, N) in current thread` the moment a
LATER call lands on a different thread. Reproduced live via /api/voice/turn
before this fix existed. Fix: every MLX-touching call (model load AND
inference, both STT and TTS) is funneled through one dedicated single-worker
executor (_MLX_EXECUTOR) so it always runs on the exact same thread for the
lifetime of the process — regardless of which thread (asyncio.to_thread's
pool, FastAPI's sync-route pool, a test) called transcribe()/synthesize().

mlx-audio's TTS pipeline (misaki's phonemizer setup, specifically) has also
been reported to shell out to `uv` on some first-run code paths and expects
a sane VIRTUAL_ENV. Verified via direct testing (see CLAUDE.md's M6
gotchas) that setting VIRTUAL_ENV defensively at import time was sufficient
in practice — synthesis succeeded from a different cwd with VIRTUAL_ENV
unset too, so no cwd requirement turned out to be needed on top of the
thread-pinning fix above.

Both transcribe() and synthesize() log their own stt_result/tts_result
event and a $0 spend row — parakeet/kokoro run at zero marginal cost, but
the record stays complete, same convention as llama3.2:3b via Ollama."""

import os
import sys
import time
import uuid
import wave
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

os.environ.setdefault("VIRTUAL_ENV", sys.prefix)

import parakeet_mlx
from mlx_audio.tts.generate import generate_audio
from mlx_audio.tts.utils import load_model

from nala import events
from nala.config import get_data_dir
from nala.spend import record_spend

STT_MODEL_ID = "mlx-community/parakeet-tdt-0.6b-v2"
TTS_MODEL_ID = "mlx-community/Kokoro-82M-bf16"
TTS_VOICE = "af_heart"
SESSION_ID = "voice"

# Loud-failure clause 3 (never guess on low-confidence perception) thresholds.
# A real test against ~200ms of silence still produced a hallucinated "Yeah."
# at ~0.8 aggregate confidence — duration/length are the primary defense for
# that failure mode; confidence is a secondary net for longer-but-garbled
# audio. All three are first-cut values; expect to retune after real PTT use.
MIN_TRANSCRIPT_CHARS = 2
MIN_AUDIO_DURATION_MS = 300
LOW_CONFIDENCE_THRESHOLD = 0.5

# Every MLX call (model load, transcribe, synthesize) is submitted here so it
# always runs on the same one thread — see the module docstring.
_MLX_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="nala-voice-mlx")

_stt_model = None
_tts_model = None


def _run_on_mlx_thread(fn, /, *args, **kwargs):
    return _MLX_EXECUTOR.submit(fn, *args, **kwargs).result()


def _get_stt_model():
    # Only ever called from within _run_on_mlx_thread — safe to check-then-set
    # without a lock since the executor guarantees one call in flight at a time.
    global _stt_model
    if _stt_model is None:
        _stt_model = parakeet_mlx.from_pretrained(STT_MODEL_ID)
    return _stt_model


def _get_tts_model():
    global _tts_model
    if _tts_model is None:
        _tts_model = load_model(TTS_MODEL_ID)
    return _tts_model


def _warmup_on_mlx_thread() -> None:
    _get_stt_model()
    _get_tts_model()


def warmup() -> None:
    """Forces both models to load now rather than on the first real request."""
    _run_on_mlx_thread(_warmup_on_mlx_thread)


def _wav_duration_ms(path: Path) -> int:
    with wave.open(str(path), "rb") as w:
        rate = w.getframerate()
        return int((w.getnframes() / rate) * 1000) if rate else 0


def _aggregate_confidence(result) -> float | None:
    """parakeet-mlx DOES expose confidence (contrary to the M6 spec's
    uncertainty) — AlignedSentence.confidence is the geometric mean of its
    tokens' confidences. Averaged across sentences here; None if there were
    no sentences at all (nothing to gate on)."""
    if not result.sentences:
        return None
    return sum(s.confidence for s in result.sentences) / len(result.sentences)


def _transcribe_on_mlx_thread(path_str: str):
    return _get_stt_model().transcribe(path_str)


def transcribe(wav_path: str | Path, *, turn_id: str | None = None, data_dir: Path | None = None) -> dict:
    """{text, duration_ms, latency_ms, confidence}. duration_ms is the actual
    uploaded audio's length (from the WAV header, independent of what the
    model made of it); confidence is None when the model returned no
    sentences to score."""
    wav_path = Path(wav_path)
    duration_ms = _wav_duration_ms(wav_path)

    start = time.monotonic()
    result = _run_on_mlx_thread(_transcribe_on_mlx_thread, str(wav_path))
    latency_ms = int((time.monotonic() - start) * 1000)

    text = result.text.strip()
    confidence = _aggregate_confidence(result)

    events.log_event(
        SESSION_ID, turn_id, "stt_result",
        {"text": text, "duration_ms": duration_ms, "latency_ms": latency_ms, "confidence": confidence},
        data_dir=data_dir,
    )
    record_spend(turn_id=turn_id, model="parakeet-tdt-0.6b", input_tokens=0, output_tokens=0, data_dir=data_dir)

    return {"text": text, "duration_ms": duration_ms, "latency_ms": latency_ms, "confidence": confidence}


def gate_low_confidence(stt_result: dict) -> tuple[bool, str | None]:
    """Loud-failure clause 3: never guess on a low-confidence transcription —
    ask the user to repeat instead of running the turn. Returns
    (should_ask_repeat, reason). Checked in order: transcript length, audio
    duration, then model confidence (the two heuristics run regardless of
    whether confidence is usable, since testing showed confidence alone
    misses the short-silence-hallucination case)."""
    text = stt_result["text"]
    if len(text) < MIN_TRANSCRIPT_CHARS:
        return True, "transcript too short or empty"
    if stt_result["duration_ms"] < MIN_AUDIO_DURATION_MS:
        return True, f"audio too short ({stt_result['duration_ms']}ms)"
    confidence = stt_result.get("confidence")
    if confidence is not None and confidence < LOW_CONFIDENCE_THRESHOLD:
        return True, f"low transcription confidence ({confidence:.2f})"
    return False, None


def _synthesize_on_mlx_thread(*, text: str, file_prefix: str) -> None:
    generate_audio(
        text=text,
        model=_get_tts_model(),
        voice=TTS_VOICE,
        file_prefix=file_prefix,
        audio_format="wav",
        join_audio=True,
        save=True,
        verbose=False,
    )


def synthesize(text: str, *, turn_id: str | None = None, data_dir: Path | None = None) -> bytes:
    """Returns WAV bytes. mlx-audio's generate_audio only knows how to write
    to disk, not return bytes directly — writes to a uuid-named temp file
    under NALA_DATA_DIR/tmp_voice (collision-proof across concurrent calls),
    reads it back, then deletes it."""
    tmp_dir = (data_dir or get_data_dir()) / "tmp_voice"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    file_prefix = tmp_dir / f"tts-{uuid.uuid4().hex}"

    start = time.monotonic()
    _run_on_mlx_thread(_synthesize_on_mlx_thread, text=text, file_prefix=str(file_prefix))
    latency_ms = int((time.monotonic() - start) * 1000)

    wav_path = file_prefix.with_suffix(".wav")
    audio_bytes = wav_path.read_bytes()
    wav_path.unlink(missing_ok=True)

    events.log_event(
        SESSION_ID, turn_id, "tts_result",
        {"text_len": len(text), "latency_ms": latency_ms},
        data_dir=data_dir,
    )
    record_spend(turn_id=turn_id, model="kokoro-82m", input_tokens=0, output_tokens=0, data_dir=data_dir)

    return audio_bytes
