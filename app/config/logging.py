from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path


def setup_logging(log_dir: str | Path | None = None) -> None:
    """配置全局日志：stdout + 轮转文件。"""
    root = logging.getLogger()
    if root.handlers:
        return  # 避免重复配置

    root.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)-7s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root.addHandler(handler)

    if log_dir:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_path / "app.log",
            maxBytes=10 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    # 降低噪音三方库的级别
    logging.getLogger("langgraph").setLevel(logging.WARNING)
    logging.getLogger("faiss").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
