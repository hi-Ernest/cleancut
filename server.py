#!/usr/bin/env python3
"""
CleanCut Web Server
运行: python server.py
然后在浏览器打开 http://localhost:8765
"""
from __future__ import annotations

import asyncio
import json
import shutil
import sys
import threading
import time
import traceback
import uuid
from pathlib import Path
from queue import Empty, Queue
from typing import Any

import uvicorn
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

sys.path.insert(0, str(Path(__file__).parent))

import config as cfg
from audio import denoise, extract_audio, has_video_stream
from cache import artifact_path, load_json, save_json, save_text
from clean import clean_transcript, subtitles_to_transcript
from edit import compute_keep_ranges, compute_cut_summary, edit_audio, edit_video
from subtitle import export_srt
from transcribe import transcribe

app = FastAPI(title="CleanCut")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

tasks: dict[str, dict[str, Any]] = {}
task_queues: dict[str, Queue] = {}
UPLOADS_DIR = Path("/tmp/cleancut_uploads")
UPLOADS_DIR.mkdir(exist_ok=True)
UI_DIR = Path(__file__).parent / "ui"


def _build_annotated_words(transcript_data: dict, clean_result: dict) -> list[dict]:
    removed_starts = {round(float(w["start"]), 3) for w in clean_result.get("removed_words", [])}
    annotated: list[dict] = []
    for seg in transcript_data.get("segments", []):
        for w in seg.get("words", []):
            start = round(float(w["start"]), 3)
            annotated.append({
                "word": w["word"],
                "start": start,
                "end": round(float(w["end"]), 3),
                "status": "remove" if start in removed_starts else "keep",
            })
    return annotated


def _generate_preview(task: dict, words: list[dict]) -> str:
    """根据标注生成预览视频/音频，返回输出文件路径。"""
    workdir = Path(task["workdir"])
    kept_words = [w for w in words if w["status"] == "keep"]
    keep_ranges = compute_keep_ranges(kept_words)

    if task["is_video"]:
        output_path = str(workdir / "preview.mp4")
        Path(output_path).unlink(missing_ok=True)
        edit_video(task["input_path"], task["denoised_wav"], keep_ranges, output_path)
    else:
        output_path = str(workdir / "preview.m4a")
        Path(output_path).unlink(missing_ok=True)
        edit_audio(task["denoised_wav"], keep_ranges, output_path)
    return output_path


def _run_pipeline(task_id: str, input_path: str, q: Queue) -> None:
    task = tasks[task_id]

    def emit(step: int, total: int, msg: str) -> None:
        q.put({"type": "progress", "step": step, "total": total, "message": msg})

    try:
        workdir = cfg.get_workdir(input_path)
        is_video = has_video_stream(input_path)
        total_steps = 6

        emit(1, total_steps, "正在读取音频…")
        raw_wav = str(artifact_path(workdir, "raw_audio"))
        extract_audio(input_path, raw_wav)

        emit(2, total_steps, "正在过滤背景噪音…")
        denoised_wav = str(artifact_path(workdir, "denoised_audio"))
        if cfg.DENOISE_ENABLED:
            denoise(raw_wav, denoised_wav)
            whisper_input = denoised_wav
        else:
            denoised_wav = raw_wav
            whisper_input = raw_wav

        emit(3, total_steps, "AI 正在识别语音内容…")
        transcript_path = artifact_path(workdir, "raw_transcript")
        cached = load_json(transcript_path)
        if cached and "words" in cached:
            transcript_data = cached
        else:
            transcript_data = transcribe(whisper_input)
            save_json(transcript_path, transcript_data)

        emit(4, total_steps, "正在标记口水话与气口…")
        clean_result_path = artifact_path(workdir, "clean_result")
        cached = load_json(clean_result_path)
        if cached and "subtitles" in cached:
            clean_result = cached
        else:
            clean_result = clean_transcript(transcript_data)
            save_json(clean_result_path, clean_result)

        emit(5, total_steps, "正在生成字幕…")
        srt_out = str(artifact_path(workdir, "subtitle"))
        export_srt(clean_result["subtitles"], srt_out)

        annotated_words = _build_annotated_words(transcript_data, clean_result)

        # 写入基本信息以便步骤 6 使用
        task.update({
            "input_path": str(input_path),
            "workdir": str(workdir),
            "is_video": is_video,
            "denoised_wav": denoised_wav,
            "words": annotated_words,
            "subtitles": clean_result["subtitles"],
        })

        emit(6, total_steps, "正在合成净化视频…")
        preview_path = _generate_preview(task, annotated_words)

        removed_duration = sum(
            w["end"] - w["start"] for w in annotated_words if w["status"] == "remove"
        )
        total_duration = annotated_words[-1]["end"] if annotated_words else 0

        task.update({
            "status": "done",
            "preview_path": preview_path,
            "stats": {
                "removed_count": sum(1 for w in annotated_words if w["status"] == "remove"),
                "removed_duration": round(removed_duration, 1),
                "total_duration": round(total_duration, 1),
            },
        })
        q.put({"type": "done"})

    except Exception as exc:
        task["status"] = "error"
        task["error"] = str(exc)
        q.put({"type": "error", "message": str(exc), "detail": traceback.format_exc()})


# ── Routes ─────────────────────────────────────────────────────

@app.get("/")
async def index():
    return FileResponse(UI_DIR / "index.html")


@app.get("/app")
async def app_page():
    return FileResponse(UI_DIR / "app.html")


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    task_id = uuid.uuid4().hex[:8]
    dest = UPLOADS_DIR / task_id / file.filename
    dest.parent.mkdir(parents=True, exist_ok=True)

    with open(dest, "wb") as f:
        shutil.copyfileobj(file.file, f)

    tasks[task_id] = {
        "status": "processing",
        "filename": file.filename,
        "created_at": time.time(),
    }
    q: Queue = Queue()
    task_queues[task_id] = q

    thread = threading.Thread(
        target=_run_pipeline, args=(task_id, str(dest), q), daemon=True
    )
    thread.start()

    return {"task_id": task_id, "filename": file.filename}


@app.get("/api/progress/{task_id}")
async def progress_sse(task_id: str):
    if task_id not in tasks:
        raise HTTPException(404, "Task not found")

    q = task_queues.get(task_id)

    async def event_stream():
        while True:
            event = None
            try:
                event = q.get(timeout=0.3) if q else None
            except Empty:
                pass

            if event is None:
                yield "data: {\"type\":\"ping\"}\n\n"
                await asyncio.sleep(0.5)
                continue

            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
            if event.get("type") in ("done", "error"):
                break

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/result/{task_id}")
async def get_result(task_id: str):
    task = tasks.get(task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    if task["status"] == "error":
        raise HTTPException(500, task.get("error", "Unknown error"))
    if task["status"] != "done":
        raise HTTPException(400, f"Task not ready: {task['status']}")

    return JSONResponse({
        "task_id": task_id,
        "filename": task["filename"],
        "words": task["words"],
        "subtitles": task["subtitles"],
        "stats": task["stats"],
        "is_video": task["is_video"],
        "has_preview": bool(task.get("preview_path")),
    })


def _serve_file(file_path: Path, request: Request):
    """Range-aware file serving for video/audio."""
    if not file_path.exists():
        raise HTTPException(404, "File not found")

    file_size = file_path.stat().st_size
    suffix = file_path.suffix.lower()
    media_map = {".mp4": "video/mp4", ".mov": "video/mp4", ".m4a": "audio/mp4",
                 ".webm": "video/webm", ".wav": "audio/wav"}
    media_type = media_map.get(suffix, "application/octet-stream")

    range_header = request.headers.get("Range")
    if range_header:
        range_val = range_header.replace("bytes=", "")
        start_str, end_str = range_val.split("-")
        start = int(start_str)
        end = int(end_str) if end_str else file_size - 1
        chunk_size = end - start + 1

        def iter_file():
            with open(file_path, "rb") as f:
                f.seek(start)
                remaining = chunk_size
                while remaining > 0:
                    data = f.read(min(65536, remaining))
                    if not data:
                        break
                    remaining -= len(data)
                    yield data

        return StreamingResponse(
            iter_file(), status_code=206, media_type=media_type,
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(chunk_size),
            },
        )

    return FileResponse(file_path, media_type=media_type)


@app.get("/api/video/{task_id}")
async def serve_original(task_id: str, request: Request):
    task = tasks.get(task_id)
    if not task or task["status"] != "done":
        raise HTTPException(404)
    return _serve_file(Path(task["input_path"]), request)


@app.get("/api/preview/{task_id}")
async def serve_preview(task_id: str, request: Request):
    task = tasks.get(task_id)
    if not task or task["status"] != "done":
        raise HTTPException(404)
    preview = task.get("preview_path")
    if not preview:
        raise HTTPException(404, "Preview not generated yet")
    return _serve_file(Path(preview), request)


@app.post("/api/regenerate/{task_id}")
async def regenerate_preview(task_id: str, request: Request):
    task = tasks.get(task_id)
    if not task or task["status"] != "done":
        raise HTTPException(404, "Task not found")

    body = await request.json()
    words: list[dict] = body.get("words", task["words"])
    task["words"] = words

    preview_path = await asyncio.get_event_loop().run_in_executor(
        None, _generate_preview, task, words
    )
    task["preview_path"] = preview_path

    removed_duration = sum(w["end"] - w["start"] for w in words if w["status"] == "remove")
    task["stats"] = {
        "removed_count": sum(1 for w in words if w["status"] == "remove"),
        "removed_duration": round(removed_duration, 1),
        "total_duration": task["stats"]["total_duration"],
    }

    return JSONResponse({"ok": True, "stats": task["stats"]})


@app.post("/api/export/{task_id}")
async def export_result(task_id: str, request: Request):
    task = tasks.get(task_id)
    if not task or task["status"] != "done":
        raise HTTPException(404, "Task not found")

    body = await request.json()
    export_type: str = body.get("export_type", "video")
    stem = Path(task["filename"]).stem

    if export_type == "srt":
        subtitles = body.get("subtitles", task["subtitles"])
        workdir = Path(task["workdir"])
        srt_path = str(workdir / "export_output.srt")
        export_srt(subtitles, srt_path)
        return FileResponse(
            srt_path,
            media_type="text/plain; charset=utf-8",
            filename=f"{stem}_cleancut.srt",
        )

    preview = task.get("preview_path")
    if not preview or not Path(preview).exists():
        raise HTTPException(400, "No preview available. Regenerate first.")

    ext = Path(preview).suffix
    return FileResponse(
        preview,
        media_type="video/mp4" if ext == ".mp4" else "audio/mp4",
        filename=f"{stem}_cleancut{ext}",
    )


if __name__ == "__main__":
    print()
    print("  ╔══════════════════════════════════╗")
    print("  ║         CleanCut  启动中          ║")
    print("  ║  打开浏览器访问:                  ║")
    print("  ║  http://localhost:8765            ║")
    print("  ╚══════════════════════════════════╝")
    print()
    uvicorn.run(app, host="0.0.0.0", port=8765, log_level="warning")
