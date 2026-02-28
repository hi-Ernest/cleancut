"""
全局配置 — 通过环境变量或 .env 文件覆盖默认值
"""

import os
from pathlib import Path


def _load_dotenv():
    """简易 .env 加载，不引入额外依赖。必须在读取变量之前调用。"""
    env_file = Path(__file__).parent / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_dotenv()

# ── API Keys ──────────────────────────────────────────────
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# ── LLM 净化模型 ─────────────────────────────────────────
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
LLM_MODEL = os.getenv("LLM_MODEL", "deepseek-chat")
LLM_API_KEY = os.getenv("LLM_API_KEY", "") or DEEPSEEK_API_KEY

# ── Whisper 转录 ─────────────────────────────────────────
WHISPER_MODE = os.getenv("WHISPER_MODE", "local")
WHISPER_MODEL_SIZE = os.getenv("WHISPER_MODEL_SIZE", "large-v3")
WHISPER_LANGUAGE = os.getenv("WHISPER_LANGUAGE", "zh")

# ── 降噪 ─────────────────────────────────────────────────
DENOISE_ENABLED = os.getenv("DENOISE_ENABLED", "1") == "1"

# ── 净化参数 ─────────────────────────────────────────────
CLEAN_BATCH_SIZE = int(os.getenv("CLEAN_BATCH_SIZE", "40"))
CLEAN_OVERLAP = int(os.getenv("CLEAN_OVERLAP", "5"))
CLEAN_MAX_TOKENS = int(os.getenv("CLEAN_MAX_TOKENS", "4096"))

# ── 字幕参数 ─────────────────────────────────────────────
SUBTITLE_MIN_CHARS = int(os.getenv("SUBTITLE_MIN_CHARS", "8"))
SUBTITLE_MAX_CHARS = int(os.getenv("SUBTITLE_MAX_CHARS", "25"))

# ── 工作目录 ─────────────────────────────────────────────
DEFAULT_WORKDIR = os.getenv("OPTMPX_WORKDIR", "")


def get_workdir(input_path: str) -> Path:
    """根据输入文件创建同名工作目录"""
    if DEFAULT_WORKDIR:
        d = Path(DEFAULT_WORKDIR)
    else:
        p = Path(input_path)
        d = p.parent / f"{p.stem}_workdir"
    d.mkdir(parents=True, exist_ok=True)
    return d
