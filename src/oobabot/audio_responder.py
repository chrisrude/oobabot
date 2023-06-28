# -*- coding: utf-8 -*-
"""
Watches the transcript, when a wakeword is detected,
it builds a prompt for the AI, queries it, and
then queues a response.
"""

import asyncio
import typing

import discord

from oobabot import discord_utils
from oobabot import discrivener
from oobabot import fancy_logger
from oobabot import ooba_client
from oobabot import prompt_generator
from oobabot import transcript
from oobabot import types


class AudioResponder:
    """
    Watches the transcript, when a wakeword is detected,
    it builds a prompt for the AI, queries it, and
    then queues a response.
    """

    TASK_TIMEOUT_SECONDS = 5.0

    def __init__(
        self,
        channel: discord.VoiceChannel,
        discrivener: discrivener.Discrivener,
        ooba_client: ooba_client.OobaClient,
        prompt_generator: prompt_generator.PromptGenerator,
        transcript: transcript.Transcript,
    ):
        self._abort = False
        self._channel = channel
        self._discrivener = discrivener
        self._ooba_client = ooba_client
        self._prompt_generator = prompt_generator
        self._transcript = transcript
        self._task: typing.Optional[asyncio.Task] = None

    async def start(self):
        await self.stop()
        self._task = asyncio.create_task(self._transcript_reply_task())

    async def stop(self):
        if self._task is None:
            return

        self._abort = True
        self._task.cancel()
        try:
            await asyncio.wait_for(self._task, timeout=self.TASK_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            fancy_logger.get().warning("audio_responder: task did not quit in time")
        except asyncio.CancelledError:
            fancy_logger.get().info("audio_responder: task stopped")
        self._task = None
        self._abort = False

    # @fancy_logger.log_async_task
    async def _transcript_reply_task(self):
        fancy_logger.get().info("audio_responder: started")
        while not self._abort:
            await self._transcript.wakeword_event.wait()
            self._transcript.wakeword_event.clear()
            await self._respond()

        fancy_logger.get().info("audio_responder: exiting")

    async def _respond(self):
        transcript_history = self._transcript_history_iterator()
        prompt_prefix = await self._prompt_generator.generate(
            message_history=transcript_history,
            image_requested=False,
        )

        response = await self._ooba_client.request_as_string(prompt_prefix)
        fancy_logger.get().debug("received response: '%s'", response)

        # wait for silence before responding
        await self._transcript.silence_event.wait()

        # shove response into history
        self._transcript.on_bot_response(response)

        self._discrivener.speak(response)
        # todo: make this a setting?
        # await self._channel.send(response)

    def _transcript_history_iterator(
        self,
    ) -> typing.AsyncIterator[types.GenericMessage]:
        voice_messages = self._transcript.message_buffer.get()
        voice_messages.sort(key=lambda message: message.start_time, reverse=True)

        # create an async generator which iterates over the lines
        # in the transcript
        async def _gen():
            for message in voice_messages:
                author = discord_utils.author_from_user_id(
                    message.user_id,
                    self._channel.guild,
                )
                if author is None:
                    author_name = f"user #{message.user_id}"
                    author_is_bot = message.is_bot
                else:
                    author_name = author.author_name
                    author_is_bot = author.author_is_bot
                yield types.GenericMessage(
                    author_id=message.user_id,
                    author_name=author_name,
                    channel_id=0,
                    channel_name="",
                    message_id=0,
                    reference_message_id=0,
                    body_text=message.text,
                    author_is_bot=author_is_bot,
                    send_timestamp=message.start_time.timestamp(),
                )

        return _gen()
