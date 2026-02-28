"""
中间结果持久化 — 每一步输出保存到工作目录，已存在则自动跳过。
"""

import json
from pathlib import Path

# 各阶段文件命名约定
FILES = {
    "raw_audio": "01_raw_audio.wav",
    "denoised_audio": "02_denoised_audio.wav",
    "raw_transcript": "03_raw_transcript.json",
    "clean_result": "04_clean_result.json",
    "clean_transcript": "04_clean_transcript.txt",
    "keep_ranges": "05_keep_ranges.json",
    "subtitle": "06_output.srt",
    "edited_video": "07_edited.mp4",
    "edited_audio": "07_edited.m4a",
}


def artifact_path(workdir: Path, key: str) -> Path:
    return workdir / FILES[key]


def load_json(path: Path) -> list | dict | None:
    if path.exists():
        return json.loads(path.read_text("utf-8"))
    return None


def save_json(path: Path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")


def save_text(path: Path, text: str):
    path.write_text(text, "utf-8")


def load_text(path: Path) -> str | None:
    if path.exists():
        return path.read_text("utf-8")
    return None
