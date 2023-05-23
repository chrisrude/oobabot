# -*- coding: utf-8 -*-
"""
Logging with colors
"""

import html
import logging
import textwrap
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

HTML_HEADER = textwrap.dedent(
    """
    <!DOCTYPE html>
    <html lang="en">
    <head>
    <meta charset="utf-8">
    <title>oobabot logs</title>
    <style>
    body {
        background-color: #0C0C0C;
        color: #CCCCCC;
        font-family: Consolas, Lucida Console, monospace;
    }
    .oobabot-red {
        color: #C50F1F;
    }
    .oobabot-yellow {
        color: #C19C00;
    }
    .oobabot-cyan {
        color: #3A96DD;
    }
    .oobabot-white {
        color: #CCCCCC;
    }
    </style>
    </head>
    <body><div class="oobabot-log">
    """
)
HTML_RECORD_SEPARATOR = "\n<br>"
HTML_FOOTER = "</div></body></html>"


def apply_color_console(color: str, text: str) -> str:
    return f"\033[{FOREGROUND_COLORS[color]}m{text}\033[0m"


def apply_color_html(color: str, text: str) -> str:
    return f"<span class='oobabot-{color}'>{text}</span>"


def make_coloring_book(
    fn_apply_color: typing.Callable[[str, str], str]
) -> typing.Dict[int, str]:
    prefix = f'{fn_apply_color("yellow", "%(asctime)s")} %(levelname)s '
    msg = "%(message)s"
    return {
        logging.DEBUG: prefix + fn_apply_color("cyan", msg),
        logging.INFO: prefix + fn_apply_color("white", msg),
        logging.WARNING: prefix + fn_apply_color("yellow", msg),
        logging.ERROR: prefix + fn_apply_color("red", msg),
        logging.CRITICAL: prefix + fn_apply_color("red", msg),
    }


class ColorfulLoggingFormatter(logging.Formatter):
    """
    Logging formatter that adds colors to the log levels.
    """

    def __init__(
        self,
        coloring_book: typing.Dict[int, str],
        fn_format_message: typing.Optional[
            typing.Callable[[typing.Optional[typing.Any]], typing.Optional[typing.Any]]
        ] = None,
    ) -> None:
        super().__init__()
        self.formatters = {}
        for logging_level, fmt_color in coloring_book.items():
            self.formatters[logging_level] = logging.Formatter(fmt_color)
        self.fn_format_message = fn_format_message

    def format(self, record: logging.LogRecord) -> str:
        if self.fn_format_message:
            record = logging.makeLogRecord(record.__dict__)
            record.msg = self.fn_format_message(record.msg)
            # record.args is a tuple.  Call self.fn_format_message for each
            # element of the tuple, and then reassemble the tuple.
            if record.args:
                record.args = tuple(self.fn_format_message(arg) for arg in record.args)

        formatter = self.formatters.get(record.levelno)
        if formatter:
            result = formatter.format(record)

            # From the Python docs for logging.Formatter():
            # ...you should be careful if you have more than one Formatter
            # subclass which customizes the formatting of exception information.
            # In this case, you will have to clear the cached value (by setting
            # the exc_text attribute to None) after a formatter has done its
            # formatting, so that the next formatter to handle the event doesn’t
            # use the cached value, but recalculates it afresh.
            record.exc_text = None
            return result
        return record.getMessage()


def get(name: str = "oobabot") -> logging.Logger:
    return logging.getLogger(name)


def do_escape(msg: typing.Optional[typing.Any]) -> typing.Optional[typing.Any]:
    if msg is None:
        return None
    if not isinstance(msg, str):
        return msg
    result = html.escape(msg)
    return result


def init_logging(
    level: typing.Union[int, str],
    log_to_console: bool = True,
) -> None:
    logger = get()
    logger.setLevel(level)

    if log_to_console:
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(
            ColorfulLoggingFormatter(
                coloring_book=make_coloring_book(apply_color_console),
            )
        )
        logger.addHandler(console_handler)

    recent_logs.setLevel(level)
    recent_logs.setFormatter(
        ColorfulLoggingFormatter(
            coloring_book=make_coloring_book(apply_color_html),
            fn_format_message=do_escape,
        )
    )
    logger.addHandler(recent_logs)


# the following class was modified from O'Reilly's Python Cookbook,
# chapter 5, section 19.  Its use is allowed under this license:
# Copyright (c) 2001, Sébastien Keim
# All rights reserved.
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#    * Redistributions of source code must retain the above copyright
#      notice, this list of conditions and the following disclaimer.
#    * Redistributions in binary form must reproduce the above
#      copyright notice, this list of conditions and the following
#      disclaimer in the documentation and/or other materials provided
#      with the distribution.
#    * Neither the name of the <ORGANIZATION> nor the names of its
#      contributors may be used to endorse or promote products derived
#      from this software without specific prior written permission.
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE REGENTS
# OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
# EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
# PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS;
# OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
# WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR
# OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF
# ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
class RingBuffer:
    """
    A generic ring buffer.
    """

    def __init__(self, size_max: int):
        self.cur = 0
        self.max = size_max
        self.data: typing.List[str] = []

    class _FullRingBuffer:
        """
        Class implementing the RingBuffer when it's full.
        With python class magic, this class is swapped in when the
        buffer becomes full.
        """

        cur: int
        max: int
        data: typing.List[str]

        def append(self, val: str) -> None:
            """
            Append an element overwriting the oldest one.
            """
            self.data[self.cur] = val
            self.cur = (self.cur + 1) % self.max

        def get(self) -> typing.List[str]:
            """
            Return a list of elements from the oldest to the newest.
            """
            return self.data[self.cur :] + self.data[: self.cur]

        def size(self) -> int:
            """
            Return the size of the buffer.
            """
            return self.max

    def append(self, val: str) -> None:
        """
        Append an element at the end of the buffer.
        """
        self.data.append(val)
        if len(self.data) == self.max:
            self.cur = 0
            # Permanently change self's class from non-full to full
            self.__class__ = self._FullRingBuffer

    def get(self) -> typing.List[str]:
        """
        Return a list of elements from the oldest to the newest.
        """
        return self.data

    def size(self) -> int:
        """
        Return the number of elements currently in the buffer.
        """
        return len(self.data)


# end of O'Reilly code


class RingBufferedHandler(logging.Handler):
    """
    A singleton logging handler that stores the last N log messages in a ring buffer.
    """

    def __init__(self, buffer_size: int = 45) -> None:
        super().__init__()
        self.buffer = RingBuffer(buffer_size)

    def emit(self, record: logging.LogRecord) -> None:
        self.buffer.append(self.format(record))

    def get_all(self) -> typing.List[str]:
        return self.buffer.get()


recent_logs = RingBufferedHandler()
