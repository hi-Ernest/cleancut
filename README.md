# CleanCut

[English](./README.md) | [中文](./README.zh-CN.md)

> AI-powered filler-word removal pipeline — automatically detects and cuts filler words, producing clean subtitles and media files

## Features

- **Word-level precision editing**: Uses Whisper word-level timestamps to remove filler words with millisecond accuracy
- **LLM semantic understanding**: Uses DeepSeek / OpenAI-compatible models to accurately distinguish meaningful words from filler sounds
- **Fully automated pipeline**: Video/Audio → Denoising → Transcription → Cleaning → Editing, all in a single command
- **Result caching**: Intermediate results are automatically cached at each stage; interrupted runs can resume from the last failure point
- **Dual output**: Cleaned SRT subtitles + cleaned audio/video file

## Pipeline

```
Input media (mp4 / mov / m4a / wav ...)
   ↓ Extract audio (FFmpeg)
   ↓ Audio denoising (noisereduce)
   ↓ Whisper transcription (word-level timestamps)
   ↓ LLM semantic cleaning (mark keep/remove)
   ↓ Precise editing (FFmpeg concat)
   ↓
Cleaned subtitles (.srt) + Cleaned media (.mp4 / .m4a)
```

## Quick Start

### 1. Install System Dependencies

Install [FFmpeg](https://ffmpeg.org/download.html) first:

```bash
# macOS
brew install ffmpeg

# Ubuntu / Debian
sudo apt install ffmpeg
```

### 2. Install Python Dependencies

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Configure API Key

```bash
cp .env.example .env
# Edit .env and fill in DEEPSEEK_API_KEY
```

### 4. Run

```bash
# Process a video (full pipeline)
python pipeline.py interview.mp4

# Process audio using OpenAI Whisper API for transcription
python pipeline.py recording.m4a --whisper-mode api

# Skip denoising and only generate clean subtitles (no media editing)
python pipeline.py video.mov --no-denoise --skip-video

# Specify output subtitle path
python pipeline.py video.mp4 -o output.srt
```

## Environment Variables

Copy `.env.example` to `.env` and modify as needed:

| Variable | Description | Default |
|----------|-------------|---------|
| `DEEPSEEK_API_KEY` | DeepSeek API Key (required) | — |
| `OPENAI_API_KEY` | OpenAI API Key (for Whisper API mode) | — |
| `LLM_BASE_URL` | LLM endpoint URL | `https://api.deepseek.com` |
| `LLM_MODEL` | Cleaning model name | `deepseek-chat` |
| `WHISPER_MODE` | Transcription mode: `local` / `api` | `local` |
| `WHISPER_MODEL_SIZE` | Local Whisper model size | `large-v3` |
| `DENOISE_ENABLED` | Enable audio denoising | `1` |
| `CLEAN_BATCH_SIZE` | Number of word segments per LLM batch | `40` |

### Using Other LLM Services

You can switch to any OpenAI-compatible endpoint in `.env`:

```bash
# SiliconFlow Qwen
LLM_BASE_URL=https://api.siliconflow.cn/v1
LLM_MODEL=Qwen/Qwen2.5-72B-Instruct
LLM_API_KEY=sk-xxx

# OpenAI GPT-4o-mini
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
LLM_API_KEY=sk-xxx
```

## Output Files

After processing, the working directory `{filename}_workdir/` contains intermediate artifacts from each stage:

| File | Description |
|------|-------------|
| `01_raw_audio.wav` | Raw audio extracted from video |
| `02_denoised_audio.wav` | Denoised audio |
| `03_raw_transcript.json` | Raw Whisper transcript (with word-level timestamps) |
| `04_clean_result.json` | LLM cleaning result (keep/remove labels) |
| `04_clean_transcript.txt` | Cleaned plain text transcript |
| `05_keep_ranges.json` | List of time ranges to keep |
| `06_output.srt` | Cleaned subtitle file |
| `07_edited.*` | Cleaned audio or video |

## Project Structure

```
cleancut/
├── pipeline.py          # Main pipeline entry point
├── config.py            # Global configuration (environment variable loading)
├── transcribe.py        # Whisper transcription (local / API)
├── clean.py             # LLM semantic cleaning
├── edit.py              # Audio/video editing
├── audio.py             # Audio extraction and denoising
├── subtitle.py          # SRT subtitle export
├── cache.py             # Intermediate result caching
├── requirements.txt     # Python dependencies
└── .env.example         # Environment variable template
```

## Dependencies

- **[faster-whisper](https://github.com/SYSTRAN/faster-whisper)**: Efficient local speech recognition
- **[FFmpeg](https://ffmpeg.org/)**: Audio/video processing
- **[noisereduce](https://github.com/timsainb/noisereduce)**: Audio denoising
- **[openai](https://github.com/openai/openai-python)**: LLM interface (compatible with DeepSeek / OpenAI)

## License

MIT
