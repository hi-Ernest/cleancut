"""
音频提取与降噪
- ffmpeg 从视频中提取音轨
- noisereduce 去除稳态噪声
"""

import subprocess
import shutil
from pathlib import Path

import numpy as np
import soundfile as sf


def _require_ffmpeg():
    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "ffmpeg 未安装。macOS: brew install ffmpeg / Linux: apt install ffmpeg"
        )


def extract_audio(input_path: str, output_wav: str) -> str:
    """从视频/音频文件提取 16kHz 单声道 WAV"""
    _require_ffmpeg()
    output = Path(output_wav)
    if output.exists():
        print(f"  [跳过] 音频已提取: {output}")
        return str(output)

    print(f"  [音频提取] {input_path} → {output}")
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", input_path,
            "-vn",                # 丢弃视频流
            "-acodec", "pcm_s16le",
            "-ar", "16000",       # Whisper 最佳采样率
            "-ac", "1",           # 单声道
            output_wav,
        ],
        capture_output=True,
        check=True,
    )
    return str(output)


def denoise(input_wav: str, output_wav: str) -> str:
    """
    用 noisereduce 做谱减法降噪。
    对稳态噪声（底噪、嗡嗡声、空调声）效果好。
    """
    output = Path(output_wav)
    if output.exists():
        print(f"  [跳过] 降噪已完成: {output}")
        return str(output)

    import noisereduce as nr

    print(f"  [降噪] {input_wav} → {output}")
    data, rate = sf.read(input_wav)

    reduced = nr.reduce_noise(
        y=data,
        sr=rate,
        stationary=True,
        prop_decrease=0.75,
    )

    sf.write(str(output), reduced, rate)
    return str(output)


def has_video_stream(input_path: str) -> bool:
    """检测文件是否包含视频流"""
    _require_ffmpeg()
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=codec_type",
            "-of", "csv=p=0",
            input_path,
        ],
        capture_output=True,
        text=True,
    )
    return "video" in result.stdout
