#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#

import asyncio
import signal
import sys

import aiohttp

from oobabot.discord_bot import DiscordBot
from oobabot.fancy_logging import get_logger
from oobabot.fancy_logging import init_logging
from oobabot.ooba_client import OobaClient
from oobabot.ooba_client import OobaClientError
from oobabot.sd_client import StableDiffusionClient
from oobabot.settings import Settings


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

    bot = None

    def sigint_handler(_signum, _frame):
        logger.info("Received SIGINT, exiting...")
        if bot:
            bot.log_stats()
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
            settings.stable_diffusion_url,
            negative_prompt=settings.stable_diffusion_negative_prompt,
            negative_prompt_nsfw=settings.stable_diffusion_negative_prompt_nsfw,
            desired_sampler=settings.stable_diffusion_sampler,
        )
        verify_client(
            stable_diffusion_client,
            "Stable Diffusion",
            settings.stable_diffusion_url,
        )

    ########################################################
    # Connect to Discord

    logger.info("Connecting to Discord... ")
    bot = DiscordBot(
        ooba_client,
        settings=settings,
        stable_diffusion_client=stable_diffusion_client,
    )
    coroutine = bot.start()

    asyncio.run(coroutine)
