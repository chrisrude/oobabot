# -*- coding: utf-8 -*-
"""
Detects when the bot is repeating previous messages, and attempts
to fix this by hiding the messages that it's repeating from its view
of the chat history.

Is also used to implement the /lobotomize command, which is the same
thing except it's triggered by a command instead of automatically.
"""
import typing

from oobabot import fancy_logger
from oobabot import types


class RepetitionTracker:
    """
    Tracks the last message the bot posted in each channel, and
    the number of times in a row it has been repeated.
    """

    def __init__(self, repetition_threshold: int) -> None:
        self.repetition_threshold = repetition_threshold

        # stores a map of channel_id ->
        #   (last_message, throttle_message_id, repetition_count)

        self.repetition_count: typing.Dict[int, typing.Tuple[str, int, int]] = {}

    def get_throttle_message_id(self, channel_id: int) -> int:
        """
        Returns the message ID of the last message that should be throttled, or 0
        if no throttling is needed
        """
        _, throttle_message_id, _ = self.repetition_count.get(
            channel_id, (None, 0, None)
        )
        return throttle_message_id

    def log_message(
        self, channel_id: int, response_message: types.GenericMessage
    ) -> None:
        """
        Logs a message sent by the bot, to be used for repetition tracking
        """
        # make string into canonical form
        sentence = self.make_canonical(response_message.body_text)

        last_message, throttle_message_id, repetition_count = self.repetition_count.get(
            channel_id, ("", 0, 0)
        )
        if last_message == sentence:
            repetition_count += 1
        else:
            repetition_count = 0

        if repetition_count > 0:
            fancy_logger.get().debug(
                "Repetition count for channel %d is %d", channel_id, repetition_count
            )

        if self.should_throttle(repetition_count):
            fancy_logger.get().warning(
                "Repetition found, will throttle history for channel #%d "
                + "in next request",
                channel_id,
            )
            throttle_message_id = response_message.message_id

        self.repetition_count[channel_id] = (
            sentence,
            throttle_message_id,
            repetition_count,
        )

    def hide_messages_before(self, channel_id: int, message_id: int) -> None:
        """
        Hides all messages before the given message ID in the given channel
        """
        sentence, _, repetition_count = self.repetition_count.get(
            channel_id, ("", 0, 0)
        )
        fancy_logger.get().info(
            "Hiding messages before message ID %d in channel %d", message_id, channel_id
        )
        self.repetition_count[channel_id] = (sentence, message_id, repetition_count)

    def should_throttle(self, repetition_count: int) -> bool:
        """
        Returns whether the bot should throttle history for a given repetition count
        """
        return repetition_count >= self.repetition_threshold

    def make_canonical(self, content: str) -> str:
        return content.strip().lower()
