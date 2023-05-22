# -*- coding: utf-8 -*-
"""
Converts Discord library objects into generic objects that can be used by the AI

This is done to make it easier to swap out the Discord library for something else
in the future, and to make it easier to test the AI without having to mock the
Discord library.
"""


import base64
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


def replace_mention_ids_with_names(
    generic_message: types.GenericMessage,
    fn_user_id_to_name: typing.Callable[["re.Match[str]"], str],
):
    """
    Replace user ID mentions with the user's chosen display
    name in the given guild (aka server)
    """
    # it looks like normal IDs are 18 digits.  But give it some
    # wiggle room in case things change in the future.
    # e.g.: <@009999999999999999>
    at_mention_pattern = r"<@(\d{16,20})>"
    while True:
        match = re.search(at_mention_pattern, generic_message.body_text)
        if not match:
            break
        generic_message.body_text = (
            generic_message.body_text[: match.start()]
            + fn_user_id_to_name(match)
            + generic_message.body_text[match.end() :]
        )


def dm_user_id_to_name(
    bot_user_id: int,
    bot_name: str,
) -> typing.Callable[["re.Match[str]"], str]:
    """
    Replace user ID mentions with the bot's name.  Used when
    we are in a DM with the bot.
    """
    if " " in bot_name:
        bot_name = f'"{bot_name}"'

    def _replace_user_id_mention(match: typing.Match[str]) -> str:
        user_id = int(match.group(1))
        print(f"bot_user_id={bot_user_id}, user_id={user_id}")
        if user_id == bot_user_id:
            return f"@{bot_name}"
        return match.group(0)

    return _replace_user_id_mention


def guild_user_id_to_name(
    guild: discord.Guild,
) -> typing.Callable[["re.Match[str]"], str]:
    def _replace_user_id_mention(match: typing.Match[str]) -> str:
        user_id = int(match.group(1))
        member = guild.get_member(user_id)
        if member is None:
            return match.group(0)
        display_name = member.display_name
        if " " in display_name:
            display_name = f'"{display_name}"'
        return f"@{display_name}"

    return _replace_user_id_mention


def get_intents() -> discord.Intents:
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True
    return intents


async def test_discord_token(discord_token: str) -> bool:
    class _SimplestBot(discord.Client):
        async def on_ready(self):
            self.has_connected = True
            await self.close()

        def __init__(self):
            super().__init__(intents=get_intents())
            self.has_connected = False

    simplest_bot = _SimplestBot()
    try:
        await simplest_bot.start(discord_token, reconnect=False)
    except discord.LoginFailure:
        return False
    finally:
        await simplest_bot.close()
    return simplest_bot.has_connected


def get_user_id_from_token(discord_token: str) -> int:
    """
    Extract the bot's user ID from the discord token.
    """

    # turns out, the discord_token includes our client ID, so we can just
    # extract it from there.
    #
    # the discord token has this format:
    # AAAAAAAAAAAAAAAAAAAAAAAAAA.BBBBBB.CCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCCC
    #
    # where each section, A, B, and C, is independently a base64-encoded string.
    #
    # Section A encodes the bot's client ID, which is a 16-digit number.
    # the other sections aren't important here.
    token_parts = discord_token.split(".")
    token_part_a = token_parts[0]

    # the base64 decoder requires the string to be a multiple of 4 characters
    # long, so we need to add padding
    if len(token_part_a) % 4 != 0:
        token_part_a += "=" * (4 - len(token_part_a) % 4)

    return int(base64.b64decode(token_part_a).decode("utf-8"))


def generate_invite_url(ai_user_id: int) -> str:
    # we want to generate a URL like this:
    # https://discord.com/api/oauth2/authorize?client_id={client_id}&permissions={permissions}}&scope=bot
    #
    # where {client_id} is the bot's client ID, and {permissions} is the
    # permissions bit array with our desired permissions set.

    # for the permissions bit array, we can generate it with the library
    permissions = discord.Permissions(
        change_nickname=True,
        send_messages=True,
        create_public_threads=True,
        send_messages_in_threads=True,
        attach_files=True,
        read_message_history=True,
        read_messages=True,
        add_reactions=True,
    ).value

    return (
        "https://discord.com/api/oauth2/authorize?client_id="
        + f"{ai_user_id}&permissions={permissions}&scope=bot"
    )
