#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#

import asyncio
import contextlib
import signal
import sys
import typing

from oobabot import bot_commands
from oobabot import decide_to_respond
from oobabot import discord_bot
from oobabot import fancy_logger
from oobabot import http_client
from oobabot import image_generator
from oobabot import ooba_client
from oobabot import prompt_generator
from oobabot import repetition_tracker
from oobabot import response_stats
from oobabot import sd_client
from oobabot import settings
from oobabot import templates


class OobaBot:
    def __init__(self, cli_args: typing.List[str]):
        fancy_logger.init_logging()

        self.settings = settings.Settings()
        self.settings.load(cli_args)

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

        # decides which messages the bot will respond to
        self.decide_to_respond = decide_to_respond.DecideToRespond(
            discord_settings=self.settings.discord_settings.get_all(),
            persona_settings=self.settings.persona_settings.get_all(),
            interrobang_bonus=self.settings.DECIDE_TO_RESPOND_INTERROBANG_BONUS,
            time_vs_response_chance=self.settings.TIME_VS_RESPONSE_CHANCE,
        )

        # once we decide to respond, this generates a prompt
        # to send to the AI, given a message history
        self.prompt_generator = prompt_generator.PromptGenerator(
            discord_settings=self.settings.discord_settings.get_all(),
            oobabooga_settings=self.settings.oobabooga_settings.get_all(),
            persona_settings=self.settings.persona_settings.get_all(),
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
                stable_diffusion_client=self.stable_diffusion_client,
                image_words=[
                    str(w)
                    for w in self.settings.stable_diffusion_settings.get_list(
                        "image_words"
                    )
                ],
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
            persona_settings=self.settings.persona_settings.get_all(),
            discord_settings=self.settings.discord_settings.get_all(),
            template_store=self.template_store,
        )

        def sigint_handler(_signum, _frame):
            fancy_logger.get().info("Received SIGINT, exiting...")
            self.response_stats.write_stat_summary_to_log()
            sys.exit(1)

        signal.signal(signal.SIGINT, sigint_handler)

    def run(self):
        if self.settings.general_settings.get("generate_config"):
            self.settings.write_sample_config(out_stream=sys.stdout)
            sys.exit(0)

        if not self.settings.discord_settings.get("discord_token"):
            msg = (
                f"Please set the '{self.settings.DISCORD_TOKEN_ENV_VAR}' "
                + "environment variable to your bot's discord token."
            )
            print(msg, file=sys.stderr)
            sys.exit(1)

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
                sys.exit(1)

        ########################################################
        # Connect to Discord

        fancy_logger.get().info("Connecting to Discord... ")
        bot = discord_bot.DiscordBot(
            self.ooba_client,
            decide_to_respond=self.decide_to_respond,
            prompt_generator=self.prompt_generator,
            repetition_tracker=self.repetition_tracker,
            response_stats=self.response_stats,
            image_generator=self.image_generator,
            bot_commands=self.bot_commands,
            persona_settings=self.settings.persona_settings.get_all(),
            discord_settings=self.settings.discord_settings.get_all(),
        )

        # opens http connections to our services,
        # then connects to Discord
        async def init_then_start():
            async with contextlib.AsyncExitStack() as stack:
                for context_manager in [
                    self.ooba_client,
                    self.stable_diffusion_client,
                ]:
                    if context_manager is not None:
                        await stack.enter_async_context(context_manager)

                try:
                    await bot.start(
                        self.settings.discord_settings.get_str("discord_token")
                    )
                finally:
                    await bot.close()

        asyncio.run(init_then_start())


def main():
    oobabot = OobaBot(sys.argv[1:])
    oobabot.run()
