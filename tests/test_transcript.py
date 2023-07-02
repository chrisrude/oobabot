# -*- coding: utf-8 -*-
"""
would include tests for Oobabot if we had any good ones
"""

import asyncio
import json
import typing

import pytest

from oobabot import discrivener_message
from oobabot import transcript
from oobabot import types

TEST_FILE = "tests/test_data/discrivener-json.data"


def load_messages() -> typing.List["types.DiscrivenerMessage"]:
    messages = []
    with open(TEST_FILE, "r", encoding="utf-8") as file:
        for line in file.readlines():
            try:
                message = json.loads(
                    line,
                    object_pairs_hook=discrivener_message.object_pairs_hook,
                )
                messages.append(message)
            except json.JSONDecodeError:
                pytest.fail(f"could not parse {line}")
    assert len(messages) == 71
    return messages


def test_can_make_transcript():
    messages = load_messages()

    # on python3.9 and earlier, we need to manually create
    # an event loop for the transcript to run in
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        print("creating new event loop")
        asyncio.set_event_loop(asyncio.new_event_loop())

    script = transcript.Transcript(1, [])
    for message in messages:
        if isinstance(message, discrivener_message.UserVoiceMessage):
            script.on_transcription(message)

    assert 16 == script.message_buffer.size()
