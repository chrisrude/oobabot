# -*- coding: utf-8 -*-
"""
Stores a transcript of a voice channel.
"""
import discord

from oobabot import discord_utils
from oobabot import discrivener
from oobabot import fancy_logger


class TranscriptLine:
    """
    A single line of a transcript.
    """

    timestamp: float
    text: str
    user: discord.User

    def __str__(self) -> str:
        return f"{self.timestamp:.1f} {self.user.name}: {self.text}"


class Transcript:
    """
    Stores a transcript of a voice channel.
    """

    _client: discord.client.Client
    _buffer: discord_utils.RingBuffer[TranscriptLine]

    def __init__(self, client: discord.client.Client):
        self._client = client
        self._buffer = discord_utils.RingBuffer[TranscriptLine](100)

    def on_transcribed_message(self, message: discrivener.TranscribedMessage) -> None:
        if not message.segments:
            # we sometimes get empty messages.  Suppress these
            # on the discrivener side?
            return

        fancy_logger.get().debug("transcript: %s", message)

        user = self._client.get_user(message.user_id)
        if user is None:
            fancy_logger.get().warning("transcript: unknown user %s", message.user_id)
            return

        dump_transcript = False
        for segment in message.segments:
            line = TranscriptLine()
            line.timestamp = message.timestamp + (segment.start_offset_ms / 1000.0)
            line.text = segment.text
            line.user = user
            self._buffer.append(line)
            if not dump_transcript:
                dump_transcript = "transcript" in segment.text.lower()

        if dump_transcript:
            fancy_logger.get().info("transcript: dumping transcript")
            fancy_logger.get().info("lines %d", len(self._buffer.get()))
            for line in self._buffer.get():
                fancy_logger.get().info("transcript: %s", line)
