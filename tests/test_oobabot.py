# -*- coding: utf-8 -*-
# todo: write tests
"""
would include tests for Oobabot if we had any good ones
"""
import os

from oobabot import oobabot


def test_things_can_be_created_at_least():
    args = ["--discord-token", "1234"]
    oobabot.Oobabot(args)


def test_discord_token():
    bot = oobabot.Oobabot([])
    connected = bot.test_discord_token("1234")
    assert connected is False

    # if token is set in the environment, expect it to be valid
    token = os.environ.get(oobabot.settings.Settings.DISCORD_TOKEN_ENV_VAR, "")
    if token:
        connected = bot.test_discord_token(token)
        assert connected is True
