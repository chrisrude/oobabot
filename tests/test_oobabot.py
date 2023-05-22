# -*- coding: utf-8 -*-
"""
would include tests for Oobabot if we had any good ones
"""
import asyncio
import os

import aiohttp

from oobabot import oobabot


def test_things_can_be_created_at_least():
    args = ["--discord-token", "1234"]
    oobabot.Oobabot(args)


def test_user_id_extraction():
    assert 1111111111111111111 == oobabot.discord_utils.get_user_id_from_token(
        "MTExMTExMTExMTExMTExMTExMQ.000000.00000000000000000000000000000000000000"
    )

    assert 1234567891101101011 == oobabot.discord_utils.get_user_id_from_token(
        "MTIzNDU2Nzg5MTEwMTEwMTAxMQ.000000.00000000000000000000000000000000000000"
    )


def test_discord_token():
    bot = oobabot.Oobabot([])
    connected = bot.test_discord_token("1234")
    assert connected is False

    # if token is set in the environment, expect it to be valid
    token = os.environ.get(oobabot.settings.Settings.DISCORD_TOKEN_ENV_VAR, "")
    if token:
        connected = bot.test_discord_token(token)
        assert connected is True


def test_invite_url():
    bot = oobabot.Oobabot([])
    token = os.environ.get(oobabot.settings.Settings.DISCORD_TOKEN_ENV_VAR, "")
    if not token:
        return
    url = bot.generate_invite_url(token)

    async def test_url(url: str) -> bool:
        print(url)
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                print(resp.status)
                return resp.status == 200

    result = asyncio.run(test_url(url))
    assert result is True
