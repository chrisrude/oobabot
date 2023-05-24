#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""
Bot entrypoint.
"""

import asyncio
import concurrent.futures
import contextlib
import signal
import sys
import threading
import typing

import discord

from oobabot import bot_commands
from oobabot import decide_to_respond
from oobabot import discord_bot
from oobabot import discord_utils
from oobabot import fancy_logger
from oobabot import http_client
from oobabot import image_generator
from oobabot import ooba_client
from oobabot import persona
from oobabot import prompt_generator
from oobabot import repetition_tracker
from oobabot import response_stats
from oobabot import sd_client
from oobabot import settings
from oobabot import templates


# this warning causes more harm than good here
# pylint: disable=W0201
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

    Class Methods:
        test_discord_token: Test a discord token to see if it's valid.
            Requires Internet access.
        generate_invite_url: Generate a URL that can be used to invite
            the bot to a server.
    """

    def __init__(
        self,
        cli_args: typing.List[str],
    ):
        """
        Initialize the bot, and load settings from the command line,
        environment variables, and config file.  These will be
        available in self.settings.

        self.settings is an :py:class:`oobabot.settings.Settings` object.
        """
        self.startup_lock = threading.Lock()
        self.settings = settings.Settings()

        self.settings.load(cli_args)

    def start(self):
        """
        Start the bot.  Blocks until the bot exits.

        When running from the CLI, the bot would normally exit
        when the user presses Ctrl-C.  Or otherwise sends a SIGINT
        or SIGTERM signal.

        This is also where one-off commands are run in CLI mode:
         - help: Print help and exit
         - generate_config: Print a the config file and exit
         - invite_url: Print a URL that can be used to invite the bot

        When running inside another process, the bot will exit
        when another thread calls stop().
        """

        with self.startup_lock:
            self._begin()

            if self.settings.general_settings.get("help"):
                self.settings.print_help()
                return

            if self.settings.general_settings.get("generate_config"):
                self.settings.write_to_stream(out_stream=sys.stdout)
                return

            if not self.settings.discord_settings.get("discord_token"):
                msg = (
                    f"Please set the '{self.settings.DISCORD_TOKEN_ENV_VAR}' "
                    + "environment variable to your bot's discord token."
                )
                print(msg, file=sys.stderr)
                if self._our_own_main():
                    sys.exit(1)
                else:
                    raise RuntimeError(msg)

            if self.settings.general_settings.get("invite_url"):
                url = self.generate_invite_url(
                    self.settings.discord_settings.get_str("discord_token")
                )
                print(url)
                return

            self._prepare_connections()

        asyncio.run(self._init_then_start())

    def _our_own_main(self) -> bool:
        """
        Returns True if we're running from the CLI, False if we're
        running inside another process.
        """
        return threading.current_thread() == threading.main_thread()

    def _begin(self):
        """
        Called after we've loaded our configuration but before we
        start the bot.  This is a good place to do any one-time setup
        for helper objects.
        """

        fancy_logger.init_logging(
            level=self.settings.discord_settings.get_str("log_level"),
            log_to_console=self._our_own_main(),
        )

        # templates used to generate prompts to send to the AI
        # as well as for some UI elements
        self.template_store = templates.TemplateStore(
            settings=self.settings.template_settings.get_all()
        )

        ########################################################
        # Connect to Oobabooga

        self.ooba_client = ooba_client.OobaClient(
            settings=self.settings.oobabooga_settings.get_all(),
        )

        ########################################################
        # Connect to Stable Diffusion, if configured

        self.stable_diffusion_client = None
        sd_settings = self.settings.stable_diffusion_settings.get_all()
        if sd_settings["stable_diffusion_url"]:
            self.stable_diffusion_client = sd_client.StableDiffusionClient(
                settings=sd_settings,
            )

        ########################################################
        # Bot logic

        self.persona = persona.Persona(
            persona_settings=self.settings.persona_settings.get_all()
        )

        # decides which messages the bot will respond to
        self.decide_to_respond = decide_to_respond.DecideToRespond(
            discord_settings=self.settings.discord_settings.get_all(),
            persona=self.persona,
            interrobang_bonus=self.settings.DECIDE_TO_RESPOND_INTERROBANG_BONUS,
            time_vs_response_chance=self.settings.TIME_VS_RESPONSE_CHANCE,
        )

        # once we decide to respond, this generates a prompt
        # to send to the AI, given a message history
        self.prompt_generator = prompt_generator.PromptGenerator(
            discord_settings=self.settings.discord_settings.get_all(),
            oobabooga_settings=self.settings.oobabooga_settings.get_all(),
            persona=self.persona,
            template_store=self.template_store,
        )

        # tracks of the time spent on responding, success rate, etc.
        self.response_stats = response_stats.AggregateResponseStats(
            fn_get_total_tokens=lambda: self.ooba_client.total_response_tokens
        )

        # generates images, if stable diffusion is configured
        # also includes a UI to regenerate images on demand
        self.image_generator = None
        if self.stable_diffusion_client is not None:
            self.image_generator = image_generator.ImageGenerator(
                ooba_client=self.ooba_client,
                persona_settings=self.settings.persona_settings.get_all(),
                prompt_generator=self.prompt_generator,
                sd_settings=self.settings.stable_diffusion_settings.get_all(),
                stable_diffusion_client=self.stable_diffusion_client,
                template_store=self.template_store,
            )

        # if a bot sees itself repeating a message over and over,
        # it will keep doing so forever.  This attempts to fix that.
        # by looking for repeated responses, and deciding how far
        # back in history the bot can see.
        self.repetition_tracker = repetition_tracker.RepetitionTracker(
            repetition_threshold=self.settings.REPETITION_TRACKER_THRESHOLD
        )

        self.bot_commands = bot_commands.BotCommands(
            decide_to_respond=self.decide_to_respond,
            repetition_tracker=self.repetition_tracker,
            persona=self.persona,
            discord_settings=self.settings.discord_settings.get_all(),
            template_store=self.template_store,
        )

        self.discord_bot = None

        if self._our_own_main():
            # if we're running as a worker thread in another process,
            # we can't (and shouldn't) register
            def exit_handler(signum, _frame):
                sig_name = signal.Signals(signum).name
                fancy_logger.get().info("Received signal %s, exiting...", sig_name)
                self.response_stats.write_stat_summary_to_log()
                sys.exit(0)

            signal.signal(signal.SIGINT, exit_handler)
            signal.signal(signal.SIGTERM, exit_handler)

    def _prepare_connections(self):
        ########################################################
        # Test connection to services
        for client in [self.ooba_client, self.stable_diffusion_client]:
            if client is None:
                continue

            fancy_logger.get().info("%s is at %s", client.service_name, client.base_url)
            try:
                client.test_connection()
                fancy_logger.get().info("Connected to %s!", client.service_name)
            except (ValueError, http_client.OobaHttpClientError) as err:
                fancy_logger.get().error(
                    "Could not connect to %s server: [%s]",
                    client.service_name,
                    client.base_url,
                )
                fancy_logger.get().error("Please check the URL and try again.")
                if err.__cause__ is not None:
                    fancy_logger.get().error("Reason: %s", err.__cause__)
                if self._our_own_main():
                    sys.exit(1)
                else:
                    raise

        ########################################################
        # Connect to Discord

        fancy_logger.get().info("Connecting to Discord... ")
        self.discord_bot = discord_bot.DiscordBot(
            bot_commands=self.bot_commands,
            decide_to_respond=self.decide_to_respond,
            discord_settings=self.settings.discord_settings.get_all(),
            ooba_client=self.ooba_client,
            image_generator=self.image_generator,
            persona=self.persona,
            prompt_generator=self.prompt_generator,
            repetition_tracker=self.repetition_tracker,
            response_stats=self.response_stats,
        )

    async def _init_then_start(self):
        """
        Opens HTTP connections to oobabooga and stable diffusion,
        then connects to Discord.  Blocks until the bot is stopped.
        """
        if self.discord_bot is None:
            raise RuntimeError("Discord bot not initialized")

        async with contextlib.AsyncExitStack() as stack:
            for context_manager in [
                self.ooba_client,
                self.stable_diffusion_client,
            ]:
                if context_manager is not None:
                    await stack.enter_async_context(context_manager)

            try:
                await self.discord_bot.start(
                    self.settings.discord_settings.get_str("discord_token")
                )
            except discord.LoginFailure as err:
                fancy_logger.get().error("Could not log in to Discord: %s", err)
                fancy_logger.get().error("Please check the token and try again.")
                if self._our_own_main():
                    sys.exit(1)
            finally:
                await self.discord_bot.close()
        fancy_logger.get().info("Disconnected from Discord.")

    def stop(self, wait_timeout: float = 5.0) -> None:
        """
        Stops the bot, if it's running.  Safe to be called
        from a separate thread from the one that called run().

        Blocks until the bot is gracefully stopped.
        """
        if self.discord_bot is None:
            return

        async def close_and_set() -> None:
            if self.discord_bot is None:
                return
            await self.discord_bot.close()

        with self.startup_lock:
            try:
                # if discord is already stopped, then their .loop is set
                # _MissingSentinel.  So instead check if it's still connected.
                if self.discord_bot.is_closed():
                    fancy_logger.get().info("Discord bot already stopped.")
                    return

                future = asyncio.run_coroutine_threadsafe(
                    close_and_set(),
                    self.discord_bot.loop,
                )
                future.result(timeout=wait_timeout)
            except RuntimeError:
                # this can happen if the main application is shutting down
                fancy_logger.get().warning("Discord bot is already stopped.")
            except concurrent.futures.TimeoutError:
                fancy_logger.get().warning(
                    "Discord bot did not stop in time, it might be busted."
                )

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


# pylint: enable=W0201


def main():
    # create the object and load our settings
    oobabot = Oobabot(sys.argv[1:])
    # start the loop
    oobabot.start()
