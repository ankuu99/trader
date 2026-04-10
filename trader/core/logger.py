import logging
import logging.handlers
from pathlib import Path


def get_logger(name: str) -> logging.Logger:
    """
    Return a logger for the given module name.

    Usage:
        from trader.core.logger import get_logger
        logger = get_logger(__name__)
    """
    return logging.getLogger(name)


def setup(log_dir: Path, level: str = "INFO") -> None:
    """
    Configure root logging. Call once at startup from main.py.

    Creates rotating log files:
        logs/system.log   — everything
        logs/orders.log   — trader.orders.*
        logs/strategy.log — trader.strategies.*
        logs/data.log     — trader.data.*
    """
    log_dir.mkdir(parents=True, exist_ok=True)

    numeric_level = getattr(logging, level.upper(), logging.INFO)
    fmt = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    def rotating(filename: str) -> logging.Handler:
        handler = logging.handlers.RotatingFileHandler(
            log_dir / filename,
            maxBytes=5 * 1024 * 1024,  # 5 MB
            backupCount=7,
            encoding="utf-8",
        )
        handler.setFormatter(fmt)
        return handler

    # Console handler
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    console.setLevel(numeric_level)

    # Root logger — catches everything
    root = logging.getLogger()
    root.setLevel(numeric_level)
    root.addHandler(console)
    root.addHandler(rotating("system.log"))

    # Component-specific file loggers
    _add_file_logger("trader.orders", rotating("orders.log"), numeric_level)
    _add_file_logger("trader.strategies", rotating("strategy.log"), numeric_level)
    _add_file_logger("trader.data", rotating("data.log"), numeric_level)


def _add_file_logger(
    logger_name: str, handler: logging.Handler, level: int
) -> None:
    logger = logging.getLogger(logger_name)
    logger.addHandler(handler)
    logger.setLevel(level)
    # Don't double-print to root — root already has system.log + console
    logger.propagate = True
