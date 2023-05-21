#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
"""
Bot entrypoint.
"""

import asyncio
import contextlib
import signal
import sys
import threading
import typing

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


# this warning causese more harm than good here
# pylint: disable=W0201
class Oobabot:
    """
    Main bot class.  Load settings, creates helper objects,
    and invokes the bot loop.
    """

    def __init__(
        self,
        cli_args: typing.List[str],
    ):
        self.startup_lock = threading.Lock()
        self.settings = settings.Settings()

        self.settings.load(cli_args)

    def run(self):
        # we'll release this after begin() is called
        with self.startup_lock:
            self._begin()

            if self.settings.general_settings.get("help"):
                self.settings.print_help()
                return

            if self.settings.general_settings.get("generate_config"):
                self.settings.write_sample_config(out_stream=sys.stdout)
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

            self._prepare_connections()

        asyncio.run(self._init_then_start())

    def _our_own_main(self) -> bool:
        return threading.current_thread() == threading.main_thread()

    def _begin(self):
        fancy_logger.init_logging(
            level=self.settings.discord_settings.get_str("log_level"),
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
            except http_client.OobaHttpClientError as err:
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

    # opens http connections to our services,
    # then connects to Discord
    async def _init_then_start(self):
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
            finally:
                await self.discord_bot.close()

    def stop(self):
        """
        Stops the bot, if it's running.  Safe to be called
        from a separate thread from the one that called run().
        """
        if self.discord_bot is None:
            return None
        with self.startup_lock:
            future = asyncio.run_coroutine_threadsafe(
                self.discord_bot.close(),
                self.discord_bot.loop,
            )
        return future.result()

    def test_discord_token(self, discord_token: str) -> bool:
        """
        Tests a discord token to see if it's valid.
        Returns True if it was able to connect with the token, False if it isn't.
        """
        return asyncio.run(discord_utils.test_discord_token(discord_token))


# pylint: enable=W0201


def main():
    # create the object and load our settings
    oobabot = Oobabot(sys.argv[1:])
    # start the loop
    oobabot.run()
