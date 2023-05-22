# -*- coding: utf-8 -*-
"""
Decides whether the bot responds to a message.
"""

import random
import typing

from oobabot import fancy_logger
from oobabot import persona
from oobabot import types


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

    def log_mention(self, channel_id: int, send_timestamp: float) -> None:
        self[channel_id] = send_timestamp

    def time_since_last_mention(self, message: types.ChannelMessage) -> float:
        self.purge_outdated(message.send_timestamp)
        return message.send_timestamp - self.get(message.channel_id, 0)


class DecideToRespond:
    """
    Decide whether to respond to a message.
    """

    def __init__(
        self,
        discord_settings: dict,
        persona: persona.Persona,
        interrobang_bonus: float,
        time_vs_response_chance: typing.List[typing.Tuple[float, float]],
    ):
        self.ignore_dms = discord_settings["ignore_dms"]
        self.interrobang_bonus = interrobang_bonus
        self.persona = persona
        self.time_vs_response_chance = time_vs_response_chance

        last_reply_cache_timeout = max(time for time, _ in time_vs_response_chance)
        self.last_reply_times = LastReplyTimes(last_reply_cache_timeout)

    def is_directly_mentioned(
        self, our_user_id: int, message: types.GenericMessage
    ) -> bool:
        """
        Returns True if the message is a direct message to us, or if it
        mentions us by @name or wakeword.
        """

        # reply to all private messages
        if isinstance(message, types.DirectMessage):
            if self.ignore_dms:
                return False
            return True

        # reply to all messages in which we're @-mentioned
        if isinstance(message, types.ChannelMessage):
            if message.is_mentioned(our_user_id):
                return True

        # reply to all messages that include a wakeword
        if self.persona.contains_wakeword(message.body_text):
            return True

        return False

    def calc_base_chance_of_unsolicited_reply(
        self, message: types.ChannelMessage
    ) -> float:
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
        self, our_user_id: int, message: types.ChannelMessage
    ) -> bool:
        """
        Returns True if we should respond to the message, even
        though we weren't directly mentioned.
        """

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
        fancy_logger.get().debug(
            "Considering unsolicited response in channel %s after %2.0f seconds.  "
            + "chance: %2.0f%%.",
            message.channel_name,
            time_since_last_mention,
            response_chance * 100.0,
        )

        if random.random() < response_chance:
            return True

        return False

    def should_reply_to_message(
        self, our_user_id: int, message: types.GenericMessage
    ) -> typing.Tuple[bool, bool]:
        """
        Returns a tuple of (should_reply, is_direct_mention).

        Direct mentions are always replied to, but also, the
        caller should log the mention later by calling log_mention().

        The only reason this method doesn't to so itself is that
        in the case of us generating a thread to reply on, the
        channel ID we want to track will be that of the thread
        we create, not the channel the message was posted in.
        """

        # ignore messages from other bots, out of fear of infinite loops,
        # as well as world domination
        if message.author_is_bot:
            return (False, False)

        # we do not want the bot to reply to itself.  This is redundant
        # with the previous check, except it won't be if someone decides
        # to run this under their own user token, rather than a proper
        # bot token.
        if message.author_id == our_user_id:
            return (False, False)

        if self.is_directly_mentioned(our_user_id, message):
            return (True, True)

        if isinstance(message, types.ChannelMessage):
            if self.provide_unsolicited_reply_in_channel(our_user_id, message):
                return (True, False)

        # ignore anything else
        return (False, False)

    def log_mention(self, channel_id: int, send_timestamp: float) -> None:
        self.last_reply_times.log_mention(channel_id, send_timestamp)
