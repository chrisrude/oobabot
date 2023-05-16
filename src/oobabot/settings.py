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


YAML_WIDTH = 88
DIVIDER = "# " * (YAML_WIDTH >> 1)
INDENT_UNIT = 2

SettingDictType = typing.Dict[
    str, typing.Union[bool, int, float, str, typing.List[str]]
]

SettingValueType = typing.Union[
    bool, int, float, str, typing.List[str], SettingDictType
]


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
    name: str,
    tokens_desc_tuple: typing.Tuple[typing.List[templates.TemplateToken], str],
) -> typing.List[str]:
    return [
        f"Path to a file containing the {name} template.",
        tokens_desc_tuple[1],
        ".",
        f"Allowed tokens: {', '.join([str(t) for t in tokens_desc_tuple[0]])}",
        ".",
    ]


T = typing.TypeVar("T", bound="SettingValueType")


class ConfigSetting(typing.Generic[T]):
    data_type: T
    description_lines: typing.List[str]
    cli_args: typing.List[str]
    include_in_argparse: bool
    include_in_yaml: bool
    show_default_in_yaml: bool
    fn_on_set: typing.Callable[[T], None]

    def __init__(
        self,
        name: str,
        default: T,
        description_lines: typing.List[str],
        cli_args: typing.Optional[typing.List[str]] = None,
        include_in_argparse: bool = True,
        include_in_yaml: bool = True,
        show_default_in_yaml: bool = True,
        fn_on_set: typing.Callable[[T], None] = lambda x: None,
    ):
        self.name = name
        self.default = default
        self.description_lines = [x.strip() for x in description_lines]
        if cli_args is None:
            cli_args = ["--" + name.replace("_", "-")]
        self.cli_args = cli_args
        self.value = default
        self.include_in_argparse = include_in_argparse
        self.include_in_yaml = include_in_yaml
        self.show_default_in_yaml = show_default_in_yaml
        self.fn_on_set = fn_on_set

    def add_to_argparse(self, parser: argparse._ArgumentGroup):
        if not self.include_in_argparse:
            return

        kwargs = {
            "default": self.value,
            "help": " ".join(self.description_lines),
        }

        # note: the other way to do this is with
        #   typing.get_args(self.__orig_class__)[0]
        # but that isn't officially supported, so
        # let's do it the jankier way
        if isinstance(self.default, str):
            kwargs["type"] = str
        elif isinstance(self.default, bool):
            kwargs["action"] = "store_true"
            if self.default:
                kwargs["action"] = "store_false"
        elif isinstance(self.default, int):
            kwargs["type"] = int
        elif isinstance(self.default, float):
            kwargs["type"] = float
        elif isinstance(self.default, list):
            kwargs["type"] = str
            kwargs["nargs"] = "*"

        parser.add_argument(*self.cli_args, **kwargs)

    def set_value_from_argparse(self, args: argparse.Namespace) -> None:
        if not self.include_in_argparse:
            return
        if not hasattr(args, self.name):
            raise ValueError(f"Namespace does not have attribute {self.name}")
        self.set_value(getattr(args, self.name))

    def add_to_yaml_group(self, group: ryaml.CommentedMap):
        if not self.include_in_yaml:
            return
        add_to_group(
            group,
            key=self.name,
            value=self.value,
            comment_lines=self.make_yaml_comment(),
            indent=INDENT_UNIT,
        )

    def make_yaml_comment(self) -> typing.List[str]:
        comment_lines = self.description_lines.copy()

        if self.show_default_in_yaml:
            if self.default is not None:
                comment_lines.append(f"  default: {str(self.default).lower()}")
            else:
                comment_lines.append("  default: None")
        return comment_lines

    def set_value_from_yaml(self, yaml: ryaml.CommentedMap) -> None:
        if not self.include_in_yaml:
            return
        if self.name not in yaml:
            return
        self.set_value(yaml[self.name])

    def set_value(self, value: T) -> None:
        self.value = value
        self.fn_on_set(value)

    def get(self) -> T:
        if isinstance(self.value, dict):
            return self.value.copy()
        return self.value


class ConfigSettingGroup:
    name: str
    description: str
    settings: typing.Dict[str, ConfigSetting]

    def __init__(
        self,
        name: str,
        description: str = "",
        include_in_argparse: bool = True,
        include_in_yaml: bool = True,
    ):
        self.name = name
        self.description = description
        self.settings = {}
        self.include_in_argparse = include_in_argparse
        self.include_in_yaml = include_in_yaml

    def add_setting(self, setting: "ConfigSetting") -> None:
        self.settings[setting.name] = setting

    def add_to_argparse(self, parser: argparse.ArgumentParser):
        if not self.include_in_argparse:
            return
        arg_group = parser.add_argument_group(self.name, self.description)
        for setting in self.settings.values():
            setting.add_to_argparse(arg_group)

    def set_values_from_argparse(self, args: argparse.Namespace) -> None:
        if not self.include_in_argparse:
            return
        for setting in self.settings.values():
            setting.set_value_from_argparse(args)

    def add_to_yaml(self, yaml: ryaml.CommentedMap):
        if not self.include_in_yaml:
            return
        group_key = self.name.lower().replace(" ", "_")

        group = ryaml.CommentedMap()
        group.yaml_set_start_comment(f"{DIVIDER}\n# {self.name}\n{DIVIDER}\n")
        for setting in self.settings.values():
            setting.add_to_yaml_group(group)

        add_to_group(
            group=yaml,
            key=group_key,
            value=group,
            comment_lines=[DIVIDER, group_key, "."],
            indent=0,
        )

    def set_values_from_yaml(self, yaml: dict):
        if not self.include_in_yaml:
            return
        if yaml is None:
            return
        group_key = self.name.lower().replace(" ", "_")
        if group_key not in yaml:
            return
        group = yaml[group_key]
        for setting in self.settings.values():
            setting.set_value_from_yaml(group)

    def get_setting(self, name: str) -> ConfigSetting:
        return self.settings[name]

    def get(self, name: str) -> SettingValueType:
        return self.settings[name].value

    def get_str(self, name: str) -> str:
        return self.settings[name].value

    def get_list(self, name: str) -> typing.List[SettingValueType]:
        return self.settings[name].value

    def get_all(self) -> typing.Dict[str, SettingValueType]:
        return {name: setting.get() for (name, setting) in self.settings.items()}.copy()


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

    OOBABOOGA_DEFAULT_REQUEST_PARAMS: SettingDictType = {
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

    # square image, 512x512
    DEFAULT_STABLE_DIFFUSION_IMAGE_SIZE: int = 512

    # 30 steps of diffusion
    DEFAULT_STABLE_DIFFUSION_STEPS: int = 30
    # set default negative prompts to make it more difficult
    # to create content against the discord TOS
    # https://discord.com/guidelines

    # use this prompt for "age_restricted" Discord channels
    #  i.e. channel.nsfw is true
    DEFAULT_SD_NEGATIVE_PROMPT_NSFW: str = "animal harm, suicide, loli"

    # no default, just use what Stable Diffusion has on tap
    DEFAULT_STABLE_DIFFUSION_SAMPLER = ""

    # use this prompt for non-age-restricted channels
    DEFAULT_SD_NEGATIVE_PROMPT: str = DEFAULT_SD_NEGATIVE_PROMPT_NSFW + ", nsfw"

    DEFAULT_SD_REQUEST_PARAMS: typing.Dict[str, typing.Union[bool, int, str]] = {
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
        "negative_prompt": DEFAULT_SD_NEGATIVE_PROMPT,
        "negative_prompt_nsfw": DEFAULT_SD_NEGATIVE_PROMPT_NSFW,
        "steps": DEFAULT_STABLE_DIFFUSION_STEPS,
        "width": DEFAULT_STABLE_DIFFUSION_IMAGE_SIZE,
        "height": DEFAULT_STABLE_DIFFUSION_IMAGE_SIZE,
        "sampler": DEFAULT_STABLE_DIFFUSION_SAMPLER,
    }
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

    # ENVIRONMENT VARIABLES ####

    DISCORD_TOKEN_ENV_VAR: str = "DISCORD_TOKEN"

    OOBABOT_PERSONA_ENV_VAR: str = "OOBABOT_PERSONA"

    DEFAULT_WAKEWORDS: typing.List[str] = ["oobabot"]
    DEFAULT_URL: str = "ws://localhost:5005"

    DEPRECATED: str = "Deprecated"

    def __init__(self):
        self._settings = None

        super().__init__(
            description=f"oobabot v{oobabot.__version__}: Discord bot for "
            + "oobabooga's text-generation-webui",
            formatter_class=argparse.ArgumentDefaultsHelpFormatter,
            add_help=False,
        )
        self.setting_groups: typing.List[ConfigSettingGroup] = []

        ###########################################################
        # General Settings
        #  won't be included in the config.yaml

        self.general_settings = ConfigSettingGroup(
            "General Settings", include_in_yaml=False
        )
        self.setting_groups.append(self.general_settings)

        self.general_settings.add_setting(
            ConfigSetting[bool](
                name="help",
                default=False,
                description_lines=[],
                cli_args=["-h", "--help"],
            )
        )
        self.general_settings.add_setting(
            ConfigSetting[bool](
                name="generate_config",
                default=False,
                description_lines=[
                    textwrap.dedent(
                        """
                        If set, oobabot will print its configuration as a .yml file,
                        then exit.  Any command-line settings also passed will be
                        reflected in this file.
                        """
                    )
                ],
            )
        )

        ###########################################################
        # Persona Settings

        self.persona_settings = ConfigSettingGroup("Persona")
        self.setting_groups.append(self.persona_settings)

        self.persona_settings.add_setting(
            ConfigSetting[str](
                name="ai_name",
                default="oobabot",
                description_lines=[
                    "Name the AI will use to refer to itself",
                ],
            )
        )
        self.persona_settings.add_setting(
            ConfigSetting[str](
                name="persona",
                default="",
                description_lines=[
                    textwrap.dedent(
                        f"""
                        This prefix will be added in front of every user-supplied
                        request.  This is useful for setting up a 'character' for the
                        bot to play.  Alternatively, this can be set with the
                        {self.OOBABOT_PERSONA_ENV_VAR} environment variable.
                        """
                    )
                ],
            )
        )
        self.persona_settings.add_setting(
            ConfigSetting[str](
                name="prompt",
                default="",
                description_lines=[
                    textwrap.dedent(
                        """
                        This prompt will be added to the beginning of every
                        user-supplied request.  This is useful for setting up
                        a 'character' for the bot to play.
                        """
                    )
                ],
            )
        )
        self.persona_settings.add_setting(
            ConfigSetting[typing.List[str]](
                name="wakewords",
                default=self.DEFAULT_WAKEWORDS,
                description_lines=[
                    textwrap.dedent(
                        """
                        One or more words that the bot will listen for.
                        The bot will listen in all discord channels can
                        access for one of these words to be mentioned, then reply
                        to any messages it sees with a matching word.
                        The bot will always reply to @-mentions and
                        direct messages, even if no wakewords are supplied.
                        """
                    )
                ],
            )
        )

        ###########################################################
        # Discord Settings

        self.discord_settings = ConfigSettingGroup("Discord")
        self.setting_groups.append(self.discord_settings)

        self.discord_settings.add_setting(
            ConfigSetting[str](
                name="discord_token",
                default="",
                description_lines=[
                    textwrap.dedent(
                        f"""
                        Token to log into Discord with.  For security purposes
                        it's strongly recommended that you set this via the
                        {self.DISCORD_TOKEN_ENV_VAR} environment variable
                        instead, if possible.
                        """
                    )
                ],
                cli_args=["--discord-token"],
            )
        )
        self.discord_settings.add_setting(
            ConfigSetting[bool](
                name="dont_split_responses",
                default=False,
                description_lines=[
                    textwrap.dedent(
                        """
                        Post the entire response as a single message, rather than
                        splitting it into seperate messages by sentence.
                        """
                    )
                ],
            )
        )
        self.discord_settings.add_setting(
            ConfigSetting[int](
                name="history_lines",
                default=self.DEFAULT_HISTORY_LINES_TO_SUPPLY,
                description_lines=[
                    textwrap.dedent(
                        """
                        Number of lines of chat history the AI will see
                        when generating a response.
                        """
                    )
                ],
            )
        )
        self.discord_settings.add_setting(
            ConfigSetting[bool](
                name="ignore_dms",
                default=False,
                description_lines=[
                    textwrap.dedent(
                        """
                        If set, the bot will not respond to direct messages.
                        """
                    )
                ],
            )
        )
        self.discord_settings.add_setting(
            ConfigSetting[bool](
                name="reply_in_thread",
                default=False,
                description_lines=[
                    textwrap.dedent(
                        """
                        If set, the bot will generate a thread to respond in
                        if it is not already in one.
                        """
                    )
                ],
            )
        )
        self.discord_settings.add_setting(
            ConfigSetting[bool](
                name="stream_responses",
                default=False,
                description_lines=[
                    textwrap.dedent(
                        """
                        Stream responses into a single message as they are generated.
                        """
                    )
                ],
            )
        )

        ###########################################################
        # Oobabooga Settings

        self.oobabooga_settings = ConfigSettingGroup("Oobabooga")
        self.setting_groups.append(self.oobabooga_settings)

        self.oobabooga_settings.add_setting(
            ConfigSetting[str](
                name="base_url",
                default=self.DEFAULT_URL,
                description_lines=[
                    textwrap.dedent(
                        """
                        Base URL for the oobabooga instance.  This should be
                        ws://hostname[:port] for plain websocket connections,
                        or wss://hostname[:port] for websocket connections over TLS.
                        """
                    )
                ],
            )
        )
        self.oobabooga_settings.add_setting(
            ConfigSetting[bool](
                name="log_all_the_things",
                default=False,
                description_lines=[
                    textwrap.dedent(
                        """
                        Print all AI input and output to STDOUT.
                        """
                    )
                ],
            )
        )
        self.oobabooga_settings.add_setting(
            ConfigSetting[SettingDictType](
                name="request_params",
                default=self.OOBABOOGA_DEFAULT_REQUEST_PARAMS,
                description_lines=[
                    textwrap.dedent(
                        """
                        A dictionary which will be passed straight through to
                        Oobabooga on every request.  Feel free to add additional
                        simple parameters here as Oobabooga's API evolves.
                        See Oobabooga's documentation for what these parameters
                        mean.
                        """
                    )
                ],
                include_in_argparse=False,
                show_default_in_yaml=False,
            )
        )

        ###########################################################
        # Stable Diffusion Settings

        self.stable_diffusion_settings = ConfigSettingGroup("Stable Diffusion")
        self.setting_groups.append(self.stable_diffusion_settings)

        self.stable_diffusion_settings.add_setting(
            ConfigSetting[typing.List[str]](
                name="image_words",
                default=self.DEFAULT_IMAGE_WORDS,
                description_lines=[
                    textwrap.dedent(
                        """
                        When one of these words is used in a message, the bot will
                        generate an image.
                        """
                    )
                ],
            )
        )
        self.stable_diffusion_settings.add_setting(
            ConfigSetting[str](
                name="stable_diffusion_url",
                default="",
                description_lines=[
                    textwrap.dedent(
                        """
                        URL for an AUTOMATIC1111 Stable Diffusion server.
                        """
                    )
                ],
            )
        )
        self.stable_diffusion_settings.add_setting(
            ConfigSetting[SettingDictType](
                name="request_params",
                default=self.DEFAULT_SD_REQUEST_PARAMS,
                description_lines=[
                    textwrap.dedent(
                        """
                        A dictionary which will be passed straight through to
                        Stable Diffusion on every request.  Feel free to add additional
                        simple parameters here as Stable Diffusion's API evolves.
                        See Stable Diffusion's documentation for what these parameters
                        mean.
                        """
                    )
                ],
                include_in_argparse=False,
                show_default_in_yaml=False,
            )
        )

        ###
        # Template Settings

        self.template_settings = ConfigSettingGroup(
            "Template",
            description="UI and AI request templates",
            include_in_argparse=False,
        )
        self.setting_groups.append(self.template_settings)

        for template, tokens_desc_tuple in templates.TemplateStore.TEMPLATES.items():
            self.template_settings.add_setting(
                ConfigSetting[str](
                    name=str(template),
                    default=templates.TemplateStore.DEFAULT_TEMPLATES[template],
                    description_lines=make_template_help(
                        str(template), tokens_desc_tuple
                    ),
                    show_default_in_yaml=False,
                )
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

        def set_sd_parm(param: str, value: SettingValueType):
            if not value:
                return
            self.stable_diffusion_settings.get_setting("request_params").get()[
                param
            ] = value

        self.deprecated_settings = ConfigSettingGroup(
            self.DEPRECATED,
            include_in_yaml=False,
            description="These settings are deprecated and will be removed in "
            + "a future release.  Please set them with config.yml instead.",
        )
        self.setting_groups.append(self.deprecated_settings)

        self.deprecated_settings.add_setting(
            ConfigSetting[int](
                name="diffusion_steps",
                default=0,
                description_lines=[
                    textwrap.dedent(
                        """
                        Number of diffusion steps to take when generating an image.
                        """
                    )
                ],
                fn_on_set=lambda x: set_sd_parm("steps", int(x)),
            )
        )
        self.deprecated_settings.add_setting(
            ConfigSetting[int](
                name="image_height",
                default=0,
                description_lines=[
                    textwrap.dedent(
                        """
                        Size of images to generate.  This is the height of the image
                        in pixels.
                        """
                    )
                ],
                fn_on_set=lambda x: set_sd_parm("height", int(x)),
            )
        )
        self.deprecated_settings.add_setting(
            ConfigSetting[int](
                name="image_width",
                default=0,
                description_lines=[
                    textwrap.dedent(
                        """
                        Size of images to generate.  This is the width of the image
                        in pixels.
                        """
                    )
                ],
                fn_on_set=lambda x: set_sd_parm("width", int(x)),
            )
        )
        self.deprecated_settings.add_setting(
            ConfigSetting[str](
                name="stable_diffusion_sampler",
                default="",
                description_lines=[
                    textwrap.dedent(
                        """
                        Sampler to use when generating images.  If not specified,
                        the one set on the AUTOMATIC1111 server will be used.
                        """
                    )
                ],
                cli_args=["--stable-diffusion-sampler", "--sd-sampler"],
                fn_on_set=lambda x: set_sd_parm("sampler", str(x)),
            )
        )
        self.deprecated_settings.add_setting(
            ConfigSetting[str](
                name="sd_negative_prompt",
                default="",
                description_lines=[
                    textwrap.dedent(
                        """
                        Negative prompt to use when generating images.  This will
                        discourage Stable Diffusion from generating images with the
                        specified content.  By default, this is set to follow
                        Discord's TOS.
                        """
                    )
                ],
                fn_on_set=lambda x: set_sd_parm("negative_prompt", str(x)),
            )
        )
        self.deprecated_settings.add_setting(
            ConfigSetting[str](
                name="sd_negative_prompt_nsfw",
                default="",
                description_lines=[
                    textwrap.dedent(
                        """
                        Negative prompt to use when generating images in a channel
                        marked as 'Age-Restricted'.
                        """
                    )
                ],
                fn_on_set=lambda x: set_sd_parm("negative_prompt_nsfw", str(x)),
            )
        )

    def _load_yaml_settings(self) -> dict:
        # todo: read from additional sources
        filename = "config.yml"
        try:
            with open(filename, "r", encoding="utf-8") as f:
                yaml = ryaml.YAML(typ="rt")  # todo: use "safe"?
                return yaml.load(f)
        except FileNotFoundError:
            print(f"Could not find {filename}.  Using defaults.")
            return {}

    def load(self, args) -> None:
        # Load settings in this order.
        # The later sources will overwrite the earlier ones.
        #
        #  1. config.yml
        #  2. command line arguments
        #  3. environment variables
        #
        self._yml_settings = self._load_yaml_settings()
        for group in self.setting_groups:
            group.set_values_from_yaml(self._yml_settings)

        # we need to initialize argparse AFTER we read from
        # the yaml file, so that the argparse defaults are
        # set to the yaml-read values.
        for group in self.setting_groups:
            group.add_to_argparse(self)

        self._cli_settings = self.parse_args(args=args)

        for group in self.setting_groups:
            group.set_values_from_argparse(self._cli_settings)

        discord_token_env = os.environ.get(self.DISCORD_TOKEN_ENV_VAR, None)
        if discord_token_env:
            self.discord_settings.get_setting("discord_token").set_value(
                discord_token_env
            )

        persona_env = os.environ.get(self.OOBABOT_PERSONA_ENV_VAR, None)
        if persona_env:
            self.persona_settings.get_setting("persona").set_value(persona_env)

        if self._cli_settings.help:
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

            if "" == self.discord_settings.get("discord_token"):
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

    START_COMMENT = textwrap.dedent(
        """
        # Welcome to Oobabot!
        #
        # This is the configuration file for Oobabot.  It is a YAML file, and
        # comments are allowed.  Oobabot attempts to load a file named
        # "config.yml" from the current directory when it is run.
        #
        """
    )

    META_INSTRUCTION = (
        "\n\n"
        + "# " * 30
        + textwrap.dedent(
            """
            # Please save this output into ./config.yml
            # edit it to your liking, then run the bot again.
            #
            #  e.g. oobabot --generate-config > config.yml
            #       oobabot
            """
        )
    )

    def write_sample_config(self, out_stream: typing.TextIO) -> None:
        if self._cli_settings is None:
            raise ValueError("Settings have not been loaded yet.")

        yaml_map = ryaml.CommentedMap()
        yaml_map.yaml_set_start_comment(self.START_COMMENT)

        add_to_group(
            group=yaml_map,
            key="version",
            value=oobabot.__version__,
            comment_lines=[],
            indent=0,
        )

        for group in self.setting_groups:
            group.add_to_yaml(yaml_map)

        yaml = ryaml.YAML()
        yaml.default_flow_style = False
        yaml.allow_unicode = True
        yaml.indent(mapping=INDENT_UNIT, sequence=2 * INDENT_UNIT, offset=INDENT_UNIT)

        yaml.dump(yaml_map, out_stream)

        if sys.stdout.isatty():
            print(self.META_INSTRUCTION, file=sys.stderr)
        else:
            print("# oobabot: config.yml output successfully", file=sys.stderr)
