"""nala/voice.py — STT/TTS wrapped as lazy-loaded singletons. Tests never
load the real multi-hundred-MB models: _get_stt_model/_get_tts_model and
generate_audio are monkeypatched with fakes throughout."""

from pathlib import Path

import pytest

from nala import voice


def _write_wav(path: Path, duration_ms: int = 1000, rate: int = 16000) -> None:
    import wave
    n = int(rate * duration_ms / 1000)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * n)


class FakeSentence:
    def __init__(self, confidence):
        self.confidence = confidence


class FakeResult:
    def __init__(self, text, confidences=None):
        self.text = text
        self.sentences = [FakeSentence(c) for c in (confidences or [])]


class FakeSTTModel:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def transcribe(self, path):
        self.calls += 1
        return self.result


def test_wav_duration_ms_computes_from_header(tmp_path):
    path = tmp_path / "a.wav"
    _write_wav(path, duration_ms=1500, rate=16000)

    assert voice._wav_duration_ms(path) == 1500


def test_transcribe_returns_text_duration_latency_confidence(tmp_path, monkeypatch, data_dir):
    path = tmp_path / "a.wav"
    _write_wav(path, duration_ms=1000)
    fake_model = FakeSTTModel(FakeResult("hello world", confidences=[0.9, 0.8]))
    monkeypatch.setattr(voice, "_get_stt_model", lambda: fake_model)

    result = voice.transcribe(path, turn_id="t1")

    assert result["text"] == "hello world"
    assert result["duration_ms"] == 1000
    assert result["confidence"] == pytest.approx(0.85)
    assert result["latency_ms"] >= 0
    assert fake_model.calls == 1


def test_transcribe_strips_whitespace_from_text(tmp_path, monkeypatch, data_dir):
    path = tmp_path / "a.wav"
    _write_wav(path, duration_ms=1000)
    fake_model = FakeSTTModel(FakeResult("  hello  ", confidences=[0.9]))
    monkeypatch.setattr(voice, "_get_stt_model", lambda: fake_model)

    result = voice.transcribe(path, turn_id="t1")

    assert result["text"] == "hello"


def test_transcribe_confidence_is_none_when_no_sentences(tmp_path, monkeypatch, data_dir):
    path = tmp_path / "a.wav"
    _write_wav(path, duration_ms=1000)
    fake_model = FakeSTTModel(FakeResult("", confidences=[]))
    monkeypatch.setattr(voice, "_get_stt_model", lambda: fake_model)

    result = voice.transcribe(path, turn_id="t1")

    assert result["confidence"] is None


def test_transcribe_logs_stt_result_event_and_zero_cost_spend(tmp_path, monkeypatch, data_dir):
    from datetime import datetime, timezone

    from nala import db, spend

    path = tmp_path / "a.wav"
    _write_wav(path, duration_ms=1000)
    fake_model = FakeSTTModel(FakeResult("hi", confidences=[0.9]))
    monkeypatch.setattr(voice, "_get_stt_model", lambda: fake_model)

    voice.transcribe(path, turn_id="t1")

    conn = db.connect()
    rows = conn.execute("SELECT * FROM events WHERE type = 'stt_result'").fetchall()
    conn.close()
    assert len(rows) == 1

    assert spend.today_total() == 0.0  # parakeet is rated at 0/0 but still ledgered
    today = datetime.now(timezone.utc).date().isoformat()
    breakdown = spend.breakdown_for_day(today)
    assert any(b["model"] == "parakeet-tdt-0.6b" for b in breakdown)


def test_gate_low_confidence_empty_transcript(data_dir):
    is_low, reason = voice.gate_low_confidence({"text": "", "duration_ms": 1000, "confidence": 0.9})

    assert is_low is True
    assert "short or empty" in reason


def test_gate_low_confidence_short_duration(data_dir):
    is_low, reason = voice.gate_low_confidence({"text": "hello there", "duration_ms": 200, "confidence": 0.9})

    assert is_low is True
    assert "too short" in reason


def test_gate_low_confidence_low_score(data_dir):
    is_low, reason = voice.gate_low_confidence({"text": "hello there", "duration_ms": 1000, "confidence": 0.2})

    assert is_low is True
    assert "confidence" in reason


def test_gate_low_confidence_passes_when_all_signals_good(data_dir):
    is_low, reason = voice.gate_low_confidence({"text": "hello there", "duration_ms": 1000, "confidence": 0.9})

    assert is_low is False
    assert reason is None


def test_gate_low_confidence_passes_when_confidence_unavailable_but_heuristics_pass(data_dir):
    is_low, reason = voice.gate_low_confidence({"text": "hello there", "duration_ms": 1000, "confidence": None})

    assert is_low is False


def test_synthesize_returns_wav_bytes_from_generate_audio(monkeypatch, data_dir):
    def fake_generate_audio(*, file_prefix, **kwargs):
        Path(file_prefix + ".wav").write_bytes(b"FAKEWAVBYTES")

    monkeypatch.setattr(voice, "generate_audio", fake_generate_audio)
    monkeypatch.setattr(voice, "_get_tts_model", lambda: "fake-model")

    audio_bytes = voice.synthesize("hello", turn_id="t1")

    assert audio_bytes == b"FAKEWAVBYTES"


def test_synthesize_passes_model_voice_and_format_through(monkeypatch, data_dir):
    captured = {}

    def fake_generate_audio(*, file_prefix, **kwargs):
        captured.update(kwargs)
        Path(file_prefix + ".wav").write_bytes(b"X")

    monkeypatch.setattr(voice, "generate_audio", fake_generate_audio)
    monkeypatch.setattr(voice, "_get_tts_model", lambda: "fake-model")

    voice.synthesize("hello there", turn_id="t1")

    assert captured["voice"] == voice.TTS_VOICE
    assert captured["model"] == "fake-model"
    assert captured["audio_format"] == "wav"
    assert captured["join_audio"] is True
    assert captured["save"] is True


def test_synthesize_cleans_up_temp_file(monkeypatch, data_dir):
    written_paths = []

    def fake_generate_audio(*, file_prefix, **kwargs):
        p = Path(file_prefix + ".wav")
        p.write_bytes(b"X")
        written_paths.append(p)

    monkeypatch.setattr(voice, "generate_audio", fake_generate_audio)
    monkeypatch.setattr(voice, "_get_tts_model", lambda: "fake-model")

    voice.synthesize("hello", turn_id="t1")

    assert not written_paths[0].exists()


def test_synthesize_logs_tts_result_event_and_zero_cost_spend(monkeypatch, data_dir):
    from datetime import datetime, timezone

    from nala import db, spend

    def fake_generate_audio(*, file_prefix, **kwargs):
        Path(file_prefix + ".wav").write_bytes(b"X")

    monkeypatch.setattr(voice, "generate_audio", fake_generate_audio)
    monkeypatch.setattr(voice, "_get_tts_model", lambda: "fake-model")

    voice.synthesize("hello there", turn_id="t1")

    conn = db.connect()
    rows = conn.execute("SELECT * FROM events WHERE type = 'tts_result'").fetchall()
    conn.close()
    assert len(rows) == 1

    assert spend.today_total() == 0.0
    today = datetime.now(timezone.utc).date().isoformat()
    breakdown = spend.breakdown_for_day(today)
    assert any(b["model"] == "kokoro-82m" for b in breakdown)


def test_warmup_loads_both_models_exactly_once(monkeypatch, data_dir):
    calls = {"stt": 0, "tts": 0}
    monkeypatch.setattr(voice, "_stt_model", None)
    monkeypatch.setattr(voice, "_tts_model", None)

    def fake_from_pretrained(model_id):
        calls["stt"] += 1
        return "fake-stt-model"

    def fake_load_model(model_id):
        calls["tts"] += 1
        return "fake-tts-model"

    monkeypatch.setattr(voice.parakeet_mlx, "from_pretrained", fake_from_pretrained)
    monkeypatch.setattr(voice, "load_model", fake_load_model)

    voice.warmup()
    voice.warmup()

    assert calls == {"stt": 1, "tts": 1}
