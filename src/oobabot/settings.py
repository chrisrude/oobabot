# -*- coding: utf-8 -*-
import argparse
import os
import shutil
import sys
import textwrap
import typing

import ruamel.yaml as ryaml

import oobabot
from oobabot import templates


def console_wrapped(message):
    width = shutil.get_terminal_size().columns
    return "\n".join(textwrap.wrap(message, width))


YAML_WIDTH = 60
DIVIDER = "# " * (YAML_WIDTH >> 1)
INDENT_UNIT = 4


def format_yaml_comment(comment_lines: typing.List[str]) -> str:
    out = []
    for line in comment_lines:
        out.append("\n".join(textwrap.wrap(line, width=YAML_WIDTH)))
    return "\n" + "\n".join(out)


def add_to_group(
    group: ryaml.CommentedMap,
    key: str,
    value: typing.Any,
    comment_lines: typing.List[str],
    indent: int,
) -> None:
    group[key] = value
    group.yaml_set_comment_before_after_key(
        key,
        before=format_yaml_comment(comment_lines),
        indent=indent,
    )


def make_template_help(
    template: templates.TemplateMessageFormatter,
) -> typing.List[str]:
    return [
        template.purpose,
        f"Allowed tokens: {', '.join([str(t) for t in template.allowed_tokens])}",
    ]


class Settings(argparse.ArgumentParser):
    """
    User=customizable settings for the bot.  Reads from
    environment variables and command line arguments.
    """

    ############################################################
    # This section is for constants which are not yet
    # customizable by the user.

    # this is the number of tokens we reserve for the AI
    # to respond with.
    OOBABOT_MAX_NEW_TOKENS: int = 250

    # this is the number of tokens the AI has available
    # across its entire request + response
    OOBABOT_MAX_AI_TOKEN_SPACE: int = 730

    # This is a table of the probability that the bot will respond
    # in an unsolicited manner (i.e. it isn't specifically pinged)
    # to a message, based on how long ago it was pinged in that
    # same channel.
    TIME_VS_RESPONSE_CHANCE: typing.List[typing.Tuple[float, float]] = [
        # (seconds, base % chance of an unsolicited response)
        (60.0, 0.90),
        (120.0, 0.70),
        (60.0 * 5, 0.50),
    ]

    # increased chance of responding to a message if it ends with
    # a question mark or exclamation point
    DECIDE_TO_RESPOND_INTERROBANG_BONUS = 0.3

    # number of times in a row that the bot will repeat itself
    # before the repetition tracker will take action
    REPETITION_TRACKER_THRESHOLD = 1

    OOBABOOGA_DEFAULT_REQUEST_PARAMS: typing.Dict[
        str, typing.Union[bool, float, int, str, typing.List[typing.Any]]
    ] = {
        "max_new_tokens": OOBABOT_MAX_NEW_TOKENS,
        "do_sample": True,
        "temperature": 1.3,
        "top_p": 0.1,
        "typical_p": 1,
        "repetition_penalty": 1.18,
        "top_k": 40,
        "min_length": 0,
        "no_repeat_ngram_size": 0,
        "num_beams": 1,
        "penalty_alpha": 0,
        "length_penalty": 1,
        "early_stopping": False,
        "seed": -1,
        "add_bos_token": True,
        "truncation_length": OOBABOT_MAX_AI_TOKEN_SPACE,
        "ban_eos_token": False,
        "skip_special_tokens": True,
        "stopping_strings": [],
    }

    ############################################################
    # These are the default settings for the bot.  They can be
    # overridden by environment variables or command line arguments.

    # number lines back in the message history to include in the prompt
    DEFAULT_HISTORY_LINES_TO_SUPPLY = 7

    # words to look for in the prompt to indicate that the user
    # wants to generate an image
    DEFAULT_IMAGE_WORDS: typing.List[str] = [
        "drawing",
        "photo",
        "pic",
        "picture",
        "image",
        "sketch",
    ]

    # square image, 512x512
    DEFAULT_STABLE_DIFFUSION_IMAGE_SIZE: int = 512

    # 30 steps of diffusion
    DEFAULT_STABLE_DIFFUSION_STEPS: int = 30

    # ENVIRONMENT VARIABLES ####

    DISCORD_TOKEN_ENV_VAR: str = "DISCORD_TOKEN"
    DISCORD_TOKEN_ENV: str = os.environ.get(DISCORD_TOKEN_ENV_VAR, "")

    OOBABOT_PERSONA_ENV_VAR: str = "OOBABOT_PERSONA"
    OOBABOT_PERSONA: str = os.environ.get(OOBABOT_PERSONA_ENV_VAR, "")

    DEFAULT_WAKEWORDS: typing.List[str] = ["oobabot"]
    DEFAULT_URL: str = "ws://localhost:5005"

    # set default negative prompts to make it more difficult
    # to create content against the discord TOS
    # https://discord.com/guidelines

    # use this prompt for "age_restricted" Discord channels
    #  i.e. channel.nsfw is true
    DEFAULT_SD_NEGATIVE_PROMPT_NSFW: str = "animal harm, suicide, loli"

    # use this prompt for non-age-restricted channels
    DEFAULT_SD_NEGATIVE_PROMPT: str = DEFAULT_SD_NEGATIVE_PROMPT_NSFW + ", nsfw"

    DEPRECATED: str = "Deprecated"

    def __init__(self):
        self._settings = None

        super().__init__(
            description=f"oobabot v{oobabot.__version__}: Discord bot for "
            + "oobabooga's text-generation-webui",
            formatter_class=argparse.ArgumentDefaultsHelpFormatter,
            add_help=False,
        )

        ###########################################################
        # General Settings
        #  won't be included in the config.yaml

        # add our own help handler so that we can print an extra
        # message at the end
        self.add_argument(
            "-h",
            "--help",
            action="store_true",
            default=argparse.SUPPRESS,
        )

        self.add_argument(
            "--generate-config",
            default=False,
            help="If set, oobabot will print its configuration "
            "as a .yml file, then exit.  Any command-line settings "
            "also passed will be reflected in this file.",
            action="store_true",
        )

        ###########################################################
        # Persona Settings

        persona_group = self.add_argument_group("Persona")
        persona_group.add_argument(
            "--ai-name",
            type=str,
            default="oobabot",
            help="Name the AI will use to refer to itself",
        )
        persona_group.add_argument(
            "--persona",
            type=str,
            help="This prefix will be added in front of every user-supplied "
            + "request.  This is useful for setting up a 'character' for the "
            + "bot to play.  Alternatively, this can be set with the "
            + f"{self.OOBABOT_PERSONA_ENV_VAR} environment variable.",
        )
        persona_group.add_argument(
            "--wakewords",
            type=str,
            nargs="*",
            default=self.DEFAULT_WAKEWORDS,
            help="One or more words that the bot will listen for.\n "
            + "The bot will listen in all discord channels can "
            + "access for one of these words to be mentioned, then reply "
            + "to any messages it sees with a matching word.  "
            + "The bot will always reply to @-mentions and "
            + "direct messages, even if no wakewords are supplied.",
        )
        ###########################################################
        # Discord Settings

        discord_group = self.add_argument_group("Discord")
        discord_group.add_argument(
            "--discord-token",
            type=str,
            help="Token to log into Discord with.  For security "
            + "purposes it's strongly recommended that you set "
            + f"this via the {self.DISCORD_TOKEN_ENV_VAR} environment "
            + "variable instead, if possible.",
        )
        discord_group.add_argument(
            "--dont-split-responses",
            default=False,
            help="Post the entire response as a single "
            + "message, rather than splitting it into seperate "
            + "messages by sentence.",
            action="store_true",
        )
        discord_group.add_argument(
            "--history-lines",
            type=int,
            default=self.DEFAULT_HISTORY_LINES_TO_SUPPLY,
            help="Number of lines of chat history the AI will see "
            + "when generating a response.",
        )
        discord_group.add_argument(
            "--ignore-dms",
            default=False,
            help="Do not respond to direct messages.",
            action="store_true",
        )
        discord_group.add_argument(
            "--reply-in-thread",
            default=False,
            help="If not in a thread, generate one to respond into.",
            action="store_true",
        )
        discord_group.add_argument(
            "--stream-responses",
            default=False,
            help="Stream responses into a single message as it is generated.",
            action="store_true",
        )

        ###########################################################
        # Oobabooga Settings

        oobabooga_group = self.add_argument_group("Oobabooga")

        oobabooga_group.add_argument(
            "--base-url",
            type=str,
            default=self.DEFAULT_URL,
            help="Base URL for the oobabooga instance.  "
            + "This should be ws://hostname[:port] for plain websocket "
            + "connections, or wss://hostname[:port] for websocket "
            + "connections over TLS.",
        )
        oobabooga_group.add_argument(
            "--log-all-the-things",
            default=False,
            help="Prints all AI input and output to STDOUT",
            action="store_true",
        )

        ###########################################################
        # Stable Diffusion Settings

        stable_diffusion_group = self.add_argument_group("Stable Diffusion")
        stable_diffusion_group.add_argument(
            "--image-words",
            type=str,
            nargs="*",
            default=self.DEFAULT_IMAGE_WORDS,
            help="When one of these words is used in a message, the bot will "
            + "generate an image.",
        )
        stable_diffusion_group.add_argument(
            "--stable-diffusion-url",
            "--sd-url",
            type=str,
            default=None,
            help="URL for an AUTOMATIC1111 Stable Diffusion server",
        )

        ###########################################################
        # Deprecated Settings
        # These used to be part of the Stable Diffusion section,
        # but now are covered in the stable_diffusion->request_params
        # section of the config.yml file.
        #
        # These are still here for backwards compatibility, but
        # will be removed in a future release.
        #
        # They're being moved since they're redundant with the
        # request_params values, and it's confusing to have those
        # set in two separate places.
        #
        # The settings won't be written to the config.yaml template,
        # as they're already covered in the request_params section.

        deprecated_group = self.add_argument_group(
            title=self.DEPRECATED,
            description="These settings are deprecated and will be removed in a "
            + "future release.  Please set them with config.yml instead.",
        )
        deprecated_group.add_argument(
            "--diffusion-steps",
            type=int,
            default=self.DEFAULT_STABLE_DIFFUSION_STEPS,
            help="Number of diffusion steps to take when generating an image.  "
            + f"The default is {self.DEFAULT_STABLE_DIFFUSION_STEPS}.",
        )
        deprecated_group.add_argument(
            "--image-height",
            type=int,
            default=self.DEFAULT_STABLE_DIFFUSION_IMAGE_SIZE,
            help="Size of images to generate.  This is the height of the image "
            + "in pixels.  The default is "
            + f"{self.DEFAULT_STABLE_DIFFUSION_IMAGE_SIZE}.",
        )
        deprecated_group.add_argument(
            "--image-width",
            type=int,
            default=self.DEFAULT_STABLE_DIFFUSION_IMAGE_SIZE,
            help="Size of images to generate.  This is the width of the image "
            + "in pixels.  The default is "
            + f"{self.DEFAULT_STABLE_DIFFUSION_IMAGE_SIZE}.",
        )
        deprecated_group.add_argument(
            "--stable-diffusion-sampler",
            "--sd-sampler",
            type=str,
            default="",
            help="Sampler to use when generating images.  If not specified, the one "
            + "set on the AUTOMATIC1111 server will be used.",
        )
        deprecated_group.add_argument(
            "--sd-negative-prompt",
            type=str,
            default=self.DEFAULT_SD_NEGATIVE_PROMPT,
            help="Negative prompt to use when generating images.  This will discourage"
            + " Stable Diffusion from generating images with the specified content.  "
            + "By default, this is set to follow Discord's TOS.",
        )
        deprecated_group.add_argument(
            "--sd-negative-prompt-nsfw",
            type=str,
            default=self.DEFAULT_SD_NEGATIVE_PROMPT_NSFW,
            help="Negative prompt to use when generating images in a channel marked as "
            + "'Age-Restricted'.",
        )

    def load(self, args) -> None:
        self._settings = self.parse_args(args=args).__dict__

        if not self.get_str("discord_token"):
            self.discord_token = self.DISCORD_TOKEN_ENV

        if not self._settings.get("persona"):
            self.persona = self.OOBABOT_PERSONA

        # todo: pass in config file dict
        self.sd_request_params = self._make_sd_request_params()
        self.oobabooga_request_params = self.OOBABOOGA_DEFAULT_REQUEST_PARAMS

        if self._settings.get("help"):
            helpstr = self.format_help()
            print(helpstr)

            print(
                "\n"
                + console_wrapped(
                    (
                        "Additional settings can be set in config.yml.  "
                        "Use the --generate-config option to print a new "
                        "copy of this file to STDOUT."
                    )
                )
            )

            if "" == self.discord_token:
                print(
                    "\n"
                    + console_wrapped(
                        (
                            f"Please set the '{self.DISCORD_TOKEN_ENV_VAR}' "
                            "environment variable to your bot's discord token."
                        )
                    )
                )

            sys.exit(0)

    def get_dict(self, key: str) -> typing.Dict[str, typing.Any]:
        return self.get(key)

    def get_int(self, key: str) -> int:
        return self.get(key)

    def get_str(self, key: str) -> str:
        return self.get(key)

    def get_bool(self, key: str) -> bool:
        return self.get(key)

    def get_str_list(self, key: str) -> typing.List[str]:
        return self.get(key)

    def get(self, key: str) -> typing.Any:
        if self._settings is None:
            raise ValueError("Settings not loaded")
        if key not in self._settings:
            raise ValueError(f"Setting {key} not found")
        return self._settings.get(key, "")

    DEFAULT_REQUEST_PARAMS: typing.Dict[str, typing.Union[bool, int, str]] = {
        # default values are commented out
        #
        # "do_not_save_samples": False,
        #    This is a privacy concern for the users of the service.
        #    We don't want to save the generated images anyway, since they
        #    are going to be on Discord.  Also, we don't want to use the
        #    disk space.
        "do_not_save_samples": True,
        #
        # "do_not_save_grid": False,
        #    Sames as above.
        "do_not_save_grid": True,
    }

    def _make_sd_request_params(
        self,
        config_request_params: typing.Optional[
            typing.Dict[str, typing.Union[bool, int, str]]
        ] = None,
    ) -> typing.Dict[str, typing.Union[bool, int, str]]:
        # todo: read from config file

        if self._settings is None:
            raise ValueError("Settings not loaded")

        if config_request_params is not None:
            request = {}.copy()
        else:
            request = self.DEFAULT_REQUEST_PARAMS.copy()

        for key_in_settings, key_in_request in [
            ("sd_negative_prompt", "negative_prompt"),
            ("diffusion_steps", "steps"),
            ("image_width", "width"),
            ("image_height", "height"),
            ("stable_diffusion_sampler", "sampler"),
        ]:
            if key_in_settings in self._settings:
                val = self._settings.get(key_in_settings)
                if val is None:
                    raise ValueError(f"None value for key {key_in_settings}")
                request[key_in_request] = val

        return request

    def get_argument_groups(self) -> typing.List[argparse._ArgumentGroup]:
        return self._action_groups


class SettingsConfigFile:
    START_COMMENT = textwrap.dedent(
        """
        # Welcome to Oobabot!
        #
        # This is the configuration file for Oobabot.  It is a YAML file, and
        # comments are allowed.  The file is loaded from the following
        # locations, in order:
        #
        #   1. the argument --config-yml {{filename}}
        #   2. ./config.yml
        #   3. ~/.config/oobabot/config.yml
        #   4. /etc/oobabot/config.yml
        #
        """
    )

    META_INSTRUCTION = (
        "\n\n"
        + "# " * 30
        + textwrap.dedent(
            """
        # Please save this output into ~/.config/oobabot/config.yml
        # edit it to your liking, then run the bot again.
        #
        #  e.g. oobabot --generate-config > config.yml
        #       oobabot --config-yml ./config.yml
        """
        )
    )

    OOBABOOGA_REQUEST_PARAMS_COMMENT = textwrap.dedent(
        """
        A dictionary which will be passed straight through to
        Oobabooga on every request.  Feel free to add additional
        simple parameters here as Oobabooga's API evolves.
        See Oobabooga's documentation for what these parameters
        mean.
        """
    )

    def __init__(
        self,
        cli_settings: Settings,
        template_store: templates.TemplateStore,
    ) -> None:
        if cli_settings._settings is None:
            raise ValueError("Settings have not been loaded yet.")

        yaml_map = ryaml.CommentedMap()
        yaml_map.yaml_set_start_comment(self.START_COMMENT)

        for argument_group in cli_settings.get_argument_groups():
            if argument_group.title is None:
                continue
            if argument_group.title == "options":
                continue
            if argument_group.title == "optional arguments":
                continue
            if argument_group.title == "positional arguments":
                continue
            if argument_group.title == cli_settings.DEPRECATED:
                continue

            group = self.make_yaml_from_argument_group(cli_settings, argument_group)

            group_key = argument_group.title.lower().replace(" ", "_")

            add_to_group(
                group=yaml_map,
                key=group_key,
                value=group,
                comment_lines=[DIVIDER, group_key, "."],
                indent=0,
            )

        # stable diffusion request params
        sd_request_params = cli_settings.sd_request_params.copy()
        sd_request_params["negative_prompt_nsfw"] = cli_settings.get(
            "sd_negative_prompt_nsfw"
        )

        add_to_group(
            group=yaml_map["stable_diffusion"],
            key="request_params",
            value=sd_request_params,
            comment_lines=["Request parameters for Stable Diffusion"],
            indent=INDENT_UNIT,
        )

        add_to_group(
            group=yaml_map["oobabooga"],
            key="request_params",
            value=cli_settings.oobabooga_request_params,
            comment_lines=[
                self.OOBABOOGA_REQUEST_PARAMS_COMMENT,
            ],
            indent=INDENT_UNIT,
        )

        template_group = ryaml.CommentedMap()
        for template in template_store.templates:
            add_to_group(
                group=template_group,
                key=str(template),
                value=template_store.templates[template].template,
                comment_lines=make_template_help(template_store.templates[template]),
                indent=INDENT_UNIT,
            )

        add_to_group(
            group=yaml_map,
            key="templates",
            value=template_group,
            comment_lines=["UI and AI request templates"],
            indent=0,
        )

        self._yaml_map = yaml_map

    def dump(self, out_stream: typing.IO) -> None:
        yaml = ryaml.YAML()
        yaml.default_flow_style = False
        yaml.allow_unicode = True
        yaml.indent(mapping=INDENT_UNIT, sequence=2 * INDENT_UNIT, offset=INDENT_UNIT)

        yaml.dump(self._yaml_map, out_stream)

        if sys.stdout.isatty():
            print(self.META_INSTRUCTION, file=sys.stderr)
        else:
            print("# oobabot: config.yml output successfully", file=sys.stderr)

    def make_action_comments(self, action) -> typing.List[str]:
        action_help = ""
        if action.help:
            action_help = action.help

        default_comment = ""
        if action.default:
            default_comment = f"  default: {action.default}"
        else:
            if isinstance(action.default, bool):
                default_comment = "  default: false"
            elif action.type is str:
                default_comment = "  default: ''"
            elif action.type is int:
                default_comment = "  default: 0"
        return [action_help, default_comment]

    def make_yaml_from_argument_group(
        self,
        cli_settings: Settings,
        argument_group: argparse._ArgumentGroup,
    ) -> ryaml.CommentedMap:
        if cli_settings is None:
            raise ValueError("Settings have not been loaded yet.")

        group = ryaml.CommentedMap()

        # pylint doesn't like this, can't really blame
        # it but the class doesn't seem to change much
        # pylint: disable=W0212
        for action in argument_group._group_actions:
            add_to_group(
                group=group,
                key=action.dest,
                value=cli_settings.get(action.dest),
                comment_lines=self.make_action_comments(action),
                indent=INDENT_UNIT,
            )
        # pylint: enable=W0212

        return group
