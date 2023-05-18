# -*- coding: utf-8 -*-
# import pytest
"""
Tests loading persona files in different formats
"""
import pytest

import oobabot.persona

BASE_SETTINGS = {
    "ai_name": "oobabot",
    "persona": "",
    "wakewords": [],
}


@pytest.fixture(autouse=True)
def change_test_dir(request, monkeypatch):
    monkeypatch.chdir(request.fspath.dirname)


def test_persona_loading_base():
    test_char_1_json = BASE_SETTINGS.copy()
    persona = oobabot.persona.Persona(test_char_1_json)
    assert persona.ai_name == BASE_SETTINGS["ai_name"]
    assert persona.persona == BASE_SETTINGS["persona"]
    assert persona.wakewords == BASE_SETTINGS["wakewords"]


def test_persona_loading_json_1():
    test_char_1_json = BASE_SETTINGS.copy()
    test_char_1_json["persona_file"] = "./test_data/test-char-1.json"
    persona = oobabot.persona.Persona(test_char_1_json)
    assert persona.ai_name == "...name..."
    assert persona.persona == "...name... ...description..."
    assert persona.wakewords == ["...name..."]


def test_persona_loading_json_2():
    test_char_2_json = BASE_SETTINGS.copy()
    test_char_2_json["persona_file"] = "./test_data/test-char-2.json"
    persona = oobabot.persona.Persona(test_char_2_json)
    assert persona.ai_name == "...name..."
    assert persona.persona == "...persona..."
    assert persona.wakewords == ["...name..."]


def test_persona_loading_json_3():
    test_char_3_json = BASE_SETTINGS.copy()
    test_char_3_json["persona_file"] = "./test_data/test-char-3.json"
    persona = oobabot.persona.Persona(test_char_3_json)
    assert persona.ai_name == "...char_name..."
    assert persona.persona == "...char_persona..."
    print(persona.wakewords)
    assert persona.wakewords == ["...char_name..."]


def test_persona_loading_yaml():
    test_char_1_yaml = BASE_SETTINGS.copy()
    test_char_1_yaml["persona_file"] = "./test_data/test-char-1.yaml"
    persona = oobabot.persona.Persona(test_char_1_yaml)
    assert persona.ai_name == "...name..."
    assert persona.persona == "...context..."
    # assert persona.wakewords == ["...name..."]


def test_persona_loading_txt():
    test_char_1_txt = BASE_SETTINGS.copy()
    test_char_1_txt["persona_file"] = "./test_data/test-char-1.txt"
    persona = oobabot.persona.Persona(test_char_1_txt)
    assert persona.ai_name == BASE_SETTINGS["ai_name"]
    assert persona.persona == "...persona...\n"
    # assert persona.wakewords == BASE_SETTINGS["wakewords"]
