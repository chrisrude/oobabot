import typing

from oobabot.fancy_logging import get_logger
from oobabot.types import GenericMessage


class RepetitionTracker:
    # how many times the bot can repeat the same thing before we
    # throttle history

    def __init__(self, repetition_threshold: int) -> None:
        self.repetition_threshold = repetition_threshold

        # stores a map of channel_id ->
        #   (last_message, throttle_message_id, repetion_count)

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

    def log_message(self, channel_id: int, response_message: GenericMessage) -> None:
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
            get_logger().debug(
                f"Repetition count for channel {channel_id} is {repetition_count}"
            )

        if self.should_throttle(repetition_count):
            get_logger().warning(
                "Repetition found, will throttle history for channel "
                + f"{channel_id} in next request"
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
        get_logger().info(
            "Hiding messages before message ID "
            + f"{message_id} in channel {channel_id}"
        )
        self.repetition_count[channel_id] = (sentence, message_id, repetition_count)

    def should_throttle(self, repetition_count: int) -> bool:
        """
        Returns whether the bot should throttle history for a given repetition count
        """
        return repetition_count >= self.repetition_threshold

    def make_canonical(self, content: str) -> str:
        return content.strip().lower()
