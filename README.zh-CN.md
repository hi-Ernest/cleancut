# CleanCut

[English](./README.md) | [中文](./README.zh-CN.md)

> AI 驱动的口语净化流水线 — 自动识别并剪除语气词，输出净化字幕与媒体文件

## 功能特性

- **词级别精准剪辑**：基于 Whisper 词级别时间戳，在毫秒级精度上切除语气词
- **LLM 语义理解**：使用 DeepSeek / OpenAI 兼容模型，准确区分有意义的词与填充音
- **全流程自动化**：视频/音频 → 降噪 → 转录 → 净化 → 剪辑，一条命令完成
- **结果缓存**：各阶段中间结果自动缓存，中断后可从失败处继续
- **双输出**：净化后的 SRT 字幕 + 净化后的音视频文件

## 处理流程

```
输入媒体 (mp4 / mov / m4a / wav ...)
   ↓ 提取音频 (FFmpeg)
   ↓ 音频降噪 (noisereduce)
   ↓ Whisper 转录 (词级别时间戳)
   ↓ LLM 语义净化 (标记保留/删除)
   ↓ 精确剪辑 (FFmpeg concat)
   ↓
净化字幕 (.srt) + 净化媒体 (.mp4 / .m4a)
```

## 快速开始

### 1. 安装系统依赖

需要预先安装 [FFmpeg](https://ffmpeg.org/download.html)：

```bash
# macOS
brew install ffmpeg

# Ubuntu / Debian
sudo apt install ffmpeg
```

### 2. 安装 Python 依赖

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. 配置 API Key

```bash
cp .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY
```

### 4. 运行

```bash
# 处理视频（完整流程）
python pipeline.py 访谈.mp4

# 处理音频，使用 OpenAI Whisper API 转录
python pipeline.py 录音.m4a --whisper-mode api

# 跳过降噪，只生成净化字幕（不剪辑媒体）
python pipeline.py 视频.mov --no-denoise --skip-video

# 指定输出字幕路径
python pipeline.py 视频.mp4 -o output.srt
```

## 环境变量

复制 `.env.example` 为 `.env` 并按需修改：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DEEPSEEK_API_KEY` | DeepSeek API Key（必须）| — |
| `OPENAI_API_KEY` | OpenAI API Key（Whisper API 模式）| — |
| `LLM_BASE_URL` | LLM 接口地址 | `https://api.deepseek.com` |
| `LLM_MODEL` | 净化模型名 | `deepseek-chat` |
| `WHISPER_MODE` | 转录模式：`local` / `api` | `local` |
| `WHISPER_MODEL_SIZE` | 本地 Whisper 模型大小 | `large-v3` |
| `DENOISE_ENABLED` | 是否启用降噪 | `1` |
| `CLEAN_BATCH_SIZE` | LLM 单批处理词段数 | `40` |

### 使用其他 LLM 服务

`.env` 中可切换到任意 OpenAI 兼容接口：

```bash
# 硅基流动 Qwen
LLM_BASE_URL=https://api.siliconflow.cn/v1
LLM_MODEL=Qwen/Qwen2.5-72B-Instruct
LLM_API_KEY=sk-xxx

# OpenAI GPT-4o-mini
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
LLM_API_KEY=sk-xxx
```

## 输出文件

处理完成后，工作目录 `{文件名}_workdir/` 下包含各阶段中间产物：

| 文件 | 说明 |
|------|------|
| `01_raw_audio.wav` | 从视频提取的原始音频 |
| `02_denoised_audio.wav` | 降噪后音频 |
| `03_raw_transcript.json` | Whisper 原始转录（含词级别时间戳）|
| `04_clean_result.json` | LLM 净化结果（保留/删除标记）|
| `04_clean_transcript.txt` | 净化后纯文本稿 |
| `05_keep_ranges.json` | 保留时间区间列表 |
| `06_output.srt` | 净化后字幕文件 |
| `07_edited.*` | 净化后的音频或视频 |

## 项目结构

```
cleancut/
├── pipeline.py          # 主流水线入口
├── config.py            # 全局配置（环境变量读取）
├── transcribe.py        # Whisper 转录（本地 / API）
├── clean.py             # LLM 语义净化
├── edit.py              # 音视频剪辑
├── audio.py             # 音频提取与降噪
├── subtitle.py          # SRT 字幕导出
├── cache.py             # 中间产物缓存
├── requirements.txt     # Python 依赖
└── .env.example         # 环境变量模板
```

## 依赖说明

- **[faster-whisper](https://github.com/SYSTRAN/faster-whisper)**：高效本地语音识别
- **[FFmpeg](https://ffmpeg.org/)**：音视频处理
- **[noisereduce](https://github.com/timsainb/noisereduce)**：音频降噪
- **[openai](https://github.com/openai/openai-python)**：LLM 接口（兼容 DeepSeek / OpenAI）

## License

MIT
