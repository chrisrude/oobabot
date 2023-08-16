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
import textwrap
import typing

from oobabot import templates
import oobabot.overengineered_settings_parser as oesp


class SettingsError(Exception):
    """
    Base class for exceptions in this module.
    """

    def __init__(self, message: str, cause: Exception):
        self.message = message
        super().__init__(message, cause)


def _console_wrapped(message):
    width = shutil.get_terminal_size().columns
    return "\n".join(textwrap.wrap(message, width))


def _make_template_comment(
    tokens_desc_tuple: typing.Tuple[typing.List[templates.TemplateToken], str, bool],
) -> typing.List[str]:
    return [
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
        "epsilon_cutoff": 0,  # In units of 1e-4
        "eta_cutoff": 0,  # In units of 1e-4
        "tfs": 1,
        "top_a": 0,
        "repetition_penalty": 1.18,
        "top_k": 40,
        "min_length": 0,
        "no_repeat_ngram_size": 0,
        "num_beams": 1,
        "penalty_alpha": 0,
        "length_penalty": 1,
        "early_stopping": False,
        "mirostat_mode": 0,
        "mirostat_tau": 5,
        "mirostat_eta": 0.1,
        "seed": -1,
        "add_bos_token": True,
        "truncation_length": 2048,
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

    SD_CLIENT_MAGIC_MODEL_KEY = "model"

    DEFAULT_SD_REQUEST_PARAMS: oesp.SettingDictType = {
        "cfg_scale": 7,
        #    This is a privacy concern for the users of the service.
        #    We don't want to save the generated images anyway, since they
        #    are going to be on Discord.  Also, we don't want to use the
        #    disk space.
        "do_not_save_samples": True,
        "do_not_save_grid": True,
        "enable_hr": False,
        # this is a fake setting, SD calls it "sd_model_checkpoint",
        # and it needs to appear under "override_params".  But put it here
        # for convenience, the SD client will do the right thing with it.
        SD_CLIENT_MAGIC_MODEL_KEY: "",
        "negative_prompt": DEFAULT_SD_NEGATIVE_PROMPT,
        "negative_prompt_nsfw": DEFAULT_SD_NEGATIVE_PROMPT_NSFW,
        "sampler_name": "",
        "seed": -1,
        "steps": 30,
        "width": 512,
        "height": 512,
    }

    DEFAULT_SD_USER_OVERRIDE_PARAMS = [
        "cfg_scale",
        "enable_hr",
        SD_CLIENT_MAGIC_MODEL_KEY,
        "negative_prompt",
        "sampler_name",
        "seed",
        "height",
        "width",
    ]

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
            oesp.ConfigSetting[int](
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
        self.discord_settings.add_setting(
            oesp.ConfigSetting[float](
                name="stream_responses_speed_limit",
                default=0.7,
                description_lines=[
                    textwrap.dedent(
                        """
                        FEATURE PREVIEW: When streaming responses, cap the
                        rate at which we send updates to Discord to be no
                        more than once per this many seconds.

                        This does not guarantee that updates will be sent
                        this fast.  Only that they will not be sent any
                        faster than this rate.

                        This is useful because Discord has a rate limit on
                        how often you can send messages, and if you exceed
                        it, the updates will suddenly become slow.

                        Example: 0.2 means we will send updates no faster
                        than 5 times per second.
                        """
                    )
                ],
                include_in_argparse=False,
            )
        )
        self.discord_settings.add_setting(
            oesp.ConfigSetting[int](
                name="unsolicited_channel_cap",
                default=3,
                description_lines=[
                    textwrap.dedent(
                        """
                        Adds a limit to the number of channels the bot will post
                        unsolicited messages in at the same time.  This is to
                        prevent the bot from being too noisy in large servers.

                        When set, only the most recent N channels the bot has
                        been summoned in will have a chance of receiving an
                        unsolicited message.  The bot will still respond to
                        @-mentions and wake words in any channel it can access.

                        Set to 0 to disable this feature.
                        """
                    )
                ],
                include_in_argparse=False,
            )
        )
        self.discord_settings.add_setting(
            oesp.ConfigSetting[bool](
                name="disable_unsolicited_replies",
                default=False,
                description_lines=[
                    textwrap.dedent(
                        """
                        If set, the bot will not reply to any messages that
                        do not @-mention it or include a wakeword.

                        If unsolicited replies are disabled, the unsolicited_channel_cap
                        setting will have no effect.
                        """
                    )
                ],
                include_in_argparse=False,
            )
        )
        self.discord_settings.add_setting(
            oesp.ConfigSetting[str](
                name="discrivener_location",
                default="",
                description_lines=[
                    textwrap.dedent(
                        """
                        FEATURE PREVIEW: Path to the Discrivener executable.
                        Will enable prototype voice integration.
                        """
                    )
                ],
                include_in_argparse=False,
            )
        )

        self.discord_settings.add_setting(
            oesp.ConfigSetting[str](
                name="discrivener_model_location",
                default="",
                description_lines=[
                    textwrap.dedent(
                        """
                        FEATURE PREVIEW: Path to the Discrivener model to
                        load.  Required if discrivener_location is set.
                        """
                    )
                ],
                include_in_argparse=False,
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
        self.oobabooga_settings.add_setting(
            oesp.ConfigSetting[bool](
                name="plugin_auto_start",
                default=False,
                description_lines=[
                    textwrap.dedent(
                        """
                        When running inside the Oobabooga plugin, automatically
                        connect to Discord when Oobabooga starts.  This has no effect
                        when running from the command line.
                        """
                    )
                ],
                include_in_argparse=False,
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
            oesp.ConfigSetting[list](
                name="user_override_params",
                default=self.DEFAULT_SD_USER_OVERRIDE_PARAMS,
                description_lines=[
                    textwrap.dedent(
                        """
                        These parameters can be overridden by the Discord user
                        by including them in their image generation request.

                        The format for this is: param_name=value

                        This is a whitelist of parameters that can be overridden.
                        They must be simple parameters (strings, numbers, booleans),
                        and they must be in the request_params dictionary.

                        The value the user inputs will be checked against the type
                        from the request_params dictionary, and if it doesn't match,
                        the default value will be used instead.

                        Otherwise, this value will be passed through to Stable
                        Diffusion without any changes, so be mindful of what you allow
                        here.  It could potentially be used to inject malicious
                        values into your SD server.

                        For example, steps=1000000 could be bad for your server.
                        """
                    )
                ],
                include_in_argparse=False,
                show_default_in_yaml=False,
                place_default_in_yaml=True,
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
                    description_lines=_make_template_comment(tokens_desc_tuple),
                    include_in_yaml=is_ai_prompt,
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

    def write_to_file(self, filename: str) -> None:
        oesp.write_to_file(self.setting_groups, filename)

    def _filename_from_args(self, args: typing.List[str]) -> typing.Tuple[str, bool]:
        """
        Get the configuration filename from the command line arguments.
        If none is supplied, return the default.

        Returns a tuple with the file to open, and True if it came
        from the default, rather than a CLI argument.
        """

        # we need to hack this in here because we want to know the filename
        # before we parse the args, so that we can load the config file
        # first and then have the arguments overwrite the config file.
        config_setting = self.general_settings.get_setting("config")
        if args is not None:
            for config_flag in config_setting.cli_args:
                # find the element after config_flag in args
                try:
                    return (args[args.index(config_flag) + 1], False)
                except (ValueError, IndexError):
                    continue
        return (config_setting.default, True)

    def load_from_yaml_stream(self, stream: typing.TextIO) -> typing.Optional[str]:
        """
        Load the config from a YAML stream.

        params:
            stream: stream to load the config from

        returns:
            None if the config was loaded successfully, otherwise a string
            containing an error message.
        """
        return oesp.load_from_yaml_stream(stream, setting_groups=self.setting_groups)

    def load(
        self,
        cli_args: typing.List[str],
        config_file: typing.Optional[str] = None,
        running_from_cli: bool = False,
    ) -> None:
        """
        Load the config from the command line arguments and config file.

        params:
            cli_args: list of command line arguments to parse
            config_file: path to the config file to load

        cli_args is intended to be used when running from a standalone
        application, while config_file is intended to be used when
        running from inside another process.

        raises SettingsError if a specific configuration file
        was requested (either by the config_file argument or the CLI),
        but it could not be found.
        """

        is_default = False
        if config_file is None:
            config_file, is_default = self._filename_from_args(cli_args)
        raise_if_file_missing = not is_default and running_from_cli

        try:
            self.arg_parser = oesp.load(
                cli_args=cli_args,
                setting_groups=self.setting_groups,
                config_file=config_file,
                raise_if_file_missing=raise_if_file_missing,
            )
        except oesp.ConfigFileMissingError as err:
            # get full path to config_file
            config_file = os.path.abspath(config_file)
            msg = f"Could not load config file at: {config_file}"
            raise SettingsError(msg, err) from err

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
