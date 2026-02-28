#!/usr/bin/env python3
"""
optmpx — 纪录片字幕净化流水线
视频/音频 → 提取音轨 → 降噪 → Whisper 转录(词级别) → LLM 净化 → 剪辑媒体

用法:
    python pipeline.py 视频.mp4
    python pipeline.py 录音.m4a --whisper-mode api
    python pipeline.py 视频.mov --no-denoise --skip-video
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import config as cfg
from audio import extract_audio, denoise, has_video_stream
from cache import artifact_path, load_json, save_json, save_text
from clean import clean_transcript, subtitles_to_transcript
from edit import compute_keep_ranges, compute_cut_summary, edit_audio, edit_video
from subtitle import export_srt
from transcribe import transcribe


def run(
    input_path: str,
    *,
    output_srt: str | None = None,
    skip_denoise: bool = False,
    skip_video: bool = False,
):
    """执行完整流水线"""
    src = Path(input_path)
    if not src.exists():
        print(f"错误: 文件不存在 — {src}")
        sys.exit(1)

    workdir = cfg.get_workdir(input_path)
    is_video = has_video_stream(input_path)
    t0 = time.time()

    print(f"\n{'='*60}")
    print(f"  optmpx 字幕净化流水线")
    print(f"  输入: {src}")
    print(f"  工作目录: {workdir}")
    print(f"  类型: {'视频' if is_video else '音频'}")
    print(f"  转录: {cfg.WHISPER_MODE} ({cfg.WHISPER_MODEL_SIZE})")
    print(f"  净化: {cfg.LLM_MODEL} @ {cfg.LLM_BASE_URL}")
    print(f"{'='*60}\n")

    # ── 步骤 1: 提取音频 ─────────────────────────────────
    print("[1/6] 提取音频 ...")
    raw_wav = str(artifact_path(workdir, "raw_audio"))
    extract_audio(input_path, raw_wav)

    # ── 步骤 2: 降噪 ────────────────────────────────────
    if skip_denoise or not cfg.DENOISE_ENABLED:
        print("[2/6] 跳过降噪")
        whisper_input = raw_wav
        denoised_wav = None
    else:
        print("[2/6] 音频降噪 ...")
        denoised_wav = str(artifact_path(workdir, "denoised_audio"))
        denoise(raw_wav, denoised_wav)
        whisper_input = denoised_wav

    # ── 步骤 3: Whisper 转录 (词级别时间戳) ──────────────
    print("[3/6] 语音转录 (词级别时间戳) ...")
    transcript_path = artifact_path(workdir, "raw_transcript")
    cached = load_json(transcript_path)
    if cached is not None and "words" in cached:
        print(f"  [跳过] 已有缓存: {transcript_path}")
        transcript_data = cached
    else:
        transcript_data = transcribe(whisper_input)
        save_json(transcript_path, transcript_data)

    # ── 步骤 4: LLM 词级别净化 ──────────────────────────
    print("[4/6] 语义净化 (词级别标记) ...")
    clean_result_path = artifact_path(workdir, "clean_result")
    cached = load_json(clean_result_path)
    if cached is not None:
        print(f"  [跳过] 已有缓存: {clean_result_path}")
        clean_result = cached
    else:
        clean_result = clean_transcript(transcript_data)
        save_json(clean_result_path, clean_result)

    subtitles = clean_result["subtitles"]
    kept_words = clean_result["kept_words"]
    removed_words = clean_result.get("removed_words", [])

    # ── 步骤 5: 生成净化稿 + SRT ────────────────────────
    print("[5/6] 生成净化稿 & 字幕 ...")
    transcript_txt = artifact_path(workdir, "clean_transcript")
    clean_text = subtitles_to_transcript(subtitles)
    save_text(transcript_txt, clean_text)
    print(f"  [净化稿] → {transcript_txt}")

    srt_out = output_srt or str(artifact_path(workdir, "subtitle"))
    export_srt(subtitles, srt_out)

    # ── 步骤 6: 基于词级别时间戳剪辑媒体 ────────────────
    media_out = None
    if skip_video or not denoised_wav:
        reason = "已跳过" if skip_video else "未降噪"
        print(f"[6/6] 跳过媒体剪辑 ({reason})")
    else:
        print("[6/6] 剪辑净化媒体 (词级别精确切除) ...")
        keep_ranges = compute_keep_ranges(kept_words)
        save_json(artifact_path(workdir, "keep_ranges"), keep_ranges)

        summary = compute_cut_summary(
            transcript_data["words"], kept_words, removed_words, keep_ranges
        )
        print(f"  [统计] 原始 {summary['total_duration']:.1f}s → "
              f"保留 {summary['keep_duration']:.1f}s, "
              f"剪除 {summary['cut_duration']:.1f}s "
              f"({summary['keep_segments']} 个片段)")
        if summary["removed_count"] > 0:
            print(f"  [删除] {summary['removed_words_text']}")

        if is_video:
            media_out = str(artifact_path(workdir, "edited_video"))
            edit_video(input_path, denoised_wav, keep_ranges, media_out)
        else:
            media_out = str(artifact_path(workdir, "edited_audio"))
            edit_audio(denoised_wav, keep_ranges, media_out)

    # ── 完成 ─────────────────────────────────────────────
    elapsed = time.time() - t0
    media_label = "净化视频" if is_video else "净化音频"
    print(f"\n{'='*60}")
    print(f"  完成! 耗时 {elapsed:.1f}s")
    print(f"  净化稿:     {transcript_txt}")
    print(f"  字幕:       {srt_out}")
    if media_out:
        print(f"  {media_label}: {media_out}")
    print(f"{'='*60}\n")


def main():
    ap = argparse.ArgumentParser(
        description="optmpx — 纪录片字幕净化流水线",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python pipeline.py 访谈.mp4
  python pipeline.py 录音.m4a --whisper-mode api
  python pipeline.py 视频.mov --no-denoise --skip-video

环境变量:
  DEEPSEEK_API_KEY    DeepSeek API Key (必须)
  OPENAI_API_KEY      OpenAI API Key (Whisper API 模式需要)
  LLM_BASE_URL        自定义 LLM 接口地址
  LLM_MODEL           自定义模型名
  WHISPER_MODE        转录模式: local / api
        """,
    )
    ap.add_argument("input", help="输入视频或音频文件")
    ap.add_argument("-o", "--output", default=None, help="输出 SRT 路径")
    ap.add_argument(
        "--whisper-mode", choices=["local", "api"], default=None,
        help="转录模式 (覆盖环境变量)",
    )
    ap.add_argument(
        "--no-denoise", action="store_true", help="跳过音频降噪",
    )
    ap.add_argument(
        "--skip-video", action="store_true", help="跳过净化视频合成",
    )
    args = ap.parse_args()

    if args.whisper_mode:
        cfg.WHISPER_MODE = args.whisper_mode

    run(
        args.input,
        output_srt=args.output,
        skip_denoise=args.no_denoise,
        skip_video=args.skip_video,
    )


if __name__ == "__main__":
    main()
