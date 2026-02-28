"""
基于转录对齐的音视频剪辑
根据净化后 segments 的时间戳，切除语气词/空白片段，拼接保留内容。
"""

from __future__ import annotations

import subprocess
import shutil
import tempfile
from pathlib import Path


def compute_keep_ranges(
    kept_words: list[dict],
    merge_gap: float = 0.15,
) -> list[tuple[float, float]]:
    """
    从保留的词列表计算要保留的时间范围。
    相邻词之间的间隙 <= merge_gap 秒时合并为一个连续区间。
    间隙 > merge_gap 即为被删除的语气词，从媒体中剪掉。
    """
    if not kept_words:
        return []

    sorted_words = sorted(kept_words, key=lambda w: float(w["start"]))
    ranges: list[tuple[float, float]] = []

    for w in sorted_words:
        start = round(float(w["start"]), 3)
        end = round(float(w["end"]), 3)
        if start >= end:
            continue
        if ranges and start <= ranges[-1][1] + merge_gap:
            ranges[-1] = (ranges[-1][0], max(ranges[-1][1], end))
        else:
            ranges.append((start, end))
    return ranges


def compute_cut_summary(
    all_words: list[dict],
    kept_words: list[dict],
    removed_words: list[dict],
    keep_ranges: list[tuple[float, float]],
) -> dict:
    """生成剪辑摘要"""
    if not all_words:
        return {
            "total_duration": 0, "keep_duration": 0,
            "cut_duration": 0, "keep_segments": 0,
            "removed_count": 0, "removed_words_text": "",
        }

    total_start = min(float(w["start"]) for w in all_words)
    total_end = max(float(w["end"]) for w in all_words)
    total_duration = total_end - total_start

    keep_duration = sum(end - start for start, end in keep_ranges)
    cut_duration = total_duration - keep_duration

    removed_text = ", ".join(
        f'"{w["word"]}"({w["start"]:.1f}s)' for w in removed_words[:20]
    )
    if len(removed_words) > 20:
        removed_text += f" ...等{len(removed_words)}个"

    return {
        "total_duration": round(total_duration, 3),
        "keep_duration": round(keep_duration, 3),
        "cut_duration": round(cut_duration, 3),
        "keep_segments": len(keep_ranges),
        "removed_count": len(removed_words),
        "removed_words_text": removed_text,
    }


def _require_ffmpeg():
    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "ffmpeg 未安装。macOS: brew install ffmpeg / Linux: apt install ffmpeg"
        )


def _build_audio_filter(keep_ranges: list[tuple[float, float]], input_idx: int = 0) -> str:
    """构建音频剪辑的 filter_complex 字符串"""
    parts = []
    labels = []
    for i, (start, end) in enumerate(keep_ranges):
        parts.append(
            f"[{input_idx}:a]atrim=start={start}:end={end},"
            f"asetpts=PTS-STARTPTS[a{i}]"
        )
        labels.append(f"[a{i}]")
    n = len(keep_ranges)
    parts.append("".join(labels) + f"concat=n={n}:v=0:a=1[outa]")
    return ";".join(parts)


def _build_video_filter(
    keep_ranges: list[tuple[float, float]],
    video_idx: int = 0,
    audio_idx: int = 1,
) -> str:
    """构建视频+音频同步剪辑的 filter_complex 字符串"""
    parts = []
    labels = []
    for i, (start, end) in enumerate(keep_ranges):
        parts.append(
            f"[{video_idx}:v]trim=start={start}:end={end},"
            f"setpts=PTS-STARTPTS[v{i}]"
        )
        parts.append(
            f"[{audio_idx}:a]atrim=start={start}:end={end},"
            f"asetpts=PTS-STARTPTS[a{i}]"
        )
        labels.append(f"[v{i}][a{i}]")
    n = len(keep_ranges)
    parts.append("".join(labels) + f"concat=n={n}:v=1:a=1[outv][outa]")
    return ";".join(parts)


def edit_audio(
    denoised_wav: str,
    keep_ranges: list[tuple[float, float]],
    output_path: str,
) -> str:
    """根据保留区间剪辑音频，切除语气词片段，输出 M4A"""
    _require_ffmpeg()
    output = Path(output_path)
    if output.exists():
        print(f"  [跳过] 剪辑音频已存在: {output}")
        return str(output)

    if not keep_ranges:
        print("  [警告] 无保留区间，跳过音频剪辑")
        return ""

    print(f"  [剪辑] 音频 → 保留 {len(keep_ranges)} 个片段 → {output}")

    fc = _build_audio_filter(keep_ranges)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False
    ) as f:
        f.write(fc)
        filter_script = f.name

    try:
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", denoised_wav,
                "-filter_complex_script", filter_script,
                "-map", "[outa]",
                "-c:a", "aac", "-b:a", "128k",
                str(output),
            ],
            capture_output=True,
            check=True,
        )
    finally:
        Path(filter_script).unlink(missing_ok=True)

    return str(output)


def edit_video(
    original_video: str,
    denoised_audio: str,
    keep_ranges: list[tuple[float, float]],
    output_path: str,
) -> str:
    """
    根据保留区间剪辑视频。
    视频流来自原始文件，音频流来自降噪文件，
    按相同时间范围同步裁剪后拼接。
    """
    _require_ffmpeg()
    output = Path(output_path)
    if output.exists():
        print(f"  [跳过] 剪辑视频已存在: {output}")
        return str(output)

    if not keep_ranges:
        print("  [警告] 无保留区间，跳过视频剪辑")
        return ""

    print(f"  [剪辑] 视频 → 保留 {len(keep_ranges)} 个片段 → {output}")

    fc = _build_video_filter(keep_ranges, video_idx=0, audio_idx=1)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False
    ) as f:
        f.write(fc)
        filter_script = f.name

    try:
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-i", original_video,
                "-i", denoised_audio,
                "-filter_complex_script", filter_script,
                "-map", "[outv]", "-map", "[outa]",
                "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                "-c:a", "aac", "-b:a", "128k",
                str(output),
            ],
            capture_output=True,
            check=True,
        )
    finally:
        Path(filter_script).unlink(missing_ok=True)

    return str(output)
