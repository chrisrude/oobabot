# -*- coding: utf-8 -*-
"""
Stores a transcript of a voice channel.
"""
import asyncio
import datetime
import re
import typing

import discord

from oobabot import discord_utils
from oobabot import discrivener
from oobabot import fancy_logger


class TranscriptLine:
    """
    A single line of a transcript.
    """

    def __init__(
        self, is_bot: bool, timestamp: datetime.datetime, text: str, user: discord.User
    ):
        self.is_bot: bool = is_bot
        self.timestamp: datetime.datetime = timestamp
        self.text: str = text
        self.user: discord.User = user

    def __str__(self) -> str:
        return f"{self.timestamp} {self.user.name}: {self.text}"


class Transcript:
    """
    Stores a transcript of a voice channel.
    """

    NUM_LINES = 50

    def __init__(self, client: discord.client.Client, wakewords: typing.List[str]):
        self._client = client
        self._buffer = discord_utils.RingBuffer[TranscriptLine](self.NUM_LINES)
        self._wakewords: typing.Set[str] = set(word.lower() for word in wakewords)
        self.wakeword_event = asyncio.Event()
        self.silence_event = asyncio.Event()

    def get_lines(self) -> typing.List[TranscriptLine]:
        """
        Returns the current transcript lines.
        """
        return self._buffer.get()

    def add_bot_response(self, message: str):
        """
        Adds a bot response to the transcript.
        """
        user = self._client.user
        line = TranscriptLine(
            is_bot=True,
            timestamp=datetime.datetime.now(),
            text=message,
            user=user,
        )
        self._buffer.append(line)

    def on_transcription(self, message: discrivener.Transcription) -> None:
        user = self._client.get_user(message.user_id)
        if user is None:
            fancy_logger.get().warning("transcript: unknown user %s", message.user_id)
            return

        # todo: make use of decide_to_respond instead
        wakeword_found = False
        for segment in message.segments:
            line = TranscriptLine(
                is_bot=user.bot,
                timestamp=message.timestamp
                + datetime.timedelta(milliseconds=segment.start_offset_ms),
                text=str(segment),
                user=user,
            )
            self._buffer.append(line)
            fancy_logger.get().debug("transcript: %s", str(line))

            if not wakeword_found:
                for word in re.split(r"[ .,!?\"']", line.text):
                    if word.lower() in self._wakewords:
                        wakeword_found = True
                        break

        # print message lag
        if message.timestamp:
            message_end_time = message.timestamp + message.audio_duration
            lag = datetime.datetime.now() - message_end_time
            fancy_logger.get().debug(
                "transcript: message lag: %s seconds", lag.total_seconds()
            )

        if wakeword_found:
            fancy_logger.get().info("transcript: wakeword detected!")
            self.wakeword_event.set()

    def on_channel_silent(self, activity: discrivener.ChannelSilentData) -> None:
        if activity.silent:
            self.silence_event.set()
        else:
            self.silence_event.clear()
