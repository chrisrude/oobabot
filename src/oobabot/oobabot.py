#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""
Bot entrypoint.
"""

import asyncio
import signal
import sys
import threading
import typing

import oobabot
from oobabot import discord_utils
from oobabot import fancy_logger
from oobabot import runtime
from oobabot import settings
from oobabot import voice_client


class Oobabot:
    """
    Main bot class.  Load settings, creates helper objects,
    and invokes the bot loop.

    Methods:
        constructor: Loads settings from the command line, environment
            variables, and config file.  This config may be changed
            before calling start().
        start: Start the bot.  Blocks until the bot exits.
        stop: Stop the bot.  Blocks until the bot exits.
        is_voice_enabled: Returns True if the bot is configured to
            participate in voice channels.
        current_voice_transcript (property): Returns the current
            voice transcript, or None if voice is not enabled.

    Class Methods:
        test_discord_token: Test a discord token to see if it's valid.
            Requires Internet access.
        generate_invite_url: Generate a URL that can be used to invite
            the bot to a server.
    """

    def __init__(
        self,
        cli_args: typing.List[str],
        log_to_console: bool = False,
    ):
        """
        Initialize the bot, and load settings from the command line,
        environment variables, and config file.  These will be
        available in self.settings.

        self.settings is an :py:class:`oobabot.settings.Settings` object.
        """

        self.runtime: typing.Optional[runtime.Runtime] = None
        # guards access to runtime from multiple threads
        self.runtime_lock = threading.Lock()
        self.settings = settings.Settings()

        try:
            self.settings.load(cli_args)
        except settings.SettingsError as err:
            print("\n".join([str(arg) for arg in list(err.args)]), file=sys.stderr)
            raise

        fancy_logger.init_logging(
            level=self.settings.discord_settings.get_str("log_level"),
            log_to_console=log_to_console,
        )

    def start(self):
        """
        Start the bot.  Blocks until the bot exits.

        When running inside another process, the bot will exit
        when another thread calls stop().  Otherwise it will
        exit when the user presses Ctrl-C, or the process receives
        a SIGTERM or SIGINT signal.
        """
        fancy_logger.get().info(
            "Starting oobabot, core version %s", oobabot.__version__
        )

        with self.runtime_lock:
            self.runtime = runtime.Runtime(self.settings)
            test_passed = self.runtime.test_connections()
            if not test_passed:
                # test_connections will have logged the error
                self.runtime = None
                return

        asyncio.run(self.runtime.run())

    def stop(self):
        """
        Stop the bot.  Blocks until the bot exits.
        """
        with self.runtime_lock:
            if self.runtime is not None:
                self.runtime.stop()
                self.runtime = None

    @classmethod
    def test_discord_token(cls, discord_token: str) -> bool:
        """
        Tests a discord token to see if it's valid.  Can be called from any thread.

        Requires Internet connectivity.

        Returns True if it was able to connect with the token, False if it isn't.
        """
        return asyncio.run(discord_utils.test_discord_token(discord_token))

    @classmethod
    def generate_invite_url(cls, discord_token: str) -> str:
        """
        Generates an invite URL for the bot with the given token.

        Can be called from any thread.  Does not require Internet connectivity.
        """
        ai_user_id = discord_utils.get_user_id_from_token(discord_token)
        return discord_utils.generate_invite_url(ai_user_id)

    def is_voice_enabled(self) -> bool:
        """
        Returns True if the bot is configured to participate in voice channels.

        This checks that both:
         a. discrivener is configured
         b. discrivener is installed
        """
        return discord_utils.is_discrivener_installed(
            self.settings.discord_settings.get_str("discrivener_location"),
            self.settings.discord_settings.get_str("discrivener_model_location"),
        )

    @property
    def current_voice_transcript(
        self,
    ) -> typing.Optional["oobabot.transcript.Transcript"]:
        """
        If the bot is currently in a voice channel, returns the transcript
        of what's being said.  Otherwise, returns None.
        """
        client = voice_client.VoiceClient.current_instance
        if client is None:
            return None
        return client.current_transcript()


def run_cli():
    """
    Run the bot from the command line.  Blocks until the bot exits.

    This is the main entrypoint for the CLI.

    In addition to running the bot, this function also handles
    other CLI commands, such as:
    - help: Print help and exit
    - generate_config: Print a the config file and exit
    - invite_url: Print a URL that can be used to invite the bot
    """

    # create the object and load our settings
    try:
        oobabot = Oobabot(sys.argv[1:], log_to_console=True)
    except settings.SettingsError:
        sys.exit(1)

    # if we're running as a worker thread in another process,
    # we can't (and shouldn't) register
    def exit_handler(signum, _frame):
        sig_name = signal.Signals(signum).name
        fancy_logger.get().info("Received signal %s, exiting...", sig_name)
        oobabot.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, exit_handler)
    signal.signal(signal.SIGTERM, exit_handler)

    if oobabot.settings.general_settings.get("help"):
        oobabot.settings.print_help()
        return

    if oobabot.settings.general_settings.get("generate_config"):
        oobabot.settings.write_to_stream(out_stream=sys.stdout)
        if sys.stdout.isatty():
            print(oobabot.settings.META_INSTRUCTION, file=sys.stderr)
        else:
            print("# oobabot: config.yml output successfully", file=sys.stderr)
        return

    if not oobabot.settings.discord_settings.get("discord_token"):
        msg = (
            f"Please set the '{oobabot.settings.DISCORD_TOKEN_ENV_VAR}' "
            + "environment variable to your bot's discord token."
        )
        print(msg, file=sys.stderr)
        sys.exit(1)

    if oobabot.settings.general_settings.get("invite_url"):
        url = oobabot.generate_invite_url(
            oobabot.settings.discord_settings.get_str("discord_token")
        )
        print(url)
        return

    oobabot.start()


def main():
    run_cli()
