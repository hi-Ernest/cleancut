"""
字幕格式化 — 将净化后的 segments 导出为 SRT 文件
"""

from __future__ import annotations

from pathlib import Path


def _to_srt_time(seconds: float) -> str:
    h, remainder = divmod(seconds, 3600)
    m, s = divmod(remainder, 60)
    ms = int((s - int(s)) * 1000)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{ms:03d}"


def export_srt(segments: list[dict], output_path: str) -> str:
    """导出 SRT 字幕文件"""
    lines: list[str] = []
    idx = 1
    for seg in segments:
        text = seg.get("text", "").strip()
        if not text:
            continue
        start = _to_srt_time(float(seg["start"]))
        end = _to_srt_time(float(seg["end"]))
        lines.append(str(idx))
        lines.append(f"{start} --> {end}")
        lines.append(text)
        lines.append("")
        idx += 1

    Path(output_path).write_text("\n".join(lines), encoding="utf-8")
    print(f"  [字幕] 已导出 {idx - 1} 条字幕 → {output_path}")
    return output_path
