# -*- coding: utf-8 -*-
"""
Stores a transcript of a voice channel.
"""
import discord

from oobabot import discord_utils
from oobabot import discrivener
from oobabot import fancy_logger


class Transcript:
    """
    Stores a transcript of a voice channel.
    """

    _client: discord.client.Client
    _buffer: discord_utils.RingBuffer

    def __init__(self, client: discord.client.Client):
        self._client = client
        self._buffer = discord_utils.RingBuffer[discrivener.TranscribedMessage](100)

    def on_transcribed_message(self, message: discrivener.TranscribedMessage) -> None:
        fancy_logger.get().debug("transcript: %s", message)
