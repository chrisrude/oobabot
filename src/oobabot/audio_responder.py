# -*- coding: utf-8 -*-
"""
Watches the transcript, when a wakeword is detected,
it builds a prompt for the AI, queries it, and
then queues a response.
"""

import asyncio
import typing

import discord

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
        prompt_generator: prompt_generator.PromptGenerator,
        ooba_client: ooba_client.OobaClient,
        transcript: transcript.Transcript,
    ):
        self._abort = False
        self._channel = channel
        self._prompt_generator = prompt_generator
        self._ooba_client = ooba_client
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

    async def _transcript_reply_task(self):
        fancy_logger.get().info("audio_responder: started")
        while not self._abort:
            fancy_logger.get().info("audio_responder: waiting for wakeword")
            await self._transcript.wakeword_event.wait()
            fancy_logger.get().info("audio_responder: wakeword detected")
            self._transcript.wakeword_event.clear()
            await self._respond()
        fancy_logger.get().info("audio_responder: exiting")

    async def _respond(self):
        fancy_logger.get().info("audio_responder: responding")
        transcript_history = self._transcript_history_iterator()
        prompt_prefix = await self._prompt_generator.generate(
            message_history=transcript_history,
            image_requested=False,
        )

        response = await self._ooba_client.request_as_string(prompt_prefix)

        # wait for silence before responding
        await self._transcript.silence_event.wait()

        # shove response into history
        self._transcript.add_bot_response(response)
        fancy_logger.get().info("audio_responder: response: %s", response)

        await self._channel.send(response)

    def _transcript_history_iterator(
        self,
    ) -> typing.AsyncIterator[types.GenericMessage]:
        lines = self._transcript.get_lines()
        lines.sort(key=lambda line: line.timestamp, reverse=True)

        # create an async generator which iterates over the lines
        # in the transcript
        async def _gen():
            for line in lines:
                author_id = line.user.id if line.user else 0
                author_name = line.user.name if line.user else "-unknown-"
                yield types.GenericMessage(
                    author_id=author_id,
                    author_name=author_name,
                    channel_id=0,
                    channel_name="",
                    message_id=0,
                    reference_message_id=0,
                    body_text=line.text,
                    author_is_bot=False,
                    send_timestamp=line.timestamp.timestamp(),
                )

        return _gen()
