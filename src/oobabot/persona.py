# -*- coding: utf-8 -*-
"""
Retrieves persona data from a variety of formats.
"""

import json
import re
import typing

import ruamel.yaml as ryaml

from oobabot import fancy_logger


class Persona:
    """
    Handles retrieving persona data from a variety of formats
    """

    ai_name: str
    """
    The name of the AI.
    """

    persona: str
    """
    The persona of the AI.
    """

    wakewords: typing.List[str]
    """
    If we see one of these words in a message, we'll respond to it.
    """

    # list of keys that, depending on the json/yaml schema, might
    # contain the AI's name.  Take the first one found, in order.
    NAME_KEYS = ["char_name", "name"]

    # list of keys that, depending on the json/yaml schema, might
    # contain the AI's persona.  Take the first one found, in order.
    PERSONA_KEYS = ["char_persona", "description", "context", "personality"]

    def __init__(self, persona_settings: dict) -> None:
        self.ai_name = persona_settings["ai_name"]
        self.persona = persona_settings["persona"]
        self.wakewords = persona_settings["wakewords"].copy()

        # if a json file is specified, load it and have
        # that overwrite everything else
        if "persona_file" in persona_settings:
            filename = persona_settings["persona_file"]
            try:
                self.load_from_file(filename)
            except FileNotFoundError:
                fancy_logger.get().warning(
                    "Could not find persona file: %s",
                    filename,
                )
                return

        # match messages that include any `wakeword`, but not as part of
        # another word
        self.wakeword_patterns = [
            re.compile(rf"\b{wakeword}\b", re.IGNORECASE) for wakeword in self.wakewords
        ]

    def contains_wakeword(self, message: str) -> bool:
        for wakeword_pattern in self.wakeword_patterns:
            if wakeword_pattern.search(message):
                return True
        return False

    def substitute(self, text: str) -> str:
        return text.replace("{{char}}", self.ai_name)

    def load_from_file(self, filename: str):
        if not filename:
            return

        if filename.endswith(".json"):
            self.load_from_json_file(filename)
            return

        if filename.endswith(".yaml"):
            self.load_from_yaml_file(filename)
            return

        if filename.endswith(".txt"):
            self.load_from_text_file(filename)
            return

        fancy_logger.get().warning(
            "Unknown persona file extension (expected .json, or .txt): %s",
            filename,
        )

    def load_from_text_file(self, filename: str):
        with open(filename, "r", encoding="utf-8") as file:
            persona = file.read()
        self.persona = persona

    def load_from_json_file(self, filename: str):
        try:
            with open(filename, "r", encoding="utf-8") as file:
                json_data = json.load(file)

        except json.JSONDecodeError as err:
            fancy_logger.get().warning(
                "Could not parse persona file: %s.  Cause: %s",
                filename,
                err,
            )
            return
        self.load_from_dict(json_data)

    def load_from_yaml_file(self, filename):
        with open(filename, "r", encoding="utf-8") as file:
            yaml = ryaml.YAML(typ="safe")
            try:
                yaml_settings = yaml.load(file)
            except ryaml.YAMLError as err:
                fancy_logger.get().warning(
                    "Could not parse persona file: %s.  Cause: %s",
                    filename,
                    err,
                )
                return
        self.load_from_dict(yaml_settings)

    def load_from_dict(self, json_data: dict):
        for name_key in Persona.NAME_KEYS:
            if name_key in json_data and json_data[name_key]:
                self.ai_name = json_data[name_key]
                break
        for persona_key in Persona.PERSONA_KEYS:
            if persona_key in json_data and json_data[persona_key]:
                self.persona = self.substitute(json_data[persona_key])
                break
        if self.ai_name not in self.wakewords and self.ai_name:
            self.wakewords.append(self.ai_name)
