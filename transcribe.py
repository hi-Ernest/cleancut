"""
语音转录 — 支持本地 faster-whisper 和 OpenAI Whisper API 两种模式
输出词级别时间戳，用于后续精确剪辑。
"""

from __future__ import annotations

import config as cfg


def transcribe(audio_path: str) -> dict:
    """
    转录音频，返回 segments + words 两层数据：
    {
        "segments": [{"id", "start", "end", "text"}, ...],
        "words":    [{"word", "start", "end"}, ...]
    }
    """
    if cfg.WHISPER_MODE == "api":
        return _transcribe_api(audio_path)
    return _transcribe_local(audio_path)


def _transcribe_local(audio_path: str) -> dict:
    """本地 faster-whisper，开启词级别时间戳"""
    from faster_whisper import WhisperModel

    print(f"  [转录] 本地 faster-whisper ({cfg.WHISPER_MODEL_SIZE}), 词级别时间戳 ...")
    model = WhisperModel(
        cfg.WHISPER_MODEL_SIZE,
        device="auto",
        compute_type="auto",
    )

    raw_segments, info = model.transcribe(
        audio_path,
        language=cfg.WHISPER_LANGUAGE,
        word_timestamps=True,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=500),
    )

    segments = []
    all_words = []
    seg_idx = 0

    for seg in raw_segments:
        text = seg.text.strip()
        if not text:
            continue

        seg_words = []
        if seg.words:
            for w in seg.words:
                word_text = w.word.strip()
                if not word_text:
                    continue
                word_entry = {
                    "word": word_text,
                    "start": round(w.start, 3),
                    "end": round(w.end, 3),
                }
                seg_words.append(word_entry)
                all_words.append(word_entry)

        segments.append({
            "id": seg_idx,
            "start": round(seg.start, 3),
            "end": round(seg.end, 3),
            "text": text,
            "words": seg_words,
        })
        seg_idx += 1

    print(f"       → {len(segments)} 个片段, {len(all_words)} 个词, "
          f"语言: {info.language} (概率 {info.language_probability:.0%})")
    return {"segments": segments, "words": all_words}


def _transcribe_api(audio_path: str) -> dict:
    """调用 OpenAI Whisper API，带词级别时间戳"""
    from openai import OpenAI

    if not cfg.OPENAI_API_KEY:
        raise ValueError("WHISPER_MODE=api 但 OPENAI_API_KEY 未设置")

    client = OpenAI(api_key=cfg.OPENAI_API_KEY)
    print(f"  [转录] OpenAI Whisper API, 词级别时间戳 ...")

    with open(audio_path, "rb") as f:
        resp = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            response_format="verbose_json",
            timestamp_granularities=["word", "segment"],
            language=cfg.WHISPER_LANGUAGE,
        )

    segments = []
    all_words = []

    for s in resp.segments:
        text = s.text.strip()
        if not text:
            continue
        segments.append({
            "id": s.id,
            "start": round(s.start, 3),
            "end": round(s.end, 3),
            "text": text,
            "words": [],
        })

    if hasattr(resp, "words") and resp.words:
        for w in resp.words:
            word_text = w.word.strip()
            if not word_text:
                continue
            word_entry = {
                "word": word_text,
                "start": round(w.start, 3),
                "end": round(w.end, 3),
            }
            all_words.append(word_entry)
            for seg in segments:
                if seg["start"] <= w.start < seg["end"]:
                    seg["words"].append(word_entry)
                    break

    print(f"       → {len(segments)} 个片段, {len(all_words)} 个词")
    return {"segments": segments, "words": all_words}
