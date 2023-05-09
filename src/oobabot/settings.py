import argparse
import os


class Settings(argparse.ArgumentParser):
    # Purpose: reads settings from environment variables and command line
    #          arguments

    DISCORD_TOKEN_ENV_VAR = "DISCORD_TOKEN"
    DISCORD_TOKEN = os.environ.get(DISCORD_TOKEN_ENV_VAR, "")

    OOBABOT_PERSONA_ENV_VAR = "OOBABOT_PERSONA"
    OOBABOT_PERSONA = os.environ.get(OOBABOT_PERSONA_ENV_VAR, "")

    DEFAULT_WAKEWORDS = ["oobabot"]
    DEFAULT_URL = "ws://localhost:5005"

    # use this prompt for "age_restricted" Dsicord channels
    #  i.e. channel.nsfw is true
    DEFAULT_SD_NEGATIVE_PROMPT_NSFW = (
        "animal harm, "
        + "suicide, self-harm, "
        + "excessive violence, "
        + "naked children, child sexualization, lolicon"
    )

    # use this prompt for non-age-restricted channels
    DEFAULT_SD_NEGATIVE_PROMPT = (
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

            # either we're using a local REPL, or we're connecting to Discord.
            # assume the user wants to connect to Discord
            if not (self.local_repl or self.DISCORD_TOKEN):
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
