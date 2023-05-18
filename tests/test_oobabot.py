# -*- coding: utf-8 -*-
# todo: write tests
"""
would include tests for Oobabot if we had any good ones
"""
from oobabot import oobabot


def test_things_can_be_created_at_least():
    args = ["--discord-token", "1234"]
    oobabot.OobaBot(args)
