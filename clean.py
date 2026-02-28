"""
LLM 语义净化 — 基于词级别时间戳的口语净化
输入带词时间戳的 segments，LLM 标记每个词保留/删除，
同时输出整理后的字幕文本。
"""

from __future__ import annotations

import json
import re

from openai import OpenAI

import config as cfg

SYSTEM_PROMPT = """你是专业纪录片字幕编辑。你将收到语音转录的片段，每个片段包含词级别时间戳。
你的任务是：标记哪些词需要删除（语气词/口水话），并输出净化后的字幕文本。

删除的词的时间段将从音视频中被剪掉，所以标记必须准确。

需要删除的词类型：
- 语气词/口水话：嗯、啊、呃、哦、那个、这个、就是（单用）、然后（连词滥用）、对吧、你知道、怎么说、对对对、是吧 等
- 重复/卡顿：说话人重复的词或未完成的断句
- 无意义的填充音

保留规则：
- 保留所有有实际意义的词
- "那个"如果指代具体事物则保留，作为口水话则删除
- "就是"如果是"A就是B"的判断句则保留，单独填充则删除
- "然后"如果表达时间顺序则保留，作为口水话连词则删除

输出格式：JSON 数组，每项对应一个输入片段：
[
  {
    "id": 0,
    "text": "净化后的字幕文本（书面表达，加标点）",
    "keep": [0, 1, 3, 5],
    "remove": [2, 4]
  }
]

字段说明：
- id: 原始片段 id
- text: 净化后的书面表达（修正语序、加标点，15~25字，过长可拆为多条用\\n分隔）
- keep: 保留的词索引列表（对应该片段 words 数组的下标）
- remove: 删除的词索引列表

keep + remove 必须覆盖该片段所有词的索引。只返回 JSON，不要输出任何解释。"""


def _get_client() -> OpenAI:
    if not cfg.LLM_API_KEY:
        raise ValueError(
            "LLM_API_KEY 未设置。请设置环境变量 LLM_API_KEY 或 DEEPSEEK_API_KEY"
        )
    return OpenAI(api_key=cfg.LLM_API_KEY, base_url=cfg.LLM_BASE_URL)


def _prepare_input(segments: list[dict]) -> list[dict]:
    """将带 words 的 segments 转为 LLM 输入格式（紧凑）"""
    result = []
    for seg in segments:
        words = seg.get("words", [])
        if not words:
            continue
        word_list = []
        for i, w in enumerate(words):
            word_list.append({
                "i": i,
                "w": w["word"],
                "s": w["start"],
                "e": w["end"],
            })
        result.append({
            "id": seg["id"],
            "text": seg["text"],
            "words": word_list,
        })
    return result


def _clean_batch(client: OpenAI, segments: list[dict]) -> list[dict]:
    """单批次净化"""
    llm_input = _prepare_input(segments)
    user_msg = json.dumps(llm_input, ensure_ascii=False)

    resp = client.chat.completions.create(
        model=cfg.LLM_MODEL,
        max_tokens=cfg.CLEAN_MAX_TOKENS,
        temperature=0.3,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
    )
    raw = resp.choices[0].message.content.strip()

    m = re.search(r"\[.*\]", raw, re.DOTALL)
    if not m:
        raise ValueError(f"LLM 返回无法解析为 JSON 数组:\n{raw[:500]}")
    return json.loads(m.group(0))


def clean_transcript(transcript_data: dict) -> dict:
    """
    基于词级别时间戳净化转录。

    输入: transcribe() 的返回值 {"segments": [...], "words": [...]}
    输出: {
        "subtitles":   [...],  # 字幕段（含 text/start/end）
        "kept_words":  [...],  # 保留的词（含时间戳，用于剪辑）
        "removed_words": [...] # 删除的词（用于统计）
    }
    """
    segments = transcript_data["segments"]
    client = _get_client()
    batch_size = cfg.CLEAN_BATCH_SIZE
    total = len(segments)

    # 分批处理
    all_results: list[dict] = []
    start = 0
    batch_idx = 0

    while start < total:
        end = min(start + batch_size, total)
        batch = segments[start:end]
        batch_idx += 1

        if total <= batch_size:
            print(f"  [净化] 单批处理 {total} 个片段 ({cfg.LLM_MODEL}) ...")
        else:
            print(f"  [净化] 批次 {batch_idx}: 片段 {start}~{end-1} "
                  f"({len(batch)} 个, {cfg.LLM_MODEL}) ...")

        cleaned = _clean_batch(client, batch)
        all_results.extend(cleaned)
        start = end

    # 根据 LLM 返回的 keep/remove 信息，提取保留/删除的词
    seg_map = {seg["id"]: seg for seg in segments}
    kept_words: list[dict] = []
    removed_words: list[dict] = []
    subtitles: list[dict] = []
    sub_id = 0

    for result in all_results:
        seg_id = result["id"]
        seg = seg_map.get(seg_id)
        if not seg or not seg.get("words"):
            continue

        words = seg["words"]
        keep_indices = set(result.get("keep", []))
        remove_indices = set(result.get("remove", []))

        # 如果 LLM 没标全，未标记的词默认保留
        all_indices = set(range(len(words)))
        if not keep_indices and not remove_indices:
            keep_indices = all_indices
        elif keep_indices and not remove_indices:
            remove_indices = all_indices - keep_indices
        elif remove_indices and not keep_indices:
            keep_indices = all_indices - remove_indices

        for i, w in enumerate(words):
            if i in remove_indices:
                removed_words.append(w)
            else:
                kept_words.append(w)

        # 处理字幕文本（支持 \n 拆分为多条）
        text = result.get("text", "").strip()
        if not text:
            continue

        seg_kept = [words[i] for i in sorted(keep_indices) if i < len(words)]
        if not seg_kept:
            continue

        text_lines = text.split("\n")
        if len(text_lines) == 1:
            subtitles.append({
                "id": sub_id,
                "start": seg_kept[0]["start"],
                "end": seg_kept[-1]["end"],
                "text": text_lines[0].strip(),
            })
            sub_id += 1
        else:
            total_chars = sum(len(line.strip()) for line in text_lines)
            seg_start = seg_kept[0]["start"]
            seg_end = seg_kept[-1]["end"]
            seg_duration = seg_end - seg_start

            cursor = seg_start
            for line in text_lines:
                line = line.strip()
                if not line:
                    continue
                ratio = len(line) / max(total_chars, 1)
                line_duration = seg_duration * ratio
                subtitles.append({
                    "id": sub_id,
                    "start": round(cursor, 3),
                    "end": round(cursor + line_duration, 3),
                    "text": line,
                })
                sub_id += 1
                cursor += line_duration

    print(f"       → {len(subtitles)} 条字幕, "
          f"保留 {len(kept_words)} 词, 删除 {len(removed_words)} 词")

    return {
        "subtitles": subtitles,
        "kept_words": kept_words,
        "removed_words": removed_words,
    }


def subtitles_to_transcript(subtitles: list[dict]) -> str:
    """将字幕段转为纯文本净化稿（按段落组织）"""
    paragraphs: list[str] = []
    current: list[str] = []
    last_end = 0.0

    for sub in subtitles:
        start = float(sub["start"])
        if current and (start - last_end) > 3.0:
            paragraphs.append("".join(current))
            current = []
        current.append(sub["text"])
        last_end = float(sub["end"])

    if current:
        paragraphs.append("".join(current))

    return "\n\n".join(paragraphs)
