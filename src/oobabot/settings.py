import argparse
import os
import typing


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
    OOBABOT_MAX_AI_TOKEN_SPACE: int = 2048

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

    ############################################################
    # These are the default settings for the bot.  They can be
    # overridden by environment variables or command line arguments.

    # number lines back in the message history to include in the prompt
    DEFAULT_HISTORY_LINES_TO_SUPPLY = 20

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
            "--history-lines",
            type=int,
            default=self.DEFAULT_HISTORY_LINES_TO_SUPPLY,
            help="Number of lines of history to supply to the AI.  "
            + "This is the number of lines of history that the AI will "
            + "see when generating a response.  The default is "
            + f"{self.DEFAULT_HISTORY_LINES_TO_SUPPLY}.",
        )
        discord_group.add_argument(
            "--ignore-dms",
            default=False,
            help="If set, the bot will ignore direct messages.",
            action="store_true",
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

        ###########################################################
        # Oobabooga Settings

        oobabooga_group = self.add_argument_group("Oobabooga Seetings")
        oobabooga_group.add_argument(
            "--ai-name",
            type=str,
            default="oobabot",
            help="Name of the AI to use for requests.  "
            + "This can be whatever you want, but might make sense "
            + "to be the name of the bot in Discord.",
        )
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
            help="Prints all oobabooga requests and responses in their "
            + "entirety to STDOUT",
            action="store_true",
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

        ###########################################################
        # Stable Diffusion Settings

        stable_diffusion_group = self.add_argument_group("Stable Diffusion Settings")
        stable_diffusion_group.add_argument(
            "--diffusion-steps",
            type=int,
            default=self.DEFAULT_STABLE_DIFFUSION_STEPS,
            help="Number of diffusion steps to take when generating an image.  "
            + f"The default is {self.DEFAULT_STABLE_DIFFUSION_STEPS}.",
        )
        stable_diffusion_group.add_argument(
            "--image-height",
            type=int,
            default=self.DEFAULT_STABLE_DIFFUSION_IMAGE_SIZE,
            help="Size of images to generate.  This is the height of the image "
            + "in pixels.  The default is "
            + f"{self.DEFAULT_STABLE_DIFFUSION_IMAGE_SIZE}.",
        )
        stable_diffusion_group.add_argument(
            "--image-width",
            type=int,
            default=self.DEFAULT_STABLE_DIFFUSION_IMAGE_SIZE,
            help="Size of images to generate.  This is the width of the image "
            + "in pixels.  The default is "
            + f"{self.DEFAULT_STABLE_DIFFUSION_IMAGE_SIZE}.",
        )
        stable_diffusion_group.add_argument(
            "--image-words",
            type=str,
            nargs="*",
            default=self.DEFAULT_IMAGE_WORDS,
            help="One or more words that will indicate the user "
            + "is requeting an image to be generated.",
        )
        stable_diffusion_group.add_argument(
            "--stable-diffusion-sampler",
            "--sd-sampler",
            type=str,
            default=None,
            help="Sampler to use when generating images.  If not specified, the one "
            + "set on the AUTOMATIC1111 server will be used.",
        )
        stable_diffusion_group.add_argument(
            "--stable-diffusion-url",
            "--sd-url",
            type=str,
            default=None,
            help="URL for an AUTOMATIC1111 Stable Diffusion server",
        )
        stable_diffusion_group.add_argument(
            "--sd-negative-prompt",
            type=str,
            default=self.DEFAULT_SD_NEGATIVE_PROMPT,
            help="Negative prompt to use when generating images.  This will discourage"
            + " Stable Diffusion from generating images with the specified content.  "
            + "By default, this is set to follow Discord's TOS.",
        )
        stable_diffusion_group.add_argument(
            "--sd-negative-prompt-nsfw",
            type=str,
            default=self.DEFAULT_SD_NEGATIVE_PROMPT_NSFW,
            help="Negative prompt to use when generating images in a channel marked as"
            + "'Age-Restricted'.",
        )

    def load(self) -> None:
        self._settings = self.parse_args().__dict__

        # Discord Settings
        self.history_lines = self._settings.pop("history_lines")
        self.ignore_dms = self._settings.pop("ignore_dms")
        self.wakewords = self._settings.pop("wakewords")

        # OogaBooga Settings
        self.ai_name = self._settings.pop("ai_name")
        self.base_url = self._settings.pop("base_url")
        print(self.base_url)
        self.log_all_the_things = self._settings.pop("log_all_the_things")
        self.persona = self._settings.pop("persona")

        # Stable Diffusion Settings
        self.diffusion_steps = self._settings.pop("diffusion_steps")
        self.image_height = self._settings.pop("image_height")
        self.image_width = self._settings.pop("image_width")
        self.image_words = self._settings.pop("image_words")
        self.stable_diffusion_negative_prompt = self._settings.pop("sd_negative_prompt")
        self.stable_diffusion_negative_prompt_nsfw = self._settings.pop(
            "sd_negative_prompt_nsfw"
        )
        self.stable_diffusion_sampler = self._settings.pop("stable_diffusion_sampler")
        self.stable_diffusion_url = self._settings.pop("stable_diffusion_url")

    def __repr__(self) -> str:
        return super().__repr__()
