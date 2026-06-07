import logging
import logging.handlers
import threading
from pathlib import Path

from core.config import settings

# ── Log directory ────────────────────────────────────────────────────────
LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "app.log"

# ── Sensitive keys to mask automatically ────────────────────────────────
_MASKED_KEYS = {"password", "password_hash", "token", "access_token", "secret_key", "gemini_api_key"}

# ── Custom formatter with thread ID ──────────────────────────────────────
class ThreadFormatter(logging.Formatter):
    FMT = "[%(asctime)s] [%(levelname)-5s] [Thd:%(thread)d] [%(name)-30s] %(message)s"
    DATE_FMT = "%Y-%m-%d %H:%M:%S"

    def __init__(self):
        super().__init__(fmt=self.FMT, datefmt=self.DATE_FMT)


# ── Root configuration (called once at startup) ──────────────────────────
def configure_logging():
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    # Rolling file: 5 MB per file, keep 5 backups
    file_handler = logging.handlers.RotatingFileHandler(
        LOG_FILE,
        maxBytes=5 * 1024 * 1024,  # 5 MB
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(ThreadFormatter())

    logging.basicConfig(
        level=level,
        handlers=[file_handler],
    )

    # Quiet noisy third-party loggers
    for noisy in (
        "uvicorn.access",
        "uvicorn.error",
        "sqlalchemy.engine",
        "httpx",
        "multipart",          # python-multipart: chunks file uploads at DEBUG — very spammy
        "multipart.multipart",
        "python_multipart",
    ):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    logging.getLogger("uvicorn").setLevel(logging.INFO)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger. Call as: logger = get_logger(__name__)"""
    return logging.getLogger(name)


# ── PII / Sensitive data helpers ──────────────────────────────────────────
def sanitize(data: dict) -> dict:
    """
    Return a copy of data with sensitive keys masked.
    Handles nested dicts recursively.
    """
    if not isinstance(data, dict):
        return data
    out = {}
    for k, v in data.items():
        if k.lower() in _MASKED_KEYS:
            out[k] = "***"
        elif isinstance(v, dict):
            out[k] = sanitize(v)
        else:
            out[k] = v
    return out


def mask_token(token: str | None, visible: int = 12) -> str:
    """Show only the first N chars of a JWT/token."""
    if not token:
        return "<none>"
    return f"{token[:visible]}... [truncated]"


def fmt_image(raw_bytes: bytes | None, detected_format: str = "jpeg") -> str:
    """Return a human-readable image descriptor — never logs binary data."""
    if raw_bytes is None:
        return "<no image>"
    size_kb = len(raw_bytes) / 1024
    if size_kb >= 1024:
        return f"<format:{detected_format} size:{size_kb/1024:.2f}MB>"
    return f"<format:{detected_format} size:{size_kb:.1f}KB>"
