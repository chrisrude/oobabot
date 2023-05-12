import random
import re
import typing
from typing import List

from oobabot.fancy_logging import get_logger
from oobabot.types import ChannelMessage
from oobabot.types import DirectMessage
from oobabot.types import GenericMessage


class LastReplyTimes(dict):
    """
    A dictionary that keeps track of the last time we were mentioned
    in a channel.

    This uses the timestamp on the message, not the local system's
    RTC.  The advantage of this is that if messages are delayed,
    we'll only respond to ones that were actually sent within the
    appropriate time window.
    """

    def __init__(self, cache_timeout: float):
        self.cache_timeout = cache_timeout

    def purge_outdated(self, latest_timestamp: float) -> None:
        oldest_time_to_keep = latest_timestamp - self.cache_timeout
        purged = {
            channel_id: response_time
            for channel_id, response_time in self.items()
            if response_time >= oldest_time_to_keep
        }
        self.clear()
        self.update(purged)

    def log_mention(self, message: ChannelMessage) -> None:
        self[message.channel_id] = message.send_timestamp

    def time_since_last_mention(self, message: ChannelMessage) -> float:
        self.purge_outdated(message.send_timestamp)
        return message.send_timestamp - self.get(message.channel_id, 0)


class DecideToRespond:
    """
    Decide whether to respond to a message.
    """

    def __init__(
        self,
        wakewords: List[str],
        ignore_dms: bool,
        interrobang_bonus: float,
        time_vs_response_chance: typing.List[typing.Tuple[float, float]],
    ):
        self.wakewords = wakewords
        self.ignore_dms = ignore_dms
        self.interrobang_bonus = interrobang_bonus
        self.time_vs_response_chance = time_vs_response_chance

        last_reply_cache_timeout = max(time for time, _ in time_vs_response_chance)
        self.last_reply_times = LastReplyTimes(last_reply_cache_timeout)

        # match messages that include any `wakeword`, but not as part of
        # another word
        self.wakeword_patterns = [
            re.compile(rf"\b{wakeword}\b", re.IGNORECASE) for wakeword in self.wakewords
        ]

    def is_directly_mentioned(self, our_user_id: int, message: GenericMessage) -> bool:
        """
        Returns True if the message is a direct message to us, or if it
        mentions us by @name or wakeword.
        """

        # reply to all private messages
        if isinstance(message, DirectMessage):
            if self.ignore_dms:
                return False
            return True

        # reply to all messages in which we're @-mentioned
        if isinstance(message, ChannelMessage):
            if message.is_mentioned(our_user_id):
                return True

        # reply to all messages that include a wakeword
        for wakeword_pattern in self.wakeword_patterns:
            if wakeword_pattern.search(message.body_text):
                return True

        return False

    def calc_base_chance_of_unsolicited_reply(self, message: ChannelMessage) -> float:
        """
        Calculate base chance of unsolicited reply using the
        TIME_VS_RESPONSE_CHANCE table.
        """
        # return a base chance that we'll respond to a message that wasn't
        # addressed to us, based on the table in TIME_VS_RESPONSE_CHANCE.
        # other factors might increase this chance.
        time_since_last_send = self.last_reply_times.time_since_last_mention(message)
        response_chance = 0.0
        for duration, chance in self.time_vs_response_chance:
            if time_since_last_send < duration:
                response_chance = chance
                break
        return response_chance

    def provide_unsolicited_reply_in_channel(
        self, our_user_id: int, message: ChannelMessage
    ) -> bool:
        # if we're not at-mentioned but others are, don't reply
        if message.mentions and not message.is_mentioned(our_user_id):
            return False

        # if message is empty, don't reply.  This can happen if someone
        # posts an image or an attachment without a comment.
        if message.is_empty():
            return False

        # if we've posted recently in this channel, there are a few
        # other reasons we may respond.  But if we haven't, just
        # ignore the message.

        # if we haven't posted to this channel recently, don't reply
        response_chance = self.calc_base_chance_of_unsolicited_reply(message)
        if response_chance == 0.0:
            return False

        # if the new message ends with a question mark, we'll respond
        if message.body_text.endswith("?"):
            response_chance += self.interrobang_bonus

        # if the new message ends with an exclamation point, we'll respond
        if message.body_text.endswith("!"):
            response_chance += self.interrobang_bonus

        time_since_last_mention = self.last_reply_times.time_since_last_mention(message)
        get_logger().debug(
            f"Considering unsolicited message in channel {message.channel_id} "
            f"after {time_since_last_mention:2.0f} seconds, "
            f"with chance {response_chance*100.0:2.0f}%."
        )

        if random.random() < response_chance:
            return True

        return False

    def should_reply_to_message(
        self, our_user_id: int, message: GenericMessage
    ) -> bool:
        # ignore messages from other bots, out of fear of infinite loops,
        # as well as world domination
        if message.author_is_bot:
            return False

        # we do not want the bot to reply to itself.  This is redundant
        # with the previous check, except it won't be if someone decides
        # to run this under their own user token, rather than a proper
        # bot token.
        if message.author_id == our_user_id:
            return False

        if self.is_directly_mentioned(our_user_id, message):
            if isinstance(message, ChannelMessage):
                self.last_reply_times.log_mention(message)
            return True

        if isinstance(message, ChannelMessage):
            if self.provide_unsolicited_reply_in_channel(our_user_id, message):
                return True

        # ignore anything else
        return False
