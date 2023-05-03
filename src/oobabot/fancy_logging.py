
import logging

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


def apply_color(color, text='%(message)s'):
    return f"\033[{FOREGROUND_COLORS[color]}m{text}\033[0m"


PREFIX = f'{apply_color("yellow", "%(asctime)s")} %(levelname)s '

FORMATS = {
    logging.DEBUG: PREFIX + apply_color('cyan'),
    logging.INFO: PREFIX + apply_color('white'),
    logging.WARNING: PREFIX + apply_color('yellow'),
    logging.ERROR: PREFIX + apply_color('red'),
    logging.CRITICAL: PREFIX + apply_color('red'),
}


class ColorfulLoggingFormatter(logging.Formatter):
    def format(self, record):
        log_fmt = FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt)
        return formatter.format(record)


def get_logger(name: str = "oobabot") -> logging.Logger:
    return logging.getLogger(name)


def init_logging() -> logging.Logger:
    logger = get_logger()
    logger.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(ColorfulLoggingFormatter())
    logger.addHandler(console_handler)

    return logger
