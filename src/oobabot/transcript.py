# -*- coding: utf-8 -*-
"""
Stores a transcript of a voice channel.
"""
import asyncio
import re
import time
import typing

import discord

from oobabot import discord_utils
from oobabot import discrivener
from oobabot import fancy_logger


class TranscriptLine:
    """
    A single line of a transcript.
    """

    def __init__(self, is_bot: bool, timestamp: float, text: str, user: discord.User):
        self.is_bot = is_bot
        self.timestamp = timestamp
        self.text = text
        self.user = user

    def __str__(self) -> str:
        return f"{self.timestamp:.1f} {self.user.name}: {self.text}"


class Transcript:
    """
    Stores a transcript of a voice channel.
    """

    NUM_LINES = 50

    def __init__(self, client: discord.client.Client, wakewords: typing.List[str]):
        self._client = client
        self._buffer = discord_utils.RingBuffer[TranscriptLine](self.NUM_LINES)
        self._speaking_user_ids = set()
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
            timestamp=time.time(),
            text=message,
            user=user,
        )
        self._buffer.append(line)

    def on_transcribed_message(self, message: discrivener.TranscribedMessage) -> None:
        if not message.segments:
            # we sometimes get empty messages.  Suppress these
            # on the discrivener side?
            return

        user = self._client.get_user(message.user_id)
        if user is None:
            fancy_logger.get().warning("transcript: unknown user %s", message.user_id)
            return

        # todo: make use of decide_to_respond instead
        wakeword_found = False
        for segment in message.segments:
            line = TranscriptLine(
                is_bot=user.bot,
                timestamp=message.timestamp + (segment.start_offset_ms / 1000.0),
                text=segment.text,
                user=user,
            )
            self._buffer.append(line)
            fancy_logger.get().debug("transcript: %s", str(line))

            if not wakeword_found:
                for word in re.split(r"[ .,!?\"']", segment.text):
                    if word.lower() in self._wakewords:
                        wakeword_found = True
                        break

        if wakeword_found:
            fancy_logger.get().info("transcript: wakeword detected!")
            self.wakeword_event.set()

    def on_voice_activity(self, activity: discrivener.VoiceActivityData) -> None:
        if activity.user_id is None:
            fancy_logger.get().warning("transcript: on_voice_activity, missing user_id")
            return

        if activity.speaking:
            self._speaking_user_ids.add(activity.user_id)
        else:
            self._speaking_user_ids.discard(activity.user_id)

        if not self._speaking_user_ids:
            self.silence_event.set()
        else:
            self.silence_event.clear()
