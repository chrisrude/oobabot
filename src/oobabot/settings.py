# -*- coding: utf-8 -*-
"""
Documents all the settings for the bot.  Allows for settings
to be loaded from the environment, command line and config file.

Methods:
    - load:
        loads settings from the environment, command line and config file

    - write_to_stream:
        writes the current config file to the given stream

    - write_to_file:
        writes the current config file to the given file path

Attributes:
    - setting_groups:
        a list of all the setting groups

    - discord_settings:
        a setting group for settings related to Discord

    - oobabooga_settings:
        a setting group for settings related to the oobabooga API

    - stable_diffusion_settings:
        a setting group for settings related to the stable diffusion API

    - general_settings:
        a setting group for settings that are not included in the config file
"""
import os
import shutil
import sys
import textwrap
import typing

from oobabot import templates
import oobabot.overengineered_settings_parser as oesp


def _console_wrapped(message):
    width = shutil.get_terminal_size().columns
    return "\n".join(textwrap.wrap(message, width))


def _make_template_comment(
    name: str,
    tokens_desc_tuple: typing.Tuple[typing.List[templates.TemplateToken], str, bool],
) -> typing.List[str]:
    return [
        f"Path to a file containing the {name} template.",
        tokens_desc_tuple[1],
        ".",
        f"Allowed tokens: {', '.join([str(t) for t in tokens_desc_tuple[0]])}",
        ".",
    ]


class Settings:
    """
    User=customizable settings for the bot.  Reads from
    environment variables and command line arguments.
    """

    ############################################################
    # This section is for constants which are not yet
    # customizable by the user.

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

    OOBABOOGA_DEFAULT_REQUEST_PARAMS: oesp.SettingDictType = {
        "max_new_tokens": 250,
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
        "truncation_length": 730,
        "ban_eos_token": False,
        "skip_special_tokens": True,
        "stopping_strings": [],
    }

    # set default negative prompts to make it more difficult
    # to create content against the discord TOS
    # https://discord.com/guidelines

    # use this prompt for "age_restricted" Discord channels
    #  i.e. channel.nsfw is true
    DEFAULT_SD_NEGATIVE_PROMPT_NSFW: str = "animal harm, suicide, loli"

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
        "steps": 30,
        "width": 512,
        "height": 512,
        "sampler": "",
    }
    # words to look for in the prompt to indicate that the user
    # wants to generate an image
    DEFAULT_IMAGE_WORDS: typing.List[str] = [
        "draw me",
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

    def __init__(self):
        self._settings = None

        self.arg_parser = None
        self.setting_groups: typing.List[oesp.ConfigSettingGroup] = []

        ###########################################################
        # General Settings
        #  won't be included in the config.yaml

        self.general_settings = oesp.ConfigSettingGroup(
            "General Settings", include_in_yaml=False
        )
        self.setting_groups.append(self.general_settings)

        self.general_settings.add_setting(
            oesp.ConfigSetting[bool](
                name="help",
                default=False,
                description_lines=[],
                cli_args=["-h", "--help"],
            )
        )
        # read a path to a config file from the command line
        self.general_settings.add_setting(
            oesp.ConfigSetting[str](
                name="config",
                default="config.yml",
                description_lines=[
                    "Path to a config file to read settings from.",
                    "Command line settings will override settings in this file.",
                ],
                cli_args=["-c", "--config"],
            )
        )
        self.general_settings.add_setting(
            oesp.ConfigSetting[bool](
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
        self.general_settings.add_setting(
            oesp.ConfigSetting[bool](
                name="invite_url",
                default=False,
                description_lines=[
                    textwrap.dedent(
                        """
                        Print a URL which can be used to invite the
                        bot to a Discord server.  Requires that
                        the Discord token is set.
                        """
                    ),
                ],
                cli_args=["--invite-url"],
            )
        )

        ###########################################################
        # Persona Settings

        self.persona_settings = oesp.ConfigSettingGroup("Persona")
        self.setting_groups.append(self.persona_settings)

        self.persona_settings.add_setting(
            oesp.ConfigSetting[str](
                name="ai_name",
                default="oobabot",
                description_lines=[
                    "Name the AI will use to refer to itself",
                ],
            )
        )
        self.persona_settings.add_setting(
            oesp.ConfigSetting[str](
                name="persona",
                default=os.environ.get(self.OOBABOT_PERSONA_ENV_VAR, ""),
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
                show_default_in_yaml=False,
            )
        )
        # path to a json or txt file containing persona
        self.persona_settings.add_setting(
            oesp.ConfigSetting[str](
                name="persona_file",
                default="",
                description_lines=[
                    textwrap.dedent(
                        """
                        Path to a file containing a persona.  This can be just a
                        single string, a json file in the common "tavern" formats,
                        or a yaml file in the Oobabooga format.

                        With a single string, the persona will be set to that string.

                        Otherwise, the ai_name and persona will be overwritten with
                        the values in the file.  Also, the wakewords will be
                        extended to include the character's own name.
                        """
                    )
                ],
                include_in_argparse=False,
            )
        )
        self.persona_settings.add_setting(
            oesp.ConfigSetting[typing.List[str]](
                name="wakewords",
                default=["oobabot"],
                description_lines=[
                    textwrap.dedent(
                        """
                        One or more words that the bot will listen for.
                        The bot will listen in all discord channels it can
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

        self.discord_settings = oesp.ConfigSettingGroup("Discord")
        self.setting_groups.append(self.discord_settings)

        self.discord_settings.add_setting(
            oesp.ConfigSetting[str](
                name="discord_token",
                default=os.environ.get(self.DISCORD_TOKEN_ENV_VAR, ""),
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
                show_default_in_yaml=False,
                place_default_in_yaml=True,
            )
        )
        self.discord_settings.add_setting(
            oesp.ConfigSetting[bool](
                name="dont_split_responses",
                default=False,
                description_lines=[
                    textwrap.dedent(
                        """
                        Post the entire response as a single message, rather than
                        splitting it into separate messages by sentence.
                        """
                    )
                ],
            )
        )
        self.discord_settings.add_setting(
            oesp.ConfigSetting[int](
                name="history_lines",
                default=7,
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
            oesp.ConfigSetting[bool](
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
        # log level
        self.discord_settings.add_setting(
            oesp.ConfigSetting[str](
                name="log_level",
                default="DEBUG",
                description_lines=[
                    "Set the log level.  Valid values are: ",
                    "CRITICAL, ERROR, WARNING, INFO, DEBUG",
                ],
                include_in_argparse=False,
            )
        )
        self.discord_settings.add_setting(
            oesp.ConfigSetting[bool](
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
            oesp.ConfigSetting[typing.List[str]](
                name="stop_markers",
                default=[
                    "### End of Transcript ###<|endoftext|>",
                    "<|endoftext|>",
                ],
                description_lines=[
                    textwrap.dedent(
                        """
                        A list of strings that will cause the bot to stop
                        generating a response when encountered.
                        """
                    )
                ],
                include_in_argparse=False,
            )
        )
        self.discord_settings.add_setting(
            oesp.ConfigSetting[bool](
                name="stream_responses",
                default=False,
                description_lines=[
                    textwrap.dedent(
                        """
                        FEATURE PREVIEW: Stream responses into a single message
                        as they are generated.
                        Note: may be janky
                        """
                    )
                ],
            )
        )

        ###########################################################
        # Oobabooga Settings

        self.oobabooga_settings = oesp.ConfigSettingGroup("Oobabooga")
        self.setting_groups.append(self.oobabooga_settings)

        self.oobabooga_settings.add_setting(
            oesp.ConfigSetting[str](
                name="base_url",
                default="ws://localhost:5005",
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
            oesp.ConfigSetting[bool](
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
        # get a regex for filtering a message
        self.oobabooga_settings.add_setting(
            oesp.ConfigSetting[str](
                name="message_regex",
                default="",
                description_lines=[
                    textwrap.dedent(
                        """
                        A regex that will be used to extract message lines
                        from the AI's output.  The first capture group will
                        be used as the message.  If this is not set, the
                        entire output will be used as the message.
                        """
                    )
                ],
            )
        )
        self.oobabooga_settings.add_setting(
            oesp.ConfigSetting[oesp.SettingDictType](
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
                place_default_in_yaml=True,
            )
        )

        ###########################################################
        # Stable Diffusion Settings

        self.stable_diffusion_settings = oesp.ConfigSettingGroup("Stable Diffusion")
        self.setting_groups.append(self.stable_diffusion_settings)

        self.stable_diffusion_settings.add_setting(
            oesp.ConfigSetting[typing.List[str]](
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
            oesp.ConfigSetting[str](
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
            oesp.ConfigSetting[str](
                name="extra_prompt_text",
                default="",
                description_lines=[
                    textwrap.dedent(
                        """
                        This will be appended to every image generation prompt
                        sent to Stable Diffusion.
                        """
                    )
                ],
            )
        )
        self.stable_diffusion_settings.add_setting(
            oesp.ConfigSetting[oesp.SettingDictType](
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
                place_default_in_yaml=True,
            )
        )
        self.stable_diffusion_settings.add_setting(
            oesp.ConfigSetting[bool](
                name="use_ai_generated_keywords",
                default=False,
                description_lines=[
                    textwrap.dedent(
                        """
                        FEATURE PREVIEW: If set, the bot will ask Oobabooga to generate
                        image keywords from a user's message.  It will then pass the
                        keywords that Oobabooga produces to Stable Diffusion to finally
                        generate an image.
                        Otherwise, the bot will simply extract keywords directly
                        from the user's message using a simple regex.
                        """
                    )
                ],
            )
        )

        ###########################################################
        # Template Settings

        self.template_settings = oesp.ConfigSettingGroup(
            "Template",
            description="UI and AI request templates",
            include_in_argparse=False,
        )
        self.setting_groups.append(self.template_settings)

        for template, tokens_desc_tuple in templates.TemplateStore.TEMPLATES.items():
            _, _, is_ai_prompt = tokens_desc_tuple

            self.template_settings.add_setting(
                oesp.ConfigSetting[str](
                    name=str(template),
                    default=templates.TemplateStore.DEFAULT_TEMPLATES[template],
                    description_lines=_make_template_comment(
                        str(template), tokens_desc_tuple
                    ),
                    include_in_yaml=is_ai_prompt,
                )
            )

        self._add_deprecated_settings()

    def _add_deprecated_settings(self) -> None:
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

        def set_sd_parm(param: str, value: oesp.SettingValueType):
            if not value:
                return
            setting = self.stable_diffusion_settings.get_setting("request_params")

            # get returns a copy of the settings dict, so we need to
            # push it back after we make a change
            setting_dict = setting.get()
            setting_dict[param] = value
            setting.set_value(setting_dict)

        self.deprecated_settings = oesp.ConfigSettingGroup(
            "Deprecated Settings",
            include_in_yaml=False,
            description="These settings are deprecated and will be removed in "
            + "a future release.  Please set them with config.yml instead.",
        )
        self.setting_groups.append(self.deprecated_settings)

        self.deprecated_settings.add_setting(
            oesp.ConfigSetting[int](
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
            oesp.ConfigSetting[int](
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
            oesp.ConfigSetting[int](
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
            oesp.ConfigSetting[str](
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
            oesp.ConfigSetting[str](
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
            oesp.ConfigSetting[str](
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

    def write_to_stream(self, out_stream) -> None:
        oesp.write_to_stream(self.setting_groups, out_stream)
        if sys.stdout.isatty():
            print(self.META_INSTRUCTION, file=sys.stderr)
        else:
            print("# oobabot: config.yml output successfully", file=sys.stderr)

    def write_to_file(self, filename: str) -> None:
        oesp.write_to_file(self.setting_groups, filename)

    def _filename_from_args(self, args: typing.List[str]) -> str:
        """
        Get the configuration filename from the command line arguments.
        If none is supplied, return the default.
        """

        # we need to hack this in here because we want to know the filename
        # before we parse the args, so that we can load the config file
        # first and then have the arguments overwrite the config file.
        config_setting = self.general_settings.get_setting("config")
        if args is not None:
            for config_flag in config_setting.cli_args:
                # find the element after config_flag in args
                try:
                    return args[args.index(config_flag) + 1]
                except (ValueError, IndexError):
                    continue
        return config_setting.default

    def load(
        self,
        cli_args: typing.List[str],
        config_file: typing.Optional[str] = None,
    ) -> None:
        """
        Load the config from the command line arguments and config file.

        params:
            cli_args: list of command line arguments to parse
            config_file: path to the config file to load

        cli_args is intended to be used when running from a standalone
        application, while config_file is intended to be used when
        running from inside another process.
        """

        if config_file is None:
            config_file = self._filename_from_args(cli_args)

        self.arg_parser = oesp.load(
            cli_args=cli_args,
            setting_groups=self.setting_groups,
            config_file=config_file,
        )

    def print_help(self):
        """
        Prints CLI usage information to STDOUT.
        """
        if self.arg_parser is None:
            raise ValueError("display_help called before load")

        help_str = self.arg_parser.format_help()
        print(help_str)

        print(
            "\n"
            + _console_wrapped(
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
                + _console_wrapped(
                    (
                        f"Please set the '{self.DISCORD_TOKEN_ENV_VAR}' "
                        "environment variable to your bot's discord token."
                    )
                )
            )
