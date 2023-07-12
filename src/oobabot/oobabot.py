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
from oobabot import types
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
            voice transcript, or an empty list if the bot is not
            in a voice channel.
        fancy_author_info: Given a Discord user_id, returns a struct
            describing a user's display name, accent color, and icon.
            Bot must be running for this to work.

    Class Methods:
        test_discord_token: Test a discord token to see if it's valid.
            Requires Internet access.
        generate_invite_url: Generate a URL that can be used to invite
            the bot to a server.
    """

    def __init__(
        self,
        cli_args: typing.List[str],
        running_from_cli: bool = False,
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
            self.settings.load(cli_args, running_from_cli=running_from_cli)
        except settings.SettingsError as err:
            print("\n".join([str(arg) for arg in list(err.args)]), file=sys.stderr)
            raise

        fancy_logger.init_logging(
            level=self.settings.discord_settings.get_str("log_level"),
            running_from_cli=running_from_cli,
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

    # pylint: disable=R1732
    def stop(self) -> bool:
        """
        Stop the bot.  Blocks until the bot exits.
        """
        result = self.runtime_lock.acquire(timeout=5)
        if result:
            try:
                if self.runtime is not None:
                    self.runtime.stop()
            finally:
                self.runtime_lock.release()
        else:
            fancy_logger.get().error(
                "Failed to acquire runtime lock, could not shutdown gracefully"
            )
        self.runtime = None
        return result

    # pylint: enable=R1732

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
        exe_location, model_location = discord_utils.validate_discrivener_locations(
            self.settings.discord_settings.get_str("discrivener_location"),
            self.settings.discord_settings.get_str("discrivener_model_location"),
        )
        return exe_location is not None and model_location is not None

    @property
    def current_voice_transcript(
        self,
    ) -> typing.List["types.VoiceMessage"]:
        """
        If the bot is currently in a voice channel, returns the transcript
        of what's being said.  Otherwise, returns an empty list.
        """
        client = voice_client.VoiceClient.current_instance
        if client is None:
            return []
        transcript = client.current_transcript()
        if transcript is None:
            return []
        return transcript.message_buffer.get()

    def fancy_author_info(self, user_id: int) -> typing.Optional["types.FancyAuthor"]:
        """
        Returns a FancyAuthor object for the given user_id.

        This will only work if the bot is running and connected
        to a voice channel, and then only for users who are
        in that discord server.

        We do this instead of a more general lookup because
        this is what lets us get more information, including
        the server-specific nickname, color, and icon.
        """
        client = voice_client.VoiceClient.current_instance
        if client is None:
            return None
        return discord_utils.author_from_user_id(user_id, client.guild)

    def log_count(self) -> int:
        """
        Returns the current number of times the log has been
        appended to.
        """
        return fancy_logger.recent_logs.changes

    def logs(self) -> typing.List[str]:
        """
        Returns a list of the most recent log messages.
        """
        return fancy_logger.recent_logs.get_all()


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
        oobabot = Oobabot(sys.argv[1:], running_from_cli=True)
    except settings.SettingsError:
        sys.exit(1)

    # if we're running as a worker thread in another process,
    # we can't (and shouldn't) register
    def exit_handler(signum, _frame):
        sig_name = signal.Signals(signum).name
        fancy_logger.get().info("Received signal %s, exiting...", sig_name)
        result = oobabot.stop()
        sys.exit(not result)

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

    sys.excepthook = fancy_logger.excepthook

    oobabot.start()


def main():
    run_cli()
