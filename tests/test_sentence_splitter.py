# -*- coding: utf-8 -*-
# import pytest
"""
Tests whether the sentence splitter works as expected
"""
from oobabot.ooba_client import SentenceSplitter


def test_split_text_to_sentences():
    text = "This is a sentence. This is another sentence."
    tokens = list(text)
    tokens.append(SentenceSplitter.END_OF_INPUT)

    sentence_1 = "This is a sentence. "
    sentence_2 = "This is another sentence."
    expected = []
    expected.extend([[]] * (len(sentence_1)))
    expected.append([sentence_1])
    expected.extend([[]] * (len(sentence_2) - 1))
    expected.append([sentence_2])

    sentence_1 = SentenceSplitter()
    for token in tokens:
        for sent in sentence_1.by_sentence(token):
            print(f"^{sent}$")

    splitter = SentenceSplitter()
    actual = [list(splitter.by_sentence(token)) for token in tokens]

    assert expected == actual
