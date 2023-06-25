# -*- coding: utf-8 -*-
"""
would include tests for Oobabot if we had any good ones
"""

import json
import typing

import pytest

from oobabot import discrivener_message
from oobabot import transcript

TEST_FILE = "tests/test_data/discrivener-json.data"


def load_messages() -> typing.List["discrivener_message.DiscrivenerMessage"]:
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
                pytest.fail("could not parse %s", line)
    assert len(messages) == 71
    return messages


def test_can_make_transcript():
    messages = load_messages()
    script = transcript.Transcript(1, [])
    for message in messages:
        if isinstance(message, discrivener_message.UserVoiceMessage):
            script.on_transcription(message)

    assert 16 == script.message_buffer.size()
