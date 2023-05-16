# -*- coding: utf-8 -*-
# import pytest

from oobabot.ooba_client import SentenceSplitter


def test_split_text_to_sentences():
    text = "This is a sentence. This is another sentence."
    tokens = list(text)
    tokens.append(SentenceSplitter.END_OF_INPUT)

    s1 = "This is a sentence. "
    s2 = "This is another sentence."
    expected = []
    expected.extend([[]] * (len(s1)))
    expected.append([s1])
    expected.extend([[]] * (len(s2) - 1))
    expected.append([s2])

    s1 = SentenceSplitter()
    for token in tokens:
        for sent in s1.by_sentence(token):
            print(f"^{sent}$")

    splitter = SentenceSplitter()
    actual = [list(splitter.by_sentence(token)) for token in tokens]

    assert expected == actual
