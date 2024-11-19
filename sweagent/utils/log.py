from __future__ import annotations

import logging
import os
import threading
from pathlib import PurePath

from rich.logging import RichHandler
from rich.text import Text

_SET_UP_LOGGERS = set()
_ADDITIONAL_HANDLERS = []

logging.TRACE = 5  # type: ignore
logging.addLevelName(logging.TRACE, "TRACE")  # type: ignore


def _interpret_level(level: int | str | None, *, default=logging.DEBUG) -> int:
    if not level:
        return default
    if isinstance(level, int):
        return level
    if level.isnumeric():
        return int(level)
    return getattr(logging, level.upper())


_STREAM_LEVEL = _interpret_level(os.environ.get("SWE_AGENT_LOG_STREAM_LEVEL"))
_FILE_LEVEL = _interpret_level(os.environ.get("SWE_AGENT_LOG_FILE_LEVEL"), default=logging.TRACE)  # type: ignore
_INCLUDE_LOGGER_NAME_IN_STREAM_HANDLER = False

_THREAD_NAME_TO_LOG_SUFFIX: dict[str, str] = {}
"""Mapping from thread name to suffix to add to the logger name."""


def register_thread_name(name: str) -> None:
    """Register a suffix to add to the logger name for the current thread."""
    thread_name = threading.current_thread().name
    _THREAD_NAME_TO_LOG_SUFFIX[thread_name] = name


class _RichHandlerWithEmoji(RichHandler):
    def __init__(self, emoji: str, *args, **kwargs):
        """Subclass of RichHandler that adds an emoji to the log message."""
        super().__init__(*args, **kwargs)
        if not emoji.endswith(" "):
            emoji += " "
        self.emoji = emoji

    def get_level_text(self, record: logging.LogRecord) -> Text:
        level_name = record.levelname
        return Text.styled((self.emoji + level_name).ljust(10), f"logging.level.{level_name.lower()}")


def get_logger(name: str, *, emoji: str = "") -> logging.Logger:
    """Get logger. Use this instead of `logging.getLogger` to ensure
    that the logger is set up with the correct handlers.
    """
    thread_name = threading.current_thread().name
    if thread_name != "MainThread":
        name = name + "-" + _THREAD_NAME_TO_LOG_SUFFIX.get(thread_name, thread_name)
    logger = logging.getLogger(name)
    if logger.hasHandlers():
        # Already set up
        return logger
    handler = _RichHandlerWithEmoji(
        emoji=emoji,
        show_time=bool(os.environ.get("SWE_AGENT_LOG_TIME", False)),
        show_path=False,
    )
    handler.setLevel(_STREAM_LEVEL)
    logger.setLevel(min(_STREAM_LEVEL, _FILE_LEVEL))
    logger.addHandler(handler)
    logger.propagate = False
    _SET_UP_LOGGERS.add(name)
    for handler in _ADDITIONAL_HANDLERS:
        if getattr(handler, "my_filter", "") in name:
            logger.addHandler(handler)
    if _INCLUDE_LOGGER_NAME_IN_STREAM_HANDLER:
        _add_logger_name_to_stream_handler(logger)
    return logger


def add_file_handler(path: PurePath | str, *, filter: str = "", level: int | str = _FILE_LEVEL) -> None:
    """Adds a file handler to all loggers that we have set up
    and all future loggers that will be set up with `get_logger`.

    Args:
        filter: If provided, only add the handler to loggers that contain the filter string.
    """
    handler = logging.FileHandler(path)
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s")
    handler.setFormatter(formatter)
    handler.setLevel(_interpret_level(level))
    for name in _SET_UP_LOGGERS:
        if filter and filter not in name:
            continue
        logger = logging.getLogger(name)
        logger.addHandler(handler)
    handler.my_filter = filter  # type: ignore
    _ADDITIONAL_HANDLERS.append(handler)


def _add_logger_name_to_stream_handler(logger: logging.Logger) -> None:
    for handler in logger.handlers:
        if isinstance(handler, _RichHandlerWithEmoji):
            formatter = logging.Formatter("[%(name)s] %(message)s")
            handler.setFormatter(formatter)


def add_logger_names_to_stream_handlers() -> None:
    """Add the logger name to the stream handler for all loggers that we have set up."""
    global _INCLUDE_LOGGER_NAME_IN_STREAM_HANDLER
    _INCLUDE_LOGGER_NAME_IN_STREAM_HANDLER = True
    for logger in _SET_UP_LOGGERS:
        _add_logger_name_to_stream_handler(logging.getLogger(logger))


default_logger = get_logger("swe-agent")


def set_default_stream_level(level: int) -> None:
    """Set the default stream level. Note: Can only be used to lower the level, not raise it."""
    global _STREAM_LEVEL
    _STREAM_LEVEL = level
