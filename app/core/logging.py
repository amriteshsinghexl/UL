import logging
import sys
from pathlib import Path
from app.core.config import settings


def setup_logging() -> None:
    log_dir = Path(settings.base_dir) / settings.log_dir
    log_dir.mkdir(parents=True, exist_ok=True)

    level = getattr(logging, settings.log_level.upper(), logging.INFO)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # Console handler — INFO and above
    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(level)
    sh.setFormatter(fmt)
    root.addHandler(sh)

    # File handler — DEBUG and above
    fh = logging.FileHandler(log_dir / "app.log", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    # Quiet noisy third-party loggers
    for noisy in ("uvicorn.access", "multipart"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
