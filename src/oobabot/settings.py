import argparse
import os
import textwrap
import typing

import aiohttp

from oobabot.fancy_logging import get_logger


class TemplateMessageFormatter:
    # Purpose: format messages using a template string

    def __init__(
        self, template_name: str, template: str, allowed_tokens: typing.List[str]
    ):
        self._validate_format_string(template_name, template, allowed_tokens)
        self.template_name = template_name
        self.template = template
        self.allowed_tokens = allowed_tokens

    def format(self, **kwargs) -> str:
        # raises if kwargs contains any keys not in allowed_tokens
        # if not set(kwargs.keys()) == set(self.allowed_tokens):
        #     raise ValueError(
        #         f"invalid template: {self.template_name} allowed "
        #         + "tokens don't match provided values"
        #     )
        return self.template.format(**kwargs)

    @staticmethod
    def _validate_format_string(
        fmt_string_name: str, fmt_string: str, allowed_args: typing.List[str]
    ):
        def find_all_ch(s: str, ch: str) -> typing.Generator[int, None, None]:
            # find all indices of ch in s
            for i, ltr in enumerate(s):
                if ltr == ch:
                    yield i

        get_logger().debug(
            f"validating template {fmt_string_name} with allowed args {allowed_args}"
        )
        get_logger().debug(f"template: {fmt_string}")

        # raises if fmt_string contains any args not in allowed_args
        allowed_close_brace_indices: typing.Set[int] = set()

        for open_brace_idx in find_all_ch(fmt_string, "{"):
            for allowed_arg in allowed_args:
                idx_end = open_brace_idx + len(allowed_arg) + 1
                next_substr = fmt_string[open_brace_idx : idx_end + 1]
                if next_substr == "{" + allowed_arg + "}":
                    allowed_close_brace_indices.add(idx_end)
                    break
            else:
                raise ValueError(
                    f"invalid template: {fmt_string_name} contains "
                    + f"an argument not in {allowed_args}"
                )
        for close_brace_idx in find_all_ch(fmt_string_name, "}"):
            if close_brace_idx not in allowed_close_brace_indices:
                raise ValueError(
                    f"invalid template: {fmt_string_name} contains "
                    + f"an argument not in {allowed_args}"
                )


class TemplateStore:
    # Purpose: store templates and format messages using them

    def __init__(self):
        self.templates: typing.Dict[str, TemplateMessageFormatter] = {}

    def add_template(
        self, template_name: str, template: str, allowed_tokens: typing.List[str]
    ):
        self.templates[template_name] = TemplateMessageFormatter(
            template_name, template, allowed_tokens
        )

    def format(self, template_name: str, **kwargs) -> str:
        return self.templates[template_name].format(**kwargs)


class Settings(argparse.ArgumentParser):
    # Purpose: reads settings from environment variables and command line
    #          arguments

    ############################################################
    # TODO: move these to a config file ####

    # TODO these strings will be used in .format() calls, so we
    # need to sanitize them to prevent injection attacks

    # this is the number of tokens we reserve for the AI
    # to respond with.

    OOBABOT_MAX_NEW_TOKENS = 250  # STAR
    OOBABOT_MAX_AI_TOKEN_SPACE: int = 2048  # STAR

    # this is set by the AI, and is the maximum length
    # it will understand before it starts to ignore
    # the rest of the prompt_prefix
    # note: we don't currently measure tokens, we just
    # count characters. This is a rough estimate.
    OOBABOT_EST_CHARACTERS_PER_TOKEN = 4

    DISCORD_PROMPT_TEMPLATE = "DISCORD_PROMPT_TEMPLATE"
    DISCORD_PROMPT_TEMPLATE_DEFAULT: str = textwrap.dedent(
        """
        You are in a chat room with multiple participants.
        Below is a transcript of recent messages in the conversation.
        Write the next one to three messages that you would send in this
        conversation, from the point of view of the participant named
        {AI_NAME}.

        {PERSONA}

        All responses you write must be from the point of view of
        {AI_NAME}.

        ### Transcript:
        {MESSAGE_HISTORY}
        {PHOTO_REQUEST}
        {AI_NAME} says:
        """
    )

    DISCORD_PROMPT_HISTORY_LINE_TEMPLATE = "DISCORD_PROMPT_HISTORY_LINE_TEMPLATE"
    DISCORD_PROMPT_HISTORY_LINE_TEMPLATE_DEFAULT: str = textwrap.dedent(
        """
        {DISCORD_USER_NAME} says:
        {DISCORD_USER_MESSAGE}

        """
    )

    DISCORD_PROMPT_PHOTO_COMING_TEMPLATE = "DISCORD_PROMPT_PHOTO_COMING_TEMPLATE"
    DISCORD_PROMPT_PHOTO_COMING_TEMPLATE_DEFAULT: str = textwrap.dedent(
        """
        {AI_NAME}: is currently generating a photo, as requested.
        """
    )

    TEMPLATE_STABLE_DIFFUSION_DETACH_MESSAGE = "STABLE_DIFFUSION_DETACH_MESSAGE"
    TEMPLATE_STABLE_DIFFUSION_DETACH_MESSAGE_DEFAULT: str = textwrap.dedent(
        """
        {DISCORD_USER_NAME} tried to make an image with the prompt:
            '{PHOTO_PROMPT}'
        ...but couldn't find a suitable one.
        """
    )

    TEMPLATE_STABLE_DIFFUSION_IMAGE_MESSAGE = "STABLE_DIFFUSION_IMAGE_MESSAGE"
    TEMPLATE_STABLE_DIFFUSION_IMAGE_MESSAGE_DEFAULT: str = textwrap.dedent(
        """
        {DISCORD_USER_NAME}, is this what you wanted?
        If no choice is made, this message will 💣 self-destuct 💣 in 3 minutes.
        """
    )

    DISCORD_HISTORY_LINES_TO_SUPPLY = 20  # STAR

    DISCORD_HISTORY_EST_CHARACTERS_PER_LINE = 30

    # some non-zero chance of responding to a message,  even if
    # it wasn't addressed directly to the bot.  We'll only do this
    # if we have posted to the same channel within the last

    DISCORD_TIME_VS_RESPONSE_CHANCE = [
        # (seconds, base % chance of an unsolicited response)
        (10.0, 80.0),
        (60.0, 40.0),
        (120.0, 20.0),
    ]

    # increased chance of responding to a message if it ends with
    # a question mark or exclamation point
    DISCORD_INTERROBANG_BONUS = 0.4

    DISCORD_REPETITION_THRESHOLD = 1

    OOBABOOGA_STREAMING_URI_PATH: str = "/api/v1/stream"

    # STAR
    OOBABOOGA_DEFAULT_REQUEST_PARAMS: dict[
        str, bool | float | int | str | typing.List[typing.Any]
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

    # STAR
    STABLE_DIFFUSION_DEFAULT_IMG_WIDTH: int = 512

    # STAR
    STABLE_DIFFUSION_DEFAULT_IMG_HEIGHT: int = STABLE_DIFFUSION_DEFAULT_IMG_WIDTH

    # STAR
    STABLE_DIFFUSION_DEFAULT_STEPS: int = 30

    STABLE_DIFFUSION_API_URI_PATH: str = "/sdapi/v1/"

    HTTP_CLIENT_TIMEOUT_SECONDS: aiohttp.ClientTimeout = aiohttp.ClientTimeout(
        total=None,
        connect=None,
        sock_connect=5.0,
        sock_read=5.0,
    )

    # ENVIRONMENT VARIABLES ####

    DISCORD_TOKEN_ENV_VAR: str = "DISCORD_TOKEN"
    DISCORD_TOKEN: str = os.environ.get(DISCORD_TOKEN_ENV_VAR, "")

    OOBABOT_PERSONA_ENV_VAR: str = "OOBABOT_PERSONA"
    OOBABOT_PERSONA: str = os.environ.get(OOBABOT_PERSONA_ENV_VAR, "")

    DEFAULT_WAKEWORDS: typing.List[str] = ["oobabot"]
    DEFAULT_URL: str = "ws://localhost:5005"

    # use this prompt for "age_restricted" Dsicord channels
    #  i.e. channel.nsfw is true
    DEFAULT_SD_NEGATIVE_PROMPT_NSFW: str = (
        "animal harm, "
        + "suicide, self-harm, "
        + "excessive violence, "
        + "naked children, child sexualization, lolicon"
    )

    # use this prompt for non-age-restricted channels
    DEFAULT_SD_NEGATIVE_PROMPT: str = (
        DEFAULT_SD_NEGATIVE_PROMPT_NSFW + ", sexually explicit content"
    )

    def __init__(self):
        self._settings = None
        self.wakewords = []

        self.template_store = TemplateStore()

        self.template_store.add_template(
            self.DISCORD_PROMPT_TEMPLATE,
            self.DISCORD_PROMPT_TEMPLATE_DEFAULT,
            ["AI_NAME", "PERSONA", "MESSAGE_HISTORY", "PHOTO_REQUEST"],
        )

        self.template_store.add_template(
            self.DISCORD_PROMPT_HISTORY_LINE_TEMPLATE,
            self.DISCORD_PROMPT_HISTORY_LINE_TEMPLATE_DEFAULT,
            ["DISCORD_USER_NAME", "DISCORD_USER_MESSAGE"],
        )
        self.template_store.add_template(
            self.DISCORD_PROMPT_PHOTO_COMING_TEMPLATE,
            self.DISCORD_PROMPT_PHOTO_COMING_TEMPLATE_DEFAULT,
            ["AI_NAME"],
        )
        self.template_store.add_template(
            self.TEMPLATE_STABLE_DIFFUSION_DETACH_MESSAGE,
            self.TEMPLATE_STABLE_DIFFUSION_DETACH_MESSAGE_DEFAULT,
            ["DISCORD_USER_NAME", "PHOTO_PROMPT"],
        )

        self.template_store.add_template(
            self.TEMPLATE_STABLE_DIFFUSION_IMAGE_MESSAGE,
            self.TEMPLATE_STABLE_DIFFUSION_IMAGE_MESSAGE_DEFAULT,
            ["DISCORD_USER_NAME", "PHOTO_PROMPT"],
        )

        super().__init__(
            description="Discord bot for oobabooga's text-generation-webui",
            epilog="Also, to authenticate to Discord, you must set the "
            + "environment variable:\n"
            f"\t{self.DISCORD_TOKEN_ENV_VAR} = <your bot's discord token>",
        )

        ###########################################################
        # Discord Settings

        discord_group = self.add_argument_group("Discord Settings")
        discord_group.add_argument(
            "--ai-name",
            type=str,
            default="oobabot",
            help="Name of the AI to use for requests.  "
            + "This can be whatever you want, but might make sense "
            + "to be the name of the bot in Discord.",
        )
        discord_group.add_argument(
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
        discord_group.add_argument(
            "--ignore-dms",
            default=False,
            help="If set, the bot will ignore direct messages.",
            action="store_true",
        )

        ###########################################################
        # Oobabooga Settings

        oobabooga_group = self.add_argument_group("Oobabooga Seetings")
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
            "--persona",
            type=str,
            default=self.OOBABOT_PERSONA,
            help="This prefix will be added in front of every user-supplied "
            + "request.  This is useful for setting up a 'character' for the "
            + "bot to play.  Alternatively, this can be set with the "
            + f"{self.OOBABOT_PERSONA_ENV_VAR} environment variable.",
        )

        oobabooga_group.add_argument(
            "--log-all-the-things",
            default=False,
            help="Prints all oobabooga requests and responses in their "
            + "entirety to STDOUT",
            action="store_true",
        )

        ###########################################################
        # Stable Diffusion Settings

        stable_diffusion_group = self.add_argument_group("Stable Diffusion Settings")
        stable_diffusion_group.add_argument(
            "--stable-diffusion-url",
            type=str,
            default=None,
            help="URL for an AUTOMATIC1111 Stable Diffusion server",
        )
        stable_diffusion_group.add_argument(
            "--stable-diffusion-sampler",
            type=str,
            default=None,
            help="Sampler to use when generating images.  If not specified, the one "
            + "set on the AUTOMATIC1111 server will be used.",
        )
        stable_diffusion_group.add_argument(
            "--stable-diffusion-negative-prompt",
            type=str,
            default=self.DEFAULT_SD_NEGATIVE_PROMPT,
            help="Negative prompt to use when generating images.  This will discourage"
            + " Stable Diffusion from generating images with the specified content.  "
            + "By default, this is set to follow Discord's TOS.",
        )
        stable_diffusion_group.add_argument(
            "--stable-diffusion-negative-prompt-nsfw",
            type=str,
            default=self.DEFAULT_SD_NEGATIVE_PROMPT_NSFW,
            help="Negative prompt to use when generating images in a channel marked as"
            + "'Age-Restricted'.  By default, this follows the Discord TOS by allowing "
            + "some sexual content forbidden in non-age-restricted channels.",
        )

    def settings(self) -> dict[str, str]:
        if self._settings is None:
            self._settings = self.parse_args().__dict__

            # this is a bit of a hack, but by doing this with
            # non-str settings, we can add stronger type hints
            self.wakewords = self._settings.pop("wakewords")
            self.log_all_the_things = self._settings.pop("log_all_the_things")
            self.stable_diffusion_url = self._settings.pop("stable_diffusion_url")
            self.stable_diffusion_sampler = self._settings.pop(
                "stable_diffusion_sampler"
            )
            self.ignore_dms = self._settings.pop("ignore_dms")

            # either we're using a local REPL, or we're connecting to Discord.
            # assume the user wants to connect to Discord
            if not self.DISCORD_TOKEN:
                msg = (
                    f"Please set the '{Settings.DISCORD_TOKEN_ENV_VAR}' "
                    + "environment variable to your bot's discord token."
                )
                # will exit() after printing
                self.error(msg)

        return self._settings

    def __getattr__(self, name) -> str:
        return self.settings().get(name, "")

    def __repr__(self) -> str:
        return super().__repr__()
