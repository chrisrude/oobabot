# todo: write tests

from oobabot import oobabot


def test_things_can_be_created_at_least():
    args = ["--discord-token", "1234"]
    oobabot.OobaBot(args)
