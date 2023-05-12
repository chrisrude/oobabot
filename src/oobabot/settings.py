import argparse
import os
import textwrap
import typing

from oobabot.types import Templates


class Settings(argparse.ArgumentParser):
    # Purpose: reads settings from environment variables and command line
    #          arguments

    ############################################################
    # TODO: move these to a config file ####

    PHOTOWORDS: typing.List[str] = [
        "drawing",
        "photo",
        "pic",
        "picture",
        "image",
        "sketch",
    ]

    # this is the number of tokens we reserve for the AI
    # to respond with.
    OOBABOT_MAX_NEW_TOKENS: int = 250

    # this is the number of tokens the AI has available
    # across its entire request + response
    OOBABOT_MAX_AI_TOKEN_SPACE: int = 2048

    PROMPT_TEMPLATE_DEFAULT: str = textwrap.dedent(
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
        {IMAGE_COMING}
        """
        # note that we don't include the bot's prompt_prefix line here
        # but it will be included in the prompt we send to the AI
    )

    PROMPT_HISTORY_LINE_TEMPLATE_DEFAULT: str = textwrap.dedent(
        """
        {USER_NAME} says:
        {USER_MESSAGE}

        """
    )

    PROMPT_IMAGE_COMING_TEMPLATE_DEFAULT: str = textwrap.dedent(
        """
        {AI_NAME}: is currently generating an image, as requested.
        """
    )

    IMAGE_DETACH_TEMPLATE_DEFAULT: str = textwrap.dedent(
        """
        {USER_NAME} tried to make an image with the prompt:
            '{IMAGE_PROMPT}'
        ...but couldn't find a suitable one.
        """
    )

    IMAGE_CONFIRMATION_TEMPLATE_DEFAULT: str = textwrap.dedent(
        """
        {USER_NAME}, is this what you wanted?
        If no choice is made, this message will 💣 self-destuct 💣 in 3 minutes.
        """
    )

    IMAGE_UNAUTHORIZED_TEMPLATE_DEFAULT: str = textwrap.dedent(
        """
        Sorry, only {USER_NAME} can press the buttons.
        """
    )

    # number lines back in the message history to include in the prompt
    HISTORY_LINES_TO_SUPPLY = 20

    # This is a table of the probability that the bot will respond
    # in an unsolicited manner (i.e. it isn't specifically pinged)
    # to a message, based on how long ago it was pinged in that
    # same channel.
    DECIDE_TO_RESPOND_TIME_VS_RESPONSE_CHANCE: typing.List[
        typing.Tuple[float, float]
    ] = [
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

    STABLE_DIFFUSION_DEFAULT_IMG_WIDTH: int = 512
    STABLE_DIFFUSION_DEFAULT_IMG_HEIGHT: int = STABLE_DIFFUSION_DEFAULT_IMG_WIDTH
    STABLE_DIFFUSION_DEFAULT_STEPS: int = 30

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

    def get_template(self, template_type: Templates) -> str:
        if Templates.IMAGE_DETACH == template_type:
            return self.IMAGE_DETACH_TEMPLATE_DEFAULT

        if Templates.IMAGE_CONFIRMATION == template_type:
            return self.IMAGE_CONFIRMATION_TEMPLATE_DEFAULT

        if Templates.IMAGE_UNAUTHORIZED == template_type:
            return self.IMAGE_UNAUTHORIZED_TEMPLATE_DEFAULT

        if Templates.PROMPT == template_type:
            return self.PROMPT_TEMPLATE_DEFAULT

        if Templates.PROMPT_HISTORY_LINE == template_type:
            return self.PROMPT_HISTORY_LINE_TEMPLATE_DEFAULT

        if Templates.PROMPT_IMAGE_COMING == template_type:
            return self.PROMPT_IMAGE_COMING_TEMPLATE_DEFAULT

        raise ValueError(f"unknown template type: {template_type}")

    def __init__(self):
        self._settings = None
        self.wakewords = []
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
