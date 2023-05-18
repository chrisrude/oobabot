# -*- coding: utf-8 -*-
import logging
import typing

FOREGROUND_COLORS = {
    "black": 30,
    "red": 31,
    "green": 32,
    "yellow": 33,
    "blue": 34,
    "magenta": 35,
    "cyan": 36,
    "white": 37,
}


def apply_color(color, text: str = "%(message)s") -> str:
    return f"\033[{FOREGROUND_COLORS[color]}m{text}\033[0m"


PREFIX = f'{apply_color("yellow", "%(asctime)s")} %(levelname)s '

FORMATS = {
    logging.DEBUG: PREFIX + apply_color("cyan"),
    logging.INFO: PREFIX + apply_color("white"),
    logging.WARNING: PREFIX + apply_color("yellow"),
    logging.ERROR: PREFIX + apply_color("red"),
    logging.CRITICAL: PREFIX + apply_color("red"),
}


class ColorfulLoggingFormatter(logging.Formatter):
    def __init__(self) -> None:
        super().__init__()
        self.formatters = {}
        for logging_level in FORMATS:
            self.formatters[logging_level] = logging.Formatter(
                FORMATS.get(logging_level)
            )

    def format(self, record: logging.LogRecord) -> str:
        formatter = self.formatters.get(record.levelno)
        if formatter:
            return formatter.format(record)
        return record.getMessage()


def get(name: str = "oobabot") -> logging.Logger:
    return logging.getLogger(name)


def init_logging(level: typing.Union[int, str]) -> logging.Logger:
    logger = get()
    if not level:
        level = logging.DEBUG
    logger.setLevel(level)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_handler.setFormatter(ColorfulLoggingFormatter())
    logger.addHandler(console_handler)

    return logger
