#!/usr/bin/env python3
"""
纪录片字幕一键清洗流程 / Documentary Subtitle Cleaner Pipeline
录音(MP3/WAV/M4A) → Whisper转录 → Claude净化语序 → 输出SRT

安装依赖 / Install:
    pip install openai anthropic

运行 / Run:
    python subtitle_pipeline.py 录音.m4a
    python subtitle_pipeline.py 录音.m4a --output 字幕.srt
"""

import os
import sys
import json
import re
import argparse
from pathlib import Path

# ──────────────────────────────────────────
# 🔑 填入你的 API Keys / Fill in your API keys
# ──────────────────────────────────────────
OPENAI_API_KEY    = "sk-..."        # https://platform.openai.com/api-keys
ANTHROPIC_API_KEY = "sk-ant-..."   # https://console.anthropic.com/


def transcribe(audio_path: str) -> list[dict]:
    """Whisper API 转录，返回带时间戳片段 / Transcribe with timestamps"""
    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)

    print(f"[1/3] 🎙️  转录中 / Transcribing: {audio_path}")
    with open(audio_path, "rb") as f:
        resp = client.audio.transcriptions.create(
            model="whisper-1",
            file=f,
            response_format="verbose_json",
            language="zh"   # 改为 "en" 处理英文 / change to "en" for English
        )

    segments = [
        {"id": s.id, "start": s.start, "end": s.end, "text": s.text.strip()}
        for s in resp.segments
    ]
    print(f"       → {len(segments)} 个原始片段 / raw segments")
    return segments


def clean(segments: list[dict]) -> list[dict]:
    """Claude 净化：删口水话 + 修语序 + 合并碎句 / Clean with Claude"""
    import anthropic
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    print("[2/3] 🤖  Claude 净化中 / Cleaning with Claude ...")
    prompt = f"""你是专业纪录片字幕编辑。对下列带时间戳的语音转录片段（JSON格式）进行处理：

处理规则：
1. 删除所有口水话和语气词：嗯、啊、那个、就是（单用）、然后（连词）、对吧、你知道、怎么说、呃、这个、那 等
2. 修正倒装、混乱语序为自然书面表达，保留核心语义
3. 合并相邻碎片化句子（同一语义），时间取第一个start和最后一个end
4. 删去仅含语气词的空片段
5. 每条字幕15~25字，过长则拆分（时间平均分配）

返回格式：严格JSON数组，每项含 id、start、end、text 字段。
不要输出任何解释，只返回JSON。

输入：
{json.dumps(segments, ensure_ascii=False, indent=2)}"""

    msg = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = msg.content[0].text.strip()

    # 提取 JSON 数组（防 markdown 包裹）
    m = re.search(r'\[.*\]', raw, re.DOTALL)
    cleaned = json.loads(m.group(0) if m else raw)
    print(f"       → {len(cleaned)} 条净化字幕 / cleaned subtitles")
    return cleaned


def to_srt_time(sec: float) -> str:
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    ms = int((s - int(s)) * 1000)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{ms:03d}"


def export_srt(segments: list[dict], out: str):
    """导出 SRT 文件 / Export SRT file"""
    print(f"[3/3] 💾  导出 / Exporting: {out}")
    lines = []
    idx = 1
    for seg in segments:
        text = seg.get("text", "").strip()
        if not text:
            continue
        lines += [
            str(idx),
            f"{to_srt_time(float(seg['start']))} --> {to_srt_time(float(seg['end']))}",
            text,
            ""
        ]
        idx += 1
    Path(out).write_text("\n".join(lines), encoding="utf-8")
    print(f"\n✅ 完成！/ Done!  →  {out}")
    print(f"   共 {idx-1} 条字幕 / {idx-1} subtitles total")


def main():
    ap = argparse.ArgumentParser(description="Documentary subtitle cleaner")
    ap.add_argument("audio", help="音频文件 / Audio file (mp3/wav/m4a)")
    ap.add_argument("--output", "-o", default=None, help="输出SRT路径 / Output .srt path")
    args = ap.parse_args()

    if not os.path.exists(args.audio):
        print(f"❌ 文件不存在 / File not found: {args.audio}")
        sys.exit(1)

    out = args.output or str(Path(args.audio).with_suffix(".srt"))
    segs = transcribe(args.audio)
    cleaned = clean(segs)
    export_srt(cleaned, out)


if __name__ == "__main__":
    main()


# ──────────────────────────────────────────────────────────────
# 🔧 没有 OpenAI Key？用本地 Whisper 替代 / No OpenAI key? Use local Whisper:
#
#   pip install openai-whisper
#
#   把 transcribe() 函数替换为 / Replace transcribe() with:
#
#   def transcribe(audio_path):
#       import whisper
#       model = whisper.load_model("large-v3")   # 或 "medium" 更快 / or "medium" for speed
#       result = model.transcribe(audio_path, language="zh")
#       return [{"id": i, "start": s["start"], "end": s["end"], "text": s["text"]}
#               for i, s in enumerate(result["segments"])]
# ──────────────────────────────────────────────────────────────
