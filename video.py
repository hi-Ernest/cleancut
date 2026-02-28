"""
媒体输出 — 视频混音 / 音频导出
"""

import subprocess
import shutil
from pathlib import Path


def _require_ffmpeg():
    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "ffmpeg 未安装。macOS: brew install ffmpeg / Linux: apt install ffmpeg"
        )


def remux_with_clean_audio(
    original_video: str,
    denoised_audio: str,
    output_video: str,
) -> str:
    """将降噪音频混回原视频，输出净化视频"""
    _require_ffmpeg()
    output = Path(output_video)
    if output.exists():
        print(f"  [跳过] 净化视频已存在: {output}")
        return str(output)

    print(f"  [混音] 合成净化视频 → {output}")
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", original_video,
            "-i", denoised_audio,
            "-c:v", "copy",
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-shortest",
            str(output),
        ],
        capture_output=True,
        check=True,
    )
    return str(output)


def export_clean_audio(
    denoised_wav: str,
    output_audio: str,
) -> str:
    """将降噪后的 WAV 编码为 M4A (AAC)，体积更小便于分发"""
    _require_ffmpeg()
    output = Path(output_audio)
    if output.exists():
        print(f"  [跳过] 净化音频已存在: {output}")
        return str(output)

    print(f"  [导出] 净化音频 → {output}")
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", denoised_wav,
            "-c:a", "aac",
            "-b:a", "128k",
            str(output),
        ],
        capture_output=True,
        check=True,
    )
    return str(output)
