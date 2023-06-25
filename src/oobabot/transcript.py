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
        self,
        is_bot: bool,
        timestamp: datetime.datetime,
        original_message: typing.Optional[discrivener.Transcription],
        text: str,
        user: typing.Optional[discord.user.BaseUser],
    ):
        self.is_bot: bool = is_bot
        # only for non-bot messages
        self.original_message = original_message
        self.timestamp: datetime.datetime = timestamp
        self.text: str = text
        # only for non-bot messages
        self.user: typing.Optional[discord.user.BaseUser] = user

    def __str__(self) -> str:
        if self.is_bot:
            # todo: use persona name
            return f"{self.timestamp} bot response: {self.text}"
        if self.user is None:
            return f"{self.timestamp} unknown user: {self.text}"
        return f"{self.timestamp} {self.user.display_name}: {self.text}"


class Transcript:
    """
    Stores a transcript of a voice channel.
    """

    NUM_LINES = 300

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
        line = TranscriptLine(
            is_bot=True,
            original_message=None,
            timestamp=datetime.datetime.now(),
            text=message,
            user=self._client.user,
        )
        self._buffer.append(line)

    def on_transcription(
        self,
        message: discrivener.Transcription,
        receive_time: datetime.datetime = datetime.datetime.now(),
    ) -> None:
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
                original_message=message,
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
            lag = receive_time - message_end_time
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
