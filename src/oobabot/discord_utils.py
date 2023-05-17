# -*- coding: utf-8 -*-
import re
import typing

import discord

from oobabot import fancy_logger
from oobabot import types

FORBIDDEN_CHARACTERS = r"[\n\r\t]"
FORBIDDEN_CHARACTERS_PATTERN = re.compile(FORBIDDEN_CHARACTERS)


def get_channel_name(channel: discord.abc.Messageable) -> str:
    if isinstance(channel, discord.Thread):
        return "thread #" + channel.name
    if isinstance(channel, discord.abc.GuildChannel):
        return "channel #" + channel.name
    if isinstance(channel, discord.DMChannel):
        return "-DM-"
    if isinstance(channel, discord.GroupChannel):
        return "-GROUP-DM-"
    return "-Unknown-"


def sanitize_string(raw_string: str) -> str:
    """
    Filter out any characters that would confuse the AI
    """
    return FORBIDDEN_CHARACTERS_PATTERN.sub(" ", raw_string)


def discord_message_to_generic_message(
    raw_message: discord.Message,
) -> typing.Union[types.GenericMessage, types.ChannelMessage, types.DirectMessage]:
    """
    Convert a discord message to a GenericMessage or subclass thereof
    """
    generic_args = {
        "author_id": raw_message.author.id,
        "author_name": sanitize_string(raw_message.author.display_name),
        "channel_id": raw_message.channel.id,
        "channel_name": get_channel_name(raw_message.channel),
        "message_id": raw_message.id,
        "body_text": sanitize_string(raw_message.content),
        "author_is_bot": raw_message.author.bot,
        "send_timestamp": raw_message.created_at.timestamp(),
        "reference_message_id": raw_message.reference.message_id
        if raw_message.reference
        else "",
    }
    if isinstance(raw_message.channel, discord.DMChannel):
        return types.DirectMessage(**generic_args)
    if isinstance(
        raw_message.channel, (discord.TextChannel, discord.GroupChannel, discord.Thread)
    ):
        return types.ChannelMessage(
            mentions=[mention.id for mention in raw_message.mentions],
            **generic_args,
        )
    fancy_logger.get().warning(
        f"Unknown channel type {type(raw_message.channel)}, "
        + f"unsolicited replies disabled.: {raw_message.channel}"
    )
    return types.GenericMessage(**generic_args)
