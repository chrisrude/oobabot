#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#

import asyncio
import signal
import sys

import aiohttp

from oobabot.decide_to_respond import DecideToRespond
from oobabot.discord_bot import DiscordBot
from oobabot.fancy_logging import get_logger
from oobabot.fancy_logging import init_logging
from oobabot.image_generator import ImageGenerator
from oobabot.ooba_client import OobaClient
from oobabot.ooba_client import OobaClientError
from oobabot.prompt_generator import PromptGenerator
from oobabot.repetition_tracker import RepetitionTracker
from oobabot.response_stats import AggregateResponseStats
from oobabot.sd_client import StableDiffusionClient
from oobabot.settings import Settings
from oobabot.templates import TemplateStore


def verify_client(client, service_name, url):
    async def try_setup(client):
        assert client is not None
        async with client:
            await client.setup()

    logger = get_logger()
    logger.info(f"{service_name} is at {url}")
    try:
        asyncio.run(try_setup(client))
    except (OobaClientError, aiohttp.ClientConnectionError) as e:
        logger.error(f"Could not connect to {service_name} server: [{url}]")
        logger.error("Please check the URL and try again.")
        logger.error(f"Reason: {e}")
        sys.exit(1)
    logger.info(f"Connected to {service_name}!")


def main():
    logger = init_logging()

    settings = Settings()
    settings.load()
    if not settings.DISCORD_TOKEN:
        msg = (
            f"Please set the '{Settings.DISCORD_TOKEN_ENV_VAR}' "
            + "environment variable to your bot's discord token."
        )
        # will exit() after printing
        settings.error(msg)

    aggregate_response_stats = None

    def sigint_handler(_signum, _frame):
        logger.info("Received SIGINT, exiting...")
        if aggregate_response_stats is not None:
            aggregate_response_stats.write_stat_summary_to_log()
        exit(1)

    signal.signal(signal.SIGINT, sigint_handler)

    ########################################################
    # Connect to Oobabooga

    ooba_client = OobaClient(settings.base_url)
    verify_client(ooba_client, "Oobabooga", settings.base_url)

    ########################################################
    # Connect to Stable Diffusion, if configured

    stable_diffusion_client = None
    if settings.stable_diffusion_url:
        stable_diffusion_client = StableDiffusionClient(
            base_url=settings.stable_diffusion_url,
            negative_prompt=settings.stable_diffusion_negative_prompt,
            negative_prompt_nsfw=settings.stable_diffusion_negative_prompt_nsfw,
            image_width=settings.image_width,
            image_height=settings.image_height,
            steps=settings.diffusion_steps,
            desired_sampler=settings.stable_diffusion_sampler,
        )
        verify_client(
            stable_diffusion_client,
            "Stable Diffusion",
            settings.stable_diffusion_url,
        )

    ########################################################
    # Bot logic

    # decides which messages the bot will respond to
    decide_to_respond = DecideToRespond(
        settings.wakewords,
        settings.ignore_dms,
        settings.DECIDE_TO_RESPOND_INTERROBANG_BONUS,
        settings.DECIDE_TO_RESPOND_TIME_VS_RESPONSE_CHANCE,
    )

    # templates used to generate prompts to send to the AI
    # as well as for some UI elements
    template_store = TemplateStore()

    # once we decide to respond, this generates a prompt
    # to send to the AI, given a message history
    prompt_generator = PromptGenerator(
        ai_name=settings.ai_name,
        persona=settings.persona,
        history_lines=settings.history_lines,
        token_space=settings.OOBABOT_MAX_AI_TOKEN_SPACE,
        template_store=template_store,
    )

    # tracks of the time spent on responding, success rate, etc.
    aggregate_response_stats = AggregateResponseStats(
        fn_get_total_tokens=lambda: ooba_client.total_response_tokens
    )

    # generates images, if stable diffusion is configured
    # also includes a UI to regenerate images on demand
    image_generator = None
    if stable_diffusion_client is not None:
        image_generator = ImageGenerator(
            stable_diffusion_client=stable_diffusion_client,
            image_words=settings.image_words,
            template_store=template_store,
        )

    # if a bot sees itself repeating a message over and over,
    # it will keep doing so forever.  This attempts to fix that.
    # by looking for repeated responses, and deciding how far
    # back in history the bot can see.
    repetition_tracker = RepetitionTracker(
        repetition_threshold=Settings.REPETITION_TRACKER_THRESHOLD
    )

    ########################################################
    # Connect to Discord

    logger.info("Connecting to Discord... ")
    bot = DiscordBot(
        ooba_client,
        decide_to_respond=decide_to_respond,
        prompt_generator=prompt_generator,
        repetition_tracker=repetition_tracker,
        aggregate_response_stats=aggregate_response_stats,
        image_generator=image_generator,
        ai_name=settings.ai_name,
        persona=settings.persona,
        ignore_dms=settings.ignore_dms,
        log_all_the_things=settings.log_all_the_things,
    )

    # opens http connections to our services,
    # then connects to Discord
    async def init_then_start():
        if stable_diffusion_client is not None:
            async with stable_diffusion_client:
                async with ooba_client:
                    await bot.start(settings.DISCORD_TOKEN)
        else:
            async with ooba_client:
                await bot.start(settings.DISCORD_TOKEN)

    asyncio.run(init_then_start())
